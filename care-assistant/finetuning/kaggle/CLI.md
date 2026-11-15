# Official Kaggle CLI — completed private run

The user approved the official browser OAuth prompt, including its `resources.admin:*` scope. Authentication completed, the private notebook was uploaded as version 1, its T4 run reached **COMPLETE**, and its artifact ZIP was downloaded. No additional approval or manual notebook import is pending.

`kaggle==2.2.5` is installed only in `finetuning/runs/kaggle-cli-venv`. Its missing undeclared dependency was repaired with `six==1.17.0`. The wrapper scopes ordinary configuration with `KAGGLE_CONFIG_DIR`. The official SDK stores OAuth credentials at its normal `~/.kaggle/credentials.json` location; do not read, print, copy or commit credentials. The login callback logs were suppressed so codes were not printed. No browser credential extraction or manual API-key generation was used.

Only this private notebook was uploaded and run:

`bhavithlolakapuri/chest-bpm-gemma-e4b-qlora-pilot/1`

Remote metadata was checked for privacy, and the submitted cells matched the local v2 notebook. The old task-owned interactive session was stopped before the batch to avoid duplicate GPU use. The completed batch used one GPU0 from its free T4 x2 allocation. No paid upgrade, public publishing or schedule was created.

Executed command forms, from `care-assistant/`:

```sh
finetuning/kaggle/kaggle-cli.sh kernels push \
  -p finetuning/kaggle/cli-run --accelerator NvidiaTeslaT4 --timeout 7200
finetuning/kaggle/kaggle-cli.sh kernels status \
  bhavithlolakapuri/chest-bpm-gemma-e4b-qlora-pilot
finetuning/kaggle/kaggle-cli.sh kernels output \
  bhavithlolakapuri/chest-bpm-gemma-e4b-qlora-pilot \
  -p finetuning/runs/kaggle-output-v1 \
  --file-pattern '.*care-e4b-pilot-artifacts[.]zip$'
```

Do not rerun push to inspect results; it starts another job. The existing output/proof is sufficient. Notebook SHA-256: `235a57c073091e2b632cc22947c9607404d4793521836f4d295e6f79f055e993`. The embedded 40-file allowlist excludes sealed tests, private data and prior evaluations. See [README.md](README.md) and [../RESULTS.md](../RESULTS.md) for actual training and evaluation evidence.
