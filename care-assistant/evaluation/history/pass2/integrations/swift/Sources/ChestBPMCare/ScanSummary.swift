import Foundation

public enum CareScanQuality: String, Codable, Sendable { case usable, unclear, unavailable }
public struct CareTimingCounters: Codable, Sendable {
    public let pattern_bpm: Double?
    public let cycle_bpm: Double?
}
public struct CareScanSummary: Codable, Sendable {
    public let schema_version: String
    public let measurement: String
    public let quality: CareScanQuality
    public let estimated_bpm: Double?
    public let analysis_window_seconds: Double?
    public let captured_at: String?
    public let synthetic: Bool
    public let timing_counters: CareTimingCounters?

    // JSONEncoder normally omits nil. The contract requires estimated_bpm:null.
    enum CodingKeys: String, CodingKey { case schema_version, measurement, quality, estimated_bpm, analysis_window_seconds, captured_at, synthetic, timing_counters }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(schema_version, forKey: .schema_version); try c.encode(measurement, forKey: .measurement)
        try c.encode(quality, forKey: .quality); try c.encode(estimated_bpm, forKey: .estimated_bpm)
        try c.encodeIfPresent(analysis_window_seconds, forKey: .analysis_window_seconds); try c.encodeIfPresent(captured_at, forKey: .captured_at)
        try c.encode(synthetic, forKey: .synthetic); try c.encodeIfPresent(timing_counters, forKey: .timing_counters)
    }
}

/// Values copied once from the displayed estimate when the user opens the sheet.
/// Does not read files, microphone, Watch, HealthKit, study state, or diagnostics.
public struct ChestBPMCareSnapshot: Sendable {
    public let acceptedBPM: Double?
    public let patternBPM: Double?
    public let cycleBPM: Double?
    public let analysisWindowSeconds: Double?
    public let capturedAt: Date?
    public init(acceptedBPM: Double?, patternBPM: Double? = nil, cycleBPM: Double? = nil, analysisWindowSeconds: Double? = nil, capturedAt: Date? = nil) {
        self.acceptedBPM = acceptedBPM; self.patternBPM = patternBPM; self.cycleBPM = cycleBPM
        self.analysisWindowSeconds = analysisWindowSeconds; self.capturedAt = capturedAt
    }
    private func validBPM(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (20...300).contains(value) else { return nil }; return value
    }
    public func summary(quality requested: CareScanQuality, synthetic: Bool = false, includeComparisonCounters: Bool = false) -> CareScanSummary {
        // Only the accepted main display is eligible. Counters never rescue nil BPM.
        let accepted = validBPM(acceptedBPM)
        let quality: CareScanQuality = requested == .usable && accepted == nil ? .unclear : requested
        let bpm = quality == .usable ? accepted : nil
        let window = analysisWindowSeconds.flatMap { $0.isFinite && $0 > 0 && $0 <= 30 ? $0 : nil }
        let counters = quality == .usable && includeComparisonCounters ? CareTimingCounters(pattern_bpm: validBPM(patternBPM), cycle_bpm: validBPM(cycleBPM)) : nil
        return CareScanSummary(schema_version: "1.1", measurement: "experimental_heart_sound_timing", quality: quality, estimated_bpm: bpm, analysis_window_seconds: window,
            captured_at: capturedAt.map { ISO8601DateFormatter().string(from: $0) }, synthetic: synthetic, timing_counters: counters)
    }
}
