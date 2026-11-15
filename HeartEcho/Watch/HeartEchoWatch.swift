import SwiftUI
import HealthKit
import WatchKit

@MainActor final class WatchMeasurement: NSObject, ObservableObject, HKWorkoutSessionDelegate, HKLiveWorkoutBuilderDelegate {
    static let shared = WatchMeasurement()
    @Published var running = false
    @Published var starting = false
    @Published var bpm: Double?
    @Published var sampleDate: Date?
    @Published var status = "Ready to compare"
    @Published var logging = false
    private let health = HKHealthStore(), heartRate = HKQuantityType(.heartRate), link = WatchLink.shared
    private var session: HKWorkoutSession?, builder: HKLiveWorkoutBuilder?, token = UUID(), began = Date(), sequence = 0
    private var timeout: Task<Void, Never>?
    private var activeCommand: TrialCommand?
    private var gate = (UserDefaults.standard.data(forKey: "trialGate").flatMap { try? JSONDecoder().decode(TrialCommandGate.self, from: $0) }) ?? TrialCommandGate()
    private func persistGate() { UserDefaults.standard.set(try? JSONEncoder().encode(gate), forKey: "trialGate") }
    private func ensureLog() {
        guard !logging else { return }
        do { try log.start(); logging = true; log.write(DiagnosticEvent(event: "watch_app_ready")) }
        catch { status = "Log failed: \(error.localizedDescription)" }
    }
    func remote(_ command: TrialCommand) {
        ensureLog()
        let rejection = gate.accept(command); persistGate()
        log.write(DiagnosticEvent(event: "watch_command", message: rejection ?? "accepted", test: command.trial, command: command))
        if let rejection, rejection != "duplicate" { ack(command, false, rejection); return }
        if rejection == "duplicate" {
            if command.action == .stop || running && activeCommand?.trial == command.trial { ack(command, true, "Already applied") }
            return
        }
        switch command.action {
        case .prepare:
            stop(reason: "new_trial")
            activeCommand = command
            Task {
                while self.starting {
                    guard self.gate.current == command.trial, self.gate.phase < 2 else { return }
                    try? await Task.sleep(for: .milliseconds(100))
                }
                await self.start(command: command)
            }
        case .record:
            guard running, activeCommand?.trial == command.trial else { ack(command, false, "Watch measurement is not running"); return }
            activeCommand = command; scheduleStop(command.deadline)
            ack(command, true, "Watch recording deadline installed")
        case .stop:
            if activeCommand?.trial == command.trial { stop(reason: "phone_stop") }
            ack(command, true, "Stopped")
        }
    }
    private func ack(_ command: TrialCommand, _ accepted: Bool, _ message: String) {
        let value = WatchAck(trial: command.trial, action: command.action, accepted: accepted, time: Date(), deadline: activeCommand?.deadline, session: token, message: message)
        log.write(DiagnosticEvent(event: "watch_ack", message: message, test: command.trial, acknowledgement: value))
        link.acknowledge(value)
    }
    private func scheduleStop(_ deadline: Date) {
        timeout?.cancel()
        timeout = Task { [weak self] in
            // Compute inside the task: sending the acknowledgement can briefly occupy the actor.
            let delay = max(0, deadline.timeIntervalSinceNow)
            try? await Task.sleep(for: .seconds(delay))
            if !Task.isCancelled { self?.stop(reason: "local_deadline") }
        }
    }
    private let log = DiagnosticLog(directory: FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Diagnostics"))
    override init() {
        super.init(); link.onStop = { [weak self] in self?.stop(reason: "manual_remote_stop") }; link.onCommand = { [weak self] in self?.remote($0) }
        link.diagnostic = { [log] in log.write($0) }
        if ProcessInfo.processInfo.arguments.contains("--diagnostics") { ensureLog() }
    }
    func start(command: TrialCommand? = nil) async {
        guard !running, !starting else { return }
        starting = true; ensureLog(); if command == nil { activeCommand = nil }; defer { starting = false }
        log.write(DiagnosticEvent(event: "watch_start_requested"))
        do {
            guard HKHealthStore.isHealthDataAvailable() else { status = "Health data unavailable"; return }
            try await health.requestAuthorization(toShare: [HKObjectType.workoutType()], read: [heartRate])
            guard health.authorizationStatus(for: HKObjectType.workoutType()) == .sharingAuthorized else {
                status = "Allow workout access to start the measurement session"; if let command { ack(command, false, status) }; log.write(DiagnosticEvent(event: "watch_permission_denied", message: status)); return
            }
            if let command { guard gate.current == command.trial, gate.phase < 2, command.deadline > Date() else { return } }
            let config = HKWorkoutConfiguration(); config.activityType = .mindAndBody; config.locationType = .indoor
            let session = try HKWorkoutSession(healthStore: health, configuration: config)
            let builder = session.associatedWorkoutBuilder(), source = HKLiveWorkoutDataSource(healthStore: health, workoutConfiguration: config)
            for type in [HKQuantityTypeIdentifier.activeEnergyBurned, .basalEnergyBurned] { source.disableCollection(for: HKQuantityType(type)) }
            builder.dataSource = source; session.delegate = self; builder.delegate = self
            self.session = session; self.builder = builder; token = UUID(); began = Date(); sequence = 0
            bpm = nil; sampleDate = nil; running = true; status = "Waiting for heart rate… check fit and Health permissions"
            scheduleStop(command?.deadline ?? began.addingTimeInterval(300))
            session.startActivity(with: began)
            try await builder.beginCollection(at: began)
            guard self.builder === builder, running else { return }
            publish()
            if let command { ack(command, true, "Watch ready; waiting for fresh heart samples") }
        } catch { stop(reason: "workout_error"); if let command { ack(command, false, error.localizedDescription) }; status = error.localizedDescription; log.write(DiagnosticEvent(event: "watch_error", message: status)) }
    }
    private func publish(start: Date? = nil, end: Date? = nil) {
        sequence += 1
        let packet = WatchPacket(session: token, began: began, sequence: sequence, active: running, bpm: bpm, start: start, end: end, status: status, trial: activeCommand?.trial, deadline: activeCommand?.deadline)
        log.write(DiagnosticEvent(event: running ? "watch_sample_or_state" : "watch_stopped", test: activeCommand?.trial, watch: packet, connection: link.status))
        link.send(packet)
    }
    func stop(reason: String = "watch_button") {
        timeout?.cancel(); timeout = nil
        let wasRunning = running
        gate.finish(activeCommand?.trial); persistGate()
        log.write(DiagnosticEvent(event: "watch_stop_reason", message: reason, test: activeCommand?.trial))
        running = false; bpm = nil; sampleDate = nil
        session?.end(); builder?.discardWorkout(); session = nil; builder = nil
        if wasRunning { status = "Stopped · session discarded"; publish(); log.stop(); logging = false }
    }
    func clearLogs() { stop(); do { try log.clear(); logging = false; status = "Diagnostic files deleted" } catch { status = error.localizedDescription } }
    nonisolated func workoutBuilder(_ workoutBuilder: HKLiveWorkoutBuilder, didCollectDataOf types: Set<HKSampleType>) {
        let hr = HKQuantityType(.heartRate)
        guard types.contains(hr), let stats = workoutBuilder.statistics(for: hr),
              let value = stats.mostRecentQuantity()?.doubleValue(for: .count().unitDivided(by: .minute())),
              let interval = stats.mostRecentQuantityDateInterval() else { return }
        Task { @MainActor in
            guard self.builder === workoutBuilder, self.running, interval.end != self.sampleDate,
                  interval.start >= self.began, value.isFinite, (20...300).contains(value) else { return }
            if let deadline = self.activeCommand?.deadline, deadline <= Date() { self.stop(reason: "local_deadline_sample_callback"); return }
            self.bpm = value; self.sampleDate = interval.end; self.status = "Measuring · session active"
            self.publish(start: interval.start, end: interval.end)
        }
    }
    nonisolated func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didChangeTo state: HKWorkoutSessionState, from old: HKWorkoutSessionState, date: Date) {
        if state == .ended || state == .stopped { Task { @MainActor in if self.session === workoutSession { self.stop() } } }
    }
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {
        let message = error.localizedDescription
        Task { @MainActor in if self.session === workoutSession { self.stop(); self.status = message } }
    }
}

