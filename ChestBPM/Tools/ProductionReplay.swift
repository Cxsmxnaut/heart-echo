import Foundation
import AVFoundation
import Darwin

private struct Update: Codable { let sequence, samples: Int; let time, elapsed, motion: Double }
private struct Request: Decodable { let id, path, output: String; let updates: [Update] }
private struct Result: Encodable { let update: Update; let estimate: RobustDiagnostics; let status: String }

// Exercise the complete shipped estimator, including its clipping/level checks.
// The request schema contains no Watch values or diagnoses.
@main struct ProductionReplay {
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
            var estimator = HeartRateEstimator(sampleRate: file.processingFormat.sampleRate, models: models), offset = 0
            let path = request.output.replacingOccurrences(of: ".ndjson", with: ".production.ndjson")
            FileManager.default.createFile(atPath: path, contents: nil)
            let stream = try FileHandle(forWritingTo: URL(fileURLWithPath: path))
            for update in request.updates {
                guard update.samples > offset, update.samples <= samples.count else { throw CocoaError(.fileReadCorruptFile) }
                estimator.append(Array(samples[offset..<update.samples]), motion: update.motion); offset = update.samples
                let result = estimator.estimate()
                var detail = result.diagnostics.enhanced ?? RobustDiagnostics()
                if result.bpm == nil, detail.bpm != nil { detail.reason = "outer_signal_guard" }
                detail.bpm = result.bpm; detail.envelope = nil; detail.brightness = nil; detail.stateProbabilities = nil
                var data = try encoder.encode(Result(update: update, estimate: detail, status: result.status)); data.append(10)
                try stream.write(contentsOf: data)
            }
            try stream.close(); print("Production replay \(request.id)")
        }
    }
}
