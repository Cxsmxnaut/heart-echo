import SwiftUI
import UniformTypeIdentifiers

struct RecordingFlowView: View {
    @EnvironmentObject private var store: HeartEchoStore
    @Environment(\.dismiss) private var dismiss
    @AppStorage("developerMode") private var developerMode = false
    @State private var importing = false
    private let previewStep: Int
    init(previewStep: Int = 0) {
        #if DEBUG
        self.previewStep = previewStep
        #else
        self.previewStep = 0
        #endif
    }
    var body: some View {
        NavigationStack {
            Group {
                if let result = store.completed { RecordingResultView(result: ScreeningResult(recording: result)) }
                else if previewStep == 2 {
                    #if DEBUG
                    RecordingResultView(result: .preview)
                    #endif
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            if store.recording || store.starting || store.analyzing || previewStep == 1 { recording } else { preparation }
                            if let error = store.error { Text(error).foregroundStyle(.red).accessibilityIdentifier("capture-error") }
                        }.padding(24)
                    }.background(AppStyle.background)
                }
            }.navigationTitle(store.completed != nil || previewStep == 2 ? "Your Result" : store.busy || previewStep == 1 ? "Heart Sounds" : "Before You Begin")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { store.cancel(); dismiss() } } }
        }
        .safeAreaInset(edge: .top) {
            if store.completed != nil, let error = store.error { Text(error).font(.callout).foregroundStyle(.red).padding().background(.regularMaterial) }
        }
        .onAppear { store.resetResult() }
        .onDisappear { store.cancel() }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.audio]) { result in
            switch result { case .success(let url): Task { await store.analyzeImport(url) }; case .failure(let error): store.error = error.localizedDescription }
        }
    }
    private var preparation: some View {
        Group {
            VStack(spacing: 18) {
                Image(systemName: "iphone").font(.system(size: 64, weight: .light)).foregroundStyle(AppStyle.accent).frame(height: 110)
                Text("A quiet moment\ngoes a long way.").font(.system(.largeTitle, design: .rounded, weight: .bold)).multilineTextAlignment(.center)
                Text("Get comfortable before your recording.").foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity).padding(.vertical, 16)
            HealthCard {
                DetailRow(symbol: "speaker.slash", title: "Find a quiet space", subtitle: "Move away from conversations, music and fans.")
                Divider()
                DetailRow(symbol: "figure.seated.side", title: "Support your arms", subtitle: "Keep still. Position and movement affect the result.")
                Divider()
                DetailRow(symbol: "iphone", title: "Position the microphone", subtitle: "Remove the case. Rest the bottom microphone gently against bare chest skin.")
                Toggle("Keep microphone audio on this iPhone", isOn: $store.keepAudio).accessibilityIdentifier("keep-recording-audio")
                Text("Off by default. A temporary capture is needed for analysis, then deleted. History keeps the result and measured waveform; imports are not copied.").font(.caption).foregroundStyle(.secondary)
            }
            if developerMode && store.monitor.logging { Text("Diagnostic logging is on. Kept audio is also available to your Mac's diagnostic collector.").font(.caption).foregroundStyle(.secondary) }
            PrimaryButton(title: "Start 20-second Recording", symbol: "mic.fill") { Task { await store.start() } }.accessibilityIdentifier("start-real-recording")
            HealthCard {
                Text("Explore without recording").font(.headline)
                ForEach([("absent", "No murmur annotated"), ("present", "Murmur annotated"), ("unknown", "Uncertain annotation")], id: \.0) { sample in
                    Button(sample.1) { Task { await store.analyzePublic(sample.0) } }.accessibilityIdentifier("product.sample.\(sample.0)")
                }
                Button("Import Audio", systemImage: "document") { importing = true }
                Text("Public stethoscope examples carry reference labels. The model can disagree. Imports use at most their first 60 seconds; microphone BPM is not measured for examples or imports.").font(.caption).foregroundStyle(.secondary)
            }
            Footnote(text: "Phone accuracy has not been established. Murmur analysis runs independently of BPM and Watch readings.")
        }.disabled(store.busy)
    }
    private var recording: some View {
        VStack(spacing: 26) {
            Text(previewStep == 1 ? "DESIGN PREVIEW · MICROPHONE OFF" : store.analyzing ? "ON-DEVICE ANALYSIS" : "MICROPHONE RECORDING").font(.caption.weight(.semibold)).tracking(1.5).foregroundStyle(.secondary)
            Text(store.analyzing ? "Reviewing the sound." : store.starting ? "Starting microphone…" : "A moment to listen.").font(.system(.largeTitle, design: .rounded, weight: .bold)).multilineTextAlignment(.center)
            ZStack {
                Circle().stroke(AppStyle.accent.opacity(0.1), lineWidth: 7)
                Circle().trim(from: 0, to: Double(20 - store.remaining) / 20).stroke(AppStyle.accent, style: StrokeStyle(lineWidth: 7, lineCap: .round)).rotationEffect(.degrees(-90))
                VStack(spacing: 5) {
                    Text(store.analyzing ? "…" : String(format: "0:%02d", store.remaining)).font(.system(size: 52, weight: .semibold, design: .rounded)).monospacedDigit()
                    Text(store.analyzing ? "Analyzing" : "remaining").foregroundStyle(.secondary)
                }
            }.frame(width: 235, height: 235).padding(.vertical, 14)
            Text(bpmText(store.live.bpm) + " BPM").font(.largeTitle.bold()).accessibilityIdentifier("live-product-bpm")
            Text(store.live.status).font(.caption).foregroundStyle(.secondary)
            MeasuredWaveform(values: store.live.waveform).frame(height: 74)
            Text("Filtered audio envelope · not an ECG").font(.caption).foregroundStyle(.secondary)
            Button("Cancel Recording", role: .destructive) { store.cancel() }
            Footnote(text: "The phone stops automatically. An unsure result is kept as unsure.")
        }.frame(maxWidth: .infinity).padding(.top, 24)
    }
}

