#!/usr/bin/env python3
"""Reconstruct overlapping logged features, verify the old math, then evaluate current selection.

No raw audio is needed. This cannot evaluate changes to microphone filters or feature extraction.
Private input/output must stay outside source control. Swift receives no Watch values.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile


def reconstruct(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    start_index = next(i for i in range(len(rows) - 1, -1, -1) if rows[i]['event'] == 'test_started')
    test = rows[start_index]['test']
    rate = next(r['sampleRate'] for r in reversed(rows[:start_index]) if r['event'] == 'microphone_started')
    frames = [r for r in rows if r.get('test') == test and r['event'] == 'estimate']
    trace = {}
    for row in frames:
        d = row['estimate']['diagnostics']
        if 'envelope' not in d:
            continue
        end = math.floor(d['signal']['totalSamples'] * 200 / rate) + 1
        envelope, brightness = d['envelope'], d['brightness']
        if len(envelope) != min(end, 1600) or len(brightness) != len(envelope):
            raise ValueError('Trace length does not match the logged sample count')
        for index, pair in enumerate(zip(envelope, brightness), end - len(envelope)):
            if index in trace and trace[index] != pair:
                raise ValueError('Overlapping traces differ; cannot reconstruct this capture')
            trace[index] = pair
    replay = []
    for row in frames:
        e = row['estimate']; d = e['diagnostics']
        end = math.floor(d['signal']['totalSamples'] * 200 / rate) + 1
        indices = range(max(0, end - 1600), end)
        if not all(i in trace for i in indices):
            continue
        replay.append(dict(sequence=row['sequence'], time=row['time'], elapsed=row['elapsed'], seconds=e['seconds'],
                           level=e['level'], clipping=d['signal']['clippingFraction'], score=e['periodicity'],
                           envelope=[trace[i][0] for i in indices], brightness=[trace[i][1] for i in indices],
                           original=e.get('original'), cycle=e.get('cycle'), previous=e.get('bpm'), legacyCapture='source' not in d))
    if not replay or replay[0]['seconds'] >= 6:
        raise ValueError('Missing initial frames; cannot reproduce smoothing state')
    # A missing tail is allowed and reported. Interior gaps would change confirmation/smoothing.
    if [r['sequence'] for r in replay] != [r['sequence'] for r in frames[:len(replay)]]:
        raise ValueError('Interior frame gap; cannot reproduce tracking state')
    pairs = [r['pair'] for r in rows if r.get('test') == test and r['event'] == 'automatic_pair']
    return test, frames, replay, pairs


def errors(values):
    return dict(count=len(values), mean_absolute_difference=statistics.mean(values) if values else None,
                median_absolute_difference=statistics.median(values) if values else None,
                max_absolute_difference=max(values) if values else None, over_5=sum(v > 5 for v in values))


def evaluate(results, pairs):
    warm = [r for r in results if r['seconds'] >= 6]
    matched = []
    for pair in pairs:
        frame = min(results, key=lambda r: abs(r['time'] - pair['time']))
        if abs(frame['time'] - pair['time']) < 1:
            matched.append(dict(elapsed=frame['elapsed'], watch=pair['watch'], previous=frame.get('previous'), candidate=frame.get('candidate')))
    common = [p for p in matched if p['previous'] is not None and p['candidate'] is not None]
    recovered = [p for p in matched if p['previous'] is None and p['candidate'] is not None]
    stats = dict(warm_frames=len(warm), previous_returns=sum(r.get('previous') is not None for r in warm),
                 candidate_returns=sum(r.get('candidate') is not None for r in warm),
                 changed_existing_returns=sum(r.get('previous') is not None and r.get('candidate') != r['previous'] for r in warm),
                 matched_pairs=len(matched), unmatched_pairs=len(pairs) - len(matched), common_pairs=len(common))
    for key in ['previous', 'candidate']:
        stats[key] = errors([abs(p[key] - p['watch']) for p in matched if p[key] is not None])
        stats[key + '_common'] = errors([abs(p[key] - p['watch']) for p in common])
    stats['newly_returned_pairs'] = errors([abs(p['candidate'] - p['watch']) for p in recovered])
    return stats, matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent.parent
    sources = [root / 'ChestBPM/HeartRateEstimator.swift', root / 'ChestBPM/NoiseAnalysis.swift', root / 'ChestBPM/NeuralSignal.swift', root / 'Tools/Replay.swift']
    fingerprint = hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()
    with tempfile.TemporaryDirectory(prefix='chestbpm-replay-') as temporary:
        work = Path(temporary); executable = work / 'replay'
        subprocess.run(['swiftc', '-O', '-module-cache-path', str(work / 'modules'), *map(str, sources), '-o', str(executable)], check=True)
        reports = []
        for index, path in enumerate(args.logs, 1):
            test, frames, replay, pairs = reconstruct(path)
            input_path = work / 'input.json'; input_path.write_text(json.dumps(replay))
            completed = subprocess.run([str(executable), str(input_path)], capture_output=True, text=True, check=True)
            results = json.loads(completed.stdout)
            stats, matched = evaluate(results, pairs)
            report = dict(test=test, input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), source_sha256=fingerprint,
                          frames_recorded=len(frames), frames_reconstructed=len(replay), old_math_reproduced=True,
                          statistics=stats, pairs=matched,
                          limitation='Development recordings with overlapping windows, not new or independent validation. Watch values only enter evaluation.')
            (args.output / f'run-{index}.json').write_text(json.dumps(report, indent=2))
            (args.output / f'run-{index}-frames.ndjson').write_text(''.join(json.dumps(r) + '\n' for r in results))
            reports.append(report)
            print(json.dumps({k: report[k] for k in ['test', 'frames_recorded', 'frames_reconstructed', 'old_math_reproduced', 'statistics']}), flush=True)
        (args.output / 'summary.json').write_text(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
