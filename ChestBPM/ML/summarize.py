"""Report every held-out case, including missing references and rejected frames."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(rows, reference_key='reference'):
    frames = [f for r in rows if r['group'] != 'negative' for f in r['frames']]
    eligible = [f for f in frames if f.get(reference_key) is not None]
    result = dict(cases=len(rows), records=len({r['record'] for r in rows if r['group'] != 'negative'}),
                  warm_frames=len(frames), reference_frames=len(eligible), missing_reference_frames=len(frames) - len(eligible))
    for field in ['bpm', 'legacy']:
        errors = [abs(f[field] - f[reference_key]) for f in eligible if f.get(field) is not None]
        result[field] = dict(returned=len(errors), coverage=len(errors) / len(eligible) if eligible else None,
                             mean_absolute_error=statistics.mean(errors) if errors else None,
                             maximum_absolute_error=max(errors) if errors else None, over_5_bpm=sum(e > 5 for e in errors),
                             returned_without_reference=sum(f.get(field) is not None and f.get(reference_key) is None for f in frames))
    negative = [f for r in rows if r['group'] == 'negative' for f in r['frames']]
    result['negative'] = dict(frames=len(negative), returned=sum(f.get('bpm') is not None for f in negative))
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('input', type=Path); parser.add_argument('--output', type=Path)
    parser.add_argument('--reference-field', choices=['reference', 'referenceLatest'], default='reference')
    args = parser.parse_args(); rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    report = dict(reference_field=args.reference_field, overall=summarize(rows, args.reference_field),
                  by_condition={c: summarize([r for r in rows if r['condition'] == c], args.reference_field) for c in sorted({r['condition'] for r in rows})})
    value = json.dumps(report, indent=2)
    if args.output: args.output.write_text(value + '\n')
    print(value)


if __name__ == '__main__': main()
