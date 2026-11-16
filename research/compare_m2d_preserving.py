"""Choose a V13 snapshot/route on selection, freeze it, then score calibration."""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from m2d_murmur import HERE,M2DMurmur,sha
from murmur_focus_metrics import aggregate,promotion_checks
from evaluate_m2d_murmur import predict,files,save
from compare_m2d_native_heads import inputs,baselines,route_reading,ROUTES
from select_m2d_blend import blend

METHODS=ROUTES+tuple(f'mixture_{w:.2f}' for w in [.25,.50,.60,.75])


def combine(head,baseline,method):
    assert method in METHODS
    return blend(baseline,head,float(method.split('_')[1])) if method.startswith('mixture_') else route_reading(head,baseline,method)


def waveforms(rows,context):
    waves={d:{} for d in ['native2k','styled']};hashes={d:{} for d in waves}
    for r in rows:
        p=context['native']/'audio'/(r['record']+'.f32')
        assert sha(p)==context['native_records'][r['record']]['native_audio_sha256']
        x=np.fromfile(p,dtype='<f4');assert len(x)==context['native_records'][r['record']]['samples']
        styled=context['styled'][r['record']]
        assert sha(styled)==context['old_freeze']['input_sha256']['styled'][r['record']]
        y,rate=sf.read(styled,dtype='float32');assert rate==2000 and len(y)==len(x)
        waves['native2k'][r['record']]=x;waves['styled'][r['record']]=y
        hashes['native2k'][r['record']]=sha(p);hashes['styled'][r['record']]=sha(styled)
    return waves,hashes


def predictions(model,device,rows,waves,epoch):
    result={d:{} for d in waves}
    for i,r in enumerate(rows,1):
        for d in waves:result[d][r['record']]=predict(model,waves[d][r['record']],2000,device)
        if i%50==0:print(json.dumps(dict(stage='preserving_comparison',epoch=epoch,recordings=i,total=len(rows))),flush=True)
    return result


def file_hashes():
    return {name:sha(HERE/name) for name in ['compare_m2d_preserving.py','compare_m2d_native_heads.py','evaluate_m2d_murmur.py','murmur_focus_metrics.py','select_m2d_blend.py']}


