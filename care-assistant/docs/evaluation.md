# Evaluation and actual verification

**Historical pass-1 report.** Current second-pass results, including remaining failures, are in [pass2.md](pass2.md). The old small-set scores below are preserved history, not current untouched validation.

Tested locally on November 14, 2026. This is an **untuned, quantized Gemma 4 E2B instruction model**, not a fine-tuned or clinically validated model. All user/scans/test identities were synthetic. The public smoke/browser runs used live public directory records; deterministic tests used explicitly synthetic fixtures.

## Model baseline and changes

| Run | Raw extraction | Raw model tool use | Interpretation |
| --- | --- | --- | --- |
| Initial baseline, `results.initial.json` | 7/12 | 1/3 | Original held-out set at its first use. Missing fields sometimes became the literal string `"null"`; the model inferred an unrequested specialty, chose an invalid search limit, or classified intent incorrectly. Backend rejected unsafe/invalid values. |
| Development retest, `results.development.json` | 9/12 | 2/3 | Same cases after inspecting failures, so these are development/regression results, **not untouched held-out validation**. Noisy-recording parsing/intent, privacy/search intent, and copying the complete plan remained imperfect. Failures are preserved. |
| Fresh final held-out, `results.final-held-out.json` | **12/12** | **3/3** | New disjoint message scenarios, run once after freezing the final model adapter. The model source hash is recorded in the report. Separate backend checks passed 5/5. |

The final adapter uses a fixed nullable extraction shape and explicit definitions for absent labels, insurance status and specialty choices. Submitted labels must occur in the user's message. The model cannot turn a BPM into a specialist search. The tool schemas are narrowed to the confirmed ZIP/specialty/insurance values. Required care searches use `tool_choice: required`, and the backend validates calls independently. This tests **constrained model function calling**, not unrestricted agent planning. The visible medical/provider facts are rendered from application knowledge and directory results; unrestricted model prose is discarded.

The backend can independently complete missing required tools, with `origin: service` in the trace. That is useful fallback behavior and is **not** scored as raw-model tool success. The final three raw tool-use cases executed every required tool with `origin: model`. The backend safety checks separately covered partial insurance/no scan, wrong plan year, changed plan clearing old network/ID, noisy scan plus upstream timeout, and an adversarial invented-plan call. The adversarial call used an explicitly labeled protocol double to guarantee the malicious arguments; it was not passed off as real inference. Other real-model cases use actual Gemma inference.

The fresh extraction cases covered unseen wording for ZIP, insurer-only coverage, full/missing plan labels, uninsured status, explicit future year/date, unknown location, scan limits/noise, explicit specialty and greeting. A small synthetic set is easy to pass and does not establish broad accuracy. Rerunning the final suite reproduces the evaluation; after seeing it, further tuning would require another unseen suite.

Fresh extraction median: **2.137 seconds**. Fresh complete tool sequences took **0.646 seconds** for app context, **1.931 seconds** for two empty care searches, and **6.066 seconds** for the exact-plan plus two care searches, using synthetic directory fixtures and actual local inference/MCP. The live two-turn scan-help/care-search smoke took **11.924 seconds** including model work and public upstreams. These are single local measurements, not controlled latency benchmarks or service-level guarantees.

No training ran. The three examples in `training-seed.jsonl` are separate from both evaluation suites and are synthetic only. A LoRA training workflow was deferred: the working runtime is an inference-only quantized setup, native device testing was running on the same 16 GiB Mac, and a tiny baseline evaluation does not yet justify adding training dependencies, larger base weights and a training run. There is no trained adapter and no claimed fine-tuning improvement. Next model work should expand the evaluation and compare another untuned model before deciding whether training is useful.

## Deterministic/protocol checks

`npm test`: **36 passed, 0 failed**. These tests use synthetic directory records and protocol doubles where specified. They cover wrong/missing/unsupported plans; current versus future plan periods; incorrect network/public plan ID; expired/inactive/missing provider-role links; changed plan clearing stale details; absent/noisy/high-BPM scans; no diagnosis or automatic specialist selection; empty results; timeout and malformed upstreams; source attribution; arbitrary-tool/URL rejection; unsafe website links; strict private-ID/recording-field rejection; session expiry; and HTTP origin/host/token behavior.

The actual MCP SDK was tested both through the web backend's in-memory transport and through an **external stdio client process**. The external test listed all four read-only tools, retrieved app facts, and rejected an invalid ZIP. No external/global MCP configuration was changed.

## Browser checks

`npm run test:browser`: **9 checks passed**, isolated local Chrome with synthetic public-directory fixtures and the real web backend/MCP. Covered keyboard focus and Enter submission, loading/disabled controls, source-backed cards, noisy scan, a 390px mobile layout with no horizontal overflow, empty-source fallback links, upstream errors versus empty data, visible request failure/recovery, and no JavaScript errors. Screenshots are ignored local artifacts in `test-results/`.

The in-app browser backend was unavailable. Browser checks therefore used a separate isolated Chrome process and did not attach to personal browser tabs. `npm run test:browser:live` additionally exercises an actual browser conversation and the payer form with the real local model and live public APIs. All **3 live browser checks passed**: a real multi-turn chat with 9 live provider/clinic cards, an explicit-2027 payer form with linked-practice evidence, and a 390px layout with no horizontal overflow. See `browser-live-results.json` for timestamps and actual tool traces.

## Live public-source checks

`npm run smoke`: **6 checks passed**. Full evidence, source URLs, timestamps and tool traces are in `live-smoke-results.json`.

- NPPES exact ZIP `94303`: 4 active identity/practice cards after backend filtering.
- HRSA exact ZIP `94303`: 5 active service-site cards. This is a bounded sample, not an exhaustive directory or guarantee of suitable services.
- CMS plan catalog: a deliberately nonexistent synthetic plan remained unsupported/unverified.
- The Health Plan Medicare: the real `H3672-014-000` 2027 plan linked through the exact network to 1 real practitioner/practice in `26003`, with source evidence for every relationship.
- The same plan name/public ID requested for **2026** was rejected because the returned plan period starts in 2027. The future candidate remains visible with its dates; it is not a current-coverage claim.
- A real Gemma scan-help conversation called app context through MCP, then generated both care-search tool calls and returned actual public listings. No fixture substitution.

Live source counts can change. Member eligibility, benefits, appointment availability, referrals and out-of-pocket cost were not verified and are never promised. Only The Health Plan Medicare has a direct payer/network adapter; other insurers receive unverified CMS catalog candidates and official directory fallbacks.
