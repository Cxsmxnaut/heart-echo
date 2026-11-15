# Results and limitations

[Overview](../README.md) · [Run it](JUDGE_GUIDE.md) · [Credits](../CREDITS.md)

The shipped audio model is phase-aware **M** in `HeartEcho/Models/Murmur.mlpackage`. In the original phase-model report, “candidate” means this now-shipped model and “baseline” means the earlier v1 detector. Later research uses M itself as its baseline. The tables below distinguish the two.

## Reused development data

Public CirCor stethoscope recordings have recording-level murmur annotations. Linked people and repeat visits were grouped before partitioning. Combine the 180 selection and 187 calibration recordings: **367 recordings**, with 70 present, 274 absent and 23 expert-unknown labels.

| Outcome | Earlier v1 detector | Shipping phase-aware M |
| --- | ---: | ---: |
| Positive recordings detected | 42 / 70 | 49 / 70 |
| Positive recordings incorrectly called absent | 13 / 70 | 8 / 70 |
| Positive recordings returned unsure | 15 / 70 | 13 / 70 |
| False alarms on absent recordings | 4 / 274 | 5 / 274 |
| Absent recordings returned unsure | 84 / 274 | 91 / 274 |
| All unsure outcomes, including expert-unknown examples | 117 / 367 | 121 / 367 |

**Tradeoff:** M found more positive recordings and made fewer confident misses, with one additional false alarm and more unsure outcomes. Unsure is neither a detection nor a confirmed negative. Positive recordings not detected include both confident misses and unsure outcomes.

Both partitions were reused during development. They are not a fresh independent test or a phone-accuracy study. [Source report: `roles.selection` and `roles.calibration`](../ChestBPM/ML/murmur-phase-report.json)

## Retrospective regression cohort

The original 440-recording test cohort had already been inspected during the earlier model's work. M's weights/rules were frozen before its regression evaluation, but this remains consumed historical evidence.

| Outcome | Earlier v1 detector | Shipping phase-aware M |
| --- | ---: | ---: |
| Positive recordings detected | 75 / 104 | 87 / 104 |
| Positive recordings incorrectly called absent | 6 / 104 | 4 / 104 |
| Positive recordings returned unsure | 23 / 104 | 13 / 104 |
| False alarms on absent recordings | 10 / 321 | 12 / 321 |
| All unsure outcomes | 110 / 440 | 106 / 440 |

The other 15 recordings had expert-unknown labels. These are recording counts, not clinical diagnoses or a new independent accuracy estimate. [Report: `roles.test`](../ChestBPM/ML/murmur-phase-report.json) · [Methods](../ChestBPM/Research/murmur-phase-v2.txt)

## Engineering evidence

**Fresh-checkout verification:** the published source snapshot was exported into an empty temporary directory, without saved keys, private datasets or app build products. Dependency installation, all 90 backend tests, native model compilation/input checks, source/model hash checks, and the no-key service startup passed. [Sanitized command results](review-checks.json). This documentation pass did not rerun a full simulator UI suite or a new clinical evaluation.

| Check | Evidence and scope |
| --- | --- |
| Care backend | 90 automated checks passed November 15 before this documentation pass: conversation continuity, natural insurance replies, credential persistence, labeled fallback, sanitization, HTTP/MCP boundaries and directory filtering. Run `npm test` to reproduce. |
| Physical care flow | Greeting, ZIP, fictional insurer, real public-directory cards and follow-up questions were observed on an iPhone 16 using sample details. The installed update kept new replies above the cards. This was a manual smoke check, not exhaustive UI automation. |
| Native audio execution | Three bundled public samples matched the Mac reader's probabilities/window counts; invalid-input controls passed. [Saved evidence](../research/results/murmur-baseline-phone.json). This checks inference on a phone, not microphone accuracy. |
| Build and install | Debug iPhone build 0.4.0 (5) built and installed during the November 15 care-flow check. Earlier simulator, Release, Watch and storage checks are recorded in [the integration history](../HeartEcho/INTEGRATION-VALIDATION.md). |

The phone care check initially failed because a Mac restart invalidated its pairing. Re-pairing restored it; the launcher now saves owner-only credentials for future starts. Review also exposed replies hidden below provider cards; the installed update scrolls to each new message. Passing API tests did not substitute for these phone checks.

## Limits

- No representative independent, clinician-labeled bare-phone cohort has established real-world sensitivity or specificity.
- Stethoscope examples, simulated phone sound and personal feasibility recordings cannot establish that evidence.
- BPM and murmur inference are independent. Watch readings do not enter microphone model inputs.
- A sound finding does not identify AFib, valve disease, severity or overall heart health. An absent result cannot rule out disease.
- Model scores are not calibrated disease probabilities. Low confidence or rejected input can return unsure.
- Listings do not establish care quality, availability, cost or insurance coverage. The exact-payer integration is narrow.

## Research outside the submitted app

[The model decision](../research/murmur-model-decision.md) reports alternative runs and rejected candidates. Some phone-style research used private, unlabeled spectral/noise statistics; those models were not adopted, and their profiles, derivatives and weights are excluded. Those experiments are not claimed as public-only submission results. M2D has separate [status and license restrictions](../research/m2d-murmur-experiment.md); its upstream implementation and checkpoints are not bundled as the app detector.

The next study needs appropriately consented phone recordings, expert reference labels, person-separated development and independent validation, with explicit missed-case, false-alarm and unsure reporting. A successful demonstration is not a substitute for that study.
