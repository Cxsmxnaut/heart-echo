import Foundation

struct HeartRecording: Codable, Identifiable {
    var id = UUID()
    var created = Date()
    var title: String
    var source: String
    var seconds: Double
    var bpm: Double?
    var bpmWindows = 0
    var signalStatus: String
    var murmur: MurmurReading?
    var error: String?
    var audioAssessment: AudioAssessment?
    var waveform: [Float] = []
    var audioFile: String?
    var diagnosticAudio: String?
    var publicSample: String?
    var reference: String?
    var modelRevision = "Phase-aware M · 2026-11-14"
    var date: String { created.formatted(date: .abbreviated, time: .shortened) }
    var isExample: Bool { publicSample != nil || source == "Design preview" }
    var effectiveMurmurFinding: MurmurFinding? {
        guard error == nil, let murmur else { return nil }
        return audioAssessment?.issue == nil ? murmur.finding : .unsure
    }
    var finding: String {
        switch effectiveMurmurFinding {
        case .present: return "Murmur-like pattern"
        case .absent: return "Not detected in this recording"
        case .unsure: return "Unsure"
        case nil: return "Analysis unavailable"
        }
    }
}

struct ScreeningResult {
    let recording: HeartRecording
    var finding: String? { recording.murmur?.title }
    var resultTitle: String {
        switch recording.effectiveMurmurFinding {
        case .present: return "Murmur-like pattern"
        case .absent: return "No murmur detected"
        case .unsure: return "Uncertain"
        case nil: return "Analysis unavailable"
        }
    }
    var explanation: String {
        if let error = recording.error { return "Analysis could not finish: \(error). No murmur result was produced." }
        if let assessment = recording.audioAssessment, assessment.issue != nil { return "The model could not give a clear result. " + assessment.detail + " This does not establish whether a murmur is present or absent." }
        switch recording.murmur?.finding {
        case .present: return "The on-device model found a murmur-like sound pattern. It cannot identify its cause or severity."
        case .absent: return "A murmur was not detected in this recording. This does not rule out a murmur elsewhere or heart disease."
        default: return "The model could not give a clear result. This does not tell you whether a murmur is present or absent."
        }
    }

    /// Text exported only when the user opens the system share sheet. Titles,
    /// filenames, raw error text and internal identifiers deliberately stay out.
    var shareSummary: String {
        let date = recording.created.formatted(.dateTime.year().month().day().hour().minute().timeZone(.genericName(.short)))
        let duration = recording.seconds.isFinite && recording.seconds >= 0
            ? recording.seconds.formatted(.number.precision(.fractionLength(0...1))) + " seconds"
            : "Unavailable"
        var lines = [
            "Heart Echo — Recording Summary",
            "Experimental prototype · not medical advice",
            "",
            "Finding: " + recording.finding,
            sharedExplanation,
            "",
            "Saved: " + date,
            "Source: " + sharedSource,
            "Analyzed duration: " + duration,
            "Estimated heart rate: " + sharedHeartRate
        ]
        if recording.source == "iPhone microphone", let bpm = recording.bpm, bpm.isFinite, bpm > 0, recording.bpmWindows > 0 {
            lines.append("Accepted microphone BPM updates: \(recording.bpmWindows)")
        }
        if recording.error == nil, let murmur = recording.murmur, murmur.windows >= 0 {
            lines.append("Analyzed audio windows: \(murmur.windows)")
        } else {
            lines.append("Analyzed audio windows: Unavailable")
        }
        lines.append("Audio checks: " + sharedAudioChecks)
        lines.append("Model revision: " + sharedModelRevision)
        if recording.isExample {
            lines.append("Example only — not a recording of your heart.")
            if recording.publicSample != nil, let reference = recording.reference,
               ["Murmur annotated", "No murmur annotated", "Uncertain annotation"].contains(reference) {
                lines.append("Dataset reference: " + reference + ". This is separate from the model finding.")
            }
        }
        lines += ["", "Heart Echo can be wrong. An unsure or unavailable result is not a negative result. An absent finding does not rule out heart disease.",
                  "Text summary only. No audio or private file information is attached."]
        return lines.joined(separator: "\n")
    }

    private var sharedExplanation: String {
        if recording.error != nil { return "Analysis could not finish. No murmur result was produced." }
        if recording.audioAssessment?.issue != nil {
            return "The model could not give a clear result because of the audio checks. This does not establish whether a murmur is present or absent."
        }
        return explanation
    }

    private var sharedSource: String {
        if recording.publicSample != nil { return "Public CirCor recording" }
        switch recording.source {
        case "iPhone microphone", "Imported recording", "Public CirCor recording": return recording.source
        case "Design preview": return "Design preview (illustrative only)"
        default: return "Saved recording (source not available)"
        }
    }

    private var sharedHeartRate: String {
        if recording.source == "Design preview" { return "Preview only — not a measurement" }
        if recording.publicSample != nil { return "Not measured for public examples" }
        if recording.source == "Imported recording" { return "Not measured for imported audio" }
        guard let bpm = recording.bpm, bpm.isFinite, bpm > 0 else { return "Unavailable — no accepted microphone estimate" }
        return String(format: "%.0f BPM (experimental)", bpm)
    }

    private var sharedAudioChecks: String {
        guard let assessment = recording.audioAssessment else { return "Not saved for this recording" }
        switch assessment.issue {
        case nil: return "Basic length, volume and distortion checks passed. This does not establish murmur audibility."
        case "too_short": return "The recording was too short for the model."
        case "invalid_audio": return "The recording contained invalid audio values."
        case "too_quiet": return "The recording was silent or too quiet for the model."
        case "clipped": return "The recording was distorted by clipping."
        default: return "The recording did not pass the available audio checks."
        }
    }

    private var sharedModelRevision: String {
        let value = recording.modelRevision.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.count <= 120,
              !value.contains("/"), !value.contains("\\"), !value.contains("\n"), !value.contains("\r") else { return "Unavailable" }
        return value
    }
}

