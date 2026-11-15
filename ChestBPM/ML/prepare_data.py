"""Fetch a fixed, patient-grouped public CirCor benchmark; no personal recordings."""
import concurrent.futures
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = 'https://physionet.org/files/circor-heart-sound/1.0.3/'


def fetch(relative, checksum=None):
    path = ROOT / 'cache/circor' / relative
    if not path.exists() or checksum and hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        for attempt in range(5):
            try:
                data = urllib.request.urlopen(BASE + relative, timeout=30).read()
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        if checksum and hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError('Published checksum mismatch: ' + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--development-per-label', type=int, default=32)
    parser.add_argument('--additional-test-per-label', type=int, default=4)
    args = parser.parse_args()
    old = json.loads((ROOT / 'manifest.json').read_text()) if (ROOT / 'manifest.json').exists() else None
    for name in ['training_data.csv', 'SHA256SUMS.txt', 'LICENSE.txt']:
        fetch(name)
    checksums = {}
    for line in (ROOT / 'cache/circor/SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        checksums[name.lstrip('* ./')] = digest
    rows = list(csv.DictReader((ROOT / 'cache/circor/training_data.csv').open()))
    parent = {}

    def group(value):
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = group(parent[value])
        return parent[value]

    for row in rows:
        subject = row['Patient ID']
        for other in re.findall(r'\d+', row['Additional ID']):
            a, b = group(subject), group(other)
            parent[max(a, b)] = min(a, b)
    selected, used = [], set()
    for label in ['Absent', 'Present', 'Unknown']:
        candidates = sorted((r for r in rows if r['Murmur'] == label),
                            key=lambda r: hashlib.sha256(('chestbpm-noise-v1:' + group(r['Patient ID'])).encode()).hexdigest())
        count = 0
        for row in candidates:
            patient, location = row['Patient ID'], row['Most audible location']
            identity = group(patient)
            if identity in used:
                continue
            used.add(identity)
            if location not in row['Recording locations:'].split('+'):
                location = sorted(row['Recording locations:'].split('+'))[0]
            record = patient + '_' + location
            names = ['training_data/' + record + extension for extension in ['.wav', '.tsv']]
            if not all(name in checksums for name in names):
                continue
            selected.append(dict(record=record, group=identity, split='development' if count < 4 else 'test',
                                 patient_murmur_label=label, files={name: checksums[name] for name in names}))
            count += 1
            if count == 8:
                break
        if count != 8:
            raise ValueError('Insufficient fixed records for ' + label)
    # Expand training/development only. The original twelve test groups stay frozen.
    for label in ['Absent', 'Present', 'Unknown']:
        count = sum(r['split'] == 'development' and r['patient_murmur_label'] == label for r in selected)
        candidates = sorted((r for r in rows if r['Murmur'] == label),
                            key=lambda r: hashlib.sha256(('chestbpm-noise-v1:' + group(r['Patient ID'])).encode()).hexdigest())
        for row in candidates:
            if count >= args.development_per_label:
                break
            identity = group(row['Patient ID'])
            if identity in used:
                continue
            location = row['Most audible location']
            if location not in row['Recording locations:'].split('+'):
                location = sorted(row['Recording locations:'].split('+'))[0]
            record = row['Patient ID'] + '_' + location
            names = ['training_data/' + record + extension for extension in ['.wav', '.tsv']]
            if not all(name in checksums for name in names):
                continue
            used.add(identity); count += 1
            selected.append(dict(record=record, group=identity, split='development', patient_murmur_label=label,
                                 files={name: checksums[name] for name in names}))
        if count < args.development_per_label:
            raise ValueError('Insufficient additional development groups')
    # A second untouched test cohort is reserved after identifying a mask recovery bug.
    # The first cohort remains unchanged and is reported separately.
    for label in ['Absent', 'Present', 'Unknown']:
        count = 0
        candidates = sorted((r for r in rows if r['Murmur'] == label),
                            key=lambda r: hashlib.sha256(('chestbpm-final-test-v1:' + group(r['Patient ID'])).encode()).hexdigest())
        for row in candidates:
            if count >= args.additional_test_per_label: break
            identity = group(row['Patient ID'])
            if identity in used: continue
            location = row['Most audible location']
            if location not in row['Recording locations:'].split('+'):
                location = sorted(row['Recording locations:'].split('+'))[0]
            record = row['Patient ID'] + '_' + location
            names = ['training_data/' + record + extension for extension in ['.wav', '.tsv']]
            if not all(name in checksums for name in names): continue
            used.add(identity); count += 1
            selected.append(dict(record=record, group=identity, split='final_test', patient_murmur_label=label,
                                 files={name: checksums[name] for name in names}))
        if count != args.additional_test_per_label: raise ValueError('Insufficient final test groups')
    if old:
        assert {r['group'] for r in old['records'] if r['split'] == 'test'} == {r['group'] for r in selected if r['split'] == 'test'}
    manifest = dict(dataset='CirCor DigiScope 1.0.3', license='Open Data Commons Attribution License v1.0',
                    citation='https://doi.org/10.13026/tshs-mw03', base=BASE,
                    note='Patient-linked groups separated before noise mixtures. No claim of independence from a pretrained model’s historical data.',
                    records=selected)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    jobs = [(name, digest) for record in selected for name, digest in record['files'].items()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for path in executor.map(lambda job: fetch(*job), jobs):
            print(path.name, flush=True)
    print('Prepared', len(selected), 'patient-grouped public recordings.', flush=True)


if __name__ == '__main__':
    main()
