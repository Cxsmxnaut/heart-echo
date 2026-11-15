import Foundation
import Darwin

@main struct StorageChecks {
    static func main() throws {
        setbuf(stdout, nil)
        let fm = FileManager.default
        let base = fm.temporaryDirectory.appendingPathComponent("HeartEcho-storage-checks-" + UUID().uuidString)
        defer { try? fm.removeItem(at: base) }
        var failures = 0
        func check(_ value: Bool, _ message: String) { print("\(value ? "PASS" : "FAIL"): \(message)"); if !value { failures += 1 } }
        func setup(_ name: String, protect: @escaping (URL) throws -> Void = { _ in }, remove: @escaping (URL) throws -> Void = { try FileManager.default.removeItem(at: $0) }, before: @escaping (URL) throws -> Void = { _ in }) throws -> RecordingFiles {
            let root = base.appendingPathComponent(name)
            let io = RecordingFiles(root: root.appendingPathComponent("Product"), diagnostics: root.appendingPathComponent("Diagnostics/Audio"), protect: protect, remove: remove, beforeCommit: before)
            try io.prepare(); return io
        }
        func record() -> HeartRecording { HeartRecording(title: "Local test", source: "iPhone microphone", seconds: 20, bpm: nil, signalStatus: "No accepted BPM", murmur: nil) }
        func source(_ io: RecordingFiles) throws -> URL { let url = io.pending.appendingPathComponent("source.wav"); try Data("test audio, not a person".utf8).write(to: url); return url }
        func hasJournal(_ io: RecordingFiles) throws -> Bool { try fm.contentsOfDirectory(atPath: io.root.appendingPathComponent("Operations").path).contains { $0.hasSuffix(".json") } }
        enum Failure: Error { case injected }

        var protectFails = false
        let protected = try setup("protection", protect: { _ in if protectFails { throw Failure.injected } })
        let first = record(); try protected.save([first]); let original = try Data(contentsOf: protected.history)
        protectFails = true
        do { try protected.save([record(), first]); check(false, "Injected protection failure throws") } catch { check(true, "Injected protection failure throws") }
        check(try Data(contentsOf: protected.history) == original, "Failed protection leaves committed history byte-for-byte unchanged")
        protectFails = false
        var rejectHistory = false
        let boundary = try setup("boundary", before: { if rejectHistory && $0.lastPathComponent == "recordings.json" { throw Failure.injected } })
        try boundary.save([first]); rejectHistory = true
        do { try boundary.save([]); check(false, "Pre-commit failure throws") } catch { check(true, "Pre-commit failure throws") }
        check(try boundary.load().map(\.id) == [first.id], "Failed replacement retains the previous record")

        var failRemoval = false
        let deleting = try setup("deletion", remove: { url in if failRemoval && url.pathExtension == "wav" { throw Failure.injected }; try fm.removeItem(at: url) })
        var retained = record(); retained.audioFile = retained.id.uuidString + ".wav"; retained.diagnosticAudio = "Audio/" + retained.id.uuidString + ".wav"
        let raw = try source(deleting); try deleting.commit(retained, source: raw, records: [retained]); var history = try deleting.load()
        failRemoval = true
        do { try deleting.delete(retained, records: &history); check(false, "Failed audio delete throws") } catch { check(true, "Failed audio delete throws") }
        check(try history.count == 1 && deleting.load().count == 1, "Deletion failure preserves both UI and disk history")
        check(try hasJournal(deleting), "Failed deletion retains a durable owner for retry")
        let manifest = deleting.diagnostics.deletingLastPathComponent().appendingPathComponent("audio-deleted.json")
        check(try JSONDecoder().decode([String].self, from: Data(contentsOf: manifest)).isEmpty, "A failed removal never claims audio was deleted")
        failRemoval = false; try deleting.recover(&history)
        check(try history.isEmpty && deleting.load().isEmpty && !hasJournal(deleting), "Relaunch recovery finishes the requested deletion and history commit")
        check(!fm.fileExists(atPath: deleting.root.appendingPathComponent(retained.audioFile!).path) && !fm.fileExists(atPath: deleting.diagnostics.appendingPathComponent(retained.id.uuidString + ".wav").path), "Recovery removes both retained copies")
        check(try JSONDecoder().decode([String].self, from: Data(contentsOf: manifest)) == [retained.diagnosticAudio!], "Successful removal is durably visible to the collector")

        let crashing = try setup("crash")
        var orphan = record(); orphan.audioFile = orphan.id.uuidString + ".wav"; orphan.diagnosticAudio = "Audio/" + orphan.id.uuidString + ".wav"
        let journal = RecordingFiles.Journal(operation: .retain, id: orphan.id, audioFile: orphan.audioFile, diagnosticAudio: orphan.diagnosticAudio)
        let path = crashing.root.appendingPathComponent("Operations/" + orphan.id.uuidString + "-retain.json")
        try crashing.write(JSONEncoder().encode(journal), to: path)
        try Data("owned".utf8).write(to: crashing.root.appendingPathComponent(orphan.audioFile!)); try Data("owned diagnostic".utf8).write(to: crashing.diagnostics.appendingPathComponent(orphan.id.uuidString + ".wav"))
        let legacy = crashing.diagnostics.appendingPathComponent(UUID().uuidString + ".wav"); try Data("legacy test; preserve".utf8).write(to: legacy)
        var empty: [HeartRecording] = []; try crashing.recover(&empty)
        check(!fm.fileExists(atPath: crashing.root.appendingPathComponent(orphan.audioFile!).path) && !fm.fileExists(atPath: crashing.diagnostics.appendingPathComponent(orphan.id.uuidString + ".wav").path), "Crash before history commit cleans only journal-owned audio")
        check(fm.fileExists(atPath: legacy.path), "Recovery preserves unrelated legacy diagnostic audio")
        try crashing.commit(orphan, source: source(crashing), records: [orphan])
        let deletionManifest = crashing.diagnostics.deletingLastPathComponent().appendingPathComponent("audio-deleted.json")
        check(try JSONDecoder().decode([String].self, from: Data(contentsOf: deletionManifest)).isEmpty, "A successful retry clears the old audio-deletion marker")
        try crashing.write(JSONEncoder().encode(journal), to: path)
        var committed = try crashing.load(); try crashing.recover(&committed)
        check(committed.count == 1 && fm.fileExists(atPath: crashing.root.appendingPathComponent(orphan.audioFile!).path), "Crash after history commit keeps saved recording and audio")
        let pending = crashing.pending.appendingPathComponent("unfinished.wav"); try Data("unfinished".utf8).write(to: pending)
        try Data("corrupt history".utf8).write(to: crashing.history); try crashing.recoverPending()
        check(try !fm.fileExists(atPath: pending.path) && Data(contentsOf: crashing.history) == Data("corrupt history".utf8), "Pending capture cleanup does not overwrite corrupt history")
        print("\(failures) failure(s). Local synthetic file checks; no personal recordings.")
        if failures > 0 { exit(1) }
    }
}
