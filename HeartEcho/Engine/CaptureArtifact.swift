import Foundation

struct CaptureArtifact {
    let url: URL
    let samples: Int
    let sampleRate: Double
    let error: String?
    var complete: Bool { error == nil && samples > 0 && sampleRate.isFinite && (19...22).contains(seconds) }
    var seconds: Double { sampleRate > 0 ? Double(samples) / sampleRate : 0 }
}

