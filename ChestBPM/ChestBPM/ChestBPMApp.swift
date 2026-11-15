import SwiftUI

@main struct ChestBPMApp: App {
    private let watch = WatchLink.shared
    var body: some Scene { WindowGroup { ContentView().environmentObject(watch) } }
}
func bpmText(_ bpm: Double?) -> String { bpm.map { String(Int($0.rounded())) } ?? "—" }

struct ContentView: View {
    @StateObject private var monitor = HeartRateMonitor()
    @EnvironmentObject private var watch: WatchLink
    @Environment(\.scenePhase) private var scene
    @Environment(\.openURL) private var openURL
    @State private var position = 0
    private let positions = ["Lower left", "Upper left", "Upper right", "Center"]
    private var r: HeartRateEstimate { monitor.result }
    var body: some View {
        TabView {
            NavigationStack {
                Form {
                    Section {
                        VStack(spacing: 8) {
                            Text(bpmText(r.bpm)).font(.system(size: 88, weight: .semibold, design: .rounded)).monospacedDigit()
                                .contentTransition(.numericText()).animation(.easeOut(duration: 0.2), value: r.bpm)
                                .accessibilityLabel(r.bpm.map { "\(Int($0.rounded())) beats per minute, experimental estimate" } ?? "No BPM estimate")
                            Text("BEATS PER MINUTE").font(.caption).foregroundStyle(.secondary)
                            Text(monitor.playing ? "Playing recent audio · microphone stopped" : r.status)
                                .font(.subheadline).multilineTextAlignment(.center)
                            SoundTrace(values: r.waveform, marks: r.marks).frame(height: 60)
                            Text("Filtered sound · dots mark candidate sounds · not an ECG").font(.caption2).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity).padding(.vertical, 8)
                        Button { if monitor.busy || monitor.playing { monitor.stop() } else { Task { await monitor.start() } } } label: {
                            Label(monitor.preparing ? "Cancel preparation" : monitor.starting ? "Starting…" : monitor.running || monitor.playing ? "Stop" : "Start listening", systemImage: monitor.busy || monitor.playing ? "stop.fill" : "mic.fill")
                        }.disabled(monitor.starting && !monitor.preparing)
                        Button("Stop & hear recent audio", systemImage: "play.fill") { monitor.replay() }.disabled(!monitor.canReplay || monitor.playing || monitor.busy)
                        Button(monitor.study == nil ? "Start \(monitor.duration)-second diagnostic test" : "Ready · start test \(min(monitor.study!.totalTests, monitor.study!.index + 1))/\(monitor.study!.totalTests)", systemImage: "timer") { Task { await monitor.timedTest() } }
                            .keyboardShortcut("r", modifiers: [.command, .shift])
                            .disabled(monitor.busy || monitor.playing || !monitor.canTest || monitor.study?.complete == true)
                        if monitor.preparing { Text(monitor.preparationStatus).foregroundStyle(.pink).accessibilityIdentifier("preparationStatus") }
                        if !monitor.testSummary.isEmpty { Text(monitor.testSummary).font(.caption) }
                        if let remaining = monitor.testRemaining { Text("Hold still · \(remaining) seconds left · stops automatically").foregroundStyle(.pink) }
                        if monitor.logging { Text(monitor.logStatus).font(.caption).foregroundStyle(.secondary) }
                        if let error = monitor.error {
                            Text(error).foregroundStyle(.red)
                            if monitor.denied { Button("Open microphone settings") { openURL(URL(string: UIApplication.openSettingsURLString)!) } }
                        }
                    }
                    Section("Final validation plan") {
                        if let plan = monitor.study {
                            Text(plan.complete ? "All \(plan.totalTests) tests complete" : "Cycle \(plan.cycle)/\(plan.cycles) · Test \(plan.index + 1)/\(plan.totalTests) · \(plan.condition)").font(.headline)
                            if !plan.complete { Text(plan.instruction).font(.subheadline) }
                            Text("The phone starts the Watch, waits for fresh samples, and installs stop timers on both devices. Tap ready between conditions. Audio saving for this plan can be changed below.").font(.caption)
                            Button("End test plan", role: .destructive) { monitor.endStudy() }.disabled(monitor.busy)
                        } else {
                            Button("Set up final validation · 2 cycles") { monitor.beginStudy() }.disabled(monitor.busy || !monitor.canTest)
                            Text("Two cycles: quiet, background sound, movement and off chest. The order rotates. About 10 minutes of recording, plus setup.").font(.caption)
                        }
                    }
                    Section("Test setup") {
                        Picker("Person", selection: $monitor.participant) { Text("A · me").tag("A"); Text("B · friend").tag("B") }
                            .accessibilityIdentifier("participant").onChange(of: monitor.participant) { _, _ in monitor.changedParticipant() }
                        Picker("Condition", selection: $monitor.condition) {
                            ForEach(TrialPlan.conditions + (monitor.condition == "Watch control check" ? ["Watch control check"] : []), id: \.self) { Text($0) }
                        }.accessibilityIdentifier("condition").disabled(monitor.study != nil)
                        if monitor.participant == "B" {
                            Toggle("My friend agrees to this test and local logs", isOn: $monitor.friendConsent).accessibilityIdentifier("friendConsent")
                            Text("Put the Watch on your friend after they agree. The phone starts a fresh session for each timed test. Apple may also add those heart samples to the Watch owner's Health history.").font(.caption)
                        }
                        Toggle("Save test audio on phone and Mac", isOn: Binding(get: { monitor.saveTestAudio }, set: monitor.setAudioPreference)).accessibilityIdentifier("saveTestAudio")
                        Text("Off by default. If enabled, the timed test saves up to 120 seconds locally for noise analysis. No uploads. Delete diagnostic files removes saved audio too.").font(.caption)
                        Toggle("Start and stop Watch automatically", isOn: $monitor.automaticWatch).accessibilityIdentifier("automaticWatch")
                        Text("Unlock and wear the Watch. Apple may ask for Health access once. Each trial has a local stop deadline on the Watch, even if the connection drops.").font(.caption)
                        Text(monitor.modelStatus).font(.caption)
                    }.disabled(monitor.busy)
                    Section("Live Apple Watch") { LiveWatchPanel(packet: monitor.acceptedWatch, pair: monitor.alignedPair) }
                    Section("Find a clear position") {
                        Picker("Position to try", selection: $position) { ForEach(positions.indices, id: \.self) { Text(positions[$0]).tag($0) } }.accessibilityIdentifier("position")
                        Button("Try next position") { position = (position + 1) % positions.count }
                        Text("Remove the case. Rest the bottom microphone gently against bare skin at the selected area of your chest. Keep still in a quiet room; wait 6–8 seconds after moving.")
                        LabeledContent("Sound level", value: monitor.running ? "\(Int(r.level)) dBFS" : "—")
                        Text("Sound level measures loudness, not whether this is your heart. Listen for a repeating lub–dub. Playback stops recording to avoid feedback.")
                    }.font(.subheadline)
                    Section("Check the two counters") {
                        LabeledContent("Original repeating pattern", value: bpmText(r.original))
                        LabeledContent("Full-cycle timing", value: bpmText(r.cycle))
                        if r.diagnostics.source == "recent_window" {
                            LabeledContent("Recent 6-second pattern", value: bpmText(r.diagnostics.recent?.patternBPM))
                            LabeledContent("Recent full-cycle timing", value: bpmText(r.diagnostics.recent?.cycleBPM))
                        }
                        LabeledContent("Previous app estimate", value: bpmText(r.diagnostics.legacyBPM))
                        LabeledContent("Model timing", value: bpmText(r.diagnostics.enhanced?.cycleBPM))
                        Text("The on-device model looks for the two heart sounds. A number also needs repeat timing in the original audio. Short noise bursts are marked and skipped without changing the clock. These labels are experimental.").font(.caption)
                    }
                    Section {
                        Text("Updates about twice a second using the latest 8 seconds. Noise can still create wrong, half, or double readings. Range: about 40–176 BPM. This does not detect AFib or diagnose heart problems.")
                        Text("Recent playback stays in memory. Diagnostics save BPM and signal features locally. Timed-test audio is saved only when you enable its toggle. Nothing is uploaded. This project is a prototype and is not medical advice.")
                        Button("Clear audio & comparisons", role: .destructive) { monitor.clear() }
                    }.font(.caption).foregroundStyle(.secondary)
                }.navigationTitle("Chest BPM")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Watch check") {
                            guard !monitor.busy, monitor.study == nil, monitor.canTest else { return }
                            monitor.condition = "Watch control check"
                            Task { await monitor.timedTest(watchOnly: true) }
                        }.keyboardShortcut("t", modifiers: [.command, .shift])
                            .disabled(monitor.busy || monitor.study != nil || !monitor.canTest)
                    }
                }
            }.tabItem { Label("Measure", systemImage: "waveform") }
            NavigationStack {
                Form {
                    Section("Diagnostic log") {
                        Toggle("Save diagnostic log", isOn: Binding(get: { monitor.logging }, set: monitor.setLogging))
                        Text(monitor.logStatus).font(.caption)
                        Text("Contains phone and Watch BPM, timestamps, signal features, and rejection reasons. Audio is separate and saved only when enabled for a timed test. The connected Mac can read diagnostics live; files remain until cleared or rotated.").font(.caption)
                        ShareLink("Share diagnostic file", item: monitor.logURL).disabled(!FileManager.default.fileExists(atPath: monitor.logURL.path))
                        Button("Delete diagnostic files", role: .destructive) { monitor.clearLogs() }
                    }
                    Section("Automatic Watch comparison") {
                        LiveWatchPanel(packet: monitor.acceptedWatch, pair: monitor.alignedPair)
                        Toggle("Automatically pair live readings", isOn: $monitor.autoCompare).accessibilityIdentifier("autoCompare")
                        Text("Timed tests request the Watch automatically. For an untimed manual comparison, start measuring on the Watch and tap Start listening here. Fresh Watch samples are matched once to phone estimates within 2 seconds of their timestamps. No manual entry is needed.").font(.caption)
                    }
                    Section("Pair with your Apple Watch") {
                        Text("Keep the Watch heart-rate screen open while resting. Read it, then immediately tap Pair reading. This freezes both app readings while you enter the Watch number.")
                        Button("Pair reading", systemImage: "applewatch") { monitor.capturePair() }.disabled(!monitor.running || r.seconds < 6)
                        Text("The app uses the preceding 8 seconds. The Watch may average a different window or update later. These manual pairs are approximate comparisons, not clinical validation.").font(.caption)
                    }
                    Section("Session comparison · \(monitor.pairs.count) pairs") {
                        Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 12) {
                            GridRow { Text("Method"); Text("Original"); Text("New") }.font(.caption.bold())
                            statsRow("Mean error (returned)", { $0.error.map { String(format: "%.1f", $0) } ?? "—" })
                            statsRow("Same-pair error", { $0.commonError.map { String(format: "%.1f", $0) } ?? "—" })
                            statsRow("More than 5 BPM off", { String($0.largeErrors) })
                            statsRow("Unsure / all pairs", { "\($0.missing)/\(monitor.pairs.count)" })
                        }
                        Text("Errors are in BPM. Each mean uses that method’s returned readings; same-pair error uses the \(ComparisonStats(monitor.pairs, improved: true).common) pairs both returned. Compare unsure counts too: rejecting readings can hide errors.").font(.caption)
                    }
                    Section("Paired readings · Watch / Original / New") {
                        ForEach(monitor.pairs.reversed()) { pair in
                            LabeledContent("\(pair.automatic ? "Live" : "Manual") \(pair.time.formatted(date: .omitted, time: .standard))", value: "\(bpmText(pair.watch)) / \(bpmText(pair.original)) / \(bpmText(pair.improved))")
                        }
                        Button("Clear comparisons", role: .destructive) { monitor.pairs = [] }.disabled(monitor.pairs.isEmpty)
                    }
                }.navigationTitle("Watch comparison")
            }.tabItem { Label("Compare", systemImage: "applewatch") }
            NavigationStack {
                MurmurView { monitor.stop(reason: "murmur_analysis") }
            }.tabItem { Label("Murmur", systemImage: "waveform.path.ecg") }
        }.tint(.pink)
        .onReceive(watch.$feed) { monitor.receiveWatch($0) }
        .onReceive(watch.$receipt) { if let event = $0 { monitor.note(event) } }
        .onReceive(watch.$status) { monitor.note(DiagnosticEvent(event: "watch_connection", connection: $0)) }
        .onReceive(monitor.$autoCompare) { monitor.note(DiagnosticEvent(event: "auto_compare_changed", message: String($0))) }
        .sheet(item: $monitor.draft) { pair in WatchEntry(pair: pair) { monitor.savePair(pair, watch: $0) } }
        .onChange(of: position) { _, _ in monitor.changedPosition(positions[position]); if monitor.busy { monitor.stop(clearAudio: true, reason: "position_changed") } }
        .onChange(of: scene) { _, phase in monitor.note(DiagnosticEvent(event: "scene_changed", message: String(describing: phase))); if phase != .active { monitor.stop(clearAudio: true, reason: "app_background") } }
    }
    private func statsRow(_ title: String, _ value: (ComparisonStats) -> String) -> some View {
        GridRow { Text(title); Text(value(ComparisonStats(monitor.pairs, improved: false))); Text(value(ComparisonStats(monitor.pairs, improved: true))) }.font(.subheadline).monospacedDigit()
    }
}

