import Foundation

var failures = 0
func check(_ condition: Bool, _ message: String) {
    if condition { print("PASS: \(message)") }
    else { print("FAIL: \(message)"); failures += 1 }
}

// Deterministic test signals, not medical validation or patient recordings.
func sound(bpm: Double, seconds: Double, sampleRate: Double = 48000, amplitude: Double = 0.03, seed: UInt64 = 42, secondPhase: Double = 0.35, secondGain: Double = 0.55, secondFrequency: Double = 95) -> [Float] {
    var state = seed
    return (0..<Int(seconds * sampleRate)).map { index in
        let t = Double(index) / sampleRate
        let period = 60 / bpm
        let phase = t.truncatingRemainder(dividingBy: period)
        func pulse(_ offset: Double, frequency: Double, gain: Double) -> Double {
            let age = phase - offset
            guard age >= 0, age < 0.11 else { return 0 }
            return gain * sin(2 * .pi * frequency * age) * exp(-age * 45) * min(age * 500, 1)
        }
        state = state &* 6364136223846793005 &+ 1
        let noise = Double(state >> 32) / Double(UInt32.max) * 2 - 1
        let signal = pulse(0, frequency: 65, gain: 1) + pulse(period * secondPhase, frequency: secondFrequency, gain: secondGain)
        return Float(amplitude * signal + noise * amplitude * 0.03)
    }
}

for sampleRate in [44100.0, 48000.0] {
    for expected in [45.0, 60, 72, 90, 120, 150, 175] {
        var estimator = HeartRateEstimator(sampleRate: sampleRate)
        let samples = sound(bpm: expected, seconds: 10, sampleRate: sampleRate)
        for start in stride(from: 0, to: samples.count, by: 2048) {
            estimator.append(Array(samples[start..<min(start + 2048, samples.count)]))
        }
        let estimate = estimator.estimate()
        check(estimate.bpm.map { abs($0 - expected) < 3 } ?? false,
              "\(Int(expected)) BPM at \(Int(sampleRate)) Hz → \(estimate.bpm.map { String(format: "%.1f", $0) } ?? "unsure")")
    }
}

var silence = HeartRateEstimator(sampleRate: 48000)
silence.append([Float](repeating: 0, count: 48000 * 9))
check(silence.estimate().bpm == nil, "Silence produces no BPM")

var short = HeartRateEstimator(sampleRate: 48000)
short.append(sound(bpm: 75, seconds: 4))
check(short.estimate().bpm == nil, "Four seconds is insufficient")

var noise = HeartRateEstimator(sampleRate: 48000)
var state: UInt64 = 99
let noiseSamples: [Float] = (0..<48000 * 10).map { _ in
    state = state &* 6364136223846793005 &+ 1
    return Float(Double(state >> 32) / Double(UInt32.max) * 2 - 1) * 0.1
}
noise.append(noiseSamples)
check(noise.estimate().bpm == nil, "Nonperiodic noise produces no BPM")

var changing = HeartRateEstimator(sampleRate: 48000)
changing.append(sound(bpm: 70, seconds: 10))
check(changing.estimate().bpm.map { abs($0 - 70) < 3 } ?? false, "Initial 70 BPM signal")
let faster = sound(bpm: 105, seconds: 12)
var final: Double?
for start in stride(from: 0, to: faster.count, by: 24000) {
    changing.append(Array(faster[start..<min(start + 24000, faster.count)]))
    final = changing.estimate().bpm
}
check(final.map { abs($0 - 105) < 3 } ?? false, "Live estimate follows a change from 70 to 105 BPM")
changing.append([Float](repeating: 0, count: 48000 * 9))
check(changing.estimate().bpm == nil, "Lost signal clears the previous BPM")

// Frozen outputs captured from the installed v1 before refactoring.
struct Golden: Decodable { let rate: Double, target: Double, second: Int, bpm: Double?, periodicity: Double }
let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("v1-golden.json")
let golden = try JSONDecoder().decode([Golden].self, from: Data(contentsOf: fixture))
var regressions = 0
for rate in [44100.0, 48000.0] {
    for target in [45.0, 60, 72, 90, 120, 150, 175] {
        var estimator = HeartRateEstimator(sampleRate: rate)
        let samples = sound(bpm: target, seconds: 12, sampleRate: rate)
        for second in 0..<12 {
            let start = Int(Double(second) * rate)
            estimator.append(Array(samples[start..<start + Int(rate)]))
            let actual = estimator.estimate()
            let expected = golden.first { $0.rate == rate && $0.target == target && $0.second == second + 1 }!
            let same = actual.original == nil && expected.bpm == nil ||
                actual.original != nil && expected.bpm != nil && abs(actual.original! - expected.bpm!) < 1e-9
            if !same || abs(actual.periodicity - expected.periodicity) > 1e-9 { regressions += 1 }
        }
    }
}
check(regressions == 0, "All 168 original BPM/periodicity snapshots match v1 within 1e-9")

