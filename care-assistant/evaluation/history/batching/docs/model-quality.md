# Model quality and local hardware tradeoff — 0.3.0

E4B is the accuracy-first local default. E2B remains a configurable speed option. The code separates choosing the user's intent from extracting newly supplied fields. Tool selection still uses a small set of allowed tools, and the backend supplies confirmed plan arguments before validated MCP execution. Factual answers and cards come from validated app facts and public directory records. No fine-tuning was performed.

## Evidence kept separate

| Run | Set status | Raw intents | Raw fields | Raw median request-pair time |
| --- | --- | --- | --- | --- |
| Preserved pass 2, E2B combined task | Former final, unchanged | 2/16 | 11/16 | See original report |
| E2B split tasks, temperature 0 | Development: 16 seen cases + 8 added cases | 21/24 | 21/24 | 6.832 s |
| E2B split tasks, temperature 1 | Development probe: first 12 cases only | 11/12 | 12/12 | 8.015 s |
| E4B split tasks, temperature 0 | Same 24 development cases as E2B temperature 0 | 24/24 | 22/24 | 14.745 s |

The development runner labels declining insurance details as `find_care`, matching the product definition; the original pass-2 labels and results remain unchanged. These runs are not all directly comparable. The improvement combines a task split and a model change; it is not evidence that model size alone caused it. All tests are small prototype checks, not clinical validation.

E4B's two raw field failures remain in the report: “I forgot my plan name” omitted the requested plan clear, and a short `plan: …; network: …` message omitted both labels. No phrase-specific patch was added to make those cases pass. The development multi-turn cost journey completed with model-selected tools, no guided turns, and no backend corrections.

Original evidence: [pass-2 report](../../../../docs/pass2.md), [unchanged pass-2 results](../../../results.pass2-final.json), [E2B development](../../../results.dev.e2b-split-t0.json), [E4B development](../../../results.dev.e4b-split-t0.json), [sampling probe](../../../results.dev.e2b-split-t1-probe.json).

## Selected configuration and resources

Actually tested: **Apple M4, arm64 macOS, 16 GiB RAM**. No other hardware, physical iPhone runtime, or production workload was tested. Only one model was loaded during each comparison. Other work was running on this Mac, so latency and responsiveness are shared-system observations.

Selected weights are public Gemma 4 E4B instruction, Unsloth Q4_K_M, 4,977,171,584 bytes. Revision and SHA-256 are pinned in [model artifacts](../scripts/model-artifacts.js) and [the implementation freeze](../../../quality-freeze.json). Runtime: pinned llama.cpp b12248 with native Jinja/template, context 8192, one slot, two CPU threads, no RAM prompt cache, reasoning off and budget 0. Requests use temperature 0, top-p 0.95, top-k 64 and thinking disabled. See [provenance](../../../../docs/provenance.md).

Before final testing, `memory_pressure -Q` reported 26% system memory free with only E4B loaded, and disk had about 14 GiB available after both weight downloads. Memory free percentage is a system report, not a complete per-process memory estimate. E4B is slower: its raw classification/extraction pair took about twice as long as E2B on the same development set. Full care turns also require tool selection and public-directory requests and can take substantially longer. During final testing the system also reported about 8.5 GiB of swap in use and 28% free memory. There is no clean pre-load swap baseline, so this cannot be attributed to E4B alone. Some ordinary command calls took several seconds; the fresh-run probes below are a narrower measurement. For concurrent heavier work, try E2B first. This is a local accuracy-first demo default, not a recommendation for broad deployment on 16 GiB machines. See [resource observation](model-resource-check.json).

For the faster choice, stop only the care model process, set `MODEL_VARIANT=e2b` and `LLM_MODEL=care-gemma4-e2b` in `.env`, run `npm run model:setup`, then `npm run model` and restart `npm start`. E2B uses about 3.2 GB of model/runtime disk space; E4B needs about 5.1 GB. The setup guard requires 16 GiB for E4B and 12 GiB for E2B, but those minimums are not performance guarantees. Keep one model loaded. Guided mode remains available with `LLM_PROVIDER=guided`; model failure is visibly labeled, with service-completed tools distinguished in telemetry. No automatic model swapping or unrelated process termination is used.

## Fresh post-freeze check

