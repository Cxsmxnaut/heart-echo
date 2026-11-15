# Opt-in native handoff — prepared, not applied

This independent Swift package does not depend on the estimator, WatchLink, HealthKit, audio engine, study state, logs or captures. No existing native/Xcode files were edited and no device application was installed.

`swift/` contains a snapshot builder, Codable v1.1 summary, async HTTP client, session owner with deletion retry, optional SwiftUI preview, and synthetic CLI example. The preview sends nothing on appearance: the user must tap **Send this summary**. Its summary and session owner use SwiftUI `@State` identity, so parent redraws cannot replace the frozen snapshot or lose the server session ID. Clear-scan sends explicit null when a server session exists; full clear deletes that session and preserves its ID if deletion fails, enabling retry.

The sheet is a **handoff preview**, not a complete native care-search/chat screen. The full care UI is the browser page. The client requires explicit consent for summary submission, allows remote HTTPS or loopback HTTP, and contains no hardcoded token. This prototype's Gemma model runs on the Mac, not on the phone.

## Mapping the current display

The native screen was inspected read-only in `ChestBPM/ChestBPM/ChestBPMApp.swift`. The orchestrator supplied the meaning of `r.seconds`: the rolling analysis window, up to about 8 seconds. Estimator/model source and private data were not read for this work.

| Native value | Handoff rule |
| --- | --- |
| `r.bpm` | The only accepted `estimated_bpm`. Never substitute a comparison counter if nil. |
| `r.original`, `r.cycle` | Optional repeating-pattern/full-cycle comparison counters. Omitted from the wire by default. They never rescue a missing accepted BPM. |
| `r.seconds` | `analysis_window_seconds`, not study or recording length. |
| Genuine measurement timestamp, if available | Optional `captured_at`. Omit when unknown; do not invent it from navigation/sheet-opening time. |
| No accepted result | `unclear` or `unavailable`, with `estimated_bpm: null` even if comparison counters have numbers. |

No waveform, marks, raw recording, Watch reading/identifier, participant identity, diagnostic feature array, or study metadata is sent. Quality means acceptance of a timing estimate, not disease-screening quality or a healthy heart.

## Minimal reviewable insertion

After active app work settles, add the local package's `ChestBPMCare` library to the intended target and review `ContentViewInsertion.swift.example`. The host must inject a separately configured `CareClient`; no Mac IP, entitlement/signing change or shared production secret is guessed.

The button snapshots the displayed accepted BPM and rolling-window duration once. It does not start/stop audio or the Watch. The user reviews the frozen summary and explicitly chooses whether to send it. Check field types and placement against the then-current app source before applying this fragment.

Remaining native work: wire an authorized endpoint/authentication into the host, add the opt-in entry point after current estimator changes settle, and implement a complete native care flow or a separately designed secure browser-session handoff. Do not place health summaries or session IDs in URL query strings. Physical phone connectivity, hosting, production authentication and permission/network policy remain separate authorized work.

## Verification

From `care-assistant/`:

```sh
swift test --jobs 2 --package-path integrations/swift --scratch-path .cache/swift-build
swift run --jobs 2 --package-path integrations/swift --scratch-path .cache/swift-build CareHandoffExample
```

The package and SwiftUI view compiled with the macOS SDK. **11 tests passed**, covering accepted-BPM-only semantics, nil/invalid values, analysis-window labeling, absent timestamps, allowlisted fields, consent, explicit null clear, server deletion/retry, URL restrictions and HTTP failure. No iOS device runtime or live native app integration was tested.

The synthetic CLI expects `http://127.0.0.1:4318`, with optional `CARE_BASE_URL` / `CARE_API_TOKEN`. Loopback refers to the client device; it does not let a physical iPhone reach this Mac. The CLI sends one synthetic summary and then deletes its session.
