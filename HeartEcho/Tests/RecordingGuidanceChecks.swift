import Foundation

@main struct RecordingGuidanceChecks {
    static func main() {
        var failures = 0
        func check(_ ok: Bool, _ description: String) {
            print("\(ok ? "PASS" : "FAIL"): \(description)")
            if !ok { failures += 1 }
        }
        func assess(_ seconds: Double = 8, level: Double = -40, clipping: Double = 0,
                    bpm: Double? = nil, reason: String? = nil,
                    phase: RecordingGuidance.Phase = .recording) -> RecordingGuidance {
            RecordingGuidance.assess(phase: phase, seconds: seconds, level: level,
                clippingFraction: clipping, bpm: bpm, reason: reason)
        }

        let startup = assess(3, level: -120, reason: "signal_too_quiet")
        check(startup.state == .listening && startup.bpm == nil, "Startup grace does not mistake initial silence for a failed recording")
        let quiet = assess(level: -90, bpm: 72, reason: "accepted")
        check(quiet.state == .quiet && quiet.bpm == nil, "Quiet-input guidance takes priority over an old BPM")
        let clipped = assess(level: -90, clipping: 0.02, bpm: 72, reason: "accepted")
        check(clipped.state == .clipping && clipped.bpm == nil, "Clipping takes priority over quiet input and an old BPM")
        check(assess(clipping: 0.01, bpm: 72).state == .detected, "The existing one-percent clipping boundary is preserved")
        check(assess(level: -85, bpm: 72).state == .detected, "The existing quiet-level boundary is preserved")
        check(assess(bpm: 72, reason: "contact_noise").state == .contact, "Contact noise gives one movement instruction")
        check(assess(bpm: 72, reason: "model_detected_noise").state == .background, "Model noise feedback does not display an old BPM")
        let stale = assess(bpm: 72, reason: "inconsistent_or_old_cycles")
        check(stale.state == .refreshing && stale.bpm == nil, "The engine's old-cycle rejection cannot become timing detected")
        let waiting = assess(reason: "counters_disagree")
        check(waiting.state == .waiting && waiting.detail.contains("recording is continuing"), "Missing BPM explains that capture continues")
        check(waiting.detail.contains("separate"), "Missing BPM does not imply that murmur analysis has failed")
        let accepted = assess(bpm: 72, reason: "accepted")
        check(accepted.state == .detected && accepted.bpm == 72, "A current accepted estimate keeps its actual BPM")
        for bpm in [Double.nan, .infinity, -1, 301] {
            check(assess(bpm: bpm).state == .waiting, "Invalid BPM cannot appear as timing detected: \(bpm)")
        }
        check(assess(level: .nan, bpm: 72).state == .waiting, "Invalid level cannot imply timing detected")
        let analyzing = assess(bpm: 72, reason: "accepted", phase: .analyzing)
        check(analyzing.state == .analyzing && analyzing.bpm == nil, "Analysis hides live capture measurements")
        let starting = assess(bpm: 72, phase: .starting)
        check(starting.state == .starting && starting.bpm == nil, "Starting the microphone does not reuse a prior estimate")
        let preview = assess(bpm: 72, phase: .preview)
        check(preview.state == .preview && preview.bpm == nil && preview.detail.contains("microphone is off"), "Design preview does not claim to be recording")
        print("\(failures) failure(s). Presentation checks, not signal or clinical validation.")
        if failures > 0 { exit(1) }
    }
}
