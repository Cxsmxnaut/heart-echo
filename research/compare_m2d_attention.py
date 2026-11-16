"""Select one checkpoint per pooling arm, freeze both, then compare development."""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from m2d_attention import M2DDecisionHead, M2DAttentionMurmur
from m2d_murmur import M2DMurmur, HERE, sha, decide
from train_m2d_attention import SOURCE_FILES
from train_m2d_native_heads import windows, ENCODER_CHECKPOINT
from compare_m2d_native_heads import inputs, baselines
from evaluate_m2d_murmur import save, files, predict
from load_m2d_attention import load_model
from murmur_focus_metrics import aggregate, promotion_checks
from summarize_m2d_preserving import paired

DOMAINS = ('native2k', 'styled')


def code_hashes():
    names = set(SOURCE_FILES) | {'compare_m2d_attention.py', 'load_m2d_attention.py',
        'compare_m2d_native_heads.py', 'evaluate_m2d_murmur.py', 'phone_style.py',
        'summarize_m2d_preserving.py'}
    return {n:sha(HERE / n) for n in sorted(names)}


def read_wave(row, context, domain):
    key = row['record']
    if domain == 'native2k':
        path = context['native'] / 'audio' / (key + '.f32')
        assert sha(path) == context['native_records'][key]['native_audio_sha256']
        wave = np.fromfile(path, dtype='<f4')
    else:
        path = context['styled'][key]
        assert sha(path) == context['old_freeze']['input_sha256']['styled'][key]
        wave, rate = sf.read(path, dtype='float32')
        assert rate == 2000
    assert wave.ndim == 1 and len(wave) == context['native_records'][key]['samples']
    return wave, sha(path)


def new_stats():
    return dict(windows=0, nonuniform_windows=0, maximum_deviation_from_uniform=0.,
                sum_maximum_weight=0., sum_normalized_entropy=0.)


def add_stats(total, weights):
    weight = weights.detach().float()
    deviation = (weight - 1. / weight.shape[1]).abs().amax(1)
    total['windows'] += len(weight)
    total['nonuniform_windows'] += int((deviation > 1e-6).sum().cpu())
    total['maximum_deviation_from_uniform'] = max(total['maximum_deviation_from_uniform'],
                                                  float(deviation.max().cpu()))
    total['sum_maximum_weight'] += float(weight.amax(1).sum().cpu())
    entropy = -(weight * weight.clamp_min(1e-12).log()).sum(1) / math.log(weight.shape[1])
    total['sum_normalized_entropy'] += float(entropy.sum().cpu())


def finish_stats(value):
    n = value['windows']
    return dict(value, mean_maximum_frame_weight=value['sum_maximum_weight'] / n if n else None,
                mean_normalized_entropy=value['sum_normalized_entropy'] / n if n else None)


def reading(logits, count):
    p = torch.cat(logits).mean(0).softmax(0).numpy() if logits else np.array([0., 0., 1.])
    return {'reading':{'probabilities':p.tolist(), 'finding':decide(p), 'windows':count}}


def run_heads(rows, context, baseline, heads, device, frame_count, output):
    predictions = {key:{d:{} for d in DOMAINS} for key in heads}
    reference = {d:{} for d in DOMAINS}
    hashes = {d:{} for d in DOMAINS}
    attention = {key:{d:new_stats() for d in DOMAINS}
                 for key,head in heads.items() if head.pooling == 'attention'}
    with torch.inference_mode():
        for index, row in enumerate(rows, 1):
            key = row['record']
            for domain in DOMAINS:
                wave, fingerprint = read_wave(row, context, domain)
                hashes[domain][key] = fingerprint
                crops = windows(wave)
                logits = {name:[] for name in heads}
                original = []
                for start in range(0, len(crops), 8):
                    mel = baseline.features(torch.from_numpy(crops[start:start + 8]).to(device))
                    frames = baseline.runtime.encode_lms(baseline.runtime.normalize_batch(mel)).float()
                    assert frames.shape[1] == frame_count and torch.isfinite(frames).all()
                    original.append(baseline.classifier(baseline.norm(frames.mean(1))).float().cpu())
                    for name, head in heads.items():
                        if head.pooling == 'attention':
                            value, weight = head(frames, return_weights=True)
                            add_stats(attention[name][domain], weight)
                        else:
                            value = head(frames)
                        assert torch.isfinite(value).all()
                        logits[name].append(value.float().cpu())
                reference[domain][key] = reading(original, len(crops))
                for name in heads:
                    predictions[name][domain][key] = reading(logits[name], len(crops))
            if index % 50 == 0:
                print(json.dumps(dict(stage='attention_comparison', recordings=index,
                                      total=len(rows), heads=len(heads))), flush=True)
                save(output / 'partial-predictions.json', predictions)
    evidence = {name:{d:finish_stats(value) for d,value in domains.items()}
                for name,domains in attention.items()}
    return predictions, reference, hashes, evidence


