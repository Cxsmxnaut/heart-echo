"""Restore disposable augmented features from frozen sources/profile, without fitting."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import hashlib
import numpy as np

HERE = Path(__file__).resolve().parent
ML = HERE.parent / 'ChestBPM/ML'
sys.path.insert(0, str(ML))
from murmur_native_data import CACHE
from murmur_model import spectrum
from murmur_data import digest
from phone_style import transform, stable_seed


def regenerate(run, role, max_files=0):
    os.umask(0o077)
    run = run.resolve()
    if 'generated' not in run.relative_to(HERE).parts:
        raise ValueError('Expected an ignored research/generated run')
    proof = json.loads((run / 'prepared.json').read_text())
    assert digest(run / 'phone-profile.json') == proof['phone_profile_sha256']
    assert digest(run / 'data.json') == proof['data_sha256']
    profile = json.loads((run / 'phone-profile.json').read_text())
    native = {r['record']: r for r in json.loads((CACHE / 'manifest.json').read_text())['records']}
    count = 0
    for r in json.loads((run / 'data.json').read_text()):
        if max_files and count >= max_files:
            break
        if r['role'] != role:
            continue
        output = run / 'features' / (r['record'] + '.npy')
        if output.exists():
            assert digest(output) == r['styled_features_sha256']
            continue
        path = CACHE / 'audio' / (r['record'] + '.f32')
        assert digest(path) == native[r['record']]['native_audio_sha256']
        wave = np.fromfile(path, dtype='<f4')
        features = spectrum(transform(wave, profile, np.random.default_rng(stable_seed('phone-style:' + r['record']))))
        buffer = io.BytesIO(); np.save(buffer, features)
        assert hashlib.sha256(buffer.getvalue()).hexdigest() == r['styled_features_sha256']
        output.write_bytes(buffer.getvalue()); count += 1
    print(json.dumps({'role': role, 'restored_features': count, 'all_hashes_verified': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--role', choices=['training', 'selection', 'calibration'], required=True)
    parser.add_argument('--max-files', type=int, default=0, help='Bound disk use; 0 restores all missing files')
    args = parser.parse_args(); regenerate(args.run, args.role, args.max_files)
