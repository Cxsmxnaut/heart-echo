import AVFoundation
import SwiftUI
import UniformTypeIdentifiers

@MainActor final class MurmurSession: NSObject, ObservableObject, AVAudioRecorderDelegate {
    @Published var recording = false
    @Published var analyzing = false
    @Published var remaining = 20
    @Published var reading: MurmurReading?
    @Published var error: String?
    @Published var source = ""
    private var recorder: AVAudioRecorder?, timer: Task<Void, Never>?, temporary: URL?
    private var token = UUID(), previousIdle = false
    var busy: Bool { recording || analyzing }
    override init() {
        super.init()
        // Remove an unfinished temporary capture left by an interrupted app process.
        let folder = FileManager.default.temporaryDirectory
        for url in (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? [] where url.lastPathComponent.hasPrefix("murmur-capture-") {
            try? FileManager.default.removeItem(at: url)
        }
    }
    func stop() {
        token = UUID(); timer?.cancel(); timer = nil
        recorder?.delegate = nil; recorder?.stop(); recorder = nil
        if recording {
            UIApplication.shared.isIdleTimerDisabled = previousIdle
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
        recording = false; analyzing = false
        if let temporary { try? FileManager.default.removeItem(at: temporary) }; temporary = nil
    }
    func start() async {
        stop(); reading = nil; error = nil; let id = token
        guard await AVAudioApplication.requestRecordPermission() else { error = "Allow microphone access in Settings to record heart sounds."; return }
        guard token == id, UIApplication.shared.applicationState == .active else { return }
        do {
            let session = AVAudioSession.sharedInstance(); try session.setCategory(.record, mode: .measurement); try session.setActive(true)
            if let input = session.availableInputs?.first(where: { $0.portType == .builtInMic }) {
                try session.setPreferredInput(input)
                if let bottom = input.dataSources?.first(where: { $0.location == .lower }) { try? input.setPreferredDataSource(bottom) }
            }
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("murmur-capture-\(UUID()).caf"); temporary = url
            let capture = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000,
                AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false])
            capture.delegate = self; recorder = capture; previousIdle = UIApplication.shared.isIdleTimerDisabled
            guard capture.record(forDuration: 20) else { throw CocoaError(.fileWriteUnknown) }
            UIApplication.shared.isIdleTimerDisabled = true; recording = true; remaining = 20; source = "Phone microphone · transfer to phone audio is unvalidated"
            let began = Date()
            timer = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(250))
                    guard !Task.isCancelled, let self, self.token == id else { return }
                    self.remaining = max(0, 20 - Int(Date().timeIntervalSince(began)))
                }
            }
        } catch { stop(); self.error = "Recording failed: \(error.localizedDescription)" }
    }
    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            guard let self, self.recorder === recorder, let url = self.temporary else { return }
            self.timer?.cancel(); self.timer = nil; self.recorder = nil; self.recording = false
            UIApplication.shared.isIdleTimerDisabled = self.previousIdle
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            guard flag else { self.stop(); self.error = "Recording was interrupted. No result was produced."; return }
            await self.perform(url, id: self.token)
        }
    }
    nonisolated func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        Task { @MainActor [weak self] in self?.stop(); self?.error = "The recording could not be completed." }
    }
    func analyze(_ url: URL, source: String) async {
        stop(); reading = nil; error = nil; self.source = source
        let scoped = url.startAccessingSecurityScopedResource(); defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        await perform(url, id: token)
    }
    private func perform(_ url: URL, id: UUID) async {
        analyzing = true
        do {
            let result = try await Task.detached(priority: .userInitiated) {
                try MurmurAnalyzer().analyze(MurmurAnalyzer.audio(url))
            }.value
            guard token == id else { return }; reading = result
        } catch { if token == id { self.error = "Analysis failed: \(error.localizedDescription)" } }
        guard token == id else { return }; analyzing = false
        if let temporary { try? FileManager.default.removeItem(at: temporary) }; temporary = nil
    }
}

