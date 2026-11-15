"""Patient-linked CirCor murmur data. Personal recordings are never read."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import re

from prepare_data import fetch

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'murmur-manifest.json'
LABELS = ['Absent', 'Present', 'Unknown']


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value): path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def reserve():
    if MANIFEST.exists(): raise ValueError('Murmur manifest exists; refusing overwrite')
    metadata = fetch('training_data.csv'); sums = fetch('SHA256SUMS.txt')
    rows = list(csv.DictReader(metadata.open())); parent = {}
    def group(x):
        parent.setdefault(x, x)
        if parent[x] != x: parent[x] = group(parent[x])
        return parent[x]
    for row in rows:
        for other in re.findall(r'\d+', row['Additional ID']):
            a, b = group(row['Patient ID']), group(other); parent[max(a, b)] = min(a, b)
    groups = {}
    for row in rows: groups.setdefault(group(row['Patient ID']), []).append(row)
    seen = {group(p.name.split('_')[0]) for p in (ROOT / 'cache/circor/training_data').glob('*.wav')}
    def label(g):
        values = {r['Murmur'] for r in groups[g]}
        return 'Present' if 'Present' in values else 'Unknown' if 'Unknown' in values else 'Absent'
    splits = {g: 'training' for g in groups}
    for split, quotas in [('test', [80, 32, 8]), ('validation', [70, 22, 8])]:
        for name, count in zip(LABELS, quotas):
            candidates = [g for g in groups if label(g) == name and splits[g] == 'training' and (split != 'test' or g not in seen)]
            candidates.sort(key=lambda g: hashlib.sha256(('murmur-v1-21142026:' + split + ':' + g).encode()).hexdigest())
            assert len(candidates) >= count, (split, name, len(candidates))
            for g in candidates[:count]: splits[g] = split
    checksums = {}
    for line in sums.read_text().splitlines():
        value, name = line.split(maxsplit=1); checksums[name.lstrip('* ./')] = value
    by_id = {r['Patient ID']: r for r in rows}; records = []
    for name, checksum in sorted(checksums.items()):
        if not name.startswith('training_data/') or not name.endswith('.wav'): continue
        record = Path(name).stem; patient, location, *_ = record.split('_'); row = by_id[patient]
        label_name = row['Murmur']
        if label_name == 'Present':
            label_name = 'Present' if location in row['Murmur locations'].split('+') else 'Absent'
        records.append(dict(record=record, patient=patient, group=group(patient), location=location,
            split=splits[group(patient)], target=LABELS.index(label_name), patient_target=LABELS.index(row['Murmur']),
            file=name, sha256=checksum))
    assert len(records) == 3163
    assert all(not (ROOT / 'cache/circor' / r['file']).exists() for r in records if r['split'] == 'test')
    save(MANIFEST, dict(dataset='CirCor DigiScope1.0.3', source='https://doi.org/10.13026/tshs-mw03',
        license='Open Data Commons Attribution1.0', labels=LABELS, seed='murmur-v1-21142026',
        metadata_sha256=digest(metadata), published_checksums_sha256=digest(sums),
        previous_audio_groups=sorted(seen), linked_group_splits=splits, records=records,
        note='All linked visits kept together. Present only at annotated murmur locations; Unknown retained. Fresh120group final test excludes all prior audio access. Do not download test before model/source/metrics freeze.'))
    print('Reserved', len(groups), 'linked groups and', len(records), 'recordings; final test remains unread.')


def download(split):
    data = json.loads(MANIFEST.read_text())
    if split == 'test':
        frozen = json.loads((ROOT / 'murmur-freeze.json').read_text())
        for name, expected in frozen['sha256'].items(): assert digest(ROOT.parent.parent / name) == expected, name
    records = [r for r in data['records'] if (r['split'] == 'test') == (split == 'test')]
    def load(r): fetch(r['file'], r['sha256'])
    with concurrent.futures.ThreadPoolExecutor(10) as pool:
        for i, _ in enumerate(pool.map(load, records)):
            if (i + 1) % 200 == 0: print('Verified', i + 1, '/', len(records), flush=True)
    print('Verified all', len(records), split, 'recordings.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=['reserve', 'development', 'test'])
    args = parser.parse_args(); reserve() if args.action == 'reserve' else download(args.action)
