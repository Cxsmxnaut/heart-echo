import Foundation

/// Owns server session identity independently of what the preview displays.
/// Failed deletion retains the ID so the user can retry the same deletion.
public actor CareHandoffSession {
    private let client: CareClient
    public private(set) var sessionID: String?
    public init(client: CareClient) { self.client = client }
    public func send(summary: CareScanSummary?, consent: Bool) async throws -> CareReply {
        let reply = try await client.send(summary: summary, consent: consent, sessionID: sessionID)
        sessionID = reply.session_id; return reply
    }
    public func clearScan() async throws -> CareReply? {
        guard sessionID != nil else { return nil }
        return try await send(summary: nil, consent: true)
    }
    public func clearAll() async throws {
        guard let id = sessionID else { return }
        try await client.clear(sessionID: id)
        sessionID = nil
    }
}