for (name, samples) in [
    ("Equal spacing with distinct sound types", sound(bpm: 72, seconds: 10, secondPhase: 0.5, secondGain: 0.4)),
    ("Quieter clean heartbeat", sound(bpm: 72, seconds: 10, amplitude: 0.001))
] {
    var estimator = HeartRateEstimator(sampleRate: 48000)
    estimator.append(samples)
    let result = estimator.estimate()
    check(result.bpm.map { abs($0 - 72) < 3 } ?? false, name)
    check(result.audio.count == 32000 && result.audio.allSatisfy { $0.isFinite }, "Replay holds at most 8 seconds at 4 kHz")
    check(!result.marks.isEmpty && result.marks.allSatisfy { result.waveform.indices.contains($0) }, "Candidate marks stay inside displayed waveform")
}
var ambiguous = HeartRateEstimator(sampleRate: 48000)
ambiguous.append(sound(bpm: 72, seconds: 10, secondPhase: 0.5, secondGain: 1, secondFrequency: 65))
check(ambiguous.estimate().bpm == nil, "Identical evenly spaced pulses cannot establish full-cycle rate")
check(agreement(144, 72) == nil && agreement(36, 72) == nil, "Half/double-rate disagreement is rejected")
check(agreement(72, 73) == 72 && agreement(nil, 72) == nil && agreement(72, nil) == nil, "Agreement requires both estimates and preserves the original timing")
var clipped = HeartRateEstimator(sampleRate: 48000)
clipped.append(sound(bpm: 72, seconds: 10).map { max(-1, min(1, $0 * 300)) })
let clippingResult = clipped.estimate()
check(clippingResult.bpm == nil && clippingResult.original == nil, "Clipping rejects both estimates")
let now = Date()
let pairs = [WatchPair(time: now, original: 70, improved: 72, watch: 72),
             WatchPair(time: now, original: 80, improved: nil, watch: 72),
             WatchPair(time: now, original: nil, improved: nil, watch: 72),
             WatchPair(time: now, original: 60, improved: 60, watch: 72)]
let before = ComparisonStats(pairs, improved: false), after = ComparisonStats(pairs, improved: true)
check(before.common == 2 && after.common == 2 && before.commonError == 7 && after.commonError == 6 &&
      abs(before.error! - 22.0 / 3) < 1e-9 && after.error == 6,
      "Comparison separates each method’s error from same-pair error")
check(before.missing == 1 && after.missing == 2 && before.largeErrors == 2 && after.largeErrors == 1,
      "Comparison includes unsure readings and large errors")
let empty = ComparisonStats([], improved: true)
check(empty.error == nil && empty.common == 0 && empty.largeErrors == 0 && empty.missing == 0,
      "Empty comparison does not invent accuracy")

// A brief old contact-noise burst must not hide a clean newest six seconds.
for rate in [44100.0, 48000.0] {
    var samples = sound(bpm: 72, seconds: 10, sampleRate: rate), random: UInt64 = 718
    for i in Int(rate * 2)..<Int(rate * 3) {
        random = random &* 6364136223846793005 &+ 1
        samples[i] += Float((Double(random >> 32) / Double(UInt32.max) * 2 - 1) * 0.4)
    }
    var estimator = HeartRateEstimator(sampleRate: rate), result = HeartRateEstimate()
    let step = Int(rate / 2)
    for i in stride(from: 0, to: samples.count, by: step) {
        estimator.append(Array(samples[i..<min(i + step, samples.count)])); result = estimator.estimate()
    }
    check(result.bpm.map { abs($0 - 72) < 3 } == true && result.diagnostics.source == "recent_window" && result.original == nil,
          "Clean recent signal survives an older noise burst at \(Int(rate)) Hz")
    check(!result.marks.isEmpty && result.marks.allSatisfy { result.waveform.indices.contains($0) } &&
          result.diagnostics.recent?.periodicity.reason == "accepted" && result.diagnostics.recent?.cycle.reason == "accepted",
          "Recent-window recovery retains diagnostics and correctly aligned waveform marks")
    estimator.append([Float](repeating: 0, count: Int(rate * 8)))
    check(estimator.estimate().bpm == nil, "Recent-window recovery clears when the signal disappears")
}
var confirmedRecent = RecentDiagnostics(bpm: 72, patternBPM: 72, cycleBPM: 73, confirmed: true)
check(selectPattern(nil, 73, recent: confirmedRecent).bpm == 72, "Recent recovery still agrees with a valid long-window counter")
check(selectPattern(144, 72, recent: confirmedRecent).bpm == nil && selectPattern(90, nil, recent: confirmedRecent).bpm == nil &&
      selectPattern(nil, 90, recent: confirmedRecent).bpm == nil, "Recent recovery cannot bypass disagreement or a conflicting valid counter")
