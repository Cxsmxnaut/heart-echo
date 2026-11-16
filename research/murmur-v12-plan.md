# V12: preserve M2D detections while reducing false alarms and abstentions

The user explicitly authorized further targeted training after V11. The goal is to retain the new murmur detections while reducing false alarms and unsure outputs. V11's decision to retain the shipping model is a deployment decision; the trained M2D weights remain useful research candidates. No new app model is installed.

## Evidence before new training

V11 completed two 50-round GPU runs. Both were independently verified, including changes in all twelve transformer blocks and identical frozen pretrained tensors. The released-code arm was chosen using selection only, before local calibration evaluation. Its selected checkpoint is epoch 11, SHA256 `e89b4a8bff063b3fed7702666f691e606737c297f14a156dae25da3624097b4e`.

On the 180 selection recordings at the app's native 2 kHz input, M detected 25/34 positives, with 1/136 false alarms and 62 unsure results. M2D detected 30/34, with 2/136 false alarms and 123 unsure results. M2D recovered seven detections and lost two. Sixty-eight recordings without murmurs moved from M's absent result to M2D's unsure result. These selection-only disagreements are saved in `generated/murmur-v11-m2d/selection-disagreement-audit.json`.

V11 used original public 4 kHz audio resampled to 16 kHz for training; the app first converts to 2 kHz. The native reader and SciPy resampling have identical lengths on all 180 selection files, but differ numerically: median waveform correlation 0.9977, median relative RMS difference 7.15%. This supports using the exact cached AVAudioConverter output, rather than assuming two conversion methods are identical. It does not establish the sole cause of the classification errors.

## Targeted experiment

1. Preserve the V11 encoder and all original app weights. Use the existing exact native float32 public-audio cache. Only the original 2,356 training recordings and 180 selection recordings may enter a cloud bundle. Calibration/test records and all personal audio/profiles are forbidden.
2. Extract frozen 3,840-value M2D embeddings for native public training audio, including bounded generic phone perturbations. Generic perturbations must use no private recording or derived profile. Keep all encoder weights and buffers identical to V11.
3. Refit the final normalization/classifier layers on training people only. Use ordinary cross entropy on logits, additional pressure on hard absent examples, and four declared positive-error costs (2, 4, 8, 12) with unknown cost 4. Keep the confidence cutoff at 0.60. Train at most sixteen rounds per head, retaining rounds 4, 8 and 16; include a training-statistics-only normalization control.
4. Compare all candidate heads on selection audio only, using both exact native inputs and the already-frozen V10 phone simulations. Four declared routes are head alone; use M when the head is unsure; additionally preserve M's positive calls; or preserve M except when a new Present result has probability at least 0.90. The 0.90 override is fixed before inspecting any V12 head results. These controls do not relabel unsure recordings without model evidence.
5. Select before scoring calibration. Prefer candidates retaining at least V11's selection detections (30 native, 31 styled), with false alarms no greater than M (1 native, 2 styled), unsure outputs no greater than M (62 native, 36 styled), and no regression in correct absent results, positive-as-absent errors, or expert-unknown retention. Report infeasibility honestly; never relax these conditions after seeing calibration. If none passes, preserve the measured tradeoff and investigate representation training separately.

A classifier is allowed to return unsure. Reducing that count must come from correct predictions of labeled public examples. No private recording is assigned a normal/murmur diagnosis. No result is forced to absent just to improve the count.

## Completed V12 result

The private GPU run completed. It fitted four cost settings for sixteen rounds each on35,909 native/generic public windows, retaining twelve trained checkpoints plus a normalization-only control. All encoder fingerprints independently matched V11, all saved tensors were finite, and six engineering/routing tests passed. All52 fixed head/route combinations were scored on selection only, with maximum cloud/local probability difference0.0000403.

None retained V11's30 native/31 styled detections while meeting every other constraint. The closest frozen candidate was `positive_cost_12_epoch_16__conservative_override`: native selection29/34 detections,1/136 false alarms and59/180 unsure, versus M's25/1/62; styled26/34,2/136 and35/180, versus M's25/2/36. Its only failed conditions were retaining all V11 detections. This is measured partial improvement over M on selection, not a completed full-cohort or phone validation. Calibration was not scored for V12. All weights/results remain intact.

The user requested continued work. `murmur-v13-plan.md` specifies a deeper refinement with a one-sided preservation penalty, declared before V13 training.

## Separate frozen partial-candidate check

While V13 was still training, `murmur-partial-check-plan.md` declared a secondary check of this existing V12 choice before any V12 calibration audio was read. This did not relax the primary acceptance conditions or choose another route. The original180 selection predictions were preserved; only the187 calibration recordings were newly scored.

On all367 reused development recordings, native detections improved49→55/70 and unsures121→114, but false alarms increased5→7/274. The candidate retained all49 detections from M and6 of the12 additional positive recordings that V11 detected over M. On the fixed phone simulations it improved49→50 detections, kept7 false alarms, and reduced70→69 unsures; only1 of V11's11 extra detections was retained. Every original M recording/person/unknown condition passed in the styled case. Native calibration and combined results failed both the recording and person false-alarm conditions. This is a partial tradeoff, not an overall accepted replacement or the primary58/59-detection goal.

Artifacts and the pre-audio fingerprint freeze are in `generated/murmur-v12-targeted/partial-evaluation/`. No route was tuned from these calibration outcomes. The app and original weights remain unchanged.

## Evidence limits

The selection and calibration people have already been used in earlier development. They are reused development evidence, even if the new candidate is chosen before its calibration pass. Training, selection and calibration remain separated by linked person. Do not describe the result as independent validation or proven phone accuracy. Do not tune against individual calibration errors.

M2D's NTT license permits this internal non-commercial evaluation; app distribution remains outside this experiment. No Graphify graph or managed refresh command is configured. Current source and fingerprinted artifacts supply the evidence.

References: [original M2D method](https://arxiv.org/abs/2404.17107), [confidence calibration background](https://arxiv.org/abs/1706.04599). Calibration literature motivates checking confidence separately; it does not guarantee that a threshold adjustment can improve every outcome.