def compare_probabilities(rows, actual, expected, label):
    maximum, differences = 0., []
    for row in rows:
        key = row['record']
        a, b = actual[key]['reading'], expected[key]['reading']
        assert a['windows'] == b['windows'], (label, key, 'window count')
        maximum = max(maximum, float(np.abs(np.asarray(a['probabilities']) - b['probabilities']).max()))
        if a['finding'] != b['finding']:
            differences.append(key)
    assert maximum < .001 and not differences, (label, maximum, differences)
    return maximum


def prior_predictions():
    path = HERE / 'generated/murmur-v11-m2d/evaluation-released/predictions.json'
    complete = json.loads((path.parent / 'complete.json').read_text())
    assert sha(path) == complete['predictions_sha256']
    return json.loads(path.read_text()), path


def balanced(metrics):
    matrix = np.asarray(metrics['recordings']['matrix'])
    assert (matrix.sum(1) > 0).all()
    return float(np.mean(np.diag(matrix) / matrix.sum(1)))


def export_and_verify(baseline, state, chosen, rows, context, expected, device, output):
    directory = output / 'selected-model'
    directory.mkdir()
    model = M2DAttentionMurmur(baseline).to(device).eval()
    model.head.load_state_dict(state, strict=True)
    for k,v in baseline.runtime.state_dict().items():
        assert torch.equal(model.runtime.state_dict()[k], v)
    path = directory / 'M2D-attention.pt'
    torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()}, path)
    save(directory / 'manifest.json', dict(pooling='learned_attention', candidate=chosen,
        weights_sha256=sha(path), initializer_sha256=ENCODER_CHECKPOINT,
        source_sha256=code_hashes(), research_only=True, app_updated=False,
        independent_validation=False, real_phone_accuracy_measured=False))
    del model
    loaded = load_model(path, HERE / 'cache/m2d-weights', device)
    samples = [r for target in [0,1,2] for r in [x for x in rows if x['target'] == target][:2]]
    assert len(samples) == 6
    checks, weights_sample = [], {}
    with torch.inference_mode():
        for row in samples:
            for domain in DOMAINS:
                wave, _ = read_wave(row, context, domain)
                actual = predict(loaded, wave, 2000, device)
                diff = compare_probabilities([row], {row['record']:actual}, expected[domain], 'full attention reload')
                checks.append(dict(record=row['record'], domain=domain, maximum_probability_difference=diff))
                if row['target'] not in weights_sample:
                    crops = windows(wave)
                    if len(crops):
                        mel = loaded.features(torch.from_numpy(crops[:1]).to(device))
                        _, weights = loaded(mel, return_weights=True)
                        weights_sample[row['target']] = dict(record=row['record'], domain=domain,
                                                             time_weights=weights[0].cpu().tolist())
    assert any(np.max(np.abs(np.asarray(v['time_weights']) - 1. / len(v['time_weights']))) > 1e-6
               for v in weights_sample.values())
    proof = dict(full_attention_checkpoint_reloaded=True, examples=len(checks), checks=checks,
                 sample_weights=weights_sample, weights_sha256=sha(path))
    save(output / 'full-inference-verification.json', proof)
    return path, proof