confirmedRecent.confirmed = false
check(selectPattern(nil, nil, recent: confirmedRecent).bpm == nil, "One isolated recent result cannot become a BPM")
check(selectPattern(74, 73, recent: confirmedRecent).bpm == 74, "Existing accepted readings keep their original numeric value")
let envelope = detailedEnvelopeForTest()
func detailedEnvelopeForTest() -> [Double] {
    var estimator = HeartRateEstimator(sampleRate: 48000)
    estimator.append(sound(bpm: 72, seconds: 8))
    return estimator.estimate().diagnostics.envelope!
}
var recentCounter = RecentCounter()
let brightness = [Double](repeating: 0, count: envelope.count)
check(!recentCounter.estimate(envelope, brightness: brightness).confirmed && recentCounter.estimate(envelope, brightness: brightness).confirmed,
      "Recent counter needs two successive agreeing results")
_ = recentCounter.estimate([Double](repeating: 0, count: 1600), brightness: brightness)
check(!recentCounter.estimate(envelope, brightness: brightness).confirmed, "An unclear update resets recent confirmation")
var falseNoise = 0
for seed in 1...8 {
    var random = UInt64(seed), estimator = HeartRateEstimator(sampleRate: 48000)
    for _ in 0..<20 {
        let samples: [Float] = (0..<24000).map { _ in
            random = random &* 6364136223846793005 &+ 1
            return Float(Double(random >> 32) / Double(UInt32.max) * 2 - 1) * 0.1
        }
        estimator.append(samples)
        if estimator.estimate().bpm != nil { falseNoise += 1 }
    }
}
check(falseNoise == 0, "Eight continuous random-noise streams never return a BPM in 160 updates")


// Live Watch packets use measurement timestamps, never arrival time as a fresh sample.
let clock = Date(timeIntervalSince1970: 1000), sessionID = UUID()
func packet(sequence: Int = 1, active: Bool = true, bpm: Double? = 72.25, age: Double = 1) -> WatchPacket {
    WatchPacket(session: sessionID, began: clock.addingTimeInterval(-60), sequence: sequence, active: active,
                bpm: bpm, start: clock.addingTimeInterval(-age - 5), end: clock.addingTimeInterval(-age))
}
let live = packet()
check(live.fresh(at: clock), "Recent Watch measurement is eligible")
check(!packet(age: 16).fresh(at: clock), "Stale Watch value is not live")
check(!packet(age: -3).fresh(at: clock), "Future-dated Watch value is rejected")
check(!packet(active: false).fresh(at: clock) && !packet(bpm: nil).fresh(at: clock), "Stopped or missing Watch readings cannot compare")
check(!packet(bpm: .nan).fresh(at: clock) && !packet(bpm: 0).fresh(at: clock), "Invalid Watch BPM is rejected")
var malformed = live; malformed.start = clock.addingTimeInterval(-100)
check(!malformed.fresh(at: clock), "Pre-session measurement is rejected")
malformed = live; malformed.start = clock
check(!malformed.fresh(at: clock), "Reversed Watch interval is rejected")
let decoded = try JSONDecoder().decode(WatchPacket.self, from: JSONEncoder().encode(live))
check(decoded.bpm == 72.25 && decoded.start == live.start && decoded.end == live.end && decoded.session == sessionID,
      "Watch transport preserves fractional BPM and measurement times")
