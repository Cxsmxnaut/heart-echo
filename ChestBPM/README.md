## Current update: 1.9 (14) · heartbeat-phase-aware murmur research

The murmur model now learns S1, systole, S2 and diastole, together with approximate murmur timing. A conservative combination adds phase-based positive evidence to the preserved v1 model. It cannot raise the original **Not detected** score. Training uses licensed public data; private recordings and Watch readings are not model inputs or training data.

On the **previously inspected** 440-recording CirCor regression:

| Result | Preserved v1 | Phase-aware model |
|---|---:|---:|
| Murmur recordings detected | 75/104 | 87/104 |
| Positive recordings called absent | 6/104 | 4/104 |
| False alarms on recordings labeled no murmur | 10/321 | 12/321 |
| All recordings returned unsure | 110/440 | 106/440 |

The 83.7% number is detection among positive recordings, **not overall accuracy**. Unique linked-person detection improved only from 25/32 to 26/32; false alarms remained 6/80. The older test set is retrospective regression evidence; both development partitions were reused during research. These results establish neither clinical reliability nor accuracy with a bare iPhone microphone. All 20 known non-heart controls remained unsure. The fixed public demo labeled no murmur now returns **Unsure**; samples were not replaced to make the demo look better. [Methods, failed experiments and limits](Research/murmur-phase-v2.txt), [aggregate comparison](ML/murmur-phase-report.json).

The signed iPhone/Watch 1.9 (14) build passes strict signature, intended-phone profile and packaged-model checks. All 24 model/Python checks, 13 native murmur checks and three UI scenarios passed. The unchanged general-screen case passed on retry after shared-simulator interference; both attempts are retained. **Installed on the iPhone 16:** the device confirms version 1.9 (14). The embedded Watch build is signed; its separate installation was not verified. No new personal recording was collected or is needed.

The original BPM code and BeatStates package remain frozen. The original murmur package is preserved in `ML/Models`; the 1.9 app uses the separate `ML/PhaseModels/Murmur.mlpackage`.

## Earlier update: 1.8 (13) · murmur research

The new **Murmur** tab analyzes bundled public examples, imported audio, or an optional 20-second phone recording on-device. A separate model returns **Murmur-like pattern**, **Not detected in this recording**, or **Unsure**. It does not identify a valve disease or detect AFib. Temporary microphone captures are deleted after analysis or cancellation; imported originals remain in their original location. Watch measurements and the BPM result do not enter this classifier.

The model was trained from scratch on CirCor with patient-linked splits and location-specific murmur labels. On the frozen test of 440 stethoscope recordings from 120 fresh linked-patient groups, it flagged 75/104 positive recordings, missed six as absent, and returned unsure on 23. Among 321 negatives it gave 10 false alarms, 234 absent results and 77 unsure results. Overall unsure: 110/440. All 20 known non-heart controls returned unsure. These results **do not establish phone accuracy**. [Full methods, baseline, confusion matrices and limits](Research/murmur-validation-v18.txt), [aggregate report](ML/murmur-report.json), [provenance](ML/PROVENANCE.txt).

The original BPM algorithm and BeatStates weights remain unchanged. The sections below retain the earlier BPM development history. Build, simulator-test and installation status are recorded in the murmur evaluation notes.

The signed 1.8 (13) iPhone/Watch build passes strict signature checks. All three simulator UI tests, 26 Python scientific checks and 13 native murmur checks pass. **Phone installation is pending:** Xcode cannot reach the iPhone (CoreDeviceError 4016); the new build has not replaced the phone app. No new personal recordings are needed for this completed experiment.

## Earlier update: 1.7 (12)

The phone still estimates BPM from its own microphone. Watch values are comparison references only. The new timing checks reject weak, conflicting cycles and exclude sounds cut off at a window edge. Independently checked pulse energy and shorter six- or four-second windows can recover a reading when the eight-second window is unclear. The existing on-device model and its input features are unchanged. More returned readings do not establish better absolute accuracy.

