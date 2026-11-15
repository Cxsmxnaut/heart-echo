import AVFoundation
import SwiftUI
import CoreMotion
import HealthKit

// Mutable audio state is confined to this serial queue.
private final class AudioProcessor: @unchecked Sendable {
    let queue = DispatchQueue(label: "ChestBPM.audio", qos: .userInitiated)
    let slots = DispatchSemaphore(value: 8)
    var estimator: HeartRateEstimator?, id: UUID?
    var pending = 0, motion = 0.0, workMS = 0.0
    var recording: AVAudioFile?, recorded = 0, recordingURL: URL?
}

@MainActor final class HeartRateMonitor: ObservableObject {
    @Published var result = HeartRateEstimate()
    @Published var running = false
    @Published var starting = false
    @Published var playing = false
    @Published var error: String?
    @Published var denied = false
    @Published var pairs: [WatchPair] = []
    @Published var draft: WatchPair?
    @Published var autoCompare = true
    @Published var logging = false
    @Published var logStatus = "Diagnostics off"
    @Published var testRemaining: Int?
    @Published var automaticWatch = true
    @Published private(set) var preparing = false
    @Published private(set) var controlChecking = false
    @Published private(set) var preparationStatus = ""
    @Published private(set) var study: TrialPlan?
    @Published private(set) var testSummary = ""
    private var request: UUID?, watchTrial: UUID?, stopAt: Date?, lastTest: UUID?
    private var testTimer: Task<Void, Never>?
    private var preparationSamples = Set<Date>(), attempt = 0
    private var contexts: [UUID: (study: UUID?, cycle: Int?, step: Int?, attempt: Int, participant: String, condition: String)] = [:]
    private var planURL: URL { log.directory.appendingPathComponent("study-state.json") }
    var busy: Bool { running || starting || preparing || controlChecking }
    private func savePlan() {
        do {
            try FileManager.default.createDirectory(at: log.directory, withIntermediateDirectories: true)
            try JSONEncoder().encode(study).write(to: planURL, options: .atomic)
        } catch { self.error = "Plan save failed: \(error.localizedDescription)" }
    }
    func beginStudy() {
        guard !busy, canTest else { return }
        if participant == "A" { saveTestAudio = true }
        study = TrialPlan(participant: participant, audio: saveTestAudio, cycles: 2); condition = study!.condition; savePlan()
        testSummary = "Two final cycles · 8 tests. Tap ready after setting up each condition."
    }
    func setAudioPreference(_ enabled: Bool) { saveTestAudio = enabled; study?.audio = enabled; if study != nil { savePlan() } }
    func endStudy() { stop(reason: "study_ended"); study = nil; savePlan(); setLogging(false) }

