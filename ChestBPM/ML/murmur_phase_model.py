"""Phase-supervised murmur candidate; preserves the frozen baseline and waveform ABI."""
import argparse
import copy
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from murmur_model import (ROOT, Frontend, MurmurNet, FRAMES, SAMPLES, BINS,
                          feature_data, predict_record, metrics, decision, spectrum)
from murmur_data import digest, save
from murmur_phase_data import PHASE_MANIFEST, targets

OUTPUT = ROOT / 'generated/murmur-phase-a'


class PhaseMurmurNet(nn.Module):
    def __init__(self, baseline=None):
        super().__init__(); baseline = baseline or MurmurNet()
        self.layers = copy.deepcopy(baseline.layers); self.head = copy.deepcopy(baseline.head)
        self.phase = nn.Conv1d(64, 5, 1)
        self.phase_head = nn.Sequential(nn.Linear(256, 64), nn.ReLU(), nn.Dropout(.25), nn.Linear(64, 3))
        nn.init.zeros_(self.phase_head[-1].weight); nn.init.zeros_(self.phase_head[-1].bias)

    def outputs(self, x):
        mean = x.mean(dim=(1, 2), keepdim=True)
        x = (x - mean) / ((x - mean).square().mean(dim=(1, 2), keepdim=True) + 1).sqrt()
        h = self.layers(x); phase = self.phase(h); weights = torch.softmax(phase, dim=1)[:, 1:]
        contexts = (h[:, None] * weights[:, :, None]).sum(dim=3) / weights.sum(dim=2, keepdim=True).clamp_min(1e-6)
        global_features = torch.cat([h.mean(dim=2), h.amax(dim=2)], dim=1)
        logits = self.head(global_features) + self.phase_head(contexts.flatten(1))
        return logits, phase

    def forward(self, x): return self.outputs(x)[0]


class WavePhaseModel(nn.Module):
    def __init__(self, classifier):
        super().__init__(); self.front = Frontend(); self.classifier = classifier

    def forward(self, waveform):
        logits, phase = self.classifier.outputs(self.front(waveform))
        return torch.softmax(logits, dim=1), torch.softmax(phase, dim=1)


def load_development():
    records = {r['record']: r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['split'] != 'test'}
    result = []
    for r, x in feature_data():
        record = dict(records[r['record']], sample_count=r['sample_count'])
        result.append((record, x, targets(record, x.shape[1])))
    return result