New validation plans contain two cycles/eight tests; saved older five-cycle plans remain readable. The collector runs indefinitely by default (`--wait 0`). The dashboard derives its totals from the plan, shows the next condition correctly, and accepts a matching local `study-ended.json` to mark an ended study without claiming every planned trial completed or prompting another recording.

The signed update was installed on the iPhone and Watch. Checks passed: 125 deterministic engineering assertions (including the 168 original golden outputs), 15 Python tool tests, two simulator UI tests, native builds, and signature checks. A separate public cohort of 12 previously unused patient groups was evaluated after freezing source, models, cohort selection, and both timing references; see `Research/bpm-validation-v17.txt`, `ML/evaluation-freeze-v17.json`, and model provenance. Those references are not simultaneous ECG on this phone.

The prospective device series ended at the participant's request after the Watch battery died: seven tests completed and the final quiet test stopped after about 45 seconds. Every saved recording and stopped attempt remains in the ignored private diagnostics folder. Both frozen estimators were replayed on identical audio; the v1.7 replay reproduced all 1,067 live return/reject decisions, with returned BPM differences below 0.001. The results show greater reading availability and some shorter gaps, alongside larger Watch disagreements in some added readings. They do not establish 100% accuracy, universal noise rejection, or diagnostic reliability. No algorithm tuning occurred between these trials, and no further personal recordings were requested.

An additional frozen check uses simultaneous ECG and heart audio from the public EPHNOGRAM dataset, with no new personal recordings. On the fixed recent-ECG reference, mean difference decreased from 1.98 to 1.80 BPM with nearly unchanged external-data coverage. Large errors remain. Automated ECG references and stethoscope recordings do not establish clinical or phone-hardware accuracy. [Protocol, complete aggregate results and limitations](Research/ecg-validation-v17.txt) describe this separate check.

Further public-data research trained three isolated sound-state candidates and tested one fixed candidate on 24 previously unread patient groups, across 168 clean, noisy and synthetic irregular-timing cases. It reduced false S1 events on synthetic noise from 320 to 46, but BPM results were mixed and real ECG regression checks worsened slightly. **The installed model remains unchanged.** The new event benchmark preserves irregular positive beats and raw sounds for later research; it does not implement AFib or murmur detection. [Methods, complete results and the decision](Research/event-model-research-v17.txt) explain the tradeoffs. No additional personal recordings are needed for this completed experiment.

## Previous update: 1.6 (11)

The update adds phone-requested Watch start, fresh-reference warm-up, acknowledged start deadlines and local Watch stop timers, queued reference delivery, and a saved five-cycle/20-trial plan. Each trial needs a ready tap after setting up its environment. Apple Health permission and an unlocked worn Watch are still required. The series enables local raw audio for wearer A under the user's explicit testing consent; its toggle can be changed before a test. Friend consent remains separate.

Logs now have per-run permanent archives and manifests, small atomic live-status snapshots, trial/study/cycle/attempt IDs, and a separate phone reference log for late Watch packets. The Watch closes and archives its local log on stopping. Restarted plans require a new ready tap. `Tools/collect_study.py` reads status snapshots and retrieves closed archives, checks sequence/count/byte integrity, and deduplicates retries. Example: `python3 Tools/collect_study.py --device '<iPhone UDID>' --output diagnostic-logs/five-cycle --wait 3600 --audio`. Use the same tool with the Watch UDID and `--bundle app.veritas.chestbpm.watchkitapp` for independent reference archives. Physical checks confirmed phone-requested Watch start, deadline acknowledgement, and a Watch-only stop before any backup stop was needed. See Research/automation-v16.txt for exact evidence and limits; a simulator cannot validate queued WatchConnectivity delivery.

The signed final phone and companion are installed. The estimator and model are unchanged from frozen 1.5 (7), so improvements here concern coordination and data retention. The notes below describe earlier builds.

## Previous build: 1.5 (7)

