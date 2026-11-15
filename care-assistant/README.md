# Heart Echo care assistant

For judging, use the [project overview](../README.md), [walkthrough](../docs/JUDGE_GUIDE.md), and [current results](../docs/RESULTS.md). Sections describing earlier Gemma passes preserve historical evidence and do not describe the current Gemini chat mode.

The Heart Echo demo uses Google Gemini when `GEMINI_API_KEY` is set. Run `node scripts/setup-gemini.js` and enter the key in its Mac-only page; it is saved with owner-only permissions in the ignored `.env.gemini.local` file. Restart `Start Heart Echo Demo.command` after saving the key. Gemini generates conversational replies throughout the care flow, including when a person provides location or insurance details. The service substitutes general workflow instructions for detected personal details and does not send the recording summary. Google may use free-tier messages to improve its products, so do not enter personal or health information in free-tier chat. A local keyword check catches some sensitive messages but is not complete. Care-directory searches remain validated application code, and coverage for most insurers cannot be verified.

Gemini defaults to `gemini-3.5-flash` and tries `gemini-3.5-flash-lite` if the first model returns a request-limit or temporary-unavailable error. Both can still be unavailable or rate-limited; the chat reports that instead of pretending an AI replied. Set `GEMINI_MODEL` or `GEMINI_FALLBACK_MODEL` to choose other available models.

The demo launcher keeps its pairing in the ignored, owner-only `.demo-pairing.local.json` file so restarting the Mac service does not invalidate the iPhone's saved credentials. Keep that file private. Conversation memory still expires or clears on restart; pairing and conversation memory are separate.

Current component: **0.3.0**. Without a Gemini key, E4B is the local default, with the trained care adapter enabled for the Heart Echo demo; E2B remains the faster base-model option. In local mode, intent classification and field extraction run as separate small tasks. Batched native tool calls reduce model round trips; `LLM_TOOL_MODE=serial` retains the earlier routing. See [model quality and resource tradeoffs](docs/model-quality.md), [the preserved second-pass report](docs/pass2.md), and [the trained adapter evaluation](finetuning/RESULTS.md). Earlier scores remain history.

A care-navigation prototype with Gemini or a local Gemma 4 model, a browser chat, four read-only MCP tools, and public provider/clinic directories. The iPhone app can connect to the care service running on the same trusted Wi-Fi network.

The app estimates **BPM and sound timing only**. This assistant does not diagnose AFib, murmurs, or heart disease, declare a BPM healthy, or decide that a specialist is needed. Care search works with a usable, unclear, or absent scan.

## Run locally

Requires Node 22+; the pinned local model setup requires Apple Silicon macOS, 16 GiB RAM for E4B (12 GiB minimum for E2B), and about 5.1 GB for E4B plus the runtime. Both models were tested on an Apple M4 Mac with 16 GiB RAM. A model server and web server run as ordinary terminal processes, not global services or watchers.

```sh
cd /Users/slolakap/Documents/ChatGPT/Hackathon/care-assistant
npm ci
cp .env.example .env # only for a NEW setup; preserve any existing .env
npm run model:setup
npm run model
```

In a second terminal:

```sh
cd /Users/slolakap/Documents/ChatGPT/Hackathon/care-assistant
# The .env created above selects E4B. For another endpoint, edit:
# LLM_PROVIDER=compatible
# LLM_BASE_URL=http://127.0.0.1:4320/v1
# LLM_MODEL=care-gemma4-e4b
npm start
```

Open **http://127.0.0.1:4318**. Model readiness: `http://127.0.0.1:4320/health`. Web health/configuration: `http://127.0.0.1:4318/api/health`. The badge distinguishes configured, verified inference, and guided fallback. `last_success_at` is the last valid model response, not a continuous health guarantee.

The installation in this workspace already has local `.env` settings, the model and the trained adapter. **Do not overwrite that `.env` merely to run this copy.** The E4B launcher checks that the adapter exists and matches its saved fingerprint; if it is unavailable, restore it or use `CARE_MODEL_ADAPTER=off npm run model` for the base model. Start the two processes if they are not already running. Stop each with Ctrl+C in its own terminal. If either port is occupied, choose `PORT` for the web server, or `MODEL_PORT` plus the corresponding `LLM_BASE_URL` for the model. Never stop an unrelated process to free a port.

