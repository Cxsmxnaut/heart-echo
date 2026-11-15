# Murmur model decision — 2026-11-15

**Keep the app's existing phase-aware M model. Reject V4, V5, the V6/V7 frozen-feature probes, V8, V9 and the V10 two-stage candidate as app replacements. Phone reliability is still unproved.**

V4's extra false alarms also appear before Apple conversion. On aligned inputs, PyTorch and CoreML probabilities differ by at most 0.0000036. Conversion is not the main explanation. V4 overrepresents uncertain examples during training; that was a plausible cause to investigate, not a proven explanation.

V5 tested one change: different proportions of absent, present and unknown training crops. Architecture, loss, optimizer, seed, data partitions, training duration and decision threshold stayed fixed. The original checkpoint rule selected epoch 20. No checkpoint was chosen using regression results.

## Native development results

Each cell shows **baseline / V5**. These sets were used during development and are not independent validation.

| Recording outcome | Selection: 180 recordings | Calibration: 187 recordings |
|---|---:|---:|
| Positive recordings detected | 25 / 21 of 34 | 24 / 21 of 36 |
| Positive recordings called absent | 3 / 2 | 5 / 8 |
| Positive recordings returned unsure | 6 / 11 | 7 / 7 |
| False alarms on absent recordings | 1 / 2 of 136 | 4 / 2 of 138 |
| Correct absent results | 88 / 125 | 90 / 120 |
| Absent recordings returned unsure | 47 / 9 | 44 / 16 |
| Expert-unknown recordings kept unsure | 9 / 3 of 10 | 8 / 2 of 13 |
| All unsure results | 62 / 23 | 59 / 25 |

V5 makes more definite decisions, but detects fewer murmurs and calls more expert-unknown recordings absent. It fails the checks set before results were available. Its reduced uncertainty is not a safe improvement.

At the linked-person level, the baseline detects 9/11 positive people in each development partition; V5 detects 8/11 in each. Among 35 absent people per partition, baseline false alarms are zero; V5 produces one per partition. These summaries combine available recording sites and repeat visits. They are descriptive research summaries, not a validated patient diagnosis.

The sampler change did not solve V4's problem. This single seeded run does not isolate a universal cause or prove that this architecture cannot improve.

The follow-up V6 pretrained-versus-random encoder experiment also failed its development checks. Its pretrained arm detected 24/70 positive recordings across the two development partitions, compared with the baseline's 49/70, and returned 237/367 unsure results versus 121/367. No V6 model was converted or scored on regression data. See `pretrained-murmur-experiment.md` for the controlled setup and complete outcome table.

V7 changed only the frequency layout in that probe. Its pretrained arm detected 21/70 positives and returned 241/367 unsure results. It was rejected before conversion or regression. See `heartband-murmur-experiment.md`.

V8 returned to V4 and added one fixed distillation loss from the frozen M baseline. Its epoch-17 checkpoint was frozen, converted and evaluated through the native reader. It detected 48/70 positives versus M's 49/70, called 6 positives absent versus 8, returned 16 positives unsure versus 13, and raised 8 false alarms versus 5. Total unsure fell from 121/367 to 84/367, but expert-unknown retention also fell from 17/23 to 12/23. At the linked-person level it added four false alarms among 70 absent people, compared with zero for M. This is not a supported replacement. Conversion passed on 22 inputs; no regression set was scored. See `distilled-murmur-experiment.md`.

## Checks and frozen artifacts