def main(a):
    os.umask(0o077);torch.set_num_threads(2)
    if a.output.exists():raise ValueError('Preserve completed/partial comparisons')
    proof=json.loads((a.run/'verification.json').read_text());assert proof['status']=='verified'
    source=a.run/'artifacts';protocol=json.loads((source/'protocol.json').read_text())
    for name,h in protocol['source_sha256'].items():assert sha(HERE/name)==h,name
    for epoch,entry in proof['snapshots'].items():assert sha(source/f'M2D-epoch{epoch}.pt')==entry['weights_sha256']
    context=inputs()
    if a.stage=='evaluate':
        frozen=json.loads(a.freeze.read_text())
        assert frozen['selection_constraints_passed'],'Keep calibration closed for an ineligible model'
        assert frozen['comparator_sources_sha256']==file_hashes()
        assert frozen['manifest_sha256']==sha(context['manifest'])
        assert frozen['baseline_predictions_sha256']==sha(context['baseline_path'])
        assert frozen['weights_sha256']==sha(source/f"M2D-epoch{frozen['epoch']}.pt")
        epochs=[frozen['epoch']]
    else:epochs=[4,8,12]
    rows=[r for r in context['rows'] if r['role'] in (['selection'] if a.stage=='select' else ['selection','calibration'])]
    assert len(rows)==(180 if a.stage=='select' else 367)
    a.output.mkdir(parents=True)
    save(a.output/'input-freeze.json',dict(stage=a.stage,comparator_sources_sha256=file_hashes(),
        manifest_sha256=sha(context['manifest']),baseline_predictions_sha256=sha(context['baseline_path']),
        app_model_files=context['app_files'],independent_validation=False,real_phone_accuracy_measured=False))
    waves,hashes=waveforms(rows,context);save(a.output/'input-fingerprints.json',hashes)
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model=M2DMurmur(HERE/'cache/m2d-weights').to(device).eval()
    raw={};parity=[];decision_differences=[]
    for epoch in epochs:
        model.load_state_dict(torch.load(source/f'M2D-epoch{epoch}.pt',map_location='cpu',weights_only=True))
        raw[str(epoch)]=predictions(model,device,rows,waves,epoch)
        if a.stage=='select':
            cloud=json.loads((source/f'selection-epoch{epoch}.json').read_text())['native2k']
            for r in rows:
                x=raw[str(epoch)]['native2k'][r['record']]['reading'];y=cloud[r['record']]['reading']
                assert x['windows']==y['windows']
                parity.append(float(np.abs(np.asarray(x['probabilities'])-y['probabilities']).max()))
                if x['finding']!=y['finding']:decision_differences.append([epoch,r['record']])
        save(a.output/'partial-model-predictions.json',raw)
    if a.stage=='select':
        assert parity and max(parity)<.001,('Cloud/local model mismatch',max(parity))
        assert not decision_differences,('Threshold decisions differ by device',decision_differences)
        candidates={};routed={}
        for epoch in epochs:
            for route in METHODS:
                key=f'epoch{epoch}__{route}';metrics={};checks={};routed[key]={}
                for d in waves:
                    base=baselines(context,d)
                    p={r['record']:combine(raw[str(epoch)][d][r['record']],base[r['record']],route) for r in rows}
                    routed[key][d]=p;metrics[d]=aggregate(rows,p)
                    checks[d]=promotion_checks(aggregate(rows,base),metrics[d])
                    checks[d]['retain_v11_positive_detection']=metrics[d]['recordings']['detected_positive']>=(30 if d=='native2k' else 31)
                failures=[d+':'+k for d,c in checks.items() for k,ok in c.items() if not ok]
                candidates[key]=dict(epoch=epoch,route=route,metrics=metrics,checks=checks,failures=failures,eligible=not failures)
        eligible=[k for k,c in candidates.items() if c['eligible']]
        def rank(key):
            c=candidates[key];m=[v['recordings'] for v in c['metrics'].values()]
            return (len(c['failures']),-sum(x['detected_positive'] for x in m),sum(x['false_alarms'] for x in m),sum(x['total_unsure'] for x in m),key)
        chosen=min(eligible or list(candidates),key=rank);c=candidates[chosen]
        save(a.output/'model-predictions.json',raw);save(a.output/'candidate-predictions.json',routed)
        save(a.output/'selection-report.json',dict(candidates=candidates,chosen=chosen,eligible_candidates=eligible,
            maximum_cloud_local_probability_difference=max(parity),device_decision_differences=decision_differences,
            selection_only=True,independent_validation=False))
        freeze=dict(candidate=chosen,epoch=c['epoch'],route=c['route'],selection_constraints_passed=c['eligible'],
            weights_sha256=sha(source/f"M2D-epoch{c['epoch']}.pt"),comparator_sources_sha256=file_hashes(),
            manifest_sha256=sha(context['manifest']),baseline_predictions_sha256=sha(context['baseline_path']),
            selection_report_sha256=sha(a.output/'selection-report.json'),chosen_before_v13_calibration=True,
            candidate_predictions_sha256=sha(a.output/'candidate-predictions.json'),
            independent_validation=False,app_update_authorized=False)
        save(a.output/'selection-freeze.json',freeze)
        print(json.dumps(dict(selection_complete=True,chosen=chosen,eligible_candidates=len(eligible),
            constraints_passed=c['eligible'],failures=c['failures'],recordings={d:m['recordings'] for d,m in c['metrics'].items()})),flush=True)
    else:
        routed={};metrics={};checks={};epoch=frozen['epoch']
        for d in waves:
            base=baselines(context,d)
            routed[d]={r['record']:combine(raw[str(epoch)][d][r['record']],base[r['record']],frozen['route']) for r in rows}
            metrics[d]={};checks[d]={}
            for role in ['selection','calibration','combined']:
                cohort=rows if role=='combined' else [r for r in rows if r['role']==role]
                b=aggregate(cohort,base);c=aggregate(cohort,routed[d])
                metrics[d][role]={'app-M':b,'V13':c};checks[d][role]=promotion_checks(b,c)
            checks[d]['combined']['retain_v11_positive_detection']=metrics[d]['combined']['V13']['recordings']['detected_positive']>=(58 if d=='native2k' else 59)
        passed=all(v for domain in checks.values() for role in domain.values() for v in role.values())
        save(a.output/'predictions.json',routed)
        save(a.output/'comparison.json',dict(candidate=frozen['candidate'],metrics=metrics,checks=checks,
            development_gate_passed=passed,independent_validation=False,real_phone_accuracy_measured=False,app_updated=False))
        save(a.output/'complete.json',dict(status='v13_comparison_complete',development_gate_passed=passed,
            comparison_sha256=sha(a.output/'comparison.json'),predictions_sha256=sha(a.output/'predictions.json'),
            selection_freeze_sha256=sha(a.freeze),shipping_model_unchanged=True))
        print(json.dumps(dict(evaluation_complete=True,development_gate_passed=passed)),flush=True)
    assert files(context['app'])==context['app_files']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['select','evaluate'],required=True)
    for name in ['run','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--freeze',type=Path);main(p.parse_args())