var feed = WatchFeed(); feed.receive(packet(sequence: 2), now: clock)
feed.receive(packet(sequence: 1, bpm: 150), now: clock)
check(feed.packet?.sequence == 2 && feed.packet?.bpm == 72.25, "Out-of-order packets do not replace a newer reading")
feed.receive(packet(sequence: 2, bpm: 150), now: clock)
check(feed.packet?.bpm == 72.25, "Duplicate packets are ignored")
feed.receive(packet(sequence: 3, active: false, bpm: nil), now: clock)
feed.receive(packet(sequence: 4), now: clock)
check(feed.packet?.active == false, "An ended session cannot be restarted by late packets")
let newer = WatchPacket(session: UUID(), began: clock.addingTimeInterval(-30), sequence: 1, active: true)
feed.receive(newer, now: clock); feed.receive(packet(sequence: 99), now: clock)
check(feed.packet?.session == newer.session, "Old-session packets do not replace a new session")
feed.receive(WatchPacket(session: UUID(), began: clock.addingTimeInterval(10), sequence: 1, active: true), now: clock)
check(feed.packet?.session == newer.session, "Future session is ignored")
let history = [PhoneReading(time: clock.addingTimeInterval(-2), seconds: 8, original: 71, improved: 71),
               PhoneReading(time: clock.addingTimeInterval(-0.8), seconds: 8, original: 73, improved: nil)]
let matched = automaticPair(live, history: history, now: clock)
check(matched?.original == 73 && matched?.improved == nil && matched?.watch == 72.25 && matched?.watchTime == live.end && matched?.automatic == true,
      "Live pairing uses nearest timestamp, retains unsure and fractional Watch BPM")
check(automaticPair(live, history: [PhoneReading(time: clock, seconds: 4, original: nil, improved: nil)], now: clock) == nil,
      "Phone warm-up does not become a comparison")
check(automaticPair(live, history: [PhoneReading(time: clock.addingTimeInterval(-10), seconds: 8, original: 72, improved: 72)], now: clock) == nil,
      "Misaligned phone estimates are not paired")
check(automaticPair(packet(age: 16), history: history, now: clock) == nil, "Stale Watch values never become automatic pairs")
let fractional = ComparisonStats([matched!], improved: false)
check(fractional.error == 0.75, "Comparison uses actual fractional Watch reading without rounding")


let logRoot = FileManager.default.temporaryDirectory.appendingPathComponent("chestbpm-log-tests-" + UUID().uuidString)
let logger = DiagnosticLog(directory: logRoot)
try logger.start()
for i in 0..<20 { logger.write(DiagnosticEvent(event: "ordering", message: String(i))) }
var loggedEstimator = HeartRateEstimator(sampleRate: 48000)
loggedEstimator.append(sound(bpm: 72, seconds: 10))
let detailed = loggedEstimator.estimate()
logger.write(DiagnosticEvent(event: "estimate", estimate: detailed, watch: live))
try logger.flush()
let lines = try String(contentsOf: logger.url, encoding: .utf8).split(separator: "\n")
let records = try lines.map { try JSONSerialization.jsonObject(with: Data($0.utf8)) as! [String: Any] }
check(records.count == 21 && records.enumerated().allSatisfy { $0.element["sequence"] as? Int == $0.offset + 1 },
      "Diagnostic rows are complete, ordered, and immediately readable")
let logged = records.last!["estimate"] as! [String: Any]
check(logged["audio"] == nil && logged["diagnostics"] != nil, "Diagnostic JSON excludes raw audio and includes decision details")
check(detailed.diagnostics.periodicity.reason == "accepted" && detailed.diagnostics.cycle.reason == "accepted" &&
      detailed.diagnostics.periodicity.selectedLag != nil && detailed.diagnostics.cycle.gaps.count > 0,
      "Accepted diagnostics retain candidate lags and sound spacing")
check(detailed.diagnostics.envelope?.count == 1600 && detailed.diagnostics.brightness?.count == 1600,
      "Detailed trace retains the complete derived eight-second window")
let quietDetails = silence.estimate().diagnostics
check(quietDetails.periodicity.reason == "signal_too_quiet" && quietDetails.signal.rawRMS == 0,
      "Silence records the actual rejection reason and input level")
