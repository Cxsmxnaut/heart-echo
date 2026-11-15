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
}

