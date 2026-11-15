import SwiftUI

@main
struct HeartEchoApp: App {
    @StateObject private var store = HeartEchoStore()
    @StateObject private var care = CareService()
    @Environment(\.scenePhase) private var scene
    var body: some Scene {
        WindowGroup {
            Group {
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("--diagnostics-ui") {
                    LegacyDiagnosticsView(monitor: store.monitor)
                } else { ScreenshotPreviewHost() }
                #else
                RootView()
                #endif
            }
            .environmentObject(store).environmentObject(care).environmentObject(WatchLink.shared).tint(AppStyle.accent)
            .onChange(of: scene) { _, phase in
                store.monitor.note(DiagnosticEvent(event: "scene_changed", message: String(describing: phase)))
                if phase == .background || phase == .inactive && store.monitor.running { store.suspend() }
            }
        }
    }
}

enum AppTab: Hashable { case summary, recordings, care }

struct RootView: View {
    @State private var tab: AppTab
    init(initialTab: AppTab = .summary) { _tab = State(initialValue: initialTab) }
    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { SummaryView(tab: $tab) }.tabItem { Label("Summary", systemImage: "heart.fill") }.tag(AppTab.summary)
            NavigationStack { RecordingsView() }.tabItem { Label("Recordings", systemImage: "waveform") }.tag(AppTab.recordings)
            NavigationStack { AssistantView() }.tabItem { Label("Care", systemImage: "cross.case.fill") }.tag(AppTab.care)
        }
    }
}

#if DEBUG
private struct ScreenshotPreviewHost: View {
    private let environment = ProcessInfo.processInfo.environment
    var body: some View {
        Group {
            switch environment["HEART_ECHO_PREVIEW_SCREEN"] {
            case "recordings": RootView(initialTab: .recordings)
            case "care": RootView(initialTab: .care)
            case "prepare": RecordingFlowView()
            case "record", "record-finished": RecordingFlowView(previewStep: 1)
            case "result", "assistant": RecordingFlowView(previewStep: 2)
            case "assistant-chat": NavigationStack { AssistantView(result: .preview, previewConversation: true) }
            default: RootView()
            }
        }.preferredColorScheme(environment["HEART_ECHO_PREVIEW_APPEARANCE"] == "dark" ? .dark : environment["HEART_ECHO_PREVIEW_APPEARANCE"] == "light" ? .light : nil)
    }
}
#endif