check(clippingResult.diagnostics.signal.clippingFraction > 0.01, "Clipping diagnostics expose the measured fraction")
let run = records.first!["run"] as! String
try logger.start(); logger.write(DiagnosticEvent(event: "second_run")); try logger.flush()
check(FileManager.default.fileExists(atPath: logRoot.appendingPathComponent("previous.ndjson").path), "A new run retains the previous diagnostic file")
let restarted = try JSONSerialization.jsonObject(with: Data(contentsOf: logger.url)) as! [String: Any]
check(restarted["run"] as? String != run && restarted["sequence"] as? Int == 1, "New run identifiers prevent confusing old and current data")
logger.write(DiagnosticEvent(event: "nonfinite", processingMS: .nan)); try logger.flush()
check(logger.state.error == nil, "Nonfinite diagnostics remain valid JSON instead of losing the log")
logger.write(DiagnosticEvent(event: "oversized", message: String(repeating: "x", count: 10_000_001))); try logger.flush()
check(logger.state.error != nil && logger.state.rows == 2, "Log size limit reports a visible error without corrupting completed rows")
try logger.clear()
check(!FileManager.default.fileExists(atPath: logRoot.path), "Clear removes diagnostic files")

// Anti-aliasing and fractional resampling must preserve the signal's clock.
for rate in [44100.0, 48000.0] {
    func rmsTone(_ frequency: Double) -> (Int, Double, Double) {
        var resampler = HeartResampler(rate: rate), output: [Double] = []
        for i in 0..<Int(rate * 2) {
            if let value = resampler.append(Float(sin(2 * .pi * frequency * Double(i) / rate))) { output.append(Double(value)) }
        }
        return (output.count, sqrt(output.dropFirst(100).reduce(0) { $0 + $1 * $1 } / Double(output.count - 100)), resampler.delay)
    }
    let pass = rmsTone(70), alias = rmsTone(1070)
    check(abs(pass.0 - 2000) <= 1 && abs(pass.1 - sqrt(0.5)) < 0.02, "Resampling preserves 70 Hz level and duration at \(rate)")
    check(alias.1 < pass.1 * 0.02 && abs(pass.2 - 0.02) < 0.0001, "Resampling rejects aliased audio and reports filter delay at \(rate)")
}
let delayedHistory = [PhoneReading(time: clock.addingTimeInterval(1), seconds: 8, original: 111, improved: 75, improvedTime: clock.addingTimeInterval(-1)),
                      PhoneReading(time: clock.addingTimeInterval(-1), seconds: 8, original: 72, improved: 99, improvedTime: clock.addingTimeInterval(-3))]
let delayedPair = automaticPair(live, history: delayedHistory, now: clock)
check(delayedPair?.original == 72 && delayedPair?.improved == 75 && delayedPair?.originalTime == clock.addingTimeInterval(-1),
      "Watch matching accounts for model delay without changing baseline timestamps")

final class BrokenModels: HeartSoundModels {
    var hasDenoiser = true, corrupt = false, failDenoise = false
    func states(_ features: [Float]) throws -> [Float] {
        if corrupt { return [Float](repeating: .nan, count: 1000) }
        return (0..<1000).map { $0 < 200 ? Float(10) : Float(-10) }
    }
    func denoise(_ samples: [Float]) throws -> [Float] { throw CocoaError(.coderReadCorrupt) }
}
let broken = BrokenModels(); broken.corrupt = true
let corruptPipeline = HeartSoundPipeline(rate: 1000, models: broken)
corruptPipeline.append(sound(bpm: 72, seconds: 8, sampleRate: 1000))
let corruptResult = corruptPipeline.estimate()
check(corruptResult.bpm == nil && corruptResult.reason.hasPrefix("Sound model failed"), "Corrupt model output fails closed")
let cleanerFailure = HeartSoundPipeline(rate: 1000, models: BrokenModels(), denoiserEnabled: true)
cleanerFailure.append(sound(bpm: 72, seconds: 8, sampleRate: 1000))
let cleanerResult = cleanerFailure.estimate()
check(cleanerResult.reason == "model_detected_noise" && cleanerResult.warning?.hasPrefix("Denoiser disabled") == true,
      "Optional denoiser failure preserves the original-audio model path")
let blankPipeline = HeartSoundPipeline(rate: 48000, models: BrokenModels())
blankPipeline.append([Float](repeating: 0, count: 48000 * 8))
check(blankPipeline.estimate().bpm == nil, "Enhanced pipeline rejects silence")
let encodedDelay = try JSONSerialization.jsonObject(with: JSONEncoder().encode(HeartRateEstimate(analysisAge: 0.425))) as! [String: Any]
check(encodedDelay["analysisAge"] as? Double == 0.425 && encodedDelay["audio"] == nil, "Logs retain analysis delay without embedding audio")

