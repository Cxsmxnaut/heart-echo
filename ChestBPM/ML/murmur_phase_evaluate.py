"""Audio-only native v2 comparison against the frozen v1 model. Old test is regression."""
import argparse
import collections
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

from murmur_data import ROOT, digest, save
from prepare_data import fetch
from murmur_model import metrics
from murmur_phase_data import PHASE_MANIFEST, targets
from murmur_phase_model import OUTPUT

RESULTS = ROOT / 'results/murmur-phase-a'
FREEZE = ROOT / 'murmur-phase-a-freeze.json'


def freeze():
    if FREEZE.exists(): raise ValueError('Candidate freeze exists; refusing overwrite')
    RESULTS.mkdir(parents=True, exist_ok=True)
    files = [Path(__file__), PHASE_MANIFEST, ROOT / 'murmur_phase_data.py', ROOT / 'murmur_phase_model.py', ROOT / 'test_murmur_phase.py',
             ROOT.parent / 'Tools/MurmurPhaseProbe.swift', ROOT.parent / 'Tools/MurmurProbe.swift', ROOT.parent / 'ChestBPM/MurmurAnalysis.swift']
    files += [p for p in OUTPUT.rglob('*') if p.is_file()]
    for source, name in [(ROOT / 'results/murmur-v1/murmur-probe', 'murmur-probe'), (Path('/tmp/chestbpm-murmur-phase-probe'), 'phase-probe')]:
        target = RESULTS / name; shutil.copy2(source, target); files.append(target)
    runtime = RESULTS / 'runtime.txt'; runtime.write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)); files.append(runtime)
    save(FREEZE, dict(time=time.time(), sha256={str(p.resolve().relative_to(ROOT.parent.parent.resolve())): digest(p) for p in files},
        evaluation='Compare fixed0.60nativepipeline on selection50/calibration50; only then old120group regression. No tuning on regression outcomes. Unknown and all abstentions retained.',
        comparability='Primary: positive detection improvement, false-alarm rate increase<=2percentagepoints, unsure increase<=5points; explicitly report positive-as-Absent and unknown misclassification. Report perpatient and record, phase confusion, known noise controls. No clinical or phone accuracy claim.'))
    print('Candidate weights, protocol, metrics, source and both binaries frozen.')


def verify():
    data = json.loads(FREEZE.read_text())
    for p, h in data['sha256'].items(): assert digest(ROOT.parent.parent / p) == h, p


def evaluate(role):
    verify(); RESULTS.mkdir(parents=True, exist_ok=True)
    records = [r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role'] == role]
    for r in records:
        assert digest(ROOT / 'cache/circor' / r['file']) == r['sha256']
        if role == 'test': fetch(r['annotation'], r['annotation_sha256'])
    old_split = 'test' if role == 'test' else 'validation'
    old_requests = json.loads((ROOT / f'results/murmur-v1/{old_split}-requests.json').read_text())
    negative = [r for r in old_requests if r['id'].startswith('negative-')]; assert len(negative) == 20
    requests = [dict(id=r['record'], path=str((ROOT / 'cache/circor' / r['file']).resolve())) for r in records]
    request_path = RESULTS / (role + '-requests.json'); save(request_path, requests + negative)
    output = RESULTS / (role + '-native.ndjson'); phase_output = RESULTS / (role + '-phase.ndjson')
    for binary, destination in [('murmur-probe', output), ('phase-probe', phase_output)]:
        with destination.open('w') as f: subprocess.run([str(RESULTS / binary), str(request_path), str(OUTPUT)], stdout=f, check=True)
    predicted = {x['id']: x['reading'] for x in map(json.loads, output.open())}
    phase_predictions = {x['id']: x for x in map(json.loads, phase_output.open())}
    old = {x['record']: x for x in json.loads((ROOT / f'results/murmur-v1/{old_split}-predictions.json').read_text())}
    assert set(predicted) == set(phase_predictions) == {r['id'] for r in requests + negative}
    rows = []; phases = np.zeros((5, 5), dtype=int); names = ['absent', 'present', 'unsure']
    for r in records:
        new = predicted[r['record']]; baseline = old[r['record']]
        assert (r['target'], r['patient_target'], r['group']) == (baseline['target'], baseline['patient_target'], baseline['group'])
        q = targets(r, 194); p = np.asarray(phase_predictions[r['record']]['phases']); mask = q != -100
        phases += np.bincount(q[mask] * 5 + p[mask], minlength=25).reshape(5, 5)
        rows.append(dict(**r, baseline=baseline['finding'], candidate=new['finding'], probabilities=new['probabilities'], windows=new['windows']))
    result = dict(role=role, records=len(rows), patients=len({r['patient'] for r in rows}), groups=len({r['group'] for r in rows}),
                  evidence='Previously inspected original test: retrospective regression, not independent validation.' if role == 'test' else 'Development selection/calibration; not independent clinical validation.',
                  phase_confusion_true_rows=phases.tolist(), phase_known_accuracy=float(np.trace(phases) / max(phases.sum(), 1)),
                  phase_recall=(np.diag(phases) / np.maximum(phases.sum(axis=1), 1)).tolist())
    old_native = {r['id']: r['reading'] for r in map(json.loads, (ROOT / f'results/murmur-v1/{old_split}-native.ndjson').open())}
    result['known_negative_controls'] = dict(total=len(negative),
        baseline=dict(collections.Counter(old_native[r['id']]['finding'] for r in negative)),
        candidate=dict(collections.Counter(predicted[r['id']]['finding'] for r in negative)),
        note='Same previously tested synthetic/knownnoise files; not unseen-noise validation.')
    for name in ['baseline', 'candidate']:
        result[name] = metrics([r['target'] for r in rows], [names.index(r[name]) for r in rows])
        patient = collections.defaultdict(list)
        for r in rows: patient[r['patient']].append(r)
        result[name + '_patient'] = metrics([v[0]['patient_target'] for v in patient.values()],
            [1 if any(r[name] == 'present' for r in v) else 2 if any(r[name] == 'unsure' for r in v) else 0 for v in patient.values()])
    save(RESULTS / (role + '-predictions.json'), rows); save(RESULTS / (role + '-summary.json'), result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['freeze', 'selection', 'calibration', 'test']); a = p.parse_args()
    freeze() if a.action == 'freeze' else evaluate(a.action)
