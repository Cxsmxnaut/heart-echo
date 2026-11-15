import Foundation

@main struct FeatureProbe {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let samples = data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        var bank = HeartFeatureBank(), output: [Float] = []
        for sample in samples { if let frame = bank.append(sample) { output += frame.values } }
        FileHandle.standardOutput.write(output.withUnsafeBytes { Data($0) })
    }
}
