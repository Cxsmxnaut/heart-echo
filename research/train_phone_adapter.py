"""Stage two: frozen public clinical model + separately learned phone correction.

All phone statistics remain local. Only public labeled crops supervise this stage;
the adapter cannot change the clinical model's weights or running statistics.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch.nn import functional as F

from two_stage_models import make_clinical, PhoneAdapter, AdaptedClinical, spectra, normalize, sha
from phone_style import transform, stable_seed, assert_person_split
from murmur_focus_metrics import aggregate, promotion_checks

HERE = Path(__file__).resolve().parent
ML = HERE.parent / 'ChestBPM/ML'
sys.path.insert(0, str(ML))
from murmur_native_data import CACHE
from murmur_additive_model import AdditiveModel
from prepare_phone_murmur import usable_starts
from train_public_backbones import starts


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def read_records():
    rows = [r for r in json.loads((ML / 'murmur-phase-manifest.json').read_text())['records'] if r['role'] != 'test']
    assert_person_split(rows)
    native = {r['record']: r for r in json.loads((CACHE / 'manifest.json').read_text())['records']}
    for r in rows:
        info = native[r['record']]
        path = CACHE / 'audio' / (r['record'] + '.f32')
        r.update(samples=info['samples'], usable=info['usable_frame_starts'], path=path,
                 audio_sha256=info['native_audio_sha256'])
    return rows


def views_for(rows, profile):
    views = {'clean': [], 'styled': []}
    for r in rows:
        assert sha(r['path']) == r['audio_sha256']
        clean = np.fromfile(r['path'], dtype='<f4')
        styled = transform(clean, profile, np.random.default_rng(stable_seed('two-stage-evaluation:' + r['record'])))
        for domain, audio in [('clean', clean), ('styled', styled)]:
            views[domain].append(dict(record=r, wave=audio, x=spectra(audio)[0],
                                      usable=r['usable'] if domain == 'clean' else usable_starts(audio)))
    return views


def evaluate(model, views, device, waveform=False):
    model.eval(); chunks, owners = [], []
    sums = np.zeros((len(views), 3)); count = np.zeros(len(views))
    for i, item in enumerate(views):
        valid = set(item['usable'])
        for start in starts(len(item['wave'])):
            frame = start // 40
            if frame in valid:
                chunks.append(item['wave'][start:start + 8000][None] if waveform
                              else item['x'][:, frame:frame + 194]); owners.append(i)
    with torch.inference_mode():
        for start in range(0, len(chunks), 8):
            x = torch.from_numpy(np.stack(chunks[start:start + 8])).to(device)
            p = model(x)[0] if waveform else model(x).softmax(1)
            p = p.cpu().numpy()
            for owner, probability in zip(owners[start:start + 8], p):
                sums[owner] += probability; count[owner] += 1
    predictions = {}
    for i, item in enumerate(views):
        p = sums[i] / count[i] if count[i] else np.array([0., 0., 1.])
        best = int(np.argmax(p)); label = best if p[best] >= .60 else 2
        predictions[item['record']['record']] = {'reading': {'finding': ['absent', 'present', 'unsure'][label],
                                                            'probabilities': p.tolist()}}
    return aggregate([r['record'] for r in views], predictions), predictions


def balanced(result):
    matrix = np.asarray(result['recordings']['matrix'])
    return float(np.mean(np.diag(matrix) / np.maximum(matrix.sum(1), 1)))


def batch(rng, pools, profile):
    clean, phone, labels = [], [], []
    for label in [0] * 3 + [1] * 3 + [2]:
        r = pools[label][int(rng.integers(len(pools[label])))]
        frame = r['usable'][int(rng.integers(len(r['usable'])))]
        audio = np.memmap(r['path'], dtype='<f4', mode='r')[frame * 40:frame * 40 + 8000].copy()
        clean.append(audio); phone.append(transform(audio, profile, rng)); labels.append(label)
    noise = rng.normal(0, .01, 8000).astype(np.float32)
    clean.append(noise); phone.append(transform(noise, profile, rng)); labels.append(2)
    return spectra(np.stack(clean)), spectra(np.stack(phone)), np.asarray(labels)


def train(args):
    os.umask(0o077); out = args.output.resolve()
    if out.exists():
        raise ValueError('Existing adapter runs must be preserved')
    source = args.clinical_dir.resolve()
    completed = json.loads((source / 'complete.json').read_text())
    assert completed['status'] == 'source_training_complete'
    source_protocol = json.loads((source / 'protocol.json').read_text())
    assert source_protocol['source_sha256']['two_stage_models.py'] == sha(HERE / 'two_stage_models.py')
    choices = {name: json.loads((source / name / 'selected.json').read_text())['score']
               for name in completed['models']}
    chosen = max(sorted(choices), key=choices.get)
    for name, proof in completed['models'].items():
        assert sha(source / name / 'Clinical.pt') == proof['weights_sha256']
        assert proof['changed_backbone_parameter_tensors'] > 0
    profile = json.loads(args.profile.read_text())
    assert profile['case_on_audio_used'] is False and profile['private_clinical_labels_created'] is False
    out.mkdir(parents=True)
    protocol = dict(seed=20261118, clinical_model=chosen, clinical_selection_scores=choices,
                    clinical_weights_sha256=sha(source / chosen / 'Clinical.pt'),
                    profile_sha256=sha(args.profile), epochs=16, steps_per_epoch=80, batch=8,
                    optimizer='AdamW adapter-only lr.001 weight_decay.001',
                    loss='Every step: normalized spectral smoothL1 + .10 clean identity correction squared. '
                         'Every fourth step: add KL to frozen clinical clean prediction + .50 public-label CE.',
                    architecture='Identity-initialized 128->32->64 mapping of spectral mean/deviation, '
                                 'bounded +/-1.5 log-power shift constant across time.',
                    selection='Every2epochs, maximum minimum clean/style three-class balanced recall on selection, then mean; trained epochs only.',
                    threshold=.60, calibration_before_freeze=False, private_clinical_targets_used=False,
                    source_sha256={name: sha(HERE / name) for name in ['two_stage_models.py', 'train_phone_adapter.py',
                                                                     'phone_style.py', 'murmur_focus_metrics.py']},
                    evidence='Both development partitions reused; simulated phone pairs do not establish real phone accuracy.')
    save(out / 'protocol.json', protocol)
    torch.manual_seed(protocol['seed']); torch.set_num_threads(2)
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    clinical = make_clinical(chosen)
    clinical.load_state_dict(torch.load(source / chosen / 'Clinical.pt', map_location='cpu', weights_only=True))
    frozen = copy.deepcopy(clinical.state_dict())
    model = AdaptedClinical(clinical).to(device)
    initial_adapter = copy.deepcopy(model.adapter.state_dict())
    optimizer = torch.optim.AdamW(model.adapter.parameters(), lr=.001, weight_decay=.001)
    rows = read_records()
    training = [r for r in rows if r['role'] == 'training' and r['usable']]
    pools = [[r for r in training if r['target'] == label] for label in [0, 1, 2]]
    selection = [r for r in rows if r['role'] == 'selection']
    selection_views = views_for(selection, profile)
    original = {domain: evaluate(model, values, device)[0] for domain, values in selection_views.items()}
    save(out / 'before-adaptation.json', original)
    rng = np.random.default_rng(protocol['seed']); history, best = [], (-1., -1.)
    for epoch in range(1, 17):
        model.train(); losses = []; began = time.perf_counter()
        for step in range(80):
            arrays = batch(rng, pools, profile)
            clean, phone, target = [torch.from_numpy(x).to(device) for x in arrays]
            optimizer.zero_grad(set_to_none=True)
            corrected = model.adapter(phone)
            loss = F.smooth_l1_loss(normalize(corrected), normalize(clean))
            loss = loss + .10 * model.adapter.correction(clean).square().mean()
            if step % 4 == 0:
                with torch.no_grad():
                    reference = model.clinical(clean).softmax(1)
                logits = model.clinical(corrected)
                loss = loss + F.kl_div(logits.log_softmax(1), reference, reduction='batchmean')
                loss = loss + .50 * F.cross_entropy(logits, target)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite adapter loss')
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.adapter.parameters(), 2.)
            optimizer.step(); losses.append(float(loss.detach().cpu()))
        row = dict(epoch=epoch, loss=float(np.mean(losses)), seconds=time.perf_counter() - began)
        if epoch % 2 == 0:
            results = {domain: evaluate(model, values, device)[0] for domain, values in selection_views.items()}
            values = [balanced(r) for r in results.values()]; score = (min(values), float(np.mean(values)))
            row['selection'] = {domain: result['recordings'] for domain, result in results.items()}
            row['score'] = score
            if score > best:
                best = score
                torch.save({k: v.detach().cpu() for k, v in model.adapter.state_dict().items()}, out / 'PhoneAdapter.pt')
                save(out / 'selected.json', dict(epoch=epoch, score=score))
        history.append(row); save(out / 'history.json', history)
        print(json.dumps(row), flush=True)
    assert all(torch.equal(v, model.clinical.state_dict()[k].detach().cpu()) for k, v in frozen.items())
    adapter = torch.load(out / 'PhoneAdapter.pt', map_location='cpu', weights_only=True)
    changed = [k for k in adapter if not torch.equal(initial_adapter[k].cpu(), adapter[k])]
    assert changed and all(torch.isfinite(v).all() for v in adapter.values())
    model.adapter.load_state_dict(adapter); model.eval()
    proof = dict(optimizer_steps=1280, semantic_loss_steps=320, changed_adapter_tensors=len(changed),
                 clinical_weights_and_buffers_unchanged=True, adapter_sha256=sha(out / 'PhoneAdapter.pt'),
                 clinical_weights_sha256=protocol['clinical_weights_sha256'], selected=json.loads((out / 'selected.json').read_text()))
    save(out / 'training-proof.json', proof)
    save(out / 'evaluation-freeze.json', dict(protocol_sha256=sha(out / 'protocol.json'), training=proof,
                                            threshold=.60, frozen_before_calibration=True))
    # All checkpoint/model selection is now over; only now load calibration audio.
    calibration = [r for r in rows if r['role'] == 'calibration']
    calibration_views = views_for(calibration, profile)
    report = dict(roles={}, clinical_model=chosen, training=proof, source_selection=choices,
                  private_phone_accuracy='Unavailable: phone references unreviewed', app_updated=False,
                  evidence=protocol['evidence'])
    all_passed, added = True, 0
    baseline = AdditiveModel(); baseline.load_state_dict(torch.load(ML / 'generated/murmur-phase-m/Murmur.pt',
                                                                  map_location='cpu', weights_only=True)); baseline.eval()
    final_predictions = {}
    for role, views in [('selection', selection_views), ('calibration', calibration_views)]:
        report['roles'][role] = {}
        final_predictions[role] = {}
        for domain, view in views.items():
            final_predictions[role][domain] = {}
            a, ap = evaluate(baseline, view, torch.device('cpu'), waveform=True)
            b, bp = evaluate(model, view, device)
            results = {'app-M': a, 'adapted': b}
            final_predictions[role][domain].update({'app-M': ap, 'adapted': bp})
            for name in completed['models']:
                other = make_clinical(name)
                other.load_state_dict(torch.load(source / name / 'Clinical.pt', map_location='cpu', weights_only=True))
                other.to(device).eval()
                results[name], values = evaluate(other, view, device)
                final_predictions[role][domain][name] = values
                del other
                if device.type == 'mps':
                    torch.mps.empty_cache()
            checks = promotion_checks(results['app-M'], results['adapted'])
            all_passed &= all(checks.values())
            added += results['adapted']['recordings']['detected_positive'] - results['app-M']['recordings']['detected_positive']
            report['roles'][role][domain] = dict(results=results, strict_checks=checks)
    report.update(development_gate_passed=bool(all_passed and added > 0),
                  decision='native_conversion_required_before_regression_or_app_use' if all_passed and added > 0
                  else 'retain_app_M; two-stage candidate is research only')
    save(out / 'comparison.json', report)
    save(out / 'final-predictions.json', final_predictions)
    save(out / 'complete.json', dict(status='adapter_training_complete', proof=proof, decision=report['decision'],
                                    predictions_sha256=sha(out / 'final-predictions.json')))
    print(json.dumps({'complete': True, 'decision': report['decision'], 'proof': proof}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clinical-dir', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    train(parser.parse_args())
