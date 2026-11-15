"""Small murmur classifier with a waveform-to-spectrum frontend exported inside Core ML.

Three research sound labels, not valve diagnoses. Test audio is never read by training.
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

from murmur_data import ROOT, MANIFEST, digest, save

OUTPUT = ROOT / 'generated/murmur-v1'
RATE, SAMPLES, NFFT, HOP, BINS = 2000, 8000, 256, 40, 32
FRAMES = (SAMPLES - NFFT) // HOP + 1


def banks():
    window = np.hanning(NFFT + 1)[:-1]
    phase = 2 * np.pi * np.arange(NFFT // 2 + 1)[:, None] * np.arange(NFFT)[None, :] / NFFT
    fourier = np.concatenate([np.cos(phase), -np.sin(phase)]) * window
    hz_to_mel = lambda x: 2595 * np.log10(1 + x / 700)
    edges = 700 * (10 ** (np.linspace(hz_to_mel(25), hz_to_mel(950), BINS + 2) / 2595) - 1)
    hz = np.arange(NFFT // 2 + 1) * RATE / NFFT
    mel = np.stack([np.maximum(0, np.minimum((hz - a) / (b - a), (c - hz) / (c - b))) for a, b, c in zip(edges, edges[1:], edges[2:])])
    return fourier.astype(np.float32), mel.astype(np.float32), window


def spectrum(audio):
    _, mel, window = banks()
    frames = np.lib.stride_tricks.sliding_window_view(audio, NFFT)[::HOP]
    power = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    return np.log(np.maximum(np.einsum('bf,tf->bt', mel, power, optimize=False), 1e-10)).astype(np.float32)


class Frontend(nn.Module):
    def __init__(self):
        super().__init__(); fourier, mel, _ = banks()
        self.register_buffer('fourier', torch.from_numpy(fourier[:, None, :]))
        self.register_buffer('mel', torch.from_numpy(mel[:, :, None]))

    def forward(self, x):
        parts = nn.functional.conv1d(x, self.fourier, stride=HOP)
        power = parts[:, :129] ** 2 + parts[:, 129:] ** 2
        return torch.log(nn.functional.conv1d(power, self.mel).clamp_min(1e-10))


class MurmurNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(nn.Conv1d(BINS, 48, 5, padding=2), nn.ReLU(),
            nn.Conv1d(48, 64, 5, padding=4, dilation=2), nn.ReLU(),
            nn.Conv1d(64, 64, 5, padding=8, dilation=4), nn.ReLU(),
            nn.Conv1d(64, 64, 5, padding=16, dilation=8), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Dropout(.25), nn.Linear(64, 3))

    def forward(self, x):
        mean = x.mean(dim=(1, 2), keepdim=True)
        x = (x - mean) / ((x - mean).square().mean(dim=(1, 2), keepdim=True) + 1).sqrt()
        x = self.layers(x)
        return self.head(torch.cat([x.mean(dim=2), x.amax(dim=2)], dim=1))


class WaveModel(nn.Module):
    def __init__(self, classifier):
        super().__init__(); self.front = Frontend(); self.classifier = classifier

    def forward(self, waveform): return torch.softmax(self.classifier(self.front(waveform)), dim=1)


def load_audio(record):
    path = ROOT / 'cache/circor' / record['file']; assert digest(path) == record['sha256']
    info = sf.info(path); x, rate = sf.read(path, frames=int(info.samplerate * 60)); assert x.ndim == 1 and np.all(np.isfinite(x))
    return signal.resample_poly(x, RATE, rate).astype(np.float32)


def windows(length):
    if length < SAMPLES: return []
    last = (length - SAMPLES) // HOP * HOP
    return sorted(set(list(range(0, last + 1, SAMPLES)) + [last]))


def feature_data():
    records = [r for r in json.loads(MANIFEST.read_text())['records'] if r['split'] != 'test']
    cache = OUTPUT / 'features'; cache.mkdir(parents=True, exist_ok=True); data = []
    for i, r in enumerate(records):
        info = sf.info(ROOT / 'cache/circor' / r['file'])
        r = dict(r, sample_count=int(np.ceil(min(info.frames, info.samplerate * 60) * RATE / info.samplerate)))
        path = cache / (r['record'] + '.npy')
        if path.exists(): a = np.load(path)
        else: a = spectrum(load_audio(r)); np.save(path, a)
        assert a.shape[1] >= FRAMES
        data.append((r, a))
        if (i + 1) % 400 == 0: print('Prepared', i + 1, '/', len(records), flush=True)
    return data


def predict_record(model, features, device, length):
    starts = [s // HOP for s in windows(length)]
    x = np.stack([features[:, s:s + FRAMES] for s in starts])
    with torch.inference_mode(): return torch.softmax(model(torch.from_numpy(x).to(device)), dim=1).cpu().numpy().mean(axis=0)


def decision(probabilities, threshold=.6):
    index = int(np.argmax(probabilities))
    return index if index != 2 and float(probabilities[index]) >= threshold else 2


def metrics(truth, predictions):
    matrix = np.zeros((3, 3), dtype=int)
    for a, b in zip(truth, predictions): matrix[int(a), int(b)] += 1
    recall = np.diag(matrix) / np.maximum(matrix.sum(axis=1), 1)
    return dict(confusion_true_rows=matrix.tolist(), balanced_recall=float(recall.mean()),
        recall=recall.tolist(), accuracy=float(np.trace(matrix) / max(matrix.sum(), 1)),
        known_positive_cases=int(matrix[1].sum()), missed_positive_as_absent=int(matrix[1, 0]),
        positive_unsure=int(matrix[1, 2]), known_negative_cases=int(matrix[0].sum()),
        false_alarms=int(matrix[0, 1]), negative_unsure=int(matrix[0, 2]),
        decisive_sensitivity=float(matrix[1, 1] / max(matrix[1].sum(), 1)),
        decisive_specificity=float(matrix[0, 0] / max(matrix[0].sum(), 1)),
        unsure=int(matrix[:, 2].sum()), total=int(matrix.sum()))


def train(epochs=24, steps=100):
    if (OUTPUT / 'Murmur.pt').exists(): raise ValueError('Checkpoint exists; refusing overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True); torch.manual_seed(2114); np.random.seed(2114); torch.set_num_threads(4)
    save(OUTPUT / 'protocol.json', dict(seed=2114, epochs=epochs, steps=steps, batch=48,
        model='32logmelbins25..950Hz,4seconds,temporalCNN,3soundlabels',
        selection='Maximum validation record balanced recall, fixed0.60decisive threshold; no test access.',
        note='Unknown murmur annotations are uncertain, not healthy or definitively noise. Synthetic artifact examples are additional uncertain targets. No personal data.'))
    save(OUTPUT / 'training-sources.json', {p.name: digest(p) for p in [Path(__file__), ROOT / 'murmur_data.py', MANIFEST]})
    data = feature_data(); training = [(r, x) for r, x in data if r['split'] == 'training']; validation = [(r, x) for r, x in data if r['split'] == 'validation']
    pools = [[x for r, x in training if r['target'] == c] for c in range(3)]
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu'); model = MurmurNet().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0005, weight_decay=.001); rng = np.random.default_rng(2114); history = []; best = -1
    noises = []
    for name in ['speech', 'babble']:
        path = ROOT / 'cache/noise' / (name + '.wav')
        if path.exists():
            x, rate = sf.read(path); x = x[:, 0] if x.ndim > 1 else x
            noises.append(spectrum(signal.resample_poly(x, RATE, rate)))
    for epoch in range(epochs):
        began = time.perf_counter(); model.train(); losses = []
        for _ in range(steps):
            xs, ys = [], []
            for j in range(48):
                target = j % 3; a = pools[target][int(rng.integers(len(pools[target])))]; start = int(rng.integers(a.shape[1] - FRAMES + 1)); x = a[:, start:start + FRAMES].copy()
                # Gentle feature perturbations preserve the murmur target; known pure artifacts use Unknown.
                x += rng.uniform(-2, 2); x += rng.normal(0, .12, x.shape)
                if rng.random() < .25:
                    f = int(rng.integers(BINS - 3)); x[f:f + 3] = x.mean()
                if j >= 42:
                    target = 2
                    if noises and j % 2:
                        a = noises[int(rng.integers(len(noises)))]; s = int(rng.integers(max(1, a.shape[1] - FRAMES + 1))); x = np.resize(a[:, s:s + FRAMES], (BINS, FRAMES)).copy()
                    else: x = spectrum(rng.normal(0, .03, SAMPLES).astype(np.float32))
                xs.append(x); ys.append(target)
            x = torch.from_numpy(np.stack(xs).astype(np.float32)).to(device); y = torch.tensor(ys, device=device)
            optimizer.zero_grad(set_to_none=True); loss = nn.functional.cross_entropy(model(x), y)
            loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 2); optimizer.step(); losses.append(float(loss.detach().cpu()))
        model.eval(); probs = [predict_record(model, x, device, r['sample_count']) for r, x in validation]
        result = metrics([r['target'] for r, _ in validation], [decision(x) for x in probs])
        row = dict(epoch=epoch + 1, loss=float(np.mean(losses)), seconds=time.perf_counter() - began, validation=result)
        history.append(row); print(json.dumps(row), flush=True)
        if result['balanced_recall'] > best:
            best = result['balanced_recall']; torch.save({k: v.cpu() for k, v in model.state_dict().items()}, OUTPUT / 'Murmur.pt')
        save(OUTPUT / 'training.json', dict(history=history, device=str(device)))
    export()


def export():
    import coremltools as ct
    torch.set_num_threads(1); torch.manual_seed(2114)
    classifier = MurmurNet(); classifier.load_state_dict(torch.load(OUTPUT / 'Murmur.pt', weights_only=True)); classifier.eval(); model = WaveModel(classifier).eval()
    converted = ct.convert(torch.jit.trace(model, torch.randn(1, 1, SAMPLES) * .03),
        inputs=[ct.TensorType(name='waveform', shape=(1, 1, SAMPLES))], outputs=[ct.TensorType(name='probabilities')],
        minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM; trained from scratch on public CirCor audio'
    converted.short_description = 'Experimental murmur sound labels on four-second 2kHz audio; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1', labels='Absent,Present,Unknown',
        dataset='https://doi.org/10.13026/tshs-mw03', weights_sha256=digest(OUTPUT / 'Murmur.pt'))
    converted.save(str(OUTPUT / 'Murmur.mlpackage')); errors = []
    for scale in [0, .0001, .01, .3]:
        x = torch.randn(1, 1, SAMPLES) * scale
        with torch.inference_mode(): expected = model(x).numpy()
        actual = converted.predict({'waveform': x.numpy()})['probabilities']; errors.append(float(np.max(np.abs(expected - actual))))
    assert max(errors) < .001, errors
    save(OUTPUT / 'conversion.json', dict(maximum_probability_difference=max(errors), examples=len(errors)))
    print('Native waveform conversion passed:', max(errors), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--epochs', type=int, default=24); p.add_argument('--steps', type=int, default=100); p.add_argument('--export-only', action='store_true'); a = p.parse_args()
    export() if a.export_only else train(a.epochs, a.steps)
