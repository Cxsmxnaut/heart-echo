# Heart murmur model progress — November 15, 2026

There is partial improvement, but no new model has passed all three goals together. The latest V15 attention replacement is trained and verified; it adds detections and false alarms relative to its matched control. Keep the original model in Heart Echo. No app or BPM update was installed. See `m2d-attention-experiment.md` for the latest full result.

## Full comparison on the same 367 public development recordings

These include 70 confirmed murmur recordings, 274 confirmed absent recordings and 23 expert-unknown recordings. The people have been used during earlier development. These are not independent accuracy estimates or tests on labeled phone recordings.

| Native app audio | Murmurs caught / 70 | False alarms / 274 | Unsure / 367 |
|---|---:|---:|---:|
| Original app model M |49|5|121|
| Earlier trained M2D, V11 |58|15|220|
| Fixed partial refinement, V12 |55|7|114|
| Matched trained mean control, V15 |55|13|70|
| Learned attention, V15 |58|14|76|

V12 reduces false alarms and unsure results compared with V11, but loses three detections in the total. Compared with the original app model, it catches six more murmurs and returns seven fewer unsure answers, with two extra false alarms. It keeps all 49 original M detections and 6 of the 12 positive recordings V11 added over M. This is a measured tradeoff, not the requested 58 detections with at most 5 false alarms and 121 unsures.

| Same recordings with a fixed simulated phone effect | Murmurs caught / 70 | False alarms / 274 | Unsure / 367 |
|---|---:|---:|---:|
| Original app model M |49|7|70|
| Earlier trained M2D, V11 |59|14|70|
| Fixed partial refinement, V12 |50|7|69|
| Matched trained mean control, V15 |55|10|23|
| Learned attention, V15 |57|13|21|

The V12 choice was fixed from selection results before its separate 187-recording calibration check. Its original 180 selection predictions were preserved. The head, route and cutoff were not tuned from calibration errors. The primary V11-retention goal remains failed; the secondary check does not change that.

## Deeper V13 training completed

V13 trained for 12 full GPU rounds. It started from V11 and changed the final two transformer blocks and classifier. A loss protected recognized true murmur/unknown training examples while allowing correction of false alarms. All three saved snapshots passed independent source, weight, frozen-layer and finite-value checks. Five local engineering checks passed.

All 24 fixed snapshot/method combinations were compared on the 180 selection recordings, using native inputs and the exact same phone simulations. None passed every requirement. The closest diagnostic route gives:

| Selection only | Murmurs caught / 34 | False alarms / 136 | Unsure / 180 |
|---|---:|---:|---:|
| M, native |25|1|62|
| V13, native |30|2|57|
| M, simulated phone |25|2|36|
| V13, simulated phone |27|2|34|

This still adds a native false alarm and misses the 31-detection phone-simulation target. It retains 5/7 native and 2/7 styled V11 extra detections. No V13 calibration audio was scored after this failure. Cloud/local probabilities agreed within 0.00001544 and every threshold decision matched.

An unsure answer can be appropriate. The raw V13 head reduced native selection unsures to 10, but confidently classified 8 of 10 expert-unknown recordings and called 4 positive recordings absent. M kept 9/10 unknown recordings unsure and called 3 positives absent. That lower unsure count did not pass the quality checks.

## Evidence and preserved results

- V12 full partial comparison and its pre-audio freeze: `generated/murmur-v12-targeted/partial-evaluation/`.
- V13 independently verified trained checkpoints: `generated/murmur-v13-preserving/source-stage/`.
- V13 selection, frozen choice and paired gains/losses: `generated/murmur-v13-preserving/selection/`.
- Protocols: `murmur-v12-plan.md`, `murmur-v13-plan.md`, `murmur-partial-check-plan.md`.

Personal recordings and the private phone profile stayed local. Today's 8:23 case-on recording remains excluded. No private recording was assigned a clinical diagnosis. Training used public clinical labels; generic public-only phone augmentation went to the GPU. All trained and original weights remain preserved. M2D's non-commercial evaluation license still limits app distribution. Physical-phone inference, a new independent clinical cohort and real-phone accuracy have not been verified. No Graphify graph or managed refresh command is configured in this repository.
