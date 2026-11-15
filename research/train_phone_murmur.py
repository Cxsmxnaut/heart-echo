"""Matched clean-control / phone-style fine-tunes of the existing M murmur model.

Public labels supervise weights. Private audio supplied only unpaired style/noise
summaries in preparation. No old test set, private clinical target, or app mutation.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
ML = HERE.parent / 'ChestBPM/ML'
sys.path.insert(0, str(ML))
from murmur_additive_model import AdditiveModel, add_positive_evidence
from murmur_model import FRAMES, HOP, windows, decision
from murmur_data import digest, save
from murmur_timing_data import timing_targets
from murmur_native_data import CACHE
from murmur_focus_metrics import aggregate, promotion_checks
from phone_style import assert_person_split


def feature_outputs(model, x):
    proposal, phase, timing = model.proposal(x)
    return add_positive_evidence(model.baseline(x).softmax(1), proposal), phase, timing


def evaluate(model, records, device, styled):
    model.eval()
    all_windows, owners, sums, numbers = [], [], np.zeros((len(records), 3)), np.zeros(len(records))
    for i, r in enumerate(records):
        usable = set(r['styled_usable' if styled else 'clean_usable'])
        for start in windows(r['samples']):
            frame = start // HOP
            if frame in usable:
                all_windows.append(r['styled_x' if styled else 'x'][:, frame:frame + FRAMES]); owners.append(i)
    with torch.inference_mode():
        for start in range(0, len(all_windows), 96):
            batch = torch.from_numpy(np.stack(all_windows[start:start + 96])).to(device)
            p = feature_outputs(model, batch)[0].cpu().numpy()
            for owner, probability in zip(owners[start:start + 96], p):
                sums[owner] += probability; numbers[owner] += 1
    labels = ['absent', 'present', 'unsure']
    predictions = {}
    for i, r in enumerate(records):
        p = sums[i] / numbers[i] if numbers[i] else np.array([0., 0., 1.])
        predictions[r['record']] = {'reading': {'finding': labels[decision(p)], 'probabilities': p.tolist()}}
    return aggregate(records, predictions)


def selection_score(clean, styled):
    def balanced(result):
        matrix = np.asarray(result['recordings']['matrix'])
        return float(np.mean(np.diag(matrix) / np.maximum(matrix.sum(axis=1), 1)))
    a, b = balanced(clean), balanced(styled)
    return min(a, b), (a + b) / 2


def short_metrics(report):
    keys = ['detected_positive', 'positive_called_absent', 'false_alarms', 'correct_absent', 'total_unsure']
    return {k: report['recordings'][k] for k in keys}


def paired_loss(model, teacher, clean, second, y, phase_target, timing_target):
    p, phase, timing = feature_outputs(model, clean)
    q, phase2, timing2 = feature_outputs(model, second)
    classification = .5 * (F.nll_loss(p.clamp_min(1e-7).log(), y)
                           + F.nll_loss(q.clamp_min(1e-7).log(), y))
    phase_mask = phase_target != -100
    phase_loss = ((F.nll_loss(phase.clamp_min(1e-7).log(), phase_target, ignore_index=-100)
                   + F.nll_loss(phase2.clamp_min(1e-7).log(), phase_target, ignore_index=-100)) / 2
                  if phase_mask.any() else p.sum() * 0)
    mask = timing_target != -100
    if mask.any():
        # Same positive timing weight as earlier experiments, applied to probabilities.
        weights = torch.where(timing_target[mask] > .5, 2., 1.)
        weak = .5 * (F.binary_cross_entropy(timing[mask].clamp(1e-6, 1 - 1e-6), timing_target[mask], weight=weights)
                     + F.binary_cross_entropy(timing2[mask].clamp(1e-6, 1 - 1e-6), timing_target[mask], weight=weights))
    else:
        weak = p.sum() * 0
    with torch.no_grad():
        reference = feature_outputs(teacher, clean)[0]
    anchor = F.kl_div(p.clamp_min(1e-7).log(), reference, reduction='batchmean')
    return classification + .30 * phase_loss + .35 * weak + .20 * anchor


def load_data(run):
    proof = json.loads((run / 'prepared.json').read_text())
    assert digest(run / 'data.json') == proof['data_sha256']
    assert digest(run / 'phone-profile.json') == proof['phone_profile_sha256']
    assert digest(run / 'noise-controls.npz') == proof['control_sha256']
    records = json.loads((run / 'data.json').read_text())
    assert_person_split(records)
    for r in records:
        clean = CACHE / 'features' / (r['record'] + '.npy')
        styled = run / 'features' / (r['record'] + '.npy')
        assert digest(clean) == r['clean_features_sha256']
        assert digest(styled) == r['styled_features_sha256']
        r['x'] = np.load(clean); r['styled_x'] = np.load(styled)
        r['phases'], r['timing'] = timing_targets(r, r['x'].shape[1])
    return records


def batch(rng, pools, controls, styled):
    clean, second, labels, phases, timing = [], [], [], [], []
    for label in [0] * 10 + [1] * 8 + [2] * 2:
        r = pools[label][int(rng.integers(len(pools[label])))]
        frame = r['paired_usable'][int(rng.integers(len(r['paired_usable'])))]
        jitter = rng.uniform(-.5, .5)
        clean.append(r['x'][:, frame:frame + FRAMES] + jitter)
        second.append(r['styled_x' if styled else 'x'][:, frame:frame + FRAMES] + jitter)
        labels.append(label); phases.append(r['phases'][frame:frame + FRAMES])
        timing.append(r['timing'][frame:frame + FRAMES])
    for _ in range(4):
        index = int(rng.integers(len(controls['clean'])))
        clean.append(controls['clean'][index]); second.append(controls['styled' if styled else 'clean'][index])
        labels.append(2); phases.append(np.zeros(FRAMES, dtype=np.int64)); timing.append(np.zeros(FRAMES, dtype=np.float32))
    return (np.stack(clean), np.stack(second), np.asarray(labels), np.stack(phases), np.stack(timing))


def shipping_hashes():
    return {str(p.relative_to(HERE.parent)): digest(p) for name in ['BeatStates', 'Murmur']
            for p in sorted((HERE.parent / 'HeartEcho/Models' / (name + '.mlpackage')).rglob('*')) if p.is_file()}


def train(run):
    os.umask(0o077)
    run = run.resolve()
    protocol = json.loads((run / 'protocol.json').read_text())
    for name, expected in protocol['source_sha256'].items():
        path = HERE / name if (HERE / name).exists() else ML / name
        assert digest(path) == expected, name
    weights = ML / 'generated/murmur-phase-m/Murmur.pt'
    assert digest(weights) == protocol['original_weights_sha256']
    if any((run / name).exists() for name in ['clean-control', 'phone-style', 'complete.json']):
        raise ValueError('An existing training run must not be restarted or overwritten')
    initial_shipping = shipping_hashes()
    torch.set_num_threads(2)
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    initial = torch.load(weights, map_location='cpu', weights_only=True)
    records = load_data(run)
    train_records = [r for r in records if r['role'] == 'training' and r['paired_usable']]
    pools = [[r for r in train_records if r['target'] == label] for label in [0, 1, 2]]
    assert all(pools)
    selection = [r for r in records if r['role'] == 'selection']
    calibration = [r for r in records if r['role'] == 'calibration']
    controls = dict(np.load(run / 'noise-controls.npz'))
    teacher = AdditiveModel(); teacher.load_state_dict(initial); teacher.to(device).eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    baseline = {domain: evaluate(teacher, selection, device, domain == 'styled') for domain in ['clean', 'styled']}
    save(run / 'baseline-selection.json', baseline)
    print(json.dumps({'baseline_selection': {domain: short_metrics(value)
                                             for domain, value in baseline.items()}}), flush=True)
    outcomes = {}
    for arm in ['clean-control', 'phone-style']:
        directory = run / arm; directory.mkdir()
        torch.manual_seed(protocol['seed']); rng = np.random.default_rng(protocol['seed'])
        model = AdditiveModel(); model.load_state_dict(initial); model.to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=.001)
        history, best = [], (-1., -1.)
        for epoch in range(1, 9):
            started = time.perf_counter(); model.train(); losses = []
            for _ in range(80):
                values = batch(rng, pools, controls, arm == 'phone-style')
                tensors = [torch.from_numpy(value).to(device) for value in values]
                optimizer.zero_grad(set_to_none=True)
                loss = paired_loss(model, teacher, *tensors)
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite training loss')
                loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 2.)
                optimizer.step(); losses.append(float(loss.detach().cpu()))
            evaluation = {domain: evaluate(model, selection, device, domain == 'styled') for domain in ['clean', 'styled']}
            score = selection_score(evaluation['clean'], evaluation['styled'])
            row = dict(epoch=epoch, loss=float(np.mean(losses)), seconds=time.perf_counter() - started,
                       score=score, clean=short_metrics(evaluation['clean']), styled=short_metrics(evaluation['styled']))
            history.append(row)
            if score > best:
                best = score
                torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, directory / 'Murmur.pt')
                save(directory / 'selected.json', dict(**row, results=evaluation))
            save(directory / 'history.json', history)
            print(json.dumps(dict(arm=arm, **row)), flush=True)
        selected = torch.load(directory / 'Murmur.pt', map_location='cpu', weights_only=True)
        differences = {k: float((v - initial[k]).abs().max()) for k, v in selected.items()
                       if v.is_floating_point() and not torch.equal(v, initial[k])}
        assert differences and all(torch.isfinite(value).all() for value in selected.values())
        proof = dict(optimizer_steps=640, selected_epoch=json.loads((directory / 'selected.json').read_text())['epoch'],
                     changed_tensors=len(differences), maximum_tensor_change=max(differences.values()),
                     weights_sha256=digest(directory / 'Murmur.pt'), private_clinical_targets_used=False,
                     regression_sets_loaded=False)
        save(directory / 'training-proof.json', proof); outcomes[arm] = proof
        del model, optimizer
        if device.type == 'mps':
            torch.mps.empty_cache()
    freeze = dict(protocol_sha256=digest(run / 'protocol.json'), data_sha256=digest(run / 'data.json'),
                  models=outcomes, threshold=.60, frozen_before_calibration=True)
    save(run / 'evaluation-freeze.json', freeze)
    report = dict(roles={}, models=outcomes, private_murmur_accuracy='Unavailable: no clinician reference labels',
                  limitations=protocol['limitations'], app_changed=False, regression_scored=False)
    models = {'baseline': teacher}
    for arm in outcomes:
        model = AdditiveModel(); model.load_state_dict(torch.load(run / arm / 'Murmur.pt', map_location='cpu', weights_only=True))
        models[arm] = model.to(device).eval()
    all_passed, added = True, 0
    for role, cohort in [('selection', selection), ('calibration', calibration)]:
        report['roles'][role] = {}
        for domain in ['clean', 'styled']:
            results = {name: evaluate(model, cohort, device, domain == 'styled') for name, model in models.items()}
            checks = promotion_checks(results['baseline'], results['phone-style'])
            all_passed &= all(checks.values())
            added += results['phone-style']['recordings']['detected_positive'] - results['baseline']['recordings']['detected_positive']
            report['roles'][role][domain] = dict(results=results, strict_candidate_checks=checks)
    report.update(development_gate_passed=bool(all_passed and added > 0),
                  decision='eligible_for_native_conversion_and_regression_only' if all_passed and added > 0
                  else 'retain_shipping_model; phone-style candidate is research only')
    assert shipping_hashes() == initial_shipping
    report['shipping_packages_unchanged'] = True
    save(run / 'comparison.json', report)
    save(run / 'complete.json', dict(models=outcomes, decision=report['decision'],
                                    comparison_sha256=digest(run / 'comparison.json'),
                                    shipping_packages_unchanged=True))
    print(json.dumps(dict(complete=True, decision=report['decision'], models=outcomes)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    train(parser.parse_args().run)
