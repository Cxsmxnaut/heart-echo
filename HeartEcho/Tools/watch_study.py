#!/usr/bin/env python3
"""Watch existing collector files and save private, continuously refreshed analytics."""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import statistics
import time

from poll_diagnostics import finite
from report_trials import analyze


def atomic_json(path, value):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def analytics(rows, study):
    rows = [r for r in rows if r.get('study') == study]
    reports = analyze(rows)
    grouped = defaultdict(list)
    for report in reports:
        trial = [r for r in rows if r.get('test') == report['test']]
        start = next(r for r in trial if r.get('event') == 'test_started')
        warm = [r for r in trial if r.get('event') == 'estimate' and r['estimate'].get('seconds', 0) >= 6]
        pairs = {}
        for row in trial:
            p = row.get('pair') or {}
            if (row.get('event') == 'automatic_pair' and finite(p.get('time')) and finite(p.get('watchTime'))
                    and abs(p['time'] - p['watchTime']) <= 2000 and finite(p.get('improved'))
                    and finite(p.get('watch'))):
                pairs.setdefault(p['watchTime'], p)
        errors = [abs(p['improved'] - p['watch']) for p in pairs.values()]
        accepted = sum(finite(r['estimate'].get('bpm')) for r in warm)
        report.update(step=start.get('step'), cycle=start.get('cycle'),
                      accepted_frame_fraction=accepted / len(warm) if warm else None,
                      rejected_frame_count=len(warm) - accepted,
                      unique_aligned_watch_samples=len(errors),
                      unique_sample_mean_absolute_error=statistics.mean(errors) if errors else None,
                      unique_sample_maximum_absolute_error=max(errors) if errors else None,
                      off_chest_accepted_frames=accepted if start.get('condition') == 'Off chest' else None,
                      completed=(report.get('ended') or {}).get('reason') == 'timed_test_complete')
        if report['completed']: grouped[report['condition']].append(report)
    conditions = {}
    for condition, trials in grouped.items():
        warm = sum(r['warm_frames'] for r in trials)
        conditions[condition] = dict(completed_trials=len(trials), warm_frames=warm,
                                     accepted_frames=sum(r['accepted_frames'] for r in trials),
                                     accepted_frame_fraction=sum(r['accepted_frames'] for r in trials) / warm if warm else None,
                                     trial_mean_absolute_errors=[r['unique_sample_mean_absolute_error'] for r in trials])
    return dict(study=study, generated_at=time.time(), archived_events=len(rows), trials=reports,
                completed_steps=sorted({r['step'] for r in reports if r['completed'] and r.get('step')}),
                conditions=conditions,
                note='Closed archives only. Acceptance is a fraction of overlapping estimate updates, not independent beats. Watch agreement uses unique Watch timestamps aligned within 2 seconds; Watch is a comparison sensor, not clinical ground truth. Aborted attempts remain separate and are excluded from completed-condition totals.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args(); os.umask(0o077)
    folder = args.input; plan = json.loads((folder / 'study-state.json').read_text()); study = plan['id']
    total_tests = max(1, min(5, int(plan.get('repetitions') or 5))) * 4
    signature = None; report = {}; last_notice = None; last_key = None
    while True:
        try:
            summary = json.loads((folder / 'summary.json').read_text())
            status = summary.get('status') or json.loads((folder / 'status.json').read_text())
            connected = summary.get('connection_ok') and time.time() - summary.get('polled_at', 0) < 20
            key = (status.get('run'), status.get('sequence'))
            if key != last_key and status.get('study') == study:
                with (folder / 'monitor-snapshots.ndjson').open('a') as stream:
                    stream.write(json.dumps(dict(observed_at=time.time(), status=status)) + '\n')
                last_key = key
            capture = folder / 'captured.ndjson'; stat = capture.stat()
            current = (stat.st_size, stat.st_mtime_ns)
            if current != signature:
                seen = set(); rows = []
                for line in capture.read_text().splitlines():
                    try: row = json.loads(line)
                    except ValueError: continue
                    identity = (row.get('run'), row.get('sequence'))
                    if identity not in seen: rows.append(row); seen.add(identity)
                report = analytics(rows, study)
                atomic_json(folder / 'live-analytics.json', report)
                signature = current
            health = dict(time=time.time(), connected=bool(connected),
                          poll_age=round(time.time() - summary.get('polled_at', 0), 1),
                          status={k:status.get(k) for k in ('test','step','cycle','state','remaining','phoneBPM','watchBPM','watchTime','time','sequence','error')},
                          archived_completed_steps=report.get('completed_steps', []),
                          conditions=report.get('conditions', {}), error=summary.get('error'),
                          archive_errors=summary.get('archive_errors', []))
            atomic_json(folder / 'monitor-health.json', health)
            notice = (bool(connected), status.get('test'), status.get('step'), status.get('state'), signature)
            if notice != last_notice:
                print(json.dumps(health), flush=True); last_notice = notice
            if len(report.get('completed_steps', [])) == total_tests:
                print(f'COMPLETE: all {total_tests} completed trial archives retrieved and analyzed.', flush=True); return
        except (OSError, ValueError) as error:
            print(json.dumps(dict(time=time.time(), monitor_error=str(error))), flush=True)
        time.sleep(5)


if __name__ == '__main__': main()
