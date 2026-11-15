import Foundation

struct WatchPacket: Codable, Sendable {
    let session: UUID, began: Date, sequence: Int, active: Bool
    var bpm: Double?, start: Date?, end: Date?
    var status: String?
    var trial: UUID?, deadline: Date?
    var key: String { "\(session):\(end?.timeIntervalSince1970 ?? 0)" }
    func fresh(at now: Date) -> Bool {
        guard active, let bpm, bpm.isFinite, (20...300).contains(bpm), let start, let end,
              start >= began, end >= start else { return false }
        return (-2...15).contains(now.timeIntervalSince(end))
    }
}
struct WatchFeed {
    private(set) var packet: WatchPacket?
    @discardableResult mutating func receive(_ value: WatchPacket, now: Date = Date()) -> String? {
        guard value.began.timeIntervalSince1970.isFinite, value.began <= now.addingTimeInterval(2), value.sequence >= 0 else { return "invalid_session" }
        if let old = packet {
            guard value.session == old.session ? value.sequence > old.sequence : value.began > old.began else { return "duplicate_out_of_order_or_old_session" }
            if value.session == old.session && !old.active && value.active { return "session_already_ended" }
        }
        packet = value
        return nil
    }
}

#if !os(watchOS)
struct PhoneReading {
    let time: Date, seconds: Double, original: Double?, improved: Double?
    var improvedTime: Date? = nil
}
func automaticPair(_ packet: WatchPacket, history: [PhoneReading], now: Date = Date()) -> WatchPair? {
    guard packet.fresh(at: now), let end = packet.end else { return nil }
    let eligible = history.filter { $0.seconds >= 6 }
    let original = eligible.filter { abs($0.time.timeIntervalSince(end)) <= 2 }
        .min(by: { abs($0.time.timeIntervalSince(end)) < abs($1.time.timeIntervalSince(end)) })
    let improved = eligible.filter { abs(($0.improvedTime ?? $0.time).timeIntervalSince(end)) <= 2 }
        .min(by: { abs(($0.improvedTime ?? $0.time).timeIntervalSince(end)) < abs(($1.improvedTime ?? $1.time).timeIntervalSince(end)) })
    guard original != nil || improved != nil else { return nil }
    return WatchPair(time: improved.map { $0.improvedTime ?? $0.time } ?? original!.time, original: original?.original,
                     improved: improved?.improved, watch: packet.bpm, watchTime: end, automatic: true, originalTime: original?.time)
}
#endif

#if os(iOS) || os(watchOS)
import WatchConnectivity
import Combine

