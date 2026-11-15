import AVFoundation
import CoreML
import Foundation

enum MurmurFinding: String, Codable { case absent, present, unsure }
struct MurmurReading: Codable {
    let finding: MurmurFinding, probabilities: [Double], windows: Int, seconds: Double
    var title: String {
        switch finding {
        case .absent: return "Not detected in this recording"
        case .present: return "Murmur-like pattern"
        case .unsure: return "Unsure"
        }
    }
}
enum MurmurRules {
    static let rate = 2000.0, size = 8000, threshold = 0.60
    static func finding(_ p: [Double]) -> MurmurFinding {
        guard p.count == 3, p.allSatisfy({ $0.isFinite && $0 >= 0 && $0 <= 1 }), abs(p.reduce(0, +) - 1) < 0.001,
              let best = p.indices.max(by: { p[$0] < p[$1] }), p[best] >= threshold else { return .unsure }
        return best == 0 ? .absent : best == 1 ? .present : .unsure
    }
    static func starts(_ count: Int) -> [Int] {
        guard count >= size else { return [] }
        let last = (count - size) / 40 * 40
        return Array(Set(Array(stride(from: 0, through: last, by: size)) + [last])).sorted()
    }
    static func usable(_ x: [Float]) -> Bool {
        x.count == size && x.allSatisfy(\.isFinite) &&
        sqrt(x.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(size)) >= 0.00002 &&
        Double(x.filter { abs($0) >= 0.999 }.count) / Double(size) <= 0.01
    }
}

/// Separate audio-only model. No Watch values or BPM decisions enter this analysis.
final class MurmurAnalyzer: @unchecked Sendable {
    private let model: MLModel
    init(directory: URL? = nil) throws {
        let package = directory?.appendingPathComponent("Murmur.mlpackage")
        let compiled = directory?.appendingPathComponent("Murmur.mlmodelc") ?? Bundle.main.url(forResource: "Murmur", withExtension: "mlmodelc")
        let url: URL
        if let compiled, FileManager.default.fileExists(atPath: compiled.path) { url = compiled }
        else if let package, FileManager.default.fileExists(atPath: package.path) { url = try MLModel.compileModel(at: package) }
        else { throw NSError(domain: "Murmur", code: 1, userInfo: [NSLocalizedDescriptionKey: "The murmur research model is missing."]) }
        model = try MLModel(contentsOf: url)
        let metadata = model.modelDescription.metadata[.creatorDefinedKey] as? [String: String]
        guard metadata?["feature_schema"] == "chestbpm-murmur-wave-2k-v1" else { throw CocoaError(.coderReadCorrupt) }
    }
    func probabilities(_ samples: [Float]) throws -> [Double] {
        guard samples.count == MurmurRules.size else { throw CocoaError(.coderInvalidValue) }
        let input = try MLMultiArray(shape: [1, 1, 8000], dataType: .float32)
        let p = input.dataPointer.bindMemory(to: Float.self, capacity: samples.count)
        for i in samples.indices { p[i] = samples[i] }
        let provider = try MLDictionaryFeatureProvider(dictionary: ["waveform": MLFeatureValue(multiArray: input)])
        guard let result = try model.prediction(from: provider).featureValue(for: "probabilities")?.multiArrayValue,
              result.count == 3 else { throw CocoaError(.coderValueNotFound) }
        return (0..<3).map { result[$0].doubleValue }
    }
    func analyze(_ samples: [Float]) throws -> MurmurReading {
        var values: [[Double]] = []
        for start in MurmurRules.starts(samples.count) {
            let x = Array(samples[start..<start + MurmurRules.size])
            if MurmurRules.usable(x) { values.append(try probabilities(x)) }
        }
        let p = values.isEmpty ? [0, 0, 1.0] : (0..<3).map { c in values.reduce(0) { $0 + $1[c] } / Double(values.count) }
        return MurmurReading(finding: MurmurRules.finding(p), probabilities: p, windows: values.count, seconds: Double(samples.count) / 2000)
    }
    static func audio(_ url: URL) throws -> [Float] {
        let file = try AVAudioFile(forReading: url)
        let count = min(file.length, AVAudioFramePosition(file.processingFormat.sampleRate * 60))
        guard count > 0, let source = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(count)) else { throw CocoaError(.fileReadCorruptFile) }
        try file.read(into: source, frameCount: AVAudioFrameCount(count))
        if source.format.sampleRate == 2000, source.format.channelCount == 1, let p = source.floatChannelData?[0] {
            return Array(UnsafeBufferPointer(start: p, count: Int(source.frameLength)))
        }
        guard let format = AVAudioFormat(standardFormatWithSampleRate: 2000, channels: 1),
              let converter = AVAudioConverter(from: source.format, to: format),
              let target = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(Double(source.frameLength) * 2000 / source.format.sampleRate + 1024)) else { throw CocoaError(.fileReadCorruptFile) }
        var supplied = false, error: NSError?
        let status = converter.convert(to: target, error: &error) { _, flag in
            if supplied { flag.pointee = .endOfStream; return nil }
            supplied = true; flag.pointee = .haveData; return source
        }
        if let error { throw error }
        guard status != .error, let p = target.floatChannelData?[0] else { throw CocoaError(.fileReadCorruptFile) }
        return Array(UnsafeBufferPointer(start: p, count: Int(target.frameLength)))
    }
}
