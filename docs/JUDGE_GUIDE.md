# Judge walkthrough

[Overview](../README.md) · [Results](RESULTS.md) · [Credits](../CREDITS.md)

## A five-minute review

Read the README for the intended user and working flow, then the results table for missed cases, false alarms and uncertainty. Choose a run route below. No hosted app or TestFlight distribution is included; physical iPhone installation requires your own development signing.

The current source is **0.4.1 (6)**. [Final validation](FINAL_VALIDATION.md) records completed engineering checks, the UI run history and Release evidence. The five changes are recording coaching, text result sharing, bounded AI wording, unpaired ZIP search and isolated judge startup.

## Route A: browser care search without a key

Requires Node.js 22+ and npm. From the project root of this source snapshot:

```sh
cd care-assistant
npm ci
npm run judge
```

Use the supplied source snapshot for 0.4.1. This local pass has not published its changes to GitHub; a clone of the public default branch can be an earlier version.

The launcher opens the browser and prints its local address. It prefers `http://127.0.0.1:4318`; if that port is occupied, it chooses a free port and leaves the existing service running. Enter `Find care in 10001` and skip insurance. Internet is needed for live public directories. Provider and community-health-center cards include source links; unavailable sources are reported rather than replaced with invented records.

**This route uses guided application logic, not generated AI replies.** It needs no API account or local model download. The isolated launcher ignores saved and inherited AI configuration and does not read or change pairing files. It binds only to this computer. Stop with Control-C. On a Mac, double-click `Start Heart Echo Judge Demo.command` for the same mode after `npm ci`.

For a headless check or an automatically assigned port:

```sh
npm run judge -- --no-open --port 0
```

Use the address printed after `HEART_ECHO_JUDGE_READY`. This review mode is separate from the Gemini/iPhone pairing route below.

## Route B: real audio inference on iPhone or simulator

Requires macOS, Xcode with an iOS Simulator runtime, and the bundled Core ML packages. The app targets iOS 17+. Debug and optimized Release simulator builds of 0.4.1 (6) passed. The Release result-sharing journey also passed, with the installed executable matching the packaged app. The latest previously reviewed physical development build was 0.4.0 (5); this pass did not install 0.4.1 on a physical phone.

1. Open `HeartEcho/HeartEchoApp.xcodeproj`; choose the **HeartEchoApp** scheme and an available iPhone simulator. For a physical phone, choose your own signing team for the app and Watch targets.
2. Build and run. On **Summary**, tap **Try a public example** and analyze a sample. No microphone permission or cloud key is needed.
3. Confirm the result opens before chat. In prior checks, the present-reference sample produced **Murmur-like pattern**; absent- and unknown-reference samples produced **Unsure**. Reference annotations and model predictions are separate. These examples do not imply perfect detection.
4. Tap **Share Result Summary** to review the system's text-sharing action, then cancel it. No audio is attached. Open **Recordings**, reopen the example and inspect its finding/source and the same sharing option.
5. Open **Care**, tap **Find care by ZIP**, enter `10001` and send it. This can search public directories without Mac pairing or an AI key. It needs internet; source outages and unverified coverage remain visible.
6. **Find care with AI** opens the shared Care chat with a local explanation of that exact result. Generated conversation needs the Mac connection described below. The result itself stays on the phone in Gemini mode.

After the review, delete only examples you created for it.

The examples are public stethoscope recordings. They exercise real model inference, not the accuracy of an iPhone microphone. Use public examples for a competition demonstration rather than collecting private health data.

During an optional microphone recording, the new live coach explains the current engine feedback and a practical action. A missing BPM does not cancel the sound recording. It is separate from the murmur finding and is never replaced with a fixed number.

Optional simulator build from the repository root:

```sh
xcodebuild -project HeartEcho/HeartEchoApp.xcodeproj \
  -scheme HeartEchoApp -configuration Debug \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/heartecho-judge-build \
  CODE_SIGNING_ALLOWED=NO build
```

## Route C: generated care conversation with Gemini

Requires Node.js 22+, an available Gemini API project and your own key, internet, and a Mac. Phone pairing needs the same trusted Wi-Fi.

```sh
cd care-assistant
npm ci
node scripts/setup-gemini.js
```

Enter your key on its local setup page. It is saved in an ignored owner-only file. Run `Start Heart Echo Demo.command` from the repository root. On the Mac, open `http://127.0.0.1:4318/connect.html`. In the iPhone Care tab, open **Connect care AI**, choose the Mac service and enter its six-digit code.