def main(a):
    os.umask(0o077)
    torch.set_num_threads(2)
    if a.output.exists():
        raise ValueError('Preserve completed/partial comparisons')
    source = a.run / 'artifacts'
    verification = json.loads((a.run / 'verification.json').read_text())
    assert verification['status'] == 'verified'
    assert sha(source / 'attention-heads.pt') == verification['heads_sha256']
    assert sha(a.encoder) == verification['encoder_sha256'] == ENCODER_CHECKPOINT
    protocol = json.loads((source / 'protocol.json').read_text())
    for name, fingerprint in protocol['source_sha256'].items():
        assert sha(HERE / name) == fingerprint, name
    all_states = torch.load(source / 'attention-heads.pt', map_location='cpu', weights_only=True)
    context = inputs()
    prior, prior_path = prior_predictions()
    if a.stage == 'evaluate':
        frozen = json.loads(a.freeze.read_text())
        assert frozen['comparator_sources_sha256'] == code_hashes()
        assert frozen['heads_sha256'] == sha(source / 'attention-heads.pt')
        assert frozen['encoder_sha256'] == sha(a.encoder)
        assert frozen['manifest_sha256'] == sha(context['manifest'])
        assert frozen['baseline_predictions_sha256'] == sha(context['baseline_path'])
        assert frozen['prior_v11_predictions_sha256'] == sha(prior_path)
        assert frozen['selection_report_sha256'] == sha(a.freeze.parent / 'selection-report.json')
        assert frozen['selection_predictions_sha256'] == sha(a.freeze.parent / 'predictions.json')
        assert frozen['full_attention_weights_sha256'] == sha(a.freeze.parent / 'selected-model/M2D-attention.pt')
        assert frozen['full_attention_manifest_sha256'] == sha(a.freeze.parent / 'selected-model/manifest.json')
        chosen = frozen['chosen']
        states = {name:all_states[name] for name in chosen.values()}
        rows = [r for r in context['rows'] if r['role'] == 'calibration']
    else:
        states = all_states
        rows = [r for r in context['rows'] if r['role'] == 'selection']
    assert len(rows) == (180 if a.stage == 'select' else 187)
    a.output.mkdir(parents=True)
    save(a.output / 'input-freeze.json', dict(stage=a.stage, comparator_sources_sha256=code_hashes(),
        heads_sha256=sha(source / 'attention-heads.pt'), encoder_sha256=sha(a.encoder),
        manifest_sha256=sha(context['manifest']), baseline_predictions_sha256=sha(context['baseline_path']),
        app_files=context['app_files'], independent_validation=False))
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    baseline = M2DMurmur(HERE / 'cache/m2d-weights').eval()
    baseline.load_state_dict(torch.load(a.encoder, map_location='cpu', weights_only=True))
    baseline.requires_grad_(False)
    baseline.to(device)
    heads = {}
    for name, state in states.items():
        head = M2DDecisionHead(baseline.norm, baseline.classifier, name.split('_')[0]).to(device).eval()
        head.load_state_dict(state, strict=True)
        heads[name] = head
    frame_count = json.loads((source / 'data-audit.json').read_text())['frame_count']
    predictions, reference, hashes, attention = run_heads(rows, context, baseline, heads, device, frame_count, a.output)
    save(a.output / 'input-fingerprints.json', hashes)
    save(a.output / 'attention-evidence.json', attention)
    reference_error = {d:compare_probabilities(rows, reference[d], prior[d], 'frozen V11 ' + d) for d in DOMAINS}
    if a.stage == 'select':
        remote = json.loads((source / 'selection-predictions.json').read_text())
        parity = {name:compare_probabilities(rows, values['native2k'], remote[name]['native2k'], name)
                  for name,values in predictions.items()}
        candidates = {}
        for name, values in predictions.items():
            metrics = {d:aggregate(rows, values[d]) for d in DOMAINS}
            scores = [balanced(m) for m in metrics.values()]
            checks = {d:promotion_checks(aggregate(rows, baselines(context, d)), metrics[d]) for d in DOMAINS}
            for d in DOMAINS:
                checks[d]['retain_v11_positive_detection'] = metrics[d]['recordings']['detected_positive'] >= (30 if d == 'native2k' else 31)
            candidates[name] = dict(metrics=metrics, checks=checks,
                lower_balanced_recall=min(scores), mean_balanced_recall=float(np.mean(scores)),
                epoch=int(name.split('_')[-1]))
        def rank(name):
            c = candidates[name]
            return (c['lower_balanced_recall'], c['mean_balanced_recall'],
                    -sum(m['recordings']['false_alarms'] for m in c['metrics'].values()), -c['epoch'])
        chosen = {arm:max((n for n in candidates if n.startswith(arm + '_')), key=rank)
                  for arm in ['mean', 'attention']}
        save(a.output / 'predictions.json', predictions)
        save(a.output / 'selection-report.json', dict(chosen=chosen, candidates=candidates,
            cloud_local_maximum_probability_difference=max(parity.values()),
            cloud_local_by_head=parity, prior_v11_maximum_probability_difference=reference_error,
            independent_validation=False))
        path, full_proof = export_and_verify(baseline, states[chosen['attention']], chosen['attention'],
            rows, context, predictions[chosen['attention']], device, a.output)
        freeze = dict(chosen=chosen, heads_sha256=sha(source / 'attention-heads.pt'),
            encoder_sha256=sha(a.encoder), comparator_sources_sha256=code_hashes(),
            manifest_sha256=sha(context['manifest']), baseline_predictions_sha256=sha(context['baseline_path']),
            prior_v11_predictions_sha256=sha(prior_path),
            selection_report_sha256=sha(a.output / 'selection-report.json'),
            selection_predictions_sha256=sha(a.output / 'predictions.json'),
            full_attention_weights_sha256=sha(path), full_attention_inference_verified=full_proof['examples'],
            full_attention_manifest_sha256=sha(path.parent / 'manifest.json'),
            selected_before_v15_calibration_audio=True, independent_validation=False,
            evaluation_plan='Compare both frozen choices regardless of promotion eligibility; no new choices on calibration',
            app_updated=False)
        save(a.output / 'selection-freeze.json', freeze)
        print(json.dumps(dict(selection_complete=True, chosen=chosen,
            cloud_local_maximum_probability_difference=max(parity.values()),
            full_attention_inference_checks=full_proof['examples'],
            recordings={arm:{d:m['recordings'] for d,m in candidates[name]['metrics'].items()}
                        for arm,name in chosen.items()})), flush=True)
    else:
        existing = json.loads((a.freeze.parent / 'predictions.json').read_text())
        for name in chosen.values():
            for d in DOMAINS:
                assert set(existing[name][d]).isdisjoint(predictions[name][d])
                predictions[name][d] = dict(existing[name][d], **predictions[name][d])
        all_rows = [r for r in context['rows'] if r['role'] in ['selection', 'calibration']]
        assert len(all_rows) == 367
        metrics, checks = {}, {}
        for d in DOMAINS:
            metrics[d], checks[d] = {}, {}
            for role in ['selection', 'calibration', 'combined']:
                cohort = all_rows if role == 'combined' else [r for r in all_rows if r['role'] == role]
                models = {'app-M':aggregate(cohort, baselines(context, d)),
                          'frozen-V11':aggregate(cohort, prior[d])}
                for arm,name in chosen.items():
                    models[arm] = aggregate(cohort, predictions[name][d])
                metrics[d][role] = models
                checks[d][role] = {arm:promotion_checks(models['app-M'], models[arm]) for arm in chosen}
                for arm in chosen:
                    checks[d][role][arm]['retain_v11_positive_detection'] = (
                        models[arm]['recordings']['detected_positive'] >= models['frozen-V11']['recordings']['detected_positive'])
        passed = all(ok for d in checks.values() for role in d.values() for ok in role['attention'].values())
        delta_keys = ['detected_positive', 'positive_called_absent', 'false_alarms', 'correct_absent', 'total_unsure']
        deltas = {d:{level:{k:metrics[d]['combined']['attention'][level][k] - metrics[d]['combined']['mean'][level][k]
                            for k in delta_keys} for level in ['recordings', 'linked_people']} for d in DOMAINS}
        paired_results = {d:paired(all_rows, baselines(context, d), prior[d], predictions[chosen['attention']][d])
                          for d in DOMAINS}
        save(a.output / 'predictions.json', predictions)
        save(a.output / 'comparison.json', dict(chosen=chosen, metrics=metrics, checks=checks,
            attention_minus_matched_mean=deltas, paired=paired_results,
            attention_development_gate_passed=passed, prior_v11_probability_difference=reference_error,
            independent_validation=False, real_phone_accuracy_measured=False, app_updated=False))
        save(a.output / 'complete.json', dict(status='attention_comparison_complete',
            attention_development_gate_passed=passed, selection_freeze_sha256=sha(a.freeze),
            comparison_sha256=sha(a.output / 'comparison.json'), predictions_sha256=sha(a.output / 'predictions.json'),
            full_attention_weights_sha256=frozen['full_attention_weights_sha256'], app_updated=False))
        print(json.dumps(dict(comparison_complete=True, attention_development_gate_passed=passed,
            recordings={d:{arm:metrics[d]['combined'][arm]['recordings'] for arm in chosen} for d in DOMAINS})), flush=True)
    assert files(context['app']) == context['app_files']


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=['select', 'evaluate'], required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--freeze', type=Path)
    p.add_argument('--encoder', type=Path,
                   default=HERE / 'generated/murmur-v11-m2d/released-source-stage/artifacts/M2D.pt')
    main(p.parse_args())
