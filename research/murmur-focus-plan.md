# Murmur model: focused improvement and reliability

Only murmur model work is in scope. No app features, care work, videos, or other disease models.

**Completed experiment:** V5 finished and failed the predeclared native development checks. Keep the existing M model. See `murmur-model-decision.md` and `results/murmur-focus-decision.json`. The high-reliability goal remains open.

## Current evidence

The shipping model is preserved in `results/murmur-focus-baseline-freeze.json`.
V4's native calibration comparison detected 26/36 positive recordings instead of 24/36, but false alarms increased from 4/138 to 8/138 and total unsure results increased from 59/187 to 74/187. It is not a supported replacement.

Paired diagnosis rules out native conversion as the main false-alarm explanation: all eight V4 calibration false alarms also occur with the original training preprocessing. The aligned PyTorch/native probability difference is at most 0.0000036. Preprocessing still changes some individual results, so final comparisons must use the native pipeline.

Confirmed training imbalance: source training recordings are 1,913 absent, 325 present and 118 unknown. V4 batches instead contain eight absent, eight present, and fourteen unknown examples including six synthetic noise controls. This may contribute to poor decision calibration; it does not prove a complete cause.

## Completed controlled experiment: V5

Change only the crop sampler: 15 absent, seven present, two expert-unknown and six synthetic-unknown crops per batch. Keep the V4 architecture, initialization seed, data split, augmentation, loss, optimizer, epochs, steps and decision threshold unchanged. Select on development data only. Freeze the selected weights before any regression scoring. Preserve unsuccessful candidates and the shipping package.

Evaluate recording and linked-person outcomes separately: detected positives, positives called absent, positives returned unsure, false alarms, correct absent results and total unsure results. Do not hide abstentions or count correlated recordings as independent people. Only promote if predeclared native checks and regression comparisons support replacement.

## Completed controlled experiment: V6 frozen pretrained features

The physical iPhone now passes public-sample execution parity and seven invalid-input controls with the preserved M baseline. The public evidence review did not verify a fresh clinician-labeled phone cohort. Accuracy still needs improvement as well as independent validation.

V6 tests pretrained versus random weights in the same fixed CNN6 encoder, with identical small classifier fits. Both arms use only the original public training groups for fitting. No encoder fine-tuning, architecture/threshold search, regression evaluation or app replacement is automatic. See `pretrained-murmur-experiment.md` for the predeclared design and license attribution.

Both arms failed the development checks. Keep the baseline. The pretrained arm detects 24/70 positive development recordings versus 49/70 for the baseline. Only 17 of its 64 mel filters are centered below the native input's 1 kHz information limit; the encoder pools frequency by a factor of 16. This motivated the V7 experiment below, which also failed its development checks.

## Completed follow-ups: V7 and V8

V7 tested that frequency-only frontend change and failed. V8 returned to V4 and added one fixed baseline-distillation term, preserving the other training choices. V8 selected epoch17, passed conversion checks and failed native development promotion: 48/70 positives detected versus49/70 baseline, eight false alarms versusfive, and poorer expert-unknown retention. Neither V7 nor V8 was scored on regression data or promoted.

See `heartband-murmur-experiment.md` and `distilled-murmur-experiment.md`. Keep M as the documented frozen model choice. The device-execution milestone is verified. The full reliability goal remains unmet pending suitable independent phone data; further public-data tuning cannot establish phone accuracy on its own.

## What “genuinely reliable” requires

A very high score on reused data does not establish reliability. Our aspirational research target is at least 99% sensitivity and specificity among answered cases, at least 95% coverage on independently assessed usable recordings, and at least 95% positive detection and negative clearance when unsure results remain in the denominators. Show confidence intervals and performance by population, phone/device and recording conditions. These are project ambitions, not established clinical acceptance standards or a promise.

Meeting those targets on previously untouched people and representative phone recordings remains unproved. Current CirCor development/test cohorts and the PASCAL phone recordings have already been inspected. They are regression evidence. More training cannot make them independent again. A fresh, clinician-labeled phone cohort with a frozen model and predeclared protocol is needed for the intended phone use; its size and acceptance criteria need appropriate clinical/statistical review. No private patient recordings are collected or used in this work.

Reference: IMDRF, *Good machine learning practice for medical device development: Guiding principles* (2025), principles 3–6 and 8: representative inputs/populations, independent testing, suitable reference labels and clinically relevant testing. https://www.imdrf.org/sites/default/files/2025-02/IMDRF_AIML%20WG_GMLP_N88%20Final.pdf

A model-choice milestone may be completed while the larger reliability goal remains unmet. Do not mark the reliability goal achieved based on this experiment alone.
