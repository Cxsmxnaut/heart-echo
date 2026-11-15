# Tested adapter-only GGUF export

The selected PEFT adapter was converted and loaded by llama.cpp b12248. No full base merge, F16 base export, base re-quantization or second full model download was needed. The original base GGUF is used for both sides of the comparison, with the adapter disabled/enabled. See [RESULTS.md](RESULTS.md) for behavior; successful conversion alone does not establish quality.

## Selected route

- Actual PEFT input: `runs/kaggle-artifacts-v1/kaggle-seed-001/adapter/`; adapter SHA-256 `b454e51ecf79090977bb9e1e11c406af18a95520b2c2a42218da4321cee89c4b`.
- Official llama.cpp tag `b12248`, commit `3837bf0bc02ea5d08f8ee3585fc8c7784a81bce8`. Source/archive/converter hashes: `config/lora-export-source.json`.
- Converter: the pinned source's `convert_lora_to_gguf.py`, using the base architecture config and the adapter weights, output type F16.
- Local isolated converter environment: `.cache/lora-convert-venv`; install reports/logs under `runs/`.
- Output: `exports/care-e4b-seed001-lora-f16.gguf`, 36,740,928 bytes, 588 tensors, SHA-256 `513abc53c84f42116bec06877c6691de83d6c224e921f15039315121fc9ea6e3`.

The converter sees a copy of the pinned training config with **only `quantization_config` removed**. That metadata describes bnb base-weight dequantization and is irrelevant to these floating-point LoRA tensors. All other fields, including architecture and EOS, match the original. Original config and PEFT weights are preserved; vendor code was not patched. The config hashes and attempt history are in `reports/lora-export-verification.json`.

The tested conversion is reproduced by the guarded script below, using a new output path. It checks the proof, config, source and adapter first, and refuses to overwrite an existing result. It does not load a full base model.

```sh
.cache/lora-convert-venv/bin/python finetuning/scripts/export-lora.py \
  --out finetuning/exports/new-name-lora-f16.gguf
```

## Checks and comparison

All 588 output tensor targets map to the existing base GGUF. Seven fixed text/control/native-tool tokenizer probes match the saved training tokenizer and serving tokenizer; this is not a full-vocabulary proof. Actual adapter-on inference is reported separately.

The base is `.cache/models/e4b/gemma-4-E4B-it-Q4_K_M.gguf`, SHA-256 `85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87`. Paired inference uses this exact file and the same b12248 runtime, native Jinja template, temperature 0, reasoning off/budget 0, context 8192, one slot, two CPU/batch threads, no RAM prompt cache, batch tool mode. Each state starts a fresh server process, and only one E4B is loaded on the 16 GiB Mac. Candidate loading adds `--lora finetuning/exports/care-e4b-seed001-lora-f16.gguf`; its observed adapter scale is 1. No adapter is loaded when the baseline is restored.

The candidate, base, tests, runtime, app source and decoding were frozen in `config/candidate-seed001-freeze.json` before held-out inference. Raw intent/fields and native-tool scores use the real application adapter and MCP. Public facts remain supplied and validated by the backend.

## Preserved unsuccessful attempts

1. A config download saved redirect text rather than JSON. The retry followed redirects and validated JSON.
2. The converter attempted unsupported bnb dequantization from the original config metadata.
3. An alternative unquantized config had a different EOS ID. A shell command continued after a failed comparison; its converted output is preserved as unselected and was never benchmarked.
4. The selected run used the checked metadata-only config copy described above. Subsequent commands enforce validation before conversion.

These were export/setup repairs, not changes selected from test performance. Logs and the unselected output remain under `runs/`. There was no test-driven retraining.

A full F16 merge followed by re-quantization remains **unexecuted and unnecessary for this pilot**. No claim is made about that route or about general GGUF exporters. This test establishes only the recorded adapter-on/off runtime and small task set.
