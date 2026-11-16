# V14 diagnostic: fixed probability mixtures during V13 GPU training

The user requested retaining M2D's extra detections while reducing false alarms and unsure outputs. V12 proved partial selection improvement but failed to retain all detections. V13 is training with a preservation penalty. While it runs, this inexpensive diagnostic tests whether M's precision and M2D's sensitivity can be combined before changing more parameters.

Before computing mixture outcomes, declare one global expert weight from0.25/0.50/0.60/0.75, identical for native and styled inputs and for every person. The other weight goes to the unchanged M probabilities. Experts are the two frozen V11 arms and the thirteen V12 head/control snapshots, fifteen total. This yields sixty declared mixtures. Apply the unchanged0.60 three-class decision rule; do not force an unsure result to absent.

Fit/select using the180 selection recordings only. The primary constraints are unchanged: at least30 native/31 styled positive detections, no regressions in M's recording/person false alarms, total unsure, negative clearance, positive-as-absent or expert-unknown retention. Rank eligible candidates by total positive detections, then fewer false alarms, then fewer unsures, with a deterministic final tie. Preserve all rejected outcomes.

Freeze the best mixture and its source hashes before computing any new calibration mixture. Do not choose between this mixture and V13 using calibration results. Wait for V13's frozen selection comparison, then choose the overall main candidate by the same selection constraints/ranking before scoring calibration. If neither is eligible, report the partial frontier honestly. These are reused development people, not an independent phone benchmark.
