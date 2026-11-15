import Foundation

protocol HeartSoundModels: AnyObject {
    var hasDenoiser: Bool { get }
    func states(_ features: [Float]) throws -> [Float]
    func denoise(_ samples: [Float]) throws -> [Float]
}

/// Windowed-sinc anti-aliasing. Interpolation retains time for 44.1/48 kHz inputs.
struct HeartResampler {
    private let rate: Double, coefficients: [Double]
    private var ring: [Double], cursor = 0, count = 0, next = 0.0
    var delay: Double { rate == 1000 ? 0 : Double(coefficients.count - 1) / (2 * rate) }
    init(rate: Double) {
        self.rate = rate
        let radius = rate == 1000 ? 0 : Int((rate * 0.02).rounded()), n = radius * 2 + 1
        var values = (0..<n).map { i -> Double in
            guard radius > 0 else { return 1 }
            let x = Double(i - radius), cutoff = min(450, rate * 0.45) / rate
            let sinc = x == 0 ? 2 * cutoff : sin(2 * .pi * cutoff * x) / (.pi * x)
            return sinc * (0.5 - 0.5 * cos(2 * .pi * Double(i) / Double(n - 1)))
        }
        let sum = values.reduce(0, +); values = values.map { $0 / sum }
        coefficients = values; ring = [Double](repeating: 0, count: n + 1)
    }
    mutating func append(_ sample: Float) -> Float? {
        ring[cursor] = sample.isFinite ? Double(sample) : 0; cursor = (cursor + 1) % ring.count
        let index = count; count += 1
        guard Double(index) >= next else { return nil }
        let fraction = Double(index) - next
        var now = 0.0, before = 0.0
        for k in coefficients.indices {
            now += coefficients[k] * ring[(cursor - 1 - k + ring.count * 2) % ring.count]
            if fraction > 1e-8 { before += coefficients[k] * ring[(cursor - 2 - k + ring.count * 2) % ring.count] }
        }
        next += rate / 1000
        return Float(now * (1 - fraction) + before * fraction)
    }
}

private struct EnergyBand {
    var high: Biquad, low: Biquad, energy = 0.0
    init(_ low: Double, _ high: Double) { self.high = Biquad(sampleRate: 1000, cutoff: low, highPass: true); self.low = Biquad(sampleRate: 1000, cutoff: high) }
    mutating func append(_ sample: Double) { let value = low.process(high.process(sample)); energy += value * value }
    mutating func take() -> Double { let value = sqrt(energy / 10); energy = 0; return value }
}

struct SoundFeatures {
    let values: [Float], rms: Double
    var pulseRMS: Double? = nil
}

struct HeartFeatureBank {
    private var bands = [(25.0, 60.0), (60, 100), (100, 160), (160, 250), (250, 400), (25, 400)].map { EnergyBand($0.0, $0.1) }
    private var filter: [Double], ring = [Double](repeating: 0, count: 41), cursor = 0, count = 0
    private var mean: Double?, previous: Double?
    init() {
        let values = (0..<41).map { i -> Double in
            let x = Double(i - 20), sinc = x == 0 ? 0.8 : sin(0.8 * .pi * x) / (.pi * x)
            return sinc * (0.5 - 0.5 * cos(2 * .pi * Double(i) / 40))
        }
        let sum = values.reduce(0, +); filter = values.map { $0 / sum }
    }
    mutating func append(_ sample: Float) -> SoundFeatures? {
        ring[cursor] = Double(sample); cursor = (cursor + 1) % ring.count
        var value = 0.0
        for i in filter.indices { value += filter[i] * ring[(cursor - 1 - i + ring.count) % ring.count] }
        for i in bands.indices { bands[i].append(value) }
        count += 1; guard count % 10 == 0 else { return nil }
        let energy = bands.indices.map { bands[$0].take() }, broad = log(max(energy[5], 1e-7))
        let slow = (mean ?? broad) * 0.995 + broad * 0.005; mean = slow
        var values = energy.prefix(5).map { log(max($0, 1e-7)) - slow }
        values += [broad - slow, broad / 8, broad - (previous ?? broad)]; previous = broad
        return SoundFeatures(values: values.map { Float(max(-8, min(8, $0))) }, rms: energy[5],
                             pulseRMS: sqrt(energy.prefix(3).reduce(0) { $0 + $1 * $1 }))
    }
}

