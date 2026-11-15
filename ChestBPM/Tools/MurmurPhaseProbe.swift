import CoreML
import Foundation

struct PhaseRequest: Decodable { let id: String, path: String }
struct PhaseOutput: Encodable {
    let id: String, classes: [Double], phases: [Int], phaseProbabilities: [[Double]]
}
@main struct MurmurPhaseProbe {
    static func main() throws {
        let args = CommandLine.arguments, directory = URL(fileURLWithPath: CommandLine.arguments[2])
        let package = directory.appendingPathComponent("Murmur.mlpackage")
        let model = try MLModel(contentsOf: MLModel.compileModel(at: package))
        let metadata = model.modelDescription.metadata[.creatorDefinedKey] as? [String: String]
        guard metadata?["phase_labels"] == "noise,S1,systole,S2,diastole" else { throw CocoaError(.coderReadCorrupt) }
        let requests = try JSONDecoder().decode([PhaseRequest].self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        for request in requests {
            let audio = try MurmurAnalyzer.audio(URL(fileURLWithPath: request.path))
            guard audio.count >= 8000 else { throw CocoaError(.fileReadCorruptFile) }
            let tensor = try MLMultiArray(shape: [1, 1, 8000], dataType: .float32)
            let pointer = tensor.dataPointer.bindMemory(to: Float.self, capacity: 8000)
            for i in 0..<8000 { pointer[i] = audio[i] }
            let result = try model.prediction(from: MLDictionaryFeatureProvider(dictionary: ["waveform": MLFeatureValue(multiArray: tensor)]))
            guard let p = result.featureValue(for: "probabilities")?.multiArrayValue,
                  let q = result.featureValue(for: "phase_probabilities")?.multiArrayValue,
                  q.shape.map(\.intValue) == [1, 5, 194] else { throw CocoaError(.coderReadCorrupt) }
            let probabilities = (0..<5).map { c in (0..<194).map { t in q[[0, NSNumber(value: c), NSNumber(value: t)]].doubleValue } }
            let phases = (0..<194).map { t in (0..<5).max(by: { probabilities[$0][t] < probabilities[$1][t] })! }
            let output = PhaseOutput(id: request.id, classes: (0..<3).map { p[$0].doubleValue }, phases: phases, phaseProbabilities: probabilities)
            print(String(decoding: try encoder.encode(output), as: UTF8.self))
        }
    }
}