private struct LiveWatchPanel: View {
    @EnvironmentObject private var watch: WatchLink
    let packet: WatchPacket?, pair: WatchPair?
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let fresh = packet?.fresh(at: context.date) == true
            let matched = fresh && pair?.watchTime == packet?.end ? pair : nil
            VStack(alignment: .leading, spacing: 10) {
                LabeledContent("Watch sensor", value: fresh ? bpmText(packet?.bpm) + " BPM" : "—")
                LabeledContent("Phone at Watch sample", value: bpmText(matched?.improved))
                LabeledContent("Time-matched difference", value: matched?.improved.flatMap { p in matched?.watch.map { String(format: "%+.1f BPM", p - $0) } } ?? "—")
                Text(fresh ? "Measured \(max(0, Int(context.date.timeIntervalSince(packet!.end!)))) seconds ago" : packet?.active == true ? "Waiting for a fresh Watch reading" : "Start measuring in Chest BPM on your Watch")
                    .font(.caption).foregroundStyle(.secondary)
                Text(watch.status).font(.caption)
                Button("Stop Watch session", role: .destructive) { watch.stopRemote() }.disabled(packet?.active != true)
            }
        }
    }
}

private struct SoundTrace: View {
    let values: [Float], marks: [Int]
    var body: some View {
        Canvas { context, size in
            var line = Path()
            for (i, value) in (values.isEmpty ? [0.5, 0.5] : values).enumerated() {
                let point = CGPoint(x: size.width * Double(i) / Double(max(values.count - 1, 1)), y: size.height * (0.9 - 0.8 * Double(value)))
                if i == 0 { line.move(to: point) } else { line.addLine(to: point) }
            }
            context.stroke(line, with: .color(.pink), lineWidth: 2)
            for i in marks where values.indices.contains(i) {
                let point = CGPoint(x: size.width * Double(i) / Double(max(values.count - 1, 1)), y: size.height * (0.9 - 0.8 * Double(values[i])))
                context.fill(Path(ellipseIn: CGRect(x: point.x - 3, y: point.y - 3, width: 6, height: 6)), with: .color(.primary))
            }
        }.accessibilityLabel("Filtered microphone sound level and candidate sounds, not an ECG")
    }
}
private struct WatchEntry: View {
    let pair: WatchPair, save: (Int) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    var body: some View {
        NavigationStack {
            Form {
                Text("Enter the Watch BPM you just saw at \(pair.time.formatted(date: .omitted, time: .standard)). App readings were frozen at that moment.")
                LabeledContent("Original / New", value: "\(bpmText(pair.original)) / \(bpmText(pair.improved))")
                TextField("Watch BPM (20–300)", text: $text).keyboardType(.numberPad).accessibilityIdentifier("watchBPM")
                Button("Save pair") { if let bpm = Int(text) { save(bpm) } }.disabled(!(20...300).contains(Int(text) ?? 0))
            }.navigationTitle("Watch reading").toolbar { Button("Cancel") { dismiss() } }
        }
    }
}
