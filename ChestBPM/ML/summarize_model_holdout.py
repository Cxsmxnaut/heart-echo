"""Aggregate a completed locked test without changing predictions or thresholds."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

import numpy as np

from model_holdout import verify


def mean(values):
    return statistics.mean(values) if values else None


def summarize(folder):
    protocol = verify(folder)
    paths = [folder / name for name in ['freeze.json', 'references.json', 'scores-v17.json',
                                       'scores-candidate.json', 'bpm-comparisons.json', 'bpm-summary.json']]
    rows = json.loads((folder / 'bpm-comparisons.json').read_text())
    events = {}
    for tag in ['v17', 'candidate']:
        reports = json.loads((folder / f'scores-{tag}.json').read_text())['reports']
        events[tag] = result = []
        for condition in protocol['conditions']:
            for mode in ['raw', 'episodes']:
                for tolerance in [.05, .1]:
                    selected = [r for r in reports if (r['condition'], r['mode'], r['tolerance']) ==
                                (condition, mode, tolerance)]
                    assert len(selected) == 24
                    known = sum(r['known_seconds'] for r in selected)
                    item = dict(condition=condition, mode=mode, tolerance=tolerance, known_seconds=known)
                    for kind in ['S1', 'S2']:
                        counts = {k: sum(r[kind][k] for r in selected) for k in
                                  ['tp', 'fp', 'fn', 'reference_intervals', 'matched_intervals']}
                        tp, fp, fn = [counts[k] for k in ['tp', 'fp', 'fn']]
                        item[kind] = dict(**counts, precision=tp / (tp + fp) if tp + fp else None,
                            recall=tp / (tp + fn) if tp + fn else None,
                            f1=2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
                            interval_mae_ms=mean([e for r in selected for e in r[kind]['consecutive_interval_errors_ms']]),
                            timing_mae_ms=mean([e for r in selected for e in r[kind]['timing_errors_ms']]),
                            false_events_per_minute=fp * 60 / known if known else None)
                    result.append(item)
    bpm = []
    for definition in ['median8', 'latest4']:
        for condition in protocol['conditions']:
            selected = [r for r in rows if r['definition'] == definition and r['condition'] == condition]
            eligible = [r for r in selected if r['in_range']]
            item = dict(condition=condition, definition=definition, updates=len(selected), eligible=len(eligible))
            for tag in ['v17', 'candidate']:
                errors = [abs(r[tag] - r['reference']) for r in eligible if r[tag] is not None]
                item[tag] = dict(returned=len(errors), mae=mean(errors), over5=sum(e > 5 for e in errors),
                    within5coverage=sum(e <= 5 for e in errors) / len(eligible) if eligible else None,
                    noise_only_returns=sum(r[tag] is not None for r in selected if condition == 'noise_only'))
            bpm.append(item)
    # Exploratory uncertainty: resample patients, keeping all their conditions and updates together.
    # This is not an extra independent test or a model-selection rule.
    eligible = [r for r in rows if r['definition'] == 'latest4' and r['in_range']]
    groups = sorted({r['group'] for r in rows})
    totals = np.array([[sum(r['group'] == g for r in eligible)] +
        [sum(r['group'] == g and r[tag] is not None and abs(r[tag] - r['reference']) <= 5 for r in eligible)
         for tag in ['v17', 'candidate']] for g in groups])
    rng = np.random.default_rng(58142026)
    samples = totals[rng.integers(len(groups), size=(8000, len(groups)))].sum(axis=1)
    usable = samples[:, 0] > 0
    differences = (samples[usable, 2] - samples[usable, 1]) / samples[usable, 0]
    result = dict(events=events, bpm=bpm,
        exploratory_patient_bootstrap=dict(seed=58142026, samples=8000, groups=len(groups),
            latest4_within5coverage_delta_ci95=np.quantile(differences, [.025, .975]).tolist()),
        note='Repeated updates and synthetic conditions are dependent. Annotation gaps remain unknown; synthetic irregularity is not diagnosed AFib.',
        sha256={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + [Path(__file__)]})
    (folder / 'aggregate.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result['exploratory_patient_bootstrap']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    summarize(parser.parse_args().folder.resolve())
