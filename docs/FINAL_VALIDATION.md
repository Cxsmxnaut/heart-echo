# Final app validation — 0.4.1 (6)

[Overview](../README.md) · [Judge walkthrough](JUDGE_GUIDE.md) · [Results](RESULTS.md) · [Submission checklist](SUBMISSION.md)

**The five improvements are implemented, and Debug and optimized Release simulator builds passed.** The nine selected native UI journeys have passing results across the full and focused runs described below. Release result sharing also passed, and its installed executable matches the packaged Release app. This is local engineering evidence; no new physical-phone installation, public GitHub update, hackathon submission or organizer confirmation is claimed.

## The five implemented changes

| Change | What is present in the source |
|---|---|
| Live recording coach | Real engine reasons produce practical quiet/clipping/contact/noise/timing guidance. BPM stays pending when no accepted estimate exists. |
| Text result sharing | Immediate and saved results open a text-only system share action with the actual finding, available measurements and limitations. Audio, private paths, internal IDs and raw errors are excluded. |
| Bounded AI wording | Gemini generation, model fallback and safety rewrite share a 12-second default budget. A timeout is labeled; validated directory cards remain available. Directory requests have their own timing. |
| Unpaired care quick start | A standalone five-digit ZIP starts native public-directory search without a Mac connection or AI key. Internet and available directory sources are still required. |
| Isolated judge startup | `npm run judge` explicitly selects guided mode, ignores saved/inherited AI settings, avoids local model startup and pairing changes, and chooses an available loopback port. |

## Completed checks

| Check | Recorded result | Scope |
|---|---|---|
| Backend regression suite | **101 tests passed** | Deterministic fixtures and HTTP/MCP protocol behavior, including AI deadline and isolated judge startup cases. |
| Browser checks | **16 scenarios passed** | Isolated Chrome, synthetic directory fixtures, real backend/MCP, guided mode. [Saved report](../care-assistant/docs/browser-test-results.json). |
| Native product/engine checks | **289 assertions passed** | BPM 125; murmur 13; recording/result 49; storage 16; care 28; recording guidance 19; ZIP intent 39. Collector and origin checks also exited successfully. [Saved report](../HeartEcho/Docs/product-checks-final.json). |
| Source-packager checks | **6 tests passed** | Temporary fixtures cover private/cached data exclusion, exact-case relative links, public sample provenance, reproducibility, overwrite refusal, symlink/path escape/tamper rejection and Git-free verification. No real submission artifact is implied by these fixture tests. |
| Debug and Release simulator builds | **Passed** | Xcode 27.2; arm64 iOS 27.2 Simulator; version 0.4.1 (6). The Release app uses the project's optimization settings. |
| Selected native UI journeys | **9 unique journeys have passing results** | Standalone live ZIP search, draft preservation, developer-mode persistence, permission denial, actual public-model result/history/explanation/deletion, new/saved text sharing, unsure preservation, large-text result sharing and the large-text microphone-off coach preview. See run history below. |
| Release UI check | **1 test passed** | A fresh Release simulator installation ran real public-model inference and shared/cancelled both the new and saved text summary. Finding and history stayed intact. The installed executable SHA-256 matches the packaged Release executable. |

These are engineering checks. They do not establish clinical effectiveness, independent phone accuracy, current Gemini availability or current public-directory coverage.

## UI run history

| Run | Result and follow-up |
|---|---|
| Initial selected run | **6/9 passed.** The public-example wait, share-menu dismissal and large-text coach lookup failed. The early result bundle was incomplete; console results were retained. |
| Focused investigation | **1/3 passed.** Public result/history passed. Screenshots showed that sharing used an iOS popover and that the coach card's accessibility ID overwrote its children's IDs. The parent ID was removed; the test now uses the observed popover dismiss region without selecting a destination. |
| Full run on corrected app | **8/9 passed.** All five product tests and both care tests passed; the coach passed. The remaining failure occurred before analysis: full-screen test swipes jumped past the public sample button at the largest text size. |
| Focused large-text rerun | **2/2 passed.** Short, controlled drags reached the actual sample, expected model result, summary action and coach. The first public-example wait failure did not repeat in the later product runs; its original cause remains unconfirmed. |
| Final viewport check | **2/2 passed.** The same large-text tests also required the complete target control to clear navigation and the fixed care bar. Screenshots were inspected. |
| Release sharing | **1/1 passed** on a fresh Release installation. The executable was verified against the packaged app. |

This is not a claim that the last full nine-test run was all-pass: it was 8/9, followed by the passing focused rerun. Screenshots and test summaries are preserved. No audio-model weights, inference rules or clinical labels were changed to make UI tests pass.

## Artifact and submission status

The submission folder supplies `START_HERE.md`, the source and Simulator archives, selected public-example screenshots, `VALIDATION.json` and `SHA256SUMS`. The source archive carries its own per-file manifest. The outer validation record associates archive hashes with manifest verification and the fresh-extraction startup check, avoiding a source archive that must contain its own hash.

This pass has not published the local changes to GitHub or sent the hackathon form. Use the supplied source snapshot for this version. Team names/emails/schools, a final public code link and organizer confirmation remain submission fields. The Simulator archive is not an iPhone-installable IPA; physical installation requires development signing.

## Reproduce the checks

From the repository root:

```sh
cd care-assistant
npm ci
npm test
npm run test:browser
cd ..
python3 HeartEcho/Tools/check_product.py
python3 -m unittest discover -s tools -p test_package_submission.py -v
```

For a private, keyless browser review, run `npm run judge -- --no-open --port 0` inside `care-assistant/` and use its printed URL. That mode uses guided application logic; it does not claim generated AI conversation.

The source packager accepts a new destination with `python3 tools/package_submission.py --output PATH_TO_NEW.zip` and verifies an existing archive with `--verify PATH_TO_EXISTING.zip`. It excludes credentials, private captures, caches, generated/research weights and local draft media. Verification checks the manifest, file hashes, expected source/model/sample files, public sample provenance and relative links. It never proves that the hackathon form was sent.

## Preserved evidence and limits

The shipped phase-aware murmur model and BPM/DSP path are unchanged. The app's reused public-development result remains 49/70 positive recordings detected, with 8 positive recordings called absent, 13 positive recordings unsure and 5 false alarms among 274 absent recordings. Research alternatives and their failed comparisons remain in [the model decision](../research/murmur-model-decision.md); they are not the shipped detector.

Private recordings and phone profiles remain local and excluded. Public examples are not the user's heart recording. Present, absent, unsure and unavailable remain distinct. An absent result does not rule out heart disease, and care listings do not establish insurance coverage or appointments. Existing [credits](../CREDITS.md), public-data licenses, original contribution disclosures and [earlier device observations](../HeartEcho/INTEGRATION-VALIDATION.md) remain intact.

An early simulator install explicitly failed for insufficient host storage. Only duplicate download archives and regenerable numeric feature caches were cleared; original audio and every learned checkpoint were retained. A later result bundle exported correctly. No configured Graphify graph or managed launcher was present, so inspection used current source and measured checks.