let gainRecovery = HeartSoundPipeline(rate: 1000, models: BrokenModels())
func feedRecovery(_ samples: [Float]) {
    for start in stride(from: 0, to: samples.count, by: 500) {
        gainRecovery.append(Array(samples[start..<min(start + 500, samples.count)]))
        _ = gainRecovery.estimate()
    }
}
feedRecovery(sound(bpm: 72, seconds: 8, sampleRate: 1000, amplitude: 0.01))
feedRecovery(sound(bpm: 72, seconds: 10, sampleRate: 1000, amplitude: 0.12))
check(gainRecovery.estimate().recentCleanFraction > 0.9, "Transient mask recovers after a sustained pressure/gain change")
let quietStart = HeartSoundPipeline(rate: 1000, models: BrokenModels())
quietStart.append([Float](repeating: 0, count: 8000))
quietStart.append(sound(bpm: 72, seconds: 10, sampleRate: 1000))
check(quietStart.estimate().recentCleanFraction > 0.9, "Transient mask recovers when clear sound follows silence")

// Remote trial control must remain safe across duplicates, disconnects and wearer changes.
let trialA = UUID(), trialB = UUID()
let prepareA = TrialCommand(trial: trialA, action: .prepare, issued: clock, expires: clock.addingTimeInterval(75), deadline: clock.addingTimeInterval(120))
var gate = TrialCommandGate()
check(gate.accept(prepareA, now: clock) == nil, "A fresh prepare command is accepted")
check(gate.accept(prepareA, now: clock) == "duplicate", "Duplicate prepare does not restart the Watch")
let changedPrepare = TrialCommand(trial: trialA, action: .prepare, issued: clock, expires: clock.addingTimeInterval(75), deadline: clock.addingTimeInterval(130))
check(gate.accept(changedPrepare, now: clock) == "conflicting_duplicate", "Duplicate trial cannot silently change its stop deadline")
let recordA = TrialCommand(trial: trialA, action: .record, issued: clock.addingTimeInterval(10), expires: clock.addingTimeInterval(105), deadline: clock.addingTimeInterval(105), start: clock.addingTimeInterval(15))
check(gate.accept(recordA, now: clock.addingTimeInterval(10)) == nil, "Matching record command installs an independent stop deadline")
check(gate.accept(prepareA, now: clock.addingTimeInterval(11)) == "earlier_phase", "Delayed prepare cannot reset a recording timer")
let stopA = TrialCommand(trial: trialA, action: .stop, issued: clock.addingTimeInterval(20), expires: clock.addingTimeInterval(200), deadline: clock.addingTimeInterval(20))
check(gate.accept(stopA, now: clock.addingTimeInterval(20)) == nil, "Stop is accepted for the same trial")
check(gate.accept(recordA, now: clock.addingTimeInterval(21)) == "completed_trial", "Late record cannot restart a stopped trial")
let prepareB = TrialCommand(trial: trialB, action: .prepare, issued: clock.addingTimeInterval(30), expires: clock.addingTimeInterval(90), deadline: clock.addingTimeInterval(140))
check(gate.accept(prepareB, now: clock.addingTimeInterval(30)) == nil, "Next wearer or test uses a new trial identity")
check(gate.accept(stopA, now: clock.addingTimeInterval(31)) == "duplicate" && gate.current == trialB, "Old queued stop cannot stop a newer wearer or test")
let lateOldStop = TrialCommand(trial: trialA, action: .stop, issued: clock.addingTimeInterval(32), expires: clock.addingTimeInterval(150), deadline: clock.addingTimeInterval(32))
_ = gate.accept(lateOldStop, now: clock.addingTimeInterval(32))
check(gate.current == trialB && gate.phase == TrialCommand.Action.prepare.rawValue, "Newly issued retry for an old trial cannot replace the new trial gate")
var cancelFirstGate = TrialCommandGate()
_ = cancelFirstGate.accept(stopA, now: clock.addingTimeInterval(20))
check(cancelFirstGate.accept(prepareA, now: clock.addingTimeInterval(21)) == "completed_trial", "Stop delivered before prepare prevents that cancelled trial from starting")
var restoredGate = try JSONDecoder().decode(TrialCommandGate.self, from: JSONEncoder().encode(gate))
check(restoredGate.accept(prepareA, now: clock.addingTimeInterval(32)) == "completed_trial", "Persisted gate rejects old starts after relaunch")
var invalidGate = TrialCommandGate()
check(invalidGate.accept(recordA, now: clock.addingTimeInterval(10)) == "wrong_or_old_trial", "Recording cannot begin without a prepare")
check(invalidGate.accept(prepareA, now: clock.addingTimeInterval(76)) == "expired_or_invalid", "Expired queued starts cannot begin a workout")
check(invalidGate.accept(prepareB, now: clock) == "expired_or_invalid", "Future-dated control commands are rejected")
let hugeLease = TrialCommand(trial: UUID(), action: .prepare, issued: clock, expires: clock.addingTimeInterval(60), deadline: clock.addingTimeInterval(3600))
check(!hugeLease.valid(at: clock), "Remote measurement cannot install an unbounded workout lease")
restoredGate.finish(trialB)
check(restoredGate.accept(prepareB, now: clock.addingTimeInterval(35)) == "completed_trial", "Watch's local stop prevents a delayed same-trial restart")

