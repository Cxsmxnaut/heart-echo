import Foundation

struct Biquad {
    private var b0: Double, b1: Double, b2: Double, a1: Double, a2: Double
    private var z1 = 0.0, z2 = 0.0
    init(sampleRate: Double, cutoff: Double, highPass: Bool = false) {
        let w = 2 * Double.pi * cutoff / sampleRate, c = cos(w), a = sin(w) / sqrt(2), d = 1 + a
        b0 = (highPass ? 1 + c : 1 - c) / 2 / d; b1 = (highPass ? -(1 + c) : 1 - c) / d
        b2 = b0; a1 = -2 * c / d; a2 = (1 - a) / d
    }
    mutating func process(_ x: Double) -> Double {
        let y = b0 * x + z1; z1 = b1 * x - a1 * y + z2; z2 = b2 * x - a2 * y
        return y
    }
}

func median(_ values: [Double]) -> Double {
    let a = values.sorted(), n = values.count
    return n == 0 ? 0 : (a[(n - 1) / 2] + a[n / 2]) / 2
}
func correlation(_ x: [Double], lag: Int, range: Range<Int>? = nil) -> Double {
    let r = range ?? x.indices
    guard r.count > lag else { return 0 }
    var product = 0.0, left = 0.0, right = 0.0
    for i in r.lowerBound + lag..<r.upperBound {
        let a = x[i], b = x[i - lag]; product += a * b; left += a * a; right += b * b
    }
    return product / max(sqrt(left * right), 1e-15)
}

/// Original algorithm, unchanged mathematically; retained for paired comparisons.
struct PeriodDiagnostics: Codable, Sendable {
    var reason = "warming_up"
    var mean: Double?, variance: Double?, selectedLag: Int?, rawBPM: Double?
    var peaks: [Int] = [], scores: [Double] = [], halfScores: [Double] = []
}
struct CycleDiagnostics: Codable, Sendable {
    var reason = "warming_up"
    var floor: Double?, top: Double?, threshold: Double?, period: Double?, jitter: Double?, coverage: Double?, regularShare: Double?
    var distinct: Bool?, amplitudeA: Double?, amplitudeB: Double?, timbreA: Double?, timbreB: Double?
    var peaks: [Int] = [], gaps: [Double] = []
}
struct SignalDiagnostics: Codable, Sendable {
    var totalSamples = 0, updateSamples = 0, clippedSamples = 0
    var clippingFraction = 0.0, rawRMS = 0.0, filteredRMS = 0.0, rawPeak = 0.0
}
struct EstimateDiagnostics: Codable, Sendable {
    var periodicity = PeriodDiagnostics(), cycle = CycleDiagnostics(), signal = SignalDiagnostics()
    var recent: RecentDiagnostics?, source = "none"
    var enhanced: RobustDiagnostics?, legacyBPM: Double?
    var envelope: [Double]?, brightness: [Double]?
}
struct Periodicity {
    var smoothed: Double?
    var diagnostics = PeriodDiagnostics()
    mutating func estimate(_ envelope: [Double]) -> (Double?, Double) {
        diagnostics = PeriodDiagnostics()
        guard envelope.count >= 1200 else { return (nil, 0) }
        func absent() -> (Double?, Double) { (nil, 0) }
        let mean = envelope.reduce(0, +) / Double(envelope.count)
        diagnostics.mean = mean
        guard mean > 0.000015 else { diagnostics.reason = "signal_too_quiet"; smoothed = nil; return absent() }
        var prefix = [0.0]
        for value in envelope { prefix.append(prefix.last! + value) }
        var x = envelope.indices.map { i -> Double in
            let a = max(0, i - 100), b = min(envelope.count, i + 101)
            return envelope[i] - (prefix[b] - prefix[a]) / Double(b - a)
        }
        let variance = x.reduce(0) { $0 + $1 * $1 } / Double(x.count)
        diagnostics.variance = variance
        guard variance > 1e-12 else { diagnostics.reason = "no_envelope_variation"; smoothed = nil; return absent() }
        let cap = sqrt(variance) * 3
        x = x.map { max(-cap, min(cap, $0)) }
        var scores = [Double](repeating: 0, count: 301)
        for lag in 66...300 { scores[lag] = correlation(x, lag: lag) }
        let peaks = (67..<300).filter { scores[$0] > scores[$0 - 1] && scores[$0] >= scores[$0 + 1] }
        diagnostics.peaks = peaks; diagnostics.scores = scores
        guard let best = peaks.max(by: { scores[$0] < scores[$1] }), scores[best] >= 0.55 else {
            diagnostics.reason = "weak_autocorrelation"; smoothed = nil; return absent()
        }
        let lag = peaks.first { scores[$0] >= max(0.55, scores[best] * 0.92) } ?? best
        diagnostics.selectedLag = lag
        diagnostics.halfScores = [0..<x.count / 2, x.count / 2..<x.count].map { correlation(x, lag: lag, range: $0) }
        guard diagnostics.halfScores.allSatisfy({ $0 > 0.35 }) else {
            diagnostics.reason = "inconsistent_window_halves"; smoothed = nil; return absent()
        }
        let a = scores[lag - 1], b = scores[lag], c = scores[lag + 1], d = a - 2 * b + c
        let offset = abs(d) > 1e-9 ? max(-0.5, min(0.5, 0.5 * (a - c) / d)) : 0
        let bpm = 12000 / (Double(lag) + offset)
        smoothed = smoothed.map { abs($0 - bpm) < 15 ? $0 * 0.55 + bpm * 0.45 : bpm } ?? bpm
        diagnostics.rawBPM = bpm; diagnostics.reason = "accepted"
        return (smoothed, scores[lag])
    }
}