    @Published var participant = "A"
    @Published var condition = "Quiet"
    @Published var friendConsent = false
    @Published var saveTestAudio = false
    @Published var modelStatus = "Sound model loads when listening starts"
    @Published private(set) var alignedPair: WatchPair?
    @Published private(set) var acceptedWatch: WatchPacket?
    private let motion = CMMotionManager()
    private var models: DeviceSoundModels?
    private var participantSince = Date.distantPast
    var duration: Int { ["Off chest", "Automation check", "Watch control check"].contains(condition) ? 20 : 90 }
    var canTest: Bool { participant == "A" || friendConsent }
    private let log = DiagnosticLog(directory: FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Diagnostics"))
    private var heartbeat: Task<Void, Never>?, testID: UUID?, testStart: Double?, lastAudio: Date?
    private lazy var references = DiagnosticLog(directory: log.directory.appendingPathComponent("WatchReferences"))
    private var referencesEnabled = false
    private var diagnosticFrame = 0
    private var position = "Lower left"
    var logURL: URL { log.url }
    private let audio = AudioProcessor()
    private var engine: AVAudioEngine?, player: AVAudioPlayerNode?, id: UUID?, hasTap = false
    private var clip: [Float] = [], observers: [NSObjectProtocol] = []
    private var history: [PhoneReading] = [], watchPacket: WatchPacket?, paired = Set<String>()
    var canReplay: Bool { !clip.isEmpty }

    init() {
        if let data = try? Data(contentsOf: planURL), let saved = try? JSONDecoder().decode(TrialPlan.self, from: data) {
            study = saved; participant = saved.participant; condition = saved.condition; saveTestAudio = saved.audio
            testSummary = "Saved plan restored · any interrupted trial needs a fresh ready tap"
        }
        if ProcessInfo.processInfo.arguments.contains("--diagnostics") { setLogging(true) }
        if ProcessInfo.processInfo.arguments.contains("--automation-check") {
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(2))
                guard let self, !self.busy else { return }
                self.study = nil; self.condition = "Automation check"; self.saveTestAudio = false
                await self.timedTest()
            }
        }
        observers.append(NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] note in
            guard note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt == AVAudioSession.InterruptionType.began.rawValue else { return }
            Task { @MainActor in self?.note(DiagnosticEvent(event: "audio_interrupted")); self?.stop(reason: "interruption"); self?.result.status = "Interrupted · tap Start to try again" }
        })
        for name in [AVAudioSession.routeChangeNotification, AVAudioSession.mediaServicesWereResetNotification, Notification.Name.AVAudioEngineConfigurationChange] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    let session = AVAudioSession.sharedInstance()
                    self?.note(DiagnosticEvent(event: "audio_configuration", message: name.rawValue, sampleRate: session.sampleRate,
                        input: session.currentRoute.inputs.map(\.portName).joined(separator: ", "), route: session.mode.rawValue))
                }
            })
        }
    }
    deinit { heartbeat?.cancel(); observers.forEach(NotificationCenter.default.removeObserver) }
    func note(_ input: DiagnosticEvent) {
        var event = input; event.schema = 3
        let context = event.test.flatMap { contexts[$0] }
        event.participant = context?.participant ?? participant; event.condition = context?.condition ?? condition
        event.study = context?.study ?? study?.id; event.cycle = context?.cycle ?? study?.cycle
        event.step = context?.step ?? study.map { $0.index + 1 }; event.attempt = context?.attempt ?? attempt
        event.denoiserEnabled = false
        if ["watch_reference_backfill", "watch_packet_received", "watch_ack"].contains(event.event) {
            if !referencesEnabled && logging {
                do { try references.start(); referencesEnabled = true } catch { self.error = "Watch reference log failed: \(error.localizedDescription)" }
            }
            if referencesEnabled { references.write(event) }
        }
        if logging { log.write(event) }
    }
    func changedParticipant() {
        clear(); study = nil; savePlan(); friendConsent = false; saveTestAudio = false
        participantSince = Date(); watchPacket = nil; acceptedWatch = nil; alignedPair = nil; paired = []
        WatchLink.shared.stopRemote()
        note(DiagnosticEvent(event: "participant_changed", message: "Restart Watch measurement for this wearer"))
    }
    func setLogging(_ enabled: Bool) {
        guard enabled != logging else { return }
        if !enabled, testID != nil || preparing { stop(reason: "logging_disabled") }
        heartbeat?.cancel(); heartbeat = nil
        if !enabled { note(DiagnosticEvent(event: "logging_disabled")); log.stop(); logging = false; logStatus = "Diagnostics off"; UIApplication.shared.isIdleTimerDisabled = running; return }
        do {
            try log.start(); logging = true; diagnosticFrame = 0; UIApplication.shared.isIdleTimerDisabled = true
            let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
            let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown"
            note(DiagnosticEvent(event: "app_ready", message: "v\(version) (\(build)) · Metrics/features; audio only with explicit test toggle", position: position))
            heartbeat = Task { [weak self] in
                while !Task.isCancelled {
                    self?.logHeartbeat()
                    try? await Task.sleep(for: .seconds(1))
                }
            }
        } catch { logging = false; logStatus = "Log failed: \(error.localizedDescription)" }
    }
    private func logHeartbeat() {
        if let started = testStart {
            let remaining = max(0, (stopAt?.timeIntervalSinceNow ?? (Double(duration) - (ProcessInfo.processInfo.systemUptime - started))))
            testRemaining = Int(ceil(remaining))
            if remaining == 0 { stop(reason: "timed_test_complete") }
        }
        let state = log.state
        logStatus = state.error.map { "Log failed: \($0)" } ?? "Logging · \(state.rows) entries"
        note(DiagnosticEvent(event: "heartbeat", message: logStatus, test: testID ?? lastTest, position: position,
            running: running, elapsed: testStart.map { ProcessInfo.processInfo.systemUptime - $0 },
            remaining: testRemaining.map(Double.init), audioAge: lastAudio.map { Date().timeIntervalSince($0) },
            watch: watchPacket, watchFresh: watchPacket?.fresh(at: Date())))
    }
    func timedTest(watchOnly: Bool = false) async {
        guard !busy, !playing, canTest, study?.complete != true else { return }
        if let study { condition = study.condition; saveTestAudio = study.audio }
        if logging { setLogging(false) }; setLogging(true)
        guard logging else { return }
        let token = UUID(); request = token; testID = token; preparing = true; preparationSamples = []; attempt += 1
        contexts[token] = (study?.id, study?.cycle, study.map { $0.index + 1 }, attempt, participant, condition)
        let seconds = duration
        UIApplication.shared.isIdleTimerDisabled = true
        note(DiagnosticEvent(event: "test_preparing", test: token, running: false, remaining: Double(seconds)))
        defer { if request == token { preparing = false } }
        do {
            preparationStatus = watchOnly ? "Checking Watch control…" : "Checking microphone and sound model…"
            if !watchOnly {
                guard await AVAudioApplication.requestRecordPermission() else {
                    denied = true; throw NSError(domain: "ChestBPM", code: 1, userInfo: [NSLocalizedDescriptionKey: "Allow microphone access in Settings."])
                }
                if models == nil { models = try await Task.detached(priority: .userInitiated) { try DeviceSoundModels() }.value }
            }
            guard request == token, UIApplication.shared.applicationState == .active else { return }
            if automaticWatch || watchOnly {
                watchTrial = token; preparationStatus = "Starting Watch automatically… unlock it if needed"
                let now = Date()
                let prepare = TrialCommand(trial: token, action: .prepare, issued: now, expires: now.addingTimeInterval(75), deadline: now.addingTimeInterval(120), study: study?.id, cycle: study?.cycle, participant: participant, condition: condition)
                WatchLink.shared.command(prepare); note(DiagnosticEvent(event: "watch_command_sent", test: token, command: prepare))
                let config = HKWorkoutConfiguration(); config.activityType = .mindAndBody; config.locationType = .indoor
                HKHealthStore().startWatchApp(with: config) { [weak self] success, error in
                    let message = error?.localizedDescription
                    Task { @MainActor in
                        guard self?.request == token else { return }
                        self?.note(DiagnosticEvent(event: "watch_wake_result", message: message ?? (success ? "Watch wake accepted" : "Open the Watch app once"), test: token))
                    }
                }
                try await waitForWatch(token, action: .prepare, timeout: 75, samples: true, retry: prepare)
                guard request == token else { return }
                let start = Date().addingTimeInterval(5), deadline = start.addingTimeInterval(Double(seconds))
                let record = TrialCommand(trial: token, action: .record, issued: Date(), expires: deadline, deadline: deadline, start: start, study: study?.id, cycle: study?.cycle, participant: participant, condition: condition)
                WatchLink.shared.command(record); note(DiagnosticEvent(event: "watch_command_sent", test: token, command: record))
                try await waitForWatch(token, action: .record, timeout: 4, samples: false, deadline: deadline, retry: record)
                guard request == token, Date() < start else { throw CocoaError(.userCancelled) }
                stopAt = deadline
                while Date() < start {
                    guard request == token else { return }
                    preparationStatus = "Watch ready · recording starts in \(max(1, Int(ceil(start.timeIntervalSinceNow))))…"
                    try await Task.sleep(for: .milliseconds(100))
                }
            } else { stopAt = Date().addingTimeInterval(Double(seconds)) }
            guard request == token else { return }
            if watchOnly {
                controlChecking = true; result.status = "Watch-only timing check · phone microphone is off"
            } else { await start(recordTestAudio: saveTestAudio, preservingTrial: true) }
            guard running || controlChecking, request == token else { throw NSError(domain: "ChestBPM", code: 2, userInfo: [NSLocalizedDescriptionKey: error ?? "Capture did not start"]) }
            preparing = false; testStart = ProcessInfo.processInfo.systemUptime; testRemaining = max(0, Int(ceil(stopAt?.timeIntervalSinceNow ?? Double(seconds))))
            note(DiagnosticEvent(event: "test_started", message: watchOnly ? "watch_control_only" : nil, test: token, running: !watchOnly, remaining: Double(testRemaining!)))
            let deadline = stopAt ?? Date().addingTimeInterval(Double(seconds))
            testTimer = Task { [weak self] in
                let delay = max(0, deadline.timeIntervalSinceNow)
                try? await Task.sleep(for: .seconds(delay))
                guard !Task.isCancelled, self?.testID == token else { return }
                self?.stop(reason: "timed_test_complete")
            }
        } catch {
            guard request == token else { return }
            let message = error.localizedDescription
            note(DiagnosticEvent(event: "test_aborted", message: message, test: token))
            stop(reason: "preparation_failed"); self.error = message
            testSummary = "Test did not start · logs kept · tap ready to retry"
        }
    }
    private func waitForWatch(_ trial: UUID, action: TrialCommand.Action, timeout: Double, samples: Bool, deadline: Date? = nil, retry: TrialCommand) async throws {
        var lastSent = Date()
        let until = Date().addingTimeInterval(timeout)
        while Date() < until {
            guard request == trial else { throw CancellationError() }
            if WatchLink.shared.ack(for: trial, action: action) == nil, Date().timeIntervalSince(lastSent) >= 2 {
                WatchLink.shared.command(retry); lastSent = Date()
                note(DiagnosticEvent(event: "watch_command_retry", test: trial, command: retry))
            }
            if let ack = WatchLink.shared.ack(for: trial, action: action) {
                guard ack.accepted else { throw NSError(domain: "ChestBPM.Watch", code: 1, userInfo: [NSLocalizedDescriptionKey: ack.message ?? "Watch request rejected"]) }
                if let deadline, ack.deadline.map({ abs($0.timeIntervalSince(deadline)) < 0.1 }) != true {
                    throw NSError(domain: "ChestBPM.Watch", code: 3, userInfo: [NSLocalizedDescriptionKey: "Watch stop timer did not match this test; retry."])
                }
                if !samples || preparationSamples.count >= 3 {
                    if !samples || watchPacket?.fresh(at: Date()) == true && watchPacket?.trial == trial && (watchPacket?.end?.timeIntervalSinceNow ?? -100) > -6 { return }
                }
                preparationStatus = "Watch started · collecting fresh readings (\(min(3, preparationSamples.count))/3)…"
            }
            try await Task.sleep(for: .milliseconds(200))
        }
        throw NSError(domain: "ChestBPM.Watch", code: 2, userInfo: [NSLocalizedDescriptionKey: "Watch did not become ready. Unlock it, open Chest BPM once, allow Health access, then retry."])
    }
    func changedPosition(_ value: String) {
        position = value; note(DiagnosticEvent(event: "position_changed", test: testID, position: value))
    }
    func clearLogs() {
        stop(reason: "logs_cleared"); setLogging(false)
        study = nil
        do { try references.clear(); referencesEnabled = false; try log.clear(); logStatus = "Diagnostic files deleted" } catch { logStatus = error.localizedDescription }
    }

    func start(recordTestAudio: Bool = false, preservingTrial: Bool = false) async {
        guard !running, !starting else { return }
        if !preservingTrial { stop(reason: "capture_restart") }; starting = true; error = nil; denied = false
        note(DiagnosticEvent(event: "microphone_start_requested", position: position))
        defer { starting = false }
        guard await AVAudioApplication.requestRecordPermission() else {
            denied = true; error = "Allow microphone access in Settings to estimate BPM."
            note(DiagnosticEvent(event: "microphone_permission_denied")); return
        }
        guard !Task.isCancelled, UIApplication.shared.applicationState == .active else { return }
        do {
            if models == nil {
                models = try await Task.detached(priority: .userInitiated) { try DeviceSoundModels() }.value
            }
            modelStatus = "On-device heart-sound model ready"
            guard !Task.isCancelled, UIApplication.shared.applicationState == .active else { return }
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement)
            try session.setPreferredSampleRate(48000); try session.setPreferredIOBufferDuration(0.02)
            try session.setActive(true)
            if let mic = session.availableInputs?.first(where: { $0.portType == .builtInMic }) {
                try session.setPreferredInput(mic)
                if let bottom = mic.dataSources?.first(where: { $0.location == .lower }) { try? mic.setPreferredDataSource(bottom) }
            }
            let engine = AVAudioEngine(), token = UUID(), audio = self.audio
            let input = engine.inputNode, format = input.outputFormat(forBus: 0)
            guard format.sampleRate > 0, format.channelCount > 0 else {
                throw NSError(domain: "ChestBPM", code: 1, userInfo: [NSLocalizedDescriptionKey: "No microphone is available."])
            }
            self.engine = engine; id = token; clip = []
            let models = self.models
            var recording: AVAudioFile?
            if recordTestAudio {
                let directory = log.directory.appendingPathComponent("Audio")
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                var local = directory, flags = URLResourceValues(); flags.isExcludedFromBackup = true; try local.setResourceValues(flags)
                let url = directory.appendingPathComponent(UUID().uuidString + ".wav")
                recording = try AVAudioFile(forWriting: url, settings: [AVFormatIDKey: kAudioFormatLinearPCM,
                    AVSampleRateKey: format.sampleRate, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                    AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false])
                try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
                note(DiagnosticEvent(event: "audio_save_started", audioFile: "Audio/" + url.lastPathComponent))
            }
            let file = recording
            audio.queue.async {
                audio.id = token; audio.estimator = HeartRateEstimator(sampleRate: format.sampleRate, models: models)
                audio.pending = 0; audio.workMS = 0; audio.motion = 0; audio.recording = file; audio.recorded = 0; audio.recordingURL = file?.url
            }
            if motion.isDeviceMotionAvailable {
                motion.deviceMotionUpdateInterval = 0.02
                motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
                    guard let a = data?.userAcceleration else { return }
                    let value = sqrt(a.x * a.x + a.y * a.y + a.z * a.z)
                    self?.audio.queue.async { audio.motion = max(audio.motion, value) }
                }
            }
            input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
                guard audio.slots.wait(timeout: .now()) == .success else {
                    Task { @MainActor [weak self] in
                        guard let self, self.id == token else { return }
                        self.note(DiagnosticEvent(event: "audio_overload", message: "Processing fell behind; stopped instead of skipping audio"))
                        self.stop(reason: "audio_overload"); self.error = "Audio processing fell behind. Stop other apps and try again."
                    }
                    return
                }
                guard let channel = buffer.floatChannelData?[0] else { audio.slots.signal(); return }
                let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
                let capturedAt = Date()
                audio.queue.async {
                    defer { audio.slots.signal() }
                    guard audio.id == token else { return }
                    let workStart = ProcessInfo.processInfo.systemUptime
                    if let file = audio.recording, audio.recorded < Int(format.sampleRate * 120),
                       let mono = AVAudioFormat(standardFormatWithSampleRate: format.sampleRate, channels: 1),
                       let copy = AVAudioPCMBuffer(pcmFormat: mono, frameCapacity: AVAudioFrameCount(samples.count)) {
                        copy.frameLength = copy.frameCapacity
                        samples.withUnsafeBufferPointer { copy.floatChannelData![0].update(from: $0.baseAddress!, count: samples.count) }
                        do { try file.write(from: copy); audio.recorded += samples.count }
                        catch {
                            audio.recording = nil
                            Task { @MainActor [weak self] in self?.note(DiagnosticEvent(event: "audio_save_failed", message: error.localizedDescription)) }
                        }
                    }
                    audio.estimator?.append(samples, motion: audio.motion); audio.motion = 0; audio.pending += samples.count
                    audio.workMS += (ProcessInfo.processInfo.systemUptime - workStart) * 1000
                    guard audio.pending >= Int(format.sampleRate / 2) else { return }
                    let began = ProcessInfo.processInfo.systemUptime
                    guard let estimate = audio.estimator?.estimate() else { return }
                    let duration = audio.workMS + (ProcessInfo.processInfo.systemUptime - began) * 1000; audio.workMS = 0
                    audio.pending = 0
                    Task { @MainActor [weak self] in
                        guard let self, self.id == token, self.running else { return }
                        self.clip = estimate.audio; self.result = estimate; self.lastAudio = capturedAt
                        if self.logging {
                            var snapshot = estimate; self.diagnosticFrame += 1
                            if self.diagnosticFrame % 4 != 0 { snapshot.diagnostics.envelope = nil; snapshot.diagnostics.brightness = nil; snapshot.diagnostics.enhanced?.envelope = nil; snapshot.diagnostics.enhanced?.stateProbabilities = nil }
                            self.note(DiagnosticEvent(time: capturedAt, event: "estimate", test: self.testID, position: self.position,
                                running: true, elapsed: self.testStart.map { ProcessInfo.processInfo.systemUptime - $0 }, processingMS: duration,
                                estimate: snapshot, watch: self.watchPacket, watchFresh: self.watchPacket?.fresh(at: capturedAt)))
                        }
                        self.history.append(PhoneReading(time: capturedAt, seconds: estimate.seconds, original: estimate.original, improved: estimate.bpm, improvedTime: capturedAt.addingTimeInterval(-estimate.analysisAge)))
                        self.history.removeAll { capturedAt.timeIntervalSince($0.time) > 30 }
                        self.pairWatch()
                    }
                }
            }
            hasTap = true; engine.prepare(); try engine.start()
            running = true; result.status = "Listening… hold still"; UIApplication.shared.isIdleTimerDisabled = true
            lastAudio = nil
            note(DiagnosticEvent(event: "microphone_started", sampleRate: format.sampleRate, channels: Int(format.channelCount),
                input: session.currentRoute.inputs.map(\.portName).joined(separator: ", "), route: session.mode.rawValue))
        } catch { note(DiagnosticEvent(event: "microphone_error", message: error.localizedDescription)); stop(reason: "microphone_error"); self.error = error.localizedDescription; result.status = "Couldn’t start the microphone" }
    }
    func stop(clearAudio: Bool = false, reason: String = "user_stop") {
        if testStart == nil, let testID, reason != "preparation_failed" {
            note(DiagnosticEvent(event: "test_aborted", message: reason, test: testID, running: false))
        }
        if let started = testStart { note(DiagnosticEvent(event: "test_ended", message: reason, test: testID, position: position, elapsed: ProcessInfo.processInfo.systemUptime - started)) }
        if running || playing { note(DiagnosticEvent(event: "audio_stopped", message: reason)) }
        testTimer?.cancel(); testTimer = nil
        let endedTest = testID
        if let endedTest { lastTest = endedTest }
        if let trial = watchTrial {
            if reason == "timed_test_complete" {
                Task { [weak self] in
                    try? await Task.sleep(for: .seconds(3))
                    let packet = WatchLink.shared.feed.packet
                    let stopped = packet?.trial == trial && packet?.active == false
                    self?.note(DiagnosticEvent(event: stopped ? "watch_deadline_stop_confirmed" : "watch_stop_retry", test: trial))
                    if !stopped { WatchLink.shared.stopRemote(trial: trial) }
                }
            } else { WatchLink.shared.stopRemote(trial: trial) }
        }
        watchTrial = nil; request = nil; preparing = false; controlChecking = false; stopAt = nil
        testStart = nil; testRemaining = nil
        id = nil; motion.stopDeviceMotionUpdates()
        if hasTap { engine?.inputNode.removeTap(onBus: 0); hasTap = false }
        player?.stop(); engine?.stop(); player = nil; engine = nil
        let saved = audio.queue.sync { () -> (URL?, Int) in
            let saved = (audio.recordingURL, audio.recorded)
            audio.id = nil; audio.estimator = nil; audio.recording = nil; audio.recordingURL = nil
            return saved
        }
        if let url = saved.0 { note(DiagnosticEvent(event: "audio_saved", message: "\(saved.1) samples", test: endedTest, audioFile: "Audio/" + url.lastPathComponent)) }
        testID = nil
        if condition == "Watch control check" { condition = "Quiet" }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        running = false; playing = false; result = HeartRateEstimate(); history = []; alignedPair = nil
        if clearAudio { clip = [] }
        UIApplication.shared.isIdleTimerDisabled = logging
        if reason == "timed_test_complete" {
            if study != nil {
                study?.advance(); savePlan()
                if study?.complete == true { testSummary = "All \(study!.totalTests) tests complete · logs and enabled audio saved" }
                else { condition = study!.condition; testSummary = "Saved · set up the next condition, then tap ready" }
            } else { testSummary = "Test complete · local log saved" }
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(5))
                if self?.busy == false, self?.testStart == nil, self?.study == nil || self?.study?.complete == true { self?.setLogging(false) }
            }
        }
    }
    func replay() {
        guard canReplay, !starting else { return }
        stop(reason: "replay"); error = nil
        note(DiagnosticEvent(event: "replay_started"))
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default); try session.setActive(true)
            guard let format = AVAudioFormat(standardFormatWithSampleRate: 4000, channels: 1),
                  let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(clip.count)),
                  let channel = buffer.floatChannelData?[0] else { throw NSError(domain: "ChestBPM", code: 2) }
            buffer.frameLength = buffer.frameCapacity
            let gain = min(1000, 0.35 / max(clip.map { abs($0) }.max() ?? 0, 0.00001))
            for i in clip.indices { channel[i] = clip[i] * gain }
            let engine = AVAudioEngine(), player = AVAudioPlayerNode(), token = UUID()
            self.engine = engine; self.player = player; id = token
            engine.attach(player); engine.connect(player, to: engine.mainMixerNode, format: format)
            player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
                Task { @MainActor in if self?.id == token { self?.stop() } }
            }
            try engine.start(); playing = true; player.play()
        } catch { stop(); self.error = "Playback failed: \(error.localizedDescription)" }
    }
    func capturePair() {
        guard running, result.seconds >= 6 else { return }
        draft = WatchPair(time: Date(), original: result.original, improved: result.bpm)
    }
    func savePair(_ pair: WatchPair, watch: Int) {
        guard (20...300).contains(watch) else { return }
        var saved = pair; saved.watch = Double(watch); pairs.append(saved); draft = nil
        note(DiagnosticEvent(event: "manual_pair", pair: saved))
    }
    func receiveWatch(_ feed: WatchFeed) {
        watchPacket = feed.packet.flatMap { $0.began >= participantSince ? $0 : nil }
        if preparing, let packet = watchPacket, packet.trial == request, packet.fresh(at: Date()), let end = packet.end { preparationSamples.insert(end) }
        acceptedWatch = watchPacket
        if running || controlChecking, let packet = watchPacket, packet.trial == testID, !packet.active {
            stop(reason: (stopAt?.timeIntervalSinceNow ?? 99) <= 0.5 ? "timed_test_complete" : "watch_stopped_early")
        }
        pairWatch()
    }
    private func pairWatch() {
        guard running, let packet = watchPacket, let pair = automaticPair(packet, history: history) else { alignedPair = nil; return }
        alignedPair = pair
        guard autoCompare, !paired.contains(packet.key) else { return }
        paired.insert(packet.key); pairs.append(pair)
        note(DiagnosticEvent(event: "automatic_pair", test: testID, pair: pair, watch: packet))
    }
    func clear() { stop(clearAudio: true, reason: "session_cleared"); pairs = []; draft = nil; error = nil; note(DiagnosticEvent(event: "comparisons_cleared")) }
}
