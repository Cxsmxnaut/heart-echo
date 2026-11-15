import Foundation

@main struct MurmurChecks {
    static func main() throws {
        var failures = 0
        func check(_ ok: Bool, _ message: String) { print("\(ok ? "PASS" : "FAIL"): \(message)"); if !ok { failures += 1 } }
        check(MurmurRules.finding([0.8, 0.1, 0.1]) == .absent, "Strong absent label is recording-specific")
        check(MurmurRules.finding([0.1, 0.8, 0.1]) == .present, "Strong present label is murmur-like")
        check(MurmurRules.finding([0.4, 0.4, 0.2]) == .unsure, "Low confidence remains unsure")
        check(MurmurRules.finding([0.1, 0.1, 0.8]) == .unsure, "Unknown annotation is not normal")
        check(MurmurRules.finding([.nan, 0, 1]) == .unsure, "Nonfinite probabilities fail closed")
        check(MurmurRules.finding([1, 1, 0]) == .unsure, "Invalid probability total fails closed")
        check(MurmurRules.starts(7999).isEmpty, "Incomplete four-second input has no window")
        check(MurmurRules.starts(40000) == [0, 8000, 16000, 24000, 32000], "Twenty seconds has five full windows")
        check(MurmurRules.starts(16019) == [0, 8000], "Final partial frame never exceeds audio")
        check(!MurmurRules.usable(Array(repeating: 0, count: 8000)), "Silence cannot receive an absent result")
        check(!MurmurRules.usable(Array(repeating: 1, count: 8000)), "Clipped audio cannot receive a result")
        if CommandLine.arguments.count > 1 {
            let model = try MurmurAnalyzer(directory: URL(fileURLWithPath: CommandLine.arguments[1]))
            let silent = try model.analyze(Array(repeating: 0, count: 40000))
            check(silent.finding == .unsure && silent.windows == 0, "Full native silence path remains unsure")
            let short = try model.analyze(Array(repeating: 0.03, count: 7999))
            check(short.finding == .unsure && short.windows == 0, "Short native input remains unsure")
        }
        print("\(failures) failure(s). Engineering checks, not clinical validation.")
        if failures > 0 { exit(1) }
    }
}
