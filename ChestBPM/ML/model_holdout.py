"""Locked patient-level test for one sound-model candidate, after development.

No personal/device data. Download requires a source/model/metric freeze first.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

import numpy as np
from scipy import signal
import soundfile as sf

from prepare_data import fetch
from event_benchmark import labels_from_annotations, warp_diastole, contact_noise, runs, requests, score

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'diagnostic-logs/2026-11-14-event-model-research/holdout'
CONDITIONS = ['clean', 'irregular', 'contact', 'irregular_contact', 'clipped', 'irregular_clipped', 'noise_only']


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data): path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def verify(folder):
    frozen = json.loads((folder / 'freeze.json').read_text())
    for name, expected in frozen['sha256'].items():
        if sha(Path(name)) != expected: raise ValueError('Frozen input changed: ' + name)
    return json.loads((folder / 'protocol.json').read_text())


def freeze(folder, model):
    if (folder / 'freeze.json').exists(): raise ValueError('Final test freeze exists; refusing overwrite')
    manifest = json.loads((ROOT / 'beat-v2-holdout.json').read_text())
    assert len(manifest['records']) == 24
    for record in manifest['records']:
        assert all(not (ROOT / 'cache/circor' / name).exists() for name in record['files'])
    model = model.resolve()
    assert (model / 'BeatStates.mlpackage').is_dir()
    event_binary = folder / 'event-probe'; shutil.copy2('/tmp/chestbpm-event-probe-v17', event_binary); event_binary.chmod(0o700)
    native = ROOT.parent / 'diagnostic-logs/2026-11-14-v17-analysis/replay-executables/chestbpm-production-v17'
    production = folder / 'production-probe'; shutil.copy2(native, production); production.chmod(0o700)
    protocol = dict(seed=48142026, candidate_model=str(model), baseline_model=str((ROOT / 'Models').resolve()),
                    records=manifest['records'], conditions=CONDITIONS, rate=1000, peak_level=.3,
                    contact_snr_db=6, clipping_quantile=.9, source_seconds_limit=30,
                    event_rules='Same event_benchmark.py raw/episodes,50/100ms,2secondwarmup,unknownannotationsnotnoise,noRRregularitygate.',
                    bpm_rules='Actual production estimator for both models. Fixed8secondmedianS1interval andlatest4intervalmean. No joins across unknown annotation gaps. All eligible/missing references, abstentions and noise-only returns reported.',
                    note='24previouslyunreadlinkedpatients; no personal/Watch data, no disease outputs. Synthetic irregularity is not diagnosedAFib. Do not tune after this test.')
    save(folder / 'protocol.json', protocol)
    (folder / 'runtime-requirements.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True))
    files = [Path(__file__), ROOT / 'event_benchmark.py', ROOT / 'reserve_model_v2.py', ROOT / 'beat-v2-holdout.json',
             ROOT / 'prepare_data.py', ROOT / 'beat_model.py', ROOT / 'beat_model_v2.py', ROOT / 'beat_model_adapt.py', ROOT / 'beat_model_ensemble.py',
             ROOT.parent / 'Tools/EventProbe.swift', ROOT.parent / 'Tools/ProductionReplay.swift', event_binary, production,
             folder / 'protocol.json', folder / 'runtime-requirements.txt']
    files += [Path(name) for name in json.loads((ROOT / 'evaluation-freeze-v17.json').read_text())['sha256']]
    files += [p for p in model.rglob('*') if p.is_file()]
    # Prior freeze paths are workspace-relative.
    hashes = {}
    for path in files:
        if not path.is_absolute(): path = ROOT.parent.parent / path
        hashes[str(path.resolve())] = sha(path)
    save(folder / 'freeze.json', dict(time=time.time(), sha256=hashes))
    print('Frozen candidate,24patientcohort,metrics,sourcesandbothnativeexecutables beforewaveformaccess.')


def download(folder):
    protocol = verify(folder)
    for record in protocol['records']:
        for name, expected in record['files'].items(): fetch(name, expected)
        print('Verified new patient', record['group'], record['record'], flush=True)


def prepare(folder):
    protocol = verify(folder)
    if (folder / 'references.json').exists(): raise ValueError('Prepared final cases exist; refusing overwrite')
    rng = np.random.default_rng(protocol['seed']); cases = []
    for record in protocol['records']:
        for name, expected in record['files'].items(): assert sha(ROOT / 'cache/circor' / name) == expected
        prefix = ROOT / 'cache/circor/training_data' / record['record']
        audio, rate = sf.read(str(prefix) + '.wav'); audio = signal.resample_poly(audio, 1000, rate)[:30000]
        audio = audio / max(float(np.max(np.abs(audio))), 1e-8) * .3
        labels = labels_from_annotations(np.loadtxt(str(prefix) + '.tsv', ndmin=2), len(audio))
        irregular, changed = warp_diastole(audio, labels, rng)
        for condition in CONDITIONS:
            wave, target = (irregular.copy(), changed.copy()) if condition.startswith('irregular') else (audio.copy(), labels.copy())
            if condition.endswith('contact'): wave += contact_noise(len(wave), rng) * np.sqrt(np.mean(wave ** 2)) * 10 ** (-6 / 20)
            if condition.endswith('clipped'):
                limit = max(float(np.quantile(np.abs(wave), .9)), 1e-5); wave = np.clip(wave, -limit, limit)
            if condition == 'noise_only': wave = contact_noise(len(wave), rng) * .03; target = np.zeros(len(wave), dtype=np.int8)
            identifier = record['record'] + '-' + condition
            path = folder / 'Audio' / (identifier + '.wav'); path.parent.mkdir(exist_ok=True)
            sf.write(path, np.clip(wave, -.95, .95), 1000, subtype='PCM_16'); label_path = path.with_suffix('.npy'); np.save(label_path, target)
            cases.append(dict(id=identifier, group=record['group'], condition=condition, path=str(path.resolve()), labels=str(label_path.resolve()),
                              audio_sha256=sha(path), labels_sha256=sha(label_path), source_files=record['files']))
    assert len(cases) == 168
    save(folder / 'references.json', cases)
    for tag in ['v17', 'candidate']:
        requests(folder, tag); native = []
        for c in cases:
            labels = np.load(c['labels']); endpoints = range(500, len(labels) + 1, 500)
            updates = [dict(sequence=i + 1, samples=n, time=n, elapsed=n / 1000, motion=0) for i, n in enumerate(endpoints)]
            native.append(dict(id=c['id'], path=c['path'], output=str((folder / tag / (c['id'] + '.ndjson')).resolve()), updates=updates))
        save(folder / ('production-requests-' + tag + '.json'), native)
    print('Prepared168finalcases; sameaudioandlabelsforbothmodels.')


def bpm_reference(labels, at, latest):
    onsets = np.array([a / 1000 for a, _, k in runs(labels) if k == 1])
    selected = onsets[(onsets >= max(0, at - 8)) & (onsets <= at)] if not latest else onsets[(onsets >= 0) & (onsets <= at)][-5:]
    if len(selected) < 5: return None, 'insufficient_events'
    if np.any(labels[int(selected[0] * 1000):int(selected[-1] * 1000)] == 0): return None, 'unknown_annotation_gap'
    intervals = np.diff(selected)
    if latest and at - selected[-1] > np.median(intervals) * 1.5: return None, 'old_reference'
    return float(240 / (selected[-1] - selected[0]) if latest else 60 / np.median(intervals)), 'available'


def evaluate(folder):
    verify(folder); cases = json.loads((folder / 'references.json').read_text()); comparisons = []
    for tag in ['v17', 'candidate']: score(folder, tag)
    for case in cases:
        labels = np.load(case['labels']); values = {}
        for tag in ['v17', 'candidate']:
            path = folder / tag / (case['id'] + '.production.ndjson')
            values[tag] = {r['update']['sequence']: r for r in map(json.loads, path.open())}
        assert set(values['v17']) == set(values['candidate'])
        for sequence, old in values['v17'].items():
            new = values['candidate'][sequence]; seconds = old['update']['elapsed']
            if seconds < 6: continue
            age = old['estimate'].get('analysisAge', 0)
            assert new['estimate'].get('bpm') is None or abs(new['estimate'].get('analysisAge', 0) - age) < 1e-9
            for latest in [False, True]:
                reference, reason = (None, 'known_no_heart') if case['condition'] == 'noise_only' else bpm_reference(labels, seconds - age, latest)
                comparisons.append(dict(id=case['id'], group=case['group'], condition=case['condition'], seconds=seconds,
                    definition='latest4' if latest else 'median8', reference=reference, reference_quality=reason,
                    in_range=reference is not None and 40 <= reference <= 176,
                    v17=old['estimate'].get('bpm'), candidate=new['estimate'].get('bpm')))
    save(folder / 'bpm-comparisons.json', comparisons); summary = {}
    for definition in ['median8', 'latest4']:
        rows = [r for r in comparisons if r['definition'] == definition]; eligible = [r for r in rows if r['in_range']]
        result = dict(updates=len(rows), eligible=len(eligible),
                      negative_control_updates=sum(r['condition'] == 'noise_only' for r in rows),
                      missing_reference=sum(r['reference'] is None and r['condition'] != 'noise_only' for r in rows),
                      out_of_range=sum(r['reference'] is not None and not r['in_range'] for r in rows))
        for tag in ['v17', 'candidate']:
            errors = [abs(r[tag] - r['reference']) for r in eligible if r[tag] is not None]
            result[tag] = dict(returned=len(errors), mae=statistics.mean(errors) if errors else None, maximum=max(errors, default=None),
                               over5=sum(e > 5 for e in errors), within5coverage=sum(e <= 5 for e in errors) / len(eligible) if eligible else None,
                               returned_without_reference=sum(r[tag] is not None and r['reference'] is None and r['condition'] != 'noise_only' for r in rows),
                               returned_outside_range=sum(r[tag] is not None and r['reference'] is not None and not r['in_range'] for r in rows),
                               noise_only_returns=sum(r[tag] is not None for r in rows if r['condition'] == 'noise_only'))
        summary[definition] = result
    save(folder / 'bpm-summary.json', summary); print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=['freeze', 'download', 'prepare', 'evaluate'])
    parser.add_argument('--output', type=Path, default=DEFAULT); parser.add_argument('--model', type=Path, default=ROOT / 'generated/beat-ensemble')
    args = parser.parse_args(); args.output = args.output.resolve(); os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    freeze(args.output, args.model) if args.action == 'freeze' else globals()[args.action](args.output)