struct SoundFrame {
    let index: Int, features: [Float], rms: Double
    var valid: Bool
    var pulseRMS: Double? = nil
}
struct StateFrame: Codable {
    let index: Int, probabilities: [Double]
}

struct NeuralTiming {
    private var previous: Double?
    private let windowFrames: Int, minimumSupport: Double, pulseBand: Bool, consistentLowSupport: Bool
    init(windowFrames: Int = 800, minimumSupport: Double = 0.25, pulseBand: Bool = false, consistentLowSupport: Bool = false) {
        self.windowFrames = windowFrames; self.minimumSupport = minimumSupport; self.pulseBand = pulseBand
        self.consistentLowSupport = consistentLowSupport
    }
    mutating func estimate(states: [StateFrame], raw: [SoundFrame]) -> RobustDiagnostics {
        var d = RobustDiagnostics(); d.method = "neural_states"
        guard let end = states.last?.index, end >= 599 else { return d }
        let begin = max(0, end - windowFrames + 1), frames = states.filter { $0.index >= begin }
        let original = raw.filter { $0.index >= begin && $0.index <= end }
        guard original.count >= min(500, windowFrames) else { return d }
        let lookup = Dictionary(uniqueKeysWithValues: original.map { ($0.index, $0) })
        let valid = original.map { $0.valid }, energy = original.map { pulseBand ? ($0.pulseRMS ?? $0.rms) : $0.rms }
        d.windowSeconds = Double(original.count) / 100; d.envelope = energy
        d.stateProbabilities = stride(from: 0, to: frames.count, by: 5).map { frames[$0].probabilities }
        var maskedStart: Int?
        for i in 0...valid.count {
            if i < valid.count && !valid[i] { if maskedStart == nil { maskedStart = i } }
            else if let start = maskedStart { d.maskedRanges.append([start, i]); maskedStart = nil }
        }
        d.cleanFraction = Double(valid.filter { $0 }.count) / Double(valid.count)
        d.recentCleanFraction = Double(original.suffix(100).filter { $0.valid }.count) / Double(min(100, original.count))
        func reject(_ reason: String) -> RobustDiagnostics { d.reason = reason; previous = nil; return d }
        guard d.cleanFraction >= 0.7, d.recentCleanFraction >= 0.7 else { return reject("contact_noise") }
        guard median(energy) > 0.000015, median(Array(energy.suffix(100))) > 0.000015 else { return reject("signal_too_quiet") }
        let noisy = frames.filter { $0.probabilities[0] > 0.6 }.count
        guard Double(noisy) / Double(max(1, frames.count)) < 0.3 else { return reject("model_detected_noise") }
        func sounds(_ state: Int) -> [(time: Int, confidence: Double)] {
            var result: [(Int, Double)] = [], active: [StateFrame] = []
            func finish() {
                defer { active = [] }
                guard (2...25).contains(active.count), active.first!.index > frames.first!.index,
                      let best = active.max(by: { $0.probabilities[state] < $1.probabilities[state] }) else { return }
                let weight = active.reduce(0) { $0 + $1.probabilities[state] }
                let center = Int((active.reduce(0) { $0 + Double($1.index) * $1.probabilities[state] } / weight).rounded())
                guard lookup[center]?.valid == true else { return }
                if let last = result.last, center - last.0 < 20 {
                    if best.probabilities[state] > last.1 { result[result.count - 1] = (center, best.probabilities[state]) }
                } else { result.append((center, best.probabilities[state])) }
            }
            for frame in frames {
                let p = frame.probabilities
                if p[state] >= 0.5 && p[state] == p.max()! { active.append(frame) } else { finish() }
            }
            // A sound cut off by either window edge has no reliable center yet.
            return result
        }
        let first = sounds(1), second = sounds(3)
        d.peaks = (first.map(\.time) + second.map(\.time)).sorted().map { $0 - begin }
        var intervals: [(period: Double, end: Int)] = []
        var eligible = 0
        for (a, b) in zip(first, first.dropFirst()) {
            let gap = b.time - a.time
            guard (34...150).contains(gap), min(a.confidence, b.confidence) >= 0.6 else { continue }
            guard (a.time...b.time).allSatisfy({ lookup[$0]?.valid == true }) else { continue }
            eligible += 1
            let sounds = second.filter { $0.time >= a.time + 8 && $0.time <= b.time - 6 && $0.confidence >= 0.6 }
            guard sounds.count == 1 else { continue }
            intervals.append((Double(gap), b.time))
        }
        d.matchedShare = Double(intervals.count) / Double(max(1, eligible))
        guard intervals.count >= 3, d.matchedShare >= 0.7 else { return reject("insufficient_confirmed_cycles") }
        let period = median(intervals.map(\.period)), good = intervals.filter { abs($0.period - period) / period < 0.18 }
        guard good.count >= 3, Double(good.count) / Double(intervals.count) >= 0.75,
              let last = good.last, Double(end - last.end) <= period * 1.5 else { return reject("inconsistent_or_old_cycles") }
        let fitted = median(good.map(\.period)), jitter = median(good.map { abs($0.period - fitted) }) / fitted
        d.jitter = jitter; d.completeCycles = good.count; d.cycleCoverage = Double(good.count) / Double(max(1, intervals.count))
        guard jitter < 0.12 else { return reject("cycle_jitter") }
        let x = centered(energy, valid: valid, radius: 50), center = Int(fitted.rounded())
        let lags = (max(33, center - 2)...min(150, center + 2)).map { ($0, maskedCorrelation(x, valid: valid, lag: $0)) }
        guard let best = lags.max(by: { $0.1 < $1.1 }), best.1 >= minimumSupport else { return reject("no_support_in_original_audio") }
        d.rawSupport = best.1; d.correlation = best.1
        // A regular subset can hide conflicting cycles when the acoustic evidence is weak.
        guard !consistentLowSupport || best.1 >= 0.4 || d.cycleCoverage >= 0.9 else { return reject("weak_audio_and_inconsistent_cycles") }
        d.halfScores = [0..<x.count / 2, x.count / 2..<x.count].map { maskedCorrelation(x, valid: valid, lag: best.0, range: $0) }
        guard d.halfScores.allSatisfy({ $0 > 0.2 }) else { return reject("inconsistent_window_halves") }
        let left = maskedCorrelation(x, valid: valid, lag: max(1, best.0 - 1)), right = maskedCorrelation(x, valid: valid, lag: best.0 + 1)
        let curvature = left - 2 * best.1 + right
        let offset = abs(curvature) > 1e-9 ? max(-0.5, min(0.5, 0.5 * (left - right) / curvature)) : 0
        let raw = 6000 / (Double(best.0) + offset), neural = 6000 / fitted
        d.patternBPM = raw; d.cycleBPM = neural
        guard agreement(raw, neural) != nil else { return reject("counters_disagree") }
        let value = previous.map { abs($0 - raw) < 15 ? $0 * 0.55 + raw * 0.45 : raw } ?? raw
        previous = value; d.bpm = value; d.reason = "accepted"
        return d
    }
}

