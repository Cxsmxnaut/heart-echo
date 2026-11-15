"""Predefined native promotion checks; original test is retrospective regression only."""
import argparse
import json
from murmur_data import ROOT,save


def check(include_regression=False):
    folder=ROOT/'results/murmur-phase-m';roles=['selection','calibration']+(['test'] if include_regression else []);out={}
    for role in roles:
        summary=json.loads((folder/(role+'-summary.json')).read_text());a,b=summary['baseline'],summary['candidate']
        old_role='test' if role=='test' else 'validation'
        original={r['record']:r for r in json.loads((ROOT/f'results/murmur-v1/{old_role}-predictions.json').read_text())}
        rows=json.loads((folder/(role+'-predictions.json')).read_text())
        max_absent_increase=max(r['probabilities'][0]-original[r['record']]['probabilities'][0] for r in rows)
        max_present_decrease=max(original[r['record']]['probabilities'][1]-r['probabilities'][1] for r in rows)
        criteria=dict(positive_detection_gain=b['confusion_true_rows'][1][1]>a['confusion_true_rows'][1][1],
            false_alarm_increase_within_2pp=b['false_alarms']/b['known_negative_cases']<=a['false_alarms']/a['known_negative_cases']+.02+1e-12,
            unsure_increase_within_5pp=b['unsure']/b['total']<=a['unsure']/a['total']+.05+1e-12,
            no_extra_positive_as_absent=b['missed_positive_as_absent']<=a['missed_positive_as_absent'],
            negative_confidence_bound_verified=max_absent_increase<.0001,
            positive_confidence_bound_verified=max_present_decrease<.0001,
            no_extra_patient_positive_as_absent=summary['candidate_patient']['missed_positive_as_absent']<=summary['baseline_patient']['missed_positive_as_absent'],
            no_lost_patient_positives=summary['candidate_patient']['confusion_true_rows'][1][1]>=summary['baseline_patient']['confusion_true_rows'][1][1],
            known_noise_controls_unsure=summary['known_negative_controls']['candidate']=={'unsure':20})
        out[role]=dict(eligible=all(criteria.values()),criteria=criteria,baseline=a,candidate=b,
            baseline_patient=summary['baseline_patient'],candidate_patient=summary['candidate_patient'],
            phase_known_accuracy=summary['phase_known_accuracy'],
            phase_annotation_coverage=sum(map(sum,summary['phase_confusion_true_rows']))/(194*summary['records']),
            maximum_absent_probability_increase=max_absent_increase,maximum_present_probability_decrease=max_present_decrease,
            evidence=summary['evidence'])
    result=dict(candidate='M',eligible=all(v['eligible'] for v in out.values()),regression_included=include_regression,
        results=out,note='Promotion engineering comparison only. Selection/calibration reused during architecture development. Original120test groups were inspected in v1, so only retrospective regression. No independent clinical or iPhone accuracy claim. Unknown labels and all abstentions retained. No private or Watch data used.')
    save(folder/('acceptance-with-regression.json' if include_regression else 'development-acceptance.json'),result)
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--regression',action='store_true');a=p.parse_args();check(a.regression)
