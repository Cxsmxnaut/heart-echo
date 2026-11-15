import Foundation

/// Explains deterministic input checks. This cannot establish murmur audibility.
struct AudioAssessment: Codable {
    let issue: String?
    let detail: String
    static func inspect(_ samples: [Float]) -> AudioAssessment {
        if samples.count < MurmurRules.size { return .init(issue: "too_short", detail: "Less than four seconds of audio could be analyzed. Record the full 20 seconds or import a longer file.") }
        if !samples.allSatisfy(\.isFinite) { return .init(issue: "invalid_audio", detail: "The recording contains invalid audio values. Try recording again or choose another file.") }
        let windows = MurmurRules.starts(samples.count).map { Array(samples[$0..<$0 + MurmurRules.size]) }
        if windows.allSatisfy({ x in sqrt(x.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(x.count)) < 0.00002 }) {
            return .init(issue: "too_quiet", detail: "The audio is silent or too quiet for this model. Check microphone permission, keep its opening uncovered and try a quiet room.")
        }
        if windows.allSatisfy({ x in Double(x.filter { abs($0) >= 0.999 }.count) / Double(x.count) > 0.01 }) {
            return .init(issue: "clipped", detail: "The audio is distorted by clipping. Avoid rubbing or pressing on the microphone and try again.")
        }
        if !windows.contains(where: MurmurRules.usable) { return .init(issue: "unusable", detail: "No four-second window passed the model's basic volume and distortion checks. Keep the phone steady and try again in a quiet room.") }
        return .init(issue: nil, detail: "Audio passed basic length, volume and distortion checks. This does not prove a subtle murmur is audible. An unsure prediction can still occur.")
    }
}