def train(epochs=24, steps=100):
    if (OUTPUT / 'Murmur.pt').exists(): raise ValueError('Phase candidate exists; refusing overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True); torch.manual_seed(2414); np.random.seed(2414); torch.set_num_threads(4)
    baseline_path = ROOT / 'generated/murmur-v1/Murmur.pt'
    frozen = json.loads((ROOT / 'murmur-freeze.json').read_text())
    assert digest(baseline_path) == frozen['sha256']['ChestBPM/ML/generated/murmur-v1/Murmur.pt']
    protocol = dict(seed=2414, epochs=epochs, steps=steps, batch=48, learning_rate=.00015,
        warm_phase_epochs=3, phase_loss_weight=.5, teacher_kl_weight=.2, teacher_temperature=2,
        selection='Maximum positive recall, then balanced recall, among selection50group checkpoints with falsealarm<=baseline+0.02,unsure<=baseline+0.05,positive-as-absent<=baseline+0.02. Fixed0.60decision; originalepoch0included. Calibration50groupsnotusedforcheckpointchoice.',
        architecture='Original learned temporal backbone/global murmur head plus explicit5statephasehead and phase-conditioned residual murmur pooling; residual startszero.',
        phase_supervision='S1/systole/S2/diastole from publishedTSV; unknown0 masked. Pure synthetic noise phase0. No BPM regularity filtering.',
        baseline_sha256=digest(baseline_path), data='Original652traininggroups only; no private data, no oldtestdata for training or selection.')
    save(OUTPUT / 'protocol.json', protocol)
    save(OUTPUT / 'training-sources.json', {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT / 'murmur_phase_data.py', ROOT / 'murmur_model.py', PHASE_MANIFEST]})
    data = load_development(); train_data = [x for x in data if x[0]['role'] == 'training']; selection = [x for x in data if x[0]['role'] == 'selection']
    pools = [[(x, y) for r, x, y in train_data if r['target'] == c] for c in range(3)]
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    teacher = MurmurNet(); teacher.load_state_dict(torch.load(baseline_path, weights_only=True)); teacher = teacher.to(device).eval()
    for p in teacher.parameters(): p.requires_grad_(False)
    model = PhaseMurmurNet(teacher).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.00015, weight_decay=.001)
    rng = np.random.default_rng(2414); history = []; best = (-1, -1); baseline_metrics = None
    weights = torch.tensor([1., 2., 1., 2., 1.], device=device)
    for epoch in range(epochs + 1):
        began = time.perf_counter(); losses = []; model.train()
        for p in model.layers.parameters(): p.requires_grad_(epoch > protocol['warm_phase_epochs'])
        for p in model.head.parameters(): p.requires_grad_(epoch > protocol['warm_phase_epochs'])
        for _ in range(steps if epoch else 0):
            xs, ys, phases = [], [], []
            for j in range(48):
                target = j % 3; x, phase = pools[target][int(rng.integers(len(pools[target])))]; start = int(rng.integers(x.shape[1] - FRAMES + 1))
                a = x[:, start:start + FRAMES].copy(); q = phase[start:start + FRAMES].copy()
                a += rng.uniform(-2, 2); a += rng.normal(0, .12, a.shape)
                if rng.random() < .25:
                    f = int(rng.integers(BINS - 3)); a[f:f + 3] = a.mean()
                if j >= 42:
                    target = 2; a = spectrum(rng.normal(0, .03, SAMPLES).astype(np.float32)); q = np.zeros(FRAMES, dtype=np.int64)
                xs.append(a); ys.append(target); phases.append(q)
            x = torch.from_numpy(np.stack(xs).astype(np.float32)).to(device); y = torch.tensor(ys, device=device); q = torch.from_numpy(np.stack(phases)).to(device)
            optimizer.zero_grad(set_to_none=True); logits, predicted_phase = model.outputs(x)
            supervised = F.cross_entropy(logits, y); phase_loss = F.cross_entropy(predicted_phase, q, weight=weights, ignore_index=-100)
            with torch.no_grad(): reference = teacher(x[:42])
            kl = F.kl_div(F.log_softmax(logits[:42] / 2, dim=1), F.softmax(reference / 2, dim=1), reduction='batchmean') * 4
            loss = supervised + .5 * phase_loss + .2 * kl
            loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 2); optimizer.step()
            losses.append([float(supervised.detach().cpu()), float(phase_loss.detach().cpu()), float(kl.detach().cpu())])
        model.eval(); predictions = []; truth = []; phase_matrix = np.zeros((5, 5), dtype=int)
        with torch.inference_mode():
            for r, x, q in selection:
                probabilities = predict_record(model, x, device, r['sample_count']); predictions.append(decision(probabilities)); truth.append(r['target'])
                # One fixed first window per record scores annotated phase frames without time duplication.
                phase = model.outputs(torch.from_numpy(x[:, :FRAMES])[None].to(device))[1].argmax(1).cpu().numpy()[0]
                known = q[:FRAMES] != -100
                phase_matrix += np.bincount(q[:FRAMES][known] * 5 + phase[known], minlength=25).reshape(5, 5)
        result = metrics(truth, predictions)
        if baseline_metrics is None: baseline_metrics = result
        def rates(m):
            return (m['false_alarms'] / max(m['known_negative_cases'], 1),
                    m['unsure'] / max(m['total'], 1),
                    m['missed_positive_as_absent'] / max(m['known_positive_cases'], 1))
        current, original = rates(result), rates(baseline_metrics)
        eligible = all(a <= b + tolerance + 1e-12 for a, b, tolerance in zip(current, original, [.02, .05, .02]))
        score = (result['decisive_sensitivity'], result['balanced_recall'])
        row = dict(epoch=epoch, losses=np.mean(losses, axis=0).tolist() if losses else None, selection=result,
                   eligible=eligible, phase_confusion=phase_matrix.tolist(), seconds=time.perf_counter() - began)
        history.append(row); print(json.dumps(row), flush=True)
        if eligible and score > best:
            best = score; torch.save({k: v.cpu() for k, v in model.state_dict().items()}, OUTPUT / 'Murmur.pt')
        save(OUTPUT / 'training.json', dict(protocol=protocol, history=history, device=str(device)))
    export()


def export():
    import coremltools as ct
    torch.set_num_threads(1); torch.manual_seed(2414)
    classifier = PhaseMurmurNet(); classifier.load_state_dict(torch.load(OUTPUT / 'Murmur.pt', weights_only=True)); classifier.eval(); model = WavePhaseModel(classifier).eval()
    converted = ct.convert(torch.jit.trace(model, torch.randn(1, 1, SAMPLES) * .03),
        inputs=[ct.TensorType(name='waveform', shape=(1, 1, SAMPLES))],
        outputs=[ct.TensorType(name='probabilities'), ct.TensorType(name='phase_probabilities')],
        minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM; public CirCor phase-supervised research'
    converted.short_description = 'Joint heartbeat-phase and murmur-pattern model; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1', labels='Absent,Present,Unknown',
        phase_labels='noise,S1,systole,S2,diastole', dataset='https://doi.org/10.13026/tshs-mw03', weights_sha256=digest(OUTPUT / 'Murmur.pt'))
    converted.save(str(OUTPUT / 'Murmur.mlpackage')); errors = []
    for scale in [0, .0001, .01, .3]:
        x = torch.randn(1, 1, SAMPLES) * scale
        with torch.inference_mode(): expected = model(x)
        actual = converted.predict({'waveform': x.numpy()})
        errors.append([float(np.max(np.abs(e.numpy() - actual[name]))) for e, name in zip(expected, ['probabilities', 'phase_probabilities'])])
    assert np.max(errors) < .001, errors
    save(OUTPUT / 'conversion.json', dict(maximum_probability_differences=np.max(errors, axis=0).tolist(), examples=len(errors)))
    print('Native joint murmur/phase conversion passed:', errors, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--epochs', type=int, default=24); p.add_argument('--steps', type=int, default=100); p.add_argument('--export-only', action='store_true'); a = p.parse_args()
    export() if a.export_only else train(a.epochs, a.steps)