The app now includes an on-device sound-state model, short-transient masking with motion cues, timestamp-aligned Watch comparisons, separate A/B test labels, and opt-in local audio for timed tests. [Validation and limitations](Research/validation-v15.txt) contains the frozen public benchmark and exact checks. [Model provenance](ML/PROVENANCE.txt) explains public training data, licenses and reproduction. The experimental denoiser is not bundled because it worsened development results.

The signed Release build is installed on the iPhone 16. A private physical test series has been completed on one wearer; personal results remain in the ignored diagnostics directory. A second wearer has not been tested. Audio saving defaults off; old statements below that no raw audio can be saved describe earlier versions. No AFib/murmur detection is implemented. Historical version notes follow.

# Chest BPM

A native SwiftUI microphone experiment for iPhone (iOS 17+). It estimates repeating chest sounds, not heart health. It does not detect AFib or diagnose any condition.

## Use

Open `ChestBPM.xcodeproj` in Xcode, choose your connected iPhone and development team, and Run. The project uses this Mac’s existing Apple development team and bundle ID `app.veritas.chestbpm`. Version 1.1 introduced the four improvements below. Version 1.2 adds the optional live Watch companion described next. Version 1.4 adds the recent-window recovery described below.

1. **Recording guidance and filtered playback.** In Measure, try the listed chest positions with the bottom microphone gently against bare skin. Remove the case, keep still, and use a quiet room. Changing position restarts a running measurement so old-position audio is excluded. Sound level measures loudness, not proof of a heartbeat. Stop & hear recent audio plays up to eight seconds of filtered audio at bounded gain. Recording stops before playback to prevent feedback. Audio is held in memory only.
2. **Full-cycle timing.** A separate heuristic detects envelope peaks and tests for alternating sound types using spacing, amplitude, and frequency balance. It counts every other candidate sound to estimate complete cycles. The waveform dots mark candidate sounds, not clinically confirmed S1/S2 labels. Identical evenly spaced sounds are ambiguous and rejected. This is an original heuristic, not the trained Springer HSMM or a validated S1/S2 classifier.
3. **Agreement check.** The original normalized-autocorrelation estimator remains as a baseline. A main-display BPM requires a repeating-pattern estimate and a full-cycle estimate to agree within the greater of 5 BPM or 6% of the cycle rate. Normally the accepted number keeps the original estimator’s finer timing and smoothing. Version 1.4 can instead use the recent six-second pattern when the longer window is unclear; the same thresholds and the extra confirmation rules below apply. The second counter is a check, not an average. Quiet or clipped audio can suppress the result. Disagreement, including half/double-rate conflicts, produces unsure.
4. **Watch comparisons.** Keep the Watch heart-rate screen open while resting. Read it and immediately tap Pair reading in Compare. This freezes the current original and improved outputs with a timestamp while you enter the Watch reading. Entries, including unsure results, remain in memory for this session. The Watch reference never enters either estimator. Clear comparisons or Clear audio & comparisons removes the relevant session data.

First estimates require six seconds. Updates occur about twice per second using the latest eight seconds plus the original smoothing, so changes take time to settle. Both algorithms use the same microphone signal and may agree on noise. The supported search range is approximately 40–180 BPM; outside rates can be missed or mistaken for multiples. A clearer capture and more selective algorithm are not proof of higher real-world accuracy.

## Live Apple Watch companion (version 1.2)

The `ChestBPMWatch` target is a small companion for watchOS 10+. The iPhone microphone feature remains usable without a Watch.

