"""Metadata-only linked-patient reservation for the next sound-model candidate."""
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def reserve():
    rows = list(csv.DictReader((ROOT / 'cache/circor/training_data.csv').open())); parent = {}
    def group(value):
        parent.setdefault(value, value)
        if parent[value] != value: parent[value] = group(parent[value])
        return parent[value]
    for r in rows:
        for other in re.findall(r'\d+', r['Additional ID']):
            a, b = group(r['Patient ID']), group(other); parent[max(a, b)] = min(a, b)
    excluded = set()
    for path in [ROOT / 'manifest.json', ROOT / 'validation-v17-manifest.json']:
        excluded.update(group(r['record'].split('_')[0]) for r in json.loads(path.read_text())['records'])
    for path in (ROOT / 'cache/circor/training_data').iterdir():
        if path.suffix in ['.wav', '.tsv'] and re.fullmatch(r'\d+_[A-Za-z0-9]+', path.stem): excluded.add(group(path.stem.split('_')[0]))
    sums = {r.split(maxsplit=1)[1].lstrip('* ./'): r.split()[0] for r in (ROOT / 'cache/circor/SHA256SUMS.txt').read_text().splitlines()}
    used = set(excluded); selected = []; seed = 'chestbpm-beat-v2-final-patients-18142026'
    for label in ['Absent', 'Present', 'Unknown']:
        count = 0
        for r in sorted((r for r in rows if r['Murmur'] == label), key=lambda r: hashlib.sha256((seed + ':' + group(r['Patient ID'])).encode()).hexdigest()):
            identity = group(r['Patient ID'])
            if identity in used: continue
            locations = r['Recording locations:'].split('+'); location = r['Most audible location'] if r['Most audible location'] in locations else sorted(locations)[0]
            record = r['Patient ID'] + '_' + location; names = ['training_data/' + record + ext for ext in ['.wav', '.tsv']]
            if not all(name in sums for name in names): continue
            assert all(not (ROOT / 'cache/circor' / name).exists() for name in names)
            selected.append(dict(record=record, group=identity, patient_murmur_label=label, files={name: sums[name] for name in names}))
            used.add(identity); count += 1
            if count == 8: break
        assert count == 8
    assert len({r['group'] for r in selected}) == 24 and not excluded.intersection(r['group'] for r in selected)
    output = ROOT / 'beat-v2-holdout.json'
    if output.exists(): raise ValueError('Holdout reservation exists; refusing overwrite')
    output.write_text(json.dumps(dict(seed=seed, excluded_groups=sorted(excluded), records=selected,
        note='Metadata only. Do not download waveforms or annotations until candidate weights, event metrics and sources are frozen. Labels stratify patients; no diagnostic classification is implemented.'), indent=2) + '\n')
    print('Reserved24unseenlinkedpatientgroups; waveforms/annotationsnotdownloaded. Excluded',len(excluded),'previouslyaccessedgroups.')


if __name__ == '__main__': reserve()