/// A shorter independently checked window may recover from older inconsistent timing.
/// Every returned reading still requires fresh complete cycles and original-audio support.
struct AdaptiveNeuralTiming {
    private var full = NeuralTiming(consistentLowSupport: true), recent = NeuralTiming(windowFrames: 400)
    private var pulse = NeuralTiming(minimumSupport: 0.4, pulseBand: true)
    private var medium = NeuralTiming(windowFrames: 600, consistentLowSupport: true)
    private var previousRecent: Double?, previousMedium: Double?
    mutating func estimate(states: [StateFrame], raw: [SoundFrame]) -> RobustDiagnostics {
        var full = full.estimate(states: states, raw: raw)
        var pulse = pulse.estimate(states: states, raw: raw)
        if full.bpm == nil, pulse.bpm != nil { pulse.method = "neural_pulse"; full = pulse }
        var medium = medium.estimate(states: states, raw: raw)
        let mediumConfirmed = agreement(medium.bpm, previousMedium) != nil
        previousMedium = medium.bpm
        var recent = recent.estimate(states: states, raw: raw)
        let confirmed = agreement(recent.bpm, previousRecent) != nil
        previousRecent = recent.bpm
        let end = states.last?.index ?? -1
        let middle = states.filter { $0.index > end - 600 }
        let middleNoise = middle.filter { $0.probabilities[0] > 0.6 }.count
        if full.bpm == nil, mediumConfirmed, medium.bpm != nil, medium.completeCycles >= 4,
           medium.rawSupport >= 0.4, medium.cycleCoverage >= 0.9, medium.matchedShare >= 0.85,
           medium.halfScores.allSatisfy({ $0 >= 0.3 }), medium.cleanFraction >= 0.9, medium.recentCleanFraction >= 0.9,
           Double(middleNoise) / Double(max(1, middle.count)) < 0.1 {
            medium.method = "neural_six_second"; return medium
        }
        let latest = states.filter { $0.index > end - 400 }
        let noisy = latest.filter { $0.probabilities[0] > 0.6 }.count
        guard full.bpm == nil, confirmed, recent.bpm != nil,
              recent.completeCycles >= 4, recent.jitter < 0.05, recent.rawSupport >= 0.5,
              recent.halfScores.allSatisfy({ $0 >= 0.35 }),
              recent.cleanFraction >= 0.9, recent.recentCleanFraction >= 0.9,
              Double(noisy) / Double(max(1, latest.count)) < 0.1 else { return full }
        recent.method = "neural_recent"
        return recent
    }
}

