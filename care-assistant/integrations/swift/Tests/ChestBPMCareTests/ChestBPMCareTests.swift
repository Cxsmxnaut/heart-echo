import XCTest
import Foundation
@testable import ChestBPMCare
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

private actor RecordingTransport: CareHTTPTransport {
    var requests: [URLRequest] = []
    let status: Int
    var deleteFailures: Int
    init(status: Int = 200, deleteFailures: Int = 0) { self.status = status; self.deleteFailures = deleteFailures }
    func perform(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        requests.append(request)
        let body = #"{"session_id":"10000000-0000-4000-8000-000000000001","message":"Synthetic reply","scan_explanation":"Synthetic explanation","model":{"mode":"guided_fallback","used_this_turn":false}}"#.data(using: .utf8)!
        let responseStatus: Int
        if request.httpMethod == "DELETE" && deleteFailures > 0 { deleteFailures -= 1; responseStatus = 503 }
        else { responseStatus = request.httpMethod == "DELETE" && status == 200 ? 204 : status }
        return (body, HTTPURLResponse(url: request.url!, statusCode: responseStatus, httpVersion: nil, headerFields: nil)!)
    }
}
@MainActor final class ChestBPMCareTests: XCTestCase {
    func encoded(_ summary: CareScanSummary) throws -> [String: Any] { try JSONSerialization.jsonObject(with: JSONEncoder().encode(summary)) as! [String: Any] }
    func testOnlyAcceptedBPMIsUsed() throws {
        let s = ChestBPMCareSnapshot(acceptedBPM: nil, patternBPM: 150, cycleBPM: 75, analysisWindowSeconds: 8).summary(quality: .usable, includeComparisonCounters: true)
        XCTAssertEqual(s.quality, .unclear); XCTAssertNil(s.estimated_bpm); XCTAssertNil(s.timing_counters)
        XCTAssertTrue(try encoded(s)["estimated_bpm"] is NSNull)
    }
    func testWindowIsNotRecordingDurationAndNoTimestampIsInvented() throws {
        let s = ChestBPMCareSnapshot(acceptedBPM: 74, analysisWindowSeconds: 8).summary(quality: .usable)
        let j = try encoded(s); XCTAssertEqual(j["analysis_window_seconds"] as? Double, 8); XCTAssertNil(j["duration_seconds"]); XCTAssertNil(j["captured_at"]); XCTAssertNil(j["timing_counters"])
    }
    func testUnclearAndUnavailableOmitAllBPMCounters() throws {
        for quality in [CareScanQuality.unclear, .unavailable] {
            let s = ChestBPMCareSnapshot(acceptedBPM: 74, patternBPM: 148, cycleBPM: 74).summary(quality: quality, includeComparisonCounters: true)
            XCTAssertNil(s.estimated_bpm); XCTAssertNil(s.timing_counters)
        }
    }
    func testInvalidAcceptedEstimateCannotBeRescuedByComparisons() {
        for bpm in [Double.nan, .infinity, 0, 301] {
            let s = ChestBPMCareSnapshot(acceptedBPM: bpm, patternBPM: 74, cycleBPM: 74).summary(quality: .usable)
            XCTAssertNil(s.estimated_bpm); XCTAssertEqual(s.quality, .unclear)
        }
    }
    func testSummaryContainsNoPrivateOrWatchFields() throws {
        let j = try encoded(ChestBPMCareSnapshot(acceptedBPM: 74).summary(quality: .usable, synthetic: true))
        XCTAssertEqual(Set(j.keys), Set(["schema_version", "measurement", "quality", "estimated_bpm", "synthetic"]))
        XCTAssertEqual(j["synthetic"] as? Bool, true)
    }
    func testNoRequestWithoutConsent() async throws {
        let transport = RecordingTransport(); let client = try CareClient(baseURL: URL(string: "http://127.0.0.1:4318")!, transport: transport)
        do { _ = try await client.send(summary: nil, consent: false); XCTFail("Must require explicit consent") } catch { XCTAssertEqual(error as? CareClientError, .consentRequired) }
        let requests = await transport.requests; XCTAssertTrue(requests.isEmpty)
    }
    func testExplicitSummaryHandoffAndNullClearAreVersionedAndDecodeFallback() async throws {
        let transport = RecordingTransport(); let client = try CareClient(baseURL: URL(string: "http://127.0.0.1:4318")!, token: "synthetic-token", transport: transport)
        let s = ChestBPMCareSnapshot(acceptedBPM: 74).summary(quality: .usable, synthetic: true)
        let reply = try await client.send(summary: s, consent: true); XCTAssertEqual(reply.model.mode, "guided_fallback")
        _ = try await client.send(summary: nil, consent: true, sessionID: reply.session_id)
        let requests = await transport.requests; XCTAssertEqual(requests.count, 2); XCTAssertEqual(requests[0].url?.path, "/api/v1/chat")
        XCTAssertEqual(requests[0].value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-token")
        let body = try JSONSerialization.jsonObject(with: requests[1].httpBody!) as! [String: Any]; XCTAssertTrue(body["scan"] is NSNull)
    }
    func testFullClearUsesDeleteAndDoesNotSendSummary() async throws {
        let transport = RecordingTransport(status: 204); let client = try CareClient(baseURL: URL(string: "http://localhost:4318")!, transport: transport)
        try await client.clear(sessionID: "10000000-0000-4000-8000-000000000001")
        let requests = await transport.requests; XCTAssertEqual(requests[0].httpMethod, "DELETE"); XCTAssertNil(requests[0].httpBody)
    }
    func testInvalidRemoteHTTPAndCredentialURLsAreRejected() {
        for url in ["http://example.com", "https://user:pass@example.com", "https://example.com/?token=private"] { XCTAssertThrowsError(try CareClient(baseURL: URL(string: url)!)) }
    }
    func testHTTPFailureIsNotCountedAsModelSuccess() async throws {
        let client = try CareClient(baseURL: URL(string: "http://localhost:4318")!, transport: RecordingTransport(status: 503))
        do { _ = try await client.send(summary: nil, consent: true); XCTFail("Should reject HTTP failure") } catch { XCTAssertEqual(error as? CareClientError, .http(503)) }
    }
    func testSessionSurvivesScanClearAndFailedDeletionForRetry() async throws {
        let transport = RecordingTransport(deleteFailures: 1)
        let session = CareHandoffSession(client: try CareClient(baseURL: URL(string: "http://localhost:4318")!, transport: transport))
        _ = try await session.send(summary: ChestBPMCareSnapshot(acceptedBPM: 74).summary(quality: .usable, synthetic: true), consent: true)
        let original = await session.sessionID; XCTAssertNotNil(original)
        _ = try await session.clearScan(); let afterScanClear = await session.sessionID; XCTAssertEqual(afterScanClear, original)
        do { try await session.clearAll(); XCTFail("First delete should fail") } catch { XCTAssertEqual(error as? CareClientError, .http(503)) }
        let retained = await session.sessionID; XCTAssertEqual(retained, original)
        try await session.clearAll(); let deleted = await session.sessionID; XCTAssertNil(deleted)
        let requests = await transport.requests; XCTAssertEqual(requests.count, 4); XCTAssertEqual(requests[2].httpMethod, "DELETE"); XCTAssertEqual(requests[3].url, requests[2].url)
    }
}