struct CycleEstimate {
    var bpm: Double?
    var peaks: [Int] = []
    var diagnostics = CycleDiagnostics()
}

/// Independent alternating-pulse heuristic, not a trained S1/S2 classifier.
func cycleEstimate(_ envelope: [Double], brightness: [Double]) -> CycleEstimate {
    var d = CycleDiagnostics()
    func reject(_ reason: String) -> CycleEstimate { var failed = d; failed.reason = reason; return CycleEstimate(diagnostics: failed) }
    guard envelope.count >= 1200, brightness.count == envelope.count else { return reject("warming_up") }
    let floor = median(envelope), top = envelope.sorted()[envelope.count * 95 / 100]
    let threshold = floor + (top - floor) * 0.28
    d.floor = floor; d.top = top; d.threshold = threshold
    guard top > max(floor * 1.5, 0.00003) else { return reject("low_pulse_contrast") }
    var peaks: [Int] = []
    for i in 1..<envelope.count - 1 where envelope[i] > threshold && envelope[i] > envelope[i - 1] && envelope[i] >= envelope[i + 1] {
        if let last = peaks.last, i - last < 16 {
            if envelope[i] > envelope[last] { peaks[peaks.count - 1] = i }
        } else { peaks.append(i) }
    }
    d.peaks = peaks
    guard peaks.count >= 8 else { return reject("fewer_than_eight_sounds") }
    let gaps = zip(peaks, peaks.dropFirst()).map { Double($1 - $0) }
    let even = stride(from: 0, to: gaps.count, by: 2).map { gaps[$0] }
    let odd = stride(from: 1, to: gaps.count, by: 2).map { gaps[$0] }
    let a = median(even), b = median(odd), period = a + b
    let periods = zip(peaks, peaks.dropFirst(2)).map { Double($1 - $0) }
    let duration = median(periods), jitter = median(periods.map { abs($0 - duration) }) / max(duration, 1)
    let amplitudeA = median(stride(from: 0, to: peaks.count, by: 2).map { envelope[peaks[$0]] })
    let amplitudeB = median(stride(from: 1, to: peaks.count, by: 2).map { envelope[peaks[$0]] })
    let timbreA = median(stride(from: 0, to: peaks.count, by: 2).map { brightness[peaks[$0]] })
    let timbreB = median(stride(from: 1, to: peaks.count, by: 2).map { brightness[peaks[$0]] })
    // Identical evenly spaced sounds cannot establish whether each is a beat or half a beat.
    let distinct = abs(a - b) / max(period, 1) > 0.12 || abs(timbreA - timbreB) > 0.12 ||
        max(amplitudeA, amplitudeB) / max(min(amplitudeA, amplitudeB), 1e-12) > 1.3
    d.gaps = gaps; d.period = duration; d.jitter = jitter; d.distinct = distinct
    d.amplitudeA = amplitudeA; d.amplitudeB = amplitudeB; d.timbreA = timbreA; d.timbreB = timbreB
    let good = periods.filter { abs($0 - duration) / duration < 0.18 }.count
    d.regularShare = Double(good) / Double(periods.count)
    d.coverage = Double(peaks.last! - peaks.first!) / Double(envelope.count)
    guard distinct else { return reject("ambiguous_sound_types") }
    guard (12000.0 / 180...300).contains(duration) else { return reject("cycle_rate_out_of_range") }
    guard jitter < 0.12 else { return reject("cycle_jitter") }
    guard good * 5 >= periods.count * 4 else { return reject("irregular_cycle_intervals") }
    guard gaps.allSatisfy({ $0 >= 16 && $0 < duration * 0.88 }) else { return reject("implausible_sound_gaps") }
    guard d.coverage! > 0.65 else { return reject("insufficient_window_coverage") }
    d.reason = "accepted"
    return CycleEstimate(bpm: 12000 / duration, peaks: peaks, diagnostics: d)
}

