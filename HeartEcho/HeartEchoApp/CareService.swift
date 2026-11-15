import Foundation
import Combine
import Security

struct CareSummary: Codable {
    let schema_version = "1.2"
    let measurement = "experimental_heart_sound_timing"
    let quality: String
    let estimated_bpm: Double?
    let analyzed_at: String
    let synthetic = false
    let recording_source: String
    let recording_seconds: Double
    let murmur: Finding?
    struct Finding: Codable { let finding: String; let model_revision: String }
    init(_ record: HeartRecording) {
        let bpm = record.bpm.flatMap { $0.isFinite && (20...300).contains($0) ? $0 : nil }
        quality = bpm == nil ? "unavailable" : "usable"; estimated_bpm = bpm
        analyzed_at = ISO8601DateFormatter().string(from: record.created)
        recording_source = record.publicSample != nil ? "public_example" : record.source == "iPhone microphone" ? "microphone" : "import"
        recording_seconds = record.seconds
        murmur = record.effectiveMurmurFinding.map { Finding(finding: $0.rawValue, model_revision: record.modelRevision) }
    }
    enum CodingKeys: String, CodingKey { case schema_version, measurement, quality, estimated_bpm, analyzed_at, synthetic, recording_source, recording_seconds, murmur }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(schema_version, forKey: .schema_version); try c.encode(measurement, forKey: .measurement)
        try c.encode(quality, forKey: .quality); try c.encode(estimated_bpm, forKey: .estimated_bpm)
        try c.encode(analyzed_at, forKey: .analyzed_at); try c.encode(synthetic, forKey: .synthetic)
        try c.encode(recording_source, forKey: .recording_source); try c.encode(recording_seconds, forKey: .recording_seconds)
        try c.encodeIfPresent(murmur, forKey: .murmur)
    }
}

struct CareListing: Decodable, Identifiable {
    let name: String
    let address: String?
    let specialty: String?
    let phone: String?
    let source: String?
    let source_url: String?
    let website: String?
    let directions_url: String?
    let reason: String?
    let retrieved_at: String?
    var id: String { (source_url ?? "") + name + (address ?? "") }
    static func safeWebURL(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value), ["https", "http"].contains(url.scheme?.lowercased()), url.host != nil, url.user == nil, url.password == nil else { return nil }
        return url
    }
    var phoneURL: URL? {
        guard let phone else { return nil }; let digits = phone.filter { $0.isASCII && ($0.isNumber || $0 == "+") }
        return digits.isEmpty ? nil : URL(string: "tel:" + digits)
    }
}
struct CareResponse: Decodable {
    let session_id: String
    let message: String
    let scan_explanation: String
    let model: ModelStatus
    let results: [String: Directory]
    struct ModelStatus: Decodable { let mode: String; let used_this_turn: Bool?; let provider: String? }
    struct Directory: Decodable { let status: String; let items: [CareListing]?; let providers: [CareListing]?; let fallbacks: [Fallback]? }
    struct Fallback: Decodable { let label: String; let url: String }
}

enum CareNetworkError: LocalizedError {
    case endpoint, consent, http(Int), response
    var errorDescription: String? {
        switch self {
        case .endpoint: return "Choose an HTTPS service, or a local address on your trusted Wi-Fi."
        case .consent: return "Review and allow sending this summary first."
        case .http(401): return "Pair with the care service again. The code may have changed after a restart."
        case .http(410): return "This chat expired. Send again to start a new chat."
        case .http(429): return "Please wait a minute before trying again."
        case .http: return "The care service could not complete this request. Try again."
        case .response: return "The care service returned an unreadable response."
        }
    }
}

struct CareChatMessage: Identifiable {
    let id = UUID()
    let text: String
    let isUser: Bool
}

