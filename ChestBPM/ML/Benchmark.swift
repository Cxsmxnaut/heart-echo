import Foundation
import AVFoundation

private struct TestCase: Decodable {
    let id, path, split, group, record, condition, method: String
    let s1: [Double]
}
private struct Frame: Encodable {
    let seconds: Double
    let bpm, original, cycle, reference: Double?
    let status: String
}
private struct Result: Encodable {
    let id, split, group, record, condition, method: String
    let frames: [Frame]
}

@main struct Benchmark {
    static func main() throws {
        let cases = try JSONDecoder().decode([TestCase].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        let encoder = JSONEncoder()
        for test in cases {
            let file = try AVAudioFile(forReading: URL(fileURLWithPath: test.path))
            let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length))!
            try file.read(into: buffer)
            let audio = Array(UnsafeBufferPointer(start: buffer.floatChannelData![0], count: Int(buffer.frameLength)))
            let rate = file.processingFormat.sampleRate, step = Int(rate / 2)
            var estimator = HeartRateEstimator(sampleRate: rate), frames: [Frame] = []
            for i in stride(from: 0, to: audio.count, by: step) {
                let end = min(i + step, audio.count)
                estimator.append(Array(audio[i..<end]))
                let result = estimator.estimate(), seconds = Double(end) / rate
                guard seconds >= 6 else { continue }
                let beats = test.s1.filter { $0 >= max(0, seconds - 8) && $0 <= seconds }
                let intervals = zip(beats, beats.dropFirst()).map { $1 - $0 }.filter { $0 > 0 }
                let reference = intervals.count >= 4 ? 60 / median(intervals) : nil
                frames.append(Frame(seconds: seconds, bpm: result.bpm, original: result.original,
                                    cycle: result.cycle, reference: reference, status: result.status))
            }
            let result = Result(id: test.id, split: test.split, group: test.group, record: test.record,
                                condition: test.condition, method: test.method, frames: frames)
            var data = try encoder.encode(result); data.append(10); FileHandle.standardOutput.write(data)
        }
    }
}
