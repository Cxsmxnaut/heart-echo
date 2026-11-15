import Foundation
import AVFoundation
import Darwin

private struct Request: Decodable {
    let id, path, output: String
    let updates: [Update]
}
private struct Update: Codable {
    let sequence, samples: Int
    let time, elapsed, motion: Double
}
private struct Frame: Encodable {
    let update: Update
    let recordedPCM: Bool
    let estimate: RobustDiagnostics
    let input: TimingReplayInput
}

// Watch/reference data are deliberately absent from this executable's input schema.
@main struct AudioReplay {
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
            let pipeline = HeartSoundPipeline(rate: file.processingFormat.sampleRate, models: models)
            let url = URL(fileURLWithPath: request.output)
            FileManager.default.createFile(atPath: url.path, contents: nil)
            let stream = try FileHandle(forWritingTo: url)
            var offset = 0
            for update in request.updates {
                guard update.samples > offset, update.samples <= samples.count else { throw CocoaError(.fileReadCorruptFile) }
                pipeline.append(Array(samples[offset..<update.samples]), motion: update.motion); offset = update.samples
                let estimate = pipeline.estimate()
                let frame = Frame(update: update, recordedPCM: true, estimate: estimate, input: pipeline.replayInput())
                var data = try encoder.encode(frame); data.append(10); try stream.write(contentsOf: data)
            }
            try stream.close()
            print("Replayed \(request.id): \(request.updates.count) updates from saved PCM audio")
        }
    }
}
