import Foundation

// Research experiment retained for reproducibility; not included in the app target.
/// Validate individual S1/S2 cycles against their acoustic pulses. No constant-period
/// autocorrelation is required across an older, changing portion of the recording.
struct EventTiming {
    private struct Sound { let time, confidence: Double }
    private struct Cycle { let first, second, next: Sound }
    private var previous: Double?
    mutating func estimate(states: [StateFrame], raw: [SoundFrame]) -> RobustDiagnostics {
        var d = RobustDiagnostics(); d.method = "neural_events"
        func reject(_ reason: String) -> RobustDiagnostics { previous = nil; d.reason = reason; return d }
        guard let end = states.last?.index, end >= 599 else { return d }
        let frames = states.filter { $0.index > end - 800 }
        let lookup = Dictionary(uniqueKeysWithValues: raw.map { ($0.index, $0) })
        func sounds(_ state: Int) -> [Sound] {
            var events: [Sound] = [], active: [StateFrame] = []
            func finish() {
                defer { active = [] }
                guard (2...25).contains(active.count), active.first!.index > frames.first!.index else { return }
                let weight = active.reduce(0) { $0 + $1.probabilities[state] }
                let time = active.reduce(0) { $0 + Double($1.index) * $1.probabilities[state] } / weight
                guard lookup[Int(time.rounded())]?.valid == true else { return }
                let confidence = active.map { $0.probabilities[state] }.max()!
                if let last = events.last, time - last.time < 20 {
                    if confidence > last.confidence { events[events.count - 1] = Sound(time: time, confidence: confidence) }
                } else { events.append(Sound(time: time, confidence: confidence)) }
            }
            for frame in frames {
                let p = frame.probabilities
                if p[state] >= 0.5 && p[state] == p.max()! { active.append(frame) } else { finish() }
            }
            // The rightmost active sound is incomplete. Wait for its actual end.
            return events
        }
        let first = sounds(1), second = sounds(3)
        var cycles: [Cycle] = []
        for (a, b) in zip(first, first.dropFirst()) {
            let gap = b.time - a.time, start = Int(a.time.rounded()), end = Int(b.time.rounded())
            let candidates = second.filter { $0.time >= a.time + 8 && $0.time <= b.time - 6 && $0.confidence >= 0.8 }
            guard (34...150).contains(gap), min(a.confidence, b.confidence) >= 0.8,
                  (start...end).allSatisfy({ lookup[$0]?.valid == true }), candidates.count == 1 else { cycles = []; continue }
            cycles.append(Cycle(first: a, second: candidates[0], next: b))
        }
        let selected = Array(cycles.suffix(4))
        guard selected.count >= 3, let last = selected.last else { return reject("insufficient_acoustic_cycles") }
        let intervals = selected.map { $0.next.time - $0.first.time }, period = median(intervals)
        guard Double(end) - last.next.time <= period * 1.3 else { return reject("acoustic_cycles_too_old") }
        let jitter = median(intervals.map { abs($0 - period) }) / period
        guard jitter < 0.08, intervals.allSatisfy({ abs($0 - period) / period < 0.18 }) else { return reject("changing_or_uncertain_cycle_spacing") }
        let begin = max(0, Int(selected[0].first.time) - 8)
        let segment = raw.filter { $0.index >= begin && $0.index <= end }
        guard !segment.isEmpty, segment.allSatisfy(\.valid) else { return reject("contact_noise") }
        let model = frames.filter { $0.index >= begin }
        guard Double(model.filter { $0.probabilities[0] > 0.6 }.count) / Double(max(1, model.count)) < 0.1 else { return reject("model_detected_noise") }
        func energy(_ i: Int) -> Double? { lookup[i].map { $0.pulseRMS ?? $0.rms } }
        func template(_ sound: Sound) -> [Double]? {
            let modelCenter = Int(sound.time.rounded())
            guard let center = (modelCenter - 4...modelCenter + 4).max(by: { (energy($0) ?? 0) < (energy($1) ?? 0) }) else { return nil }
            let samples = (center - 6...center + 6).compactMap(energy)
            guard samples.count == 13 else { return nil }
            let base = samples.sorted()[2], positive = samples.map { max(0, $0 - base) }
            let norm = sqrt(positive.reduce(0) { $0 + $1 * $1 })
            return norm > 1e-8 ? positive.map { $0 / norm } : nil
        }
        func similarity(_ sounds: [Sound]) -> Double {
            let templates = sounds.compactMap(template)
            guard templates.count == sounds.count else { return 0 }
            var values: [Double] = []
            for i in templates.indices { for j in templates.indices where j > i {
                values.append(zip(templates[i], templates[j]).reduce(0) { $0 + $1.0 * $1.1 })
            } }
            let latest = templates.dropLast().map { previous in zip(previous, templates.last!).reduce(0) { $0 + $1.0 * $1.1 } }
            return min(median(values), median(latest))
        }
        let firsts = [selected[0].first] + selected.map(\.next), seconds = selected.map(\.second)
        let coherence = min(similarity(firsts), similarity(seconds)); d.eventSimilarity = coherence
        guard coherence >= 0.8 else { return reject("inconsistent_acoustic_pulses") }
        var contrasts: [Double] = []
        for cycle in selected {
            let a = Int(cycle.first.time.rounded()), b = Int(cycle.next.time.rounded()), s = Int(cycle.second.time.rounded())
            let background = (a...b).filter { abs($0 - a) > 6 && abs($0 - b) > 6 && abs($0 - s) > 6 }.compactMap(energy)
            guard background.count >= 5 else { return reject("insufficient_acoustic_background") }
            let floor = max(median(background), 1e-8)
            for center in [a, s] {
                let peak = (center - 6...center + 6).compactMap(energy).max() ?? 0
                guard peak > 0.00003 else { return reject("signal_too_quiet") }
                contrasts.append(peak / floor)
            }
        }
        d.pulseContrast = contrasts.min()
        guard contrasts.allSatisfy({ $0 >= 2.5 }) else { return reject("low_acoustic_pulse_contrast") }
        let systolic = zip(seconds, seconds.dropFirst()).map { $1.time - $0.time }
        let secondary = median(systolic)
        guard secondary > 0, abs(secondary - period) / period <= 0.06 else { return reject("sound_families_disagree") }
        // Fit the slope of successive complete cycle positions without quantizing to 10ms.
        var slopes: [Double] = []
        for i in firsts.indices { for j in firsts.indices where j > i {
            slopes.append((firsts[j].time - firsts[i].time) / Double(j - i))
        } }
        let fitted = median(slopes), bpm = 6000 / fitted
        let value = previous.map { abs($0 - bpm) < 15 ? $0 * 0.55 + bpm * 0.45 : bpm } ?? bpm
        previous = value; d.bpm = value; d.cycleBPM = bpm; d.patternBPM = 6000 / secondary
        d.reason = "accepted"; d.jitter = jitter; d.completeCycles = selected.count
        d.windowSeconds = Double(segment.count) / 100; d.cleanFraction = 1; d.recentCleanFraction = 1
        d.matchedShare = 1; d.cycleCoverage = 1
        d.peaks = (firsts + seconds).map { Int($0.time.rounded()) - begin }.sorted()
        d.envelope = segment.map { $0.pulseRMS ?? $0.rms }
        return d
    }
}

