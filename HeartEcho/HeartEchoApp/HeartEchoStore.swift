import AVFoundation
import Combine
import SwiftUI

@MainActor final class HeartEchoStore: NSObject, ObservableObject, AVAudioPlayerDelegate {
    let monitor = HeartRateMonitor()
    @Published private(set) var recordings: [HeartRecording] = []
    @Published private(set) var starting = false
    @Published private(set) var recording = false
    @Published private(set) var analyzing = false
    @Published private(set) var remaining = 20
    @Published private(set) var live = HeartRateEstimate()
    @Published private(set) var completed: HeartRecording?
    @Published var error: String?
    @Published var playing: UUID?
    @Published var keepAudio = false
    private var capture: URL?
    private var historyReady = false
    private var task: Task<Void, Never>?
    private var token = UUID()
    private var bpms: [Double] = []
    private var player: AVAudioPlayer?
    private var subscriptions = Set<AnyCancellable>()
    private let files = FileManager.default
    private var root: URL { files.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("HeartEcho", isDirectory: true) }
    private var audioDirectory: URL { monitor.logURL.deletingLastPathComponent().appendingPathComponent("Audio", isDirectory: true) }
    private var pending: URL { root.appendingPathComponent("Pending", isDirectory: true) }
    private lazy var storage = RecordingFiles(root: root, diagnostics: audioDirectory)
    var busy: Bool { starting || recording || analyzing }

    override init() {
        super.init()
        #if DEBUG && targetEnvironment(simulator)
        if ProcessInfo.processInfo.arguments.contains("--developer-mode") { UserDefaults.standard.set(true, forKey: "developerMode") }
        if ProcessInfo.processInfo.arguments.contains("--consumer-mode") { UserDefaults.standard.set(false, forKey: "developerMode") }
        #endif
        do {
            try storage.prepare()
            #if DEBUG && targetEnvironment(simulator)
            if ProcessInfo.processInfo.arguments.contains("--ui-reset-recordings") { try? files.removeItem(at: storage.history) }
            #endif
            try storage.recoverPending()
            recordings = try storage.load(); historyReady = true
            try storage.recover(&recordings)
        } catch { self.error = "Saved files need attention: \(error.localizedDescription)" }
        monitor.$result.sink { [weak self] value in
            guard let self else { return }; self.live = value
            if self.recording, let bpm = value.bpm, bpm.isFinite { self.bpms.append(bpm) }
        }.store(in: &subscriptions)
        monitor.$running.dropFirst().sink { [weak self] running in
            guard let self, self.recording, !running else { return }
            self.cancel(message: "The recording was interrupted. No result was saved.")
        }.store(in: &subscriptions)
        let watch = WatchLink.shared
        watch.$feed.sink { [weak self] in self?.monitor.receiveWatch($0) }.store(in: &subscriptions)
        watch.$receipt.sink { [weak self] in if let event = $0 { self?.monitor.note(event) } }.store(in: &subscriptions)
        watch.$status.sink { [weak self] in self?.monitor.note(DiagnosticEvent(event: "watch_connection", connection: $0)) }.store(in: &subscriptions)
        monitor.$autoCompare.sink { [weak self] in self?.monitor.note(DiagnosticEvent(event: "auto_compare_changed", message: String($0))) }.store(in: &subscriptions)
    }

    private func removeTransient(_ url: URL) {
        do { try storage.removePending(url) }
        catch { self.error = "Temporary audio could not be deleted. It remains tracked for cleanup on next launch: \(error.localizedDescription)" }
    }
    private func recoverCapture() {
        do { try storage.recoverPending() }
        catch { self.error = "Temporary audio cleanup needs a retry: \(error.localizedDescription)" }
    }

