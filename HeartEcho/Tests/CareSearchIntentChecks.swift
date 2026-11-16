import Foundation

@main
struct CareSearchIntentChecks {
    static func main() {
        var failures = 0
        func check(_ condition: Bool, _ name: String) {
            print("\(condition ? "PASS" : "FAIL"): \(name)")
            if !condition { failures += 1 }
        }
        let primary = CareSearchIntent(zip: "10001", specialty: "family_medicine", affordable: false)
        check(CareSearchIntent.parse("10001") == primary, "ZIP alone starts a primary-care directory request")
        check(CareSearchIntent.parse(" \n10001\t ") == primary, "ZIP-only quick start trims whitespace")
        check(CareSearchIntent.parse("Find care in 10001") == primary, "Explicit care search still works")
        check(CareSearchIntent.parse("Find healthcare in 10001") == primary, "Healthcare search remains an explicit care request")
        check(CareSearchIntent.parse("Doctor in ZIP: 10001") == primary, "Explicit doctor search preserves ZIP parsing")
        check(CareSearchIntent.parse("Find a cardiologist doctor in 10001")?.specialty == "cardiology", "Explicit cardiology request is preserved")
        check(CareSearchIntent.parse("Find care in 10001, not cardiology")?.specialty == "family_medicine", "Negated cardiology stays primary care")
        check(CareSearchIntent.parse("No cardiologist, find a provider in 10001")?.specialty == "family_medicine", "A declined cardiologist does not become the specialty")
        check(CareSearchIntent.parse("I don’t want cardiology; find care in 10001")?.specialty == "family_medicine", "Curly-apostrophe cardiology negation is preserved")
        for phrase in ["no cardiology", "do not want cardiology", "avoid cardiology", "without cardiology", "not a cardiologist", "no need for a cardiologist", "not looking for cardiology", "not interested in cardiology"] {
            check(CareSearchIntent.parse("Find care in 10001. " + phrase)?.specialty == "family_medicine", "Direct specialty refusal stays primary care: \(phrase)")
        }
        for text in [
            "No insurance. Find a cardiology provider in 10001",
            "I don't have insurance. Find a cardiology provider in 10001",
            "Not sure about cost. Find a cardiology provider in 10001",
            "No appointment yet. Find a cardiology doctor in 10001",
            "I am not a smoker. Find a cardiology provider in 10001",
            "Find a cardiology provider in 10001 without insurance"
        ] {
            check(CareSearchIntent.parse(text)?.specialty == "cardiology", "Unrelated negation does not suppress cardiology: \(text)")
        }
        check(CareSearchIntent.parse("Affordable clinics in 10001")?.affordable == true, "Affordable clinic request is preserved")
        check(CareSearchIntent.parse("Community health care in 10001")?.affordable == true, "Community health request is preserved")
        check(CareSearchIntent.parse("Find low-cost providers in 10001")?.affordable == true, "Cost preference is preserved")
        for text in ["", "1000", "100001", "１０００１", "９10001", "10001-1234", "My invoice is 10001", "Be careful with invoice 10001", "My number is 10001"] {
            check(CareSearchIntent.parse(text) == nil, "Unrelated or invalid ZIP message stays out of directory search: \(text.debugDescription)")
        }
        for text in ["Find care in 100001", "Find care in １０００１", "Find care in ９10001", "Find care in abc10001xyz"] {
            check(CareSearchIntent.parse(text) == nil, "Malformed embedded ZIP is rejected: \(text)")
        }
        exit(failures == 0 ? 0 : 1)
    }
}