struct HeartRateEstimate: Encodable, Sendable {
    var bpm: Double?, original: Double?, cycle: Double?
    var periodicity = 0.0, seconds = 0.0, level: Double = -120
    var waveform: [Float] = [], marks: [Int] = [], audio: [Float] = []
    var status = "Ready when you are"
    var analysisAge = 0.0
    var diagnostics = EstimateDiagnostics()
    enum CodingKeys: String, CodingKey { case bpm, original, cycle, periodicity, seconds, level, waveform, marks, status, diagnostics, analysisAge }
}

func agreement(_ original: Double?, _ cycle: Double?) -> Double? {
    guard let a = original, let b = cycle, abs(a - b) <= max(5, b * 0.06) else { return nil }
    return a // Keep the original's finer timing; the cycle count is an independent check.
}

struct RecentDiagnostics: Codable, Sendable {
    var bpm: Double?, patternBPM: Double?, cycleBPM: Double?
    var periodicity = PeriodDiagnostics(), cycle = CycleDiagnostics()
    var confirmed = false
}

/// Same acceptance rules on the newest six seconds; no held or Watch-derived rate.
struct RecentCounter {
    private var pattern = Periodicity(), previous: Double?
    mutating func estimate(_ envelope: [Double], brightness: [Double]) -> RecentDiagnostics {
        let (bpm, _) = pattern.estimate(Array(envelope.suffix(1200)))
        let cycle = cycleEstimate(Array(envelope.suffix(1200)), brightness: Array(brightness.suffix(1200)))
        let value = agreement(bpm, cycle.bpm)
        let result = RecentDiagnostics(bpm: value, patternBPM: bpm, cycleBPM: cycle.bpm,
            periodicity: pattern.diagnostics, cycle: cycle.diagnostics, confirmed: agreement(value, previous) != nil)
        previous = value
        return result
    }
}

func selectPattern(_ original: Double?, _ cycle: Double?, recent: RecentDiagnostics) -> (bpm: Double?, source: String) {
    if let bpm = agreement(original, cycle) { return (bpm, "full_window") }
    // A shorter window cannot override an explicit disagreement or a valid conflicting counter.
    guard !(original != nil && cycle != nil), recent.confirmed, let bpm = recent.bpm,
          original == nil || agreement(original, bpm) != nil,
          cycle == nil || agreement(cycle, bpm) != nil else { return (nil, "none") }
    return (bpm, "recent_window")
}

