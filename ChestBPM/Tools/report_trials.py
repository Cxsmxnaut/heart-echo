#!/usr/bin/env python3
"""Summarize private trials without using Watch readings as estimator input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

from poll_diagnostics import finite, summary


def error_stats(values):
    return dict(count=len(values), mean_absolute_error=statistics.mean(values) if values else None,
                maximum_absolute_error=max(values) if values else None, over_5_bpm=sum(v > 5 for v in values))


def analyze(rows):
    reports = []
    for start in [r for r in rows if r.get('event') == 'test_started']:
        trial = [r for r in rows if r.get('test') == start['test']]
        report = summary(trial)
        frames = [r for r in trial if r['event'] == 'estimate' and r['estimate']['seconds'] >= 6]
        pairs = [r['pair'] for r in trial if r['event'] == 'automatic_pair']
        old_errors, common_old, common_new = [], [], []
        for pair in pairs:
            if not frames or not finite(pair.get('watchTime')):
                continue
            closest = min(frames, key=lambda r: abs(r['time'] - pair['watchTime']))
            old = closest['estimate'].get('diagnostics', {}).get('legacyBPM')
            if abs(closest['time'] - pair['watchTime']) > 2000 or not finite(old):
                continue
            error = abs(old - pair['watch']); old_errors.append(error)
            if finite(pair.get('improved')):
                common_old.append(error); common_new.append(abs(pair['improved'] - pair['watch']))
        report.update(started_at=start['time'], previous_app_returned_frames=sum(finite(r['estimate'].get('diagnostics', {}).get('legacyBPM')) for r in frames),
                      previous_app_errors=error_stats(old_errors), same_pair_previous_app_errors=error_stats(common_old), same_pair_new_errors=error_stats(common_new),
                      note='Previous-app comparison uses the closest recorded legacyBPM within 2 seconds of each saved Watch sample. original_errors refers to the original repeating counter, not the previous app main display. Overlapping updates and Watch comparisons are not independent clinical trials.')
        end = next((r['time'] for r in trial if r.get('event') == 'test_ended'), start['time'] + (report.get('ended') or {}).get('seconds', 0) * 1000)
        report['saved_audio'] = [r.get('audioFile') for r in rows if r.get('event') == 'audio_saved' and end <= r['time'] <= end + 8000 and r.get('participant') == start.get('participant') and r.get('condition') == start.get('condition')]
        report['completion_events'] = [r['event'] for r in rows if end <= r['time'] <= end + 8000 and r['event'] in ['audio_stopped', 'logging_disabled', 'audio_saved']]
        report['watch_stop_acknowledged'] = any(end <= r['time'] <= end + 8000 and r.get('event') == 'watch_packet_received' and (r.get('watch') or {}).get('active') is False for r in rows)
        reports.append(report)
    return reports


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('input', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); os.umask(0o077)
    raw = args.input.read_bytes(); seen = set(); rows = []
    for line in raw.splitlines():
        row = json.loads(line); key = (row.get('run'), row.get('sequence'))
        if key not in seen:
            seen.add(key); rows.append(row)
    result = dict(input_sha256=hashlib.sha256(raw).hexdigest(), trials=analyze(rows))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    for r in result['trials']:
        print(json.dumps({k: r.get(k) for k in ['test', 'participant', 'condition', 'warm_frames', 'accepted_frames', 'previous_app_returned_frames', 'improved_errors', 'previous_app_errors', 'same_pair_new_errors', 'ended']}))


if __name__ == '__main__': main()
