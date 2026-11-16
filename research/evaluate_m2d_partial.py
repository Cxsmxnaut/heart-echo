"""Score a frozen partial V12 improvement without relaxing the primary goal."""
import argparse
import json
import os
from pathlib import Path

import torch

from compare_m2d_native_heads import inputs, baselines, extract, route_reading
from evaluate_m2d_murmur import save
from m2d_murmur import HERE, M2DMurmur, sha
from murmur_focus_metrics import aggregate, promotion_checks
from train_m2d_native_heads import select_predictions, ENCODER_CHECKPOINT
from summarize_m2d_preserving import paired


def main(a):
    os.umask(0o077)
    torch.set_num_threads(2)
    if a.output.exists():
        raise ValueError('Preserve completed/partial secondary checks')
    v12 = HERE / 'generated/murmur-v12-targeted'
    selected = v12 / 'selection'
    frozen = json.loads((selected / 'selection-freeze.json').read_text())
    report_path = selected / 'selection-report.json'
    assert sha(report_path) == frozen['selection_report_sha256']
    report = json.loads(report_path.read_text())
    candidate = 'positive_cost_12_epoch_16__conservative_override'
    assert frozen['candidate'] == report['chosen'] == candidate
    assert not frozen['selection_constraints_passed']
    expected_failures = {d + ':retain_v11_positive_detection' for d in ['native2k', 'styled']}
    assert set(report['candidates'][candidate]['failures']) == expected_failures
    assert sha(HERE / 'compare_m2d_native_heads.py') == frozen['comparator_sha256']
    source = v12 / 'source-stage/artifacts'
    proof = json.loads((source.parent / 'verification.json').read_text())
    assert proof['status'] == 'verified'
    heads_path = source / 'native-heads.pt'
    assert sha(heads_path) == frozen['heads_sha256'] == proof['heads_sha256']
    encoder = HERE / 'generated/murmur-v11-m2d/released-source-stage/artifacts/M2D.pt'
    assert sha(encoder) == frozen['encoder_sha256'] == ENCODER_CHECKPOINT
    context = inputs()
    assert sha(context['manifest']) == frozen['manifest_sha256']
    assert sha(context['baseline_path']) == frozen['baseline_predictions_sha256']
    predictions_path = selected / 'candidate-predictions.json'
    predictions = json.loads(predictions_path.read_text())[candidate]
    cal = [r for r in context['rows'] if r['role'] == 'calibration']
    rows = [r for r in context['rows'] if r['role'] in ['selection', 'calibration']]
    assert len(cal) == 187 and len(rows) == 367
    assert all(len(p) == 180 for p in predictions.values())
    a.output.mkdir(parents=True)
    save(a.output / 'comparison-freeze.json', {
        'candidate': candidate, 'head': frozen['head'], 'route': frozen['route'],
        'secondary_partial_check': True, 'primary_constraints_passed': False,
        'head_sha256': sha(heads_path), 'encoder_sha256': sha(encoder),
        'selection_freeze_sha256': sha(selected / 'selection-freeze.json'),
        'selection_predictions_sha256': sha(predictions_path),
        'baseline_predictions_sha256': sha(context['baseline_path']),
        'manifest_sha256': sha(context['manifest']),
        'sources_sha256': {n: sha(HERE / n) for n in [
            'evaluate_m2d_partial.py', 'compare_m2d_native_heads.py',
            'train_m2d_native_heads.py', 'evaluate_m2d_murmur.py',
            'murmur_focus_metrics.py', 'summarize_m2d_preserving.py']},
        'frozen_before_this_candidate_calibration_audio': True,
        'independent_validation': False, 'real_phone_accuracy_measured': False,
        'app_updated': False,
    })
    head = torch.load(heads_path, map_location='cpu', weights_only=True)[frozen['head']]
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model = M2DMurmur(HERE / 'cache/m2d-weights')
    model.load_state_dict(torch.load(encoder, map_location='cpu', weights_only=True))
    model.to(device).eval()
    features, fingerprints = extract(cal, context, model, device)
    for domain in ['native2k', 'styled']:
        new = select_predictions(head, features[domain], torch.device('cpu'))
        base = baselines(context, domain)
        for r in cal:
            k = r['record']
            assert k not in predictions[domain]
            predictions[domain][k] = route_reading(new[k], base[k], frozen['route'])
    save(a.output / 'predictions.json', predictions)
    save(a.output / 'calibration-input-fingerprints.json', fingerprints)
    metrics, checks = {}, {}
    for domain in ['native2k', 'styled']:
        metrics[domain], checks[domain] = {}, {}
        base = baselines(context, domain)
        for role in ['selection', 'calibration', 'combined']:
            cohort = rows if role == 'combined' else [r for r in rows if r['role'] == role]
            b, c = aggregate(cohort, base), aggregate(cohort, predictions[domain])
            metrics[domain][role] = {'app-M': b, 'partial-V12': c}
            checks[domain][role] = promotion_checks(b, c)
    prior_path = HERE / 'generated/murmur-v11-m2d/evaluation-released/predictions.json'
    prior_complete = json.loads((prior_path.parent / 'complete.json').read_text())
    assert sha(prior_path) == prior_complete['predictions_sha256']
    prior = json.loads(prior_path.read_text())
    same_recordings = {d: paired(rows, baselines(context, d), prior[d], predictions[d])
                       for d in ['native2k', 'styled']}
    passed = all(ok for domain in checks.values() for role in domain.values() for ok in role.values())
    result = dict(candidate=candidate, secondary_partial_check=True,
                  primary_constraints_passed=False, all_original_M_checks_passed=passed,
                  metrics=metrics, checks=checks, paired=same_recordings,
                  independent_validation=False, real_phone_accuracy_measured=False, app_updated=False)
    save(a.output / 'comparison.json', result)
    save(a.output / 'complete.json', dict(status='partial_comparison_complete',
         comparison_sha256=sha(a.output / 'comparison.json'),
         predictions_sha256=sha(a.output / 'predictions.json'),
         freeze_sha256=sha(a.output / 'comparison-freeze.json')))
    print(json.dumps(dict(secondary_check_complete=True, all_original_M_checks_passed=passed,
        recordings={d: metrics[d]['combined']['partial-V12']['recordings'] for d in metrics})), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args())