struct HeartRateEstimator {
    private let rate: Double
    private var high: Biquad, low: Biquad, bright: Biquad, smooth = Biquad(sampleRate: 200, cutoff: 8)
    private var count = 0, energyCount = 0, clipCount = 0, blockCount = 0
    private var nextEnvelope = 0.0, nextAudio = 0.0, energy = 0.0, highEnergy = 0.0
    private var envelope: [Double] = [], brightness: [Double] = [], audio: [Float] = []
    private var original = Periodicity()
    private var recent = RecentCounter()
    private var enhanced: HeartSoundPipeline?
    private var rawEnergy = 0.0, filteredEnergy = 0.0, rawPeak = 0.0
    init(sampleRate: Double, models: HeartSoundModels? = nil, denoiserEnabled: Bool = false) {
        rate = sampleRate; high = Biquad(sampleRate: sampleRate, cutoff: 25, highPass: true)
        low = Biquad(sampleRate: sampleRate, cutoff: 160); bright = Biquad(sampleRate: sampleRate, cutoff: 85, highPass: true)
        if let models { enhanced = HeartSoundPipeline(rate: sampleRate, models: models, denoiserEnabled: denoiserEnabled, adaptiveTiming: true) }
    }
    mutating func append(_ samples: [Float], motion: Double = 0) {
        enhanced?.append(samples, motion: motion)
        for sample in samples {
            let x = low.process(high.process(Double(sample))), h = bright.process(x)
            rawEnergy += Double(sample) * Double(sample); filteredEnergy += x * x; rawPeak = max(rawPeak, abs(Double(sample)))
            energy += x * x; highEnergy += h * h; energyCount += 1; count += 1; blockCount += 1
            if abs(sample) >= 0.98 { clipCount += 1 }
            if Double(count) >= nextAudio { audio.append(Float(x)); nextAudio += rate / 4000 }
            if Double(count) >= nextEnvelope {
                envelope.append(max(0, smooth.process(sqrt(energy / Double(energyCount)))))
                brightness.append(highEnergy / max(energy, 1e-20))
                energy = 0; highEnergy = 0; energyCount = 0; nextEnvelope += rate / 200
            }
        }
        if envelope.count > 1600 { brightness.removeFirst(envelope.count - 1600); envelope.removeFirst(envelope.count - 1600) }
        if audio.count > 32000 { audio.removeFirst(audio.count - 32000) }
    }
    mutating func estimate() -> HeartRateEstimate {
        let (baseline, score) = original.estimate(envelope), cycles = cycleEstimate(envelope, brightness: brightness)
        let recent = recent.estimate(envelope, brightness: brightness)
        let selected = selectPattern(baseline, cycles.bpm, recent: recent)
        let marks = selected.source == "recent_window" ? recent.cycle.peaks.map { $0 + max(0, envelope.count - 1200) } : cycles.peaks
        let display = Array(envelope.suffix(600)), scale = max(display.max() ?? 0, 0.00001)
        let clipped = clipCount > blockCount / 100
        let signal = SignalDiagnostics(totalSamples: count, updateSamples: blockCount, clippedSamples: clipCount,
            clippingFraction: Double(clipCount) / Double(max(1, blockCount)), rawRMS: sqrt(rawEnergy / Double(max(1, blockCount))),
            filteredRMS: sqrt(filteredEnergy / Double(max(1, blockCount))), rawPeak: rawPeak)
        clipCount = 0; blockCount = 0; rawEnergy = 0; filteredEnergy = 0; rawPeak = 0
        var result = HeartRateEstimate(bpm: selected.bpm, original: clipped ? nil : baseline, cycle: cycles.bpm,
            periodicity: score, seconds: min(8, Double(envelope.count) / 200),
            level: 20 * log10(max(sqrt(envelope.suffix(200).reduce(0) { $0 + $1 * $1 } / Double(max(1, min(200, envelope.count)))), 1e-9)),
            waveform: stride(from: 0, to: display.count, by: 3).map { Float(display[$0] / scale) },
            marks: marks.filter { $0 >= envelope.count - display.count }.map { ($0 - envelope.count + display.count) / 3 }, audio: audio)
        if result.seconds < 6 { result.status = "Listening… \(Int(ceil(6 - result.seconds))) more seconds" }
        else if clipped { result.bpm = nil; result.status = "Too loud · reduce pressure and avoid rubbing" }
        else if result.level < -85 { result.bpm = nil; result.status = "Very quiet · try another chest position" }
        else if selected.source == "recent_window" { result.status = "Recent 6-second pattern agrees · experimental estimate" }
        else if baseline == nil { result.status = "Unclear pattern · keep still in a quiet room" }
        else if cycles.bpm == nil { result.status = "Unsure · can’t separate the two heart sounds" }
        else if result.bpm == nil { result.status = "Unsure · counters disagree; possible half/double rate" }
        else { result.status = "Counters agree · experimental estimate" }
        result.diagnostics = EstimateDiagnostics(periodicity: original.diagnostics, cycle: cycles.diagnostics,
            signal: signal, recent: recent, source: result.bpm == nil ? "none" : selected.source, envelope: envelope, brightness: brightness)
        result.diagnostics.legacyBPM = result.bpm
        if let enhanced {
            let value = enhanced.estimate()
            result.diagnostics.enhanced = value; result.analysisAge = value.analysisAge
            result.bpm = clipped || result.level < -85 ? nil : value.bpm
            result.diagnostics.source = result.bpm == nil ? "none" : value.method
            let offset = envelope.count - Int(((value.windowSeconds + value.analysisAge) * 200).rounded())
            result.marks = value.peaks.map { $0 * 2 + offset }.filter { $0 >= envelope.count - display.count && $0 < envelope.count }
                .map { ($0 - envelope.count + display.count) / 3 }
            if !clipped && result.level >= -85 {
                if result.seconds < 6 { result.status = "Learning the sound pattern… \(Int(ceil(6 - result.seconds))) more seconds" }
                else if result.bpm != nil { result.status = "Heart-sound model and audio timing agree · experimental" }
                else if value.reason == "contact_noise" { result.status = "Brief contact noise · waiting for clear beats" }
                else if value.reason == "model_detected_noise" { result.status = "Background sound · no confirmed beat pattern" }
                else { result.status = "Unsure · collecting enough clear heart cycles" }
            }
        }
        return result
    }
}

struct WatchPair: Identifiable, Encodable, Sendable {
    let id = UUID(), time: Date
    let original: Double?, improved: Double?
    var watch: Double?
    var watchTime: Date? = nil
    var automatic = false
    var originalTime: Date? = nil
}
struct ComparisonStats {
    let error: Double?, commonError: Double?, largeErrors: Int, missing: Int, common: Int
    init(_ pairs: [WatchPair], improved: Bool) {
        let common = pairs.filter { $0.watch != nil && $0.original != nil && $0.improved != nil }
        func errors(_ pairs: [WatchPair]) -> [Double] {
            pairs.compactMap { pair in
                guard let watch = pair.watch, let value = improved ? pair.improved : pair.original else { return nil }
                return abs(value - Double(watch))
            }
        }
        func average(_ values: [Double]) -> Double? { values.isEmpty ? nil : values.reduce(0, +) / Double(values.count) }
        let errors = errors(pairs)
        self.common = common.count; error = average(errors); commonError = average(common.map { abs((improved ? $0.improved! : $0.original!) - Double($0.watch!)) })
        largeErrors = errors.filter { $0 > 5 }.count
        missing = pairs.filter { (improved ? $0.improved : $0.original) == nil }.count
    }
}
