#!/usr/bin/env python3
"""Compare native audio replays with saved phone decisions and aligned Watch samples."""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import statistics


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def errors(values):
    return dict(count=len(values), mean=statistics.mean(values) if values else None,
                maximum=max(values) if values else None, over5=sum(x > 5 for x in values),
                over10=sum(x > 10 for x in values))


def evaluate(reference, frames):
    recorded = {r['sequence']:r for r in reference['recorded']}
    warm = [r for r in frames if r['input']['raw'] and r['input']['raw'][-1]['index'] >= 599]
    matches, delta = 0, []
    for r in warm:
        old, new = recorded[r['update']['sequence']].get('bpm'), r['estimate'].get('bpm')
        matches += (old is None) == (new is None)
        if finite(old) and finite(new): delta.append(abs(old - new))
    pairs = {}; unmatched = 0
    for p in reference['pairs']:
        if not finite(p.get('watchTime')) or not finite(p.get('time')) or abs(p['time'] - p['watchTime']) > 2000: continue
        closest = min(frames, key=lambda r:abs(r['update']['time'] - (recorded[r['update']['sequence']].get('diagnostics') or {}).get('analysisAge', 0) * 1000 - p['time']))
        original = recorded[closest['update']['sequence']]
        offset = abs(closest['update']['time'] - (original.get('diagnostics') or {}).get('analysisAge', 0) * 1000 - p['time'])
        if offset > 2: unmatched += 1; continue
        if p['watchTime'] not in pairs:
            pairs[p['watchTime']] = dict(watch=p['watch'], recorded=p.get('improved'), replay=closest['estimate'].get('bpm'),
                                         elapsed=closest['update']['elapsed'], sequence=closest['update']['sequence'])
    both = [p for p in pairs.values() if finite(p['recorded']) and finite(p['replay'])]
    gaps=[];begin=None
    for r in warm:
        elapsed=r['update']['elapsed']
        if r['estimate'].get('bpm') is None:
            if begin is None:begin=elapsed
        elif begin is not None:gaps.append(elapsed-begin);begin=None
    if begin is not None:gaps.append(warm[-1]['update']['elapsed']+.5-begin)
    return dict(id=reference['id'], step=reference['step'], cycle=reference['cycle'], condition=reference['condition'], completed=reference['completed'],
                warm_frames=len(warm), recorded_returns=sum(finite(recorded[r['update']['sequence']].get('bpm')) for r in warm),
                replay_returns=sum(finite(r['estimate'].get('bpm')) for r in warm),
                recorded_acceptance_matches=matches, recorded_common_output_delta=errors(delta),
                unique_aligned_watch_samples=len(pairs), unmatched_pairs=unmatched,
                recorded_watch_difference=errors([abs(p['recorded']-p['watch']) for p in pairs.values() if finite(p['recorded'])]),
                replay_watch_difference=errors([abs(p['replay']-p['watch']) for p in pairs.values() if finite(p['replay'])]),
                recorded_common_difference=errors([abs(p['recorded']-p['watch']) for p in both]),
                replay_common_difference=errors([abs(p['replay']-p['watch']) for p in both]),
                reasons=dict(Counter(r['estimate']['reason'] for r in warm)), longest_gap_seconds=max(gaps,default=0), pairs=list(pairs.values()))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate',action='store_true');parser.add_argument('--cycle',type=int)
    parser.add_argument('--production',action='store_true')
    args=parser.parse_args();os.umask(0o077);reports=[]
    for reference in json.loads((args.input/'evaluation-only-references.json').read_text()):
        if args.cycle and reference['cycle'] != args.cycle: continue
        path=args.input/(reference['id']+'.ndjson')
        frames=[json.loads(line) for line in path.open()]
        if args.candidate or args.production:
            candidate={r['update']['sequence']:r for r in map(json.loads,path.with_suffix('.production.ndjson' if args.production else '.candidate.ndjson').open())}
            for frame in frames: frame['estimate']=candidate[frame['update']['sequence']]['estimate']
        report=evaluate(reference,frames);reports.append(report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('pairs','reasons')}),flush=True)
    args.output.write_text(json.dumps(reports,indent=2)+'\n')


if __name__=='__main__':main()
