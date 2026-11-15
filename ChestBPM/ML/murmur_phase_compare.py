"""Paired group-bootstrap differences; all v2 cohorts are retrospective/development."""
import argparse
import json
import numpy as np
from murmur_data import ROOT, save


def compare(candidate, role):
    folder = ROOT / 'results' / candidate
    rows = json.loads((folder / (role + '-predictions.json')).read_text())
    groups = sorted({r['group'] for r in rows}); counts = np.zeros((len(groups), 11), dtype=int)
    for r in rows:
        positive, negative = r['target'] == 1, r['target'] == 0
        a, b = r['baseline'], r['candidate']
        counts[groups.index(r['group'])] += [positive, positive and a == 'present', positive and b == 'present',
            negative, negative and a == 'present', negative and b == 'present', a == 'unsure', b == 'unsure',
            positive and a == 'absent', positive and b == 'absent', 1]
    def deltas(a):
        return np.stack([(a[..., 2] - a[..., 1]) / np.maximum(a[..., 0], 1),
            (a[..., 5] - a[..., 4]) / np.maximum(a[..., 3], 1),
            (a[..., 7] - a[..., 6]) / np.maximum(a[..., 10], 1),
            (a[..., 9] - a[..., 8]) / np.maximum(a[..., 0], 1)], axis=-1) * 100
    rng = np.random.default_rng(4414); draws = counts[rng.integers(len(groups), size=(3000, len(groups)))].sum(1)
    observed = deltas(counts.sum(0)); intervals = np.percentile(deltas(draws), [2.5, 97.5], axis=0).T
    result = dict(candidate=candidate, role=role, linked_groups=len(groups), recordings=len(rows), bootstrap_repeats=3000,
        note='Paired linked-group bootstrap, percentile95%intervals in percentage points. Exploratory uncertainty, not clinical or fresh independent validation. Selection/model development can bias intervals. Old test is previously inspected regression.',
        differences={key: dict(percentage_points=float(value), interval95=interval.tolist()) for key, value, interval in zip(
            ['positive_detection', 'false_alarm', 'unsure', 'positive_as_absent'], observed, intervals)})
    save(folder / (role + '-paired-comparison.json'), result); print(json.dumps(result, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('candidate'); p.add_argument('role', choices=['selection', 'calibration', 'test']); a = p.parse_args(); compare(a.candidate, a.role)