- The app package and native reader match their saved SHA-256 fingerprints.
- Selected V5 weights, package files, evaluator, native probe, cohort manifest, metric code and 0.60 threshold were fingerprinted before native evaluation. V5 never advanced to regression scoring.
- Both baseline and V5 conversions agree with PyTorch within 0.001 on all outputs across 22 inputs, including 18 public development audio clips. These checks ran on this Mac's CoreML runtime. They do not measure physical-phone accuracy or latency.
- The frozen baseline subsequently passed a physical iPhone check on iOS 27.0.1: all three bundled public samples produced exactly the same probabilities and window counts as the Mac native reader. Seven invalid-input/unknown-label controls passed. An isolated validation build used the existing app identifier; product source, weights, personal recordings and settings were preserved. The normal app was restored and launched afterward. Results are in `results/murmur-baseline-phone.json`. These were public stethoscope recordings played through the inference code, not new microphone recordings.
- Five metric/data tests passed, including checks that unsure results stay visible and repeat visits never cross partitions.
- Native rule and noise-control outcomes are saved in `results/murmur-focus-decision.json`.
- No configured Graphify graph or managed launcher was found. Conclusions use current source and measured artifacts; no graph refresh was available.

Reproduce with the existing public caches and `ChestBPM/.venv-ml/bin/python`:

```sh
ChestBPM/.venv-ml/bin/python -m unittest discover -s research -p test_murmur_focus.py
ChestBPM/.venv-ml/bin/python research/evaluate_murmur_v5.py
ChestBPM/.venv-ml/bin/python research/finalize_murmur_focus.py
```

Training runs are preserved and refuse to overwrite themselves. The saved original training source and protocol document how to reproduce a run in a separate output directory. Generated weights/caches stay outside source control.

## Remaining work

This completes a documented model-choice milestone. It does not meet the larger high-reliability goal. The baseline still misses murmurs and returns many unsure results. A fresh, appropriately labeled phone cohort remains necessary to measure the intended use; reusing old development or regression sets cannot establish that evidence. Identify available independent public evidence before expanding training or making stronger claims. See `murmur-focus-plan.md` for the predeclared research ambitions and limitations.

The follow-up search found no suitable fresh public phone cohort among the reviewed sources; see `phone-evidence-review.md`. The current-state audit in `results/murmur-reliability-audit.json` separates completed engineering requirements from the unmet reliability requirement. No clinical reliability claim is supported.

The model-choice and conversion work is complete. The broader request for genuinely reliable phone results remains unmet: even the baseline's reused-development positive detection is 49/70, and no representative independent clinician-labeled phone cohort was verified. The same missing evidence has persisted across the focused goal turns. Closing it requires authorized phone data with appropriate reference labels and a patient-level development/validation plan. Do not train on the only consumed phone regression set and then present its score as independent validation. The existing baseline stays frozen while that external evidence is unavailable.

## V9: phone-style fine-tuning — completed November 15, 2026

The user authorized using yesterday's and today's recordings to approximate phone sound during public-data training. This experiment completed real fine-tuning of M. It did not produce a supported app replacement.

Five local chest recordings supplied unlabeled spectral and volume statistics: three confirmed case-off clips today and two quiet clips yesterday, including the retained partial attempt. Two off-chest recordings supplied noise power statistics. Today's first, case-on recording was excluded. No private murmur targets, app-prediction labels, Watch targets or private heartbeat waveforms were inserted into the public examples. The private statistics do influence the research weights; this is not an exclusively public-input experiment.

The transformation applies a smooth, symmetric filter bounded to ±6 dB, phone-like volume, and synthesized noise at 24–36 dB signal-to-noise ratio. Noise copies only the measured power spectrum, not recorded heartbeat cycles. Duration and annotation times stay fixed. These unpaired differences include anatomy and placement; they do not identify the microphone's true response or guarantee that every faint murmur stays audible.