    func start() async {
        guard historyReady, !busy, !monitor.busy else { error = historyReady ? "Stop the current live or diagnostic session first." : "History could not load. Existing data has been preserved."; return }
        stopPlayback(); error = nil; completed = nil; bpms = []; starting = true; remaining = 20
        let id = UUID(); token = id
        let url = pending.appendingPathComponent(id.uuidString + ".wav"); capture = url
        await monitor.start(captureURL: url)
        guard token == id else { removeTransient(url); return }
        starting = false
        guard monitor.running else { removeTransient(url); capture = nil; error = monitor.error ?? "The microphone did not start."; return }
        recording = true
        let end = Date().addingTimeInterval(20)
        task = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.token == id else { return }
                self.remaining = max(0, Int(ceil(end.timeIntervalSinceNow)))
                if self.remaining == 0 { await self.finish(id: id); return }
                do { try await Task.sleep(for: .milliseconds(200)) } catch { return }
            }
        }
    }

    private func finish(id: UUID) async {
        guard token == id, let url = capture else { return }
        recording = false; analyzing = true
        let bpm = bpms.isEmpty ? nil : median(bpms), count = bpms.count
        let artifact = monitor.stop(clearAudio: true, reason: "product_recording_complete")
        guard let artifact, artifact.url.resolvingSymlinksInPath().standardizedFileURL.path == url.resolvingSymlinksInPath().standardizedFileURL.path, artifact.complete else {
            analyzing = false; capture = nil; removeTransient(url)
            error = artifact?.error.map { "Recording failed: " + $0 } ?? "The full 20-second recording could not be saved. No result was produced."
            return
        }
        await analyze(url, id: id, source: "iPhone microphone", title: "Heart-sound recording", bpm: bpm, bpmWindows: count, transient: true, capturedSeconds: artifact.seconds)
    }

    func analyzePublic(_ name: String) async {
        guard ["absent", "present", "unknown"].contains(name), !busy, !monitor.busy,
              let url = Bundle.main.url(forResource: name, withExtension: "wav", subdirectory: "MurmurSamples") else { return }
        stopPlayback(); error = nil; completed = nil; let id = UUID(); token = id; analyzing = true
        await analyze(url, id: id, source: "Public CirCor recording", title: "Public \(name) sample", publicSample: name)
    }

    func analyzeImport(_ url: URL) async {
        guard !busy, !monitor.busy else { error = "Stop the current session before importing."; return }
        stopPlayback(); error = nil; completed = nil; let id = UUID(); token = id; analyzing = true
        let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
        await analyze(url, id: id, source: "Imported recording", title: url.deletingPathExtension().lastPathComponent)
    }

    private func analyze(_ url: URL, id: UUID, source: String, title: String, bpm: Double? = nil, bpmWindows: Int = 0, transient: Bool = false, publicSample: String? = nil, capturedSeconds: Double? = nil) async {
        let retain = keepAudio
        do {
            let output = try await Task.detached(priority: .userInitiated) { () -> (MurmurReading, [Float], AudioAssessment) in
                let audio = try MurmurAnalyzer.audio(url); let reading = try MurmurAnalyzer().analyze(audio)
                let stride = max(1, audio.count / 480)
                var wave = Swift.stride(from: 0, to: audio.count, by: stride).map { start in audio[start..<min(audio.count, start + stride)].map { abs($0) }.max() ?? 0 }
                let scale = max(wave.max() ?? 0, 0.000001); wave = wave.map { $0 / scale }
                return (reading, wave, AudioAssessment.inspect(audio))
            }.value
            guard token == id else { return }
            var result = HeartRecording(title: title, source: source, seconds: capturedSeconds ?? output.0.seconds, bpm: bpm, bpmWindows: bpmWindows,
                signalStatus: bpm == nil ? "BPM unavailable" : "BPM returned · experimental", murmur: output.0, waveform: output.1, publicSample: publicSample,
                reference: publicSample.map { $0 == "absent" ? "No murmur annotated" : $0 == "present" ? "Murmur annotated" : "Uncertain annotation" })
            result.audioAssessment = output.2
            if retain && transient {
                result.audioFile = result.id.uuidString + ".wav"
                if monitor.logging { result.diagnosticAudio = "Audio/" + result.id.uuidString + ".wav" }
            }
            guard historyReady else { throw CocoaError(.fileReadCorruptFile) }
            let next = [result] + recordings
            try storage.commit(result, source: retain && transient ? url : nil, records: next)
            recordings = next
            if let name = result.diagnosticAudio { monitor.note(DiagnosticEvent(event: "audio_saved", message: "Explicitly retained product audio", audioFile: name)) }
            completed = result
            monitor.note(DiagnosticEvent(event: "murmur_result", message: String(data: try JSONEncoder().encode(output.0), encoding: .utf8)))
            if transient { removeTransient(url) }
        } catch {
            if token == id { self.error = "Analysis could not finish: \(error.localizedDescription)" }
            if transient { removeTransient(url) }
        }
        if token == id { analyzing = false; capture = nil }
    }

    func cancel(message: String? = nil) {
        token = UUID(); task?.cancel(); task = nil
        let wasCapturing = recording || starting || capture != nil; recording = false; starting = false; analyzing = false
        if wasCapturing { monitor.stop(clearAudio: true, reason: "product_recording_cancelled") }
        if let capture { removeTransient(capture) }; capture = nil; recoverCapture()
        if let message { error = message }
    }
    func suspend() {
        cancel(); stopPlayback(); monitor.stop(clearAudio: true, reason: "app_background")
    }
    func resetResult() { completed = nil; error = nil }

    func audioURL(_ recording: HeartRecording) -> URL? {
        if let name = recording.publicSample { return Bundle.main.url(forResource: name, withExtension: "wav", subdirectory: "MurmurSamples") }
        guard let name = recording.audioFile, name == URL(fileURLWithPath: name).lastPathComponent else { return nil }
        let url = root.appendingPathComponent(name); return files.fileExists(atPath: url.path) ? url : nil
    }
    @discardableResult func delete(_ recording: HeartRecording) -> Bool {
        if playing == recording.id { stopPlayback() }
        do { try storage.delete(recording, records: &recordings) }
        catch { self.error = "Deletion could not finish. The result stays available and cleanup is saved for retry: \(error.localizedDescription)"; return false }
        if let name = recording.diagnosticAudio { monitor.note(DiagnosticEvent(event: "audio_deleted", message: "Owned audio removed", audioFile: name)) }
        return true
    }
    func play(_ recording: HeartRecording) {
        guard !busy, !monitor.busy, let url = audioURL(recording) else { return }
        if playing == recording.id { stopPlayback(); return }
        stopPlayback(); monitor.stop(reason: "recording_playback")
        do {
            let session = AVAudioSession.sharedInstance(); try session.setCategory(.playback); try session.setActive(true)
            player = try AVAudioPlayer(contentsOf: url); player?.delegate = self
            guard player?.play() == true else { throw CocoaError(.fileReadUnknown) }; playing = recording.id
        } catch { stopPlayback(); try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation); self.error = "Playback failed: \(error.localizedDescription)" }
    }
    func stopPlayback() {
        let active = player != nil; player?.delegate = nil; player?.stop(); player = nil; playing = nil
        if active { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
    }
    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [weak self, weak player] in
            guard let self, let player, self.player === player else { return }; self.stopPlayback(); self.error = "The saved audio could not be played."
        }
    }
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [weak self, weak player] in
            guard let self, let player, self.player === player else { return }; self.stopPlayback()
        }
    }
}

struct MeasuredWaveform: View {
    let values: [Float]
    var body: some View {
        Canvas { context, size in
            guard !values.isEmpty else { return }; var path = Path()
            for (i, value) in values.enumerated() {
                let x = size.width * Double(i) / Double(max(1, values.count - 1)), height = size.height * Double(min(1, max(0.01, abs(value)))) * 0.9
                path.move(to: CGPoint(x: x, y: (size.height - height) / 2)); path.addLine(to: CGPoint(x: x, y: (size.height + height) / 2))
            }
            context.stroke(path, with: .color(AppStyle.accent), lineWidth: 2)
        }.accessibilityLabel(values.isEmpty ? "No sound samples yet" : "Measured audio envelope, not an ECG")
    }
}
