# E4B pilot results — November 14, 2026

**November 15 update:** The Heart Echo demo now loads this trained adapter by default for E4B, at the user's request. Set `CARE_MODEL_ADAPTER=off` to run the original base. The evaluation below remains unchanged: the adapter did not improve the small held-out scores and does not establish clinical benefit.

**Original pilot decision:** Keep the original model as the default. Real training and GGUF LoRA inference worked. The adapter fixed one validation case and one regression conversation, but it did not improve the held-out scores. This small pilot does not establish broad accuracy or clinical benefit. The later demo change above follows the user's request.

## Training and artifact proof

The private Kaggle notebook `bhavithlolakapuri/chest-bpm-gemma-e4b-qlora-pilot/1` reached COMPLETE. One Tesla T4 trained language LoRA only for 17 optimizer steps. The proof records 516 changed trainable tensors and 116.351 seconds (trainer runtime 109.7395 seconds). Audio, vision and base weights stayed frozen. All 588 saved tensors were independently checked as finite and equal to the recorded after-training hashes; 258/294 saved LoRA B tensors are nonzero. Loss 0.113396 is training evidence, not quality evidence.

The seed contains 36 training scenarios/32 wording families, projected into 66 task records. Validation and test each contain 10 scenarios/10 families and 17 task records. A message produces two tasks, so these counts are not independent messages. Labels and rationales are agent-authored synthetic data, not human or clinician annotation. Sealed tests were excluded from the Kaggle upload and from training. No private recordings, chats, identities, provider facts or clinical labels were used.

| Artifact | SHA-256 | Bytes |
| --- | --- | ---: |
| PEFT adapter | `b454e51ecf79090977bb9e1e11c406af18a95520b2c2a42218da4321cee89c4b` | 73,486,800 |
| Selected F16 GGUF LoRA | `513abc53c84f42116bec06877c6691de83d6c224e921f15039315121fc9ea6e3` | 36,740,928 |
| Original Q4_K_M base | `85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87` | Existing serving artifact |

The PEFT adapter is under `runs/kaggle-artifacts-v1/kaggle-seed-001/adapter/`; selected GGUF LoRA is `exports/care-e4b-seed001-lora-f16.gguf`. The original training proof is preserved unchanged. Later evidence is in [training verification](reports/kaggle-training-verification.json), [tensor verification](reports/adapter-tensor-verification.json), [export verification](reports/lora-export-verification.json), [target mapping](reports/lora-gguf-target-check.json) and [tokenizer probes](reports/tokenizer-parity-probes.json). All 588 converted targets exist in the base; seven fixed tokenizer probes match. Neither check alone proves inference quality.

## Frozen paired inference

The comparison used the same exact base GGUF and llama.cpp b12248 on this Apple M4 Mac with 16 GiB unified memory. The only model-state difference was LoRA off/on at scale 1. Each state used a fresh process, one model at a time, context 8192, one slot, two CPU/batch threads, no RAM prompt cache, native Jinja, reasoning off/budget 0, temperature 0 and batch tools. No hidden states were carried across states.

Training used the pinned bnb4bit model; serving uses Q4_K_M. This comparison measures the adapter's effect on this exact serving base, not a newly merged/re-quantized model. The [candidate freeze](config/candidate-seed001-freeze.json) was written before held-out inference. No prompt, label, hyperparameter or weight was changed from held-out results, and no further GPU run was performed.

| Measure | Original control | Adapter candidate |
| --- | ---: | ---: |
| Validation raw intents | 7/7 | 7/7 |
| Validation exact field sets | 5/7 | 6/7 |
| Validation constrained tool tasks | 3/3 | 3/3 |
| Held-out raw intents | 7/7 | 7/7 |
| Held-out exact field sets | 6/7 | 6/7 |
| Held-out constrained tool tasks | 2/3 | 2/3 |
| Seen regression journeys completed | 1/2 | 2/2 |

These scores use the current app's real JSON-schema/native-tool adapter and actual in-memory MCP. Raw intent and exact field scores are measured before service corrections. Tool tasks use empty synthetic directory responses; they do not score public provider facts. There are no service-completed calls in the raw task reports.

Case-level changes:

- The validation plan replacement changed from missing the supplied plan to extracting `Fictional Juniper Select` correctly. This was the only changed raw intent/field output across the paired validation and test cases. Neither side extracted the paired partial plan/network labels correctly.
- Held-out outputs and scored tool outcomes were unchanged. Both missed the named plan-forgetting request. Both proposed an injected wrong-ZIP search; the app rejected it as `model_changed_search` before executing that search. The 2/3 score is a model failure, not a successful unsafe search.
- The candidate completed the seen plan-correction/cost/saved-results conversation that the control failed at plan replacement. It preserved the payer, replaced the plan, cleared the old network, handled the unknown-network answer, selected affordable clinics and explained saved results without another directory fetch. This is regression evidence, not new held-out evidence.
- Both passed the unclear/absent scan and diagnosis-injection guard journey. Those responses are also protected by the app's canonical guards, so passing them does not establish a model's medical reliability.

