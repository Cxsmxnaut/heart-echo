import XCTest

/// Keeps a second copy of simulator evidence if Xcode cannot export attachments.
@MainActor enum SubmissionEvidence {
    static func capture(_ app: XCUIApplication, name: String, test: XCTestCase, includeHierarchy: Bool = false) {
        let screenshot = app.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        test.add(attachment)

        let hierarchy = includeHierarchy ? app.debugDescription : nil
        if let hierarchy {
            let attachment = XCTAttachment(string: hierarchy)
            attachment.name = name + " — accessibility hierarchy"
            attachment.lifetime = .keepAlways
            test.add(attachment)
        }

        #if targetEnvironment(simulator)
        do {
            let documents = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask,
                                                        appropriateFor: nil, create: true)
            let directory = documents.appendingPathComponent("HeartEchoSubmissionEvidence", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let safeName = name.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) ? String($0) : "-" }.joined()
            let stamp = String(Int(Date().timeIntervalSince1970 * 1_000)) + "-" + String(UUID().uuidString.prefix(8))
            let base = directory.appendingPathComponent(stamp + "-" + String(safeName.prefix(90)))
            try screenshot.pngRepresentation.write(to: base.appendingPathExtension("png"), options: .atomic)
            if let hierarchy {
                try hierarchy.write(to: base.appendingPathExtension("txt"), atomically: true, encoding: .utf8)
            }
            let metadata = ["name": name, "test": test.name, "capturedAt": ISO8601DateFormatter().string(from: Date())]
            try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys])
                .write(to: base.appendingPathExtension("json"), options: .atomic)
            print("HEART_ECHO_UI_EVIDENCE " + base.lastPathComponent)
        } catch {
            print("Simulator evidence copy failed: " + error.localizedDescription)
        }
        #endif
    }
}
