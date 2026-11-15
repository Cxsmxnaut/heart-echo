import Foundation

struct AudioRequest: Decodable { let id: String, path: String }
struct AudioExport: Encodable { let id: String, samples: Int, file: String }

@main struct MurmurAudioExport {
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 3 else { throw CocoaError(.fileReadInvalidFileName) }
        let folder = URL(fileURLWithPath: args[2], isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let requests = try JSONDecoder().decode([AudioRequest].self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
        guard Set(requests.map(\.id)).count == requests.count else { throw CocoaError(.coderReadCorrupt) }
        for request in requests {
            guard request.id.range(of: "^[A-Za-z0-9_]+$", options: .regularExpression) != nil else { throw CocoaError(.fileReadInvalidFileName) }
            let audio = try MurmurAnalyzer.audio(URL(fileURLWithPath: request.path))
            guard audio.allSatisfy(\.isFinite), audio.count >= 8000 else { throw CocoaError(.fileReadCorruptFile) }
            let bits = audio.map { $0.bitPattern.littleEndian }
            let data = bits.withUnsafeBytes { Data($0) }
            let file = request.id + ".f32"
            try data.write(to: folder.appendingPathComponent(file), options: .atomic)
            let result = AudioExport(id: request.id, samples: audio.count, file: file)
            print(String(decoding: try JSONEncoder().encode(result), as: UTF8.self))
        }
    }
}
