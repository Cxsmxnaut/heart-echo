"""Freeze then test the native murmur model on all reserved patient recordings."""
import argparse
import collections
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

from murmur_data import ROOT, MANIFEST, digest, save, download
from murmur_model import OUTPUT, metrics

RESULTS = ROOT / 'results/murmur-v1'


def negative_cases(split):
    rng = np.random.default_rng(3114 if split == 'validation' else 4114)
    folder = ROOT / 'cache/murmur-negative' / split; folder.mkdir(parents=True, exist_ok=True)
    result = []
    for i in range(20):
        t = np.arange(40000) / 2000; x = rng.normal(0, .03, len(t))
        if i < 4: x *= 0
        elif i < 8: x = .04 * np.sin(2 * np.pi * (50 if i % 2 else 60) * t)
        elif i < 12:
            envelope = np.zeros(len(t))
            for at in rng.uniform(0, 19, 25):
                a = int(at * 2000); envelope[a:a + 120] += np.hanning(120)
            x *= envelope
        elif i >= 16:
            name = 'speech' if i % 2 else 'babble'
            noise, rate = sf.read(ROOT / 'cache/noise' / (name + '.wav'))
            from scipy.signal import resample_poly
            noise = noise[:, 0] if noise.ndim > 1 else noise
            x = np.resize(resample_poly(noise, 2000, rate), len(t)) * .15
        path = folder / f'{i:02d}.wav'; sf.write(path, x, 2000, subtype='PCM_16')
        result.append(dict(id=f'negative-{i:02d}', path=str(path.resolve())))
    return result


def evaluate(split):
    RESULTS.mkdir(parents=True, exist_ok=True)
    if split == 'test': download('test')
    records = [r for r in json.loads(MANIFEST.read_text())['records'] if r['split'] == split]
    requests = [dict(id=r['record'], path=str((ROOT / 'cache/circor' / r['file']).resolve())) for r in records]
    negative = negative_cases(split)
    request_path = RESULTS / (split + '-requests.json'); save(request_path, requests + negative)
    native = RESULTS / (split + '-native.ndjson')
    binary = str(RESULTS / 'murmur-probe') if split == 'test' else '/tmp/chestbpm-murmur-probe'
    with native.open('w') as f: subprocess.run([binary, str(request_path), str(OUTPUT)], stdout=f, check=True)
    outputs = {r['id']: r for r in map(json.loads, native.open())}
    assert set(outputs) == {r['id'] for r in requests + negative}
    rows = [dict(**r, **outputs[r['record']]['reading'], milliseconds=outputs[r['record']]['milliseconds']) for r in records]
    names = ['absent', 'present', 'unsure']; truth = [r['target'] for r in rows]; pred = [names.index(r['finding']) for r in rows]
    patients = collections.defaultdict(list)
    for r in rows: patients[r['patient']].append(r)
    pt, pp = [], []
    for values in patients.values():
        pt.append(values[0]['patient_target']); decisions = {x['finding'] for x in values}
        pp.append(1 if 'present' in decisions else 2 if 'unsure' in decisions else 0)
    summary = dict(split=split, recordings=len(rows), patients=len(patients), linked_groups=len({r['group'] for r in rows}),
        record=metrics(truth, pred), patient=metrics(pt, pp),
        majority_absent_record_baseline=metrics(truth, [0] * len(truth)),
        majority_absent_patient_baseline=metrics(pt, [0] * len(pt)),
        negative_controls=dict(total=len(negative), decisions=dict(collections.Counter(outputs[r['id']]['reading']['finding'] for r in negative)),
            note='Synthetic silence,hum,white,contact and known speech/babble sources; not unseen real-world noise.'),
        median_processing_ms=float(np.median([r['milliseconds'] for r in rows])),
        note='Native Core ML including real4kHzfile conversion, gates and fixed0.60decision. Patient aggregation: any present, else any unsure, else absent. Linked patients are split together. Same-dataset stethoscope evaluation, not phone or clinical validation.')
    save(RESULTS / (split + '-predictions.json'), rows); save(RESULTS / (split + '-summary.json'), summary)
    print(json.dumps(summary, indent=2), flush=True)


def freeze():
    path = ROOT / 'murmur-freeze.json'
    if path.exists(): raise ValueError('Final murmur freeze exists; refusing overwrite')
    for r in json.loads(MANIFEST.read_text())['records']:
        if r['split'] == 'test': assert not (ROOT / 'cache/circor' / r['file']).exists()
    files = [MANIFEST, ROOT / 'murmur_data.py', ROOT / 'murmur_model.py', Path(__file__),
        ROOT.parent / 'ChestBPM/MurmurAnalysis.swift', ROOT.parent / 'Tools/MurmurProbe.swift', ROOT / 'test_murmur.py']
    files += [p for p in OUTPUT.rglob('*') if p.is_file() and 'features' not in p.parts]
    RESULTS.mkdir(parents=True, exist_ok=True); binary = RESULTS / 'murmur-probe'; shutil.copy2('/tmp/chestbpm-murmur-probe', binary)
    runtime = RESULTS / 'runtime.txt'; runtime.write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)); files += [binary, runtime]
    save(path, dict(time=time.time(), sha256={str(p.resolve().relative_to(ROOT.parent.parent.resolve())): digest(p) for p in files},
        decision='Native three-class argmax only if winningAbsent/Present>=0.60, otherwiseUnsure. Silence/clipping gates, full recording mean. Report all known/unknown/unsure, separate missedpositives and falsealarms. No tuning after test.',
        model='Murmur.pt selected on validation only; exact Core ML model included. No BPM/Watch input.'))
    print('Model, native executable, sources, metrics and120group cohort frozen before test audio access.')


def samples():
    destination = ROOT.parent / 'MurmurSamples'; destination.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'cache/circor/LICENSE.txt', destination / 'LICENSE.txt')
    records = [r for r in json.loads(MANIFEST.read_text())['records'] if r['split'] == 'validation']; manifest = []
    for target, name in enumerate(['absent', 'present', 'unknown']):
        r = sorted((r for r in records if r['target'] == target), key=lambda r: r['record'])[0]
        x, rate = sf.read(ROOT / 'cache/circor' / r['file']); sf.write(destination / (name + '.wav'), x[:rate * 20], rate, subtype='PCM_16')
        manifest.append(dict(name=name, record=r['record'], reference=['Absent', 'Present', 'Unknown'][target], source_sha256=r['sha256'], bundled_sha256=digest(destination / (name + '.wav'))))
    save(destination / 'sources.json', dict(samples=manifest, selection='First record alphabetically per validation location label; no selection by model correctness.',
        citation='CirCor DigiScope1.0.3,Oliveiraetal.,https://doi.org/10.13026/tshs-mw03', license='Open Data Commons Attribution1.0; samples truncated to20seconds and PCM16 encoded.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=['validation', 'freeze', 'test', 'samples'])
    action = parser.parse_args().action
    evaluate(action) if action in ['validation', 'test'] else globals()[action]()
