import Foundation

/// Presentation of existing capture feedback, not another signal-quality model.
/// This never creates, changes or saves a BPM estimate.
struct RecordingGuidance: Equatable {
    enum Phase { case starting, recording, analyzing, preview }
    enum State { case starting, listening, quiet, clipping, contact, background, refreshing, waiting, detected, analyzing, preview }

    let state: State
    let title: String
    let detail: String
    let symbol: String
    let bpm: Double?

    static func assess(phase: Phase, seconds: Double, level: Double, clippingFraction: Double,
                       bpm: Double?, reason: String?) -> RecordingGuidance {
        func guidance(_ state: State, _ title: String, _ detail: String, _ symbol: String,
                      bpm: Double? = nil) -> RecordingGuidance {
            .init(state: state, title: title, detail: detail, symbol: symbol, bpm: bpm)
        }
        switch phase {
        case .starting:
            return guidance(.starting, "Starting the microphone", "Keep the bottom microphone uncovered and hold the phone gently against bare chest skin.", "mic.fill")
        case .analyzing:
            return guidance(.analyzing, "Analyzing your recording", "The microphone has stopped. Heart rate and murmur analysis are separate; your result opens when analysis finishes.", "waveform")
        case .preview:
            return guidance(.preview, "Recording guide preview", "The microphone is off. During a recording, this card explains the phone’s measured sound feedback.", "iphone")
        case .recording: break
        }

        // Match the existing engine's startup grace and warning thresholds.
        // A warning always takes priority over an old numeric estimate.
        guard seconds.isFinite, seconds >= 6 else {
            return guidance(.listening, "Listening for clear beats", "Keep still while the phone collects enough sound. The recording will stop automatically.", "waveform")
        }
        if clippingFraction.isFinite && clippingFraction > 0.01 {
            return guidance(.clipping, "Ease pressure on the microphone", "Avoid rubbing the phone against your skin or clothing. Keep its microphone opening uncovered.", "hand.raised.fill")
        }
        if (level.isFinite && level < -85) || reason == "signal_too_quiet" {
            return guidance(.quiet, "Try a nearby chest position", "Remove the case. Rest the bottom microphone gently against bare chest skin and keep your fingers clear of it.", "iphone")
        }
        if reason == "inconsistent_or_old_cycles" || reason?.contains("stale") == true {
            return guidance(.refreshing, "Waiting for a fresh beat pattern", "Keep the phone still while it checks the latest sound. The recording is continuing.", "clock.arrow.circlepath")
        }
        if reason == "contact_noise" {
            return guidance(.contact, "Keep the phone still", "Movement or rubbing is interrupting the sound. Rest your arms and hold this position gently.", "hand.raised.fill")
        }
        if reason == "model_detected_noise" {
            return guidance(.background, "Reduce nearby sound", "Move away from conversations, music or fans and keep the phone steady.", "speaker.slash.fill")
        }
        if let bpm, bpm.isFinite, (20...300).contains(bpm), level.isFinite, clippingFraction.isFinite {
            return guidance(.detected, "Timing detected · keep still", "An experimental heart-rate estimate is available. Hold this position until the recording ends.", "waveform", bpm: bpm)
        }
        return guidance(.waiting, "Heart rate isn’t ready yet", "Keep still in a quiet room. The sound recording is continuing; BPM and murmur analysis are separate.", "waveform")
    }
}
