# V13: native adaptation with a penalty for forgetting confirmed detections

V12 completed and was independently verified. All runtime/encoder tensors stayed identical to V11; twelve trained classifier checkpoints and a normalization-only control were compared using selection people only. Cloud/local probabilities agreed within0.000041. No candidate met every fixed constraint, so V12 calibration was not scored. The closest conservative route improved native selection from25 to29 detections, kept1 false alarm and reduced unsures62→59. Styled selection improved25→26, kept2 false alarms and reduced unsures36→35. This is useful partial progress, not preservation of all V11 gains.

The V12 linear heads mostly lost styled detections. V13 therefore tests representation adaptation with explicit protection for prior confirmed detections, instead of repeatedly changing the same classifier costs. This stage is authorized by the user's request to build the best supported model and retain the gains while reducing false alarms/abstentions.

## Fixed experiment before new training

- Initialize exactly from V11's selected released-code checkpoint, SHA256 `e89b4a8bff063b3fed7702666f691e606737c297f14a156dae25da3624097b4e`.
- Keep the first ten transformer blocks, patch/positional embeddings, frontend, normalization buffers and other unlisted parameters fixed. Train only transformer blocks10/11 and the final classifier. Keep evaluation-mode normalization/dropout behavior during fitting so the initial predictor equals V11.
- Reuse the verified public native bundle:2,356 training and180 selection recordings. No calibration/test record, personal recording or private phone profile goes to the GPU. Generic EQ/gain/synthesized-noise augmentation is unchanged from V12.
- Cache five-second training spectra at2.5-second stride outside the cloud output folder. Cache the original frozen model's training-window probabilities once. Use only valid RMS/clipping/finite-input windows.
- Train twelve full rounds, batch32. AdamW learning rates1e-5 for the final two blocks and3e-5 for the classifier, weight decay0.0001, one-round warmup and cosine decay. CUDA AMP and gradient-norm clipping1.0. Record batch attempts rather than claiming independently verified optimizer updates.
- Ordinary cross entropy uses absent/present/expert-unknown costs1/6/8. A currently false Present probability above0.60 on a true absent example gets3x additional loss weight. A one-sided penalty protects the original model's probability of the true label for confirmed positive or expert-unknown examples it recognized with at least0.60 probability. This penalty is zero when the new probability improves. It never preserves a false positive on a known absent example. The coefficient is2.
- Retain exactly rounds4,8 and12; no checkpoint/threshold choice based on calibration. Evaluate those three models locally on selection native inputs and the existing frozen phone simulations, with the same four fixed routing rules and the same V12 detection/false-alarm/unsure/person/unknown constraints. Choose before any V13 calibration evaluation. Preserve failed results and report infeasibility honestly.

While the run was in its early training rounds, before inspecting any V13 checkpoint prediction outcomes, the V14 diagnostic tested the original two V11 and thirteen V12 experts at four fixed probability weights. None met every constraint. The same four global mixture weights0.25/0.50/0.60/0.75 are now declared as additional inference methods for each V13 checkpoint. They apply identically to every person and both input conditions. This yields24 checkpoint/method combinations total. The primary acceptance conditions stay unchanged; no calibration mixture is used to choose a method. `compare_m2d_preserving.py` freezes this comparison and all imported decision code before calibration.

Both the old M and V11 M2D models remain intact. The partial V12 candidate remains intact. No failed checkpoint is installed in the app. All development data are reused, so passing these checks would still require independent clinical phone validation and deployment rights before app use.

## Training verification

The private GPU job completed all 12 rounds and 13,476 batch attempts. The downloaded archive SHA256 is `b5db5f9f4fccfb407b7925c458a221724c941ae18787b1acc9a4d61998ed5754`. Independent local verification matched all five uploaded training source files, the public-only bundle, and the exact V11 initializer. All three retained checkpoints are finite; each changed 26 parameter tensors in blocks 10/11 and the classifier, while all other state tensors, including the first ten blocks and normalization, stayed exact. Five local training/routing checks passed, including a real-network gradient/update test. Local selection comparison followed verification; training completion alone is not an accuracy claim.

## Completed selection comparison

All24 fixed checkpoint/method combinations were compared on the180 selection recordings in both conditions. None met every condition. Cloud/local probabilities agreed within0.00001544 and every threshold decision matched.

The closest diagnostic candidate is `epoch12__conservative_override`. On native inputs it detects30/34 positives, raises2/136 false alarms and returns57/180 unsure, versus M25/1/62. It keeps all25 M detections and5 of V11's7 extra detections, while losing2 V11 extras. On the fixed phone simulations it detects27/34, raises2/136 false alarms and returns34/180 unsure, versus M25/2/36; it retains2 of V11's7 extra detections. It fails both native false-alarm checks and the styled31-detection target. This diagnostic choice is frozen; no V13 calibration audio was scored.

The raw epoch12 head illustrates why reducing unsure alone is insufficient: native unsures fall to10, but only2/10 expert-unknown recordings remain unsure, versus9/10 for M, and4 positive recordings are called absent, versus3 for M. The conservative route avoids those particular regressions but still does not satisfy the full goal.

The complete trained snapshots and verification remain in `generated/murmur-v13-preserving/source-stage/`. The24-way selection report, frozen choice and paired detection audit remain in `selection/`. See `murmur-model-progress.md` for the shorter cross-stage result. The separate fixed V12 partial check is reported in `murmur-partial-check-plan.md`; it does not change this primary failure. No app update or new GPU arm followed from these reused calibration outcomes.
