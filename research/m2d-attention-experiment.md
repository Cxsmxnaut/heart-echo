# M2D learned attention — completed November 15, 2026

The requested replacement is implemented, trained, saved and verified. The new M2D inference path uses learned attention over time. In this run it detects more murmur recordings than the matched averaging control, but adds false alarms. It does not pass the app replacement checks. Heart Echo and its BPM model remain unchanged.

## What changed

`M2DAttentionMurmur` in `m2d_attention.py` replaces the final within-window time average with a learned weighted sum. A small network scores each of the 32 time positions in a five-second window, and a softmax makes their weights sum to one. The score starts at zero, giving equal weights and the original model's output before training. The existing aggregation of separate recording windows stays fixed.

The original fingerprinted M2D implementation remains as the comparison baseline. New trained inference uses `load_m2d_attention.py` and the full checkpoint at:

`generated/murmur-v15-attention/selection/selected-model/M2D-attention.pt`

Its adjacent `manifest.json` records the chosen checkpoint, weight hash and source fingerprints. The attention model is the normal path in this loader; it does not fall back to the original time average.

## Controlled training

Both arms started from the same selected V11 released checkpoint. The complete encoder and original normalization statistics stayed fixed. One arm trained a classifier with mean pooling; the other trained the same classifier plus attention pooling. Both used the same data, batches, loss, learning-rate schedule and decision cutoff. This compares the contribution of attention against a matched control.

The private [GPU run](https://www.kaggle.com/code/bhavithlolakapuri/heart-echo-m2d-attention-v15) completed 12 full rounds and 3,372 optimizer steps per arm on 35,909 public training windows. Only 2,356 training recordings and 180 selection recordings entered the cloud job. Generic phone perturbations used no personal recording or private phone profile. Training cached unaveraged time features in float16, converted them to float32 for fitting, and kept selection/inference in float32. Five-second windows, quality gates, separate-window mean logits and the 0.60 cutoff stayed fixed.

Three checkpoints per arm were retained. The declared selection rule chose `mean_epoch_8` and `attention_epoch_4` using the lower native/styled three-class balanced recall, with fixed tie breakers. Both choices were fingerprinted before their 187-recording calibration check. No choice was changed from calibration results. The original 180 selection predictions were preserved when assembling the 367-recording comparison.

## Full reused development comparison

There are 70 positive, 274 absent and 23 expert-unknown recordings. These people have been used in earlier development, so these are not independent validation results. Simulated phone sound does not establish real-phone accuracy.

| Native input | Murmurs caught / 70 | Positive recordings called absent | False alarms / 274 | Expert unknown kept unsure / 23 | Unsure / 367 |
|---|---:|---:|---:|---:|---:|
| Original app M | 49 | 8 | 5 | 17 | 121 |
| Frozen V11 M2D | 58 | 1 | 15 | 16 | 220 |
| Matched trained mean control | 55 | 8 | 13 | 11 | 70 |
| Trained attention | 58 | 8 | 14 | 9 | 76 |

| Fixed phone simulation | Murmurs caught / 70 | Positive recordings called absent | False alarms / 274 | Expert unknown kept unsure / 23 | Unsure / 367 |
|---|---:|---:|---:|---:|---:|
| Original app M | 49 | 10 | 7 | 10 | 70 |
| Frozen V11 M2D | 59 | 5 | 14 | 5 | 70 |
| Matched trained mean control | 55 | 8 | 10 | 4 | 23 |
| Trained attention | 57 | 8 | 13 | 5 | 21 |

Against the matched control, native attention gains three positive recordings, adds one false alarm and adds six unsure results. Simulated phone audio gains two positive recordings, adds three false alarms and removes two unsure results. At the linked-person level it detects no additional positive people over the control, while adding one native and two styled false alarms. Recording gains must not be presented as newly detected patients.

Matching V11's native total of 58 does not mean retaining exactly the same detections. Attention retains 9 of the 12 native and 9 of the 11 styled positive recordings that V11 added over M. It also loses one original M detection in each condition. Native expert-unknown retention falls below M, and the styled detection total falls below V11. The recording/person checks and paired gains/losses are preserved in the comparison JSON. No app replacement is supported.

## What was verified

- Five tests passed, including initial equivalence to a real M2D model, actual attention learning, fixed encoder/normalization during updates, reload equivalence, valid masked weights and preservation of time frames/label alignment in the cache.
- The server notebook was private and all seven uploaded source files matched. The returned archive, source, initializer, six trained heads, initial states, normalization and finite values passed local verification. All three attention parameter tensors and both classifier tensors changed in each attention checkpoint; only the classifier tensors changed in the controls.
- The selected attention head used nonuniform weights in all 704 valid native selection windows. Its average largest time weight was about 7.05%, compared with 3.125% for equal weighting. This proves the pooling learned different weights; it does not prove those weights identify the clinical murmur location.
- Cloud/local native probabilities agreed within 0.00002182 for all six candidates, with identical findings and window counts. Replayed frozen V11 predictions also matched the prior native/styled results.
- The full attention checkpoint was exported, reloaded and checked on 12 real public examples. The command-line loader also reproduced a frozen public example with zero probability difference.
- The original app model and native reader retained their fingerprints. No physical-phone model integration, new labeled phone cohort or independent clinical accuracy was tested.

## Artifacts and reproduction

All learned weights, private-derived local simulations and detailed results remain ignored under `generated/`. Original source audio, private recordings and earlier weights were preserved. M2D's NTT non-commercial internal-evaluation license still applies.

The run root is `research/generated/murmur-v15-attention/`. Its main artifacts are `source-stage/verification.json`, `selection/selection-freeze.json`, `selection/selected-model/`, `selection/full-inference-verification.json`, `evaluation/comparison.json` and `cli-inference-check.json`. `murmur-v15-attention-plan.md` preserves the protocol declared before training.

Run from the repository root. Use fresh output directories when repeating an import or comparison; completed/partial outputs refuse overwrites.

```sh
ChestBPM/.venv-ml/bin/python -m unittest discover -s research -p test_m2d_attention.py
python3 research/build_m2d_attention_job.py --output research/generated/NEW_ATTENTION/public-kaggle --bundle-directory research/generated/murmur-v12-targeted/public-native-dataset
```

The builder creates the allowlisted GPU notebook and its upload audit. Run it privately on a GPU, retain the returned `heart-m2d-attention.zip`, and verify it before scoring:

```sh
ChestBPM/.venv-ml/bin/python research/import_m2d_attention.py --archive PATH_TO_ZIP --output research/generated/NEW_ATTENTION/source-stage --audit research/generated/NEW_ATTENTION/public-kaggle/upload-audit.json --encoder research/generated/murmur-v11-m2d/released-source-stage/artifacts/M2D.pt
ChestBPM/.venv-ml/bin/python research/compare_m2d_attention.py --stage select --run research/generated/NEW_ATTENTION/source-stage --output research/generated/NEW_ATTENTION/selection
ChestBPM/.venv-ml/bin/python research/compare_m2d_attention.py --stage evaluate --run research/generated/NEW_ATTENTION/source-stage --freeze research/generated/NEW_ATTENTION/selection/selection-freeze.json --output research/generated/NEW_ATTENTION/evaluation
```

Load the already-trained model for research inference on a mono WAV:

```sh
ChestBPM/.venv-ml/bin/python research/load_m2d_attention.py --checkpoint research/generated/murmur-v15-attention/selection/selected-model/M2D-attention.pt --audio PATH_TO_MONO_WAV
```

There is no configured Graphify graph/runtime or refresh command in this repository. The conclusions above use current source, fixed fingerprints, measured outputs and the saved trained model.
