#!/usr/bin/env python3
"""Prepare private, audio-only native replay inputs; references stay in evaluation files."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); os.umask(0o077); args.output.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in (args.input / 'captured.ndjson').read_text().splitlines()]
    study = json.loads((args.input / 'study-state.json').read_text())['id']
    rows = [r for r in rows if r.get('study') == study]
    starts = [r for r in rows if r.get('event') == 'test_started']
    requests, references = [], []
    for start in starts:
        trial = [r for r in rows if r.get('test') == start['test']]
        audio = next((r for r in trial if r.get('event') == 'audio_saved'), None)
        if not audio: continue
        path = args.input / audio['audioFile']
        frames = [r for r in trial if r.get('event') == 'estimate']
        identifier = f"step-{start['step']:02d}-{start['test']}"
        updates = [dict(sequence=r['sequence'], samples=r['estimate']['diagnostics']['signal']['totalSamples'],
                        time=r['time'], elapsed=r['elapsed'], motion=(r['estimate']['diagnostics'].get('enhanced') or {}).get('motion', 0)) for r in frames]
        requests.append(dict(id=identifier, path=str(path.resolve()), output=str((args.output / (identifier + '.ndjson')).resolve()), updates=updates))
        references.append(dict(id=identifier, step=start['step'], cycle=start['cycle'], condition=start['condition'],
                               test=start['test'], completed=any(r.get('event') == 'test_ended' and r.get('message') == 'timed_test_complete' for r in trial),
                               source_audio_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               pairs=[r['pair'] for r in trial if r.get('event') == 'automatic_pair'],
                               recorded=[dict(sequence=r['sequence'], bpm=r['estimate'].get('bpm'), diagnostics=r['estimate']['diagnostics'].get('enhanced')) for r in frames]))
    (args.output / 'audio-only-requests.json').write_text(json.dumps(requests))
    (args.output / 'evaluation-only-references.json').write_text(json.dumps(references))
    (args.output / 'limitations.txt').write_text('Saved PCM16 audio is quantized from the live microphone floats. Estimate boundaries follow logged sample counts. Motion is the logged maximum per update, applied to that update; exact 20ms motion history was not saved. Replay baseline must be compared with recorded decisions before relying on improvements. References are evaluation only. All saved study cycles are development/regression evidence: their summary outcomes have already been inspected. Two new physical cycles are reserved for prospective validation after the final code freeze.\n')
    print(f'Prepared {len(requests)} recordings. Watch references excluded from native replay inputs.')


if __name__ == '__main__': main()
