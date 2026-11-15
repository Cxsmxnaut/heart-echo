# V11: M2D murmur comparison

Status: the paper-description GPU job completed all 50 rounds and its downloaded weights passed independent checks. All 12 transformer blocks changed; frozen pretrained tensors stayed identical. The released-code arm is still training. The final comparison is not yet complete. The original plan was saved before M2D results were available. The second arm was added after observing the first arm's early selection results, before any calibration evaluation. The app keeps M while this research comparison runs.

The user authorized trying the published [Niizumi et al., IEEE EMBC 2024](https://arxiv.org/abs/2404.17107) M2D murmur method. The [authors' implementation](https://github.com/nttcslab/m2d/tree/master/app/circor) supplies the checkpoint and model. This is a controlled adaptation to the project's existing cohorts, not a reproduction of the paper's reported accuracy.

## Frozen setup

- Model: approximately 85 million parameters; the authors' unchanged portable M2D encoder, pretrained checkpoint 300 from `m2d_vit_base-80x608p16x16-220930-mr7_enconly`. The wrapper fingerprints both artifacts. All 12 transformer blocks train. Patch and fixed positional embeddings stay frozen, as intended by the model configuration.
- Frontend: 16 kHz, five-second audio, FFT/window 400, hop 160, 80 mel bands from 50 to 8,000 Hz, published normalization of -7.1/4.2. Training crops overlap by 2.5 seconds; evaluation crops do not overlap. Short recordings are zero padded. The public source remains capped at 60 seconds.
- Training: 50 full rounds over public crops, batch 32, AdamW at 0.00025, weight decay 0.0001, betas 0.9/0.95, five warmup rounds and cosine learning-rate decay. Cross entropy uses class weights calculated from training crops. No SpecAugment, mixup or phone augmentation.
- Cohort: retain 2,356 training and 180 selection recordings, including the existing linked-person groups and recording-level murmur targets. All groups remain disjoint. No calibration or test data go to the cloud. Calibration is loaded locally only after the trained checkpoint has been chosen and frozen.
- Selection: maximize recording-level three-class balanced recall on selection using the existing 0.60 decision threshold. M2D combines five-second logits, following the paper's recording aggregation. No threshold search. One fixed seed, 20261120.
- Privacy: the upload contains an explicit allowlist of three research code files and public metadata. It contains no personal recording, phone profile or credential. Server metadata and the pulled source verify privacy and submitted code. Public audio and upstream assets are downloaded into Kaggle's temporary cache, outside the output folder.

## Differences from the paper and code

The paper used three different patient splits and averaged 15 runs; this experiment uses one seed on the existing project groups. It retains recording-specific murmur targets and selects using our fixed confidence rule rather than reproducing the paper's validation-window accuracy. These choices keep the comparison aligned with this project. Report reused development outcomes without treating them as independent accuracy estimates.

The paper describes AdamW, but the released batch command and the called Python function default to SGD. Its EVAR patch also applies softmax before cross entropy. The first arm explicitly follows the paper's AdamW description and uses ordinary cross entropy on logits. These choices were recorded before results. The wrapper uses the authors' unchanged portable runtime, the EVAR-style 3,840-feature normalization/classifier head, and SciPy polyphase resampling. The paper used Torchaudio for resampling. Both new arms use CUDA mixed precision as a computational adaptation.

A further source audit found two preparation details in the authors' notebook: it retains a final partial training crop of at least 2.5 seconds and pads it, and it writes resampled crops back to int16 WAV. Both of our arms retain full five-second crops from longer recordings and keep floating-point audio; only recordings shorter than five seconds are padded. These are additional shared preparation differences. Together with the different groups, labels and selection rule, they prevent calling either arm an exact reproduction of the published score. The released-code arm specifically reproduces the released optimizer/loss combination.

After seeing the first arm's first five selection rounds, a second arm was declared to test the released optimizer/loss combination as well. It uses SGD with momentum 0.9 and zero weight decay, plus the released softmax-before-cross-entropy calculation with double-precision class weights and one-hot soft targets. All model/data/seed/window/schedule/selection settings otherwise match. This second choice was not made blind to the first arm's early selection outcomes; report that honestly. No calibration outcome informed it.

Both complete 50-round runs must be retrieved and their chosen weights verified before any local calibration audio is loaded. Choose the main M2D candidate using the higher saved selection score only, with the paper arm winning ties. `freeze_m2d_comparison.py` records that choice, both weight hashes and the evaluation code hash. Local evaluation checks this joint freeze and requires the same evaluation code for both arms. Report both arms and do not replace this choice after seeing calibration or phone-style outcomes.

## Evaluation planned before results

Evaluate all 367 reused development recordings: 180 selection and 187 calibration, totaling 70 positive, 274 absent and 23 expert-unknown recordings. Record every unsure result. Compare recording and linked-person detection, positive-as-absent errors, false alarms, negative clearance and expert-unknown retention.

Three fixed input conditions:

1. Original public audio resampled to 16 kHz, retaining the original source bandwidth. This is descriptive evidence for the published method's input path.
2. The unchanged app reader's cached 2 kHz waveform, upsampled to 16 kHz. This is the main comparison against M on the same available sound information.
3. The exact frozen V10 phone-style PCM32 files, with source fingerprints checked. Compare against the saved M predictions on those identical files. No new private clinical labels are created.

The M baseline retains its original four-second windows and mean probabilities; M2D uses five-second windows and mean logits. This compares complete methods, not an isolated architecture change. The existing minimum-volume/clipping/finite-input gates apply to M2D's windows. Inputs shorter than the app's four-second minimum stay unsure; valid four-to-five-second inputs are padded for M2D. No original test or other consumed regression set is scored. No physical-phone accuracy or latency claim follows from these public recordings or from synthetic phone sound.

The existing strict recording/person checks remain. Report all tradeoffs even if the checks fail. An improvement would still need independent clinical phone evidence and engineering integration before any app use.

## License and artifacts

### Bounded TPU speed investigation

The user asked whether Kaggle's TPU could shorten the run, then limited total TPU setup to 30 minutes. A separate private speed probe used synthetic inputs only, with no audio, patient metadata, clinical score or model export. The GPU runs continued throughout.

The default TPU image lacked a PyTorch TPU backend. Installing the native backend did not produce a registered usable TPU device. A paired legacy CPU PyTorch/XLA setup required a Python 3.13-compatible libtpu patch; its initialization did not reach a training step before the hard deadline. The final notebook had an absolute setup deadline and bounded subprocesses. At the follow-up check, Kaggle reported `CANCEL_ACKNOWLEDGED` after the notebook timeout.

TPU setup was stopped at the user's limit. No TPU speed or accuracy result was measured, and no clinical training run was moved to TPU. Do not interpret this setup failure as a hardware speed comparison. `generated/murmur-v11-m2d/tpu-summary.json` and `tpu-time-limit.json` record the outcome. Do not restart TPU setup without a new user request.

The upstream package uses NTT's non-commercial internal-evaluation license, not MIT. This run is a private research comparison; it does not authorize app distribution. See `third_party/M2D-NOTICE.md` and the linked original license. No upstream implementation or trained weight is added to source control.

Ignored artifacts: `generated/murmur-v11-m2d/`, including `public-kaggle/`, `remote-submission/`, `source-job.json`, the retrieved training archive and local comparison. The official runtime/checkpoint live in ignored `cache/m2d-weights/`. Preserve completed runs and use new output directories for reproduction.

```sh
ChestBPM/.venv-ml/bin/python -m unittest discover -s research -p test_m2d_murmur.py -v
ChestBPM/.venv-ml/bin/python research/build_m2d_job.py --output research/generated/NEW_M2D_JOB
# Build the released-code arm in another directory with --released-recipe.
# Run the private GPU notebook, retrieve heart-m2d-stage.zip, and verify all fingerprints.
ChestBPM/.venv-ml/bin/python research/freeze_m2d_comparison.py --paper research/generated/murmur-v11-m2d/source-stage/artifacts --released research/generated/murmur-v11-m2d/released-source-stage/artifacts --output research/generated/murmur-v11-m2d/joint-selection-freeze.json
ChestBPM/.venv-ml/bin/python research/evaluate_m2d_murmur.py --source research/generated/murmur-v11-m2d/source-stage/artifacts --output research/generated/NEW_M2D_COMPARISON
```

Local checks passed before upload: expected pretrained layout and outputs, gradients in all 12 transformer blocks, frozen patch/position parameters, five-second window boundaries, confidence/unknown rules and rejection of forbidden data before downloads. No Graphify graph or managed refresh command exists in this repository; evidence comes from current source and fingerprinted artifacts.
