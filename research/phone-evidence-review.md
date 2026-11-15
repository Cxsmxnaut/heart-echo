# Independent phone evidence review — 2026-11-15

**Result: no suitable fresh public phone validation cohort was verified in the sources checked below.** This is a bounded search result, not proof that no such dataset exists. More training can improve the model, but cannot turn reused recordings into an independent accuracy test.

## Sources checked

| Source | What the primary source establishes | Use for this goal |
|---|---|---|
| [PASCAL challenge](https://k4all.org/project/classifying-heart-sounds-challenge/) | Set A contains iPhone recordings with challenge categories; public labeled archives have 34 murmur, 31 normal, 40 artifact and 19 extra-heart-sound recordings. | Already evaluated locally. Keep as regression evidence. Patient identities and a clinical reference standard are not verified. |
| [Echoes study](https://academic.oup.com/ehjdh/article/3/3/473/6675713) | The study assessed whether heart sounds could be recorded clearly. Its limitations say recognition of pathological sounds, including murmurs, needs a future patient study. | Does not supply a verified murmur-labeled phone cohort for this task. Recording quality and murmur detection are different outcomes. |
| [Stethophone feasibility study, 2026](https://sciencepg.com/article/10.11648/j.sjph.20261401.16) | Uses proprietary training data. Its population study assessed feasibility; algorithm outputs were not adjudicated by clinicians in that study. | No verified downloadable reference-labeled audio cohort for our model. Another system's outputs cannot serve as expert truth. |
| [Stethophone clinical paper on Zenodo](https://zenodo.org/records/18093086) | Repository lists one file, `JAMES.pdf`, describing results for another system. | A paper is available; participant audio and labels are not listed. Do not mistake this deposit for an audio dataset. |
| [AUSC1 conference abstract, 2026](https://www.jacc.org/doi/10.1016/j.jacc.2026.02.3004) and [trial record](https://clinicaltrials.gov/study/NCT06070298) | Study used built-in phone microphones and a clinical comparison. The registry's official API reports `ipdSharing: NO`, last updated April 24, 2025. | Relevant evidence that phone use needs its own evaluation, but no usable public cohort verified. No participant records or author contact requested. |
| [Fraiwan regurgitation dataset](https://data.mendeley.com/datasets/jfbdvjw6sf/1) | Public CC BY 4.0 recordings use a Littmann 3200 electronic stethoscope in a quiet clinic. | Potential future research source. Does not validate our built-in phone microphone. Valve disease labels must not be silently converted into audible-murmur labels. |
| [ZCHSound repository](https://github.com/WeiJieOvO/ZCHSound-Dataset) and [cross-dataset study](https://cinc.org/archives/2024/pdf/CinC2024-023.pdf) | Pediatric heart recordings; the comparison study lists normal and congenital-condition categories. | No direct phone-microphone murmur cohort verified. Disease categories cannot substitute for recording-level murmur truth. |
| [MYSTETH study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12519439/) | Its data statement points to the existing Kaggle heartbeat-sounds collection, derived from PASCAL. | Does not establish a new independent phone source. New processing or synthetic augmentation does not create new independent people. |

The official AUSC1 registry JSON was retrieved directly from `https://clinicaltrials.gov/api/v2/studies/NCT06070298`. Its SHA-256 is `851f3ab68aa5daa4fef43356dbeb09cf5bccf9970b16b5f9658acc37a4ecbc33`. The cached public registry metadata is excluded from source control under `cache/phone-evidence/`. Registry sharing plans can change; recheck before relying on future availability.

## What would close the gap

We need authorized access to previously untouched audio from independent people, captured using the intended phone microphones and recording flow. It must include clinically appropriate murmur reference labels, expert-unknown cases, recording-quality assessments, device information, and enough population detail to examine important subgroups. Keep every person's sites and repeat visits together. Audit overlap with all prior training and evaluation sources before accepting independence.

Freeze the model, threshold, native reader, eligibility rules and analysis before reading test outcomes. Count every attempted recording, technical failure and unsure result. Report detection, false alarms, positive-as-absent errors, coverage and uncertainty separately, with person-level confidence intervals and subgroup results. Appropriate clinical and statistical review must determine study size and acceptance criteria; the project's aspirational percentages are not a clinical standard.

**Current limit:** the preserved baseline already falls short of the project ambitions on reused development data. New evidence alone will not fix those errors. Stronger model performance and independent phone validation are both still needed. No new audio was used to train or tune models during this review.
