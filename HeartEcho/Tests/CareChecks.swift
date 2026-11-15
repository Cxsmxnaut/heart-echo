import Foundation

@main struct CareChecks {
    @MainActor static func main() async throws {
        var failures = 0
        func check(_ ok: Bool, _ message: String) { print("\(ok ? "PASS" : "FAIL"): \(message)"); if !ok { failures += 1 } }
        let silent = AudioAssessment.inspect(Array(repeating: 0, count: 40000))
        check(silent.issue == "too_quiet", "Silence explains the volume problem")
        check(AudioAssessment.inspect(Array(repeating: 1, count: 8000)).issue == "clipped", "Clipping explains distortion")
        check(AudioAssessment.inspect(Array(repeating: 0.02, count: 100)).issue == "too_short", "Short audio suggests a longer recording")
        check(AudioAssessment.inspect([Float.nan] + Array(repeating: 0.02, count: 8000)).issue == "invalid_audio", "Invalid values cannot pass the input check")
        let audio = (0..<8000).map { Float(sin(Double($0) * 0.2) * 0.03) }
        check(AudioAssessment.inspect(audio).issue == nil, "Basic checks do not invent a clinical quality score")
        for finding in [MurmurFinding.present, .absent, .unsure] {
            var record = HeartRecording(title: "Public test", source: "Public CirCor recording", seconds: 20, bpm: nil, signalStatus: "BPM unavailable", murmur: MurmurReading(finding: finding, probabilities: [0,0,1], windows: 5, seconds: 20))
            record.publicSample = "present"
            let data = try JSONEncoder().encode(CareSummary(record))
            let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            check(json["estimated_bpm"] is NSNull && (json["murmur"] as? [String:String])?["finding"] == finding.rawValue, "\(finding): null BPM preserves independent murmur finding")
            check(json["recording_source"] as? String == "public_example" && json["captured_at"] == nil && json["analyzed_at"] != nil, "Public example analysis time is not called a capture time")
            check(Set(json.keys).isDisjoint(with: ["waveform", "audioFile", "diagnosticAudio", "id", "title", "probabilities"]), "Summary excludes audio, waveform and identifiers")
        }
        let rawNegative = MurmurReading(finding: .absent, probabilities: [1,0,0], windows: 5, seconds: 20)
        var poor = HeartRecording(title: "Poor signal", source: "iPhone microphone", seconds: 20, bpm: nil, signalStatus: "Unavailable", murmur: rawNegative)
        poor.audioAssessment = AudioAssessment(issue: "too_quiet", detail: "The audio was too quiet.")
        let poorJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(CareSummary(poor))) as! [String: Any]
        check((poorJSON["murmur"] as? [String:String])?["finding"] == "unsure", "Poor audio stays uncertain when a result summary is shared")
        let chat = CareService()
        let first = HeartRecording(title: "First", source: "Imported recording", seconds: 20, bpm: nil, signalStatus: "Unavailable", murmur: nil)
        let second = HeartRecording(title: "Second", source: "Imported recording", seconds: 20, bpm: nil, signalStatus: "Unavailable", murmur: nil)
        await chat.prepareChat(for: first)
        chat.appendChatMessage("A question", isUser: true)
        chat.chatShareSummary = true
        await chat.prepareChat(for: nil)
        check(chat.chatRecording?.id == first.id && chat.chatMessages.count == 1, "Opening Care without a new result preserves the same chat")
        await chat.prepareChat(for: second)
        check(chat.chatRecording?.id == second.id && chat.chatMessages.isEmpty && !chat.chatShareSummary, "A different recording starts a clean chat and resets sharing consent")
        await chat.forgetDeletedRecording(second.id)
        check(chat.chatRecording == nil && chat.chatMessages.isEmpty && !chat.chatShareSummary, "Deleting a result removes it from the active chat")
        for value in ["http://evil.example", "http://192.168.1.2.evil.example", "https://user:secret@example.org", "https://example.org/?summary=private"] {
            do { _ = try CareService.validatedEndpoint(value); check(false, "Reject invalid endpoint \(value)") } catch { check(true, "Reject invalid endpoint") }
        }
        check((try? CareService.validatedEndpoint("http://demo.local:4318")) != nil, "Explicit local demo endpoint is supported")
        check(CareListing.safeWebURL("javascript:alert(1)") == nil && CareListing.safeWebURL("https://example.org/source") != nil, "Directory links accept only web URLs")
        check(NativeCareDirectory.validZIP("94303") && !NativeCareDirectory.validZIP("９４３０３") && !NativeCareDirectory.validZIP("12'45"), "Direct directory queries require five ASCII digits")
        let clinic: [String: Any] = ["OBJECTID": 1, "SITE_NM": "SYNTHETIC CLINIC", "SITE_ADDRESS": "SYNTHETIC ADDRESS", "SITE_ZIP_CD": "94303-0000", "HCC_STATUS_DESC": "Active", "SITE_URL": "javascript:alert(1)"]
        let valid = NativeCareDirectory.clinics(["features": [["attributes": clinic]]], zip: "94303", now: "test")
        check(valid.count == 1 && valid[0].website == nil && valid[0].source == "HRSA Health Center Sites", "Direct care keeps provenance and rejects unsafe websites")
        var inactive = clinic; inactive["HCC_STATUS_DESC"] = "Inactive"
        var wrongZIP = clinic; wrongZIP["SITE_ZIP_CD"] = "10001"
        check(NativeCareDirectory.clinics(["features": [["attributes": inactive], ["attributes": wrongZIP]]], zip: "94303", now: "test").isEmpty, "Direct care excludes inactive sites and mismatched ZIPs")
        var dental = clinic; dental["SITE_NM"] = "Synthetic Family Dentistry"
        var mobileDental = clinic; mobileDental["SITE_NM"] = "Synthetic mobile DENTAL unit"
        check(NativeCareDirectory.clinics(["features": [["attributes": dental], ["attributes": mobileDental], ["attributes": clinic]]], zip: "94303", now: "test").map(\.name) == ["SYNTHETIC CLINIC"], "Heart-care search excludes explicitly dental sites")
        if CommandLine.arguments.contains("--live") {
            let reply = await NativeCareDirectory().search(zip: "94303", specialty: "family_medicine", affordable: true)
            let count = reply.results["search_affordable_clinics"]?.items?.count ?? 0
            check(count > 0 && reply.model.mode == "native_directories", "Live iPhone directory code works without the care server or a scan")
            let report: [String: Any] = ["checked_at": ISO8601DateFormatter().string(from: Date()), "zip": "94303", "source": "HRSA", "listings": count, "mode": reply.model.mode, "summary_sent": false]
            try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: "HeartEcho/Docs/native-directories-live.json"))
        }
        print("\(failures) failure(s). Contract/input checks; no patient data.")
        if failures > 0 { exit(1) }
    }
}
