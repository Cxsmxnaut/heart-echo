"""Development sound-event benchmark. Irregular timing is never a noise label.

Uses public validation subjects only; no clinical rhythm/disease labels or personal data.
The original sound-state annotations are semi-supervised, not clinical ground truth.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.optimize import linear_sum_assignment
import soundfile as sf

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'diagnostic-logs/2026-11-14-event-model-research'


def runs(labels):
    edges = np.r_[0, np.flatnonzero(labels[1:] != labels[:-1]) + 1, len(labels)]
    return [(int(a), int(b), int(labels[a])) for a, b in zip(edges, edges[1:]) if b > a]


def labels_from_annotations(annotations, samples, rate=1000):
    labels = np.zeros(samples, dtype=np.int8)
    for start, end, kind in annotations:
        labels[max(0, round(start * rate)):min(samples, round(end * rate))] = int(kind)
    return labels


def warp_diastole(audio, labels, rng):
    """Alter diastolic duration; preserve every S1/S2 waveform sample and its label."""
    waves, targets = [], []
    for a, b, kind in runs(labels):
        count = max(1, round((b - a) * rng.uniform(.55, 1.65))) if kind == 4 else b - a
        wave = np.interp(np.linspace(0, b - a - 1, count), np.arange(b - a), audio[a:b]) if kind == 4 else audio[a:b].copy()
        waves.append(wave); targets.append(np.full(count, kind, dtype=np.int8))
    return np.concatenate(waves), np.concatenate(targets)


def contact_noise(samples, rng, rate=1000):
    """Known noise-only synthetic contact pulses, with independent irregular timing."""
    noise = signal.sosfilt(signal.butter(2, [20, 350], btype='bandpass', fs=rate, output='sos'), rng.normal(size=samples))
    envelope = np.full(samples, .03); at = .3
    while at < samples / rate:
        a = int(at * rate); count = min(samples - a, int(rng.uniform(.04, .18) * rate))
        if count > 0: envelope[a:a + count] += np.hanning(count) * rng.uniform(.4, 1)
        at += rng.uniform(.45, .9)
    noise *= envelope
    return noise / max(float(np.sqrt(np.mean(noise ** 2))), 1e-12)


def prepare(folder):
    output = folder / 'references.json'
    if output.exists(): raise ValueError('Prepared cases already exist; refusing overwrite')
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    groups = set(json.loads((ROOT / 'results/beat-training.json').read_text())['groups']['validation_groups'])
    rng = np.random.default_rng(18142026); cases = []
    for record in manifest['records']:
        if record['group'] not in groups: continue
        prefix = ROOT / 'cache/circor/training_data' / record['record']
        audio, rate = sf.read(str(prefix) + '.wav'); audio = signal.resample_poly(audio, 1000, rate)[:30000]
        audio = audio / max(float(np.max(np.abs(audio))), 1e-8) * .3
        labels = labels_from_annotations(np.loadtxt(str(prefix) + '.tsv', ndmin=2), len(audio))
        irregular, changed = warp_diastole(audio, labels, rng)
        for condition in ['clean', 'irregular', 'contact', 'irregular_contact', 'noise_only']:
            wave, target = (irregular.copy(), changed.copy()) if condition.startswith('irregular') else (audio.copy(), labels.copy())
            if condition == 'noise_only':
                wave = contact_noise(len(wave), rng) * .03; target = np.zeros(len(wave), dtype=np.int8)
            elif condition.endswith('contact'):
                wave += contact_noise(len(wave), rng) * np.sqrt(np.mean(wave ** 2)) * 10 ** (-6 / 20)
            identifier = record['record'] + '-' + condition
            path = folder / 'Audio' / (identifier + '.wav'); path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, np.clip(wave, -.95, .95), 1000, subtype='PCM_16')
            label_path = path.with_suffix('.npy'); np.save(label_path, target)
            cases.append(dict(id=identifier, group=record['group'], condition=condition, path=str(path.resolve()), labels=str(label_path.resolve()),
                              audio_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), labels_sha256=hashlib.sha256(label_path.read_bytes()).hexdigest()))
    assert {c['group'] for c in cases} == groups and len(cases) == len(groups) * 5
    output.write_text(json.dumps(cases, indent=2) + '\n')
    (folder / 'protocol.json').write_text(json.dumps(dict(seed=18142026, rate=1000, tolerances_seconds=[.05, .1], score_start=2,
        end_margin=.25, fragment_gap=.05, maximum_sound_duration=.25,
        data='Existing16publicvalidationgroups, development evidence only. No personal or Watch data.',
        rhythm='Diastolic duration varies; every original S1/S2 sample retained. This does not create diagnosed AFib.',
        annotation='State0 is unannotated/unknown, not assumed noise. Only explicit synthetic noise-only cases score all events as false.',
        intervals='Only consecutive matched predictions and consecutive annotated S1 events form a scored interval. Never bridge missed/extra beats or unknown annotation gaps.'), indent=2) + '\n')
    print('Prepared', len(cases), 'development cases from', len(groups), 'validation groups.')


def requests(folder, tag):
    cases = json.loads((folder / 'references.json').read_text()); target = folder / tag; target.mkdir(exist_ok=True)
    result = [dict(id=c['id'], path=c['path'], output=str((target / (c['id'] + '.json')).resolve())) for c in cases]
    (folder / ('requests-' + tag + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    print('Prepared audio-only event requests:', tag, len(result))


def episodes(events, masks, gap=.05, maximum=.25):
    """Join short fragments of one sound, never smooth heart-to-heart intervals."""
    merged = []
    for event in events:
        e = dict(event); e['parts'] = 1; e['observedFrames'] = e['lastFrame'] - e['firstFrame'] + 1
        if merged:
            old = merged[-1]
            masked = any(a < e['end'] and b > old['start'] for a, b in masks)
            if (old['kind'] == e['kind'] and old['complete'] and e['complete'] and not masked
                    and 0 <= e['start'] - old['end'] <= gap and e['end'] - old['start'] <= maximum):
                n1 = old['observedFrames']; n2 = e['observedFrames']
                w1 = old['meanConfidence'] * n1; w2 = e['meanConfidence'] * n2
                e.update(start=old['start'], firstFrame=old['firstFrame'], parts=old['parts'] + 1, observedFrames=n1 + n2,
                         time=(old['time'] * w1 + e['time'] * w2) / (w1 + w2),
                         confidence=max(old['confidence'], e['confidence']), meanConfidence=(w1 + w2) / (n1 + n2),
                         acousticValid=old['acousticValid'] and e['acousticValid'])
                merged.pop()
        e['qualified'] = e['complete'] and e['acousticValid'] and 2 <= e['lastFrame'] - e['firstFrame'] + 1 <= round(maximum * 100)
        merged.append(e)
    return merged


def match(truth, predictions, tolerance):
    if not len(truth) or not len(predictions): return []
    distances = np.abs(np.array(truth)[:, None] - np.array(predictions)[None, :])
    allowed = distances <= tolerance + 1e-12
    a, b = linear_sum_assignment(np.where(allowed, distances, 1000))
    return [(int(i), int(j), float(distances[i, j])) for i, j in zip(a, b) if allowed[i, j]]


def score(folder, tag):
    cases = json.loads((folder / 'references.json').read_text()); reports = []
    for case in cases:
        labels = np.load(case['labels']); data = json.loads((folder / tag / (case['id'] + '.json')).read_text())
        for name, expected in [('audio', case['audio_sha256']), ('labels', case['labels_sha256'])]:
            path = Path(case['path'] if name == 'audio' else case['labels'])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
        begin = max(2, data['coverageStart']); end = min(data['seconds'] - .25, data['coverageEnd'])
        known = labels > 0 if case['condition'] != 'noise_only' else np.ones(len(labels), dtype=bool)
        reference = {kind: [((a + b) / 2000) for a, b, k in runs(labels) if k == state and begin <= (a + b) / 2000 <= end]
                     for kind, state in [('S1', 1), ('S2', 3)]}
        for mode, events in [('raw', data['events']), ('episodes', episodes(data['events'], data['maskedRanges']))]:
            for tolerance in [.05, .1]:
                report = dict(id=case['id'], group=case['group'], condition=case['condition'], mode=mode, tolerance=tolerance,
                              known_seconds=float(np.sum(known[max(0, int(begin * 1000)):max(0, int(end * 1000))]) / 1000))
                for kind in ['S1', 'S2']:
                    pred = [e['time'] for e in events if e['kind'] == kind and e['qualified'] and begin <= e['time'] <= end
                            and 0 <= int(e['time'] * 1000) < len(known) and known[int(e['time'] * 1000)]]
                    truth = reference[kind]; pairs = match(truth, pred, tolerance)
                    errors = [p[2] * 1000 for p in pairs]; intervals = []
                    for (a, b, _), (c, d, _) in zip(pairs, pairs[1:]):
                        if c == a + 1 and d == b + 1 and np.all(known[int(truth[a] * 1000):int(truth[c] * 1000)]):
                            intervals.append(abs((pred[d] - pred[b]) - (truth[c] - truth[a])) * 1000)
                    reference_intervals = sum(np.all(known[int(a * 1000):int(b * 1000)]) for a, b in zip(truth, truth[1:]))
                    report[kind] = dict(tp=len(pairs), fp=len(pred) - len(pairs), fn=len(truth) - len(pairs),
                                        reference_intervals=int(reference_intervals), matched_intervals=len(intervals),
                                        timing_errors_ms=errors, consecutive_interval_errors_ms=intervals)
                reports.append(report)
    output = dict(tag=tag, cases=len(cases), groups=len({c['group'] for c in cases}), reports=reports,
                  note='Development benchmark against public semi-supervised sound annotations; not AFib or murmur diagnosis, not independent clinical validation.')
    (folder / ('scores-' + tag + '.json')).write_text(json.dumps(output, indent=2) + '\n')
    for condition in sorted({c['condition'] for c in cases}):
        values = [r for r in reports if r['condition'] == condition and r['mode'] == 'episodes' and r['tolerance'] == .1]
        result = dict(condition=condition)
        for kind in ['S1', 'S2']:
            tp, fp, fn = [sum(r[kind][key] for r in values) for key in ['tp', 'fp', 'fn']]
            result[kind] = dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None)
        print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'requests', 'score']); parser.add_argument('--tag', default='v17')
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args(); os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    prepare(args.output) if args.action == 'prepare' else requests(args.output, args.tag) if args.action == 'requests' else score(args.output, args.tag)
