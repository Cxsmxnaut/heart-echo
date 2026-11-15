# E4B fine-tuning pilot

> Historical experiment record. Serving-default statements below describe that experiment's original state. The current judge path uses Gemini or an explicitly labeled no-key guided mode; see the [judge walkthrough](../../docs/JUDGE_GUIDE.md). The trained adapter is not included in the public repository.

**Real training completed on November 14, 2026 (Pacific time).** The private Kaggle run saved a verified language LoRA adapter after 17 optimizer steps. The adapter was converted to a 36.7 MB GGUF LoRA and completed a frozen comparison with the original model. The original model remains the serving default. The adapter improved validation fields (5/7 → 6/7) and completed both regression journeys (control: 1/2), while held-out scores tied. See [RESULTS.md](RESULTS.md) for the comparison and limits; evaluation reports are under `reports/`.

QLoRA trains a small adapter while keeping the quantized base model fixed. This pilot targets request parsing and native tool selection. It does not train the sound estimator, diagnose disease, learn provider directories, or replace the backend's validation and factual replies. Native/Xcode, estimator, audio, signing and device files were not changed.

## Actual artifacts

| Item | Evidence |
| --- | --- |
| Private Kaggle version | `bhavithlolakapuri/chest-bpm-gemma-e4b-qlora-pilot/1`, COMPLETE |
| Training | 17 steps, 516 changed trainable tensors, 116.351 seconds on one Tesla T4 |
| Saved PEFT adapter | 73,486,800 bytes; SHA-256 `b454e51ecf79090977bb9e1e11c406af18a95520b2c2a42218da4321cee89c4b` |
| GGUF LoRA | `exports/care-e4b-seed001-lora-f16.gguf`, 36,740,928 bytes; SHA-256 `513abc53c84f42116bec06877c6691de83d6c224e921f15039315121fc9ea6e3` |
| Independent tensor check | All 588 saved tensors finite and matching the recorded after-training hashes; 258/294 LoRA B tensors nonzero |
| Runtime target check | All 588 GGUF LoRA tensor targets exist in the original base; seven fixed tokenizer probes match |
| Frozen candidate | `config/candidate-seed001-freeze.json`, created before held-out inference |

The original training proof under `runs/kaggle-artifacts-v1/kaggle-seed-001/training-complete.json` records the state at training completion, so its export/held-out flags remain false. Later checks are separate reports. Files under `runs/`, `exports/` and `.cache/` are local artifacts, not material to commit.

## Data and separation

| Split | Unique scenarios | Scenario/wording families | Model task records |
| --- | ---: | ---: | ---: |
| Train | 36 | 32 | 66 |
| Validation | 10 | 10 | 17 |
| Held-out test | 10 | 10 | 17 |

These are 56 agent-authored synthetic scenarios. A message produces separate intent and field targets because the app makes two requests. Tool scenarios target native calls. These are not 100 independent scenarios or human/clinician labels. Related wording families stay in one split. Exact and token-overlap checks supplement review; they do not prove complete semantic separation.

No private chats, audio, member identities, provider listings, clinical outcomes, eligibility or cost labels were used. Prior evaluation examples and outputs were excluded from training; their fingerprints are in `config/seen-evaluation-inventory.json`. Earlier failure classes informed coverage, but old examples and answers were not imported. No external dataset was mixed in.

The training transfer includes only allowlisted train/validation data and code. `data/sealed-test.jsonl` and `data/tools.test.jsonl` were excluded from the Kaggle upload. They were first used for model inference during the frozen paired comparison. Do not tune or retrain this candidate from its test failures. Any later development needs new held-out data.

## Training and export

The selected base is `unsloth/gemma-4-E4B-it-unsloth-bnb-4bit` at revision `6f10b2aa522ba471321d8246fd71a3dfa8c5b9a2`. Source and dependency pins are in `config/upstream-pins.json` and `requirements.candidate.txt`. The actual Kaggle environment lock, package checks and logs were downloaded with the adapter.

The fixed recipe uses language-only LoRA rank/alpha 8, learning rate 5e-5, one epoch, micro-batch 1, accumulation 4 and a 2,048-token cap. Audio, vision and base parameters stay frozen. Full HF target rendering and assistant-only masking passed before optimization. The 66 training records took 17 steps. The reported training loss is not proof of useful app behavior.

[The Kaggle notes](kaggle/README.md) cover the private CLI run and the setup failure/repair. [EXPORT.md](EXPORT.md) records the tested adapter-only conversion. No additional full base weights were downloaded for conversion, and no base weights were merged. The runtime comparison uses the exact same existing Q4_K_M base with the LoRA off and on, which isolates the adapter's effect on this runtime. Training bnb4bit and runtime Q4_K_M remain different model packaging.

## Verification and serving

The data checks and five tamper checks passed before training. The real baseline validation was 7/7 intents, 5/7 exact field sets and 3/3 constrained tool tasks. The benchmark repeats this control and compares the frozen candidate through the current app's JSON-schema/native-tool path and actual in-memory MCP. Raw scores exclude service corrections. End-to-end and browser results report corrections and fallback separately.

Benchmark policy: fresh process for each state, one E4B loaded at a time, same base/runtime/decoding, no cache carried between states. The sequential swap was authorized and restores the baseline on port 4320 in `finally`. `.env` and app source are unchanged. The adapter stays disabled pending review of actual benefits and remaining failures.

No repository Graphify setup was found. Source hashes in `config/baseline-lock.json` identify the baseline because the snapshot had no HEAD commit. Generated artifacts do not prove runtime behavior; the inference reports do.

Safe local checks from `care-assistant/`:

```sh
node finetuning/scripts/prepare.mjs
node finetuning/scripts/self-test.mjs
python3 finetuning/scripts/train.py  # preview only
```

Do not rerun `benchmark-sequential.py` blindly: it owns a temporary model swap and refuses the existing run directory. Existing evaluation reports are preserved rather than overwritten. Further training, public publishing and default-model adoption are separate work.