struct RecordingResultView: View {
    let result: ScreeningResult

    private var symbol: String {
        switch result.resultTitle {
        case "Murmur-like pattern": return "waveform.path.ecg"
        case "No murmur detected": return "heart.text.clipboard"
        default: return "questionmark.heart"
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 12) {
                    Image(systemName: symbol)
                        .font(.system(size: 34, weight: .medium))
                        .foregroundStyle(AppStyle.accent)
                        .frame(width: 68, height: 68)
                        .background(AppStyle.accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 20))
                    Text("YOUR HEART-SOUND RESULT")
                        .font(.caption.weight(.semibold)).tracking(1.3).foregroundStyle(.secondary)
                    Text(result.resultTitle)
                        .font(.system(.largeTitle, design: .rounded, weight: .bold))
                        .accessibilityIdentifier("recording-result-title")
                    Text(result.explanation)
                        .font(.body).foregroundStyle(.secondary)
                        .accessibilityIdentifier("recording-result-explanation")
                }.frame(maxWidth: .infinity, alignment: .leading)

                if result.recording.isExample {
                    Label("This is a public example, not your recording.", systemImage: "info.circle")
                        .font(.subheadline).foregroundStyle(.secondary)
                        .accessibilityIdentifier("recording-result-example")
                }

                HealthCard {
                    CardLabel(title: "Recording overview", symbol: "waveform")
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Heart rate").font(.caption).foregroundStyle(.secondary)
                            Text(result.recording.bpm.map { bpmText($0) + " BPM" } ?? "Unavailable")
                                .font(.title3.weight(.semibold))
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            Text("Recording").font(.caption).foregroundStyle(.secondary)
                            Text("\(Int(result.recording.seconds.rounded())) seconds").font(.subheadline.weight(.medium))
                        }
                    }
                }
                Text("Heart Echo can be wrong. This result is not a diagnosis. A clinician can review it and help you decide what to do next.")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .accessibilityIdentifier("recording-result-reminder")
            }.padding(24)
        }
        .background(AppStyle.background)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 8) {
                NavigationLink { AssistantView(result: result) } label: {
                    Label("Find care with AI", systemImage: "bubble.left.and.bubble.right.fill")
                        .font(.body.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: 54)
                        .foregroundStyle(.white)
                        .background(Color(red: 0.78, green: 0.10, blue: 0.24), in: RoundedRectangle(cornerRadius: 15))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("result-find-care")
                Text("Your audio stays on this iPhone.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 20).padding(.vertical, 12)
            .background(.regularMaterial)
        }
    }
}