struct SummaryView: View {
    @EnvironmentObject private var store: HeartEchoStore
    @AppStorage("developerMode") private var developerMode = false
    @Binding var tab: AppTab
    @State private var showRecording = false
    @State private var showExamples = false
    @State private var showAbout = false
    @State private var showTools = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text(Date.now, format: .dateTime.weekday(.wide).month(.wide).day())
                    Spacer(); Text("HEART ECHO").tracking(1.8)
                }.font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                HealthCard {
                    CardLabel(title: "Heart Sounds", symbol: "waveform.path.ecg")
                    Text("Take a moment.\nListen to your heart.").font(.system(.title, design: .rounded, weight: .bold))
                    Text("A private recording. An experimental on-device analysis.").font(.subheadline).foregroundStyle(.secondary)
                    MeasuredWaveform(values: store.recordings.first?.waveform ?? []).frame(height: 74)
                    PrimaryButton(title: "Record Heart Sounds", symbol: "waveform") { showRecording = true }.accessibilityIdentifier("record-heart-sounds")
                    Button("Try a public example", systemImage: "play.circle") { showExamples = true }.accessibilityIdentifier("try-public-example")
                    Label("About 20 seconds · Just your iPhone", systemImage: "iphone").font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                }
                SectionHeading(title: "Highlights")
                if let latest = store.recordings.first {
                    NavigationLink { RecordingDetailView(recording: latest) } label: {
                        HealthCard {
                            CardLabel(title: "Latest Result", symbol: "heart.fill")
                            HStack(alignment: .lastTextBaseline) {
                                Text(bpmText(latest.bpm)).font(.system(size: 44, weight: .bold, design: .rounded))
                                Text("BPM").foregroundStyle(.secondary)
                            }
                            Text(latest.finding).font(.headline)
                            Text(latest.source + " · " + latest.date).font(.caption).foregroundStyle(.secondary)
                        }
                    }.buttonStyle(.plain)
                } else {
                    HealthCard {
                        CardLabel(title: "No recordings yet", symbol: "heart")
                        Text("Your measurements will appear here. You can also analyze a public example without using the microphone.").foregroundStyle(.secondary)
                    }.accessibilityIdentifier("empty-history")
                }
                HealthCard {
                    HStack { CardLabel(title: "Recent Recordings", symbol: "waveform", color: .orange); Spacer(); Button("See All") { tab = .recordings } }
                    ForEach(store.recordings.prefix(2)) { recording in
                        NavigationLink { RecordingDetailView(recording: recording) } label: { RecordingRow(recording: recording) }.buttonStyle(.plain)
                    }
                    if store.recordings.isEmpty { Text("No saved results").foregroundStyle(.secondary) }
                }
                if developerMode {
                HealthCard {
                    CardLabel(title: "Live BPM & Watch", symbol: "applewatch")
                    Text("Live microphone estimates, Watch comparisons, audio replay and diagnostic test cycles.").font(.subheadline).foregroundStyle(.secondary)
                    Button("Open Live & Diagnostic Tools") { store.stopPlayback(); showTools = true }.accessibilityIdentifier("open-diagnostics")
                }
                }
                HealthCard {
                    CardLabel(title: "Find Care", symbol: "cross.case.fill", color: .blue)
                    Text("Care starts with\na conversation.").font(.title2.bold())
                    Text("Explore care options and questions to ask a provider.").foregroundStyle(.secondary)
                    Button("Explore Care") { tab = .care }
                }
                Footnote()
            }.padding(.horizontal, 20).padding(.top, 6)
        }.background(AppStyle.background).navigationTitle("Summary")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button { showAbout = true } label: { Image(systemName: "gearshape.fill").font(.title2) }.accessibilityLabel("Settings") } }
            .sheet(isPresented: $showRecording) { RecordingFlowView() }
            .sheet(isPresented: $showExamples) { PublicExamplesView() }
            .sheet(isPresented: $showAbout) { AboutView() }
            .fullScreenCover(isPresented: $showTools, onDismiss: { store.monitor.stop(reason: "diagnostics_closed") }) {
                VStack(spacing: 0) {
                    HStack { Text("Live & Diagnostic Tools").font(.headline); Spacer(); Button("Done") { showTools = false } }.padding()
                    LegacyDiagnosticsView(monitor: store.monitor)
                }
            }
    }
}

struct AboutView: View {
    @EnvironmentObject private var store: HeartEchoStore
    @AppStorage("developerMode") private var developerMode = false
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label("Heart Echo", systemImage: "heart.fill").font(.title2.bold()).foregroundStyle(AppStyle.accent)
                    Text("Version \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")")
                }
                Section("Developer Tools") {
                    Toggle("Developer Mode", isOn: $developerMode).accessibilityIdentifier("developer-mode")
                        .onChange(of: developerMode) { _, enabled in
                            if !enabled { store.monitor.stop(clearAudio: true, reason: "developer_mode_disabled"); store.monitor.setLogging(false) }
                        }
                    Text("Show live BPM, Watch comparisons, diagnostic tracking and diagnostic controls. Turning this off gives you the regular app experience. Your saved tests stay intact.").font(.caption).foregroundStyle(.secondary)
                }
                Section("On this iPhone") {
                    Text("Microphone BPM, motion checks and the phase-aware murmur model run on this device. Watch BPM is an optional comparison reference and never enters either estimate.")
                    Text("Recording history stays here. Microphone audio is deleted after analysis unless you choose to retain it. The original Chest BPM app and its diagnostic data remain separate.")
                    Text("Saved results have local explanations. Care search uses public directories directly from this iPhone. Connect the optional care service for Gemma-assisted chat. You choose whether to send a small result summary; audio stays here.")
                }
                Section("About Your Results") {
                    Text("Phone accuracy has not been established. These research sound labels cannot tell you whether your heart is healthy, identify a valve disease, or check for AFib.")
                    Text("This project is a prototype and is not medical advice.")
                    Footnote()
                    Link("Public CirCor data and attribution", destination: URL(string: "https://doi.org/10.13026/tshs-mw03")!)
                }
            }.navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
