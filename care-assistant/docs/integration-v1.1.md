# Version 1.1 summary and conversation handoff

The server preserves v1.0 support. Version 1.1 distinguishes the rolling **analysis window** from recording/study length and optionally carries comparison counters. No raw recording or diagnostic object is accepted.

```json
{
  "schema_version": "1.1",
  "measurement": "experimental_heart_sound_timing",
  "quality": "usable",
  "estimated_bpm": 74.333333,
  "analysis_window_seconds": 8,
  "synthetic": true
}
```

The API preserves the numeric measurement; visible text rounds to a whole BPM like the native screen. Only usable summaries carry an accepted main BPM. Unclear/unavailable summaries require null and omit comparison counters. Optional `timing_counters.pattern_bpm` / `cycle_bpm` never replace a missing accepted BPM; the native adapter omits them by default.

`captured_at` must be a genuine measurement time. Unknown time stays absent and is not labeled recent. More than 30 minutes old is labeled an earlier snapshot; more than five minutes ahead is flagged. These are context labels, not clinical thresholds, and never block care search. Version 1.1 rejects ambiguous `duration_seconds`; legacy v1.0 retains it.

Send `scan` when attaching/replacing a snapshot; omit it to retain the current snapshot; send `scan: null` to clear it. Replies include `scan_state`, `scan_changed` and the current explanation. Scan changes never silently change ZIP, specialty or insurance. The UI distinguishes synthetic examples, attached summaries and no scan. Full reset clears scan/profile/chat/results and retains failed deletion IDs for retry.

`POST /api/v1/chat` also accepts specific `clear_fields`, `action: affordable`, and `action: why`. `profile.care_preference` is `all` or `affordable`; `profile.coverage_preference` is `check_if_possible` or `skip`. Unknown network clears only that field; year changes clear an incompatible old date unless a new date is supplied. New payer/plan clears dependent details. Ambiguous ZIP-like numbers prompt a question.

“Why these?” explains saved directory results without another directory request. Each card has a source-backed reason. Lower-cost mode uses HRSA sites, without ranking unknown prices. Other plan-listed practices have a visible unconfirmed-category label and are not counted as category matches.

See `scan-summary.v1.1.schema.json` and [the isolated native package](../integrations/README.md). No live native app, estimator, device, signing or capture changes were made.
