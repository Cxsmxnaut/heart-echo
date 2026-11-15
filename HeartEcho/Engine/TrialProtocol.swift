import Foundation

struct TrialCommand: Codable, Sendable, Equatable {
    enum Action: Int, Codable, Sendable { case prepare, record, stop }
    let trial: UUID, action: Action, issued: Date, expires: Date, deadline: Date
    var start: Date?, study: UUID?, cycle: Int?, participant = "A", condition = "Quiet"
    var key: String { "command/\(trial)/\(action.rawValue)" }
    func valid(at now: Date) -> Bool {
        [issued, expires, deadline].allSatisfy { $0.timeIntervalSince1970.isFinite } && issued <= now.addingTimeInterval(3) && expires > now && expires > issued &&
        (action == .stop || deadline > now && deadline.timeIntervalSince(now) <= 180) &&
        (action != .record || start.map { $0.timeIntervalSince1970.isFinite && $0 < deadline && deadline.timeIntervalSince($0) <= 120 } == true)
    }
}

/// Persisted on Watch. Old, repeated or reordered commands cannot restart a completed trial.
struct TrialCommandGate: Codable {
    private(set) var current: UUID?, issued = Date.distantPast, phase = -1
    private var deadline: Date?, start: Date?
    private var finished: [UUID] = []
    private mutating func remember(_ trial: UUID) { if !finished.contains(trial) { finished.append(trial) }; if finished.count > 64 { finished.removeFirst() } }
    mutating func accept(_ command: TrialCommand, now: Date = Date()) -> String? {
        guard command.valid(at: now) else { return "expired_or_invalid" }
        if finished.contains(command.trial) { return command.action == .stop ? "duplicate" : "completed_trial" }
        if command.action == .stop && current != command.trial { remember(command.trial); return nil }
        if current == command.trial {
            guard command.action.rawValue >= phase else { return "earlier_phase" }
            if command.action.rawValue == phase {
                guard command.action == .stop || deadline == command.deadline && start == command.start else { return "conflicting_duplicate" }
                return "duplicate"
            }
        } else {
            guard command.action != .record, command.issued > issued else { return "wrong_or_old_trial" }
        }
        current = command.trial; issued = max(issued, command.issued); phase = command.action.rawValue
        deadline = command.deadline; start = command.start
        if command.action == .stop { remember(command.trial) }
        return nil
    }
    mutating func finish(_ trial: UUID?) { if let trial { remember(trial) }; if trial == current { phase = TrialCommand.Action.stop.rawValue } }
}

struct WatchAck: Codable, Sendable {
    let trial: UUID, action: TrialCommand.Action, accepted: Bool, time: Date
    var deadline: Date?, session: UUID?, message: String?
}
struct WatchMessage: Codable, Sendable {
    var packet: WatchPacket?, command: TrialCommand?, ack: WatchAck?
}

struct TrialPlan: Codable, Sendable {
    let id: UUID, participant: String
    let repetitions: Int?
    private(set) var index = 0
    var audio = false
    static let conditions = ["Quiet", "Background sound", "Brief repositioning", "Off chest"]
    init(participant: String, audio: Bool, cycles: Int = 5) {
        id = UUID(); self.participant = participant; self.audio = audio; repetitions = max(1, min(5, cycles))
    }
    var cycles: Int { max(1, min(5, repetitions ?? 5)) }
    var totalTests: Int { cycles * 4 }
    var complete: Bool { index >= totalTests }
    var cycle: Int { min(cycles, index / 4 + 1) }
    var condition: String { Self.conditions[(index % 4 + index / 4) % 4] }
    var duration: Int { condition == "Off chest" ? 20 : 90 }
    mutating func advance() { if !complete { index += 1 } }
    var instruction: String {
        switch condition {
        case "Background sound": return "Play the same spoken video on another device, about one metre away at the same volume. Hold the phone steady against your chest."
        case "Brief repositioning": return "Pause the video. Hold against your chest; make one small adjustment at 45 seconds remaining, then settle again."
        case "Off chest": return "Pause the video. Leave the phone on the table away from your body for 20 seconds."
        default: return "Pause the video. Rest the bottom microphone gently against bare chest skin with your arms supported."
        }
    }
}