/// Audio-queue confined. Models receive only audio features; no Watch or participant data.
final class HeartSoundPipeline {
    private let models: HeartSoundModels
    private var resampler: HeartResampler, rawBank = HeartFeatureBank(), cleanBank = HeartFeatureBank()
    private var raw: [SoundFrame] = [], cleaned: [SoundFrame] = [], states: [StateFrame] = [], cleanStates: [StateFrame] = []
    private var timing = NeuralTiming(), cleanTiming = NeuralTiming(), output = RobustDiagnostics()
    private var adaptive = AdaptiveNeuralTiming()
    private let adaptiveTiming: Bool
    private var count = 0, cleanCount = 0, pending: [Float] = [], previousDenoised: [Float]?
    private var blockMaximum = 0.0, blockPeaks: [Double] = [], invalidThrough = -1, maxMotion = 0.0
    private var denoiseMS = 0.0, error: String?, warning: String?, denoiserEnabled: Bool
    private var denoiseHigh = Biquad(sampleRate: 1000, cutoff: 25, highPass: true), denoiseLow = Biquad(sampleRate: 1000, cutoff: 400)
    init(rate: Double, models: HeartSoundModels, denoiserEnabled: Bool = false, adaptiveTiming: Bool = false) {
        self.adaptiveTiming = adaptiveTiming
        resampler = HeartResampler(rate: rate); self.models = models; self.denoiserEnabled = denoiserEnabled && models.hasDenoiser
    }
    func append(_ samples: [Float], motion: Double = 0) {
        maxMotion = max(maxMotion, motion)
        for sample in samples {
            guard let value = resampler.append(sample) else { continue }
            count += 1
            if denoiserEnabled { pending.append(Float(denoiseLow.process(denoiseHigh.process(Double(value))))) }
            if let f = rawBank.append(value) {
                let index = count / 10 - 1
                let reference = blockPeaks.sorted().dropFirst(blockPeaks.count * 3 / 4).first ?? 1
                let artifact = blockPeaks.count >= 4 && (f.rms > reference * 4 || motion > 0.06 && f.rms > reference * 2.5)
                if artifact || abs(sample) >= 0.98 || !sample.isFinite {
                    invalidThrough = index + 15
                    for i in raw.indices where raw[i].index >= index - 10 { raw[i].valid = false }
                }
                raw.append(SoundFrame(index: index, features: f.values, rms: f.rms, valid: index > invalidThrough, pulseRMS: f.pulseRMS))
                // Adapt the reference even during a burst, so silence or a gain step cannot latch the mask.
                blockMaximum = max(blockMaximum, f.rms)
                if index % 50 == 49 { blockPeaks.append(blockMaximum); if blockPeaks.count > 8 { blockPeaks.removeFirst() }; blockMaximum = 0 }
                if raw.count > 1200 { raw.removeFirst(raw.count - 1200) }
                if raw.count >= 200 && index % 20 == 19 { infer(raw, into: &states) }
            }
            if pending.count >= 800 {
                let started = ProcessInfo.processInfo.systemUptime
                do {
                    let frame = Array(pending.prefix(800)), scale = max(frame.map { abs($0) }.max() ?? 0, 1e-8)
                    let denoised = try models.denoise(frame.map { $0 / scale }).map { $0 * scale }
                    guard denoised.count == 800, denoised.allSatisfy(\.isFinite) else { throw CocoaError(.coderReadCorrupt) }
                    for i in 0..<400 {
                        let w = Float(0.5 - 0.5 * cos(2 * .pi * Double(i) / 800))
                        let sample = previousDenoised.map { $0[i + 400] * (1 - w) + denoised[i] * w } ?? denoised[i]
                        cleanCount += 1
                        if let f = cleanBank.append(sample) {
                            let index = cleanCount / 10 - 1
                            cleaned.append(SoundFrame(index: index, features: f.values, rms: f.rms, valid: true))
                            if cleaned.count > 1200 { cleaned.removeFirst(cleaned.count - 1200) }
                            if cleaned.count >= 200 && index % 20 == 19 { infer(cleaned, into: &cleanStates) }
                        }
                    }
                    previousDenoised = denoised; pending.removeFirst(400)
                } catch { self.warning = "Denoiser disabled: \(error.localizedDescription)"; denoiserEnabled = false; pending = [] }
                denoiseMS = (ProcessInfo.processInfo.systemUptime - started) * 1000
            }
        }
    }
    private func infer(_ frames: [SoundFrame], into history: inout [StateFrame]) {
        let recent = Array(frames.suffix(200)), input = (0..<8).flatMap { channel in recent.map { $0.features[channel] } }
        do {
            let logits = try models.states(input)
            guard logits.count == 1000, logits.allSatisfy(\.isFinite) else { throw CocoaError(.coderReadCorrupt) }
            for t in (history.isEmpty ? 125 : 180)..<200 {
                let values = (0..<5).map { Double(logits[$0 * 200 + t]) }, maximum = values.max()!
                let exp = values.map { Foundation.exp($0 - maximum) }, sum = exp.reduce(0, +)
                history.append(StateFrame(index: recent[t].index, probabilities: exp.map { $0 / sum }))
            }
            if history.count > 1000 { history.removeFirst(history.count - 1000) }
        } catch { self.error = "Sound model failed: \(error.localizedDescription)" }
    }
    func estimate() -> RobustDiagnostics {
        var result = adaptiveTiming ? adaptive.estimate(states: states, raw: raw) : timing.estimate(states: states, raw: raw)
        if denoiserEnabled {
            let alternative = cleanTiming.estimate(states: cleanStates, raw: raw)
            if let a = result.bpm, let b = alternative.bpm, agreement(a, b) == nil { result.bpm = nil; result.reason = "raw_and_denoised_disagree" }
            else if result.bpm == nil, alternative.bpm != nil { result = alternative; result.method = "neural_denoised" }
        }
        let end = result.method == "neural_denoised" ? cleanStates.last?.index : states.last?.index
        result.analysisAge = max(0, Double(count) / 1000 - Double((end ?? -1) + 1) / 100) + resampler.delay + 0.025
        result.warning = warning; result.motion = maxMotion; result.denoiseMS = denoiseMS; maxMotion = 0
        if error != nil { result.reason = error!; result.bpm = nil }
        output = result; return result
    }
    // Research-only snapshot. Called by the local audio replay executable, never by capture.
    func replayInput() -> TimingReplayInput {
        TimingReplayInput(states: states, raw: raw.map { TimingEnergy(index: $0.index, rms: $0.rms, valid: $0.valid, pulseRMS: $0.pulseRMS) })
    }
}

struct TimingEnergy: Codable {
    let index: Int, rms: Double, valid: Bool
    var pulseRMS: Double? = nil
}
struct TimingReplayInput: Codable {
    let states: [StateFrame], raw: [TimingEnergy]
    var frames: [SoundFrame] { raw.map { SoundFrame(index: $0.index, features: [], rms: $0.rms, valid: $0.valid, pulseRMS: $0.pulseRMS) } }
}
