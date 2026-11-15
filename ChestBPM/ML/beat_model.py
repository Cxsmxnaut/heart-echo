"""Small causal, noise-augmented sound-state model; no personal audio or Watch input.

Targets are CirCor's public semi-supervised sound-state annotations, not diagnoses.
The fixed public test groups are never loaded by training.
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
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parent
BANDS = [(25, 60), (60, 100), (100, 160), (160, 250), (250, 400)]


def features(audio):
    """Eight 100 Hz causal features, mirrored by the iPhone's feature bank."""
    x = signal.lfilter(signal.firwin(41, 400, fs=1000, window='hann'), [1], audio)
    def filtered(low, high):
        y = signal.sosfilt(signal.butter(2, low, btype='highpass', fs=1000, output='sos'), x)
        return signal.sosfilt(signal.butter(2, high, btype='lowpass', fs=1000, output='sos'), y)
    def log_energy(y):
        y = y[:len(y) // 10 * 10]
        return np.log(np.maximum(np.sqrt(np.mean(y.reshape(-1, 10) ** 2, axis=1)), 1e-7))
    broad = log_energy(filtered(25, 400))
    mean = signal.lfilter([.005], [1, -.995], broad, zi=[broad[0] * .995])[0]
    channels = [log_energy(filtered(low, high)) - mean for low, high in BANDS]
    channels += [broad - mean, broad / 8, np.diff(broad, prepend=broad[0])]
    return np.clip(np.stack(channels), -8, 8).astype(np.float32)


class CausalLayer(nn.Module):
    def __init__(self, source, target, dilation):
        super().__init__(); self.padding = dilation * 4
        self.conv = nn.Conv1d(source, target, 5, dilation=dilation)
        self.residual = source == target

    def forward(self, x):
        y = torch.relu(self.conv(F.pad(x, (self.padding, 0))))
        return (y + x) * .70710678 if self.residual else y


class BeatNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(CausalLayer(8, 24, 1), *[CausalLayer(24, 24, d) for d in [2, 4, 8, 16]])
        self.head = nn.Conv1d(24, 5, 1)

    def forward(self, x):
        return self.head(self.layers(x))


def repeat(x, n):
    return np.resize(x, n)


def load_data():
    manifest = json.load(open(ROOT / 'manifest.json'))
    records = [r for r in manifest['records'] if r['split'] == 'development']
    # Validation groups are also separated from training before augmentation.
    order = sorted(records, key=lambda r: hashlib.sha256(('beat-validation:' + r['group']).encode()).hexdigest())
    validation = {r['group'] for r in order[:16]}
    noises = {}
    for name in ['speech', 'babble']:
        x, rate = sf.read(ROOT / ('cache/noise/' + name + '.wav'))
        if x.ndim > 1: x = x[:, 0]
        noises[name] = signal.resample_poly(x, 1000, rate)
    data = {'training': [], 'validation': []}
    rng = np.random.default_rng(71123)
    for i, record in enumerate(records):
        prefix = ROOT / 'cache/circor/training_data' / record['record']
        x, rate = sf.read(str(prefix) + '.wav'); x = signal.resample_poly(x, 1000, rate)[:30000]
        x = x / max(np.max(np.abs(x)), 1e-8) * .3
        annotations = np.loadtxt(str(prefix) + '.tsv', ndmin=2)
        times = (np.arange(len(x) // 10) + .5) * .01 - .02
        labels = np.zeros(len(times), np.int64)
        for start, end, state in annotations:
            labels[(times >= start) & (times < end)] = int(state)
        split = 'validation' if record['group'] in validation else 'training'
        variants = []
        for condition in ['unmodified', 'gain', 'speech', 'babble', 'white', 'hum', 'taps', 'dropout']:
            y = x.copy(); target = labels.copy(); n = len(y); t = np.arange(n) / 1000
            if condition == 'gain':
                y *= np.where((t > 4) & (t < 5.5), .2, 1)
            elif condition in ['speech', 'babble', 'white', 'hum']:
                noise = repeat(noises[condition], n) if condition in noises else rng.normal(0, 1, n) if condition == 'white' else np.sin(2 * np.pi * 50 * t)
                db = float(rng.choice([0, 6, 12]))
                y += noise * np.sqrt(np.mean(x * x) / max(np.mean(noise * noise), 1e-10)) * 10 ** (-db / 20)
            elif condition == 'taps':
                for at in rng.uniform(2, max(2.01, n / 1000 - 1), 3):
                    a, b = int(at * 1000), min(n, int(at * 1000) + 120)
                    y[a:b] += rng.normal(0, .15, b - a) * np.hanning(b - a)
                    target[(times >= at - .1) & (times <= at + .22)] = 0
            elif condition == 'dropout':
                at = float(rng.uniform(2, max(2.01, n / 1000 - 1)))
                y[(t > at) & (t < at + .5)] = 0
                target[(times >= at - .02) & (times <= at + .6)] = 0
            y *= 10 ** float(rng.uniform(-1, .3)); y = np.clip(y, -.95, .95)
            variants.append((features(y), target))
        # Noise-only targets prevent interpreting speech and equipment hum as beats.
        for name in ['speech', 'babble', 'white', 'hum', 'silence']:
            y = repeat(noises[name], len(x)) if name in noises else rng.normal(0, .03, len(x)) if name == 'white' else np.sin(np.arange(len(x)) * np.pi * .1) * .05 if name == 'hum' else np.zeros_like(x)
            variants.append((features(y), np.zeros(len(labels), np.int64)))
        data[split] += variants
        if (i + 1) % 12 == 0: print('Prepared training features', i + 1, '/', len(records), flush=True)
    return data, dict(training_groups=sorted({r['group'] for r in records} - validation), validation_groups=sorted(validation),
                     test_groups=sorted({r['group'] for r in manifest['records'] if r['split'] == 'test'}))


def batch(data, rng, size, device):
    x, y = [], []
    for _ in range(size):
        a, b = data[int(rng.integers(len(data)))]; start = int(rng.integers(0, max(1, a.shape[1] - 200)))
        x.append(a[:, start:start + 200]); y.append(b[start:start + 200])
    return torch.from_numpy(np.stack(x)).to(device), torch.from_numpy(np.stack(y)).to(device)


def train(epochs, steps):
    torch.manual_seed(611); np.random.seed(611); torch.set_num_threads(4)
    data, groups = load_data()
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model = BeatNet().to(device); optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.0001)
    counts = np.bincount(np.concatenate([b for a, b in data['training']]), minlength=5)
    weights = np.sqrt(counts.sum() / np.maximum(counts, 1)); weights /= weights.mean()
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device))
    rng = np.random.default_rng(9171); validation_rng_seed = 4107
    best, history = float('inf'), []
    output = ROOT / 'generated/BeatStates.pt'; output.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(epochs):
        began = time.perf_counter(); model.train(); total = 0
        for _ in range(steps):
            x, y = batch(data['training'], rng, 64, device); optimizer.zero_grad(set_to_none=True)
            logits = model(x); loss = criterion(logits[:, :, 125:], y[:, 125:]); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2); optimizer.step(); total += float(loss.detach().cpu())
        model.eval(); losses = []; confusion = np.zeros((5, 5), np.int64); vrng = np.random.default_rng(validation_rng_seed)
        with torch.inference_mode():
            for _ in range(30):
                x, y = batch(data['validation'], vrng, 64, device); logits = model(x)
                losses.append(float(criterion(logits[:, :, 125:], y[:, 125:]).cpu()))
                truth = y[:, 125:].cpu().numpy().ravel(); predicted = logits[:, :, 125:].argmax(1).cpu().numpy().ravel()
                confusion += np.bincount(truth * 5 + predicted, minlength=25).reshape(5, 5)
        record = dict(epoch=epoch + 1, training_loss=total / steps, validation_loss=float(np.mean(losses)),
                      seconds=time.perf_counter() - began, confusion=confusion.tolist())
        history.append(record); print(json.dumps(record), flush=True)
        if record['validation_loss'] < best:
            best = record['validation_loss']; torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, output)
    report = dict(groups=groups, epochs=epochs, steps_per_epoch=steps, seed=611, device=str(device), history=history,
                  input='Eight causal log-energy filter-bank features, 100 Hz, 2 seconds',
                  target='Public CirCor semi-supervised sound states 0..4; no murmur/AFib diagnosis.',
                  model_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (ROOT / 'results/beat-training.json').write_text(json.dumps(report, indent=2))


def export():
    import coremltools as ct
    model = BeatNet(); model.load_state_dict(torch.load(ROOT / 'generated/BeatStates.pt', map_location='cpu', weights_only=True)); model.eval()
    torch.set_num_threads(1)
    example = torch.randn(1, 8, 200)
    traced = torch.jit.trace(model, example)
    converted = ct.convert(traced, inputs=[ct.TensorType(name='features', shape=(1, 8, 200))],
                           outputs=[ct.TensorType(name='logits')], minimum_deployment_target=ct.target.iOS17,
                           compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM; trained using public CirCor DigiScope annotations'
    converted.short_description = 'Experimental heart-sound timing states. No diagnostic output.'
    converted.user_defined_metadata['feature_schema'] = 'chestbpm-energy-v1'
    converted.user_defined_metadata['weights_sha256'] = hashlib.sha256((ROOT / 'generated/BeatStates.pt').read_bytes()).hexdigest()
    converted.user_defined_metadata['dataset'] = 'https://doi.org/10.13026/tshs-mw03'
    path = ROOT / 'generated/BeatStates.mlpackage'; converted.save(str(path))
    with torch.inference_mode(): expected = model(example).numpy()
    actual = converted.predict({'features': example.numpy()})['logits']
    error = float(np.max(np.abs(actual - expected))); assert error < .001, error
    (ROOT / 'results/beat-conversion.json').write_text(json.dumps(dict(max_absolute_logit_error=error), indent=2))
    print('Native Core ML maximum logit difference:', error, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=30); parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--export-only', action='store_true'); args = parser.parse_args()
    if args.export_only: export()
    else: train(args.epochs, args.steps)
