# Scan-summary handoff v1.0

The server also supports [v1.1 and conversational corrections](integration-v1.1.md), with an [isolated tested Swift/SwiftUI preview](../integrations/README.md). Below is the preserved legacy v1.0 shape.

The native app can add a care-navigation step later without changing recording or BPM estimation. The care service accepts only a small summary. It does not accept recordings, waveforms, diagnostic labels, private logs, user names, member IDs or credentials.

```json
{
  "schema_version": "1.0",
  "measurement": "experimental_heart_sound_timing",
  "quality": "usable",
  "estimated_bpm": 74,
  "duration_seconds": 20,
  "synthetic": true
}
```

Required fields: `schema_version`, `measurement`, `quality`, `estimated_bpm`, `synthetic`. Optional: `duration_seconds`, `captured_at` (ISO UTC datetime). Real future measurements must send `synthetic: false`; examples/tests use `true`. `quality` is `usable`, `unclear` or `unavailable`. Only usable summaries carry a finite BPM value (20–300); other qualities require JSON `null`. These are input bounds, not “normal heart rate” thresholds. All unknown fields and diagnostic claims are rejected with HTTP 400.

The machine-readable contract is `scan-summary.v1.schema.json`. Its conditional BPM rule matches the backend's cross-field validation. Changes to required meaning or shape require a new schema version.

1. POST the summary to `/api/v1/chat` with `action: "explain"`, or POST to `/api/v1/scan-summary` just for validation/explanation.
2. Save the returned `session_id` only for the active flow. Send later messages and structured `profile` values to `/api/v1/chat` using that ID. Do not provide client-controlled system/assistant roles.
3. For care search, send `action: "search"`, a five-digit `profile.zip`, and `profile.insurance.status` (`insured`, `unknown`, or `uninsured`). Exact-plan lookup needs `payer`, `plan` and `network`. Optional public `plan_id` identifies the plan, not a member. Optional `coverage_year` and `coverage_date` select when the directory evidence must apply. A new payer/plan clears stale plan/network/ID details.
4. Render `scan_explanation`, `message`, `stage`, model configuration/fallback status, and source-backed result cards. Never treat `directory_linked` as member eligibility or guaranteed benefits/cost. Never synthesize providers from a model answer. Show evidence links, retrieval time, effective date/period, practice address and network basis.
5. On HTTP 410, start a new chat; the previous session expired. On 400, display field validation. On 409, wait for the earlier request. On 429, wait one minute. Upstream source failures are represented per result and preserve other available results.

Run the synthetic example with `node examples/integrate.js`. Use `CARE_API_TOKEN` server-side for future native requests; do not embed a shared production secret in a shipped client. This local demo binds only to the Mac's loopback interface and is not reachable from a phone. Hosting, production authentication, health-data governance and native networking need their own implementation and approval. No native app files were changed in this work.
