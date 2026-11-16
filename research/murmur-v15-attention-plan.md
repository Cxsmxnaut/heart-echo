# V15: replace M2D time averaging with learned attention

The user explicitly requested this implementation and training experiment. The goal is to replace the last time average inside each five-second M2D window with learned, content-dependent attention weights. Earlier source files and checkpoints stay unchanged so their fingerprints and results remain reproducible. New inference uses `M2DAttentionMurmur` in `m2d_attention.py`.

## Fixed experiment before training

- Start from the selected V11 released checkpoint, SHA256 `e89b4a8bff063b3fed7702666f691e606737c297f14a156dae25da3624097b4e`. Keep the complete encoder, frontend and original normalization statistics fixed.
- Replace the window's feature mean with a normalized attention-weighted sum. Scores use non-affine LayerNorm, Linear(3840,64), tanh, Linear(64,1), and a softmax over time. Zero-initialize the final score weights so initial predictions match the original mean-pooling function.
- Train two matched arms: the original mean pool plus a trainable classifier; and attention pooling plus a trainable classifier. Both start with the same classifier and normalization. Their only architectural difference is the new pooling layer. Retain rounds 4, 8 and 12 from each arm, for six candidates total.
- Reuse the verified public native bundle: 2,356 training recordings and 180 selection recordings, separated by linked person. Use the exact native 2 kHz inputs, existing five-second/2.5-second-stride training crops, quality gates and deterministic generic phone augmentation from V12. No private recording/profile, calibration or test audio enters the cloud job.
- Cache the frozen encoder's full time-frame features on cloud temporary disk. Training cache uses float16 storage and is converted to float32 before training. Selection features and inference use float32. Derive frame counts from actual encoder output rather than assuming a count. No feature cache enters the returned artifact archive.
- Train both heads for 12 complete rounds, batch 128, in the same batch order. AdamW classifier learning rate 1e-4 in both arms; attention learning rate 3e-4; weight decay 0.01. Use one warmup round and cosine decay to 0.05 of base rates, float32 training and gradient clipping at 1.0.
- Use the same V13 raw-logit loss in both arms: class costs 1/6/8, 3x hard false-positive weight on true absent examples above 0.60 Present probability, and a coefficient-2 one-sided floor protecting the frozen teacher's recognized true Present/Unknown examples. The floor never preserves teacher false positives on known absent examples.
- Keep the 0.60 decision cutoff and the existing recording-window mean-logit aggregation fixed. Only the within-window time pooling changes. No ensembles, threshold search or routing rules are added in this experiment.

## Selection and comparison

Verify returned source hashes, all saved tensors, classifier/attention changes, unchanged encoder/normalization, and genuinely nonuniform learned weights. Compare all six heads locally on the 180 selection recordings using exact native audio and the existing frozen V10 phone simulations. Require native cloud/local probability difference below 0.001 and identical decisions/window counts.

Choose one checkpoint per arm before reading any V15 calibration audio. Maximize the lower of native/styled three-class balanced recall; then their mean; then prefer fewer false alarms; then the earlier round. Fingerprint both choices, all decision code, inputs and reference predictions. This is a predeclared two-arm comparison: score both fixed choices on the 187 calibration recordings even if neither qualifies as an app replacement. Preserve the original selection predictions and report selection, calibration and combined results separately. These are reused development people, not independent validation.

Report detected murmurs, murmurs incorrectly called absent, false alarms, correct absent results, unsure counts and expert-unknown retention at both recording and linked-person level. Show the matched attention-minus-mean changes as well as original M and frozen V11 reference results. Check the existing strict M conditions and the desired V11 detection counts; a failed check remains a failure. No checkpoint/rule may be changed from calibration results.

## Completion evidence

The goal requires a working full attention inference path, initial mean-equivalence, real learned attention after public-data training, independently verified reloadable weights, a completed matched comparison and reproducible commands. A benefit is an empirical question, not a completion guarantee. The original Heart Echo/BPM models remain unchanged during this research experiment. Keep private profiles/recordings local, keep all results, and make no real-phone accuracy claim. No Graphify graph or configured knowledge runtime/refresh command was found; this work uses current source and fingerprinted artifacts.

Method background: [Rohr et al., multiple-instance learning for murmur detection](https://journals.plos.org/digitalhealth/article?id=10.1371/journal.pdig.0000461). This supports studying where recording-level evidence occurs; it does not establish that this specific attention replacement will improve our models.

## Completed result

Both arms completed all 12 rounds and 3,372 optimizer steps on 35,909 windows with 32 time positions each. All six checkpoints passed local source/state verification. Selection chose mean round 8 and attention round 4 before calibration. Native cloud/local maximum probability difference was 0.00002182, with identical decisions/window counts. The saved full attention model passed 12 real-public-example reload checks and a command-line inference check.

On all 367 reused development recordings, attention versus the matched mean control gives native 58 versus 55 detections, 14 versus 13 false alarms and 76 versus 70 unsure results. Styled results are 57 versus 55 detections, 13 versus 10 false alarms and 21 versus 23 unsure results. The layer genuinely learned nonuniform weights, but this run does not provide an overall accepted app replacement. The implementation/training objective is complete; the broader reliability goal remains unmet. See `m2d-attention-experiment.md` for the full comparison, limitations, preserved artifacts and reproduction commands.