1. Install the iPhone target with the embedded Watch app. For development, select the **ChestBPMWatch** scheme and the physical Watch in Xcode, enable Developer Mode on the Watch, and let Xcode register it and create the correct profile. The Watch must be paired with this iPhone and trusted for development. After registration, the companion can also appear under Available Apps in the iPhone Watch app.
2. Open **Chest BPM** on the Watch and tap **Start measuring**. Allow heart-rate read access and workout-session access. Apple requires workout sharing permission to run this session, even though the app discards the workout rather than saving it.
3. Open the iPhone app and tap **Start listening**. The Live Apple Watch panel shows the real sensor BPM, the measurement age, connection state, and the current phone-minus-Watch difference. Freshness is based on the Watch’s sample timestamp, not receipt time.
4. In Compare, **Automatically pair live readings** is on by default. Each distinct fresh Watch sample is matched once to the nearest warmed-up phone estimate whose timestamp is within two seconds. The matched Watch value retains its fractional precision for error calculation. Missing phone estimates remain unsure in the comparisons. Manual pairing remains available as a fallback; rows identify Live or Manual.
5. Tap **Stop & discard** on the Watch, or **Stop Watch session** on a reachable iPhone. A five-minute limit ends the session automatically. The companion calls `discardWorkout()`, never `finishWorkout()`. Recovery after a session crash also ends and discards a recoverable session.

The Watch uses an explicit `HKWorkoutSession` with a mind-and-body configuration and `HKLiveWorkoutBuilder` to receive sensor measurements. Only heart-rate read access and workout-session sharing are requested. Energy statistics are disabled in the builder. **This does not guarantee unchanged Activity rings or Health history:** Apple may independently record heart-rate samples or activity during the session. The UI states this before measurement. No fabricated BPM or exercise result is generated.

Packets travel directly through an active `WCSession.sendMessageData` connection. There is no queued application-context delivery, no server, and no health-history import on iPhone. Disconnected messages can be dropped; the UI reports the connection and suppresses BPM after 15 seconds without a fresh measurement. Stopped, duplicate, out-of-order, invalid, future-dated, and old-session readings cannot become fresh comparisons. Two seconds of future clock tolerance permits minor device clock differences. Both devices’ clocks should be set automatically.

Automatic matching is approximate: the microphone uses its eight-second window plus smoothing, while the Watch has its own sample window. A current on-screen difference is not necessarily the same as the timestamp-matched comparison row. These are independent consumer-sensor measurements, not ECG ground truth. Watch values never enter the microphone estimator.

## Detailed live diagnostics (version 1.3)

Diagnostics are opt-in in Compare, or can be enabled for a development launch using the `--diagnostics` argument. The iPhone shows the log status and keeps its screen awake while logging. **Start 90-second diagnostic test** starts capture, marks the test with an identifier, and counts down while the user holds the phone still and breathes normally. At completion it stops the microphone, requests the Watch session to stop if reachable, provides haptic feedback, and closes logging after five more seconds. Stop, backgrounding, interruptions, position changes, and disabled logging end an active timed test with an explicit reason.

The ordered JSON-lines file is `Documents/Diagnostics/live.ndjson` in each enabled app’s own container. There is a 10 MB limit with a visible failure state. Starting a new log retains one `previous.ndjson`; logs are excluded from backup and use protection that permits access after the first device unlock. A clear control removes the files. The Watch companion supports the same development argument and has a delete control. Diagnostic files contain health-related BPM and signal features, so keep copies outside source control. The repository ignores NDJSON, the `diagnostic-logs` folder, and Python caches.

The iPhone logs every roughly half-second analysis update and records:

- Wall time, monotonic uptime, run/sequence/test identifiers, selected position, frame processing time, capture state, recent-audio age, lifecycle and audio-configuration changes.
- Main, original, and full-cycle BPM; display status; signal level; raw/filtered RMS, input peak, clipping fraction, sample counts, microphone route and sample rate.
- Baseline acceptance/rejection reason, selected lag, all lag scores, candidate peaks, raw BPM before smoothing, and consistency scores for each half of the window.
- Cycle acceptance/rejection reason, candidate sound positions and gaps, threshold/contrast, alternating amplitude/frequency features, cycle period, jitter, regular-interval share, and window coverage.
- Every fourth update includes the full derived eight-second amplitude/frequency-balance trace. The compact display waveform is also included. **Raw audio is explicitly excluded from diagnostic JSON.**
- Watch packets with original measurement times, status, freshness, packet acceptance/rejection, connection state, manual/automatic comparisons, and test start/end events. A one-second heartbeat proves that idle/capture logging is still advancing. With Watch-side diagnostics enabled, its local file also records measurement start, authorization errors, sensor updates, send attempts/skips/failures, and stop/discard events.

