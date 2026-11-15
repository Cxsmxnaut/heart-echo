import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public enum CareClientError: Error, Equatable { case consentRequired, invalidEndpoint, invalidResponse, http(Int) }
public protocol CareHTTPTransport: Sendable { func perform(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) }
public struct CareURLSessionTransport: CareHTTPTransport {
    public init() {}
    public func perform(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw CareClientError.invalidResponse }
        return (data, response)
    }
}
public struct CareReply: Decodable, Sendable {
    public let session_id: String
    public let message: String
    public let scan_explanation: String
    public let model: ModelStatus
    public struct ModelStatus: Decodable, Sendable { public let mode: String; public let used_this_turn: Bool? }
}
public actor CareClient {
    private let baseURL: URL
    private let token: String?
    private let transport: any CareHTTPTransport
    public init(baseURL: URL, token: String? = nil, transport: any CareHTTPTransport = CareURLSessionTransport()) throws {
        let local = ["127.0.0.1", "localhost", "::1", "[::1]"].contains(baseURL.host ?? "")
        guard baseURL.user == nil, baseURL.password == nil, baseURL.query == nil, baseURL.fragment == nil,
              baseURL.scheme == "https" || (baseURL.scheme == "http" && local) else { throw CareClientError.invalidEndpoint }
        self.baseURL = baseURL; self.token = token; self.transport = transport
    }
    private struct Handoff: Encodable { let action = "explain"; let scan: CareScanSummary?; let session_id: String?; enum CodingKeys: String, CodingKey { case action, scan, session_id }
        func encode(to encoder: Encoder) throws { var c = encoder.container(keyedBy: CodingKeys.self); try c.encode(action, forKey: .action); try c.encode(scan, forKey: .scan); try c.encodeIfPresent(session_id, forKey: .session_id) }
    }
    public func send(summary: CareScanSummary?, consent: Bool, sessionID: String? = nil) async throws -> CareReply {
        guard consent else { throw CareClientError.consentRequired }
        var request = URLRequest(url: baseURL.appendingPathComponent("api/v1/chat")); request.httpMethod = "POST"; request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try JSONEncoder().encode(Handoff(scan: summary, session_id: sessionID))
        let (data, response) = try await transport.perform(request)
        guard (200...299).contains(response.statusCode) else { throw CareClientError.http(response.statusCode) }
        return try JSONDecoder().decode(CareReply.self, from: data)
    }
    public func clear(sessionID: String) async throws {
        guard UUID(uuidString: sessionID) != nil else { throw CareClientError.invalidResponse }
        var request = URLRequest(url: baseURL.appendingPathComponent("api/session/\(sessionID)")); request.httpMethod = "DELETE"; request.timeoutInterval = 15
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        let (_, response) = try await transport.perform(request)
        guard response.statusCode == 204 else { throw CareClientError.http(response.statusCode) }
    }
}
