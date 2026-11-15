# V6: test pretrained sound features

**Question:** Does prior training on general audio produce more useful fixed murmur features than the same randomly initialized network?

The controlled factor is the encoder's weights. Both arms use the same CNN6 architecture, native-resampled public input audio, usable-window rules, classifier, fitting weights, regularization and 0.60 decision threshold. Each arm gets one fixed classifier fit. Neither uses regression data or threshold search. The app's M model remains the comparison baseline.

This follows the general transfer-learning direction studied in [Niizumi et al., EMBC 2024](https://arxiv.org/abs/2404.17107). It is a small frozen-feature experiment, not a reproduction of their M2D/CNN14 fine-tuning results.

## Fixed setup

- Encoder: [PANNs CNN6](https://github.com/qiuqiangkong/audioset_tagging_cnn/tree/d2f4b8c18eab44737fcc0de1248ae21eb43f6aa4), AudioSet pretrained weights from [Zenodo](https://zenodo.org/records/3987831). Upstream code is MIT licensed; the weights' repository API declares CC BY 4.0. Attribution/license text is preserved under `third_party/`.
- Weight SHA-256: `8a17541944f2623a2a0164e072ac2f915dcedca99968083cc44bfbc7eb682275`.
- Inputs: unchanged native 2 kHz audio, four-second usable windows. Linear upsampling meets the pretrained encoder's 32 kHz input shape; it adds no signal bandwidth. This is a fixed research adapter, not evidence that it reproduces a phone microphone.
- Features: published frozen CNN6 embedding, 512 values per window. The random arm uses seeded Xavier initialization and the same architecture and fixed spectral frontend.
- Classifier: weighted training-only feature normalization and three-class logistic regression, `C=1`, at most 2,000 solver iterations. Each recording has equal total weight within its class; classes have equal total fitting weight. No encoder fine-tuning.
- Evaluation: mean probabilities across the native usable windows. A recording without usable windows remains unsure. Compare recording and linked-person outcomes on reused selection and calibration partitions.
- Promotion: the existing strict no-regression checks apply. The pretrained arm must add positive detection without worsening the predeclared errors or uncertainty. Development success would still require verified CoreML conversion, frozen regression comparison and physical-device checks. Neither arm enters the app automatically.

`protocol.json` fingerprints the feature source, classifier source, cohort, metrics, decision rule and pretrained weights before extraction. Both fitted classifiers are frozen before either development outcome is read. Generated files stay outside source control.

Run with the existing public caches:

```sh
ChestBPM/.venv-ml/bin/python research/panns_murmur_features.py
research/.venv/bin/python research/fit_panns_murmur_probe.py
```

Each command refuses to overwrite a completed experiment. This work can test a model improvement; it cannot supply the missing independent clinician-labeled phone cohort.

## Completed result

Both arms failed the predeclared development checks. Keep the app's M model. The following totals combine the two reused development partitions; they are not independent validation.

| Recording outcome | App baseline | Pretrained encoder | Random encoder |
|---|---:|---:|---:|
| Positive recordings detected / 70 | 49 | 24 | 26 |
| Positive recordings called absent | 8 | 15 | 6 |
| Positive recordings returned unsure | 13 | 31 | 38 |
| False alarms / 274 absent recordings | 5 | 1 | 1 |
| Correct absent results | 178 | 88 | 58 |
| Expert-unknown recordings kept unsure / 23 | 17 | 21 | 21 |
| Total unsure / 367 recordings | 121 | 237 | 274 |

The pretrained encoder reduces uncertainty relative to the random control, but does not improve positive detection over it in this setup. Both are substantially worse than the app baseline at detecting positive recordings. The coefficients were frozen before scoring. Neither advanced to CoreML conversion or regression evaluation. See `results/murmur-v6-pretrained-probe.json`.

This rejects the fixed frozen-feature setup. It does not test encoder fine-tuning. The pretrained model's broad frequency frontend may also be poorly matched to a 2 kHz input; inspect `results/murmur-v6-bandwidth-diagnosis.json` before choosing a focused follow-up. That remains a hypothesis, not an established explanation for these errors.
