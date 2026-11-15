# Archived design-preview history

These notes describe the earlier UI-only preview, before the measurement-engine port. They are kept for design provenance and attribution. Current functionality is described in the main README.


# Heart Echo — iPhone UI

A separate native SwiftUI app for designing the real product. The experimental ChestBPM and care-assistant projects are independent of this app.

The first visual direction takes cues from Apple Health: native navigation, a light grouped background, white rounded cards, bold system type, and pink/red accents. Colors also adapt to the system appearance.

This version uses sample data only. It does not record audio, run a model, request health or location access, contact provider directories, or save health information. The recording and AI conversation are interactive visual previews. Chat messages stay only in view memory; suggested questions use fixed sample replies, and typed messages receive an explicit preview response.

Open `HeartEchoApp.xcodeproj`, select the **HeartEchoApp** scheme and an iPhone simulator, then Run. A physical iPhone needs a development team selected in Xcode's Signing & Capabilities settings.

## Screens

- Home: recording entry point, recent sample recording, and care entry point.
- Record: preparation, a simulated recording, then an automatic handoff to Heart Echo AI with the sample result already visible.
- AI: a possible-finding card, a reminder that the app can be wrong, a provider-search link, suggested questions, and a sample chat composer. The illustrative murmur-like finding is supplied separately from BPM and audio quality; it is never inferred from them. It is not a diagnosis.
- Recordings: sample history and recording details.
- Care: illustrative providers and filters; no actual provider or insurance claims.

## Local build

```sh
xcodebuild -project HeartEchoApp.xcodeproj -scheme HeartEchoApp -sdk iphonesimulator -configuration Debug -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

No external packages or configured Graphify graph. Important UI values live in `DesignSystem.swift`; sample recordings live in `SampleData.swift`.

## Capture screenshots

With a booted iPhone simulator, Python with Pillow, and the Debug build above:

```sh
python3 Tools/capture_previews.py --device '<booted simulator UUID>'
```

This saves real simulator screenshots under `Previews/`. Debug-only launch values open each existing screen directly and set appearance for that launch. They do not change device settings or add a production entry point. The script finishes by relaunching the ordinary Summary screen using system appearance.

Use `--screen result --screen assistant-chat` to capture the new AI screens. `--screen record-finished` starts the actual sample recording timer, waits for completion, and captures the automatic handoff, rather than opening the result directly.

## Verification

The Debug simulator build passed with Xcode 27.2. The app was installed and launched on the iPhone 18 Pro simulator as **Heart Echo**. Real screenshots cover Summary in light and dark appearance, plus Recordings, Care, preparation, simulated recording, and the sample result in light appearance. Screens were opened directly with Debug launch values and visually reviewed. These checks also caught a missing phone symbol and overlapping animated countdown digits; both were corrected.

A full tap-through check was not completed: Device Hub's UI automation connection failed during interaction. Larger accessibility text sizes have not been visually reviewed yet. No physical-device installation was performed.

### Recording-to-AI update

The updated Debug build passed. The actual 20-second simulated recording was started in the iPhone simulator, allowed to finish, and visually confirmed to open Heart Echo AI automatically with the sample finding, the app-can-be-wrong reminder, the provider link, and the chat controls. `Previews/record-finished-light.png` records that timer-driven transition. `Previews/result-light.png` shows the same destination opened directly for design review; `Previews/assistant-chat-light.png` shows an example exchange. Replies are fixed UI examples, not model output. The provider link and suggested-message handlers have been checked in source; full tap-through and keyboard interaction remain unverified.

### Unslop pass: result and assistant screens

Applied [Unslop](https://github.com/heydamir/unslop) by [Damir Sokolovsky](https://github.com/heydamir), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with its guidance adapted to native SwiftUI. The user chose to limit this pass to the result and AI screens. The other app screens retain their existing design.

Direction:

- Product: review a heart-sound recording and choose a next step.
- Character: factual, calm, familiar.
- World: a native iPhone health record, keeping system type and the existing pink accent.
- Moments: the finding and recording measurements carry the emphasis; navigation and chat controls stay neutral.
- Signature: a compact recording summary carries the result into the conversation.

Passes:

1. Spacing: consistent 4-point steps, aligned metric columns, and controls at least 44 points tall.
2. Color: neutral text and surfaces; pink reserved for the provider action and enabled send button. Local light/dark accent variants improve contrast.
3. Icons: removed the sparkle tile, colored metric icons, and decorative prompt icons.
4. Copy: replaced the opening speech with a direct question; retained the app-can-be-wrong reminder, diagnosis limitation, and provider option.
5. Type: sentence-case labels, regular and medium body text, semibold native headings, and tabular measurement digits.
6. Layout: compact result summary, followed by the conversation and suggested questions in their original order.
7. Details: native-style question rows replace prompt pills; assistant replies use plain text, with a quiet surface only for the user's messages.
8. Visuals: kept the actual sample recording content; added no stock imagery or decorative waveform.
9. Motion: retained the existing conversational scroll; added no entrance effects, looping motion, or bouncing controls.

Before screenshots are preserved as `Previews/unslop-before-result-light.png` and `Previews/unslop-before-assistant-chat-light.png`. Use `--appearance dark` with selected screenshot screens to check their dark appearance. Sample replies and the recording-to-assistant flow remain unchanged in behavior.

Verification: the updated Debug build passed, and `Previews/result-dark.png` was visually confirmed to show the revised Heart Echo result/assistant screen. The local accent variants have contrast ratios of 5.77:1 against white in light appearance and 7.28:1 against black in dark appearance; the enabled dark send button uses dark ink. This is a check of those accent combinations, not an accessibility certification of the whole app. The shared simulator switched to another app during the light screenshots. A separate preview simulator failed to complete app installation after a restart and two 180-second installation attempts. Full-chat and light-mode visual checks remain pending. The light screenshots at `result-light.png` and `assistant-chat-light.png` retain the verified pre-pass images; they do not show the revised UI. Use a dedicated, fully started simulator for future captures and visually verify that every captured screen belongs to Heart Echo.

### Phone chat layout

The user supplied an iPhone ChatGPT screenshot as the next visual reference. This revision changes the assistant screen, including its post-recording presentation; the other tabs retain their existing design.

- Plain system backgrounds, right-aligned user bubbles, and unboxed assistant text replace the grouped result-and-question panels.
- A recording attachment opens a detail sheet. The possible finding and app-can-be-wrong reminder appear in the first assistant reply, followed by the provider link.
- A rounded composer contains the recording/sample-question menu and send control. The footer always labels the conversation as a sample and reminds users that Heart Echo can be wrong.
- The toolbar supports a new conversation about the same recording, recording details, and provider navigation. Assistant replies have a local copy action. Example replies support emphasis, paragraphs, and numbered questions.
- Recording completion still opens the assistant automatically. The chat uses fixed sample replies; no model, audio capture, speech service, account, or chat database has been connected.

To keep this revision's screenshots separate, pass `--output-dir Previews/phone-chat` to the capture tool. After installing this exact build once, use `--skip-install` for additional appearance captures.

Verification: the current Debug simulator build passed. Native screenshot capture could not proceed because simulator installation exceeded 180 seconds; Device Hub control also failed to respond. Native visual and tap-through checks for this revision remain pending. The accompanying in-chat design preview is a separate interactive representation, not a native simulator screenshot.
