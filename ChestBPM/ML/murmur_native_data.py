"""Public development audio through the unchanged shipping AVAudioConverter."""
import json
from pathlib import Path
import subprocess
import numpy as np
from murmur_model import ROOT, spectrum, SAMPLES, HOP, windows, FRAMES, decision, metrics
from murmur_data import digest, save
from murmur_phase_data import PHASE_MANIFEST, targets

CACHE = ROOT / 'generated/murmur-native-development'


def prepare():
    if (CACHE / 'manifest.json').exists(): raise ValueError('Native cache exists; refusing overwrite')
    CACHE.mkdir(parents=True, exist_ok=True)
    records = [r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role'] != 'test']
    requests = []
    for r in records:
        path = ROOT / 'cache/circor' / r['file']; assert digest(path) == r['sha256']
        requests.append(dict(id=r['record'], path=str(path.resolve())))
    save(CACHE / 'requests.json', requests)
    binary = Path('/tmp/chestbpm-murmur-audio-export')
    with (CACHE / 'audio-export.ndjson').open('w') as out:
        subprocess.run([str(binary), str(CACHE / 'requests.json'), str(CACHE / 'audio')], stdout=out, check=True)
    exported = {r['id']: r for r in map(json.loads, (CACHE / 'audio-export.ndjson').open())}
    assert set(exported) == {r['record'] for r in records}
    features = CACHE / 'features'; features.mkdir(exist_ok=True); provenance = []
    for i, r in enumerate(records):
        item = exported[r['record']]; raw = CACHE / 'audio' / item['file']; x = np.fromfile(raw, dtype='<f4')
        assert x.shape == (item['samples'],) and np.all(np.isfinite(x))
        output = features / (r['record'] + '.npy'); np.save(output, spectrum(x))
        starts = np.arange(0, len(x) - SAMPLES + 1, HOP)
        energy = np.r_[0., np.cumsum(x.astype(np.float64) ** 2)]
        clipped = np.r_[0, np.cumsum(np.abs(x) >= .999)]
        usable = ((energy[starts + SAMPLES] - energy[starts]) / SAMPLES >= .00002 ** 2) & ((clipped[starts + SAMPLES] - clipped[starts]) / SAMPLES <= .01)
        provenance.append(dict(record=r['record'], samples=len(x), usable_frame_starts=np.flatnonzero(usable).tolist(), source_sha256=r['sha256'], native_audio_sha256=digest(raw), features_sha256=digest(output)))
        if (i + 1) % 400 == 0: print('Native development features', i + 1, '/', len(records), flush=True)
    save(CACHE / 'manifest.json', dict(records=provenance, phase_manifest_sha256=digest(PHASE_MANIFEST),
        converter_binary_sha256=digest(binary), source_sha256=digest(Path(__file__)),
        swift_source_sha256=digest(ROOT.parent / 'Tools/MurmurAudioExport.swift'),
        native_reader_sha256=digest(ROOT.parent / 'ChestBPM/MurmurAnalysis.swift'),
        note='All2723public development recordings only. Shipping native reader with cap60seconds; little-endianfloat32. Original test and private audio never read.'))
    print('Verified native development feature cache complete.', flush=True)


def load_development():
    manifest = json.loads((CACHE / 'manifest.json').read_text()); assert manifest['phase_manifest_sha256'] == digest(PHASE_MANIFEST)
    records = {r['record']: r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role'] != 'test'}
    assert {r['record'] for r in manifest['records']} == set(records)
    result = []
    for item in manifest['records']:
        r = dict(records[item['record']], sample_count=item['samples'], usable_frame_starts=item['usable_frame_starts']); path = CACHE / 'features' / (r['record'] + '.npy')
        assert digest(path) == item['features_sha256']; x = np.load(path)
        result.append((r, x, targets(r, x.shape[1])))
    return result


def predict_native_record(model, record, features, device):
    import torch
    usable = set(record['usable_frame_starts'])
    starts = [s // HOP for s in windows(record['sample_count']) if s // HOP in usable]
    if not starts: return np.array([0., 0., 1.])
    x = np.stack([features[:, s:s + FRAMES] for s in starts])
    with torch.inference_mode(): return model(torch.from_numpy(x).to(device)).softmax(1).cpu().numpy().mean(0)


if __name__ == '__main__': prepare()
