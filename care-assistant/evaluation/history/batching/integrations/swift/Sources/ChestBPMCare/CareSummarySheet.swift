#if canImport(SwiftUI)
import SwiftUI

/// Optional sheet: no work occurs on appearance; sending requires an explicit tap.
/// This is a handoff preview, not a replacement native care-search UI.
public struct CareSummarySheet: View {
    @State private var session: CareHandoffSession
    @State private var summary: CareScanSummary?
    @State private var reply: CareReply?
    @State private var busy = false
    @State private var error: String?
    public init(summary: CareScanSummary?, client: CareClient) { _session = State(initialValue: CareHandoffSession(client: client)); _summary = State(initialValue: summary) }
    public var body: some View {
        NavigationStack {
            Form {
                Section("Summary to share") {
                    if let summary {
                        Text(summary.synthetic ? "Synthetic example" : "Chest BPM summary")
                        Text(summary.estimated_bpm.map { "\(Int($0.rounded())) BPM · experimental timing" } ?? "No usable BPM estimate")
                        Text(summary.captured_at == nil ? "Capture time unavailable" : "Capture time supplied")
                    } else { Text("No scan attached. Care help can continue.") }
                    Text("A usable timing estimate is not a healthy-heart result or disease screen.").font(.caption)
                    Text("Only this summary is sent. No audio, Watch data, participant details or diagnostic logs. The care model runs on the configured Mac/server, not on this iPhone.").font(.caption)
                    Button("Send this summary") { Task { await send() } }.disabled(busy)
                    Button("Clear scan", role: .destructive) { Task { await clearScan() } }.disabled(busy)
                }
                if let reply {
                    Section("Chest BPM care assistant") {
                        Text(reply.message)
                        if reply.model.mode == "guided_fallback" { Text("Using guided help. The care model could not complete this request.").font(.caption) }
                    }
                }
                if let error { Text(error).foregroundStyle(.red) }
                if busy { ProgressView("Contacting care assistant…") }
                Button("Clear chat and scan", role: .destructive) { Task { await clear() } }.disabled(busy)
            }.navigationTitle("Care assistant")
        }
    }
    @MainActor private func send() async {
        busy = true; error = nil; defer { busy = false }
        do { reply = try await session.send(summary: summary, consent: true) }
        catch { self.error = "The care assistant could not be reached. Check the separately configured connection and try again." }
    }
    @MainActor private func clear() async {
        busy = true; error = nil; defer { busy = false }; summary = nil; reply = nil
        do { try await session.clearAll() }
        catch { self.error = "Cleared this preview. The server chat could not be deleted. Tap Clear chat and scan to retry; otherwise server memory expires after inactivity." }
    }
    @MainActor private func clearScan() async {
        summary = nil
        busy = true; defer { busy = false }
        do { reply = try await session.clearScan() }
        catch { self.error = "Cleared this preview. The server could not be reached to clear its attached summary." }
    }
}
#endif