The source/configuration was frozen before creating [eight new raw cases](../../../quality-final-scenarios.json). The new runner also checks two constrained tool-selection tasks and five short journeys, including corrections, lower-cost follow-up, saved-result explanation, absent/unclear scan, wrong plan year, an injected model outage and an injected directory timeout. The first run is retained in [results.quality-final.json](../../../results.quality-final.json); repeat runs are reproductions. No tuning follows its results in this pass.

Raw intent and raw fields are scored independently before backend corrections. Tool scores mean selection from constrained schemas: exact plan data is server-bound, not independently generated by the model. Journey completion can use guarded backend rules or explicit fallback; correction, service-call and fallback counts are reported separately. The model-outage case is an injected failure, not real inference success. Directories in this final set are fixtures; separate live browser/smoke reports use actual public APIs.

The first fresh run passed **8/8 raw intents, 8/8 raw field extractions, 2/2 constrained tool tasks, and 5/5 journeys**. Its raw request-pair median was **15.994 seconds**. The 9 journey turns included one explicitly injected model outage: that one turn used guided fallback, backend adjustments and two service-completed searches. The remaining eight turns used the model, with no backend corrections or service-completed tool calls. The directory-timeout case correctly returned source errors rather than pretending there were no providers.

The first multi-turn correction/cost/reason journey took 85.870 seconds over four turns. The three-tool fixture sequence took 44.793 seconds; the single affordable-clinic tool took 7.509 seconds. These are concrete UX limits even when raw intent is correct.

During the eight raw request pairs, tiny Python-start/file-read probes took **0.262–1.970 seconds**, median 1.273 seconds. Memory free was 29% before and the final system reading is recorded in the JSON. These limited probes do not cancel the observed multi-second command delays or substantial swap use on this shared Mac.

Regression checks passed: **58 Node tests, 16 browser fixture checks, and 11 isolated Swift package tests**. The first restricted Node run could not open four loopback test listeners; the approved loopback rerun passed all tests. See [regression evidence](quality-regression-results.json). The original pass-2 result file still matches its archived bytes (SHA-256 `41bf646a1c9d87cedec3a3d2d0718b43e83d414b54ce54023a675e8e04f585e3`).

Live public-source/browser and synthetic Swift handoff results are recorded separately below.

## Remaining limits

This remains a bounded care-navigation prototype. Unfamiliar wording may miss fields or route to a generic app-help answer. A failed model turn can still complete through explicit guided fallback; that is not raw model success. Directory limits, exact-ZIP sampling, unsupported insurers, unverified payer-role specialty, fees, eligibility and appointment availability remain as documented in the README. Native work is prepared as an isolated opt-in package, not applied to the Xcode app. No native, estimator, training, capture, study or device settings were changed in this pass.

## Bounded batching experiment and validated default

A separate adapter set `parallel_tool_calls: true` and asked for all independent native calls in one response. It used two already-seen synthetic scenarios. The unchanged production handler still bounded the call count, checked exact ZIP/category/limit, and bound plan details before validated MCP execution. Neither the frozen source nor the fresh final result was modified.

Both cases completed in one model response: the three-tool exact-plan case took **14.136 s**, and the two-tool uninsured case took **10.996 s**. All executed tool calls had `origin: model`; no service completed missing calls. The three-tool observation is much faster than the separate fresh serial case at 44.793 s, but the messages and run conditions differ, so this is directional evidence, not a controlled speed ratio. The source calls themselves still execute sequentially in the existing handler; the saved work is additional model requests.

This promising two-case experiment is retained as a reproducible candidate, not silently substituted for the frozen implementation or presented as a fresh held-out score. That experiment itself was not deployed. A subsequent, separately frozen configurable implementation was checked on new tool cases before enabling batch mode. [Experiment runner](../../../batching-experiment.js), [actual results](../../../results.batching-experiment.json).

## Post-freeze batching change

Batching is now the running default. `LLM_TOOL_MODE=batch` asks for the required independent native function calls in one response; `LLM_TOOL_MODE=serial` retains the earlier routing. Calls still execute through the same per-call validators and MCP client, with the four-call bound, retry/missing-call fallback and model/service traces intact. No unrestricted model prose is rendered.