var plan = TrialPlan(participant: "A", audio: true), conditionCounts: [String: Int] = [:], plannedSeconds = 0
let originalPlanID = plan.id
var plannedCycles: [Int: Set<String>] = [:]
for _ in 0..<20 {
    plannedCycles[plan.cycle, default: []].insert(plan.condition)
    conditionCounts[plan.condition, default: 0] += 1; plannedSeconds += plan.duration
    plan.advance()
}
check(plannedCycles.count == 5 && plannedCycles.values.allSatisfy { $0 == Set(TrialPlan.conditions) }, "Every cycle covers all four environments")
check(plan.complete && plannedSeconds == 1450 && conditionCounts.values.allSatisfy { $0 == 5 } && conditionCounts.count == 4, "Five-cycle plan contains exactly five of each condition and 1450 recording seconds")
plan.advance(); check(plan.index == 20, "Completed plan cannot advance beyond 20 trials")
let restoredPlan = try JSONDecoder().decode(TrialPlan.self, from: JSONEncoder().encode(plan))
check(restoredPlan.id == originalPlanID && restoredPlan.complete && restoredPlan.audio, "Plan and audio preference survive a saved-state round trip")

try logger.start(); logger.write(DiagnosticEvent(event: "test_started", test: trialA, running: true)); try logger.flush()
let firstArchive = try FileManager.default.contentsOfDirectory(at: logRoot.appendingPathComponent("Runs"), includingPropertiesForKeys: nil)
try logger.start(); logger.write(DiagnosticEvent(event: "second_archive")); try logger.flush()
try logger.start(); logger.write(DiagnosticEvent(event: "third_archive")); try logger.flush()
let archives = try FileManager.default.contentsOfDirectory(at: logRoot.appendingPathComponent("Runs"), includingPropertiesForKeys: nil)
check(firstArchive.count == 1 && archives.count == 3 && archives.allSatisfy { (try? Data(contentsOf: $0).isEmpty) == false }, "Every run remains archived after previous/live rotation")
logger.write(DiagnosticEvent(event: "estimate", running: true, estimate: HeartRateEstimate(bpm: 72))); try logger.flush()
logger.write(DiagnosticEvent(event: "estimate", running: true, estimate: HeartRateEstimate())); try logger.flush()
let snapshotData = try Data(contentsOf: logRoot.appendingPathComponent("status.json"))
let snapshot = try JSONSerialization.jsonObject(with: snapshotData) as! [String: Any]
check(snapshot["phoneBPM"] == nil && snapshot["sequence"] as? Int == 3 && snapshotData.count < 2048, "Small live snapshot clears unsure BPM and reports current sequence")
logger.write(DiagnosticEvent(event: "test_ended", message: "timed_test_complete", test: trialA)); try logger.flush()
let stoppedSnapshot = try JSONSerialization.jsonObject(with: Data(contentsOf: logRoot.appendingPathComponent("status.json"))) as! [String: Any]
check(stoppedSnapshot["running"] as? Bool == false, "Live snapshot marks capture stopped")
logger.write(DiagnosticEvent(event: "test_preparing", test: trialB, running: false, remaining: 90))
logger.write(DiagnosticEvent(event: "test_aborted", message: "user_cancel", test: trialB, running: false)); try logger.flush()
let abortedSnapshot = try JSONSerialization.jsonObject(with: Data(contentsOf: logRoot.appendingPathComponent("status.json"))) as! [String: Any]
check(abortedSnapshot["state"] as? String == "aborted" && abortedSnapshot["remaining"] as? Int == 0, "Cancelled preparation leaves a truthful finished snapshot")
try logger.clear()

