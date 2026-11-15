"""Frozen, audio-only production replay against independent simultaneous ECG.

Run with the ML virtual environment. No personal recordings or device commands.
ECG reference peaks are automated, not clinician-verified ground truth.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'diagnostic-logs/2026-11-14-v17-ecg-validation'
BASE = 'https://physionet.org/files/ephnogram/1.0.0/'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def fetch(url, path, expected=None):
    if path.exists() and (expected is None or digest(path) == expected): return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.download')
    with urllib.request.urlopen(url, timeout=45) as source, temporary.open('wb') as target:
        size = 0
        while block := source.read(1024 * 1024):
            size += len(block)
            if size > 180_000_000: raise ValueError('Unexpected file size; download stopped')
            target.write(block)
    if expected is not None and digest(temporary) != expected: raise ValueError('Source checksum mismatch: ' + path.name)
    temporary.replace(path)


def reserve(folder):
    metadata = folder / 'metadata'
    for local, remote in [('ephnogram-spreadsheet.csv', 'ECGPCGSpreadsheet.csv'),
                          ('ephnogram-sha256.txt', 'SHA256SUMS.txt'), ('ephnogram-license.txt', 'LICENSE.txt')]:
        fetch(BASE + remote, metadata / local)
    rows = [r for r in csv.DictReader((metadata / 'ephnogram-spreadsheet.csv').open()) if r['Record Name'].startswith('ECGPCG')]
    rng = random.Random(17142026); used = set(); selected = []
    for category, keyword in [('rest', 'Rest:'), ('walking', 'walking at constant'),
                              ('treadmill', 'Bruce protocol'), ('bicycle', 'bicycle')]:
        groups = defaultdict(list)
        for r in rows:
            if keyword in r['Recording Scenario'] and float(r['Record Duration (min)']) >= 30 and r['Subject ID'] not in used:
                groups[r['Subject ID']].append(r)
        subjects = sorted(groups); rng.shuffle(subjects)
        for subject in subjects[:3]:
            r = min(groups[subject], key=lambda v: v['Record Name']); used.add(subject)
            selected.append(dict(record=r['Record Name'], group=subject, condition=category,
                                 ecg_note=r['ECG Notes'], pcg_note=r['PCG Notes']))
    assert len(selected) == len(used) == 12
    protocol = dict(dataset='EPHNOGRAM 1.0.0', source=BASE, seed=17142026, records=selected,
                    starts_seconds=[120, 720, 1440], seconds=30, gains_rms=[0.01, 0.03, 0.1], audio_rate=48000,
                    ecg_rate=500, detector_context_seconds=8, peak_tolerance_seconds=0.05,
                    references=['Eight-second median ECG interval', 'Latest four ECG intervals'],
                    reference_rules='At least five nonnegative-time QRS peaks; both corrected detectors must agree one-to-one within50ms, with no unmatched beat in the reference span. RR intervals0.28–2.4s; maximum interval below1.8median intervals; newest beat within1.5median intervals. No imputation or time-shift optimization.',
                    audio_rules='PCG only; remove clip median, normalize each clip to each fixed RMS, resample to48kHz, PCM16. Report every gain, including clipping. No motion channel available; replay motion=0.',
                    scope='Report40–176BPM accuracy, out-of-range outputs, all missing references and abstentions separately. Repeated gains/windows stay in participant clusters.',
                    limitations='Automated ECG QRS timing is a stronger independent comparison, not clinician-verified ground truth or validation of the phone microphone. Do not tune estimators after seeing this cohort.')
    plan = folder / 'protocol.json'; freeze = folder / 'freeze.json'
    if plan.exists() or freeze.exists(): raise ValueError('Reservation already frozen; refusing overwrite')
    save(plan, protocol)
    frozen = json.loads((ROOT / 'ML/evaluation-freeze-v17.json').read_text())['sha256']
    # Earlier freeze paths are relative to the parent workspace.
    hashes = {str((ROOT.parent / k).resolve()): v for k, v in frozen.items()}
    baseline = ROOT / 'diagnostic-logs/2026-11-14-v17-analysis'
    for f in [Path(__file__), ROOT / 'ML/ecg-requirements.txt', ROOT / 'Tools/ProductionReplay.swift',
              baseline / 'replay-executables/chestbpm-production-v16-frozen',
              baseline / 'replay-executables/chestbpm-production-v17',
              *list((baseline / 'baseline').glob('*.swift')), plan, *metadata.iterdir()]:
        if f.is_file(): hashes[str(f.resolve())] = digest(f)
    save(freeze, dict(time=time.time(), sha256=hashes, note='Frozen before any selected waveform download or inspection.'))
    print(json.dumps(protocol), flush=True)


def verify(folder):
    for name, value in json.loads((folder / 'freeze.json').read_text())['sha256'].items():
        if digest(Path(name)) != value: raise ValueError('Frozen file changed: ' + name)
    return json.loads((folder / 'protocol.json').read_text())


def download(folder):
    plan = verify(folder)
    sums = {line.split(maxsplit=1)[1].lstrip('*./'): line.split()[0]
            for line in (folder / 'metadata/ephnogram-sha256.txt').read_text().splitlines() if line.strip()}
    def one(record):
        name = 'MAT/' + record['record'] + '.mat'; target = folder / name
        fetch(BASE + name, target, sums[name])
        print('Verified source', name, target.stat().st_size, flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(one, plan['records']))


def reference(a, b, at, latest=False, tolerance=0.05):
    import numpy as np
    chosen = a[(a >= max(0, at - 8)) & (a <= at)] if not latest else a[(a >= 0) & (a <= at)][-5:]
    if len(chosen) < 5: return None, 'insufficient_peaks'
    other = b[(b >= chosen[0] - tolerance) & (b <= at)]
    if len(other) != len(chosen) or np.any(np.abs(chosen - other) > tolerance): return None, 'detectors_disagree'
    rr = np.diff(chosen)
    if np.any((rr < 0.28) | (rr > 2.4)): return None, 'implausible_ecg_intervals'
    if max(rr) >= 1.8 * np.median(rr): return None, 'possible_missing_ecg_beat'
    if at - chosen[-1] > 1.5 * np.median(rr): return None, 'old_ecg_reference'
    return float(240 / (chosen[-1] - chosen[0]) if latest else 60 / np.median(rr)), 'available'


def prepare(folder):
    import numpy as np
    from scipy.io import loadmat
    from scipy.signal import resample_poly, butter, sosfiltfilt
    import soundfile as sf
    from wfdb import processing
    plan = verify(folder); cases = []; requests = []
    for record in plan['records']:
        source = folder / 'MAT' / (record['record'] + '.mat')
        data = loadmat(source, variable_names=['ECG', 'PCG', 'fs']); rate = int(np.asarray(data['fs']).item())
        ecg = np.asarray(data['ECG']).squeeze(); pcg = np.asarray(data['PCG']).squeeze()
        assert ecg.ndim == pcg.ndim == 1 and len(ecg) == len(pcg)
        for start in plan['starts_seconds']:
            context = plan['detector_context_seconds']; begin = start - context; duration = plan['seconds']
            segment = ecg[int(begin * rate):int((start + duration + context) * rate)]
            if len(segment) != (duration + context * 2) * rate: raise ValueError('Incomplete predeclared ECG span')
            common = math.gcd(rate, plan['ecg_rate']); e = resample_poly(segment, plan['ecg_rate'] // common, rate // common)
            e = e - np.median(e); e = e / max(float(np.std(e)), 1e-12)
            peaks = []; detector_errors = []
            for detect in [lambda: processing.xqrs_detect(e, plan['ecg_rate'], verbose=False),
                           lambda: processing.gqrs_detect(e, plan['ecg_rate'])]:
                try:
                    if not np.all(np.isfinite(e)) or np.std(e) < 1e-12: raise ValueError('Missing or flat ECG')
                    band = sosfiltfilt(butter(3, [5, 40], fs=plan['ecg_rate'], btype='bandpass', output='sos'), e)
                    values = detect()
                    corrected = processing.correct_peaks(np.abs(band), values, search_radius=40, smooth_window_size=5, peak_dir='up') if len(values) else []
                    peaks.append((np.unique(corrected) / plan['ecg_rate'] - context).tolist()); detector_errors.append(None)
                except Exception as error:
                    peaks.append([]); detector_errors.append(str(error))
            raw = np.asarray(pcg[start * rate:(start + duration) * rate], dtype=float)
            assert len(raw) == duration * rate and np.all(np.isfinite(raw))
            raw -= np.median(raw); rms = float(np.sqrt(np.mean(raw ** 2)))
            for gain in plan['gains_rms']:
                case_id = f"{record['record']}-t{start}-rms{gain}"
                normalized = raw * gain / max(rms, 1e-12)
                common = math.gcd(rate, plan['audio_rate']); audio = resample_poly(normalized, plan['audio_rate'] // common, rate // common)
                path = folder / 'Audio' / (case_id + '.wav'); path.parent.mkdir(exist_ok=True)
                sf.write(path, np.clip(audio, -.999, .999), plan['audio_rate'], subtype='PCM_16')
                cases.append(dict(id=case_id, **record, start=start, gain=gain, pcg_rms=rms,
                                  clipping_fraction=float(np.mean(np.abs(audio) >= .999)),
                                  ecg_xqrs=peaks[0], ecg_gqrs=peaks[1], detector_errors=detector_errors,
                                  source_sha256=digest(source), audio_sha256=digest(path)))
                updates = [dict(sequence=n, samples=n * plan['audio_rate'] // 2, time=n * 500, elapsed=n / 2, motion=0) for n in range(1, duration * 2 + 1)]
                requests.append(dict(id=case_id, path=str(path.resolve()), output='', updates=updates))
            print('Prepared', record['record'], start, flush=True)
    save(folder / 'evaluation-only-references.json', cases)
    for version in ['v16', 'v17']:
        output = folder / ('production-' + version); output.mkdir(exist_ok=True)
        native = [dict(r, output=str((output / (r['id'] + '.ndjson')).resolve())) for r in requests]
        save(folder / ('audio-only-' + version + '.json'), native)
    save(folder / 'prepared.json', dict(cases=len(cases), time=time.time(), ecg_detectors='WFDB4.3.1 XQRS and GQRS, absolute-QRS peak correction, one-to-one agreement. GQRS has documented known issues; agreement is a quality screen, not proof of correct annotations.'))


def evaluate(folder):
    import numpy as np
    plan = verify(folder); results = []
    for case in json.loads((folder / 'evaluation-only-references.json').read_text()):
        outputs = {}
        for version in ['v16', 'v17']:
            path = folder / ('production-' + version) / (case['id'] + '.production.ndjson')
            outputs[version] = {r['update']['sequence']: r for r in map(json.loads, path.open())}
        assert set(outputs['v16']) == set(outputs['v17']) == set(range(1, plan['seconds'] * 2 + 1))
        for sequence, newer in outputs['v17'].items():
            older = outputs['v16'][sequence]; seconds = newer['update']['elapsed']
            if seconds < 6: continue
            age = newer['estimate'].get('analysisAge', 0)
            assert abs(age - older['estimate'].get('analysisAge', 0)) < 1e-9
            at = seconds - age
            for latest in [False, True]:
                value, quality = reference(np.array(case['ecg_xqrs']), np.array(case['ecg_gqrs']), at, latest, plan['peak_tolerance_seconds'])
                results.append(dict(id=case['id'], group=case['group'], condition=case['condition'], gain=case['gain'], seconds=seconds,
                                    definition='latest4' if latest else 'median8', reference=value, reference_quality=quality,
                                    in_range=value is not None and 40 <= value <= 176,
                                    v16=older['estimate'].get('bpm'), v17=newer['estimate'].get('bpm')))
    save(folder / 'comparisons.json', results)
    summaries = {}
    for definition in ['median8', 'latest4']:
        data = [r for r in results if r['definition'] == definition]
        eligible = [r for r in data if r['in_range']]
        summary = dict(frames=len(data), available_reference=sum(r['reference'] is not None for r in data),
                       missing_reference=dict(Counter(r['reference_quality'] for r in data if r['reference'] is None)),
                       in_range=len(eligible), out_of_range=sum(r['reference'] is not None and not r['in_range'] for r in data))
        for version in ['v16', 'v17']:
            returned = [r for r in eligible if r[version] is not None]; errors = [abs(r[version] - r['reference']) for r in returned]
            summary[version] = dict(returned=len(returned), coverage=len(returned) / len(eligible) if eligible else None,
                                    mean_absolute_error=statistics.mean(errors) if errors else None, maximum_absolute_error=max(errors, default=None),
                                    over5=sum(v > 5 for v in errors), over10=sum(v > 10 for v in errors),
                                    within5_coverage=sum(v <= 5 for v in errors) / len(eligible) if eligible else None,
                                    returned_without_reference=sum(r[version] is not None and r['reference'] is None for r in data),
                                    returned_outside_range=sum(r[version] is not None and r['reference'] is not None and not r['in_range'] for r in data))
        summaries[definition] = summary
    save(folder / 'summary.json', dict(time=time.time(), protocol=plan, results=summaries,
                                      note='Same audio and reference times for both frozen production estimators. Automated ECG comparison, not clinician-verified or phone-hardware validation.'))
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['reserve', 'download', 'prepare', 'evaluate'])
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args(); os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    globals()[args.action](args.output)
