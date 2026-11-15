#!/usr/bin/env python3
"""Poll small status snapshots; retrieve closed, permanent run archives once."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

UUID = r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}'


def copy_file(device, bundle, source, target, timeout=12):
    temporary = target.with_suffix(target.suffix + '.download')
    temporary.parent.mkdir(parents=True, exist_ok=True); temporary.unlink(missing_ok=True)
    command = ['xcrun', 'devicectl', 'device', 'copy', 'from', '--device', device, '--domain-type', 'appDataContainer',
               '--domain-identifier', bundle, '--source', source, '--destination', str(temporary), '--timeout', str(timeout)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 5)
    if result.returncode or not temporary.exists():
        temporary.unlink(missing_ok=True)
        raise RuntimeError((result.stderr or result.stdout).strip()[-400:])
    temporary.replace(target); target.chmod(0o600)


def read_rows(path):
    rows = []; incomplete = 0
    for line in path.read_bytes().splitlines():
        try: rows.append(json.loads(line))
        except json.JSONDecodeError: incomplete += 1
    return rows, incomplete


def validate_archive(path, expected):
    rows, incomplete = read_rows(path)
    sequence = [r.get('sequence') for r in rows]
    if incomplete or sequence != list(range(1, len(rows) + 1)) or any(r.get('run') != expected['run'] for r in rows):
        raise ValueError('Archive contains incomplete, missing, reordered, or mixed-run events')
    if not expected.get('error') and (len(rows) != expected['rows'] or path.stat().st_size != expected['bytes']):
        raise ValueError('Archive does not match the closed manifest counts')
    return rows


def merge_rows(path, rows, seen):
    fresh = [r for r in rows if (r['run'], r['sequence']) not in seen]
    with path.open('a') as out:
        for row in fresh:
            key = (row['run'], row['sequence'])
            if key not in seen:
                out.write(json.dumps(row, separators=(',', ':')) + '\n'); seen.add(key)
    return len(fresh)


def collect_archives(device, bundle, output, seen):
    manifest = output / 'manifest.json'
    copy_file(device, bundle, 'Documents/Diagnostics/manifest.json', manifest)
    errors = []; added = 0
    for entry in json.loads(manifest.read_text()):
        if not entry.get('closed'): continue
        name = entry.get('file', '')
        if not re.fullmatch('Runs/' + UUID + r'\.ndjson', name):
            errors.append('Unsafe archive path rejected'); continue
        target = output / name
        try:
            if not target.exists(): copy_file(device, bundle, 'Documents/Diagnostics/' + name, target, 30)
            rows = validate_archive(target, entry)
            added += merge_rows(output / 'captured.ndjson', rows, seen)
        except ValueError as error:
            rejected = output / 'Rejected' / target.name
            rejected.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): target.replace(rejected)
            errors.append({'run': entry['run'], 'error': str(error), 'retained_for_review': str(rejected)})
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            errors.append({'run': entry['run'], 'error': str(error)})
    return added, errors


def collect_audio(device, bundle, output):
    rows, _ = read_rows(output / 'captured.ndjson') if (output / 'captured.ndjson').exists() else ([], 0)
    errors = []
    deleted = {r.get('audioFile') for r in rows if r.get('event') == 'audio_deleted'}
    manifest = output / 'audio-deleted.json'
    try:
        copy_file(device, bundle, 'Documents/Diagnostics/audio-deleted.json', manifest)
        current = json.loads(manifest.read_text())
        if not isinstance(current, list) or not all(isinstance(name, str) and re.fullmatch('Audio/' + UUID + r'\.wav', name) for name in current):
            raise ValueError('Invalid audio deletion manifest')
        deleted.update(current)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        return [{'audio': 'deletion manifest unavailable; skipped audio collection', 'error': str(error)}]
    for name in deleted:
        if isinstance(name, str) and re.fullmatch('Audio/' + UUID + r'\.wav', name): (output / name).unlink(missing_ok=True)
    for row in rows:
        name = row.get('audioFile', '')
        if name in deleted:
            if re.fullmatch('Audio/' + UUID + r'\.wav', name): (output / name).unlink(missing_ok=True)
            continue
        if row.get('event') != 'audio_saved' or not re.fullmatch('Audio/' + UUID + r'\.wav', name): continue
        target = output / name
        if target.exists(): continue
        try: copy_file(device, bundle, 'Documents/Diagnostics/' + name, target, 45)
        except (RuntimeError, subprocess.TimeoutExpired) as error: errors.append({'audio': name, 'error': str(error)})
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True); parser.add_argument('--bundle', default='app.veritas.heartecho')
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--interval', type=float, default=3)
    parser.add_argument('--wait', type=float, default=0, help='Stop after this many seconds; 0 keeps collecting until stopped')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--audio', action='store_true', help='Retrieve explicitly enabled audio after closed archives arrive')
    args = parser.parse_args(); os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    capture = args.output / 'captured.ndjson'; previous, _ = read_rows(capture) if capture.exists() else ([], 0)
    seen = {(r['run'], r['sequence']) for r in previous}; began = time.monotonic(); last_archives = -100; errors = 0
    while args.wait <= 0 or time.monotonic() - began < args.wait:
        report = dict(polled_at=time.time(), connection_ok=False)
        try:
            status_file = args.output / 'status.json'
            copy_file(args.device, args.bundle, 'Documents/Diagnostics/status.json', status_file)
            status = json.loads(status_file.read_text()); report.update(connection_ok=True, status=status, snapshot_age=max(0, time.time() - status['time'] / 1000))
            # Read complete archives, never the active growing log. Audio waits for completion.
            if args.once or time.monotonic() - last_archives >= 25 and status.get('state') != 'recording':
                report['new_events'], report['archive_errors'] = collect_archives(args.device, args.bundle, args.output, seen)
                last_archives = time.monotonic()
                if args.audio: report['audio_errors'] = collect_audio(args.device, args.bundle, args.output)
            report['captured_events'] = len(seen); errors = 0
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
            errors += 1; report.update(connection_ok=False, error=str(error), consecutive_errors=errors)
        summary = args.output / 'summary.json'
        temporary = summary.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n'); temporary.replace(summary)
        print(json.dumps(report), flush=True)
        if args.once: return
        time.sleep(max(1, args.interval))


if __name__ == '__main__': main()