@MainActor final class CareService: NSObject, ObservableObject, NetServiceBrowserDelegate, NetServiceDelegate {
    @Published var endpoint = UserDefaults.standard.string(forKey: "careEndpoint") ?? "http://127.0.0.1:4318"
    @Published var busy = false
    @Published var error: String?
    @Published var reply: CareResponse?
    @Published var connected = false
    @Published private(set) var hasSavedPairing = false
    @Published private(set) var modelProvider = UserDefaults.standard.string(forKey: "careModelProvider") ?? "local"
    @Published var connectionNote: String?
    @Published var discovered: String?
    @Published private(set) var chatMessages: [CareChatMessage] = []
    @Published private(set) var chatRecording: HeartRecording?
    @Published var chatShareSummary = false
    private var token: String = ""
    private var sessionID: String?
    private var sessionEndpoint: URL?
    private var generation = UUID()
    private let browser = NetServiceBrowser()
    private var services: [NetService] = []
    private let credential: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "app.veritas.heartecho.care", kSecAttrAccount as String: "demo"]
    override init() {
        super.init()
        #if DEBUG && targetEnvironment(simulator)
        if ProcessInfo.processInfo.arguments.contains("--ui-reset-care") {
            SecItemDelete(credential as CFDictionary)
            UserDefaults.standard.removeObject(forKey: "careEndpoint")
            UserDefaults.standard.removeObject(forKey: "careModelProvider")
            modelProvider = "local"
            endpoint = "http://127.0.0.1:4318"
        }
        #endif
        var query = credential; query[kSecReturnData as String] = true
        var item: CFTypeRef?
        if SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data { token = String(data: data, encoding: .utf8) ?? "" }
        hasSavedPairing = !token.isEmpty
        browser.delegate = self
    }
    var canAttemptChat: Bool { connected || hasSavedPairing }

    func prepareChat(for recording: HeartRecording?) async {
        guard let recording, chatRecording?.id != recording.id else { return }
        guard !busy else { error = "Wait for the current message before opening another recording."; return }
        busy = true; error = nil; defer { busy = false }
        do {
            // A different result starts a new session so an earlier result cannot
            // leak into this conversation. The same Care chat is used everywhere.
            try await clearSession()
            chatMessages.removeAll(); reply = nil; chatShareSummary = false; chatRecording = recording
        } catch {
            self.error = "The previous conversation could not be cleared. Reconnect and try again."
        }
    }
    func appendChatMessage(_ text: String, isUser: Bool) {
        chatMessages.append(CareChatMessage(text: text, isUser: isUser))
    }
    func forgetDeletedRecording(_ id: UUID) async {
        guard chatRecording?.id == id else { return }
        chatRecording = nil; chatShareSummary = false; chatMessages.removeAll(); reply = nil
        do { try await clearSession() }
        catch {
            // Never reuse the deleted result in a later chat if the service is offline.
            generation = UUID(); sessionID = nil; sessionEndpoint = nil
            self.error = "The old care conversation could not be cleared from the service. It will expire automatically."
        }
    }
    static func validatedEndpoint(_ value: String) throws -> URL {
        guard let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)), let host = url.host?.lowercased(), url.user == nil, url.password == nil, url.query == nil, url.fragment == nil, url.path.isEmpty || url.path == "/" else { throw CareNetworkError.endpoint }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        let localIP = host.split(separator: ".").count == 4 && parts.count == 4 && parts.allSatisfy { (0...255).contains($0) } && (parts[0] == 10 || parts[0] == 192 && parts[1] == 168 || parts[0] == 172 && (16...31).contains(parts[1]))
        guard url.scheme == "https" || url.scheme == "http" && (["localhost", "127.0.0.1", "::1"].contains(host) || host.hasSuffix(".local") || localIP) else { throw CareNetworkError.endpoint }
        return url
    }
    func discover() { services = []; browser.stop(); browser.searchForServices(ofType: "_heartecho._tcp.", inDomain: "local.") }
    nonisolated func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        Task { @MainActor in self.services.append(service); service.delegate = self; service.resolve(withTimeout: 5) }
    }
    nonisolated func netServiceDidResolveAddress(_ sender: NetService) {
        Task { @MainActor in
            if let host = sender.hostName, sender.port > 0 { self.discovered = "http://\(host.trimmingCharacters(in: CharacterSet(charactersIn: "."))):\(sender.port)" }
        }
    }
    private func request(_ base: URL, path: String, body: Data? = nil, method: String = "POST", authenticated: Bool = true) async throws -> Data {
        var r = URLRequest(url: base.appendingPathComponent(path)); r.httpMethod = method; r.timeoutInterval = 150
        r.setValue("application/json", forHTTPHeaderField: "Content-Type"); r.httpBody = body
        if authenticated && !token.isEmpty { r.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        let (data, response) = try await URLSession.shared.data(for: r)
        guard let response = response as? HTTPURLResponse else { throw CareNetworkError.response }
        guard (200...299).contains(response.statusCode) else { throw CareNetworkError.http(response.statusCode) }
        return data
    }
    func pair(code: String) async {
        guard !busy else { return }; busy = true; error = nil; defer { busy = false }
        do {
            let base = try Self.validatedEndpoint(endpoint)
            let data = try await request(base, path: "api/pair", body: JSONEncoder().encode(["code": code]), authenticated: false)
            struct Paired: Decodable { let token: String; let model_provider: String? }
            let pairing = try JSONDecoder().decode(Paired.self, from: data)
            let newToken = pairing.token
            // An existing conversation belongs to its original service.
            var oldSessionUnavailable = false
            do { try await clearSession() }
            catch CareNetworkError.http(let code) where code == 401 || code == 410 {
                generation = UUID(); sessionID = nil; sessionEndpoint = nil; reply = nil
                oldSessionUnavailable = true
            }
            var entry = credential; entry[kSecValueData as String] = Data(newToken.utf8); entry[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemDelete(credential as CFDictionary)
            let status = SecItemAdd(entry as CFDictionary, nil)
            connectionNote = oldSessionUnavailable ? "Paired. The previous conversation could not be cleared and may remain until it expires." : status == errSecSuccess ? "Pairing saved securely in Keychain." : "Paired for this launch only. Secure storage is unavailable; reconnect after closing the app."
            modelProvider = pairing.model_provider ?? "local"
            UserDefaults.standard.set(modelProvider, forKey: "careModelProvider")
            if modelProvider == "gemini" { chatShareSummary = false }
            token = newToken; UserDefaults.standard.set(endpoint, forKey: "careEndpoint"); hasSavedPairing = true; connected = true
        } catch { self.error = error.localizedDescription }
    }
    func send(message: String = "", action: String = "message", zip: String? = nil, specialty: String = "family_medicine", record: HeartRecording? = nil, consent: Bool = false) async -> CareResponse? {
        guard !busy else { return nil }; busy = true; error = nil; reply = nil; defer { busy = false }
        do {
            let base = try Self.validatedEndpoint(endpoint)
            if !token.isEmpty && endpoint != UserDefaults.standard.string(forKey: "careEndpoint") { throw CareNetworkError.http(401) }
            if sessionID != nil && sessionEndpoint != base { try await clearSession() }
            if record != nil && !consent { throw CareNetworkError.consent }
            struct Profile: Encodable { let zip: String; let specialty: String; let coverage_preference = "skip" }
            struct Body: Encodable {
                let session_id: String?; let message: String; let action: String; let profile: Profile?; let scan: CareSummary?
                enum CodingKeys: String, CodingKey { case session_id, message, action, profile, scan }
                func encode(to encoder: Encoder) throws {
                    var c = encoder.container(keyedBy: CodingKeys.self); try c.encodeIfPresent(session_id, forKey: .session_id)
                    try c.encode(message, forKey: .message); try c.encode(action, forKey: .action); try c.encodeIfPresent(profile, forKey: .profile)
                    // Explicit null clears a previously attached recording when searching without one.
                    try c.encode(scan, forKey: .scan)
                }
            }
            let turn = generation
            let body = Body(session_id: sessionID, message: message, action: action, profile: zip.map { Profile(zip: $0, specialty: specialty) }, scan: modelProvider == "gemini" ? nil : record.map(CareSummary.init))
            let data = try await request(base, path: "api/v1/chat", body: JSONEncoder().encode(body))
            let result = try JSONDecoder().decode(CareResponse.self, from: data)
            guard turn == generation else { return nil }
            if let provider = result.model.provider { modelProvider = provider; UserDefaults.standard.set(provider, forKey: "careModelProvider"); if provider == "gemini" { chatShareSummary = false } }
            sessionID = result.session_id; sessionEndpoint = base; reply = result; connected = true; return result
        } catch {
            if case CareNetworkError.http(410) = error { sessionID = nil; sessionEndpoint = nil }
            if case CareNetworkError.http(401) = error { connected = false; hasSavedPairing = false }
            self.error = error.localizedDescription; return nil
        }
    }
    func clearSession() async throws {
        guard !busy || sessionID != nil else { return }
        if let id = sessionID, let base = sessionEndpoint { _ = try await request(base, path: "api/session/" + id, method: "DELETE") }
        generation = UUID(); sessionID = nil; sessionEndpoint = nil; reply = nil
    }
    func clear() async {
        guard !busy else { return }; error = nil
        do {
            try await clearSession()
            chatMessages.removeAll(); chatShareSummary = false
        } catch { self.error = "The conversation could not be deleted. Try clearing it again. " + error.localizedDescription }
    }
    func search(zip: String, specialty: String, affordable: Bool, record: HeartRecording?, consent: Bool) async {
        guard !busy else { return }
        guard NativeCareDirectory.validZIP(zip) else { error = "Enter a five-digit US ZIP code."; return }
        if connected {
            let result = await send(action: affordable ? "affordable" : "search", zip: zip, specialty: specialty, record: record, consent: consent)
            if result != nil { return }
            connectionNote = "The care assistant is unavailable. Care search is using public directories directly."
        }
        await searchDirect(zip: zip, specialty: specialty, affordable: affordable)
    }
    func searchDirect(zip: String, specialty: String, affordable: Bool) async {
        guard !busy else { return }
        guard NativeCareDirectory.validZIP(zip) else { error = "Enter a five-digit US ZIP code."; return }
        busy = true; error = nil; reply = nil
        reply = await NativeCareDirectory().search(zip: zip, specialty: specialty, affordable: affordable)
        busy = false
    }
}
