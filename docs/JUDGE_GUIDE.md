# Judge walkthrough

[Overview](../README.md) · [Results](RESULTS.md) · [Credits](../CREDITS.md)

## A five-minute review

Read the README for the intended user and working flow, then the results table for missed cases, false alarms and uncertainty. Choose a run route below. No hosted app or TestFlight distribution is included; physical iPhone installation requires your own development signing.

## Route A: browser care search without a key

Requires Node.js 22+ and npm. From a fresh clone:

```sh
git clone https://github.com/Cxsmxnaut/heart-echo.git
cd heart-echo/care-assistant
npm ci
LLM_PROVIDER=guided npm start
```

Open `http://127.0.0.1:4318`. Enter `Find care in 10001` and skip insurance. Internet is needed for live public directories. Provider and community-health-center cards include source links; unavailable sources are reported rather than replaced with invented records.

**This route uses guided application logic, not generated AI replies.** It needs no API account. A fresh clone has no credentials. A saved Gemini key takes precedence over guided mode in an existing configured copy, so use a separate fresh clone for this route. Stop with Control-C.

## Route B: real audio inference on iPhone or simulator

Requires macOS, Xcode with an iOS Simulator runtime, and the bundled Core ML packages. The app targets iOS 17+. The latest physical development build reviewed was 0.4.0 (5).

1. Open `HeartEcho/HeartEchoApp.xcodeproj`; choose the **HeartEchoApp** scheme and an available iPhone simulator. For a physical phone, choose your own signing team for the app and Watch targets.
2. Build and run. On **Summary**, tap **Try a public example** and analyze a sample. No microphone permission or cloud key is needed.
3. Confirm the result opens before chat. In prior checks, the present-reference sample produced **Murmur-like pattern**; absent- and unknown-reference samples produced **Unsure**. Reference annotations and model predictions are separate. These examples do not imply perfect detection.
4. Open **Recordings**, reopen the example and inspect its finding/source. Delete only a sample created for your review.
5. Tap **Find care with AI** to open the same Care chat used by the Care tab. Generated conversation needs the Mac connection described below.

The examples are public stethoscope recordings. They exercise real model inference, not the accuracy of an iPhone microphone. Use public examples for a competition demonstration rather than collecting private health data.

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

Provider names come from validated directory data. New replies remain above the cards. Limits/outages are labeled; fallback is not counted as a successful model reply. Directory entries and generated wording can change.

The current settings use `gemini-3.5-flash` with `gemini-3.5-flash-lite` fallback for request-limit/temporary-unavailable errors. Model availability depends on your project; override `GEMINI_MODEL` and `GEMINI_FALLBACK_MODEL` if needed. No API key is included.

**Use sample details only.** Audio and results are withheld from Gemini, but filtering of sensitive typed text is incomplete. Google prohibits sending personal/sensitive information to unpaid services: [terms](https://ai.google.dev/gemini-api/terms). The local phone-to-Mac connection uses HTTP. This is not a patient-data service.

## Reproduce the checks

Backend fixtures and protocol checks need no key or live directory access:

```sh
cd care-assistant
npm ci
npm test
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

More storage/capture and historical UI checks are in [the integration record](../HeartEcho/INTEGRATION-VALIDATION.md). Training requires additional public downloads and Python dependencies. Judges do not need to retrain to run the included detector.

## Where to look in the code

| Question | Entry point |
| --- | --- |
| Model inference and uncertainty | [MurmurAnalysis.swift](../HeartEcho/Engine/MurmurAnalysis.swift), [NeuralSignal.swift](../HeartEcho/Engine/NeuralSignal.swift) |
| Recording and durable history | [HeartEchoStore.swift](../HeartEcho/HeartEchoApp/HeartEchoStore.swift), [RecordingFiles.swift](../HeartEcho/HeartEchoApp/RecordingFiles.swift) |
| Result-first flow and shared chat | [RecordingFlowView.swift](../HeartEcho/HeartEchoApp/RecordingFlowView.swift), [AssistantView.swift](../HeartEcho/HeartEchoApp/AssistantView.swift) |
| Data leaving the phone | [CareService.swift](../HeartEcho/HeartEchoApp/CareService.swift) |
| Generated replies and fallbacks | [service.js](../care-assistant/src/service.js), [model.js](../care-assistant/src/model.js) |
| Directory evidence | [directories.js](../care-assistant/src/directories.js), [healthplan.js](../care-assistant/src/healthplan.js) |
| Training and model origins | [Provenance](../ChestBPM/ML/PROVENANCE.txt), [research decision](../research/murmur-model-decision.md) |

`ChestBPM/` is preserved for provenance and reproducibility. Historical UI descriptions and research variants are not descriptions of the latest app. Downloaded pretrained research checkpoints and private recordings are not required by the shipped detector.
