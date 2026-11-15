import Foundation

struct RobustDiagnostics: Codable, Sendable {
    var reason = "warming_up", method = "classical"
    var warning: String?
    var bpm: Double?, cycleBPM: Double?, patternBPM: Double?
    var correlation = 0.0, rawSupport = 0.0, cleanFraction = 0.0, recentCleanFraction = 0.0
    var windowSeconds = 0.0
    var matchedShare = 0.0, cycleCoverage = 0.0, jitter = 0.0, motion = 0.0, analysisAge = 0.0, denoiseMS = 0.0
    var completeCycles = 0, peaks: [Int] = [], maskedRanges: [[Int]] = []
    var halfScores: [Double] = []
    var envelope: [Double]?, brightness: [Double]?
    var stateProbabilities: [[Double]]?
    var eventSimilarity: Double?, pulseContrast: Double?
}

func maskedCorrelation(_ x: [Double], valid: [Bool], lag: Int, range: Range<Int>? = nil) -> Double {
    let range = range ?? x.indices
    guard range.count > lag else { return 0 }
    var product = 0.0, left = 0.0, right = 0.0, used = 0
    for i in range.lowerBound + lag..<range.upperBound where valid[i] && valid[i - lag] {
        product += x[i] * x[i - lag]; left += x[i] * x[i]; right += x[i - lag] * x[i - lag]; used += 1
    }
    return used >= max(50, (range.count - lag) / 2) ? product / max(sqrt(left * right), 1e-15) : 0
}

func centered(_ envelope: [Double], valid: [Bool], radius: Int = 100) -> [Double] {
    var sum = [0.0], count = [0]
    for i in envelope.indices { sum.append(sum.last! + (valid[i] ? envelope[i] : 0)); count.append(count.last! + (valid[i] ? 1 : 0)) }
    let x = envelope.indices.map { i -> Double in
        let a = max(0, i - radius), b = min(envelope.count, i + radius + 1)
        return valid[i] ? envelope[i] - (sum[b] - sum[a]) / Double(max(1, count[b] - count[a])) : 0
    }
    let scale = max(median(x.enumerated().compactMap { valid[$0.offset] ? abs($0.element) : nil }) * 6, 1e-9)
    return x.map { max(-scale, min(scale, $0)) }
}

private struct SequenceFit {
    var bpm: Double?, score = 0.0, matched = 0.0, coverage = 0.0, jitter = 0.0, complete = 0
    var peaks: [Int] = []
}

/// Fit two repeating sound families in time; extra/missing peaks do not flip every later label.
private func sequenceFit(_ envelope: [Double], brightness: [Double], valid: [Bool]) -> SequenceFit {
    let n = envelope.count
    var threshold = [Double](repeating: .infinity, count: n)
    for base in stride(from: 0, to: n, by: 100) {
        let values = (max(0, base - 100)..<min(n, base + 300)).compactMap { valid[$0] ? envelope[$0] : nil }.sorted()
        guard values.count >= 100 else { continue }
        let floor = values[values.count * 2 / 5], top = values[values.count * 9 / 10]
        guard top > max(floor * 1.5, 0.00003) else { continue }
        for i in base..<min(n, base + 100) { threshold[i] = floor + (top - floor) * 0.32 }
    }
    var peaks: [Int] = []
    for i in 1..<n - 1 where valid[i] && envelope[i] > threshold[i] && envelope[i] > envelope[i - 1] && envelope[i] >= envelope[i + 1] {
        if let previous = peaks.last, i - previous < 16 {
            if envelope[i] > envelope[previous] { peaks[peaks.count - 1] = i }
        } else { peaks.append(i) }
    }
    guard peaks.count >= 8, peaks.count <= 65 else { return SequenceFit(peaks: peaks) }
    var best = SequenceFit(peaks: peaks)
    let amplitudes = peaks.map { envelope[$0] }, scale = max(median(amplitudes), 1e-9)
    for period in stride(from: 67, through: 300, by: 1) {
        let tolerance = max(3, Int(Double(period) * 0.06))
        var histogram = [Double](repeating: 0, count: period)
        for peak in peaks {
            let phase = peak % period, weight = min(2, envelope[peak] / scale)
            for offset in -tolerance...tolerance {
                histogram[(phase + offset + period) % period] += weight * (1 - Double(abs(offset)) / Double(tolerance + 1))
            }
        }
        let a = histogram.indices.max(by: { histogram[$0] < histogram[$1] })!
        func distance(_ a: Int, _ b: Int) -> Int { let d = abs(a - b); return min(d, period - d) }
        guard let b = histogram.indices.filter({ distance($0, a) > max(tolerance * 2, period * 15 / 100) })
            .max(by: { histogram[$0] < histogram[$1] }) else { continue }
        let phases = [a, b].sorted()
        var families = [[Int: Int](), [Int: Int]()]
        for peak in peaks {
            let distances = phases.map { distance(peak % period, $0) }, family = distances[0] <= distances[1] ? 0 : 1
            guard distances[family] <= tolerance else { continue }
            let cycle = Int((Double(peak - phases[family]) / Double(period)).rounded())
            if let old = families[family][cycle], envelope[old] >= envelope[peak] { continue }
            families[family][cycle] = peak
        }
        let first = Int(ceil(-Double(phases[0]) / Double(period))), last = (n - 1 - phases[1]) / period
        guard last >= first else { continue }
        let expected = (first...last).filter { cycle in
            phases.allSatisfy { phase in
                let center = phase + cycle * period, radius = max(3, period / 12)
                return (max(0, center - radius)..<min(n, center + radius + 1)).allSatisfy { valid[$0] }
            }
        }
        guard expected.count >= 3 else { continue }
        let complete = expected.filter { families[0][$0] != nil && families[1][$0] != nil }.count
        let coverage = Double(complete) / Double(expected.count)
        let matched = Double(families[0].count + families[1].count) / Double(peaks.count)
        guard complete >= 3, coverage >= 0.75, matched >= 0.8 else { continue }
        let left = families[0].values.sorted(), right = families[1].values.sorted()
        guard let lastLeft = left.last, let lastRight = right.last,
              n - min(lastLeft, lastRight) < period * 2 else { continue }
        let gap = Double(phases[1] - phases[0]) / Double(period)
        let ampA = median(left.map { envelope[$0] }), ampB = median(right.map { envelope[$0] })
        let timbre = abs(median(left.map { brightness[$0] }) - median(right.map { brightness[$0] }))
        guard abs(gap - 0.5) > 0.06 || timbre > 0.12 || max(ampA, ampB) / max(min(ampA, ampB), 1e-12) > 1.3 else { continue }
        let intervals = [left, right].flatMap { family in
            zip(family, family.dropFirst()).compactMap { start, end -> Double? in
                let gap = end - start
                return abs(Double(gap - period)) / Double(period) < 0.18 && (start...end).allSatisfy({ valid[$0] }) ? Double(gap) : nil
            }
        }
        guard intervals.count >= 4 else { continue }
        let fitted = median(intervals), jitter = median(intervals.map { abs($0 - fitted) }) / max(1, fitted)
        guard jitter < 0.10 else { continue }
        let score = coverage * 0.45 + matched * 0.35 + (1 - jitter) * 0.2
        if score > best.score { best = SequenceFit(bpm: 12000 / fitted, score: score, matched: matched, coverage: coverage, jitter: jitter, complete: complete, peaks: peaks) }
    }
    return best
}

