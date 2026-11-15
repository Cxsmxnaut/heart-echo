import Foundation

struct Request: Decodable { let id: String, path: String }
@main struct MurmurProbe {
    static func main() throws {
        let args = CommandLine.arguments
        let requests = try JSONDecoder().decode([Request].self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
        let model = try MurmurAnalyzer(directory: URL(fileURLWithPath: args[2]))
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        for request in requests {
            let start = Date(); let x = try MurmurAnalyzer.audio(URL(fileURLWithPath: request.path))
            let result = try model.analyze(x)
            struct Output: Encodable { let id: String, reading: MurmurReading, milliseconds: Double }
            let value = Output(id: request.id, reading: result, milliseconds: Date().timeIntervalSince(start) * 1000)
            print(String(decoding: try encoder.encode(value), as: UTF8.self))
        }
    }
}
