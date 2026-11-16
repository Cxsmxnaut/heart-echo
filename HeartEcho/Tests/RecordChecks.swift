import Foundation

@main struct RecordChecks {
    static func main() throws {
        var failures = 0
        func check(_ ok: Bool, _ message: String) { print("\(ok ? "PASS" : "FAIL"): \(message)"); if !ok { failures += 1 } }
        for (finding, text) in [(MurmurFinding.present, "murmur-like sound pattern"), (.absent, "not detected"), (.unsure, "could not give a clear result")] {
            let reading = MurmurReading(finding: finding, probabilities: finding == .present ? [0,1,0] : finding == .absent ? [1,0,0] : [0,0,1], windows: 5, seconds: 20)
            let value = HeartRecording(title: "Saved test", source: "Imported recording", seconds: 20, bpm: nil, signalStatus: "BPM unavailable", murmur: reading)
            let restored = try JSONDecoder().decode(HeartRecording.self, from: JSONEncoder().encode([value]).dropFirst(0).withUnsafeBytes { _ in try JSONEncoder().encode(value) })
            check(restored.id == value.id && restored.murmur?.finding == finding && restored.bpm == nil, "History preserves \(finding.rawValue) independently of missing BPM")
            check(ScreeningResult(recording: restored).explanation.contains(text), "\(finding.rawValue) has its own truthful explanation")
            let expectedTitle = finding == .present ? "Murmur-like pattern" : finding == .absent ? "No murmur detected" : "Uncertain"
            check(ScreeningResult(recording: restored).resultTitle == expectedTitle, "\(finding.rawValue) has the correct result screen title")
            let summary = ScreeningResult(recording: restored).shareSummary
            check(summary.contains("Finding: " + restored.finding) && summary.contains(text), "Shared \(finding.rawValue) preserves the actual result and explanation")
            check(summary.contains("Estimated heart rate: Not measured for imported audio") && !summary.contains("72 BPM"), "Shared \(finding.rawValue) does not invent a BPM for an import")
        }
        var failed = HeartRecording(title: "Failure", source: "iPhone microphone", seconds: 0, bpm: nil, signalStatus: "Unavailable", murmur: nil)
        failed.error = "Microphone interrupted"
        check(ScreeningResult(recording: failed).explanation.contains("No murmur result was produced"), "Capture failure is not a negative murmur result")
        check(ScreeningResult(recording: failed).resultTitle == "Analysis unavailable", "An analysis failure is not displayed as a murmur result")
        let reading = MurmurReading(finding: .absent, probabilities: [1,0,0], windows: 5, seconds: 20)
        var poor = HeartRecording(title: "Poor signal", source: "iPhone microphone", seconds: 20, bpm: nil, signalStatus: "Unavailable", murmur: reading)
        poor.audioAssessment = AudioAssessment(issue: "too_quiet", detail: "The audio was too quiet.")
        check(ScreeningResult(recording: poor).resultTitle == "Uncertain", "Poor audio cannot be shown as a definite negative")
        let poorSummary = ScreeningResult(recording: poor).shareSummary
        check(poorSummary.contains("Finding: Unsure") && !poorSummary.contains("Finding: Not detected"), "Shared poor audio keeps the effective unsure outcome instead of the raw negative")
        check(poorSummary.contains("silent or too quiet") && poorSummary.contains("does not establish whether a murmur is present or absent"), "Shared poor audio explains the actual quality limitation")

        failed.murmur = reading
        failed.error = "/private/var/mobile/PRIVATE_FAILURE/recording.wav could not be read"
        let failedSummary = ScreeningResult(recording: failed).shareSummary
        check(failedSummary.contains("Finding: Analysis unavailable") && failedSummary.contains("No murmur result was produced"), "Shared analysis failure cannot become a negative result")
        check(!failedSummary.contains("/private") && !failedSummary.contains("PRIVATE_FAILURE") && !failedSummary.contains("recording.wav"), "Shared failure omits raw errors and private file paths")

        var measured = HeartRecording(title: "PRIVATE_TITLE INSURANCE_SENTINEL", source: "iPhone microphone", seconds: 20, bpm: 73, bpmWindows: 12, signalStatus: "PRIVATE_SIGNAL_STATUS", murmur: reading)
        measured.created = Date(timeIntervalSince1970: 1_700_000_000)
        measured.modelRevision = "Checked M · 2026-11-15"
        measured.audioAssessment = AudioAssessment(issue: nil, detail: "PRIVATE_ASSESSMENT_DETAIL")
        measured.audioFile = "/private/RAW_AUDIO_SENTINEL.wav"
        measured.diagnosticAudio = "Audio/DIAGNOSTIC_SENTINEL.wav"
        measured.reference = "PRIVATE_REFERENCE INSURANCE_SENTINEL"
        let measuredSummary = ScreeningResult(recording: measured).shareSummary
        check(measuredSummary.contains("73 BPM (experimental)") && measuredSummary.contains("Accepted microphone BPM updates: 12"), "Shared summary includes the actual accepted BPM and update count")
        check(measuredSummary.contains("Analyzed duration: 20 seconds") && measuredSummary.contains("Analyzed audio windows: 5"), "Shared summary retains measured duration and analyzed window count")
        check(measuredSummary.contains("Saved: ") && measuredSummary.contains("2023") && measuredSummary.contains("Source: iPhone microphone") && measuredSummary.contains(measured.modelRevision), "Shared summary retains the saved date, source and model revision")
        var imported = measured
        imported.source = "Imported recording"
        let importedSummary = ScreeningResult(recording: imported).shareSummary
        check(importedSummary.contains("Saved: ") && !importedSummary.contains("Recorded: ") && !importedSummary.contains("Captured: "), "Imported audio labels the result's saved timestamp without inventing an original recording time")
        check(measuredSummary.contains("prototype") && measuredSummary.contains("not medical advice") && measuredSummary.contains("No audio"), "Shared summary carries its limits and text-only scope")
        for privateValue in [measured.id.uuidString, "PRIVATE_TITLE", "INSURANCE_SENTINEL", "RAW_AUDIO_SENTINEL", "DIAGNOSTIC_SENTINEL", "PRIVATE_REFERENCE", "PRIVATE_SIGNAL_STATUS", "PRIVATE_ASSESSMENT_DETAIL", "/private"] {
            check(!measuredSummary.contains(privateValue), "Shared summary excludes private metadata: \(privateValue == measured.id.uuidString ? "recording identifier" : privateValue)")
        }
        var example = HeartRecording(title: "Public present sample", source: "Public CirCor recording", seconds: 20, bpm: nil, signalStatus: "BPM unavailable", murmur: MurmurReading(finding: .unsure, probabilities: [0.4,0.3,0.3], windows: 5, seconds: 20), publicSample: "present", reference: "Murmur annotated")
        let exampleSummary = ScreeningResult(recording: example).shareSummary
        check(exampleSummary.contains("Finding: Unsure") && exampleSummary.contains("Dataset reference: Murmur annotated") && exampleSummary.contains("separate from the model finding"), "Public reference and model finding stay distinct in the shared summary")
        check(exampleSummary.contains("not a recording of your heart") && exampleSummary.contains("Not measured for public examples"), "Shared public examples remain examples without a microphone BPM")
        example.source = "Design preview"; example.publicSample = nil; example.reference = nil; example.bpm = 72
        check(ScreeningResult(recording: example).shareSummary.contains("Preview only — not a measurement"), "Design preview values are not exported as measured BPM")
        measured.bpm = .nan; measured.seconds = .infinity; measured.modelRevision = "/private/MODEL_SENTINEL"
        let invalidSummary = ScreeningResult(recording: measured).shareSummary
        check(invalidSummary.contains("Estimated heart rate: Unavailable") && invalidSummary.contains("Analyzed duration: Unavailable"), "Nonfinite saved values are unavailable instead of formatted as measurements")
        check(!invalidSummary.contains("MODEL_SENTINEL"), "An invalid model revision cannot leak a private path")
        measured.source = "/private/SOURCE_SENTINEL.wav"
        check(!ScreeningResult(recording: measured).shareSummary.contains("SOURCE_SENTINEL"), "Unknown source strings cannot leak an imported filename")
        let url = URL(fileURLWithPath: "/tmp/owned-capture.wav")
        check(CaptureArtifact(url: url, samples: 960000, sampleRate: 48000, error: nil).complete, "Complete 20-second capture is accepted")
        check(!CaptureArtifact(url: url, samples: 240000, sampleRate: 48000, error: nil).complete, "Partial five-second capture cannot masquerade as a full recording")
        check(!CaptureArtifact(url: url, samples: 960000, sampleRate: 48000, error: "Disk write failed").complete, "A write error rejects capture even with enough samples")
        for rate in [0.0, -.infinity, .nan, .infinity] {
            check(!CaptureArtifact(url: url, samples: 960000, sampleRate: rate, error: nil).complete, "Invalid sample rate is rejected: \(rate)")
        }
        print("\(failures) failure(s). Data-flow checks, not phone or clinical validation.")
        if failures > 0 { exit(1) }
    }
}
