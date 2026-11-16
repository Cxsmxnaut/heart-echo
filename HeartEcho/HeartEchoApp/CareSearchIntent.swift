import Foundation

/// A local directory request, including the ZIP-only quick start shown in Care.
/// Apart from a standalone ZIP, a message needs an explicit care keyword.
struct CareSearchIntent: Equatable {
    let zip: String
    let specialty: String
    let affordable: Bool

    static func parse(_ message: String) -> CareSearchIntent? {
        let text = message.trimmingCharacters(in: .whitespacesAndNewlines)
        let query = text.lowercased()
        let standaloneZIP = text.count == 5 && text.allSatisfy { $0.isASCII && $0.isNumber }
        let requestsCare = query.range(
            of: "\\b(care|healthcare|clinics?|doctors?|providers?)\\b",
            options: .regularExpression
        ) != nil
        guard standaloneZIP || requestsCare,
              let zip = text.range(
                of: "(?<![\\p{L}\\p{N}])[0-9]{5}(?![\\p{L}\\p{N}])",
                options: .regularExpression
              ) else { return nil }
        // A refusal must name the specialty directly. Unrelated phrases such
        // as "no insurance" or "not sure about cost" must not change it.
        let declinesCardiology = query.range(
            of: #"\b(?:no(?:\s+need\s+for)?|not(?:\s+(?:looking\s+for|interested\s+in|want|need))?|(?:do\s+not|don['’]t)\s+(?:want|need|prefer|request)|avoid|without)\s+(?:(?:a|an|any|the)\s+)?cardiolog(?:y|ists?)\b"#,
            options: .regularExpression
        ) != nil
        return CareSearchIntent(
            zip: String(text[zip]),
            specialty: query.contains("cardiolog") && !declinesCardiology ? "cardiology" : "family_medicine",
            affordable: query.contains("affordable") || query.contains("cost") || query.contains("community health")
        )
    }
}
