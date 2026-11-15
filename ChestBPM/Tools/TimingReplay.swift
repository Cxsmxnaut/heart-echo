import Foundation
import Darwin

private struct Update: Codable { let sequence, samples: Int; let time, elapsed, motion: Double }
private struct Frame: Decodable { let update: Update; let input: TimingReplayInput }
private struct Result: Encodable { let update: Update; let estimate, recent, events: RobustDiagnostics }

@main struct TimingReplay {
    static func main() throws {
        umask(0o077)
        for path in CommandLine.arguments.dropFirst() {
            let text = try String(contentsOfFile: path, encoding: .utf8)
            var timing = AdaptiveNeuralTiming()
            var recent = NeuralTiming(windowFrames: 400)
            var events = EventTiming()
            let encoder = JSONEncoder(), decoder = JSONDecoder()
            let output = path.replacingOccurrences(of: ".ndjson", with: ".candidate.ndjson")
            FileManager.default.createFile(atPath: output, contents: nil)
            let stream = try FileHandle(forWritingTo: URL(fileURLWithPath: output))
            for line in text.split(separator: "\n") {
                let frame = try decoder.decode(Frame.self, from: Data(line.utf8))
                var result = timing.estimate(states: frame.input.states, raw: frame.input.frames)
                var short = recent.estimate(states: frame.input.states, raw: frame.input.frames)
                var acoustic = events.estimate(states: frame.input.states, raw: frame.input.frames)
                result.envelope = nil; result.stateProbabilities = nil
                short.envelope = nil; short.stateProbabilities = nil
                acoustic.envelope = nil; acoustic.stateProbabilities = nil
                var data = try encoder.encode(Result(update: frame.update, estimate: result, recent: short, events: acoustic)); data.append(10)
                try stream.write(contentsOf: data)
            }
            try stream.close(); print(output)
        }
    }
}