var finalPlan = TrialPlan(participant: "A", audio: true, cycles: 2)
var finalConditions: [String: Int] = [:]
for _ in 0..<8 { finalConditions[finalPlan.condition, default: 0] += 1; finalPlan.advance() }
finalPlan.advance()
check(finalPlan.complete && finalPlan.index == 8 && finalConditions.values.allSatisfy { $0 == 2 }, "Final validation stops at eight tests with two repeats per condition")
var oldPlanJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(TrialPlan(participant: "A", audio: true))) as! [String: Any]
oldPlanJSON.removeValue(forKey: "repetitions")
let oldPlan = try JSONDecoder().decode(TrialPlan.self, from: JSONSerialization.data(withJSONObject: oldPlanJSON))
check(oldPlan.totalTests == 20 && oldPlan.cycles == 5, "Saved older plans retain their original five-cycle length")

// Decoder-only fixtures have known acoustic events and no Watch/reference input.
func timingFixture(bpm: Double, seconds: Double = 12, flatAudio: Bool = false, missingSecond: Bool = false) -> ([StateFrame], [SoundFrame]) {
    var states: [StateFrame] = [], raw: [SoundFrame] = []
    let period = 6000 / bpm
    for i in 0..<Int(seconds * 100) {
        let phase = (Double(i) - 15).truncatingRemainder(dividingBy: period)
        let cyclePhase = phase < 0 ? phase + period : phase
        let firstDistance = min(cyclePhase, period - cyclePhase)
        let secondDistance = abs(cyclePhase - period * 0.35)
        var probabilities = [Double](repeating: 0.01, count: 5)
        let state = firstDistance <= 4 ? 1 : secondDistance <= 3 && !missingSecond ? 3 : 4
        probabilities[state] = 0.96
        let energy = flatAudio ? 0.01 : 0.0001 + 0.01 * exp(-firstDistance * firstDistance / 10) + 0.008 * exp(-secondDistance * secondDistance / 10)
        states.append(StateFrame(index: i, probabilities: probabilities))
        raw.append(SoundFrame(index: i, features: [], rms: energy, valid: true, pulseRMS: energy))
    }
    return (states, raw)
}
for bpm in [40.0, 60, 90, 120, 175] {
    let (states, raw) = timingFixture(bpm: bpm)
    var decoder = AdaptiveNeuralTiming()
    let value = decoder.estimate(states: states, raw: raw)
    check(value.bpm.map { abs($0 - bpm) < 0.8 } == true, "Adaptive timing preserves known \(Int(bpm)) BPM")
}
let (eventStates, eventRaw) = timingFixture(bpm: 90)
var acousticWarmup = AdaptiveNeuralTiming()
check(acousticWarmup.estimate(states: Array(eventStates.prefix(550)), raw: Array(eventRaw.prefix(550))).bpm == nil, "Adaptive decoder retains the six-second warm-up")
let (flatStates, flatRaw) = timingFixture(bpm: 90, flatAudio: true)
var flatDecoder = AdaptiveNeuralTiming()
check(flatDecoder.estimate(states: flatStates, raw: flatRaw).bpm == nil, "Confident model labels cannot invent pulses in flat audio")
let (missingStates, missingRaw) = timingFixture(bpm: 90, missingSecond: true)
var missingDecoder = AdaptiveNeuralTiming()
check(missingDecoder.estimate(states: missingStates, raw: missingRaw).bpm == nil, "Adaptive decoder requires both heart-sound families")
var maskedRaw = eventRaw
for i in 1150..<1200 { maskedRaw[i].valid = false }
var maskedDecoder = AdaptiveNeuralTiming()
check(maskedDecoder.estimate(states: eventStates, raw: maskedRaw).bpm == nil, "Adaptive decoder withholds readings during current masked contact noise")
var staleStates = eventStates
for i in 1050..<staleStates.count { staleStates[i] = StateFrame(index: i, probabilities: [0.01, 0.01, 0.01, 0.01, 0.96]) }
var staleDecoder = AdaptiveNeuralTiming()
check(staleDecoder.estimate(states: staleStates, raw: eventRaw).bpm == nil, "Adaptive decoder clears old beats when new sounds disappear")
var partialSoundDecoder = NeuralTiming()
let partialCount = 1151
let partialResult = partialSoundDecoder.estimate(states: Array(eventStates.prefix(partialCount)), raw: Array(eventRaw.prefix(partialCount)))
check(partialResult.bpm != nil && partialResult.peaks.allSatisfy({ $0 + partialCount - 800 < 1145 }),
      "An incomplete sound at the window edge cannot supply a beat center")

print("\(failures) failure(s). Deterministic engineering checks; not clinical validation.")
exit(failures == 0 ? 0 : 1)