struct MurmurView: View {
    let stopBPM: () -> Void
    @StateObject private var session = MurmurSession()
    @State private var importing = false
    @Environment(\.scenePhase) private var scene
    var body: some View {
        Form {
            Section {
                Label("Murmur research", systemImage: "waveform.path.ecg").font(.title2.bold())
                Text("Looks for murmur-like sound patterns. This does not identify a valve disease or check for AFib.")
                Text("This project is a prototype and is not medical advice.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Analyze a public recording") {
                ForEach([("absent", "No murmur annotated"), ("present", "Murmur annotated"), ("unknown", "Uncertain annotation")], id: \.0) { sample in
                    Button(sample.1, systemImage: "waveform") {
                        guard let url = Bundle.main.url(forResource: sample.0, withExtension: "wav", subdirectory: "MurmurSamples") else { session.error = "Public sample is missing."; return }
                        stopBPM(); Task { await session.analyze(url, source: "Public CirCor sample · reference: \(sample.1.lowercased())") }
                    }.accessibilityIdentifier("murmur.sample.\(sample.0)")
                }.disabled(session.busy)
                Text("These are public stethoscope recordings with dataset labels. The model can disagree with a label.").font(.caption)
                Button("Import an audio recording", systemImage: "document") { stopBPM(); importing = true }.disabled(session.busy)
            }
            Section("Experimental phone recording") {
                Text("Remove the case and rest the bottom microphone gently against bare chest skin. Support your arms and keep still in a quiet room. Position affects which sounds can be heard.")
                Button(session.recording ? "Cancel recording · \(session.remaining)s left" : "Record 20 seconds", systemImage: session.recording ? "stop.fill" : "mic.fill") {
                    if session.recording { session.stop() } else { stopBPM(); Task { await session.start() } }
                }.disabled(session.analyzing).accessibilityIdentifier("murmur.record")
                Text("Phone accuracy has not been established. Audio is processed on this device; the temporary capture is deleted after analysis or cancellation. Imported audio uses at most its first 60 seconds.").font(.caption)
            }
            if session.analyzing { Section { ProgressView("Analyzing sound on this device…") } }
            if let r = session.reading {
                Section("Research result") {
                    Text(r.title).font(.headline).accessibilityIdentifier("murmur.result")
                    Text(session.source).font(.caption).accessibilityIdentifier("murmur.source")
                    if r.finding == .present { Text("The model found a murmur-like pattern. It cannot determine its cause or severity.") }
                    else if r.finding == .absent { Text("A murmur was not detected in this recording. This does not rule out a murmur elsewhere or heart disease.") }
                    else { Text("The model could not give a clear result. This does not tell you whether a murmur is present or absent.") }
                    Text("\(r.windows) usable four-second windows · \(Int(r.seconds)) seconds of audio. Windows can overlap.").font(.caption)
                }
            }
            if let error = session.error { Section { Text(error).foregroundStyle(.red).accessibilityIdentifier("murmur.error") } }
            Section("About the model") {
                Text("Experimental model trained on public stethoscope recordings. It uses heartbeat phases and murmur timing to look for sound patterns. Its three labels describe sounds, not a diagnosis. Phone accuracy has not been established.").font(.caption)
                Link("CirCor data and attribution · Oliveira et al.", destination: URL(string: "https://doi.org/10.13026/tshs-mw03")!)
            }
        }.navigationTitle("Murmur")
            .onAppear { stopBPM() }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.audio]) { result in
                switch result {
                case .success(let url): stopBPM(); Task { await session.analyze(url, source: "Imported audio · \(url.lastPathComponent)") }
                case .failure(let error): session.error = error.localizedDescription
                }
            }
            .onDisappear { session.stop() }
            .onChange(of: scene) { _, phase in if phase != .active { session.stop() } }
            .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { event in
                if event.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt == AVAudioSession.InterruptionType.began.rawValue { session.stop() }
            }
    }
}
