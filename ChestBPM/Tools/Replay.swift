import Foundation

// Only microphone features enter estimation. Watch references stay in the Python evaluator.
private struct Frame: Decodable {
    let sequence: Int
    let time, elapsed, seconds, level, clipping, score: Double
    let envelope, brightness: [Double]
    let original, cycle, previous: Double?
    let legacyCapture: Bool
}
private struct Result: Encodable {
    let sequence: Int
    let time, elapsed, seconds: Double
    let previous, candidate: Double?
    let source: String
}

@main struct Replay {
    static func main() throws {
        let frames = try JSONDecoder().decode([Frame].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        var full = Periodicity(), recent = RecentCounter(), results: [Result] = []
        func equal(_ a: Double?, _ b: Double?) -> Bool {
            a == nil && b == nil || a != nil && b != nil && abs(a! - b!) < 1e-9
        }
        for f in frames {
            let (bpm, score) = full.estimate(f.envelope), cycle = cycleEstimate(f.envelope, brightness: f.brightness)
            let rejected = f.seconds < 6 || f.clipping > 0.01 || f.level < -85
            let previous = rejected ? nil : agreement(bpm, cycle.bpm)
            guard equal(f.original, f.clipping > 0.01 ? nil : bpm), equal(f.cycle, cycle.bpm), abs(f.score - score) < 1e-9,
                  !f.legacyCapture || equal(f.previous, previous) else {
                throw NSError(domain: "Replay", code: 1, userInfo: [NSLocalizedDescriptionKey: "Old calculation did not reproduce at event \(f.sequence); do not trust this replay."])
            }
            let d = recent.estimate(f.envelope, brightness: f.brightness)
            let selected = selectPattern(bpm, cycle.bpm, recent: d)
            results.append(Result(sequence: f.sequence, time: f.time, elapsed: f.elapsed, seconds: f.seconds,
                previous: previous, candidate: rejected ? nil : selected.bpm, source: rejected ? "none" : selected.source))
        }
        FileHandle.standardOutput.write(try JSONEncoder().encode(results))
    }
}
