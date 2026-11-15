"""Joint phase and weak murmur timing candidate, isolated from frozen A/v1."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from murmur_model import ROOT, Frontend, MurmurNet, FRAMES, SAMPLES, BINS, feature_data, predict_record, metrics, decision, spectrum
from murmur_phase_model import PhaseMurmurNet
from murmur_phase_data import PHASE_MANIFEST
from murmur_timing_data import timing_targets
from murmur_data import digest, save

OUTPUT = ROOT / 'generated/murmur-phase-c'


class TimingMurmurNet(PhaseMurmurNet):
    def __init__(self):
        super().__init__()
        self.context = nn.Conv1d(64, 64, 5, padding=32, dilation=16)
        nn.init.zeros_(self.context.weight); nn.init.zeros_(self.context.bias)
        self.murmur = nn.Conv1d(64, 1, 1)
        self.timing_head = nn.Sequential(nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 3))
        nn.init.zeros_(self.timing_head[-1].weight); nn.init.zeros_(self.timing_head[-1].bias)

    def joint(self, x):
        mean = x.mean(dim=(1, 2), keepdim=True)
        x = (x - mean) / ((x - mean).square().mean(dim=(1, 2), keepdim=True) + 1).sqrt()
        h = self.layers(x); h = h + self.context(h)
        phase = self.phase(h); weights = phase.softmax(1)[:, 1:]
        denominator = weights.sum(2).clamp_min(1e-6)
        contexts = (h[:, None] * weights[:, :, None]).sum(3) / denominator[:, :, None]
        murmur = self.murmur(h)
        strength = murmur.sigmoid() * weights
        timing = torch.cat([strength.sum(2) / denominator, strength.amax(2)], 1)
        logits = self.head(torch.cat([h.mean(2), h.amax(2)], 1)) + self.phase_head(contexts.flatten(1)) + self.timing_head(timing)
        return logits, phase, murmur[:, 0]

    def forward(self, x): return self.joint(x)[0]


class WaveTimingModel(nn.Module):
    def __init__(self, model):
        super().__init__(); self.front = Frontend(); self.classifier = model

    def forward(self, waveform):
        logits, phase, murmur = self.classifier.joint(self.front(waveform))
        return logits.softmax(1), phase.softmax(1), murmur.sigmoid()


def train(epochs=24, steps=100):
    if (OUTPUT / 'Murmur.pt').exists(): raise ValueError('Candidate C exists; refusing overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True); torch.manual_seed(3414); torch.set_num_threads(4)
    for name in ['murmur-freeze.json', 'murmur-phase-a-freeze.json']:
        for path, expected in json.loads((ROOT / name).read_text())['sha256'].items():
            assert digest(ROOT.parent.parent / path) == expected
    protocol = dict(seed=3414, epochs=epochs, steps=steps, learning_rate=.0001, warm_epochs=3,
        losses='recordCE +.25phaseCE +.5weakTimingBCE(posweight2) +.2originalTeacherKL(temp2)',
        initialization='Frozen candidateA; zero context and timing residuals initially preserve A logits.',
        timing='Approximate public early/mid/late/holo timing; positive S1/S2 and unknown labels masked. Not dense expert murmur labels.',
        selection='Against original v1 at fixed.60: maximize selection50 positive recall then balancedrecall, with FPrate<=v1+.02, unsure<=v1+.05 and positive-asAbsent<=v1+.02. No oldtest access. Calibration already used during architecture development; not independent validation.')
    save(OUTPUT / 'protocol.json', protocol)
    save(OUTPUT / 'training-sources.json', {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT / 'murmur_timing_data.py', PHASE_MANIFEST]})
    records = {r['record']: r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['split'] != 'test'}
    data = []
    for r, x in feature_data():
        record = dict(records[r['record']], sample_count=r['sample_count'])
        q, t = timing_targets(record, x.shape[1]); data.append((record, x, q, t))
    pools = [[item for item in data if item[0]['role'] == 'training' and item[0]['target'] == c] for c in range(3)]
    selection = [item for item in data if item[0]['role'] == 'selection']
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    teacher = MurmurNet(); teacher.load_state_dict(torch.load(ROOT / 'generated/murmur-v1/Murmur.pt', weights_only=True)); teacher.to(device).eval()
    for p in teacher.parameters(): p.requires_grad_(False)
    model = TimingMurmurNet(); model.load_state_dict(torch.load(ROOT / 'generated/murmur-phase-a/Murmur.pt', weights_only=True), strict=False); model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0001, weight_decay=.001)
    rng = np.random.default_rng(3414); history = []; best = (-1., -1.)
    truth = [r['target'] for r, _, _, _ in selection]
    reference = metrics(truth, [decision(predict_record(teacher, x, device, r['sample_count'])) for r, x, _, _ in selection])
    def rates(m): return np.array([m['false_alarms'] / m['known_negative_cases'], m['unsure'] / m['total'], m['missed_positive_as_absent'] / m['known_positive_cases']])
    noises = []
    import soundfile as sf
    from scipy.signal import resample_poly
    for name in ['speech', 'babble']:
        path = ROOT / 'cache/noise' / (name + '.wav')
        if path.exists():
            audio, rate = sf.read(path); audio = audio[:, 0] if audio.ndim > 1 else audio
            audio = resample_poly(audio, 2000, rate)
            if len(audio) < SAMPLES: audio = np.tile(audio, int(np.ceil(SAMPLES / len(audio))))
            noises.append(spectrum(audio))
    for epoch in range(epochs + 1):
        began = time.perf_counter(); model.train(); losses = []
        for p in model.layers.parameters(): p.requires_grad_(epoch > 3)
        for p in model.head.parameters(): p.requires_grad_(epoch > 3)
        for _ in range(steps if epoch else 0):
            xs, ys, qs, ts = [], [], [], []
            for j in range(48):
                y = j % 3; _, x, q, t = pools[y][int(rng.integers(len(pools[y])))]; start = int(rng.integers(x.shape[1] - FRAMES + 1))
                a = x[:, start:start + FRAMES].copy(); q = q[start:start + FRAMES].copy(); t = t[start:start + FRAMES].copy()
                a += rng.uniform(-2, 2); a += rng.normal(0, .12, a.shape)
                if rng.random() < .25:
                    f = int(rng.integers(BINS - 3)); a[f:f + 3] = a.mean()
                if j >= 42:
                    y = 2; q = np.zeros(FRAMES, dtype=np.int64); t = np.zeros(FRAMES, dtype=np.float32)
                    if noises and j % 2:
                        noise = noises[int(rng.integers(len(noises)))]; k = int(rng.integers(noise.shape[1] - FRAMES + 1)); a = noise[:, k:k + FRAMES].copy()
                    else: a = spectrum(rng.normal(0, .03, SAMPLES).astype(np.float32))
                xs.append(a); ys.append(y); qs.append(q); ts.append(t)
            x = torch.from_numpy(np.stack(xs).astype(np.float32)).to(device); y = torch.tensor(ys, device=device)
            q = torch.from_numpy(np.stack(qs)).to(device); t = torch.from_numpy(np.stack(ts)).to(device)
            optimizer.zero_grad(set_to_none=True); logits, phase, timing = model.joint(x)
            ce = F.cross_entropy(logits, y); ph = F.cross_entropy(phase, q, weight=torch.tensor([1., 2., 1., 2., 1.], device=device), ignore_index=-100)
            mask = t != -100; weak = F.binary_cross_entropy_with_logits(timing[mask], t[mask], pos_weight=torch.tensor(2., device=device))
            with torch.no_grad(): original = teacher(x[:42])
            kl = F.kl_div(F.log_softmax(logits[:42] / 2, 1), F.softmax(original / 2, 1), reduction='batchmean') * 4
            loss = ce + .25 * ph + .5 * weak + .2 * kl; loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 2); optimizer.step()
            losses.append([float(v.detach().cpu()) for v in [ce, ph, weak, kl]])
        model.eval(); result = metrics(truth, [decision(predict_record(model, x, device, r['sample_count'])) for r, x, _, _ in selection])
        eligible = bool(np.all(rates(result) <= rates(reference) + [.02, .05, .02] + np.array([1e-12] * 3)))
        score = (result['decisive_sensitivity'], result['balanced_recall'])
        row = dict(epoch=epoch, selection=result, eligible=eligible, seconds=time.perf_counter() - began, losses=np.mean(losses, 0).tolist() if losses else None)
        history.append(row); print(json.dumps(row), flush=True)
        if eligible and score > best:
            best = score; torch.save({k: v.cpu() for k, v in model.state_dict().items()}, OUTPUT / 'Murmur.pt')
        save(OUTPUT / 'training.json', dict(protocol=protocol, baseline=reference, history=history, device=str(device)))
    export()


def export():
    import coremltools as ct
    torch.set_num_threads(1); torch.manual_seed(3414)
    model = TimingMurmurNet(); model.load_state_dict(torch.load(OUTPUT / 'Murmur.pt', weights_only=True)); model = WaveTimingModel(model).eval()
    names = ['probabilities', 'phase_probabilities', 'murmur_timing']
    converted = ct.convert(torch.jit.trace(model, torch.randn(1, 1, SAMPLES) * .03), inputs=[ct.TensorType(name='waveform', shape=(1, 1, SAMPLES))], outputs=[ct.TensorType(name=n) for n in names], minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM public-data research'; converted.short_description = 'Joint phase and weak murmur timing model; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1', labels='Absent,Present,Unknown', phase_labels='noise,S1,systole,S2,diastole', dataset='https://doi.org/10.13026/tshs-mw03', weights_sha256=digest(OUTPUT / 'Murmur.pt'))
    converted.save(str(OUTPUT / 'Murmur.mlpackage')); errors = []
    for scale in [0, .0001, .01, .3]:
        x = torch.randn(1, 1, SAMPLES) * scale
        with torch.inference_mode(): expected = model(x)
        actual = converted.predict({'waveform': x.numpy()}); errors.append([float(np.max(np.abs(v.numpy() - actual[n]))) for v, n in zip(expected, names)])
    assert np.max(errors) < .001, errors
    save(OUTPUT / 'conversion.json', dict(maximum_probability_differences=np.max(errors, 0).tolist(), examples=4)); print('Native timing conversion passed', errors, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--export-only', action='store_true'); a = p.parse_args()
    export() if a.export_only else train()
