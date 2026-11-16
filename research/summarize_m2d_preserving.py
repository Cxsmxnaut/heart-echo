"""Report paired gains/losses without changing the frozen V13 selection rule."""
import argparse
import json
from pathlib import Path

from compare_m2d_native_heads import inputs, baselines
from evaluate_m2d_murmur import save
from m2d_murmur import HERE, sha
from murmur_focus_metrics import aggregate


def paired(rows, baseline, previous, candidate):
    positive = {r['record'] for r in rows if r['target'] == 1}
    detected = lambda p: {k for k in positive if p[k]['reading']['finding'] == 'present'}
    old, prior, new = map(detected, (baseline, previous, candidate))
    prior_gains = prior - old
    retained, lost = prior_gains & new, prior_gains - new
    assert retained.isdisjoint(lost) and retained | lost == prior_gains
    transition = [[0] * 3 for _ in range(3)]
    labels = {'absent': 0, 'present': 1, 'unsure': 2}
    for r in rows:
        k = r['record']
        transition[labels[baseline[k]['reading']['finding']]][labels[candidate[k]['reading']['finding']]] += 1
    assert sum(map(sum, transition)) == len(rows)
    return {
        'recordings': len(rows),
        'positive_count': len(positive),
        'M_detections': len(old),
        'V11_detections': len(prior),
        'candidate_detections': len(new),
        'V11_extra_detections_over_M': sorted(prior_gains),
        'V11_extra_detections_retained': sorted(retained),
        'V11_extra_detections_lost': sorted(lost),
        'M_detections_lost': sorted(old - new),
        'detections_gained_over_M': sorted(new - old),
        'all_V11_detections_lost': sorted(prior - new),
        'M_to_candidate_transition_order': ['absent', 'present', 'unsure'],
        'M_to_candidate_transition_matrix': transition,
        'metrics': {name: aggregate(rows, p) for name, p in [
            ('app-M', baseline), ('V11', previous), ('candidate', candidate)]},
    }


def main(a):
    if a.output.exists():
        raise ValueError('Preserve completed paired reports')
    frozen = json.loads((a.selection / 'selection-freeze.json').read_text())
    report_path = a.selection / 'selection-report.json'
    assert sha(report_path) == frozen['selection_report_sha256']
    report = json.loads(report_path.read_text())
    assert report['chosen'] == frozen['candidate']
    context = inputs()
    if a.evaluation:
        complete = json.loads((a.evaluation / 'complete.json').read_text())
        assert frozen['selection_constraints_passed']
        assert complete['selection_freeze_sha256'] == sha(a.selection / 'selection-freeze.json')
        assert complete['comparison_sha256'] == sha(a.evaluation / 'comparison.json')
        assert complete['predictions_sha256'] == sha(a.evaluation / 'predictions.json')
        predictions = json.loads((a.evaluation / 'predictions.json').read_text())
        roles = ['selection', 'calibration']
    else:
        assert frozen['candidate_predictions_sha256'] == sha(a.selection / 'candidate-predictions.json')
        predictions = json.loads((a.selection / 'candidate-predictions.json').read_text())[frozen['candidate']]
        roles = ['selection']
    rows = [r for r in context['rows'] if r['role'] in roles]
    assert len(rows) == (367 if a.evaluation else 180)
    prior_path = HERE / 'generated/murmur-v11-m2d/evaluation-released/predictions.json'
    prior_complete = json.loads((prior_path.parent / 'complete.json').read_text())
    assert sha(prior_path) == prior_complete['predictions_sha256']
    prior = json.loads(prior_path.read_text())
    result = {
        'candidate': frozen['candidate'],
        'roles': roles,
        'selection_constraints_passed': frozen['selection_constraints_passed'],
        'changes_selection_or_decision_rules': False,
        'independent_validation': False,
        'real_phone_accuracy_measured': False,
        'domains': {d: paired(rows, baselines(context, d), prior[d], predictions[d])
                    for d in ['native2k', 'styled']},
        'source_sha256': sha(Path(__file__)),
    }
    save(a.output, result)
    print(json.dumps({d: {k: v[k] for k in [
        'M_detections', 'V11_detections', 'candidate_detections',
        'V11_extra_detections_retained', 'V11_extra_detections_lost']}
        for d, v in result['domains'].items()}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--evaluation', type=Path)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args())