Use Apple’s developer connection to poll without restarting the app:

```sh
python3 Tools/poll_diagnostics.py --device '<iPhone UDID>' --output /tmp/chestbpm-diagnostic-run --interval 5 --wait 600 --audio
```

The reader copies the running app’s file every five seconds, preserves new records once per run/sequence, tolerates an unfinished final line, and writes a local `captured.ndjson` and `summary.json`. It reports connection errors and stale log age rather than treating silence as a normal result. It waits for a marked test, reports each window’s rejection details and comparison coverage, and exits after the test ends. `--once` verifies initial file access. Add `--follow` to keep polling through stopped attempts and repeated tests until `--wait` expires; without it the reader exits after a test ends. The phone must stay unlocked with the app open during measurement. Live access requires an active Xcode connection by cable or a verified wireless development connection; being paired alone does not guarantee wireless access. If the connection drops, the app continues logging locally for later retrieval. No HTTP server, internet upload, or background automation is used.

On November 14, 2026, the build and 63 deterministic checks passed, including all 168 original-estimator snapshots, ordered/valid log writes, raw-audio exclusion, complete derived traces, rotation, nonfinite-value handling, size-limit failures, and deletion. The simulator screen test passed. Both updated apps were installed; fresh iPhone log heartbeats were retrieved while the app was running. A complete 90-second physical test was subsequently retrieved, including ordered per-window records, actual Watch comparisons, automatic microphone stop, and the Watch stop acknowledgement. Its microphone output was intermittent; personal measurements remain in the ignored diagnostic-logs folder. The first run was retrieved after a cable disconnect. A second complete test was then monitored over a verified wireless Xcode connection with the phone unplugged. Some file transfers failed and recovered; the final log had a continuous event sequence, and microphone, Watch, and logging stops were confirmed. No estimator thresholds changed between the two tests. These checks verify the diagnostic flow rather than clinical accuracy.

## Recent-window recovery (version 1.4)

The logs exposed a practical problem: one unclear part of an eight-second window could suppress an otherwise usable recent pattern. The original eight-second repeating-pattern and cycle calculations remain unchanged. Existing accepted full-window outputs keep their exact numeric value.

When that path is unclear, a second instance of the same calculations checks the newest six seconds. Both counters must pass the existing score, window-half consistency, sound-type, cycle-spacing, and agreement rules. Two successive recent estimates must also agree. A valid long-window counter must agree with the recent result; an explicit long-window counter disagreement always blocks recovery. Quiet, clipped, missing, and ambiguous signals retain their rejection rules. A missing current result clears the recent confirmation; no old BPM is held on screen.

The UI identifies recent-window recovery and shows its two counters. Diagnostic records include both recent decisions, confirmation, the selected window, and the app version/build. Waveform marks follow the selected window. Watch values never enter either calculation.

`Tools/replay_diagnostics.py` reconstructs overlapping derived envelope/frequency traces using logged sample counts, checks every overlap for exact equality, and verifies the original calculations within 1e-9 before evaluating the new selection. It reports any unrecoverable tail rather than inventing data, refuses missing initial/interior history, and passes no Watch fields into the Swift estimator. It cannot test changes to raw-audio filters. Reports fingerprint both the input and estimator source. Keep inputs and outputs in the ignored diagnostics folder or outside this repository:

```sh
python3 Tools/replay_diagnostics.py /private/path/capture.ndjson --output diagnostic-logs/replay
python3 -m unittest discover -s Tools -p 'test_*.py'
```

Version 1.4 build 5 passed 76 deterministic engineering assertions (including the 168 frozen original snapshots), five replay-tool tests, the simulator screen/permission test, native build, and signing. The signed update was installed on the iPhone 16; its first launch was blocked because the phone was locked. After unlock, versioned live heartbeats and two complete fresh physical tests verified launch, recent-window recovery, automatic microphone stop, Watch stop acknowledgement, and logging close. Performance varied between captures; private numerical results remain in the ignored diagnostics folder. No estimator changes were made between these fresh tests.

