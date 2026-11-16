"""Fit only declared global expert weights on selection; keep calibration closed."""
import argparse
import json
from pathlib import Path

import numpy as np

from m2d_murmur import HERE,sha,decide
from murmur_focus_metrics import aggregate,promotion_checks
from compare_m2d_native_heads import inputs,baselines
from evaluate_m2d_murmur import save

WEIGHTS=(.25,.50,.60,.75)


def blend(a,b,weight):
    p=(1-weight)*np.asarray(a['reading']['probabilities'])+weight*np.asarray(b['reading']['probabilities'])
    assert np.isfinite(p).all() and np.min(p)>=0 and np.max(p)<=1 and abs(p.sum()-1)<.001
    return dict(reading=dict(finding=decide(p),probabilities=p.tolist()),
        window_counts={'M':a['reading']['windows'],'expert':b['reading']['windows']})


def select(output):
    if output.exists():raise ValueError('Preserve mixture selection runs')
    context=inputs();rows=[r for r in context['rows'] if r['role']=='selection'];assert len(rows)==180
    v11=HERE/'generated/murmur-v11-m2d';v12=HERE/'generated/murmur-v12-targeted'
    experts={};sources={}
    for arm in ['paper','released']:
        path=v11/f'evaluation-{arm}/predictions.json';complete=json.loads((path.parent/'complete.json').read_text())
        assert sha(path)==complete['predictions_sha256']
        experts['v11_'+arm]=json.loads(path.read_text());sources['v11_'+arm]=dict(path=str(path),sha256=sha(path),kind='v11',arm=arm)
    path=v12/'selection/candidate-predictions.json'
    selected=json.loads((v12/'selection/selection-freeze.json').read_text())
    report=v12/'selection/selection-report.json';assert sha(report)==selected['selection_report_sha256']
    heads=json.loads(path.read_text())
    for name,p in heads.items():
        if name.endswith('__head'):
            key='v12_'+name[:-len('__head')];experts[key]=p
            sources[key]=dict(path=str(path),sha256=sha(path),kind='v12',head=name[:-len('__head')],
                heads_sha256=selected['heads_sha256'],encoder_sha256=selected['encoder_sha256'])
    assert len(experts)==15
    output.mkdir(parents=True);candidates={};predictions={}
    for expert,p in experts.items():
        for weight in WEIGHTS:
            key=f'{expert}__weight_{weight:.2f}';metrics={};checks={};predictions[key]={}
            for domain in ['native2k','styled']:
                base=baselines(context,domain)
                values={r['record']:blend(base[r['record']],p[domain][r['record']],weight) for r in rows}
                predictions[key][domain]=values;metrics[domain]=aggregate(rows,values)
                checks[domain]=promotion_checks(aggregate(rows,base),metrics[domain])
                checks[domain]['retain_v11_positive_detection']=metrics[domain]['recordings']['detected_positive']>=(30 if domain=='native2k' else 31)
            failures=[d+':'+k for d,c in checks.items() for k,ok in c.items() if not ok]
            candidates[key]=dict(expert=expert,weight=weight,metrics=metrics,checks=checks,failures=failures,eligible=not failures)
    eligible=[k for k,c in candidates.items() if c['eligible']]
    def rank(key):
        c=candidates[key];m=[v['recordings'] for v in c['metrics'].values()]
        return (len(c['failures']),-sum(v['detected_positive'] for v in m),sum(v['false_alarms'] for v in m),sum(v['total_unsure'] for v in m),key)
    chosen=min(eligible or list(candidates),key=rank);c=candidates[chosen]
    save(output/'candidate-predictions.json',predictions)
    save(output/'selection-report.json',dict(candidates=candidates,chosen=chosen,eligible_candidates=eligible,
        sources=sources,selection_only=True,independent_validation=False))
    save(output/'selection-freeze.json',dict(candidate=chosen,expert=c['expert'],expert_source=sources[c['expert']],
        weight=c['weight'],selection_constraints_passed=c['eligible'],
        selector_sha256=sha(Path(__file__)),manifest_sha256=sha(context['manifest']),
        baseline_predictions_sha256=sha(context['baseline_path']),selection_report_sha256=sha(output/'selection-report.json'),
        calibration_mixture_not_scored=True,wait_for_v13_joint_selection=True,independent_validation=False))
    print(json.dumps(dict(chosen=chosen,constraints_passed=c['eligible'],eligible_candidates=len(eligible),
        failures=c['failures'],recordings={d:m['recordings'] for d,m in c['metrics'].items()})),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    select(p.parse_args().output)
