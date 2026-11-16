"""V15: matched learned-attention versus mean-pooling public-data training."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time
import zipfile

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from m2d_attention import M2DDecisionHead, FEATURE_DIM, ATTENTION_DIM
from m2d_murmur import M2DMurmur, HERE, sha, decide
from train_m2d_murmur import save, tensor_sha
from train_m2d_native_heads import public_input, windows, generic_phone, ENCODER_CHECKPOINT
from train_m2d_preserving import preserving_loss, load_reference
from murmur_focus_metrics import aggregate

EPOCHS = 12
SNAPSHOTS = (4, 8, 12)
BATCH_SIZE = 128
SOURCE_FILES = (
    'm2d_murmur.py', 'm2d_attention.py', 'train_m2d_murmur.py',
    'train_m2d_native_heads.py', 'train_m2d_preserving.py',
    'murmur_focus_metrics.py', 'train_m2d_attention.py',
)


def fingerprints(model):
    return {k: tensor_sha(v) for k, v in model.state_dict().items()}


def snapshot(head):
    return {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}


def prepare(config, read, baseline, device, cache):
    """Cache full time features, with no averaging before the decision head."""
    path = cache / 'training-time-frames.f16'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError('Preserve an existing feature cache')
    labels, reference, audit = [], [], []
    selection = {'native2k': [], 'generic': []}
    frame_count = None
    with path.open('wb') as output:
        for i, r in enumerate(config['records'], 1):
            raw = read(r['native_file'])
            assert hashlib.sha256(raw).hexdigest() == r['native_sha256']
            wave = np.frombuffer(raw, dtype='<f4').copy()
            assert len(wave) == r['samples'] and np.isfinite(wave).all()
            counts = []
            for domain, audio in [('native2k', wave), ('generic', generic_phone(wave, r['record']))]:
                crops = windows(audio, r['role'] == 'training')
                parts = []
                with torch.inference_mode():
                    for start in range(0, len(crops), 16):
                        mel = baseline.features(torch.from_numpy(crops[start:start + 16]).to(device))
                        frames = baseline.runtime.encode_lms(baseline.runtime.normalize_batch(mel)).float()
                        assert frames.ndim == 3 and frames.shape[2] == FEATURE_DIM
                        if frame_count is None:
                            frame_count = frames.shape[1]
                        assert frames.shape[1] == frame_count and torch.isfinite(frames).all()
                        if r['role'] == 'training':
                            half = frames.half()
                            assert torch.isfinite(half).all()
                            half.cpu().numpy().tofile(output)
                            teacher = baseline.classifier(baseline.norm(frames.mean(1))).softmax(1)
                            reference.append(teacher.cpu().numpy())
                            labels.extend([r['target']] * len(frames))
                        else:
                            parts.append(frames.cpu().numpy())
                counts.append(len(crops))
                if r['role'] == 'selection':
                    values = np.concatenate(parts) if parts else np.empty((0, frame_count, FEATURE_DIM), dtype=np.float32)
                    selection[domain].append(dict(r, frames=values))
            audit.append(dict(record=r['record'], role=r['role'], windows=counts,
                              native_sha256=r['native_sha256']))
            if i % 200 == 0:
                print(json.dumps(dict(stage='attention_time_features', recordings=i,
                                      total=len(config['records']))), flush=True)
    assert frame_count and path.stat().st_size == len(labels) * frame_count * FEATURE_DIM * 2
    assert len(selection['native2k']) == len(selection['generic']) == 180
    return path, frame_count, np.asarray(labels, dtype=np.int64), np.concatenate(reference), selection, audit


class TimeFeatures(Dataset):
    def __init__(self, path, labels, reference, frame_count):
        self.frames = np.memmap(path, mode='r', dtype='<f2',
                                shape=(len(labels), frame_count, FEATURE_DIM))
        self.labels, self.reference = labels, reference

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        return (torch.from_numpy(self.frames[i].copy()), int(self.labels[i]),
                torch.from_numpy(self.reference[i].copy()))


def evaluate_head(head, records, device):
    head.eval()
    predictions = {}
    deviations, maxima, entropy = [], [], []
    with torch.inference_mode():
        for r in records:
            logits = []
            for start in range(0, len(r['frames']), 16):
                frames = torch.from_numpy(r['frames'][start:start + 16]).float().to(device)
                if head.pooling == 'attention':
                    value, weight = head(frames, return_weights=True)
                    deviations.extend((weight - 1. / weight.shape[1]).abs().amax(1).cpu().tolist())
                    maxima.extend(weight.amax(1).cpu().tolist())
                    h = -(weight * weight.clamp_min(1e-12).log()).sum(1) / math.log(weight.shape[1])
                    entropy.extend(h.cpu().tolist())
                else:
                    value = head(frames)
                logits.append(value.float().cpu())
            p = torch.cat(logits).mean(0).softmax(0).numpy() if logits else np.array([0., 0., 1.])
            predictions[r['record']] = {'reading': {'finding': decide(p), 'probabilities': p.tolist(),
                                                   'windows': len(r['frames'])}}
    attention = None
    if head.pooling == 'attention':
        attention = dict(windows=len(deviations), maximum_deviation_from_uniform=max(deviations, default=0.),
                         mean_maximum_frame_weight=float(np.mean(maxima)) if maxima else None,
                         mean_normalized_entropy=float(np.mean(entropy)) if entropy else None,
                         nonuniform_windows=sum(x > 1e-6 for x in deviations))
    return aggregate(records, predictions), predictions, attention


def train(a):
    os.umask(0o077)
    torch.set_num_threads(2)
    torch.manual_seed(20261115)
    torch.cuda.manual_seed_all(20261115)
    if a.output.exists():
        raise ValueError('Preserve completed/partial training runs')
    config, read = public_input(a.bundle, a.config_sha, a.bundle_sha)
    assert torch.cuda.is_available(), 'CUDA GPU required'
    a.output.mkdir(parents=True)
    protocol = dict(
        epochs=EPOCHS, retained_epochs=list(SNAPSHOTS), batch_size=BATCH_SIZE, seed=20261115,
        base_checkpoint_sha256=ENCODER_CHECKPOINT, encoder_frozen=True,
        normalization='Original normalization statistics frozen in both arms',
        arms=['mean', 'attention'], feature_dim=FEATURE_DIM, attention_dim=ATTENTION_DIM,
        attention='Non-affine LayerNorm; Linear(3840,64); tanh; Linear(64,1); softmax(time); weighted sum',
        initialization='Zero score weights; attention initially equals mean',
        trainable='Classifier in both arms; attention score/project layers only in attention arm',
        learning_rates={'classifier':1e-4, 'attention':3e-4}, weight_decay=.01,
        optimizer='AdamW; float32; same batches/order; one-round warmup and cosine to.05; clip1',
        loss='Identical V13 preserving_loss: raw CE costs1/6/8,3x hard false-Present,2x recognized trueP/Unknown floor',
        cache='Full encoder time frames; training float16 storage->float32 fitting; selection/inference float32',
        input='Exact public native2k->16k;5s/2.5s training stride; same V12 generic augmentation',
        confidence_threshold=.60, recording_aggregation='Mean separate-window logits; unchanged',
        config_sha256=a.config_sha, bundle_sha256=a.bundle_sha,
        private_audio_included=False, private_profile_included=False, calibration_or_test_loaded=False,
        source_sha256={n:sha(HERE / n) for n in SOURCE_FILES},
        environment={'torch':torch.__version__, 'gpu':torch.cuda.get_device_name(0)},
        evidence='Reused development; no independent clinical phone validation or app update')
    save(a.output / 'protocol.json', protocol)
    device = torch.device('cuda:0')
    baseline = M2DMurmur(a.cache / 'upstream').eval()
    baseline.load_state_dict(load_reference(a.checkpoint))
    baseline.requires_grad_(False)
    baseline.to(device)
    assert shutil.disk_usage(a.cache).free > 10 * 1024**3, 'Need 10GiB scratch for unpooled time features'
    before = fingerprints(baseline)
    heads = {arm:M2DDecisionHead(baseline.norm, baseline.classifier, arm).to(device)
             for arm in ['mean', 'attention']}
    initial = {arm:snapshot(head) for arm, head in heads.items()}
    torch.save(initial, a.output / 'initial-heads.pt')
    path, frame_count, labels, reference, selection, audit = prepare(config, read, baseline, device, a.cache)
    assert reference.shape == (len(labels), 3) and np.isfinite(reference).all()
    assert fingerprints(baseline) == before
    save(a.output / 'base-fingerprints.json', before)
    # Verify the initial full-precision function before any optimizer step.
    first = next(r for r in selection['native2k'] if len(r['frames']))
    with torch.no_grad():
        frames = torch.from_numpy(first['frames'][:4]).to(device)
        expected = baseline.classifier(baseline.norm(frames.mean(1)))
        initial_error = float((heads['attention'](frames) - expected).abs().max().cpu())
        assert initial_error < .0001
        torch.testing.assert_close(heads['mean'](frames), expected, atol=0, rtol=0)
    counts = np.bincount(labels, minlength=3).tolist()
    assert min(counts) > 0
    save(a.output / 'data-audit.json', dict(training_records=2356, selection_records=180,
        training_windows=len(labels), training_class_counts=counts, frame_count=frame_count,
        cache_bytes=path.stat().st_size, records=audit, persons_disjoint=True,
        initial_attention_maximum_logit_error=initial_error))
    loader = DataLoader(TimeFeatures(path, labels, reference, frame_count), batch_size=BATCH_SIZE,
        shuffle=True, num_workers=0, pin_memory=True,
        generator=torch.Generator().manual_seed(20261115))
    optimizers = {}
    for arm, head in heads.items():
        groups = [{'params':list(head.classifier.parameters()), 'lr':1e-4, 'base_lr':1e-4}]
        if arm == 'attention':
            groups.append({'params':list(head.pool.parameters()), 'lr':3e-4, 'base_lr':3e-4})
        optimizers[arm] = torch.optim.AdamW(groups, weight_decay=.01)
    saved, predictions, audits, history = {}, {}, {}, []
    steps = 0
    for epoch in range(1, EPOCHS + 1):
        began = time.perf_counter()
        losses = {arm:[] for arm in heads}
        for head in heads.values():
            head.train()
        for step, (frames, target, reference_p) in enumerate(loader):
            phase = epoch - 1 + (step + 1) / len(loader)
            factor = phase if phase < 1 else .05 + .95 * .5 * (1 + math.cos(math.pi * (phase - 1) / (EPOCHS - 1)))
            frames = frames.to(device, dtype=torch.float32, non_blocking=True)
            target, reference_p = target.to(device), reference_p.to(device)
            for arm, head in heads.items():
                optimizer = optimizers[arm]
                for group in optimizer.param_groups:
                    group['lr'] = group['base_lr'] * factor
                optimizer.zero_grad(set_to_none=True)
                loss, _, _ = preserving_loss(head(frames), target, reference_p)
                assert torch.isfinite(loss), 'Nonfinite training loss'
                loss.backward()
                torch.nn.utils.clip_grad_norm_([p for p in head.parameters() if p.requires_grad],
                                              1., error_if_nonfinite=True)
                optimizer.step()
                losses[arm].append(float(loss.detach().cpu()))
            steps += 1
            if step % 100 == 0:
                print(json.dumps(dict(stage='attention_training', epoch=epoch, step=step + 1,
                    steps=len(loader), loss={arm:x[-1] for arm,x in losses.items()})), flush=True)
        row = dict(epoch=epoch, optimizer_steps_per_arm=steps,
                   loss={arm:float(np.mean(x)) for arm,x in losses.items()},
                   seconds=time.perf_counter()-began)
        if epoch in SNAPSHOTS:
            row['selection'] = {}
            for arm, head in heads.items():
                key = f'{arm}_epoch_{epoch}'
                state = snapshot(head)
                assert all(torch.isfinite(v).all() for v in state.values())
                for k,v in baseline.norm.state_dict().items():
                    assert torch.equal(state['norm.' + k], v.cpu()), (key,k)
                assert not torch.equal(state['classifier.weight'], initial[arm]['classifier.weight'])
                saved[key], predictions[key], audits[key], row['selection'][arm] = state, {}, {}, {}
                for domain, records in selection.items():
                    metrics, pred, attention = evaluate_head(head, records, device)
                    predictions[key][domain] = pred
                    row['selection'][arm][domain] = metrics['recordings']
                    if attention:
                        audits[key][domain] = attention
                        assert attention['nonuniform_windows'] > 0
                        assert attention['maximum_deviation_from_uniform'] > 1e-6
        history.append(row)
        save(a.output / 'history.json', history)
        print(json.dumps(dict(stage='attention_epoch_complete', **row)), flush=True)
    assert fingerprints(baseline) == before, 'Frozen source model changed'
    assert len(saved) == 6
    torch.save(saved, a.output / 'attention-heads.pt')
    save(a.output / 'selection-predictions.json', predictions)
    save(a.output / 'complete.json', dict(status='attention_training_complete', epochs=EPOCHS,
        optimizer_steps_per_arm=steps, heads=6, base_model_unchanged=True,
        heads_sha256=sha(a.output / 'attention-heads.pt'),
        initial_heads_sha256=sha(a.output / 'initial-heads.pt'),
        protocol_sha256=sha(a.output / 'protocol.json'), attention_audit=audits,
        private_audio_used=False, private_profile_used=False, calibration_or_test_loaded=False,
        app_updated=False))
    print(json.dumps(dict(complete=True, attention_heads=3, matched_mean_controls=3,
                          base_model_unchanged=True)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['bundle', 'checkpoint', 'output', 'cache']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--config-sha', required=True)
    p.add_argument('--bundle-sha', required=True)
    a = p.parse_args()
    try:
        train(a)
    finally:
        if a.output.exists():
            with zipfile.ZipFile(a.output.parent / 'heart-m2d-attention.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(a.output.rglob('*')):
                    if path.is_file():
                        archive.write(path, 'artifacts/' + str(path.relative_to(a.output)))
