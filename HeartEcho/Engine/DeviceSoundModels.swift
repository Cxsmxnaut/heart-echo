import Foundation
import CoreML

final class DeviceSoundModels: HeartSoundModels, @unchecked Sendable {
    private let timing: MLModel, cleaner: MLModel?
    var hasDenoiser: Bool { cleaner != nil }
    init(directory: URL? = nil) throws {
        func load(_ name: String, required: Bool) throws -> MLModel? {
            let compiled = directory?.appendingPathComponent(name + ".mlmodelc") ?? Bundle.main.url(forResource: name, withExtension: "mlmodelc")
            let package = directory?.appendingPathComponent(name + ".mlpackage")
            let location: URL?
            if let compiled, FileManager.default.fileExists(atPath: compiled.path) { location = compiled }
            else if let package, FileManager.default.fileExists(atPath: package.path) { location = try MLModel.compileModel(at: package) }
            else { location = nil }
            guard let location else {
                if required { throw NSError(domain: "ChestBPM.Model", code: 1, userInfo: [NSLocalizedDescriptionKey: "The sound-timing model is missing."]) }
                return nil
            }
            let config = MLModelConfiguration(); config.computeUnits = .all
            return try MLModel(contentsOf: location, configuration: config)
        }
        timing = try load("BeatStates", required: true)!
        let metadata = timing.modelDescription.metadata[.creatorDefinedKey] as? [String: String]
        guard metadata?["feature_schema"] == "chestbpm-energy-v1" else { throw CocoaError(.coderReadCorrupt) }
        cleaner = try load("HeartDenoiser", required: false)
    }
    private func predict(_ values: [Float], shape: [NSNumber], input: String, output: String, model: MLModel) throws -> [Float] {
        let tensor = try MLMultiArray(shape: shape, dataType: .float32)
        guard tensor.count == values.count else { throw CocoaError(.coderInvalidValue) }
        let pointer = tensor.dataPointer.bindMemory(to: Float.self, capacity: values.count)
        for i in values.indices { pointer[i] = values[i] }
        let features = try MLDictionaryFeatureProvider(dictionary: [input: MLFeatureValue(multiArray: tensor)])
        guard let result = try model.prediction(from: features).featureValue(for: output)?.multiArrayValue else { throw CocoaError(.coderValueNotFound) }
        // Read through MLMultiArray indexing: native output strides are not assumed contiguous.
        if result.shape.count == 3 {
            let channels = result.shape[1].intValue, samples = result.shape[2].intValue
            return (0..<channels).flatMap { channel in (0..<samples).map { result[[0, NSNumber(value: channel), NSNumber(value: $0)]].floatValue } }
        }
        return (0..<result.count).map { result[$0].floatValue }
    }
    func states(_ features: [Float]) throws -> [Float] { try predict(features, shape: [1, 8, 200], input: "features", output: "logits", model: timing) }
    func denoise(_ samples: [Float]) throws -> [Float] {
        guard let cleaner else { throw CocoaError(.coderValueNotFound) }
        return try predict(samples, shape: [1, 1, 800], input: "noisy", output: "cleaned", model: cleaner)
    }
}