Replay of the two development captures recovered additional returned readings while preserving all previously accepted outputs. Some new readings had larger Watch differences than the old returned-reading average. This supports improved availability, not a claim of better accuracy. The two captures were already used during development, their analysis windows overlap, and they did not independently validate the change. The subsequent fresh physical tests verified the new code path on new input but still showed variable availability and timing differences. No trained segmentation model, raw-audio recording, or clinical validation is added.

## Compare fairly

The app reports:

- Mean absolute BPM error for each method’s returned readings.
- Mean absolute error on the identical subset where both methods returned a reading.
- The number of readings more than 5 BPM from the Watch reference (an exploratory threshold).
- Unsure count divided by all saved pairs, with the individual timestamped readings below.

A lower returned-reading error can result from rejecting more measurements. Always compare the error, unsure count, and common-pair error together. When the main output uses the full window, it retains the original rate. A recent-window recovery can differ from the baseline. The comparison therefore reports each method’s returned and common-pair error as well as unsure counts; additional outputs alone do not prove an accuracy improvement.

The phone uses the preceding audio window. A Watch may average a different interval, update later, or itself be wrong. These manually paired readings are approximate personal comparisons, not an ECG-backed accuracy study. The optional companion uses HealthKit on Watch and WatchConnectivity between the paired devices. No cloud service or app account is used.

## Implementation and privacy

`AVAudioEngine` captures the built-in microphone in `AVAudioSession` measurement mode, preferring the bottom input when available. A 25–160 Hz biquad band filter feeds the original 200 Hz RMS envelope and 8 Hz envelope filter. An additional high-frequency energy ratio helps distinguish alternating candidate sound types. The recent filtered signal is sampled at 4 kHz for replay. Processing runs on a serial background queue; SwiftUI updates on the main actor.

Recording and playback stop on backgrounding or interruption. Backgrounding also erases recent audio. Restarting capture replaces it. With diagnostics off, the app writes no audio or comparison files. Optional diagnostics retain the numerical/derived records described above. No analytics or server requests are used. Optional sensor BPM is sent from the Watch to the paired iPhone using WatchConnectivity. Comparisons disappear when the iPhone app process ends; Apple’s own Health or Activity records are separate. No dataset, trained model, or third-party package is bundled.

## Checks

Run from this folder:

```sh
swiftc -O -module-cache-path /tmp/chestbpm-module-cache ChestBPM/HeartRateEstimator.swift ChestBPM/NoiseAnalysis.swift ChestBPM/NeuralSignal.swift Shared/WatchLink.swift Shared/TrialProtocol.swift Shared/DiagnosticLog.swift Tests/main.swift -o /tmp/chestbpm-tests
/tmp/chestbpm-tests
```

`Tests/v1-golden.json` freezes 168 original BPM and periodicity outputs captured before refactoring, at 44.1 and 48 kHz over multiple rates and successive time windows. Regression tests compare the retained baseline to those outputs within 1e-9. Other deterministic tests cover clean and quiet synthetic two-sound cycles, warm-up, noise, silence, changing rate, lost signal, ambiguous equally spaced sounds, half/double disagreement, clipping, replay-buffer limits, waveform marker bounds, and comparison math. Additional tests cover Watch packet encoding, fractional precision, freshness, invalid or future values, ordering, session changes, nearest-time matching, warm-up, and unaligned readings. These checks are not medical validation.

`UITests/ChestBPMUITests.swift` checks the tabs, live-Watch placeholder, automatic-pairing toggle, empty comparison state, position menu, denied microphone permission, and clear-session control. Run it on an iPhone simulator through Xcode’s Test action. For deterministic permission testing, revoke this app’s simulator microphone permission first using `xcrun simctl privacy <simulator-id> revoke microphone app.veritas.chestbpm`.

