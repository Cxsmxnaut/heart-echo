// Injected only into an isolated validation build. Never part of the product app.
import Foundation
import UIKit

enum MurmurPhoneCheck {
    @MainActor static func run() {
        do {
            let fixture = Bundle.main.url(forResource: "phone-check-expected", withExtension: "json", subdirectory: "MurmurSamples")!
            let expected = try JSONSerialization.jsonObject(with: Data(contentsOf: fixture)) as! [String: Any]
            let model = try MurmurAnalyzer()
            var cases: [[String: Any]] = []
            for reference in expected["cases"] as! [[String: Any]] {
                let name = reference["id"] as! String
                let url = Bundle.main.url(forResource: name, withExtension: "wav", subdirectory: "MurmurSamples")!
                let began = ProcessInfo.processInfo.systemUptime
                let reading = try model.analyze(MurmurAnalyzer.audio(url))
                let old = reference["reading"] as! [String: Any]
                let probabilities = old["probabilities"] as! [Double]
                let delta = zip(reading.probabilities, probabilities).map { abs($0 - $1) }.max()!
                let passed = delta < 0.001 && reading.finding.rawValue == old["finding"] as! String && reading.windows == old["windows"] as! Int
                cases.append(["id": name, "finding": reading.finding.rawValue, "probabilities": reading.probabilities, "windows": reading.windows, "seconds": reading.seconds, "maximum_probability_difference_from_mac_native": delta, "milliseconds": (ProcessInfo.processInfo.systemUptime - began) * 1000, "passed": passed])
            }
            var controls: [[String: Any]] = []
            for (name, samples) in [("silence", [Float](repeating: 0, count: 40000)), ("short", [Float](repeating: 0.03, count: 7999)), ("clipped", [Float](repeating: 1, count: 8000)), ("nonfinite_audio", [Float](repeating: .nan, count: 8000))] {
                let reading = try model.analyze(samples)
                controls.append(["name": name, "passed": reading.finding == .unsure && reading.windows == 0])
            }
            for (name, probabilities) in [("invalid_total", [1.0, 1, 0]), ("nonfinite_probability", [Double.nan, 0, 1]), ("expert_unknown", [0.1, 0.1, 0.8])] {
                controls.append(["name": name, "passed": MurmurRules.finding(probabilities) == .unsure])
            }
            #if targetEnvironment(simulator)
            let physical = false
            #else
            let physical = true
            #endif
            let passed = physical && cases.allSatisfy { $0["passed"] as! Bool } && controls.allSatisfy { $0["passed"] as! Bool }
            let report: [String: Any] = ["passed": passed, "physical_device": physical, "device_family": UIDevice.current.model, "os_version": UIDevice.current.systemVersion, "cases": cases, "controls": controls, "note": "Public sample parity and invalid-input engineering checks only. No microphone captures or private recordings. Not clinical validation."]
            let data = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
            print("MURMUR_PHONE_CHECK=" + String(decoding: data, as: UTF8.self)); fflush(stdout)
            exit(passed ? 0 : 1)
        } catch {
            print("MURMUR_PHONE_CHECK_ERROR=" + error.localizedDescription); fflush(stdout); exit(1)
        }
    }
}
