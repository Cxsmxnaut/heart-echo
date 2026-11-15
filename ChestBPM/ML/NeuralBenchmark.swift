import Foundation
import AVFoundation

private struct Case: Decodable {
    let id, path, split, group, record, condition, method: String
    let s1: [Double]
}
private struct Frame: Encodable {
    let seconds, age: Double
    let bpm, legacy, reference: Double?
    let referenceLatest: Double?
    let measurementSpan: Double
    let diagnostics: RobustDiagnostics
    let reason, source: String
    let rawSupport: Double
}
private struct Result: Encodable {
    let id, split, group, record, condition, method: String
    let frames: [Frame]
}
@main struct NeuralBenchmark {
    static func main() throws {
        let args = CommandLine.arguments
        let cases = try JSONDecoder().decode([Case].self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
        let models = try DeviceSoundModels(directory: URL(fileURLWithPath: args[2]))
        let encoder = JSONEncoder(), denoise = args.contains("--denoised")
        for test in cases {
            let file = try AVAudioFile(forReading: URL(fileURLWithPath: test.path))
            let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length))!
            try file.read(into: buffer)
            let samples = Array(UnsafeBufferPointer(start: buffer.floatChannelData![0], count: Int(buffer.frameLength)))
            let rate = file.processingFormat.sampleRate, step = Int(rate / 2)
            let pipeline = HeartSoundPipeline(rate: rate, models: models, denoiserEnabled: denoise, adaptiveTiming: args.contains("--adaptive"))
            var legacy = HeartRateEstimator(sampleRate: rate), frames: [Frame] = []
            for start in stride(from: 0, to: samples.count, by: step) {
                let end = min(start + step, samples.count), block = Array(samples[start..<end])
                pipeline.append(block); legacy.append(block)
                let estimate = pipeline.estimate(), baseline = legacy.estimate(), time = Double(end) / rate
                guard time >= 6 else { continue }
                let effective = time - estimate.analysisAge
                let beats = test.s1.filter { $0 >= max(0, effective - 8) && $0 <= effective }
                let intervals = zip(beats, beats.dropFirst()).map { $1 - $0 }
                let reference = intervals.count >= 4 ? 60 / median(intervals) : nil
                let latest = Array(test.s1.filter { $0 >= 0 && $0 <= effective }.suffix(5))
                let latestIntervals = zip(latest, latest.dropFirst()).map { $1 - $0 }
                let latestReference: Double?
                if latest.count == 5, let last = latest.last, effective - last <= median(latestIntervals) * 1.5 {
                    latestReference = 240 / (latest[4] - latest[0])
                } else { latestReference = nil }
                var detail = estimate
                detail.envelope = nil; detail.brightness = nil; detail.stateProbabilities = nil
                frames.append(Frame(seconds: time, age: estimate.analysisAge, bpm: estimate.bpm, legacy: baseline.bpm,
                                    reference: reference, referenceLatest: latestReference, measurementSpan: estimate.windowSeconds,
                                    diagnostics: detail,
                                    reason: estimate.reason, source: estimate.method, rawSupport: estimate.rawSupport))
            }
            var data = try encoder.encode(Result(id: test.id, split: test.split, group: test.group, record: test.record,
                                                condition: test.condition, method: denoise ? "neural_fused" : args.contains("--adaptive") ? "neural_adaptive" : "neural_raw", frames: frames))
            data.append(10); FileHandle.standardOutput.write(data)
        }
    }
}
