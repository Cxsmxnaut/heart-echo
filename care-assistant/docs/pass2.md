# Second pass: Chest BPM care assistant 0.2.0

Implemented and tested locally on November 14, 2026. The complete component remains under `care-assistant/`. Existing native app/Xcode files, estimator/model/training files, private studies/captures, Watch/devices, signing and unrelated processes were not changed. Native UI/display source was inspected read-only for the small summary mapping. No graph tooling was configured, so no Graphify query/refresh is claimed.

## What changed

- Chest BPM-specific UI and help: positive explanation of microphone/model-based BPM and repeating sound timing; separate usable, unclear and absent summary states; rounded visible BPM; earlier/unknown/future capture-time labels. One persistent limitation replaces repeated dense caveats. A usable timing estimate is never a healthy-heart result.
- Useful FAQ context covers positioning/retry in the iPhone app, optional Watch comparison, and the two distinct AI roles. The browser never records heart sounds. The iPhone model estimates timing independently; the Watch is comparison only. This prototype's separate untuned Gemma runs on the Mac; public directories need internet.
- Confirmed ZIP, category, insurer/plan/network/year/date persist across follow-ups. Unknown-network corrections preserve unrelated known details. Year changes clear incompatible old dates. New payer/plan clears dependent fields. Explicitly labeled/replacement ZIP wins over an old ZIP/street number; genuinely ambiguous numbers cause a question.
- Users can decline insurance checking and still search, request lower-cost health centers, or ask why existing options were shown. “Why these?” explains saved results with their actual ZIP/category/source/plan basis without blindly refreshing directories. No price ranking or guaranteed free care is invented.
- Cards show a public source and retrieval date, contact/address/directions, and a reason. Technical provenance is optional. Self-pay users get fee/contact guidance instead of repeated network warnings. Other payer-listed practices visibly say their match to the chosen category is unconfirmed; they are not counted as confirmed category matches.
- Model failures and service-completed searches are explicitly labeled as guided help. Raw model IDs/codes remain in optional technical details. Current affirmative symptom reports can show a proportional notice; negated/historical/hypothetical wording and later ordinary searches do not inherit a stale interruption. This remains a conservative text rule, not a triage classifier.
- Clear-scan and full-clear are explicit. Failed server deletions retain their IDs and offer a retry instead of implying server memory was deleted. The mobile header has a jump-to-chat control, optional details start collapsed on narrow screens, and the composer respects safe-area spacing.
- The [v1.1 contract](integration-v1.1.md) separates the rolling analysis window from recording length. The [isolated Swift/SwiftUI package](../integrations/README.md) uses only the accepted displayed BPM, never comparison values as substitutes, and omits a capture timestamp when unavailable. No native integration was applied.

## Actual model, interface and evidence

Same untuned Gemma 4 E2B instruction model, attributable Unsloth Q4_K_M conversion, pinned llama.cpp runtime, local alias `care-gemma4-e2b` on port 4320. No fine-tuning was performed. The web UI remains on port 4318.

Extraction now uses a flat, grounded JSON shape and field names rather than old field values as context. This reduced copied-old-value failures found in development, but the final raw intent results below remain poor. The backend does not display unrestricted model medical/provider prose.

Tool evaluation is **constrained/bound tool selection**, not a claim that the model independently generates all correct plan parameters. Search schemas restrict ZIP/category/limit to confirmed values. For an exact-plan check the model selects `lookup_plan_network` with `confirmed_plan: true`; trusted backend code binds the confirmed insurance/year/date/ZIP and executes the full strict read-only MCP tool. Attempts to supply changed plan fields are rejected. Tool traces identify `arguments_basis: server_bound_confirmed_profile`.

Initial pass-1 results and reports are preserved in `evaluation/history/pass1/`; the original files are also retained. Pass-1's 7/12 initial extraction, 1/3 initial tools, development retest, and later 12/12 small fresh result describe that earlier adapter/set. They are not current untouched validation for the expanded conversational task.

## Fresh frozen evaluation — failures retained

