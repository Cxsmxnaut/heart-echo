# V7: frequency-only frontend experiment

**Question:** Does using the encoder's frequency grid for the available heart-sound band improve the failed V6 probe?

V6 receives 2 kHz native audio, so its input contains no independent signal information above 1 kHz. Only 17 of its 64 pretrained mel filters have centers below that limit. The encoder then pools the frequency axis by a factor of 16. This suggests a mismatch worth testing; it does not establish why V6 failed.

V7 makes one change: retain those 17 existing log-mel bands and resize them to the same 64-band input grid. It does not change the FFT, time resolution, audio, native usable-window checks, encoder architecture or weights, random seed, classifiers, fitting weights, regularization, threshold or evaluation rules. Resizing adds no information. Both pretrained and random encoder arms remain, and each gets one fixed classifier fit.

The same 16,810 windows from 2,723 non-test public recordings must match V6 exactly. Fit classifiers and feature scaling only on original training groups. Freeze both fits before reading development outcomes. Reused selection and calibration remain development evidence. No threshold search, regression scoring or app replacement follows automatically.

The original strict recording and linked-person promotion checks apply. Development success would still require CoreML conversion checks, frozen regression comparisons and device verification. Phone-microphone accuracy remains unproved.

Source: `panns_heartband_features.py`. Classifier fitting is byte-for-byte V6 code except the experiment output name, in `fit_panns_heartband_probe.py`. The V7 protocol fingerprints both sources and the original V6 source. PANNs attribution remains in `pretrained-murmur-experiment.md` and `third_party/PANNs-LICENSE.MIT`.

```sh
ChestBPM/.venv-ml/bin/python research/panns_heartband_features.py
research/.venv/bin/python research/fit_panns_heartband_probe.py
```

Requires the existing public caches. Both commands preserve completed experiments instead of silently refitting them.

## Completed result

Both arms failed development checks; retain the app baseline. No V7 CoreML model was created and no regression set was scored. These totals combine the two reused development partitions.

| Recording outcome | App baseline | V7 pretrained | V7 random |
|---|---:|---:|---:|
| Positive recordings detected / 70 | 49 | 21 | 32 |
| Positive recordings called absent | 8 | 9 | 8 |
| Positive recordings returned unsure | 13 | 40 | 30 |
| False alarms / 274 absent recordings | 5 | 3 | 3 |
| Correct absent results | 178 | 91 | 76 |
| Expert-unknown recordings kept unsure / 23 | 17 | 21 | 22 |
| Total unsure / 367 recordings | 121 | 241 | 247 |

Compared with V6, the frequency change reduced the pretrained arm's detection from 24 to 21 positive recordings and increased its total unsure outputs from 237 to 241. It increased the random arm's detection from 26 to 32, while adding two false alarms. This does not support replacing the baseline or continuing to tune this fixed pretrained probe.

The follow-up coefficient replay matches saved probabilities within 0.000001. Ranking diagnostics are in `results/murmur-frozen-probe-diagnostics.json`; training scores are in-sample and all development scores remain reused evidence. No threshold was changed or selected.
