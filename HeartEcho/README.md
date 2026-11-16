# Heart Echo

For judging, start with the [project overview](../README.md), [walkthrough](../docs/JUDGE_GUIDE.md), and [current evidence](../docs/RESULTS.md). This file contains component/developer details.

Heart Echo adopts the new native SwiftUI design and the original Chest BPM measurement features. It is a **separate app** (`app.veritas.heartecho`); Chest BPM (`app.veritas.chestbpm`), its Watch app, frozen models and personal diagnostics remain untouched.

Current source version: **0.4.1 (6)**. [Final validation](../docs/FINAL_VALIDATION.md) records native assertions, UI reruns, Debug/Release builds and the Release sharing check. This pass used the iPhone Simulator; it did not install the new build on the physical phone.

## Final app pass

- The live recording coach turns existing engine feedback into a clear next action. Quiet input, clipping, contact noise, stale timing and pending BPM stay distinct. It does not invent a BPM or change the DSP thresholds.
- **Share Result Summary** is available on the immediate result and in saved recording details. It opens the system share sheet with text only, preserving the actual finding, source, measured values, limitations and model revision. Audio, private paths, identifiers and raw error text are excluded.
- Gemini wording uses one 12-second default budget across generation, fallback and rewrite attempts. Directory requests have their own timing. A model timeout is labeled, and already validated directory cards remain available.
- Care accepts a standalone five-digit ZIP and offers **Find care by ZIP** before pairing. This is a direct public-directory path, not a generated AI reply; internet is still required.
- `../Start Heart Echo Judge Demo.command` and `npm run judge` in `care-assistant/` start an isolated guided browser review. They do not load saved AI configuration, start a local model or change the phone's pairing.

## Current app

- Summary, real 20-second microphone recording with live accepted BPM, independent on-device murmur analysis, and a persistent local recording history.
- Saved results retain the actual outcome, model revision, source, duration, measured audio envelope and optional BPM. Reopening a result explains that exact result. No fixed 72 BPM, invented audio-quality grade or decorative ECG is used as measurement data.
- **Try a public example** is available directly from Summary, without Developer Mode or microphone access. **Settings → Developer Mode** defaults OFF and exposes diagnostic tools and additional import controls. Turning it off stops diagnostics/logging and keeps saved results. This setting is separate from Apple's device Developer Mode.
- Live & Diagnostic Tools preserve original Measure / Compare / Murmur, motion/quality checks, replay, positions, participant/consent controls, automatic Watch start/stop, timed diagnostic tests, resumable cycles, Watch reference alignment, archived logs, and sharing.
- A separate Heart Echo Watch companion uses the original HealthKit/WatchConnectivity implementation and protocol. Neither Watch BPM nor Watch references enter microphone BPM or murmur inference. Temporary workout sessions are discarded.
- Public samples run the real shipping model; their reference annotations and the model's output can differ. Examples/imports have no microphone BPM. Imports analyze at most the first 60 seconds and do not copy the imported original.
- Each completed recording first opens a result screen with the actual murmur outcome, a plain-language explanation and a **Find care with AI** button. Public examples and saved recordings use the same care chat as the Care tab.
- The chat connects to `../care-assistant/` on the demo Mac after pairing. When a Gemini key is configured, Gemini writes conversational replies throughout the care flow and the app labels that connection. Recorded results are not sent to Gemini; detected location and insurance details are replaced with general instructions. The filter is incomplete. Free-tier messages may be used by Google to improve its products, so don't enter personal or health information. Without a Gemini key, the existing local Gemma setup remains available.

Start `../Start Heart Echo Demo.command` on the Mac, then use **Connect to use care AI** in the app and pair on the same trusted Wi-Fi. In the local model mode, the optional summary switch sends the finding and available measurements to the Mac. In Gemini mode, recorded results stay on the phone. Raw audio stays on the phone in both modes.

## Privacy and capture behavior

There is no automatic recording on app launch. A normal recording writes raw microphone audio to the app's private, backup-excluded `Application Support/HeartEcho/Pending` directory. The timer starts only after capture starts. The monitor drains its audio queue and returns the final URL, sample count, rate and any write failure; partial or failed captures cannot become successful 20-second records. The accepted BPM summary is captured before stopping the monitor.

**Keep microphone audio on this iPhone** defaults OFF. Pending audio is removed after analysis, cancellation, interruptions and recovery from an unfinished capture. Failed file cleanup stays tracked and reports an error. Protected staged writes and durable operation journals keep saves/deletes recoverable after a crash. History stores results plus a normalized measured waveform. Opting in retains playback/share audio in private app storage. If diagnostic logging is also enabled, a protected diagnostic copy is logged for explicit collector retrieval. Deleting the result removes its retained and diagnostic copies. Audio from imports and bundled public examples is never deleted from its original location. No cloud storage or upload service is connected.

Original diagnostic tests still have their own explicit audio toggle. Those diagnostic files remain until cleared, as in Chest BPM. Heart Echo's app container and collector output are separate from Chest BPM.

## Build

```sh
python3 Tools/configure_project.py
xcodebuild -project HeartEchoApp.xcodeproj -scheme HeartEchoApp -configuration Debug -destination 'platform=iOS Simulator,id=YOUR_SIMULATOR_ID' -derivedDataPath build-integration ONLY_ACTIVE_ARCH=YES CODE_SIGNING_ALLOWED=NO build
xcodebuild -project HeartEchoApp.xcodeproj -scheme HeartEchoApp -configuration Release -destination generic/platform=iOS -derivedDataPath build-phone -allowProvisioningUpdates build
```

The standalone project bundles only `BeatStates.mlpackage` and the shipping phase-aware `Murmur.mlpackage`. Experimental denoisers are not bundled. `PORTING.json` records the origin hashes. `Tools/configure_project.py` recreates the iPhone, embedded Watch and UI-test targets without reading or editing Chest BPM.

## Diagnostic dashboard

Enable Developer Mode, open Live & Diagnostic Tools, then enable logging. In separate terminals from this directory:

```sh
python3 Tools/collect_study.py --device YOUR_IPHONE_UDID --output diagnostic-logs/live
python3 Tools/dashboard.py --input diagnostic-logs/live --port 8766
```

Open http://127.0.0.1:8766 on this Mac. Add `--audio` to the collector only to retrieve explicitly retained diagnostic audio. The collector checks the phone’s deletion manifest, skips deleted audio and removes corresponding local copies; it skips audio retrieval if it cannot verify that manifest. Port 8766 avoids the original Chest BPM dashboard on 8765. Device connection/unlock requirements still apply.

## Validation and limits

See [final validation](../docs/FINAL_VALIDATION.md) for the 0.4.1 pass and `INTEGRATION-VALIDATION.md` for earlier integration observations. The initial current UI run still needs a successful rerun; do not read earlier device observations as proof that every new screen has passed. The original DSP and murmur model are preserved; a UI port does not establish phone accuracy. Present, absent and unsure remain distinct; a murmur-like pattern is not a diagnosis, an absent result does not rule out disease, and an unsure result is not a negative. No AFib or valve-disease detector has been added.


[Archived design-preview notes and design attribution](Docs/DesignPreviewHistory.md).
