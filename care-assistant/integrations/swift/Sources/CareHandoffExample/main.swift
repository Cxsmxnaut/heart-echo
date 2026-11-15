import Foundation
import ChestBPMCare

// Explicitly synthetic CLI smoke example; never reads the native app or files.
@main struct CareHandoffExample {
    static func main() async throws {
        let url = URL(string: ProcessInfo.processInfo.environment["CARE_BASE_URL"] ?? "http://127.0.0.1:4318")!
        let client = try CareClient(baseURL: url, token: ProcessInfo.processInfo.environment["CARE_API_TOKEN"])
        let summary = ChestBPMCareSnapshot(acceptedBPM: 74.33333, analysisWindowSeconds: 8).summary(quality: .usable, synthetic: true)
        let reply = try await client.send(summary: summary, consent: true)
        print("Synthetic Swift handoff passed. Response mode: \(reply.model.mode)")
        print(reply.scan_explanation)
        try await client.clear(sessionID: reply.session_id)
        print("Synthetic session cleared.")
    }
}