The source is [CirCor DigiScope 1.0.3](https://physionet.org/content/circor-heart-sound/1.0.3/), credited to Oliveira and colleagues under the dataset license recorded in `ChestBPM/ML/murmur-manifest.json`. A source reference used 90 training people only, with equal class counts and at most one recording per person. The original patient partitions were retained: 2,356 training recordings, 180 selection recordings and 187 calibration recordings. One training recording lacked usable paired crops, leaving 2,355 for sampling. Selection and calibration are reused development evidence.

Two arms started from identical frozen M weights. Both ran eight epochs and 640 optimizer steps with the same seed, sampler, optimizer, clean teacher and supervision. The control's second view was clean; V9's was phone-style. Selection used the predeclared minimum of clean/style three-class balanced recall, with their mean as tie-breaker. Calibration was scored after both chosen weights were frozen. The selected epochs were control 8 and V9 7. Independent verification confirmed 50 changed, finite weight tensors per arm and an unchanged waveform frontend.

### Native results

These totals combine both reused development partitions: 70 positive, 274 absent and 23 expert-unknown recordings. They are not independent phone accuracy estimates.

| Outcome on original public audio | App M | Clean fine-tune | Phone-style V9 |
|---|---:|---:|---:|
| Positive recordings detected / 70 | 49 | 53 | 52 |
| Positive recordings called absent | 8 | 8 | 9 |
| False alarms / 274 absent recordings | 5 | 9 | 9 |
| Correct absent results | 178 | 202 | 207 |
| Expert-unknown recordings kept unsure / 23 | 17 | 11 | 13 |
| Total unsure / 367 | 121 | 83 | 80 |

| Outcome on simulated phone-style public audio | App M | Clean fine-tune | Phone-style V9 |
|---|---:|---:|---:|
| Positive recordings detected / 70 | 49 | 54 | 53 |
| Positive recordings called absent | 10 | 10 | 10 |
| False alarms / 274 absent recordings | 6 | 8 | 9 |
| Correct absent results | 212 | 235 | 220 |
| Expert-unknown recordings kept unsure / 23 | 7 | 6 | 9 |
| Total unsure / 367 | 74 | 43 | 61 |

V9 increases detection relative to M but adds false alarms and does not consistently beat matched clean fine-tuning. It fails the existing strict recording/person checks. Keep M. No old CirCor regression or PASCAL test was scored, no app update was installed, and the BPM model was not fine-tuned in this murmur experiment.

Both candidates were exported to separate Core ML packages. Conversion passed on 16 aligned inputs per candidate; all-output maximum differences were below 0.000002. The complete native comparison checked all 367 recordings in both input conditions for all three models. Native and cached-feature mean probabilities matched within 0.0000005, with matching audio lengths. The candidate's 13 native input/rule checks, six augmentation/data-boundary tests and five existing metric tests passed.

The first evaluation used IEEE-float WAVs that `AVAudioFile` read short on this Mac. A same-sample format check isolated the container difference; PCM32 preserved the full input. The final native evaluation uses PCM32 and asserts lengths and whole-cohort probability agreement. The earlier files, results and evaluator remain under `float-wav-reader-audit/`. This correction changed test packaging, not weights, selection, threshold or product code.

### Sources and reproduction

Implementation: `phone_style.py`, `prepare_phone_murmur.py`, `train_phone_murmur.py`, `evaluate_phone_murmur.py` and `test_phone_style.py` in this directory. All private profiles, derivative audio, learned weights and results remain ignored under `generated/murmur-v9-phone-style/`. Important artifacts are `protocol.json`, `training-verification.json`, `comparison.json`, `native-comparison.json`, and `phone-style/Murmur.mlpackage`.

From the workspace root, use a **new** output directory; completed experiments refuse overwrites:

```sh
ChestBPM/.venv-ml/bin/python research/prepare_phone_murmur.py --today-cohort HeartEcho/diagnostic-logs/2026-11-15-phone-review/cohort.json --yesterday ChestBPM/diagnostic-logs/2026-11-14-v17-final-two-cycles --output research/generated/NEW_RUN
ChestBPM/.venv-ml/bin/python research/train_phone_murmur.py --run research/generated/NEW_RUN
ChestBPM/.venv-ml/bin/python research/evaluate_phone_murmur.py --run research/generated/NEW_RUN
```

After verification, a full temporary disk required removing only this run's reproducible training-feature cache. Source audio, personal recordings, models and all results were retained. `rebuild_phone_cache.py --run research/generated/murmur-v9-phone-style --role training` restores missing features with exact hash checks; `--max-files 1` passed a bounded restoration check. Check available disk space before restoring the full cache.

Method background: [Kośmider, Spectrum Correction: Acoustic Scene Classification with Mismatched Recording Devices](https://www.isca-archive.org/interspeech_2020/kosmider20_interspeech.pdf). This experiment borrows the broad spectral-correction idea; that paper does not validate this heart-sound transformation or our phone use.

## V10: full public-model training, then a separate phone layer — completed November 15, 2026

The requested two-stage experiment completed. The phone layer recovers some of ResNet18's lost detections on simulated phone sound, but adds false alarms and still detects fewer positives than M. Keep M in the app. All new weights, exports and results are preserved separately.

### Stage one: train the main model

Two standard architectures were adapted to heart-sound spectrograms and actually fine-tuned through their main feature layers:

- [PANNs CNN6](https://github.com/qiuqiangkong/audioset_tagging_cnn), initialized from the official AudioSet checkpoint: 40 training rounds, 4,800 optimizer updates, selected round 34. Sixteen backbone parameter tensors changed.
- [ResNet18](https://docs.pytorch.org/vision/main/models/generated/torchvision.models.resnet18.html), initialized from official TorchVision ImageNet weights, with the first convolution averaged to one input channel: 18 rounds, 2,160 updates, selected round 6. Sixty backbone parameter tensors changed. Later rounds did not improve the selection score, so the declared stopping rule ended this run.

Both use 64 frequency bands between 25 and 950 Hz, four-second windows and three outputs: Absent, Present and Unknown. These are adaptations of standard architectures, not reproductions of published clinical scores. The initial two rounds train the new classifier; subsequent rounds train the full backbone. Sampling balances classes and retains expert-unknown and synthetic-noise controls. A training round contains 120 sampled batches; repeated crops are not new independent recordings.

Only public CirCor training and selection data went to the private Kaggle GPU notebook: 2,356 training recordings and 180 selection recordings, with linked people kept in one partition. Checksums verify public downloads, submitted source, retrieved source and trained weights. Server metadata confirmed that the notebook remained private. No personal recording, phone profile, calibration or test recording was uploaded. Independent local checks confirmed that both selected backbones changed and all saved tensors are finite.

The fixed selection rule chose ResNet18 before phone-layer training: three-class balanced recall was 0.7544 versus CNN6's 0.7113 on the source preprocessing. These are reused development scores. The source GPU uses SciPy resampling; the later native comparison separately checks the app's reader.

### Stage two: learn phone correction locally

ResNet18's weights and running statistics were frozen. A separate 128 → 32 → 64 layer learned a bounded change to each frequency band, constant across a window's time axis. It can reweight sound already present; it cannot insert or move heartbeat cycles. The layer started as an identity transform.

The layer trained locally for 16 rounds and 1,280 updates, using synthetic clean/phone pairs made from public training audio and the V9 profile. The profile uses yesterday's and today's unlabeled recordings, excludes today's case-on recording, and never leaves this computer. Public murmur labels and the frozen clean model's predictions help preserve the task. No private clinical target was created. Every clinical weight and running statistic remained exactly unchanged while all four adapter tensors learned changes.

The predeclared selection rule chose adapter round 6. Both chosen weights and the 0.60 threshold were frozen before loading calibration audio. The original test partition and other consumed regression sets were not scored. The unpaired profile approximates sound differences; it does not measure a true microphone transfer function or establish real-phone accuracy.

### Native comparison

Both reused development partitions are combined below: 70 positive, 274 absent and 23 expert-unknown recordings. The same public recordings were tested before and after a fixed simulated phone transformation. That transformation has a different deterministic seed from V9, so its styled totals should not be compared directly with V9's styled totals.

| Outcome on original public audio | App M | ResNet18 | ResNet18 + phone layer |
|---|---:|---:|---:|
| Positive recordings detected / 70 | 49 | 48 | 47 |
| Positive recordings called absent | 8 | 9 | 9 |
| Positive recordings returned unsure | 13 | 13 | 14 |
| False alarms / 274 absent recordings | 5 | 9 | 9 |
| Correct absent results | 178 | 195 | 181 |
| Expert-unknown recordings kept unsure / 23 | 17 | 17 | 19 |
| Total unsure / 367 | 121 | 100 | 117 |

| Outcome on simulated phone-style public audio | App M | ResNet18 | ResNet18 + phone layer |
|---|---:|---:|---:|
| Positive recordings detected / 70 | 49 | 41 | 47 |
| Positive recordings called absent | 10 | 17 | 10 |
| Positive recordings returned unsure | 11 | 12 | 13 |
| False alarms / 274 absent recordings | 7 | 7 | 11 |
| Correct absent results | 218 | 230 | 163 |
| Expert-unknown recordings kept unsure / 23 | 10 | 10 | 18 |
| Total unsure / 367 | 70 | 59 | 131 |

The phone layer raises ResNet18's simulated-phone detection from 41 to 47, but raises false alarms from 7 to 11 and total unsure results from 59 to 131. It fails the existing recording/person checks in both partitions. This is evidence of a partial benefit from the correction layer, not a supported replacement or proof of reliable phone detection.

CNN6 was also scored in PyTorch on the same native-reader waveforms: on original/styled audio it detected 46/36 positives, raised 3/2 false alarms and returned 101/56 unsure results. It did not beat M's positive detection. CNN6 was not exported; the selected ResNet18 and its adapted version were exported and checked through Core ML.

Conversion passed on ten inputs per exported model, including six public audio examples. The largest all-output difference was below 0.000001. Native evaluation covered all 367 recordings in both input conditions for M, ResNet18 and the adapted model. Mean probabilities agreed with the feature-based evaluation within 0.0000011 across every recording, and all audio lengths matched. Styled WAVs use PCM32 to avoid the previously identified float-container reader issue. The adapted package passed all 13 native input/rule checks. The six two-stage tests passed, including frontend agreement, real backbone gradients, a frozen clinical model during adapter learning, and rejection of calibration/test records before any cloud download. The unchanged app passed its port verification: 38 origin hashes, 26 exact copies and both shipping model packages matched.

No app update was installed. This experiment did not modify or train the BPM model. Physical-phone runtime, new labeled phone accuracy and independent clinical validation were not tested.

### Artifacts and reproduction

Implementation: `two_stage_models.py`, `train_public_backbones.py`, `build_public_backbone_job.py`, `train_phone_adapter.py`, `evaluate_two_stage_murmur.py` and `test_two_stage_murmur.py`. PANNs and TorchVision licenses are retained under `third_party/`.

Ignored artifacts are under `generated/murmur-v10-two-stage/`. The submitted notebook and upload audit are in `public-kaggle/`; downloaded frozen GPU artifacts are in `source-stage/artifacts/`; local training, final predictions, both Core ML packages, native results and the final summary are in `local-adapter/`. `source-verification.json` records the independent backbone check. `source-job.json` records the completed cloud job and verified download.

To reproduce, build a new allowlisted notebook with `build_public_backbone_job.py --output research/generated/NEW_PUBLIC_JOB`, run that notebook with a GPU, retrieve its `heart-public-source-stage.zip`, and verify its source/weights against the upload audit. Keep private profile data local. Use a fresh local output directory:

```sh
ChestBPM/.venv-ml/bin/python -m unittest discover -s research -p test_two_stage_murmur.py
ChestBPM/.venv-ml/bin/python research/train_phone_adapter.py --clinical-dir research/generated/murmur-v10-two-stage/source-stage/artifacts --profile research/generated/murmur-v9-phone-style/phone-profile.json --output research/generated/NEW_LOCAL_ADAPTER
ChestBPM/.venv-ml/bin/python research/evaluate_two_stage_murmur.py --run research/generated/NEW_LOCAL_ADAPTER --clinical-dir research/generated/murmur-v10-two-stage/source-stage/artifacts --profile research/generated/murmur-v9-phone-style/phone-profile.json
```

Completed training and native comparisons refuse overwrites. Private profiles and native public-audio caches are required for the exact local reproduction. There is still no configured Graphify graph or refresh command; these conclusions use the current source, frozen fingerprints and measured results.
