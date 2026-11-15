#!/usr/bin/env python3
"""Read this development app's NDJSON file over CoreDevice without restarting it."""
import argparse
import collections
import json
import math
import os
import re
from pathlib import Path
import statistics
import subprocess
import time


def finite(value):
    return isinstance(value, (float, int)) and math.isfinite(value)


def summary(rows):
    starts = [r for r in rows if r.get('event') == 'test_started']
    test = starts[-1].get('test') if starts else None
    active = [r for r in rows if test and r.get('test') == test]
    frames = [r for r in active if r.get('event') == 'estimate']
    warm = [r for r in frames if r.get('estimate', {}).get('seconds', 0) >= 6]
    pairs = [r['pair'] for r in active if r.get('event') == 'automatic_pair']
    def errors(key):
        return [abs(p[key] - p['watch']) for p in pairs if finite(p.get(key)) and finite(p.get('watch'))]
    def stats(values):
        return {'count': len(values), 'mean_absolute_error': statistics.mean(values) if values else None,
                'median_absolute_error': statistics.median(values) if values else None,
                'maximum_absolute_error': max(values) if values else None,
                'over_5_bpm': sum(v > 5 for v in values)}
    result = {'test': test, 'frames': len(frames), 'warm_frames': len(warm),
              'accepted_frames': sum(finite(r.get('estimate', {}).get('bpm')) for r in warm),
              'fresh_watch_frames': sum(r.get('watchFresh') is True for r in warm), 'pairs': len(pairs),
              'original_errors': stats(errors('original')), 'improved_errors': stats(errors('improved')),
              'original_unsure_pairs': sum(p.get('original') is None for p in pairs),
              'improved_unsure_pairs': sum(p.get('improved') is None for p in pairs),
              'display_reasons': dict(collections.Counter(r.get('estimate', {}).get('status') for r in warm)),
              'selection_sources': dict(collections.Counter(r.get('estimate', {}).get('diagnostics', {}).get('source', 'legacy') for r in warm)),
              'baseline_reasons': dict(collections.Counter(r.get('estimate', {}).get('diagnostics', {}).get('periodicity', {}).get('reason') for r in warm)),
              'cycle_reasons': dict(collections.Counter(r.get('estimate', {}).get('diagnostics', {}).get('cycle', {}).get('reason') for r in warm))}
    for name, key in [('level_dbfs', 'level'), ('periodicity', 'periodicity')]:
        values = [r['estimate'][key] for r in warm if finite(r.get('estimate', {}).get(key))]
        result[name] = {'min': min(values), 'median': statistics.median(values), 'max': max(values)} if values else None
    if frames:
        row = frames[-1]; e = row['estimate']; d = e.get('diagnostics', {}); c = d.get('cycle', {}); recent = d.get('recent') or {}
        result['latest'] = {'elapsed': row.get('elapsed'), 'phone': e.get('bpm'), 'original': e.get('original'),
                            'cycle': e.get('cycle'), 'watch': row.get('watch', {}).get('bpm'), 'watch_fresh': row.get('watchFresh'),
                            'display': e.get('status'), 'level': e.get('level'), 'periodicity': e.get('periodicity'),
                            'baseline_reason': d.get('periodicity', {}).get('reason'), 'cycle_reason': c.get('reason'),
                            'peaks': len(c.get('peaks', [])), 'cycle_jitter': c.get('jitter'), 'cycle_coverage': c.get('coverage'),
                            'raw_rms': d.get('signal', {}).get('rawRMS'), 'filtered_rms': d.get('signal', {}).get('filteredRMS'),
                            'clipping_fraction': d.get('signal', {}).get('clippingFraction'), 'processing_ms': row.get('processingMS')}
        result['latest'].update(source=d.get('source', 'legacy'), recent_pattern=recent.get('patternBPM'),
                                recent_cycle=recent.get('cycleBPM'), recent_confirmed=recent.get('confirmed'),
                                recent_pattern_reason=recent.get('periodicity', {}).get('reason'), recent_cycle_reason=recent.get('cycle', {}).get('reason'))
    if starts:
        result.update(participant=starts[-1].get('participant'), condition=starts[-1].get('condition'))
    result['neural_reasons'] = dict(collections.Counter((r.get('estimate', {}).get('diagnostics', {}).get('enhanced') or {}).get('reason') for r in warm))
    work = [r['processingMS'] for r in frames if finite(r.get('processingMS'))]
    if work: result['processing_ms'] = {'median': statistics.median(work), 'max': max(work), 'over_500_ms': sum(x > 500 for x in work)}
    if frames:
        enhanced = frames[-1]['estimate'].get('diagnostics', {}).get('enhanced') or {}
        result['latest']['neural'] = {k: enhanced.get(k) for k in ['reason', 'cycleBPM', 'patternBPM', 'rawSupport', 'cleanFraction', 'recentCleanFraction', 'motion', 'analysisAge', 'matchedShare', 'halfScores']}
    result['saved_audio'] = [r.get('audioFile') for r in rows if r.get('event') == 'audio_saved']
    ends = [r for r in active if r.get('event') == 'test_ended']
    if ends: result['ended'] = {'reason': ends[-1].get('message'), 'seconds': ends[-1].get('elapsed')}
    return result