`evaluation/pass2-freeze.json` records SHA-256 hashes for 18 implementation files. The new scenario set was created after that freeze and run once. The runner verified the hashes at both start and end. Implementation/prompt behavior was not tuned on the resulting failures. Full results: `evaluation/results.pass2-final.json`; scenarios: `pass2-final-scenarios.json`.

| Measurement | Result |
| --- | --- |
| Raw model fields accepted/correct | **11/16** |
| Raw model expected intent | **2/16** |
| Raw model fields and intent both correct | **2/16** |
| Constrained model tool-selection sequences | **3/3** |
| End-to-end user journeys completed | **9/10** |
| Turns in composed journeys | 19 |
| Turns with backend corrections | 7 |
| Guided-fallback turns | 4, including the deliberately unavailable-model case |
| Service-completed tool calls | 7; not counted as model selection success |

The failed user journey asked for **“Only health centers with possible sliding discounts, please.”** The model returned an unrequested field clear, validation rejected it, and the guided parser did not recognize that phrasing as lower-cost search. The response stayed in a ready state rather than starting that search. The existing **Lower-cost options** button and tested “cheaper options” phrasing work, but that unfamiliar wording remains a real limitation. It was not patched and re-tested on the same supposedly unseen set to force a perfect score.

Other raw failures included unrequested clears and wrong intents for postal correction, unknown network, year correction, explaining existing clinics, uninsured status, two-AI help, usable-versus-healthy meaning, ambiguous location, disease-invention wording, and Watch help. The validation/explicit update rules recovered several composed tasks, but this does **not** make those raw model decisions successful. Rejected extraction is visible as guided fallback; backend corrections are recorded separately.

Completed composed journeys covered unknown-network retention, explicit ZIP replacement, year/date correction and wrong-year rejection, declining insurance while retaining care access, noisy→usable→absent snapshots, refusing invented diagnosis/coverage claims, escaping a stale symptom notice, a model outage, an upstream timeout, and an unverified-category payer role. The cost-paraphrase journey stopped at its failure, so later steps in that specific journey were not claimed tested.

These results do **not** support a broad, reliable free-form chatbot claim. Use the tested controls/forms and concise corrections for this prototype. Next model work should improve or replace the small extraction/intent layer against a new evaluation set; it should not disguise backend repairs as ML accuracy or add fine-tuning just for appearance.

## Other checks

- **55 Node tests passed**, including actual HTTP middleware and actual MCP in-memory/stdio protocol execution. Source records are synthetic fixtures, with real public-source tests kept separate.
- **16 isolated Chrome UI checks passed**, including keyboard input, 390px layout, visible reason/source/date/directions, why-follow-up, clear-scan/full-reset, failed deletion retry, plain-language model fallback, empty/error states, and jumping to the composer and sending a follow-up after **ten cards**. The unavailable in-app browser was attempted; isolated Chrome was the working fallback. This does not claim a physical phone keyboard test.
- **11 Swift tests passed**. The standalone package and SwiftUI preview compiled with the macOS SDK. Tests cover accepted-BPM-only mapping, null/invalid/unclear semantics, window versus recording length, absent timestamp, allowed fields, consent, URL rules, HTTP failure, and send→clear scan→failed full deletion→same-ID retry. No physical iPhone/Watch application was installed/tested by this component.
- Actual live browser/model/public-directory checks are recorded separately in `browser-live-results.json`; they distinguish user-task completion, actual model-selected calls and any guided fallback. The synthetic Swift CLI live handoff is also checked separately. Public APIs, model inference, synthetic fault injection and fixture tests are never silently substituted for one another.

## Native work remaining

The prepared package, synthetic CLI and reviewable host insertion are ready for review. The running app still needs an explicitly configured authorized connection/authentication, the optional entry point added after active native work settles, and a complete native care UI or secure browser-session handoff. The provided SwiftUI sheet is a consented summary preview only. This Mac's loopback URL cannot be used from a physical phone. There was no public deployment or global configuration/service change.
