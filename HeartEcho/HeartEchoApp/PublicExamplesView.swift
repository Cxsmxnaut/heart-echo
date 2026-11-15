import SwiftUI

struct PublicExamplesView: View {
    @EnvironmentObject private var store: HeartEchoStore
    @Environment(\.dismiss) private var dismiss
    private let examples = [
        ("present", "Murmur annotated", "An expert annotated a murmur in this public stethoscope recording.", "waveform"),
        ("absent", "No murmur annotated", "The reference label is absent. Our model may still return unsure.", "waveform.path"),
        ("unknown", "Uncertain annotation", "The expert annotation is uncertain. This is different from absent.", "questionmark.circle")
    ]
    var body: some View {
        NavigationStack {
            Group {
                if let record = store.completed { RecordingResultView(result: ScreeningResult(recording: record)) }
                else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            Text("Hear the difference.").font(.largeTitle.bold())
                            Text("Run the actual on-device model on licensed public recordings. These are examples, not recordings of your heart.").foregroundStyle(.secondary)
                            ForEach(examples, id: \.0) { example in
                                HealthCard {
                                    CardLabel(title: example.1, symbol: example.3)
                                    Text(example.2).font(.subheadline).foregroundStyle(.secondary)
                                    Button("Analyze recording", systemImage: "play.circle.fill") { Task { await store.analyzePublic(example.0) } }
                                        .accessibilityIdentifier("product.sample.\(example.0)")
                                }
                            }
                            if store.analyzing { ProgressView("Analyzing on this iPhone…") }
                            if let error = store.error { Text(error).foregroundStyle(.red) }
                            Link("CirCor dataset and attribution", destination: URL(string: "https://doi.org/10.13026/tshs-mw03")!)
                            Footnote(text: "Reference annotations and model predictions can disagree. No microphone permission is needed. No BPM is measured for these examples.")
                        }.padding(20)
                    }.disabled(store.busy)
                }
            }.background(AppStyle.background).navigationTitle(store.completed == nil ? "Public Recordings" : "Your Result").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { store.cancel(); dismiss() } } }
        }.onAppear { store.resetResult() }.onDisappear { store.cancel() }
    }
}