@MainActor final class WatchLink: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = WatchLink()
    @Published var feed = WatchFeed()
    @Published var reachable = false
    @Published var status = "Connecting to companion…"
    @Published var receipt: DiagnosticEvent?
    @Published var acknowledgement: WatchAck?
    var onCommand: ((TrialCommand) -> Void)?
    var onStop: (() -> Void)?
    var diagnostic: ((DiagnosticEvent) -> Void)?
    private var pending: [String: Data] = [:]
    private var outgoing: WatchPacket?
    private var acks: [String: WatchAck] = [:]
    func ack(for trial: UUID, action: TrialCommand.Action) -> WatchAck? { acks["\(trial)/\(action.rawValue)"] }
    override init() {
        super.init()
        guard WCSession.isSupported() else { status = "Watch connection unavailable"; return }
        WCSession.default.delegate = self; WCSession.default.activate()
    }
    private func refresh() {
        let session = WCSession.default
        reachable = session.activationState == .activated && session.isReachable
        #if os(iOS)
        status = !session.isPaired ? "No paired Apple Watch" : !session.isWatchAppInstalled ? "Install Heart Echo on your Watch" : reachable ? "Watch connected" : "Watch offline · requests and readings are queued"
        #else
        status = reachable ? "iPhone connected" : "iPhone offline · readings saved locally and queued"
        #endif
        if session.activationState == .activated {
            let waiting = pending; pending = [:]
            for (key, data) in waiting { transport(data, key: key) }
        }
        diagnostic?(DiagnosticEvent(event: "watch_connection_state", connection: status))
    }
    private func send(_ value: WatchMessage, key: String) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        transport(data, key: key)
    }
    private func transport(_ data: Data, key: String) {
        let session = WCSession.default
        guard session.activationState == .activated else { pending[key] = data; return }
        if key.hasPrefix("command/"), let command = (try? JSONDecoder().decode(WatchMessage.self, from: data))?.command {
            guard command.valid(at: Date()) else { pending.removeValue(forKey: key); return }
            if !session.isReachable { pending[key] = data } else { pending.removeValue(forKey: key) }
        }
        // The system queue survives suspension; direct delivery supplies low-latency updates.
        if !session.outstandingUserInfoTransfers.contains(where: { $0.userInfo["key"] as? String == key }) {
            if session.outstandingUserInfoTransfers.count < 512 || key.hasPrefix("command/") {
                session.transferUserInfo(["chestBPM": data, "key": key])
            } else { diagnostic?(DiagnosticEvent(event: "watch_queue_full", message: "Local log retained; queued reference backlog is full")) }
        }
        if session.isReachable {
            session.sendMessageData(data, replyHandler: nil) { [weak self] _ in
                Task { @MainActor in self?.reachable = false; self?.status = "Connection interrupted · queued delivery remains active" }
            }
        }
    }
    func send(_ packet: WatchPacket) {
        outgoing = packet
        diagnostic?(DiagnosticEvent(event: "watch_send_attempt", watch: packet, connection: status))
        send(WatchMessage(packet: packet), key: "packet/\(packet.session)/\(packet.sequence)")
    }
    func command(_ value: TrialCommand) { send(WatchMessage(command: value), key: value.key) }
    func acknowledge(_ value: WatchAck) { send(WatchMessage(ack: value), key: "ack/\(value.trial)/\(value.action.rawValue)/\(value.accepted)") }
    func stopRemote(trial: UUID? = nil) {
        guard let trial = trial ?? feed.packet?.trial else {
            if reachable { WCSession.default.sendMessage(["stop": true], replyHandler: nil, errorHandler: nil) }
            return
        }
        let now = Date()
        command(TrialCommand(trial: trial, action: .stop, issued: now, expires: now.addingTimeInterval(180), deadline: now))
    }
    private func receive(_ data: Data, backfill: Bool) {
        if let packet = try? JSONDecoder().decode(WatchPacket.self, from: data) { receive(packet, backfill: backfill); return }
        if let message = try? JSONDecoder().decode(WatchMessage.self, from: data) {
            guard [message.packet != nil, message.command != nil, message.ack != nil].filter({ $0 }).count == 1 else { return }
            if let command = message.command { onCommand?(command) }
            if let ack = message.ack {
                let key = "\(ack.trial)/\(ack.action.rawValue)"
                if acks[key].map({ $0.time <= ack.time }) ?? true { acks[key] = ack }
                acknowledgement = ack
                receipt = DiagnosticEvent(event: "watch_ack", message: ack.message, test: ack.trial, command: nil, acknowledgement: ack)
            }
            if let packet = message.packet { receive(packet, backfill: backfill) }
        } else if let packet = try? JSONDecoder().decode(WatchPacket.self, from: data) { receive(packet, backfill: backfill) }
    }
    private func receive(_ packet: WatchPacket, backfill: Bool) {
        var next = feed; let rejection = next.receive(packet)
        receipt = DiagnosticEvent(event: backfill ? "watch_reference_backfill" : "watch_packet_received", message: rejection ?? "accepted", test: packet.trial, watch: packet, watchFresh: packet.fresh(at: Date()))
        if rejection == nil { feed = next }
    }
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        let message = error?.localizedDescription
        Task { @MainActor in self.refresh(); if let message { self.status = message } }
    }
    nonisolated func sessionReachabilityDidChange(_ session: WCSession) { Task { @MainActor in self.refresh() } }
    nonisolated func session(_ session: WCSession, didReceiveMessageData data: Data) { Task { @MainActor in self.receive(data, backfill: false) } }
    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        guard let data = userInfo["chestBPM"] as? Data else { return }
        Task { @MainActor in self.receive(data, backfill: true) }
    }
    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        if message["stop"] as? Bool == true { Task { @MainActor in self.onStop?() } }
    }
    #if os(iOS)
    nonisolated func sessionWatchStateDidChange(_ session: WCSession) { Task { @MainActor in self.refresh() } }
    nonisolated func sessionDidBecomeInactive(_ session: WCSession) { Task { @MainActor in self.reachable = false; self.feed = WatchFeed() } }
    nonisolated func sessionDidDeactivate(_ session: WCSession) { WCSession.default.activate() }
    #endif
}
#endif
