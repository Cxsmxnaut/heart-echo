# Heart Echo

Heart Echo adopts the new native SwiftUI design and the original Chest BPM measurement features. It is a **separate app** (`app.veritas.heartecho`); Chest BPM (`app.veritas.chestbpm`), its Watch app, frozen models and personal diagnostics remain untouched.

## Current app

- Summary, real 20-second microphone recording with live accepted BPM, independent on-device murmur analysis, and a persistent local recording history.
- Saved results retain the actual outcome, model revision, source, duration, measured audio envelope and optional BPM. Reopening a result explains that exact result. No fixed 72 BPM, invented audio-quality grade or decorative ECG is used as measurement data.
- **Settings → Developer Mode** is OFF by default. Turning it on exposes Live & Diagnostic Tools and the three public test recordings/import controls. The switch persists. Turning it off stops active diagnostics/logging and keeps saved tests. It is unrelated to Apple's device Developer Mode requirement for development-signed apps.
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

See `INTEGRATION-VALIDATION.md` for checks actually completed on the current port. The original DSP and murmur model are preserved; a UI port does not establish phone accuracy. Present, absent and unsure remain distinct; a murmur-like pattern is not a diagnosis, an absent result does not rule out disease, and an unsure result is not a negative. No AFib or valve-disease detector has been added.


[Archived design-preview notes and design attribution](Docs/DesignPreviewHistory.md).
