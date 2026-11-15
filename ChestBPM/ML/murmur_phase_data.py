"""Add public phase supervision without changing the frozen murmur v1 split."""
import argparse
import concurrent.futures
import csv
import hashlib
import json

import numpy as np

from murmur_data import ROOT, MANIFEST, digest, save
from prepare_data import fetch

PHASE_MANIFEST = ROOT / 'murmur-phase-manifest.json'


def reserve():
    if PHASE_MANIFEST.exists(): raise ValueError('Phase manifest exists; refusing overwrite')
    base = json.loads(MANIFEST.read_text()); checksums = {}
    for line in (ROOT / 'cache/circor/SHA256SUMS.txt').read_text().splitlines():
        h, n = line.split(maxsplit=1); checksums[n.lstrip('* ./')] = h
    # Split the original validation groups equally for checkpoint selection/calibration.
    # All prior test results are already inspected and will only be regression evidence.
    metadata = {r['Patient ID']: r for r in csv.DictReader((ROOT / 'cache/circor/training_data.csv').open())}
    group_labels = {}
    for r in base['records']:
        if r['split'] == 'validation': group_labels.setdefault(r['group'], set()).add(r['patient_target'])
    calibration = set()
    for label in [0, 1, 2]:
        groups = [g for g, labels in group_labels.items() if (1 if 1 in labels else 2 if 2 in labels else 0) == label]
        groups.sort(key=lambda g: hashlib.sha256(('murmur-phase-calibration-2414:' + g).encode()).hexdigest())
        calibration.update(groups[:len(groups) // 2])
    assert len(calibration) == 50
    records = []
    for r in base['records']:
        name = r['file'].replace('.wav', '.tsv'); row = metadata[r['patient']]
        records.append(dict(**r, annotation=name, annotation_sha256=checksums[name],
            role=r['split'] if r['split'] != 'validation' else 'calibration' if r['group'] in calibration else 'selection',
            systolic_timing=row['Systolic murmur timing'], diastolic_timing=row['Diastolic murmur timing']))
    save(PHASE_MANIFEST, dict(source_manifest_sha256=digest(MANIFEST), records=records,
        labels=['noise', 'S1', 'systole', 'S2', 'diastole'], seed=2414,
        annotation='Public semi-supervised CirCor phase labels; unannotated state0 is masked, never silently declared noise. Known synthetic pure artifacts use state0.',
        evaluation='Original120group murmur test was inspected during v1; only retrospective regression for v2. Original validation split into50selection/50calibration groups before v2 training. No private/Watch inputs.'))
    print('Reserved phase supervision and50/50selection-calibration groups; original split unchanged.')


def download():
    records = [r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['split'] != 'test']
    def get(r): fetch(r['annotation'], r['annotation_sha256'])
    with concurrent.futures.ThreadPoolExecutor(10) as pool:
        for i, _ in enumerate(pool.map(get, records)):
            if (i + 1) % 400 == 0: print('Verified phase files', i + 1, '/', len(records), flush=True)
    print('All development phase annotations verified.', flush=True)


def targets(record, frames):
    path = ROOT / 'cache/circor' / record['annotation']
    assert digest(path) == record['annotation_sha256']
    rows = np.loadtxt(path, ndmin=2)
    assert rows.shape[1] == 3 and np.all(np.isfinite(rows))
    centers = (np.arange(frames) * 40 + 128) / 2000
    labels = np.full(frames, -100, dtype=np.int64)
    for a, b, state in rows:
        # A published file has only "0 0 28". A zero-length entry labels no audio.
        if a == b: continue
        assert 0 <= state <= 4 and state == int(state) and a <= b
        if state: labels[(centers >= a) & (centers < b)] = int(state)
    return labels


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['reserve', 'download'])
    a = p.parse_args(); reserve() if a.action == 'reserve' else download()
