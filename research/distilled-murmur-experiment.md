# V8: teach V4 with the frozen baseline

**Question:** Can baseline guidance reduce V4's extra errors while preserving its ability to learn from murmur and heartbeat-phase annotations?

V5's sampler change and the V6/V7 frozen generic-audio probes did not support replacing the app model. V8 returns to V4's cardiac-specific architecture and changes one training term.

Add `0.20 × KL(student / T, teacher / T) × T²`, with `T=2`, to V4's existing loss. The teacher is the frozen M app baseline. Its probability outputs are converted to tempered soft targets. The teacher receives the same augmented features as the student and never receives gradients. The coefficient and temperature follow the existing recipe in `ChestBPM/ML/murmur_timing_model.py`; neither is searched in this experiment.

Keep V4's architecture, student initialization seed, original sampler, phase/timing losses, augmentation, optimizer, epochs, steps, 0.60 threshold and development-only checkpoint rule unchanged. Teacher construction preserves the student's RNG streams. Preflight checks confirm matching student initialization, teacher probability decomposition, frozen teacher parameters and finite student gradients. Epoch-zero selection outcomes match V4.

Only original public training groups fit weights. Selection chooses the checkpoint; calibration is evaluated after the chosen weights are frozen. Both are reused development data. The teacher is a prior research model chosen through historical model development; distillation does not make the evidence independent. No regression or private phone audio enters this run.

After training, export only an eligible checkpoint and apply the stricter native recording/person checks from `murmur_focus_acceptance.json`. A failed development gate retains the baseline. A passed gate still requires frozen regression comparisons and device checks before any app replacement. Independent phone-microphone accuracy remains unproved.

```sh
ChestBPM/.venv-ml/bin/python research/train_murmur_v8_distillation.py
ChestBPM/.venv-ml/bin/python research/evaluate_murmur_v8.py
```

Existing runs are preserved. Weights, teacher hash, original V4 source and protocol are fingerprinted for reproducibility. Source: `train_murmur_v8_distillation.py`; preflight evidence: `results/murmur-v8-preflight.json`.

## Completed result

The predeclared rule selected epoch 17. Freeze and native evaluation completed. V8 fails the strict development checks; keep the baseline. No regression set was scored and the app model was not replaced.

| Native recording outcome | App baseline | V8 |
|---|---:|---:|
| Positive recordings detected / 70 | 49 | 48 |
| Positive recordings called absent | 8 | 6 |
| Positive recordings returned unsure | 13 | 16 |
| False alarms / 274 absent recordings | 5 | 8 |
| Correct absent results | 178 | 210 |
| Expert-unknown recordings kept unsure / 23 | 17 | 12 |
| Total unsure / 367 recordings | 121 | 84 |

V8 makes more definite decisions, but adds false alarms and does not preserve murmur detection or expert-unknown retention. At the linked-person level, detection drops from 18/22 to 17/22 and false alarms rise from 0/70 to 4/70. These are reused development cohorts, not independent accuracy estimates.

CoreML conversion passed on 22 inputs including 18 public development audio clips, with all-output maximum differences below 0.000009. Those checks ran on the Mac. The selected app baseline's separate physical-iPhone check remains valid; rejected V8 was not installed as the app model.

See `results/murmur-v8-native-development.json` and the generated evaluation freeze for the full per-partition comparisons and fingerprints. This one fixed distillation term did not support replacing M. It does not prove that no other model could improve.
