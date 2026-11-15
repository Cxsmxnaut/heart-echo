# Sources and evidence rules

Second-pass app knowledge v1.1 also uses the current native UI/display code read-only in `ChestBPMApp.swift` and product facts explicitly supplied by the orchestrator. Only the main displayed BPM is accepted for handoff; comparison counters never substitute. No private captures or estimator/model source was read. See [pass2.md](pass2.md) for the frozen evaluation and the constrained/server-bound tool interface.

Official documents were checked and actual public API responses were smoke-tested on November 14, 2026. Per-result `retrieved_at` is when this service read the source, not when a plan became effective or a provider updated its listing.

| Source | Role | Evidence limit |
| --- | --- | --- |
| [CMS NPPES API documentation](https://npiregistry.cms.hhs.gov/api-page) and [v2.1 API](https://npiregistry.cms.hhs.gov/api/?version=2.1) | Active provider identity, taxonomy, practice address and phone. | No exact-plan, appointment, cost, quality or licensure conclusion. Location addresses only; mailing addresses are excluded. |
| [CMS National Provider Directory developer docs](https://directory.cms.gov/developers) and [FHIR capability statement](https://directory.cms.gov/fhir/metadata) | Read-only plan-name catalog candidates for otherwise unsupported payers. | Name-only matches remain unverified. No provider/practice/network chain is implemented against this source. |
| [CMS payer-directory API FAQ](https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/frequently-asked-questions/provider-directory-api) | Explains the public directory requirements for affected Medicare Advantage, Medicaid and CHIP payers. | These rules do not provide one complete all-insurer API. App registration may still be required by individual payers. |
| [The Health Plan public API page](https://www.healthplan.org/patient-access-api) and [public Medicare FHIR base](https://api.thehealthplanfhir.com/r4/public/metadata) | Exact Medicare plan, owner, network and practitioner-role/location chain. | Only this public Medicare source is implemented. An exact match is directory evidence, not member eligibility, referrals, benefits, cost or appointments. |
| [HRSA health-center data](https://data.hrsa.gov/topics/health-centers/), [GIS developer tools](https://data.hrsa.gov/tools/gis-developer-tools), and [service-site layer](https://gisportal.hrsa.gov/server/rest/services/HealthCareFacilities/PrimaryHealthCareFacilities_FS/MapServer/0) | Active health-center service sites and available contact data. | Site type/services can vary. Same-ZIP results are not distance ranking. Public ArcGIS is used; no registration-only HRSA web-service key is assumed. |
| [HRSA Find a Health Center](https://findahealthcenter.hrsa.gov/) and [sliding-fee compliance guidance](https://bphc.hrsa.gov/compliance/compliance-manual/chapter9) | Official fallback and fee-context source. | Ask the clinic about eligibility and services. No guaranteed prices/free care. |
| [NHLBI heart-attack symptoms](https://www.nhlbi.nih.gov/health/heart-attack/symptoms) | Source-linked emergency notice. | Keyword matching is not clinical triage or a validated symptom classifier. |

## Narrow payer match

The Health Plan lookup requires a user-provided exact payer name, exact plan name, requested coverage date/year, and exact network name. If exact-name plans are ambiguous, it asks for a public CMS plan ID. It then verifies:

1. Exactly one active `InsurancePlan` with the requested name/public ID covers the requested day.
2. `InsurancePlan.ownedBy` resolves to an active payer organization named The Health Plan.
3. A plan network resolves to exactly one active organization with the exact requested network name and that payer as `partOf`.
4. Each returned active `PractitionerRole` covers that day and explicitly references that network through the Plan-Net `network-reference` extension.
5. The included active practitioner and active location are exactly the references on that role. The location has a US address in the requested ZIP.

The card includes the URLs for all six links. FHIR references must be relative, match a specific resource type and safe ID, and remain on the fixed payer base. Source-provided arbitrary URLs and next-page URLs are not fetched. The search is bounded to 100 name candidates, 5 network references, 8 practitioner roles and 5 locations per role. These caps can omit matches and are reported as limited coverage rather than completeness.

The live November 14 check returned a plan with a 2027 period and a practice network linkage for a synthetic scenario requesting 2027. The same plan ID/name is rejected for 2026. A plan marked `active` by a directory is not automatically effective today.

## Model/runtime attribution

- [Google Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4) and [official function-calling guidance](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4). Instruction-tuned E4B (default) and E2B (speed option) model families; text-only usage here. No medical model claim.
- [Unsloth Gemma 4 E2B instruction GGUF conversion](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/tree/0314792d7f1f7e229411f620751375812bb9faf2), revision `0314792d7f1f7e229411f620751375812bb9faf2`, `gemma-4-E2B-it-Q4_K_M.gguf`, SHA-256 `740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8`. Public/ungated conversion; upstream metadata declares Apache-2.0. Original model and conversion attribution remain applicable. No legal/account terms were accepted on the user's behalf.
- [llama.cpp release b12248](https://github.com/ggml-org/llama.cpp/releases/tag/b12248), Apple Silicon macOS archive, SHA-256 `7f643b4d35803ccc69270302f3368d9e8a40f56f74ef5a266e6f686d9dc7d3c6`; upstream MIT license. Runtime is pinned rather than following a moving latest release.
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) and [stdio transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports); installed versions are locked in `package-lock.json`. Express, Zod, Playwright and Supertest retain their package licenses in `node_modules/`.

The model, runtime, source records and test fixtures are distinct: public directories are not model training data; synthetic fixtures are not presented as real providers in the live demo. No fine-tuned weights were created.

## Selected E4B configuration (quality pass)

[Unsloth Gemma 4 E4B instruction GGUF](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/tree/bfc15c382204943c3a8fff0c750b94ae2364d7a3), revision `bfc15c382204943c3a8fff0c750b94ae2364d7a3`, file `gemma-4-E4B-it-Q4_K_M.gguf`, 4,977,171,584 bytes, SHA-256 `85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87`. Public/ungated; upstream metadata declares Apache-2.0. Setup verifies the pinned hash before use. The pinned runtime remains b12248.

The live `/props` template matched native Gemma turn/tool syntax, SHA-256 `74a88f94c57c14e22dcdbe08e94127f42b87c6f584cb73838e73e32126f3f6b3`. [Google's Gemma function-calling guidance](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4) and the [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) were checked. Requests use temperature 0, top-p 0.95, top-k 64, and `enable_thinking: false`; runtime uses native Jinja, reasoning off and reasoning budget 0. Google's general sampling defaults were also tried in a small E2B development probe; this was not a fresh final evaluation.

E2B sometimes returned empty classifier content at the token limit during development even with thinking disabled. Template configuration alone is not proof of valid output. JSON, labels, grounded fields and tool arguments remain independently checked. No hidden reasoning is shown, logged or used as factual copy. See [the frozen quality report](model-quality.md) for results, errors, hardware and latency.
