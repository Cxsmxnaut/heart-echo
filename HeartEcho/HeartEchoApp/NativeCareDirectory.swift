import Foundation

/// Public, read-only directory searches work without pairing a Mac or sharing a scan.
struct NativeCareDirectory {
    static let hrsa = "https://gisportal.hrsa.gov/server/rest/services/HealthCareFacilities/PrimaryHealthCareFacilities_FS/MapServer/0"
    let session: URLSession
    init(session: URLSession = .shared) { self.session = session }
    static func validZIP(_ zip: String) -> Bool { zip.count == 5 && zip.allSatisfy { $0.isASCII && $0.isNumber } }
    static let taxonomy = ["family_medicine": "Family Medicine", "internal_medicine": "Internal Medicine", "cardiology": "Cardiovascular Disease"]
    static func query(_ base: String, _ values: [String: String]) -> URL {
        var parts = URLComponents(string: base)!
        parts.queryItems = values.sorted(by: { $0.key < $1.key }).map { URLQueryItem(name: $0.key, value: $0.value) }
        return parts.url!
    }
    static func text(_ value: Any?) -> String? {
        guard let value = value as? String else { return nil }
        let clean = String(value.trimmingCharacters(in: .whitespacesAndNewlines).prefix(300))
        return clean.isEmpty ? nil : clean
    }
    static func address(_ parts: [Any?]) -> String { parts.compactMap(text).joined(separator: ", ") }
    static func providers(_ data: [String: Any], zip: String, specialty: String, now: String) -> [CareListing] {
        let category = taxonomy[specialty] ?? taxonomy["family_medicine"]!
        return ((data["results"] as? [[String: Any]]) ?? []).compactMap { p -> CareListing? in
            guard let basic = p["basic"] as? [String: Any], basic["status"] as? String == "A",
                  let number = p["number"] as? NSNumber, String(describing: number).count == 10,
                  let places = p["addresses"] as? [[String: Any]],
                  let place = places.first(where: { $0["address_purpose"] as? String == "LOCATION" && $0["country_code"] as? String == "US" && String(($0["postal_code"] as? String ?? "").prefix(5)) == zip }),
                  text(place["address_1"]) != nil,
                  let taxonomies = p["taxonomies"] as? [[String: Any]], taxonomies.contains(where: { text($0["desc"])?.caseInsensitiveCompare(category) == .orderedSame }) else { return nil }
            let person = address([basic["first_name"], basic["middle_name"], basic["last_name"], basic["credential"]]).replacingOccurrences(of: ", ", with: " ")
            guard let name = text(basic["organization_name"]) ?? text(person) else { return nil }
            return CareListing(name: name, address: address([place["address_1"], place["address_2"], place["city"], place["state"], place["postal_code"]]), specialty: category, phone: text(place["telephone_number"]), source: "CMS NPPES", source_url: "https://npiregistry.cms.hhs.gov/provider-view/\(number)", website: nil, directions_url: nil, reason: "Active directory entry and practice address in ZIP \(zip). Insurance, availability and cost are unverified.", retrieved_at: now)
        }.prefix(5).map { $0 }
    }
    static func clinics(_ data: [String: Any], zip: String, now: String) -> [CareListing] {
        ((data["features"] as? [[String: Any]]) ?? []).compactMap { f -> CareListing? in
            guard let a = f["attributes"] as? [String: Any], a["HCC_STATUS_DESC"] as? String == "Active",
                  String((a["SITE_ZIP_CD"] as? String ?? "").prefix(5)) == zip,
                  let name = text(a["SITE_NM"]), text(a["SITE_ADDRESS"]) != nil,
                  name.range(of: #"(?i)\bdent(?:al|istry|ists?)\b"#, options: .regularExpression) == nil,
                  let number = a["OBJECTID"] as? NSNumber, number.doubleValue.rounded() == number.doubleValue else { return nil }
            return CareListing(name: name, address: address([a["SITE_ADDRESS"], a["SITE_CITY"], a["SITE_STATE_ABBR"], a["SITE_ZIP_CD"]]), specialty: "Health center site · confirm services", phone: text(a["SITE_PHONE_NUM"]), source: "HRSA Health Center Sites", source_url: "\(hrsa)/\(number)?f=pjson", website: CareListing.safeWebURL(text(a["SITE_URL"]))?.absoluteString, directions_url: nil, reason: "Active HRSA-listed site in ZIP \(zip). Ask about services and eligibility for sliding fees; no price is guaranteed.", retrieved_at: now)
        }.prefix(5).map { $0 }
    }
    private func json(_ url: URL) async throws -> [String: Any] {
        var request = URLRequest(url: url); request.timeoutInterval = 15; request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, response.statusCode == 200, data.count <= 2_000_000,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any], object["error"] == nil, object["Errors"] == nil else { throw CareNetworkError.response }
        return object
    }
    private func group(zip: String, specialty: String, clinics: Bool) async -> CareResponse.Directory {
        let fallback = CareResponse.Fallback(label: clinics ? "HRSA: Find a Health Center" : "NPI Registry", url: clinics ? "https://findahealthcenter.hrsa.gov/" : "https://npiregistry.cms.hhs.gov/")
        let url = clinics ? Self.query(Self.hrsa + "/query", ["f": "json", "where": "SITE_ZIP_CD LIKE '\(zip)%' AND HCC_STATUS_DESC = 'Active'", "outFields": "OBJECTID,SITE_NM,SITE_ADDRESS,SITE_CITY,SITE_STATE_ABBR,SITE_ZIP_CD,SITE_PHONE_NUM,SITE_URL,HCC_STATUS_DESC", "returnGeometry": "false", "resultRecordCount": "20", "orderByFields": "SITE_NM"]) : Self.query("https://npiregistry.cms.hhs.gov/api/", ["version": "2.1", "postal_code": zip, "address_purpose": "LOCATION", "taxonomy_description": Self.taxonomy[specialty] ?? "Family Medicine", "limit": "5"])
        do {
            let value = try await json(url)
            guard clinics ? value["features"] is [[String: Any]] : value["results"] is [[String: Any]] || (value["result_count"] as? Int == 0) else { throw CareNetworkError.response }
            let now = ISO8601DateFormatter().string(from: Date())
            let items = clinics ? Self.clinics(value, zip: zip, now: now) : Self.providers(value, zip: zip, specialty: specialty, now: now)
            return .init(status: items.isEmpty ? "empty" : "ok", items: items, providers: nil, fallbacks: [fallback])
        } catch { return .init(status: "error", items: [], providers: nil, fallbacks: [fallback]) }
    }
    func search(zip: String, specialty: String, affordable: Bool) async -> CareResponse {
        var results: [String: CareResponse.Directory] = [:]
        if affordable { results["search_affordable_clinics"] = await group(zip: zip, specialty: specialty, clinics: true) }
        else {
            async let providers = group(zip: zip, specialty: specialty, clinics: false)
            async let clinics = group(zip: zip, specialty: specialty, clinics: true)
            results = await ["search_providers": providers, "search_affordable_clinics": clinics]
        }
        let count = results.values.reduce(0) { $0 + ($1.items?.count ?? 0) }
        var message = count > 0 ? "\(count) public directory listings in ZIP \(zip)." : "No listings returned for this exact ZIP. Try a nearby ZIP or an official directory."
        if results.values.contains(where: { $0.status == "error" }) { message += " One source is unavailable; that does not mean no care exists." }
        return .init(session_id: UUID().uuidString, message: message, scan_explanation: "No recording summary was sent. Care search works with any result or without a scan.", model: .init(mode: "native_directories", used_this_turn: false, provider: nil), results: results)
    }
}