Try this synthetic conversation:

| Message | Expected behavior |
| --- | --- |
| `Hi` | Generated greeting; status identifies Gemini. |
| `Can you help me find care?` | Asks for a ZIP. |
| `10001` | Offers optional insurance or skipping it. |
| `I have Synthetic Healthcare` | Accepts the label without guessing a real insurer, shows public listings, and explains that coverage is unverified. |
| `What should I ask at an appointment?` | Answers conversationally. |

Provider names come from validated directory data. New replies remain above the cards. Gemini wording has a shared 12-second default budget across its fallback and rewrite attempts; public-directory requests have separate deadlines. Limits/outages are labeled, validated cards are retained, and fallback is not counted as a successful model reply. Directory entries and generated wording can change.

The current settings use `gemini-3.5-flash` with `gemini-3.5-flash-lite` fallback for request-limit/temporary-unavailable errors. Model availability depends on your project; override `GEMINI_MODEL` and `GEMINI_FALLBACK_MODEL` if needed. No API key is included.

**Use sample details only.** Audio and results are withheld from Gemini, but filtering of sensitive typed text is incomplete. Google prohibits sending personal/sensitive information to unpaid services: [terms](https://ai.google.dev/gemini-api/terms). The local phone-to-Mac connection uses HTTP. This is not a patient-data service.

## Reproduce the checks

Backend fixtures and protocol checks need no key or live directory access:

```sh
cd care-assistant
npm ci
npm test
```

Focused checks for isolated startup and the source-package tool are also available:

```sh
node --test test/judge-start.test.js
cd ..
python3 -m unittest discover -s tools -p test_package_submission.py -v
```

On macOS, check the actual native murmur model without a microphone:

```sh
cd HeartEcho
swiftc -module-cache-path /tmp/heartecho-module-cache \
  Engine/MurmurAnalysis.swift Tools/MurmurChecks.swift \
  -o /tmp/heartecho-murmur-checks
/tmp/heartecho-murmur-checks Models
python3 Tools/verify_port.py
```

The complete native check runner is `python3 HeartEcho/Tools/check_product.py` from the repository root. [Final validation](FINAL_VALIDATION.md) records the current completed checks and unresolved UI/release status. More storage/capture and historical UI checks are in [the integration record](../HeartEcho/INTEGRATION-VALIDATION.md). Training requires additional public downloads and Python dependencies. Judges do not need to retrain to run the included detector.

## Where to look in the code

| Question | Entry point |
| --- | --- |
| Model inference and uncertainty | [MurmurAnalysis.swift](../HeartEcho/Engine/MurmurAnalysis.swift), [NeuralSignal.swift](../HeartEcho/Engine/NeuralSignal.swift) |
| Recording and durable history | [HeartEchoStore.swift](../HeartEcho/HeartEchoApp/HeartEchoStore.swift), [RecordingFiles.swift](../HeartEcho/HeartEchoApp/RecordingFiles.swift) |
| Result-first flow and shared chat | [RecordingFlowView.swift](../HeartEcho/HeartEchoApp/RecordingFlowView.swift), [AssistantView.swift](../HeartEcho/HeartEchoApp/AssistantView.swift) |
| Recording coach and text export | [RecordingGuidance.swift](../HeartEcho/HeartEchoApp/RecordingGuidance.swift), [HeartRecording.swift](../HeartEcho/HeartEchoApp/HeartRecording.swift) |
| Unpaired ZIP search | [CareSearchIntent.swift](../HeartEcho/HeartEchoApp/CareSearchIntent.swift), [NativeCareDirectory.swift](../HeartEcho/HeartEchoApp/NativeCareDirectory.swift) |
| Data leaving the phone | [CareService.swift](../HeartEcho/HeartEchoApp/CareService.swift) |
| Generated replies and fallbacks | [service.js](../care-assistant/src/service.js), [model.js](../care-assistant/src/model.js) |
| Directory evidence | [directories.js](../care-assistant/src/directories.js), [healthplan.js](../care-assistant/src/healthplan.js) |
| Isolated judge startup and source packaging | [start-judge.js](../care-assistant/scripts/start-judge.js), [package_submission.py](../tools/package_submission.py) |
| Training and model origins | [Provenance](../ChestBPM/ML/PROVENANCE.txt), [research decision](../research/murmur-model-decision.md) |

`ChestBPM/` is preserved for provenance and reproducibility. Historical UI descriptions and research variants are not descriptions of the latest app. Downloaded pretrained research checkpoints and private recordings are not required by the shipped detector.
