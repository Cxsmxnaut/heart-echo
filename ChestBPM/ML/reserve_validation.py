"""Reserve a reproducible public cohort disjoint from every previously used patient group.

Selection reads metadata only. Download after freezing the final algorithm, never while tuning.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

from prepare_data import ROOT, fetch


def reserve(per_label=4):
    rows = list(csv.DictReader((ROOT / 'cache/circor/training_data.csv').open()))
    parent = {}

    def group(value):
        parent.setdefault(value, value)
        if parent[value] != value: parent[value] = group(parent[value])
        return parent[value]

    for row in rows:
        for other in re.findall(r'\d+', row['Additional ID']):
            a, b = group(row['Patient ID']), group(other)
            parent[max(a, b)] = min(a, b)
    prior = json.loads((ROOT / 'manifest.json').read_text())
    excluded = {group(r['record'].split('_')[0]) for r in prior['records']}
    used = set(excluded); checksums = {}
    for line in (ROOT / 'cache/circor/SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split(maxsplit=1); checksums[name.lstrip('* ./')] = digest
    records = []; seed = 'chestbpm-v17-public-validation-v1'
    for label in ['Absent', 'Present', 'Unknown']:
        count = 0
        candidates = sorted((r for r in rows if r['Murmur'] == label),
                            key=lambda r: hashlib.sha256((seed + ':' + group(r['Patient ID'])).encode()).hexdigest())
        for row in candidates:
            identity = group(row['Patient ID'])
            if identity in used: continue
            locations = row['Recording locations:'].split('+')
            location = row['Most audible location'] if row['Most audible location'] in locations else sorted(locations)[0]
            record = row['Patient ID'] + '_' + location
            if not re.fullmatch(r'\d+_[A-Za-z0-9]+', record): raise ValueError('Unsafe public record identifier')
            names = ['training_data/' + record + extension for extension in ['.wav', '.tsv']]
            if not all(name in checksums for name in names): continue
            used.add(identity); count += 1
            records.append(dict(record=record, group=identity, split='validation_v17', patient_murmur_label=label,
                                files={name: checksums[name] for name in names}))
            if count == per_label: break
        if count != per_label: raise ValueError('Insufficient new linked-patient groups for ' + label)
    assert not excluded.intersection(r['group'] for r in records)
    return dict(dataset=prior['dataset'], license=prior['license'], citation=prior['citation'], base=prior['base'],
                selection_seed=seed, excluded_groups=sorted(excluded), records=records,
                note='Metadata-only reservation. Download/evaluate only after source and model freeze. Public patient labels stratify selection; no disease classification is implemented. Noise mixtures reuse known sources and do not constitute unseen-noise validation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'validation-v17-manifest.json')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--freeze', type=Path)
    args = parser.parse_args(); manifest = reserve()
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        if previous['records'] != manifest['records']: raise ValueError('Refusing to replace an existing cohort with different patients')
    args.output.write_text(json.dumps(manifest, indent=2) + '\n')
    if args.download:
        if not args.freeze: raise ValueError('Download requires an explicit final source/model freeze')
        freeze = json.loads(args.freeze.read_text())
        for name, digest in freeze['sha256'].items():
            if hashlib.sha256((ROOT.parent.parent / name).read_bytes()).hexdigest() != digest:
                raise ValueError('Source/model changed after freeze: ' + name)
        for record in manifest['records']:
            for name, digest in record['files'].items(): fetch(name, digest)
    print('Reserved', len(manifest['records']), 'new linked-patient groups;', 'downloaded with source freeze verified' if args.download else 'waveforms and annotations untouched')


if __name__ == '__main__': main()