For a different approved model endpoint, set `LLM_PROVIDER=compatible`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` if required. It must implement `/chat/completions`, JSON-schema responses, and function `tool_calls`, including `tool_choice: required`. HTTPS is required for non-loopback model endpoints. Tokens stay server-side and are not included in prompts or logs. No key, account, subscription, or external deployment is required for the included local setup.

To use the faster E2B option, stop only your model process, set `MODEL_VARIANT=e2b` and `LLM_MODEL=care-gemma4-e2b` in `.env`, then run `npm run model:setup`, `npm run model`, and restart the web server. E2B needs about 3.2 GB on disk. Keep only one model loaded. E4B takes roughly twice as long in the development comparison; this setup does not automatically switch models or hide failures.

`LLM_PROVIDER=guided` runs a useful, explicitly labeled form/chat flow with live directories. It is **not an LLM**. Model errors also produce an explicit guided-fallback status, and the server still validates and searches public data.

## Try it

1. Explain a synthetic scan or leave the scan absent.
2. Enter a five-digit US ZIP. `94303` returned NPPES providers and HRSA sites in the live smoke check.
3. Supply the insurer, full plan name and network, or choose “I’m not sure” / “No insurance.” A payer name alone is not enough for an exact-plan check.
4. Review practice addresses, phone numbers, source links, retrieval dates, and the evidence/limits disclosure on each card.

To try the narrow payer integration, use this **synthetic user scenario with real public plan/directory data**, explicitly selecting the future plan year:

| Field | Value |
| --- | --- |
| ZIP | `26003` |
| Insurer | `The Health Plan` |
| Full plan name | `The Health Plan SecureCare Integrity Plan 3 (HMO)` |
| Network | `THPWV Medicare Network` |
| Public CMS plan ID | `H3672-014-000` |
| Plan year | `2027` |

The live check found a source chain from this exact plan to its network, practitioner role, practitioner, and practice location. **The same record is rejected for 2026.** The directory currently returns a 2027 effective period. That is not evidence of current 2026 coverage. Payer-linked results are separately labeled and are not specialty-filtered; the generic NPPES search is specialty-filtered.

The default effective date is today for the current year, or January 1 of an explicitly chosen other year. API callers may send `coverage_date` for a specific day in the requested year. Conflicting year/date values do not match. Plan and practitioner-role periods must both cover the requested day. Directory evidence does not check membership, benefits, cost, referral rules, or appointment availability.

## What the model does

The **Gemma 4 E4B instruction model**, in an attributable Unsloth Q4_K_M GGUF conversion, runs with pinned llama.cpp `b12248` and the locally trained care adapter. It separately classifies intent, extracts user-supplied details, and makes native function calls. Model and runtime files are pinned and SHA-256 checked by `npm run model:setup`; the launcher also checks the adapter's fingerprint. Set `CARE_MODEL_ADAPTER=off` to use the original base model. E2B does not use this E4B adapter. No audio/vision projector is needed or downloaded: this component sends text and the small structured scan summary only.

The intent and field tasks receive only the current message. Tool selection receives versioned app facts, confirmed preferences, the summary, and a limited recent chat history. It does not memorize provider listings or changing app facts through fine-tuning. App facts are authored in `src/knowledge.js`; `npm run schema` exports `docs/app-knowledge.v1.json` and the scan schema reproducibly.

In local Gemma mode, this prototype renders **medical limitations, questions, and directory facts from validated application data** rather than unrestricted model prose. Gemini mode generates conversational replies across the care flow; it is prompted not to diagnose or invent providers, and recording summaries are not passed to Gemini. The Mac supplies generic context instead of detected location, insurance, or personal-health details; its keyword check is incomplete, so users must not enter personal information into the free service. Directory cards and emergency notices still come from controlled application data. For local model tool calls, schemas are narrowed to confirmed values and the backend independently rejects changed details. Search limits are bounded; missing required searches are completed by the service and identified in the trace.

## MCP and APIs

The web backend connects to a real MCP SDK server through an in-memory transport. External clients can launch the same server over stdio:

```sh
node --env-file-if-exists=.env /absolute/path/to/care-assistant/src/mcp.js
```

Or run `npm run mcp`. Configure the MCP client's working directory as this component when using `.env`. The server writes protocol messages only to stdout; it has no arbitrary URL-fetch, shell, or code-execution tool. No global MCP configuration was changed.

| Tool | Source and scope |
| --- | --- |
| `search_providers` | CMS NPPES v2.1; active provider identities and US practice locations in an exact ZIP; selected family medicine, internal medicine or cardiology taxonomy. No insurance inference. |
| `lookup_plan_network` | The Health Plan public **Medicare** FHIR Plan-Net directory for an exact payer/plan/public plan ID/year/network/practice evidence chain. Other payers: CMS National Provider Directory plan-name candidates only, explicitly unverified. |
| `search_affordable_clinics` | Active HRSA-listed health-center service sites in an exact ZIP. Sites may be dental, school-based, mobile, or offer other limited services; call to confirm. Sliding fees depend on income, family size and clinic policies. |
| `get_app_context` | Versioned app capabilities, limitations, privacy and insurance facts. |

All tools accept strict schemas. The source hosts and FHIR resource paths are fixed. Upstream reference/pagination URLs are not executed. Backend filters check ZIP, active status and required relationship evidence even if an upstream ignores filters. Upstream timeout, HTTP error, malformed data and empty results are distinguished. Public responses are size-limited. Source results are not cached or used for training.

The API is versioned for future native integration:

| Route | Purpose |
| --- | --- |
| `POST /api/v1/chat` | `{message?, session_id?, scan?, profile?, action?}`. Returns server-owned session ID, stage, explanation, confirmed profile, model status, results and tool trace. |
| `POST /api/v1/scan-summary` | Validate and explain a v1 scan summary without storing it. |
| `GET /api/v1/scan-summary/schema` | Machine-readable v1 JSON Schema. |
| `DELETE /api/session/:id` | Discard an in-memory chat. |
| `GET /api/health` | Configuration and last successful model-response time. |

See [the native handoff contract](docs/integration.md), `examples/scan-handoff.json`, and `examples/integrate.js`. `npm start` binds to loopback. The Heart Echo demo launcher offers a separate paired local-network connection so a phone on the same trusted Wi-Fi can use the chat; a phone cannot reach the Mac through the phone's own loopback address.

## Checks

```sh
npm test                    # deterministic fixtures + real HTTP/MCP protocol tests
npm run test:browser        # isolated local Chrome; synthetic directory fixtures
npm run test:browser:live   # actual browser + local model + LIVE public sources
npm run smoke               # LIVE public sources + actual configured model conversation
npm run evaluate            # original suite, now development/regression data
node --env-file-if-exists=.env evaluation/batching-final.js --reproduction # current batch-tool reproduction
npm run schema              # reproducible contract/context exports
```

The historical `npm run evaluate:quality` runner protects its earlier serial freeze and rejects the newer batching source. Its first results and source snapshot are retained under `evaluation/history/quality/`; current tool checks use the batching reproduction command above.

Browser checks use Google Chrome at its standard macOS path. Set `CHROME_PATH` to a different installed Chromium executable if needed. They start and stop their own ephemeral test server and isolated browser. They do not attach to personal tabs. Screenshots go to ignored `test-results/`. The in-app browser backend was unavailable in this session, so isolated Chrome was used for the actual UI checks.

See [evaluation results and limitations](docs/evaluation.md), `docs/live-smoke-results.json`, `docs/browser-test-results.json`, and the evaluation JSON reports. Synthetic fixtures are labeled in `test/fixtures.js`; public smoke checks never silently substitute fixtures. Results are a small prototype evaluation, not clinical validation or a claim of nationwide insurance support.

## Privacy, limits and deployment boundary

- No private recordings/captures are read or accepted by the scan schema. No model training, analytics, conversation database, or request-body logging is present. Do not enter personal/member identifiers or upload private health files. Free chat text is still user input; the form cannot guarantee that a user will never type sensitive material.
- Chat is kept in server memory for 30 minutes of inactivity. Expired sessions are pruned on the next request; reset/delete and restart discard them. The browser keeps its session ID in memory only. Requests and source results are marked `no-store`.
- Same-origin checks, allowed loopback hosts, strict JSON bodies, bounded requests and a per-process rate limit protect this local demo. A configured `CARE_API_TOKEN` is required for non-browser native/CLI writes; it is never placed in the browser. This is not a production identity system.
- No exact payer integration beyond The Health Plan Medicare is claimed. Its Medicaid/CHIP endpoints were documented but are not integrated. CMS catalog matching is not exact-network/provider coverage. “Unsupported” means this source did not establish a match, not that a plan is invalid or a provider is out of network.
- Exact-ZIP results are limited samples, not exhaustive or distance-ranked. A missing listing is not proof that no care is available. Directory timestamps can be old; call to confirm. NPPES identity is not licensure or quality validation.
- A symptom keyword notice is a conservative interruption, not a medical triage classifier. It can miss or over-trigger symptoms. The emergency notice remains visible regardless of model output.
- The original care-service evaluation preceded fine-tuning. A later synthetic-data language-adapter pilot is documented in [finetuning/README.md](finetuning/README.md); it is separate from Gemini and from the phone audio models. Do not train on private chats, insurance records or audio.
- This is a local demo with native integration and a public source repository, not a publicly hosted patient service. Repository graph tooling was absent, so no Graphify results or refresh are claimed.

Sources, model versions, license attribution, and evidence rules are in [provenance](docs/provenance.md).
