# Heart Echo

Heart Echo is an experimental iPhone app for recording and analyzing heart sounds. It runs murmur-pattern analysis on the phone, keeps detected, not detected and uncertain outcomes distinct, and estimates BPM when the signal supports it. Users can review saved results and connect to a care assistant that searches public provider directories.

**This project is a prototype and is not medical advice.** Phone-recording accuracy has not been clinically validated. An absent finding does not rule out heart disease, and the app is not HIPAA compliant in its current demo configuration.

## Project layout

- [`HeartEcho/`](HeartEcho/README.md): current SwiftUI iPhone app, Watch companion, bundled Core ML models, public examples, and native checks.
- [`care-assistant/`](care-assistant/README.md): Mac-hosted Gemini or local Gemma care chat, public-directory tools, tests, and setup instructions.
- [`research/`](research/): model experiments, evaluation code, public-data reports, and third-party notices. Research candidates are separate from the shipping app model; included development results are not independent clinical validation.
- [`ChestBPM/`](ChestBPM/README.md): original measurement app and supporting model/training tools from which Heart Echo was developed.

## Run the demo

1. Follow the [iPhone build instructions](HeartEcho/README.md#build). Xcode and an appropriate signing team are needed for a physical phone; choose your own team in Xcode.
2. Install Node.js 22 or newer. Run `npm ci` in `care-assistant/`.
3. For Gemini, run `Start Gemini Setup.command` and enter your own API key on its local setup page. Never commit the saved key. Local Gemma setup is documented in the care-assistant README.
4. Run `Start Heart Echo Demo.command` on the Mac. Keep the Mac and phone on the same trusted Wi-Fi and pair from the app with the code at `http://127.0.0.1:4318/connect.html` on the Mac.

On-device heart-sound analysis works separately from care chat. Raw audio and recording summaries are not sent to Gemini. Free-tier Gemini must not receive personal or health information; the text filter is incomplete. The phone-to-Mac demo currently uses local HTTP and requires a trusted network. Care listings do not establish insurance coverage or appointment availability.

## Verification

Run `npm test` inside `care-assistant/` for backend, conversation, pairing and directory checks. Native build/test instructions and the limits of prior checks are in [`HeartEcho/INTEGRATION-VALIDATION.md`](HeartEcho/INTEGRATION-VALIDATION.md). Software checks do not measure clinical accuracy.

## Data and attribution

Only public example audio is bundled. Personal recordings, diagnostic captures, credentials, downloaded research datasets, caches, and build products are excluded from this repository. See the [sample-audio license](HeartEcho/Resources/MurmurSamples/LICENSE.txt), [care-service provenance](care-assistant/docs/provenance.md), and [`research/third_party/`](research/third_party/) for source and license details. Research dependencies may have separate restrictions; their checkpoints are not bundled with this snapshot.
