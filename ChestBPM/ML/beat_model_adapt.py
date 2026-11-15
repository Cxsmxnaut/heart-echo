"""Research candidate: retain deployed sound patterns while learning new artifacts.

Public training patients only. No new personal recordings, ECG or disease targets.
"""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from beat_model import BeatNet, batch
import beat_model_v2

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'generated/beat-adapt'


def main():
    if (OUTPUT / 'BeatStates.pt').exists(): raise ValueError('Adaptation checkpoint exists; refusing overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original = ROOT / 'generated/BeatStates.pt'
    expected = json.loads((ROOT / 'results/beat-training.json').read_text())['model_sha256']
    assert hashlib.sha256(original.read_bytes()).hexdigest() == expected
    protocol = dict(seed=611, epochs=16, steps=100, learning_rate=.00015, original_checkpoint_sha256=expected,
                    anchor_batch=48, augmentation_batch=16, distillation_temperature=2, distillation_weight=1,
                    selection='Minimum .75original-validation CE + .25augmentation-validation CE, including the original model at epoch0.',
                    labels='Public CirCor sound states only; irregular positive beats remain positive. No diagnoses, ECG, Watch or personal training data.')
    (OUTPUT / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    source_files = [Path(__file__), ROOT / 'beat_model.py', ROOT / 'beat_model_v2.py', ROOT / 'event_benchmark.py', ROOT / 'manifest.json']
    (OUTPUT / 'source-sha256.json').write_text(json.dumps({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}, indent=2) + '\n')
    torch.manual_seed(611); np.random.seed(611); torch.set_num_threads(4)
    data, groups = beat_model_v2.data_with_artifacts()
    anchors, augmented = {}, {}
    for split, key in [('training', 'training_groups'), ('validation', 'validation_groups')]:
        size = len(groups[key]); assert len(data[split]) == size * 19
        anchors[split], augmented[split] = data[split][:size * 13], data[split][size * 13:]
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    state = torch.load(original, map_location='cpu', weights_only=True)
    model, teacher = BeatNet().to(device), BeatNet().to(device)
    model.load_state_dict(state); teacher.load_state_dict(state); teacher.eval()
    for p in teacher.parameters(): p.requires_grad_(False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=protocol['learning_rate'], weight_decay=.0001)
    counts = np.bincount(np.concatenate([y for _, y in data['training']]), minlength=5)
    weights = np.sqrt(counts.sum() / np.maximum(counts, 1)); weights /= weights.mean()
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device))
    rng = np.random.default_rng(9171); best = float('inf'); history = []

    def validate():
        model.eval(); losses = []
        with torch.inference_mode():
            for source in [anchors['validation'], augmented['validation']]:
                vrng = np.random.default_rng(4107); values = []
                for _ in range(30):
                    x, y = batch(source, vrng, 64, device)
                    values.append(float(criterion(model(x)[:, :, 125:], y[:, 125:]).cpu()))
                losses.append(float(np.mean(values)))
        return losses

    for epoch in range(protocol['epochs'] + 1):
        began = time.perf_counter(); total = 0
        if epoch:
            model.train()
            for _ in range(protocol['steps']):
                ax, ay = batch(anchors['training'], rng, 48, device)
                nx, ny = batch(augmented['training'], rng, 16, device)
                x, y = torch.cat([ax, nx]), torch.cat([ay, ny])
                optimizer.zero_grad(set_to_none=True); logits = model(x)
                supervised = criterion(logits[:, :, 125:], y[:, 125:])
                with torch.no_grad(): reference = teacher(ax)[:, :, 125:]
                temperature = protocol['distillation_temperature']
                student = logits[:48, :, 125:].transpose(1, 2).reshape(-1, 5) / temperature
                target = reference.transpose(1, 2).reshape(-1, 5) / temperature
                retain = F.kl_div(F.log_softmax(student, dim=1), F.softmax(target, dim=1), reduction='batchmean') * temperature ** 2
                loss = supervised + retain; loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 2)
                optimizer.step(); total += float(loss.detach().cpu())
        old_loss, new_loss = validate(); score = .75 * old_loss + .25 * new_loss
        row = dict(epoch=epoch, training_loss=total / protocol['steps'] if epoch else None,
                   anchor_validation_loss=old_loss, augmentation_validation_loss=new_loss,
                   selection_score=score, seconds=time.perf_counter() - began)
        history.append(row); print(json.dumps(row), flush=True)
        if score < best:
            best = score; torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, OUTPUT / 'BeatStates.pt')
        (OUTPUT / 'training.json').write_text(json.dumps(dict(protocol=protocol, groups=groups, history=history, device=str(device)), indent=2) + '\n')
    # Reuse the same checked exporter with this candidate's separate output directory.
    beat_model_v2.OUTPUT = OUTPUT
    beat_model_v2.export()


if __name__ == '__main__': main()