final class RecoveryDelegate: NSObject, WKApplicationDelegate {
    func handle(_ workoutConfiguration: HKWorkoutConfiguration) {
        _ = WatchMeasurement.shared
        // The queued, expiring prepare command identifies the participant and trial.
        // Never start an unscoped workout merely because a delayed wake-up arrived.
    }
    func handleActiveWorkoutRecovery() {
        HKHealthStore().recoverActiveWorkoutSession { session, _ in
            session?.end(); session?.associatedWorkoutBuilder().discardWorkout()
        }
    }
}

@main struct ChestBPMWatch: App {
    @WKApplicationDelegateAdaptor(RecoveryDelegate.self) private var recovery
    @StateObject private var measurement = WatchMeasurement.shared
    @ObservedObject private var link = WatchLink.shared
    var body: some Scene {
        WindowGroup {
            ScrollView {
                VStack(spacing: 10) {
                    Text("Heart Echo").font(.headline)
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        let fresh = measurement.sampleDate.map { context.date.timeIntervalSince($0) < 15 } ?? false
                        Text(fresh ? measurement.bpm.map { String(Int($0.rounded())) } ?? "—" : "—")
                            .font(.system(size: 48, weight: .semibold, design: .rounded)).monospacedDigit()
                        Text(fresh ? "BPM · Watch sensor" : "Waiting for fresh reading").font(.caption)
                    }
                    Text(measurement.status).font(.caption).multilineTextAlignment(.center)
                    Button(measurement.starting ? "Starting…" : measurement.running ? "Stop & discard" : "Start measuring") {
                        if measurement.running { measurement.stop() } else { Task { await measurement.start() } }
                    }.tint(.pink).disabled(measurement.starting)
                    Text(link.status).font(.caption2)
                    if measurement.logging { Text("Diagnostic BPM log is on").font(.caption2).foregroundStyle(.orange) }
                    Button("Delete diagnostic files") { measurement.clearLogs() }.font(.caption2)
                    Text("Phone tests start automatically and install a local stop timer. Manual measurement stops after 5 min. No workout is saved. Watch may still record health or Activity data.")
                        .font(.caption2).foregroundStyle(.secondary)
                }.padding(.horizontal, 4)
            }
        }
    }
}
