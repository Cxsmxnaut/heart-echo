import SwiftUI

struct RecordingsView: View {
    @EnvironmentObject private var store: HeartEchoStore
    @State private var showRecording = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HealthCard {
                    CardLabel(title: "Your Heart Sounds", symbol: "waveform")
                    Text("Small moments.\nAll in one place.").font(.title2.bold())
                    Text("Revisit your results and what you'd like to discuss with a clinician.").font(.subheadline).foregroundStyle(.secondary)
                    PrimaryButton(title: "New Recording", symbol: "plus") { showRecording = true }.accessibilityIdentifier("new-recording")
                }
                SectionHeading(title: "Saved Results")
                HealthCard {
                    if store.recordings.isEmpty { Text("No saved recordings yet.").foregroundStyle(.secondary).accessibilityIdentifier("empty-recordings") }
                    ForEach(store.recordings) { recording in
                        NavigationLink { RecordingDetailView(recording: recording) } label: { RecordingRow(recording: recording) }.buttonStyle(.plain)
                        if recording.id != store.recordings.last?.id { Divider() }
                    }
                }
                Footnote(text: "Results are stored on this iPhone. Audio is available only for public samples or microphone recordings you chose to keep.")
                if let error = store.error { Text(error).foregroundStyle(.red) }
            }.padding(20)
        }.background(AppStyle.background).navigationTitle("Recordings")
            .sheet(isPresented: $showRecording) { RecordingFlowView() }
    }
}

struct RecordingRow: View {
    let recording: HeartRecording
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "waveform").font(.title3.weight(.medium)).foregroundStyle(AppStyle.accent)
                .frame(width: 44, height: 44).background(AppStyle.accent.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 5) {
                Text(recording.title).font(.subheadline.weight(.semibold))
                Text(recording.date).font(.caption).foregroundStyle(.secondary)
                Text(recording.source).font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 6)
            VStack(alignment: .trailing, spacing: 5) {
                Text(recording.bpm.map { bpmText($0) + " BPM" } ?? "BPM —").font(.subheadline.weight(.semibold))
                Text(recording.finding).font(.caption).foregroundStyle(.secondary)
            }
            Image(systemName: "chevron.right").font(.caption.bold()).foregroundStyle(.tertiary)
        }.padding(.vertical, 2).contentShape(Rectangle())
    }
}

struct RecordingDetailView: View {
    let recording: HeartRecording
    @EnvironmentObject private var store: HeartEchoStore
    @EnvironmentObject private var care: CareService
    @Environment(\.dismiss) private var dismiss
    @State private var confirmDelete = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(recording.source.uppercased()).font(.caption.weight(.semibold)).tracking(1).foregroundStyle(.secondary)
                HealthCard {
                    CardLabel(title: "Heart Sounds", symbol: "waveform")
                    Text(recording.title).font(.title2.bold())
                    Text(recording.date).font(.subheadline).foregroundStyle(.secondary)
                    MeasuredWaveform(values: recording.waveform).frame(height: 110).padding(.vertical, 12)
                    HStack { Label("\(Int(recording.seconds.rounded())) seconds analyzed", systemImage: "clock"); Spacer(); Text("Measured audio") }.font(.caption).foregroundStyle(.secondary)
                    if let reference = recording.reference { Text("Dataset reference: " + reference).font(.caption).foregroundStyle(.secondary) }
                    if let audio = store.audioURL(recording) {
                        HStack {
                            Button(store.playing == recording.id ? "Stop Audio" : "Play Audio", systemImage: store.playing == recording.id ? "stop.fill" : "play.fill") { store.play(recording) }
                            Spacer(); ShareLink(item: audio) { Label("Share Audio", systemImage: "square.and.arrow.up") }
                        }
                    } else { Text("Audio was not retained.").font(.caption).foregroundStyle(.secondary) }
                }
                HealthCard {
                    CardLabel(title: "Recording Overview", symbol: "heart.text.clipboard", color: .orange)
                    Text("Estimated Heart Rate").font(.subheadline).foregroundStyle(.secondary)
                    Text(bpmText(recording.bpm) + " BPM").font(.system(size: 40, weight: .bold, design: .rounded))
                    Text(recording.signalStatus).font(.caption).foregroundStyle(.secondary)
                    Divider()
                    Text(recording.finding).font(.title2.bold()).accessibilityIdentifier("saved-murmur-result")
                    Text(ScreeningResult(recording: recording).explanation).font(.subheadline)
                    if let assessment = recording.audioAssessment { Text(assessment.detail).font(.caption).foregroundStyle(.secondary) }
                    Text("\(recording.murmur?.windows ?? 0) analyzed windows · \(recording.modelRevision)").font(.caption).foregroundStyle(.secondary)
                    NavigationLink { AssistantView(result: ScreeningResult(recording: recording)) } label: { Label("Find care with AI", systemImage: "bubble.left.and.bubble.right") }.accessibilityIdentifier("explain-saved-result")
                }
                ResultSummaryShareCard(result: ScreeningResult(recording: recording), accessibilityID: "saved-share-summary")
                Footnote()
                if let error = store.error { Text(error).foregroundStyle(.red).accessibilityIdentifier("recording-file-error") }
                Button("Delete Recording", role: .destructive) { confirmDelete = true }
                    .disabled(care.busy && care.chatRecording?.id == recording.id)
                    .accessibilityIdentifier("delete-recording")
            }.padding(20)
        }.background(AppStyle.background).navigationTitle("Recording").navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("Delete this result and its retained audio?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete", role: .destructive) {
                    if store.delete(recording) {
                        Task { await care.forgetDeletedRecording(recording.id) }
                        dismiss()
                    }
                }
            }
            .onDisappear { store.stopPlayback() }
    }
}

struct ResultSummaryShareCard: View {
    let result: ScreeningResult
    let accessibilityID: String

    var body: some View {
        HealthCard {
            CardLabel(title: "Take your result with you", symbol: "square.and.arrow.up")
            Text("Share the finding and measured values to help prepare for a conversation with a clinician.")
                .font(.subheadline).foregroundStyle(.secondary)
            ShareLink(item: result.shareSummary, subject: Text("Heart Echo recording summary"),
                      preview: SharePreview("Heart Echo result summary")) {
                Label("Share Result Summary", systemImage: "square.and.arrow.up")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 32)
            }
            .buttonStyle(.bordered)
            .tint(AppStyle.accent)
            .accessibilityIdentifier(accessibilityID)
            .accessibilityHint("Opens the share sheet for a text summary. Audio is not attached.")
            Text("Text only. No audio is attached.").font(.caption).foregroundStyle(.secondary)
        }
    }
}