The candidate completed 8 regression turns versus the control's 5 (the control's first journey stopped on its assertion failure). Both recorded zero guided-fallback turns, zero reported backend-adjusted turns and zero service-completed tool calls in these runs. Those counters do not mean the backend's normal validators and dependent-field logic were absent.

Raw reports: [control validation](reports/seed001-control-validation.json), [candidate validation](reports/seed001-candidate-validation.json), [control held-out](reports/seed001-control-test.json), [candidate held-out](reports/seed001-candidate-test.json), [control regression](reports/seed001-control-e2e.json), [candidate regression](reports/seed001-candidate-e2e.json).

## Latency and limits

| Median elapsed time | Control | Candidate |
| --- | ---: | ---: |
| Validation message pair (intent + fields) | 18.30 s | 17.37 s |
| Validation tool task | 13.01 s | 13.94 s |
| Held-out message pair (intent + fields) | 16.04 s | 18.47 s |
| Held-out tool task | 13.13 s | 15.05 s |

These are single sequential runs on a shared Mac, with only seven message pairs and three tool cases per split. The adapter was slower on this held-out sample; this is not a reliable general speed estimate. There was no repeated performance study or measured peak memory comparison. Different completed regression turn counts make whole-journey timing unsuitable for a speed comparison. No GPU-to-Mac speed claim is made.

The small seed, agent labels and limited wording coverage restrict what can be concluded. Family splits and duplicate checks cannot prove semantic independence. Provider accuracy, eligibility, cost, appointments, diagnosis, clinical outcomes, native-device performance and broad prompt-injection resistance were not established by this pilot. The backend's validation and factual copy remain necessary. llama.cpp also reported an unsupported ZIP regex escape in grammar conversion; application-side ZIP/argument validation remained active on both sides.

## Browser and restoration

The candidate passed all four live browser checks: app question/ZIP/uninsured care flow (nine live cards), the explicit 2027 payer-linked form, saved-result explanations with the unverified category visible, and the 390 px mobile layout with no horizontal overflow. Five observed API turns used the model, with zero guided fallback, zero reported backend adjustments and zero service-completed calls. Desktop and mobile screenshots were also inspected. This was a candidate smoke check against live public sources using a synthetic user, not a fresh paired browser accuracy study or a native-device test.

The benchmark completed and restored the original no-adapter model on port 4320. The model health endpoint and the web app health endpoint on 4318 both returned `ok`; `/lora-adapters` returned `[]`. Temporary evaluation port 4324 was closed. The 14 frozen source files and both held-out data files still matched their hashes at that time. This final health check did not run a new post-restoration conversation. `.env` and application source were not changed by the pilot.

Evidence: [full comparison](reports/comparison-seed001.json), [benchmark stages/process settings](reports/sequential-benchmark.json), [candidate browser](reports/seed001-candidate-browser-live.json), [restored serving state](reports/serving-restoration.json). Candidate screenshots remain at `.cache/benchmark-seed001/test-results/live-desktop.png` and `live-mobile.png` under the app root. Earlier baseline browser and model evidence were not overwritten. The adapter was disabled at the end of the pilot; the November 15 update above records the later demo change.

## Reproducing the local experiment

The trained artifact is ready to load; no upload, training or conversion step remains. The demo launcher now loads it by default for E4B. The command below reproduces the pilot's explicit adapter launch.

On this 16 GiB Mac, stop the existing care `llama-server` before starting the command below. If it runs in a terminal, use Ctrl+C there. The current restored PID and verified command are recorded in `reports/serving-restoration.json`; verify the current listener still belongs to this app before stopping a detached process. Do not run two E4B processes together.

From `care-assistant/`, launch the trained variant on the app's existing model port:

```sh
.cache/runtime/llama-b12248/llama-server \
  -m .cache/models/e4b/gemma-4-E4B-it-Q4_K_M.gguf \
  --lora finetuning/exports/care-e4b-seed001-lora-f16.gguf \
  --alias care-gemma4-e4b --host 127.0.0.1 --port 4320 \
  -c 8192 -np 1 -t 2 -tb 2 --cache-ram 0 --jinja \
  --reasoning off --reasoning-budget 0 --no-webui --log-disable
```

The existing web app at `http://127.0.0.1:4318` uses that alias/port, so `.env` needs no change. Wait until `http://127.0.0.1:4320/health` reports `ok`; `/lora-adapters` should show this adapter at scale 1. Ctrl+C stops this experimental model. Restore the original without an adapter with:

```sh
MODEL_VARIANT=e4b CARE_MODEL_ADAPTER=off npm run model
```

Wait for the same health check; `/lora-adapters` should then be `[]`. These launch commands reproduce the benchmarked model state. This documentation does not start another model or change the current default.
