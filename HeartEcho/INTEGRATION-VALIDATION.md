# Heart Echo integration checks

Current release: **0.2.1 (3)**, 2026-11-14. The original Chest BPM remains **1.9 (14)**.

## Completed

- Standalone iOS Simulator build passed. Standalone Release iPhone and Watch build passed after Xcode account sign-in. Strict, deep signature verification passed for the Release app with its embedded Watch companion.
- Heart Echo installed and launched on iPhone 16. Separate device queries confirmed both `app.veritas.heartecho` 0.2.1(3) and `app.veritas.chestbpm` 1.9(14) coexist. The original app was never replaced or uninstalled.
- All **125** inherited deterministic BPM engineering checks passed against Heart Echo's copies. These are engineering checks, not clinical validation.
- All **13** native murmur checks passed using Heart Echo's shipping model, including silence, short input, clipped samples and invalid probabilities remaining unsure/rejected.
- All **14** record/capture checks passed: present/absent/unsure explanations stay distinct across persistence; missing BPM does not change the murmur outcome; partial capture, write failure and invalid sample rates cannot become a complete recording.
- All **14** Python collector/poller checks passed. Deleted audio is skipped during collection and a previously collected copy is removed when its deletion marker arrives.
- Dashboard HTTP smoke checks passed on an empty temporary input: Heart Echo page, JSON state, and rejection of an unexpected Host header. No original personal diagnostics were read for this test.
- The inherited simulator checks for saved diagnostic-cycle persistence and all three public murmur samples passed. Samples returned the original shipping outcomes: absent-reference → Unsure, present-reference → Murmur-like pattern, uncertain-reference → Unsure. No microphone was used for these examples.
- Original release's **13** pinned source/doc hashes remain unchanged. `Tools/verify_port.py` checks origin hashes, all unadapted copied files, and both complete shipping model packages. `PORTING.json` records origins and the limited adapter changes.

## Final screen and storage checks

All four final acceptance scenarios passed across focused runs:

1. Developer Mode defaults off, turns on to reveal diagnostic tools, persists across relaunch, and hides the diagnostic controls/public samples again when switched off.
2. Microphone denial produces an error and no success/history entry.
3. A real public sample runs the shipping model, opens its actual explanation with no invented BPM, survives relaunch, reopens with the original result, and deletes durably across another relaunch.
4. Original Measure/Compare controls, participant consent, automatic Watch pairing switch, position changes, microphone denial and clearing controls work through the injected shared monitor.

Product tests: **3 passed, 0 failed** in `build-integration/AcceptanceTests.xcresult`. The diagnostic-control check passed separately with **xcodebuild exit 0** in `build-integration/DiagnosticsControls.xcresult`. Earlier test interaction failures were traced to full-row switch accessibility frames and scrolling in the wrong direction for a virtualized control; the tests now tap the actual child switches and scroll deliberately. The Mac restarted during a previous run; that incomplete archive is not counted as a completed test run.

All **16** additional native file checks passed, including injected protection/pre-commit failures, failed deletion with retained history and ownership, cleanup after a crash before/after commit, preservation of legacy diagnostic audio, deletion-manifest retry behavior, and pending capture cleanup without overwriting corrupt history. These tests exercise `RecordingFiles`, the same file owner used by the app. They also caught a canonical-URL comparison bug that was fixed before this release.

JSON is protected while staged, then atomically renamed with no throwing post-commit attribute change. Retention and deletion have durable operation journals. A failed delete keeps the result and retry ownership. The collector checks a persistent deletion manifest even if logging is off, skips deleted audio and removes corresponding local copies. Old audio-player callbacks are ignored unless they belong to the current player.

Visual checks: `Previews/settings-consumer.png`, `Previews/consumer-recording.png`, and `Previews/public-model-result.png` are actual simulator captures. No microphone/Watch recording was used to produce them.

## Boundaries

- The physical Watch is currently unavailable. The new companion is signed and embedded, but its separate physical installation, Health permission, pairing and automatic start/stop have not been verified in this port. Original Watch functionality was preserved in source, with separate bundle IDs and companion routing.
- No fresh physical chest recording was requested or performed for this port. No original personal audio/logs were copied into Heart Echo, uploaded or used for training.
- Phone accuracy has not been established. This port does not improve or clinically validate the detector. No AFib or valve-disease detection was added.
- The assistant is an explicitly labeled local guided explainer. The separate care-assistant service has not been connected. Care listings remain examples.
- No configured Graphify graph/launcher was found. Current source and pinned origin/model hashes were used for verification.

## Reproduce the native checks

Run from the Heart Echo directory:

```sh
swiftc -O -module-cache-path /tmp/heartecho-module-cache Engine/HeartRateEstimator.swift Engine/NoiseAnalysis.swift Engine/NeuralSignal.swift Engine/WatchLink.swift Engine/TrialProtocol.swift Engine/DiagnosticLog.swift Tests/main.swift -o /tmp/heartecho-bpm-tests
/tmp/heartecho-bpm-tests
swiftc -module-cache-path /tmp/heartecho-module-cache Engine/MurmurAnalysis.swift Tools/MurmurChecks.swift -o /tmp/heartecho-murmur-checks
/tmp/heartecho-murmur-checks Models
swiftc -module-cache-path /tmp/heartecho-module-cache Engine/MurmurAnalysis.swift Engine/CaptureArtifact.swift HeartEchoApp/HeartRecording.swift Tests/RecordChecks.swift -o /tmp/heartecho-record-checks
/tmp/heartecho-record-checks
swiftc -module-cache-path /tmp/heartecho-module-cache Engine/MurmurAnalysis.swift HeartEchoApp/HeartRecording.swift HeartEchoApp/RecordingFiles.swift Tests/StorageChecks.swift -o /tmp/heartecho-storage-checks
/tmp/heartecho-storage-checks
python3 -m unittest discover -s Tools -p 'test_*.py'
python3 Tools/verify_port.py
```

Revoke only Heart Echo's simulator microphone permission before permission-denial UI checks. Do not change the real phone's permission for automated testing.
