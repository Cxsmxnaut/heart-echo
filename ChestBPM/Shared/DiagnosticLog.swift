import Foundation

struct DiagnosticEvent: Encodable, Sendable {
    var schema = 1, sequence = 0
    var run = UUID(), time = Date(), uptime = ProcessInfo.processInfo.systemUptime
    let event: String
    var message: String?, test: UUID?, position: String?
    var participant: String?, condition: String?, audioFile: String?
    var denoiserEnabled: Bool?
    var study: UUID?, cycle: Int?, step: Int?, attempt: Int?
    var command: TrialCommand?, acknowledgement: WatchAck?
    var running: Bool?, elapsed: Double?, remaining: Double?, audioAge: Double?, processingMS: Double?
    #if !os(watchOS)
    var estimate: HeartRateEstimate?, pair: WatchPair?
    #endif
    var watch: WatchPacket?, watchFresh: Bool?
    var sampleRate: Double?, channels: Int?, input: String?, route: String?, connection: String?
}

/// Ordered, bounded local log. File work never runs on the microphone callback.
final class DiagnosticLog: @unchecked Sendable {
    private let queue = DispatchQueue(label: "ChestBPM.diagnostics", qos: .utility)
    let directory: URL
    var url: URL { directory.appendingPathComponent("live.ndjson") }
    private var file: FileHandle?, run = UUID(), sequence = 0, bytes = 0, failure: String?
    private var snapshot = LogSnapshot()
    private var archives: [LogArchive] = []
    private var manifestURL: URL { directory.appendingPathComponent("manifest.json") }
    init(directory: URL) { self.directory = directory }
    var state: (rows: Int, bytes: Int, error: String?) { queue.sync { (sequence, bytes, failure) } }
    func start() throws {
        try queue.sync {
            closeCurrent()
            if let data = try? Data(contentsOf: manifestURL) { archives = try JSONDecoder().decode([LogArchive].self, from: data) }
            for i in archives.indices where !archives[i].closed { archives[i].closed = true; archives[i].error = "Interrupted before clean close" }
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            var local = directory, flags = URLResourceValues(); flags.isExcludedFromBackup = true
            try local.setResourceValues(flags)
            let previous = directory.appendingPathComponent("previous.ndjson")
            if FileManager.default.fileExists(atPath: previous.path) { try FileManager.default.removeItem(at: previous) }
            if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.moveItem(at: url, to: previous) }
            guard FileManager.default.createFile(atPath: url.path, contents: nil) else { throw CocoaError(.fileWriteUnknown) }
            #if os(iOS) || os(watchOS)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
            #endif
            run = UUID()
            let archive = directory.appendingPathComponent("Runs")
            try FileManager.default.createDirectory(at: archive, withIntermediateDirectories: true)
            try FileManager.default.linkItem(at: url, to: archive.appendingPathComponent(run.uuidString + ".ndjson"))
            file = try FileHandle(forWritingTo: url); sequence = 0; bytes = 0; failure = nil
            snapshot = LogSnapshot(run: run)
            archives.append(LogArchive(run: run, file: "Runs/" + run.uuidString + ".ndjson", created: Date()))
            try saveManifest()
        }
    }
    func write(_ value: DiagnosticEvent) {
        queue.async {
            guard let file = self.file, self.failure == nil else { return }
            do {
                var value = value; value.sequence = self.sequence + 1; value.run = self.run
                let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .millisecondsSince1970
                encoder.nonConformingFloatEncodingStrategy = .convertToString(positiveInfinity: "Infinity", negativeInfinity: "-Infinity", nan: "NaN")
                var data = try encoder.encode(value); data.append(10)
                guard self.bytes + data.count <= 10_000_000 else { throw CocoaError(.fileWriteOutOfSpace) }
                try file.write(contentsOf: data)
                self.sequence += 1; self.bytes += data.count
                self.snapshot.update(value, rows: self.sequence, bytes: self.bytes)
                // A small atomically replaced status avoids repeatedly copying a growing multi-MB log.
                try self.snapshotData().write(to: self.directory.appendingPathComponent("status.json"), options: .atomic)
                if value.event == "heartbeat" || value.event.hasSuffix("ended") || value.event == "watch_stopped" { try file.synchronize() }
            } catch { self.failure = error.localizedDescription; self.closeCurrent() }
        }
    }
    private func snapshotData() throws -> Data {
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .millisecondsSince1970
        encoder.nonConformingFloatEncodingStrategy = .convertToString(positiveInfinity: "Infinity", negativeInfinity: "-Infinity", nan: "NaN")
        return try encoder.encode(snapshot)
    }
    func flush() throws { try queue.sync { try file?.synchronize() } }
    private func saveManifest() throws { try JSONEncoder().encode(archives).write(to: manifestURL, options: .atomic) }
    private func closeCurrent() {
        guard file != nil else { return }
        try? file?.synchronize(); try? file?.close(); file = nil
        snapshot.closed = true; snapshot.error = failure
        if let i = archives.firstIndex(where: { $0.run == run }) {
            archives[i].closed = true; archives[i].rows = sequence; archives[i].bytes = bytes; archives[i].error = failure
            try? saveManifest()
        }
        try? snapshotData().write(to: directory.appendingPathComponent("status.json"), options: .atomic)
    }
    func stop() { queue.sync { closeCurrent() } }
    func clear() throws { stop(); try queue.sync { if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }; sequence = 0; bytes = 0; failure = nil; archives = [] } }
}

private struct LogSnapshot: Encodable {
    var run = UUID(), time = Date(), sequence = 0, bytes = 0
    var closed = false, error: String?
    var state = "idle"
    var event = "ready", test: UUID?, study: UUID?, participant: String?, condition: String?, cycle: Int?, step: Int?
    var running = false, elapsed: Double?, remaining: Double?, phoneBPM: Double?, watchBPM: Double?, watchTime: Date?, processingMS: Double?, message: String?
    mutating func update(_ value: DiagnosticEvent, rows: Int, bytes: Int) {
        time = value.time; event = value.event; sequence = rows; self.bytes = bytes
        if value.test != nil || value.event == "app_ready" {
            test = value.test ?? test; study = value.study ?? study; participant = value.participant ?? participant; condition = value.condition ?? condition
            cycle = value.cycle ?? cycle; step = value.step ?? step
        }
        running = value.running ?? running
        elapsed = value.elapsed ?? elapsed; remaining = value.remaining ?? remaining; message = value.message
        if value.event == "test_preparing" { state = "preparing"; phoneBPM = nil; elapsed = nil }
        if value.event == "test_started" { state = value.message == "watch_control_only" ? "control_check" : "recording"; phoneBPM = nil; elapsed = 0 }
        if value.event == "test_ended" { state = value.message == "timed_test_complete" ? "completed" : "aborted" }
        if value.event == "test_aborted" { state = "aborted" }
        if ["test_ended", "test_aborted", "audio_stopped"].contains(value.event) { running = false; remaining = 0 }
        if let watch = value.watch {
            watchBPM = watch.bpm; watchTime = watch.end
            #if os(watchOS)
            running = watch.active; state = watch.active ? "measuring" : "completed"; test = watch.trial ?? test
            #endif
        }
        #if !os(watchOS)
        if let estimate = value.estimate { phoneBPM = estimate.bpm; processingMS = value.processingMS }
        #endif
    }
}

private struct LogArchive: Codable {
    let run: UUID, file: String, created: Date
    var rows = 0, bytes = 0, closed = false
    var error: String?
}