This changes `src/model.js` **after** the original quality freeze. Do not treat the original whole-source freeze as identical to the running version. The intent and field prompt strings are byte-for-byte unchanged (SHA-256 `249b3ac16bc3fa9b276ef8418a95666809dfaeddd60183528357c016ecb68e0e` and `e497e92f06185aa8bcc40b20add7ec262ae511726d4a7049274d9f702513fa3a`). The original fresh 8/8 intent and 8/8 field evidence remains historical evidence for those unchanged tasks, not a new whole-system held-out score. [Batching freeze](../../../batching-freeze.json).

Four new tool-selection scenarios were created after the batching freeze. Three passed first time: only affordable clinics (5.452 s), supported plan plus both care sources (13.676 s), and skipping a stored plan (10.402 s). All completed in one model response with model-origin calls and no backend completion. The app-privacy case correctly called `get_app_context`, but the first scorer looked for `privacy` at the top level instead of `sections.privacy`, causing a **test harness failure**. The first report is preserved as 3/4, not rewritten. Only the scorer path was fixed; the privacy case was rechecked once and passed in one response (3.659 s). No prompt, model or production-code adjustment followed these cases.

See [new cases](../../../batching-final-scenarios.json), [first result including scorer failure](../../../results.batching-final.first.json), and [privacy scorer recheck](../../../results.batching-privacy-recheck.json). Reproduction runs use `node --env-file-if-exists=.env evaluation/batching-final.js --reproduction` and write a separate reproduction result. `npm run evaluate:quality` protects the earlier serial freeze and correctly rejects the changed source; its archived source is under `evaluation/history/quality/`.

All **60 Node regression tests** passed after the change. A browser loading-state assertion initially missed the fixture's 150 ms delay under shared load. Its failure is retained in [the failure log](../../../../docs/browser-loading-test-failure.txt); the test now holds its own directory fixture until the loading state is observed, then releases it. All 16 browser checks passed on recheck. This changes the test timing control, not the product UI.

## Live checks on the selected batching version

All six [live smoke checks](live-smoke-results.json) passed: NPPES, HRSA, unsupported CMS plan status, the narrow supported 2027 payer chain, rejection for 2026, and a real two-turn model/MCP conversation. That conversation took 46.626 seconds, compared with 61.834 seconds in the earlier serial live run. These separate runs are observations, not an isolated benchmark.

All four [live browser checks](browser-live-results.json) passed in isolated Chrome. All five recorded model turns used E4B batch mode with **zero backend corrections, guided turns or service-completed calls**. Both the uninsured search and supported-plan form used model-selected calls and live source cards. The supported-plan tool sequence took 14.638 seconds; the uninsured search tools took 12.217 seconds. The form selected the explicit future year, payer-role specialty stayed qualified, the reason follow-up reused saved cards, and the 390px page had no horizontal overflow. Screenshots were visually inspected. The in-app browser backend was unavailable; no personal browser tabs were used.

The [synthetic Swift CLI handoff](native-live-results.json) passed against the running batch backend and deleted its own session. It sent only the accepted synthetic BPM and 8-second analysis window, omitted an unknown capture time, and displayed a rounded 74 BPM. The isolated Swift package still has 11 passing tests; no live iOS app/device integration was tested.

At handoff, health checks pass for `http://127.0.0.1:4318` and model port 4320. Exactly one selected E4B model server is listening; temporary 4322 is closed. The final system observation was 34% free memory with approximately 9.4 GiB swap used. This is still a shared-machine observation with no clean baseline. E2B remains the documented speed option, and serial tool mode remains configurable. Native insertion, endpoint/authentication and device/network work remain as listed in [the native handoff](../../../../integrations/README.md). All changes are under `care-assistant/`; no commit or external deployment was made.

## Independent review after handoff

The coordinating chat independently reported these checks passing against the running E4B/batch server: a usable synthetic v1.1 summary returned a timing-only explanation; an unclear summary with numeric BPM was rejected with HTTP 400; a natural-language network clear preserved the Example Health/Copper Choice labels without backend correction or fallback; explicit `scan: null` removed the existing session attachment; and HTTP 204 confirmed deletion of that synthetic session. The reviewer also inspected the updated mobile screenshot and native session-ownership code. These are reported independent checks, not a second execution by this implementation chat.

No further implementation was requested. Native integration remains staged in `integrations/`; no insertion into the Xcode app, device installation, endpoint/network change or signing change was applied.
