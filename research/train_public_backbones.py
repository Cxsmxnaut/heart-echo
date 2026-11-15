"""Substantial public-only CNN6/ResNet18 training; portable to a Kaggle GPU.

Input configuration MUST contain only public training/selection records. No phone
profile, private recording, calibration/test record, or credential is accepted.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.request
import zipfile

import numpy as np
from scipy import signal
import soundfile as sf
import torch
from torch.nn import functional as F

from two_stage_models import make_clinical, spectra, sha, HERE, WEIGHTS, WEIGHT_SHA
from murmur_focus_metrics import aggregate


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def download(url, path, expected):
    path = Path(path)
    if path.exists() and sha(path) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.download')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as target:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    target.write(block)
            assert sha(temporary) == expected, 'Public source checksum mismatch'
            temporary.replace(path)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def starts(count):
    if count < 8000:
        return []
    return sorted(set(list(range(0, (count - 8000) // 40 * 40 + 1, 8000))
                      + [(count - 8000) // 40 * 40]))


def usable(x):
    offsets = np.arange(0, len(x) - 8000 + 1, 40)
    energy = np.r_[0., np.cumsum(x.astype(np.float64) ** 2)]
    clipped = np.r_[0, np.cumsum(np.abs(x) >= .999)]
    valid = ((energy[offsets + 8000] - energy[offsets]) / 8000 >= .00002 ** 2)
    valid &= (clipped[offsets + 8000] - clipped[offsets]) / 8000 <= .01
    return np.flatnonzero(valid).tolist()


def prepare(config, folder):
    rows = config['records']
    groups = {}
    for r in rows:
        assert r['role'] in ('training', 'selection')
        assert groups.setdefault(r['group'], r['role']) == r['role']
        assert Path(r['file']).parts[0] == 'training_data' and '..' not in Path(r['file']).parts
    def read(record):
        path = folder / record['file']
        download('https://physionet.org/files/circor-heart-sound/1.0.3/' + record['file'], path, record['sha256'])
        info = sf.info(path)
        x, rate = sf.read(path, frames=int(info.samplerate * 60), dtype='float32')
        assert x.ndim == 1 and np.all(np.isfinite(x))
        divisor = math.gcd(rate, 2000)
        x = signal.resample_poly(x, 2000 // divisor, rate // divisor).astype(np.float32)
        return dict(record, samples=len(x), usable=usable(x), x=spectra(x)[0])
    data = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for index, record in enumerate(pool.map(read, rows), 1):
            data.append(record)
            if index % 200 == 0:
                print(json.dumps({'public_records_prepared': index, 'total': len(rows)}), flush=True)
    return data


def predict(model, records, device):
    model.eval(); chunks, owners = [], []
    sums = np.zeros((len(records), 3)); count = np.zeros(len(records))
    for i, r in enumerate(records):
        valid = set(r['usable'])
        for offset in starts(r['samples']):
            frame = offset // 40
            if frame in valid:
                chunks.append(r['x'][:, frame:frame + 194]); owners.append(i)
    with torch.inference_mode():
        for index in range(0, len(chunks), 64):
            x = torch.from_numpy(np.stack(chunks[index:index + 64])).to(device)
            probabilities = model(x).softmax(1).cpu().numpy()
            for owner, p in zip(owners[index:index + 64], probabilities):
                sums[owner] += p; count[owner] += 1
    values = {}
    for i, r in enumerate(records):
        p = sums[i] / count[i] if count[i] else np.array([0., 0., 1.])
        best = int(np.argmax(p)); label = best if p[best] >= .60 else 2
        values[r['record']] = {'reading': {'finding': ['absent', 'present', 'unsure'][label], 'probabilities': p.tolist()}}
    return aggregate(records, values), values


def score(result):
    matrix = np.asarray(result['recordings']['matrix'])
    return float(np.mean(np.diag(matrix) / np.maximum(matrix.sum(1), 1)))


def batch(rng, pools, controls):
    xs, ys = [], []
    for label in [0] * 12 + [1] * 12 + [2] * 4:
        record = pools[label][int(rng.integers(len(pools[label])))]
        frame = record['usable'][int(rng.integers(len(record['usable'])))]
        x = record['x'][:, frame:frame + 194].copy()
        x += rng.uniform(-.5, .5)
        x += np.linspace(-1, 1, 64, dtype=np.float32)[:, None] * rng.uniform(-.35, .35)
        if rng.random() < .25:
            offset = int(rng.integers(60)); x[offset:offset + 4] = x.mean()
        if rng.random() < .25:
            offset = int(rng.integers(186)); x[:, offset:offset + 8] = x.mean()
        xs.append(x); ys.append(label)
    for _ in range(4):
        xs.append(controls[int(rng.integers(len(controls)))]); ys.append(2)
    return np.stack(xs), np.asarray(ys)


def train(config_path, output, max_epochs=40, steps=120):
    os.umask(0o077); output = Path(output)
    if output.exists():
        raise ValueError('Preserve previous training output; choose a fresh directory')
    output.mkdir(parents=True)
    config = json.loads(Path(config_path).read_text())
    assert config['public_only'] is True and config['private_audio_included'] is False
    assert all(r['role'] in ['training', 'selection'] for r in config['records'])
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
    torch.set_num_threads(2)
    if device.type == 'cuda':
        torch.backends.cudnn.benchmark = True
    protocol = dict(seed=20261117, max_epochs=max_epochs, steps_per_epoch=steps, batch=32,
                    warm_head_epochs=2, evaluation_every_epochs=2,
                    early_stop='After at least12epochs, stop after6 selection checks without improvement.',
                    learning='AdamW backbone1e-4/head3e-4, head-only warmup1e-3; cosine decay; weight_decay.01; label_smoothing.05',
                    sampling='12Absent/12Present/4expertUnknown/4syntheticUnknown; mild spectral/time masks.',
                    selection='Maximum three-class balanced recall on public selection only; no threshold tuning.',
                    threshold=.60, models=['panns-cnn6', 'resnet18'],
                    preprocessing='Full public WAV, at most60s, Scipy polyphase resample2k; 64 mel bands25..950Hz, FFT256/hop40,4s windows. Native-reader comparison is a separate local check.',
                    private_audio_included=False, private_phone_profile_included=False,
                    calibration_or_test_included=False, config_sha256=sha(config_path),
                    source_sha256={name: sha(HERE / name) for name in ['two_stage_models.py', 'train_public_backbones.py', 'murmur_focus_metrics.py']},
                    environment={'torch': torch.__version__, 'device': str(device),
                                 'gpu': torch.cuda.get_device_name(0) if device.type == 'cuda' else None},
                    limitations=['Selection is reused development; no independent accuracy estimate.',
                                 'Architectures adapted to heart spectrograms; not reproduction of a published score.'])
    save(output / 'protocol.json', protocol)
    download('https://zenodo.org/records/3987831/files/Cnn6_mAP%3D0.343.pth?download=1', WEIGHTS, WEIGHT_SHA)
    download('https://download.pytorch.org/models/resnet18-f37072fd.pth',
             HERE / 'cache/resnet-review/resnet18-f37072fd.pth',
             'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec')
    data = prepare(config, HERE / 'public-data')
    training = [r for r in data if r['role'] == 'training' and r['usable']]
    selection = [r for r in data if r['role'] == 'selection']
    pools = [[r for r in training if r['target'] == label] for label in [0, 1, 2]]
    rng = np.random.default_rng(2026111701)
    controls = spectra(rng.normal(0, .01, (64, 8000)).astype(np.float32))
    completed = {}
    for name in protocol['models']:
        directory = output / name; directory.mkdir()
        torch.manual_seed(protocol['seed'])
        if device.type == 'cuda':
            torch.cuda.manual_seed_all(protocol['seed'])
        rng = np.random.default_rng(protocol['seed'])
        model = make_clinical(name, pretrained=True)
        parameter_names = set(dict(model.named_parameters()))
        initial = {k: v.detach().clone() for k, v in model.state_dict().items()}
        model.to(device)
        head = list(model.classifier.parameters()); head_ids = {id(p) for p in head}
        body = [p for p in model.parameters() if id(p) not in head_ids]
        optimizer = torch.optim.AdamW([{'params': body, 'lr': 1e-4}, {'params': head, 'lr': 3e-4}], weight_decay=.01)
        scaler = torch.amp.GradScaler('cuda', enabled=device.type == 'cuda')
        history, best, stale = [], -1., 0
        for epoch in range(1, max_epochs + 1):
            began = time.perf_counter(); model.train(); losses = []
            for parameter in body:
                parameter.requires_grad_(epoch > 2)
            factor = .05 + .95 * .5 * (1 + math.cos(math.pi * max(0, epoch - 3) / max(1, max_epochs - 3)))
            optimizer.param_groups[0]['lr'] = 1e-4 * factor
            optimizer.param_groups[1]['lr'] = 1e-3 if epoch <= 2 else 3e-4 * factor
            for _ in range(steps):
                x, y = batch(rng, pools, controls)
                x = torch.from_numpy(x).to(device); y = torch.from_numpy(y).to(device)
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == 'cuda'):
                    loss = F.cross_entropy(model(x), y, label_smoothing=.05)
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite source training loss')
                scaler.scale(loss).backward(); scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 2.)
                scaler.step(optimizer); scaler.update(); losses.append(float(loss.detach().cpu()))
            row = dict(epoch=epoch, optimizer_steps=epoch * steps, loss=float(np.mean(losses)),
                       seconds=time.perf_counter() - began)
            if epoch % 2 == 0:
                result, predictions = predict(model, selection, device); value = score(result)
                row.update(selection_balanced_recall=value, selection=result['recordings'])
                if value > best:
                    best = value; stale = 0
                    temporary = directory / 'best.pending'
                    torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, temporary)
                    temporary.replace(directory / 'Clinical.pt')
                    save(directory / 'selected.json', dict(epoch=epoch, score=value, metrics=result))
                    save(directory / 'selection-predictions.json', predictions)
                else:
                    stale += 1
            history.append(row); save(directory / 'history.json', history)
            print(json.dumps({'model': name, **row}), flush=True)
            if epoch >= 12 and stale >= 6:
                break
        selected = torch.load(directory / 'Clinical.pt', map_location='cpu', weights_only=True)
        changed = [k for k in parameter_names if not torch.equal(initial[k], selected[k])]
        backbone_changed = [k for k in changed if not k.startswith('classifier.')]
        assert backbone_changed and all(torch.isfinite(v).all() for v in selected.values())
        proof = dict(epochs_run=len(history), optimizer_steps_run=len(history) * steps,
                     selected_epoch=json.loads((directory / 'selected.json').read_text())['epoch'],
                     changed_parameter_tensors=len(changed), changed_backbone_parameter_tensors=len(backbone_changed),
                     all_finite=True, weights_sha256=sha(directory / 'Clinical.pt'),
                     private_data_used=False, calibration_or_test_loaded=False)
        save(directory / 'training-proof.json', proof); completed[name] = proof
        del model, optimizer, initial, selected
        if device.type == 'cuda':
            torch.cuda.empty_cache()
        elif device.type == 'mps':
            torch.mps.empty_cache()
    save(output / 'complete.json', dict(status='source_training_complete', models=completed,
                                       protocol_sha256=sha(output / 'protocol.json')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=40)
    parser.add_argument('--steps', type=int, default=120)
    args = parser.parse_args()
    try:
        train(args.config, args.output, args.epochs, args.steps)
    finally:
        if args.output.exists():
            with zipfile.ZipFile(args.output.parent / 'heart-public-source-stage.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in args.output.rglob('*'):
                    if path.is_file():
                        archive.write(path, str(path.relative_to(args.output.parent)))
