# Private Kaggle E4B pilot — completed

The actual private notebook version `bhavithlolakapuri/chest-bpm-gemma-e4b-qlora-pilot/1` reached **COMPLETE** on November 14, 2026 (Pacific time). Its downloaded adapter has 17 optimizer steps and 516 changed trainable tensors. The local saved tensors and SHA-256 were independently verified. See [../RESULTS.md](../RESULTS.md) for quality, rather than treating completion or loss as proof of improvement.

The run used the repaired self-contained `care-e4b-qlora-private-v2.ipynb`, SHA-256 `235a57c073091e2b632cc22947c9607404d4793521836f4d295e6f79f055e993`, through the [official CLI](CLI.md). Remote notebook privacy and cell equality were verified. The user approved CLI OAuth. No manual upload, auth or GPU step remains. Do not publish this notebook or start another run simply to save the result.

## Actual compute and outputs

One Tesla T4 (~15 GiB visible VRAM), CUDA 12.8, driver 580.178.04 and Python 3.13.16 passed the resource checks. Although the allocation offered T4 x2, the recipe exposed only GPU0. Two cards were not treated as pooled memory. The actual environment lock, install checks and stage logs are inside the downloaded artifact.

The bounded language-only QLoRA recipe used 66 task records from 36 synthetic training scenarios, rank/alpha 8, learning rate 5e-5, one epoch, micro-batch 1 and accumulation 4. Training took 116.351 seconds including recorded setup around the trainer (trainer runtime 109.7395 seconds). Audio, vision and base parameters stayed frozen. Target rendering and assistant-only masks passed before the first step.

Downloaded output: `../runs/kaggle-output-v1/care-e4b-pilot-artifacts.zip`, safely extracted to `../runs/kaggle-artifacts-v1/`. It includes the PEFT adapter/tokenizer, training proof, environment and stage logs. Adapter SHA-256: `b454e51ecf79090977bb9e1e11c406af18a95520b2c2a42218da4321cee89c4b` (73,486,800 bytes).

Only source and small artifacts were saved under `/kaggle/working`. The isolated environment, base/cache and compiler/download scratch lived under `/tmp/chest-bpm-e4b-pilot`. No full base merge or GGUF conversion occurred on Kaggle. The later Mac adapter-only export is documented in [../EXPORT.md](../EXPORT.md).

The upload contained only 40 allowlisted source/train/validation files. Sealed message/tool tests and prior evaluation examples were excluded. No private chats, audio, member identities, provider facts or clinical labels were used. Training proof records `test_loaded: false`.

## Preserved setup failures and repair

The earlier interactive attempt passed T4/Python preflight but failed venv setup. A second attempt skipped the partial venv and then failed pip. Its small output archive overwrote the first archive before preservation; only the coordinating UI record of the first failure remains. The original notebook is preserved unchanged. Do not claim the first archive was recovered.

`bootstrap_env.py` now checks whether pip actually works, captures `ensurepip` stdout/stderr, and repairs only this isolated environment with checksum-pinned official uv/pip wheels if needed. It renames the partial environment and preserves currently available diagnostics. Three local mocked bootstrap tests passed.

The successful CLI job captured the actual missing `ensurepip` module and a separate Kaggle sitecustomize/wrapt warning. The uv repair then succeeded. CUDA packages, pinned training packages, `pip check`, CUDA/import smoke test, environment lock and training all completed. No model, dataset, training hyperparameter or test label was changed to repair setup.

Helpers for the earlier interactive session (`diagnose-ensurepip-cell.py`, `repair-ensurepip-cell.py`, `repair-existing-session.py`) remain as evidence. They are not needed for the completed run. The v2 notebook embeds the fixed bootstrap and the complete source package. No unrelated private Kaggle project was accessed.
