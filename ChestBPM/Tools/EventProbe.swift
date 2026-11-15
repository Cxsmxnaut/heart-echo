import Foundation
import AVFoundation
import Darwin

private struct Request: Decodable { let id, path, output: String }
private struct SoundEvent: Encodable {
    let kind: String
    let time, start, end, confidence, meanConfidence: Double
    let firstFrame, lastFrame: Int
    let acousticValid, complete, qualified: Bool
}
private struct ProbeResult: Encodable {
    let id: String
    let seconds, coverageStart, coverageEnd: Double
    let events: [SoundEvent]
    let maskedRanges: [[Double]]
}

// Research probe: export sound events before any BPM, interval-regularity or
// disease decision. No ECG, Watch values, diagnoses or expected rate are inputs.
@main struct EventProbe {
    static func main() throws {
        umask(0o077)
        let requests = try JSONDecoder().decode([Request].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        let models = try DeviceSoundModels(directory: URL(fileURLWithPath: CommandLine.arguments[2]))
        let encoder = JSONEncoder()
        for request in requests {
            let file = try AVAudioFile(forReading: URL(fileURLWithPath: request.path))
            guard let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)) else { throw CocoaError(.fileReadCorruptFile) }
            try file.read(into: buffer)
            guard let channel = buffer.floatChannelData?[0] else { throw CocoaError(.fileReadCorruptFile) }
            let samples = Array(UnsafeBufferPointer(start: channel, count: Int(buffer.frameLength)))
            let rate = file.processingFormat.sampleRate, delay = HeartResampler(rate: rate).delay + 0.025
            let pipeline = HeartSoundPipeline(rate: rate, models: models)
            var states: [StateFrame] = [], valid: [Int: Bool] = [:], last = -1
            for start in stride(from: 0, to: samples.count, by: max(1, Int(rate / 2))) {
                let end = min(samples.count, start + Int(rate / 2))
                pipeline.append(Array(samples[start..<end]))
                let snapshot = pipeline.replayInput()
                for frame in snapshot.raw { valid[frame.index] = (valid[frame.index] ?? true) && frame.valid }
                for frame in snapshot.states where frame.index > last { states.append(frame); last = frame.index }
            }
            var events: [SoundEvent] = [], active: [StateFrame] = [], kind = 0
            func timestamp(_ index: Double) -> Double { (index + 1) / 100 - delay }
            func finish(edge: Bool) {
                guard let first = active.first, let last = active.last, kind != 0 else { active = []; return }
                let probabilities = active.map { $0.probabilities[kind] }, weight = probabilities.reduce(0, +)
                let center = zip(active, probabilities).reduce(0) { $0 + Double($1.0.index) * $1.1 } / max(weight, 1e-15)
                let clean = (first.index...last.index).allSatisfy { valid[$0] == true }
                let complete = !edge && first.index != states.first?.index
                events.append(SoundEvent(kind: kind == 1 ? "S1" : "S2", time: timestamp(center),
                    start: timestamp(Double(first.index)) - 0.005, end: timestamp(Double(last.index)) + 0.005,
                    confidence: probabilities.max() ?? 0, meanConfidence: weight / Double(active.count),
                    firstFrame: first.index, lastFrame: last.index, acousticValid: clean, complete: complete,
                    qualified: clean && complete && (2...25).contains(active.count)))
                active = []
            }
            for frame in states {
                let p = frame.probabilities, maximum = p.max() ?? 0
                let next = p[1] >= 0.5 && p[1] == maximum ? 1 : p[3] >= 0.5 && p[3] == maximum ? 3 : 0
                let gap = active.last.map { frame.index != $0.index + 1 } ?? false
                if next != kind || gap { finish(edge: gap); kind = next }
                if next != 0 { active.append(frame) }
            }
            finish(edge: true)
            var maskedRanges: [[Double]] = [], maskStart: Int?
            if let end = valid.keys.max() {
                for index in 0...end + 1 {
                    if index <= end && valid[index] != true { if maskStart == nil { maskStart = index } }
                    else if let start = maskStart {
                        maskedRanges.append([timestamp(Double(start)) - 0.005, timestamp(Double(index - 1)) + 0.005]); maskStart = nil
                    }
                }
            }
            let result = ProbeResult(id: request.id, seconds: Double(samples.count) / rate,
                coverageStart: states.first.map { timestamp(Double($0.index)) } ?? 0,
                coverageEnd: states.last.map { timestamp(Double($0.index)) } ?? 0, events: events, maskedRanges: maskedRanges)
            try encoder.encode(result).write(to: URL(fileURLWithPath: request.output), options: .atomic)
            print("Exported \(request.id): \(events.count) typed sound events; no rhythm regularity filter")
        }
    }
}