def copy_audio(rows, device, bundle, output):
    """Only retrieve files whose opt-in capture completed; never trust arbitrary log paths."""
    failures = []
    for row in rows:
        name = row.get('audioFile', '')
        if row.get('event') != 'audio_saved' or not re.fullmatch(r'Audio/[0-9A-Fa-f-]{36}\.wav', name):
            continue
        target = output / name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        command = ['xcrun', 'devicectl', 'device', 'copy', 'from', '--device', device,
                   '--source', 'Documents/Diagnostics/' + name, '--domain-type', 'appDataContainer',
                   '--domain-identifier', bundle, '--destination', str(temporary), '--timeout', '20']
        try:
            response = subprocess.run(command, capture_output=True, text=True, timeout=25)
            if response.returncode or not temporary.exists():
                raise RuntimeError((response.stderr or response.stdout).strip()[-300:])
            temporary.replace(target)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            temporary.unlink(missing_ok=True); failures.append({'file': name, 'error': str(error)})
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--bundle', default='app.veritas.heartecho')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--wait', type=float, default=600)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--audio', action='store_true', help='Copy completed opt-in local test audio to this private output directory')
    parser.add_argument('--follow', action='store_true', help='Keep polling after a test ends, allowing retries until --wait expires')
    args = parser.parse_args()
    os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    seen, rows = set(), []
    captured = args.output / 'captured.ndjson'
    if captured.exists():
        for line in captured.read_text().splitlines():
            try: record = json.loads(line)
            except json.JSONDecodeError: continue
            key = (record.get('run'), record.get('sequence'))
            if key not in seen: seen.add(key); rows.append(record)
    began = time.monotonic(); last_new = began; completed = None; errors = 0
    while time.monotonic() - began < args.wait:
        temporary = args.output / 'download.tmp'
        temporary.unlink(missing_ok=True)
        command = ['xcrun', 'devicectl', 'device', 'copy', 'from', '--device', args.device,
                   '--source', 'Documents/Diagnostics/live.ndjson', '--domain-type', 'appDataContainer',
                   '--domain-identifier', args.bundle, '--destination', str(temporary), '--timeout', '10']
        try:
            response = subprocess.run(command, capture_output=True, text=True, timeout=15)
            if response.returncode or not temporary.exists():
                raise RuntimeError((response.stderr or response.stdout).strip()[-500:])
            current = args.output / 'latest.ndjson'; temporary.replace(current)
            fresh = []
            for line in current.read_text().splitlines():
                try: record = json.loads(line)
                except json.JSONDecodeError: continue  # An in-progress final write is retried next poll.
                key = (record.get('run'), record.get('sequence'))
                if key not in seen: seen.add(key); fresh.append(record)
            if fresh:
                last_new = time.monotonic()
                with (args.output / 'captured.ndjson').open('a') as stream:
                    for record in fresh: stream.write(json.dumps(record, separators=(',', ':')) + '\n')
                rows.extend(fresh)
            errors = 0
            result = summary(rows)
            result.update(connection_ok=True, polled_at=time.time(), new_rows=len(fresh), total_rows=len(rows),
                          last_event_age=max(0, time.time() - rows[-1]['time'] / 1000) if rows else None,
                          seconds_without_new_rows=round(time.monotonic() - last_new, 1))
            if args.audio: result['audio_copy_errors'] = copy_audio(rows, args.device, args.bundle, args.output)
            (args.output / 'summary.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result), flush=True)
            if result.get('ended') and completed is None: completed = time.monotonic()
            if args.once or not args.follow and completed is not None and time.monotonic() - completed >= 5: break
            if result.get('test') and not result.get('ended') and time.monotonic() - began > args.wait: break
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            errors += 1
            failure = summary(rows)
            failure.update(connection_ok=False, polled_at=time.time(), connection_error=str(error), consecutive_errors=errors,
                           seconds_without_new_rows=round(time.monotonic() - last_new, 1))
            (args.output / 'summary.json').write_text(json.dumps(failure, indent=2))
            print(json.dumps(failure), flush=True)
            if args.once: raise SystemExit(1)
        time.sleep(max(1, args.interval))
    final = summary(rows)
    print(json.dumps({'final': final, 'output': str(args.output)}), flush=True)
    if not args.once and not final.get('ended'): raise SystemExit(2)


if __name__ == '__main__':
    main()
