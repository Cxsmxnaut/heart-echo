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
        }
        var failed = HeartRecording(title: "Failure", source: "iPhone microphone", seconds: 0, bpm: nil, signalStatus: "Unavailable", murmur: nil)
        failed.error = "Microphone interrupted"
        check(ScreeningResult(recording: failed).explanation.contains("No murmur result was produced"), "Capture failure is not a negative murmur result")
        check(ScreeningResult(recording: failed).resultTitle == "Analysis unavailable", "An analysis failure is not displayed as a murmur result")
        let reading = MurmurReading(finding: .absent, probabilities: [1,0,0], windows: 5, seconds: 20)
        var poor = HeartRecording(title: "Poor signal", source: "iPhone microphone", seconds: 20, bpm: nil, signalStatus: "Unavailable", murmur: reading)
        poor.audioAssessment = AudioAssessment(issue: "too_quiet", detail: "The audio was too quiet.")
        check(ScreeningResult(recording: poor).resultTitle == "Uncertain", "Poor audio cannot be shown as a definite negative")
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
