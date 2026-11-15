"""Research-only sound model: preserve irregular beats, augment contact artifacts.

Same eight-feature/five-state native ABI. Never overwrites the deployed model.
Only the original public80training/16validationgroups enter this experiment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy import signal
import soundfile as sf
import torch
from torch import nn

from beat_model import BeatNet, batch, features, load_data
from event_benchmark import labels_from_annotations, warp_diastole, contact_noise

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'generated/beat-v2'


def data_with_artifacts():
    data, groups = load_data()
    prior = json.loads((ROOT / 'results/beat-training.json').read_text())['groups']
    assert groups['training_groups'] == prior['training_groups'] and groups['validation_groups'] == prior['validation_groups']
    training = set(groups['training_groups']); validation = set(groups['validation_groups'])
    assert not training & validation
    rng = np.random.default_rng(28142026)
    records = json.loads((ROOT / 'manifest.json').read_text())['records']
    for record in records:
        if record['group'] not in training | validation: continue
        prefix = ROOT / 'cache/circor/training_data' / record['record']
        audio, rate = sf.read(str(prefix) + '.wav'); audio = signal.resample_poly(audio, 1000, rate)[:30000]
        audio = audio / max(float(np.max(np.abs(audio))), 1e-8) * .3
        target = labels_from_annotations(np.loadtxt(str(prefix) + '.tsv', ndmin=2), len(audio))
        irregular, warped = warp_diastole(audio, target, rng)
        split = 'training' if record['group'] in training else 'validation'
        for condition in ['irregular', 'clipped', 'contact', 'irregular_contact', 'irregular_clipped', 'contact_only']:
            wave, labels = (irregular.copy(), warped.copy()) if condition.startswith('irregular') else (audio.copy(), target.copy())
            if condition.endswith('clipped'):
                limit = max(float(np.quantile(np.abs(wave), rng.uniform(.85, .97))), 1e-5)
                wave = np.clip(wave, -limit, limit)
            if condition.endswith('contact'):
                snr = float(rng.choice([0, 6, 12])); wave += contact_noise(len(wave), rng) * np.sqrt(np.mean(wave ** 2)) * 10 ** (-snr / 20)
            if condition == 'contact_only': wave = contact_noise(len(wave), rng) * .03; labels = np.zeros(len(wave), dtype=np.int8)
            wave *= 10 ** float(rng.uniform(-1, .3)); wave = np.clip(wave, -.95, .95)
            tensor = features(wave)
            # Same physical feature timestamps as the deployed feature bank.
            indices = np.floor(((np.arange(tensor.shape[1]) + .5) * .01 - .02) * 1000).astype(int)
            y = np.zeros(len(indices), np.int64); good = (indices >= 0) & (indices < len(labels)); y[good] = labels[indices[good]]
            data[split].append((tensor, y))
    return data, groups


def train(epochs=40, steps=100):
    if (OUTPUT / 'BeatStates.pt').exists(): raise ValueError('Research checkpoint exists; refusing to overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protocol = dict(seed=611, epochs=epochs, steps=steps, training_rng=9171, augmentation_rng=28142026,
                    features='Unchangedchestbpm-energy-v1', model='UnchangedBeatNet8->24causalTCN,5soundstates',
                    additional_augmentation=['Diastolic-onlydurationvariation;S1/S2samplesretained', 'Amplitude clipping with true sound-state targets retained',
                                             'Independent synthetic contact noise at0/6/12dBSNR', 'Explicit contact-only negative controls'],
                    diagnosis='No AFib/murmur diagnosis labels; irregularity never makes a positive sound a noise target.',
                    selection='Bestvalidationcrossentropyonly; original80training/16validationgroups, no personaldata, no ECG/Watch inputs.')
    (OUTPUT / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    (OUTPUT / 'source-sha256.json').write_text(json.dumps({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path(__file__), ROOT / 'beat_model.py', ROOT / 'event_benchmark.py', ROOT / 'manifest.json']}, indent=2) + '\n')
    torch.manual_seed(611); np.random.seed(611); torch.set_num_threads(4)
    data, groups = data_with_artifacts()
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model = BeatNet().to(device); optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.0001)
    counts = np.bincount(np.concatenate([y for _, y in data['training']]), minlength=5)
    weights = np.sqrt(counts.sum() / np.maximum(counts, 1)); weights /= weights.mean()
    loss_function = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device))
    rng = np.random.default_rng(9171); best = float('inf'); history = []
    for epoch in range(epochs):
        began = time.perf_counter(); model.train(); total = 0
        for _ in range(steps):
            x, y = batch(data['training'], rng, 64, device); optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(x)[:, :, 125:], y[:, 125:]); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 2)
            optimizer.step(); total += float(loss.detach().cpu())
        model.eval(); losses = []; confusion = np.zeros((5, 5), np.int64); validation_rng = np.random.default_rng(4107)
        with torch.inference_mode():
            for _ in range(30):
                x, y = batch(data['validation'], validation_rng, 64, device); logits = model(x)
                losses.append(float(loss_function(logits[:, :, 125:], y[:, 125:]).cpu()))
                truth = y[:, 125:].cpu().numpy().ravel(); predicted = logits[:, :, 125:].argmax(1).cpu().numpy().ravel()
                confusion += np.bincount(truth * 5 + predicted, minlength=25).reshape(5, 5)
        row = dict(epoch=epoch + 1, training_loss=total / steps, validation_loss=float(np.mean(losses)),
                   seconds=time.perf_counter() - began, confusion=confusion.tolist())
        history.append(row); print(json.dumps(row), flush=True)
        if row['validation_loss'] < best:
            best = row['validation_loss']; torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, OUTPUT / 'BeatStates.pt')
        (OUTPUT / 'training.json').write_text(json.dumps(dict(protocol=protocol, groups=groups, history=history, device=str(device)), indent=2))
    export()


def export():
    import coremltools as ct
    torch.set_num_threads(1); torch.manual_seed(1814)
    model = BeatNet(); model.load_state_dict(torch.load(OUTPUT / 'BeatStates.pt', map_location='cpu', weights_only=True)); model.eval()
    example = torch.randn(1, 8, 200); traced = torch.jit.trace(model, example)
    converted = ct.convert(traced, inputs=[ct.TensorType(name='features', shape=(1, 8, 200))], outputs=[ct.TensorType(name='logits')],
                           minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM; public CirCor sound-state research'
    converted.short_description = 'Experimental sound-state candidate; no diagnostic outputs.'
    converted.user_defined_metadata['feature_schema'] = 'chestbpm-energy-v1'
    converted.user_defined_metadata['weights_sha256'] = hashlib.sha256((OUTPUT / 'BeatStates.pt').read_bytes()).hexdigest()
    converted.user_defined_metadata['dataset'] = 'https://doi.org/10.13026/tshs-mw03'
    converted.save(str(OUTPUT / 'BeatStates.mlpackage'))
    errors = []
    for _ in range(8):
        x = torch.randn(1, 8, 200)
        with torch.inference_mode(): expected = model(x).numpy()
        actual = converted.predict({'features': x.numpy()})['logits']; errors.append(float(np.max(np.abs(actual - expected))))
    assert max(errors) < .001, errors
    (OUTPUT / 'conversion.json').write_text(json.dumps(dict(maximum_logit_error=max(errors), examples=len(errors)), indent=2) + '\n')
    print('Nativeconversionpassed; researchcandidateonly:', max(errors), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--epochs', type=int, default=40)
    parser.add_argument('--steps', type=int, default=100); parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args(); export() if args.export_only else train(args.epochs, args.steps)
