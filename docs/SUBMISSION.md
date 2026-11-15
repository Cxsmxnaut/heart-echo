# Veritas submission checklist

[Write-up](../README.md) · [Walkthrough](JUDGE_GUIDE.md) · [Results](RESULTS.md) · [Credits](../CREDITS.md)

This maps the repository to the [official requirements](https://highschoolhackathon.org/briefs) and [rubric](https://highschoolhackathon.org/judges). It does not claim organizer approval or prove that the form has been submitted.

## Submission fields

| Field | Material |
| --- | --- |
| Project / track | Heart Echo / AI + Health |
| Code | https://github.com/Cxsmxnaut/heart-echo |
| Write-up | The README; the rules accept a GitHub README. |
| Credits | [CREDITS.md](../CREDITS.md) and its detailed source records. |
| Team | Enter each contributor's correct name, email and school in the form. Personal team details are not repeated here. |
| Video | Optional. This package supplies a written walkthrough and runnable app; no demo video is included. |

Published deadline: **November 15, 2026, 11:59 PM Eastern / 8:59 PM Pacific**. Replacement submissions are allowed before the deadline; the latest version is judged. Check the actual form for submission status.

## Rule disclosures

- **Timing/reuse:** on November 15, the team confirmed that both Chest BPM and Heart Echo were created during the event. This is a contributor statement, not independent organizer verification. Reuse of Chest BPM is disclosed and preserved in `PORTING.json`; a new commit date alone does not establish creation time.
- **Central AI task:** trained phone models analyze audio. Gemini handles care conversation, not the sound finding.
- **Data:** the shipped models and bundled examples use public data. Review instructions use public audio and fictional care details. Research involving private-derived statistics is identified separately and was not adopted into the shipped model.
- **Results:** the evidence page separates false alarms, confident misses, uncertainty, reused development data, retrospective regression and unvalidated phone accuracy.
- **Attribution:** datasets, research models, software, design guidance and AI assistance are credited. Third-party work is not claimed as unaided original work.
- **Required statement:** the README states “This project is a prototype and is not medical advice.”

## Evidence by judging criterion

| Criterion | Review material |
| --- | --- |
| Technical execution — 30 | [Run routes/source map](JUDGE_GUIDE.md), automated checks and real device observations. |
| Originality — 20 | Integration of phase-aware audio analysis, explicit uncertainty, result-first UI and care navigation; [contribution disclosure](../CREDITS.md#project-contribution-and-ai-assistance). |
| Impact/track fit — 20 | Recording-to-care journey in the README; access is a design goal, not a measured health outcome. |
| Testing/honesty — 15 | [Baseline comparisons, failures and limits](RESULTS.md). |
| Communication — 15 | README overview, walkthrough and linked evidence. |

## Before submitting

- Open code/write-up links signed out and confirm they work without requesting access.
- Confirm every listed teammate contributed and that the form details are correct.
- Match any later model/app update to its actual evidence; do not substitute pending research scores.
- Use the intended commit link if submitting a frozen snapshot.
- Keep credentials, personal captures and downloaded datasets excluded. The local Gemini key is not a judge credential.
- Retain the organizer's confirmation. This repository does not submit the form itself.