Version 1.0 was built, signed, installed, and launched on the user’s iPhone 16 on November 13, 2026. Its 20 synthetic checks passed. Real chest audio and agreement with an Apple Watch have not yet been reported. See the project brief for the latest version’s build/install status. Neither version has established clinical accuracy.

Version 1.1 (build 2) passed all 34 signal/comparison checks, including the 168 frozen v1 snapshots, and the simulator UI test. The iPhone and simulator builds passed, and the signed update was installed on the iPhone 16. Automatic launch was blocked by the phone’s lock screen; unlock it and open Chest BPM. Live chest capture, audible replay on that device, and actual Watch comparisons still need user testing. The app remains three Swift source files (424 lines versus 410 before adding the four features); before adding the companion, the capture controller was reduced from 150 to 115 lines, with the original estimator extracted into a smaller reusable calculation. No claim of complete equivalence for every possible input or improved clinical accuracy follows from the regression checks.

Version 1.2 passed 52 signal/protocol/comparison checks, all 168 v1 snapshots, and the iPhone simulator UI test. The Watch and combined iPhone builds signed successfully. After the physical Watch was paired to the Mac and registered, its identifier was verified in both the directly installed companion’s profile and the iPhone’s embedded copy. Both apps are installed on the iPhone 16 and Apple Watch Series 9. After starting the session and allowing Health access, the user confirmed that a real BPM appeared on the Watch and that the Watch BPM appeared and updated automatically on iPhone. This verifies the live sensor-to-phone path by user observation. Physical microphone accuracy and the resulting automatic comparison statistics still need testing; the transport check does not establish them.

## Credits and research

Built with Apple Swift, SwiftUI, and AVFoundation, with Codex assistance. The alternating-cycle heuristic was written for this app; no third-party segmentation code or trained weights were copied. Research informing the approach:

- [Echoes recording-quality study](https://pmc.ncbi.nlm.nih.gov/articles/PMC9708017/): guidance and retrying can help users obtain clearer phone recordings; its recording-quality success rate is not BPM accuracy.
- [Springer heart-sound segmentation](https://physionet.org/content/hss/1.0/): published four-state segmentation and reference code; not implemented as the trained model here.
- [Apple workout sessions](https://developer.apple.com/documentation/healthkit/running-workout-sessions), [discarding a session](https://developer.apple.com/documentation/healthkit/hkworkoutbuilder/discardworkout()), and [WatchConnectivity messages](https://developer.apple.com/documentation/watchconnectivity/wcsession/sendmessage(_:replyhandler:errorhandler:)).
- [Apple measurement mode](https://developer.apple.com/documentation/avfaudio/avaudiosession/mode-swift.struct/measurement) and [microphone permission](https://developer.apple.com/documentation/avfaudio/avaudioapplication/requestrecordpermission(completionhandler:)).

This is a personal feasibility experiment. Confirm competition eligibility before including this work or personal recordings in a submission. This project is a prototype and is not medical advice.


### Live browser dashboard

Run the existing phone collector, then open the read-only dashboard on this Mac:

```sh
python3 Tools/dashboard.py --input diagnostic-logs/2026-11-14-v16-five-cycle
```

Open http://localhost:8765. It refreshes every second; the collector normally supplies a new phone snapshot about every three seconds. The dashboard shows phone and Watch BPM, countdown, a three-minute trend, completed study steps and recent status snapshots. Missing or stale readings are hidden. Only matching study tests count toward progress; engineering control checks are excluded. Full event archives arrive when the app closes its log. Keep the collector running and Chest BPM open on the phone. The server binds only to this Mac and does not serve raw audio or arbitrary files.

The collector runs until stopped by default (`--wait 0`). Use a positive `--wait` value only for an intentionally limited session; the old one-hour setting stops collection even while the phone keeps recording. Restarting the collector retrieves saved closed archives without duplicating events. Summary updates are written atomically so the dashboard never reads half-written JSON.