struct RobustPattern {
    private var previous: Double?
    mutating func estimate(envelope: [Double], brightness: [Double], raw: [Double], valid: [Bool]) -> RobustDiagnostics {
        var d = RobustDiagnostics()
        guard envelope.count >= 1200, brightness.count == envelope.count, raw.count == envelope.count, valid.count == envelope.count else { previous = nil; return d }
        let n = envelope.count
        d.cleanFraction = Double(valid.filter { $0 }.count) / Double(n)
        d.recentCleanFraction = Double(valid.suffix(200).filter { $0 }.count) / Double(min(200, n))
        var begin: Int?
        for i in 0...n {
            if i < n, !valid[i] { if begin == nil { begin = i } }
            else if let start = begin { d.maskedRanges.append([start, i]); begin = nil }
        }
        func reject(_ reason: String) -> RobustDiagnostics { d.reason = reason; previous = nil; return d }
        guard d.cleanFraction >= 0.7, d.recentCleanFraction >= 0.7 else { return reject("contact_noise") }
        let values = envelope.indices.compactMap { valid[$0] ? envelope[$0] : nil }
        guard median(values) > 0.000015 else { return reject("signal_too_quiet") }
        let x = centered(envelope, valid: valid), rawX = centered(raw, valid: valid)
        var scores = [Double](repeating: 0, count: 301)
        for lag in 66...300 { scores[lag] = maskedCorrelation(x, valid: valid, lag: lag) }
        let peaks = (67..<300).filter { scores[$0] > scores[$0 - 1] && scores[$0] >= scores[$0 + 1] }
        guard let best = peaks.max(by: { scores[$0] < scores[$1] }), scores[best] >= 0.55 else { return reject("weak_repeating_pattern") }
        let lag = peaks.first { scores[$0] >= max(0.55, scores[best] * 0.92) } ?? best
        d.correlation = scores[lag]
        guard [0..<n / 2, n / 2..<n].allSatisfy({ maskedCorrelation(x, valid: valid, lag: lag, range: $0) > 0.35 }) else { return reject("inconsistent_window_halves") }
        let a = scores[lag - 1], b = scores[lag], c = scores[lag + 1], curvature = a - 2 * b + c
        let offset = abs(curvature) > 1e-9 ? max(-0.5, min(0.5, 0.5 * (a - c) / curvature)) : 0
        let pattern = 12000 / (Double(lag) + offset), sequence = sequenceFit(envelope, brightness: brightness, valid: valid)
        d.patternBPM = pattern; d.cycleBPM = sequence.bpm; d.peaks = sequence.peaks; d.matchedShare = sequence.matched
        d.cycleCoverage = sequence.coverage; d.jitter = sequence.jitter; d.completeCycles = sequence.complete
        guard agreement(pattern, sequence.bpm) != nil else { return reject(sequence.bpm == nil ? "unclear_sound_sequence" : "counters_disagree") }
        d.rawSupport = maskedCorrelation(rawX, valid: valid, lag: lag)
        guard d.rawSupport >= 0.25 else { return reject("no_support_in_original_audio") }
        let value = previous.map { abs($0 - pattern) < 15 ? $0 * 0.55 + pattern * 0.45 : pattern } ?? pattern
        previous = value; d.bpm = value; d.reason = "accepted"
        return d
    }
}
