import Foundation
import Darwin

/// Owns product files only. Legacy diagnostic recordings are never swept.
final class RecordingFiles {
    enum Operation: String, Codable { case retain, delete }
    struct Journal: Codable {
        var operation: Operation
        var id: UUID
        var audioFile: String?
        var diagnosticAudio: String?
    }
    let root: URL, diagnostics: URL
    var pending: URL { root.appendingPathComponent("Pending", isDirectory: true) }
    var history: URL { root.appendingPathComponent("recordings.json") }
    private var operations: URL { root.appendingPathComponent("Operations", isDirectory: true) }
    private var deletionList: URL { diagnostics.deletingLastPathComponent().appendingPathComponent("audio-deleted.json") }
    private let fm: FileManager
    private let protect: (URL) throws -> Void
    private let remove: (URL) throws -> Void
    private let beforeCommit: (URL) throws -> Void

    init(root: URL, diagnostics: URL, files: FileManager = .default,
         protect: @escaping (URL) throws -> Void = RecordingFiles.protect,
         remove: @escaping (URL) throws -> Void = { try FileManager.default.removeItem(at: $0) },
         beforeCommit: @escaping (URL) throws -> Void = { _ in }) {
        self.root = root; self.diagnostics = diagnostics; fm = files
        self.protect = protect; self.remove = remove; self.beforeCommit = beforeCommit
    }
    static func protect(_ url: URL) throws {
        #if os(iOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
        #endif
    }
    func prepare() throws {
        for directory in [root, pending, operations, diagnostics] { try fm.createDirectory(at: directory, withIntermediateDirectories: true) }
        for var directory in [root, diagnostics.deletingLastPathComponent()] {
            var flags = URLResourceValues(); flags.isExcludedFromBackup = true; try directory.setResourceValues(flags)
        }
        if !fm.fileExists(atPath: deletionList.path) { try write(try JSONEncoder().encode([String]()), to: deletionList) }
    }
    /// All throwing protection/checks happen before rename, the single commit point.
    func write(_ data: Data, to url: URL) throws {
        let stage = url.deletingLastPathComponent().appendingPathComponent(".heartecho-write-" + UUID().uuidString + ".tmp")
        defer { try? fm.removeItem(at: stage) }
        #if os(iOS)
        try data.write(to: stage, options: .completeFileProtectionUntilFirstUserAuthentication)
        #else
        try data.write(to: stage)
        #endif
        try protect(stage); try beforeCommit(url)
        guard rename(stage.path, url.path) == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
    }
    func load() throws -> [HeartRecording] {
        fm.fileExists(atPath: history.path) ? try JSONDecoder().decode([HeartRecording].self, from: Data(contentsOf: history)) : []
    }
    func save(_ records: [HeartRecording]) throws { try write(JSONEncoder().encode(records), to: history) }
    private func journalURL(_ journal: Journal) -> URL { operations.appendingPathComponent(journal.id.uuidString + "-" + journal.operation.rawValue + ".json") }
    private func journal(_ record: HeartRecording, _ operation: Operation) -> Journal {
        Journal(operation: operation, id: record.id, audioFile: record.audioFile, diagnosticAudio: record.diagnosticAudio)
    }
    private func owned(_ entry: Journal) throws -> [(URL, String?)] {
        var urls: [(URL, String?)] = []
        if let name = entry.audioFile {
            guard name == URL(fileURLWithPath: name).lastPathComponent, UUID(uuidString: URL(fileURLWithPath: name).deletingPathExtension().lastPathComponent) == entry.id,
                  URL(fileURLWithPath: name).pathExtension == "wav" else { throw CocoaError(.fileReadCorruptFile) }
            urls.append((root.appendingPathComponent(name), nil))
        }
        if let name = entry.diagnosticAudio {
            guard name == "Audio/" + entry.id.uuidString + ".wav" else { throw CocoaError(.fileReadCorruptFile) }
            urls.append((diagnostics.appendingPathComponent(entry.id.uuidString + ".wav"), name))
        }
        return urls
    }
    private func markDeleted(_ name: String, _ deleted: Bool) throws {
        var names = Set(try JSONDecoder().decode([String].self, from: Data(contentsOf: deletionList)))
        if deleted { names.insert(name) } else { names.remove(name) }
        try write(JSONEncoder().encode(names.sorted()), to: deletionList)
    }
    private func removeOwned(_ entry: Journal) throws {
        for (url, diagnosticName) in try owned(entry) {
            if fm.fileExists(atPath: url.path) { try remove(url) }
            if let diagnosticName {
                try markDeleted(diagnosticName, true)
            }
        }
    }
    func commit(_ record: HeartRecording, source: URL?, records: [HeartRecording]) throws {
        try prepare()
        guard let source else { try save(records); return }
        guard !(try load()).contains(where: { $0.id == record.id }) else { throw CocoaError(.fileWriteFileExists) }
        let entry = journal(record, .retain), path = journalURL(journal(record, .retain))
        let destinations = try owned(entry)
        try write(JSONEncoder().encode(entry), to: path)
        do {
            if let name = entry.diagnosticAudio { try markDeleted(name, false) }
            for (url, _) in destinations { try fm.copyItem(at: source, to: url); try protect(url) }
            try save(records)
        } catch {
            // A failed cleanup keeps its durable journal for retry on next launch.
            if (try? removeOwned(entry)) != nil { try? fm.removeItem(at: path) }
            throw error
        }
        try? fm.removeItem(at: path)
    }
    func delete(_ record: HeartRecording, records: inout [HeartRecording]) throws {
        try prepare()
        let entry = journal(record, .delete), path = journalURL(journal(record, .delete))
        _ = try owned(entry); try write(JSONEncoder().encode(entry), to: path)
        try removeOwned(entry)
        let next = records.filter { $0.id != record.id }; try save(next)
        records = next; try? fm.removeItem(at: path)
    }
    func removePending(_ url: URL) throws {
        guard url.deletingLastPathComponent().resolvingSymlinksInPath().standardizedFileURL.path == pending.resolvingSymlinksInPath().standardizedFileURL.path else { throw CocoaError(.fileWriteNoPermission) }
        if fm.fileExists(atPath: url.path) { try remove(url) }
    }
    func recoverPending() throws {
        for url in try fm.contentsOfDirectory(at: pending, includingPropertiesForKeys: nil) { try removePending(url) }
    }
    func recover(_ records: inout [HeartRecording]) throws {
        for url in try fm.contentsOfDirectory(at: operations, includingPropertiesForKeys: nil) where url.pathExtension == "json" {
            let entry = try JSONDecoder().decode(Journal.self, from: Data(contentsOf: url)); _ = try owned(entry)
            if entry.operation == .delete {
                try removeOwned(entry)
                let next = records.filter { $0.id != entry.id }; try save(next); records = next
            } else if !records.contains(where: { $0.id == entry.id }) { try removeOwned(entry) }
            try? fm.removeItem(at: url)
        }
        // Upgrade recovery: UUID.wav in this private root was created only by product retention.
        let referenced = Set(records.compactMap(\.audioFile))
        for url in try fm.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) where url.pathExtension == "wav" && !referenced.contains(url.lastPathComponent) {
            guard let id = UUID(uuidString: url.deletingPathExtension().lastPathComponent) else { continue }
            let diagnostic = diagnostics.appendingPathComponent(id.uuidString + ".wav")
            let entry = Journal(operation: .retain, id: id, audioFile: url.lastPathComponent, diagnosticAudio: fm.fileExists(atPath: diagnostic.path) ? "Audio/" + diagnostic.lastPathComponent : nil)
            let path = journalURL(entry); try write(JSONEncoder().encode(entry), to: path); try removeOwned(entry); try? fm.removeItem(at: path)
        }
        for directory in [root, operations, diagnostics.deletingLastPathComponent()] {
            for url in try fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) where url.lastPathComponent.hasPrefix(".heartecho-write-") && url.pathExtension == "tmp" { try? fm.removeItem(at: url) }
        }
    }
}
