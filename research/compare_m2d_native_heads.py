"""Select V12 using selection people only, then evaluate the frozen candidate."""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch.nn import functional as F

from m2d_murmur import HERE,M2DMurmur,sha,decide
from train_m2d_native_heads import windows,select_predictions,ENCODER_CHECKPOINT
from murmur_focus_metrics import aggregate,promotion_checks
from phone_style import assert_person_split
from evaluate_m2d_murmur import files,save

ROUTES=('head','fallback','preserve_positive','conservative_override')


def route_reading(head,baseline,route):
    h=head['reading'];b=baseline['reading']
    if route=='head':return head
    if route=='conservative_override':
        return head if h['finding']=='present' and h['probabilities'][1]>=.90 else baseline
    if route=='preserve_positive' and b['finding']=='present':return baseline
    return baseline if h['finding']=='unsure' else head


def inputs():
    ml=HERE.parent/'ChestBPM/ML';path=ml/'murmur-phase-manifest.json'
    all_rows=[r for r in json.loads(path.read_text())['records'] if r['role']!='test']
    assert_person_split(all_rows)
    native=ml/'generated/murmur-native-development'
    manifest=json.loads((native/'manifest.json').read_text());assert manifest['phase_manifest_sha256']==sha(path)
    v10=HERE/'generated/murmur-v10-two-stage/local-adapter'
    summary=json.loads((v10/'summary.json').read_text())
    assert sha(v10/'native-predictions.json')==summary['artifacts_sha256']['local-adapter/native-predictions.json']
    baseline=json.loads((v10/'native-predictions.json').read_text())
    old_freeze=json.loads((v10/'native-freeze.json').read_text())
    styled={r['id']:Path(r['path']) for r in json.loads((v10/'native-styled-requests.json').read_text())}
    expected=json.loads((HERE/'results/murmur-focus-baseline-freeze.json').read_text())
    app=HERE.parent/'HeartEcho/Models/Murmur.mlpackage'
    reader=HERE.parent/'HeartEcho/Engine/MurmurAnalysis.swift'
    assert files(app)==expected['model_files'] and sha(reader)==old_freeze['sources']['MurmurAnalysis.swift']
    return dict(rows=all_rows,native=native,manifest=path,baseline=baseline,old_freeze=old_freeze,
        native_records={r['record']:r for r in manifest['records']},styled=styled,
        app=app,app_files=expected['model_files'],reader=reader,baseline_path=v10/'native-predictions.json')


def load_run(a):
    source=a.run/'artifacts'
    proof=json.loads((a.run/'verification.json').read_text());assert proof['status']=='verified'
    assert sha(source/'native-heads.pt')==proof['heads_sha256']
    assert sha(a.encoder)==ENCODER_CHECKPOINT
    protocol=json.loads((source/'protocol.json').read_text())
    for name,h in protocol['source_sha256'].items():assert sha(HERE/name)==h,name
    return torch.load(source/'native-heads.pt',map_location='cpu',weights_only=True),source


def encoder(a):
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model=M2DMurmur(HERE/'cache/m2d-weights')
    model.load_state_dict(torch.load(a.encoder,map_location='cpu',weights_only=True))
    return model.to(device).eval(),device


def extract(rows,context,model,device):
    result={d:[] for d in ['native2k','styled']};hashes={d:{} for d in result}
    for i,r in enumerate(rows,1):
        path=context['native']/'audio'/(r['record']+'.f32')
        assert sha(path)==context['native_records'][r['record']]['native_audio_sha256']
        native=np.fromfile(path,dtype='<f4')
        assert len(native)==context['native_records'][r['record']]['samples']
        styled=context['styled'][r['record']]
        assert sha(styled)==context['old_freeze']['input_sha256']['styled'][r['record']]
        wave,rate=sf.read(styled,dtype='float32');assert rate==2000 and len(wave)==len(native)
        for domain,audio,p in [('native2k',native,path),('styled',wave,styled)]:
            crops=windows(audio);parts=[]
            with torch.inference_mode():
                for start in range(0,len(crops),8):
                    mel=model.features(torch.from_numpy(crops[start:start+8]).to(device))
                    z=model.runtime.encode_lms(model.runtime.normalize_batch(mel)).mean(1)
                    parts.append(z.cpu().numpy())
            embedding=np.concatenate(parts) if parts else np.empty((0,3840),dtype=np.float32)
            result[domain].append(dict(r,embedding=embedding))
            hashes[domain][r['record']]=sha(p)
        if i%50==0:print(json.dumps(dict(stage='native_head_comparison_features',recordings=i,total=len(rows))),flush=True)
    return result,hashes


def baselines(context,domain):
    return context['baseline']['clean' if domain=='native2k' else 'styled']['app-M']


def main(a):
    os.umask(0o077);torch.set_num_threads(2)
    if a.output.exists():raise ValueError('Preserve prior comparison outputs')
    heads,source=load_run(a);context=inputs()
    if a.stage=='evaluate':
        frozen=json.loads(a.freeze.read_text())
        assert frozen['selection_constraints_passed'],'Do not score calibration for an ineligible head'
        assert frozen['comparator_sha256']==sha(Path(__file__))
        assert frozen['heads_sha256']==sha(source/'native-heads.pt')
        assert frozen['manifest_sha256']==sha(context['manifest'])
        assert frozen['encoder_sha256']==sha(a.encoder)
        assert frozen['baseline_predictions_sha256']==sha(context['baseline_path'])
    rows=[r for r in context['rows'] if r['role'] in (['selection'] if a.stage=='select' else ['selection','calibration'])]
    assert len(rows)==(180 if a.stage=='select' else 367)
    a.output.mkdir(parents=True)
    save(a.output/'input-freeze.json',dict(encoder_sha256=sha(a.encoder),heads_sha256=sha(source/'native-heads.pt'),
        comparator_sha256=sha(Path(__file__)),manifest_sha256=sha(context['manifest']),
        baseline_predictions_sha256=sha(context['baseline_path']),app_model_files=context['app_files'],
        stage=a.stage,independent_validation=False,private_phone_accuracy_measured=False))
    model,device=encoder(a);features,hashes=extract(rows,context,model,device)
    save(a.output/'input-fingerprints.json',hashes)
    if a.stage=='select':
        candidates={};predictions={};parity=[]
        remote=json.loads((source/'selection-predictions.json').read_text())
        for name,head in heads.items():
            head_predictions={d:select_predictions(head,features[d],torch.device('cpu')) for d in features}
            for r in rows:
                local=head_predictions['native2k'][r['record']]['reading'];cloud=remote[name][r['record']]['reading']
                assert local['windows']==cloud['windows']
                parity.append(float(np.abs(np.asarray(local['probabilities'])-cloud['probabilities']).max()))
            for route in ROUTES:
                key=name+'__'+route;predictions[key]={};metrics={};checks={}
                for domain in features:
                    base=baselines(context,domain)
                    p={r['record']:route_reading(head_predictions[domain][r['record']],base[r['record']],route) for r in rows}
                    predictions[key][domain]=p
                    metrics[domain]=aggregate(rows,p)
                    checks[domain]=promotion_checks(aggregate(rows,base),metrics[domain])
                    checks[domain]['retain_v11_positive_detection']=metrics[domain]['recordings']['detected_positive']>=(30 if domain=='native2k' else 31)
                failures=[d+':'+k for d,c in checks.items() for k,passed in c.items() if not passed]
                candidates[key]=dict(head=name,route=route,metrics=metrics,checks=checks,failures=failures,eligible=not failures)
        assert parity and max(parity)<.001,('Cloud/local head predictions disagree',max(parity))
        eligible=[k for k,v in candidates.items() if v['eligible']]
        def ranking(key):
            c=candidates[key];recordings=[m['recordings'] for m in c['metrics'].values()]
            return (len(c['failures']),-sum(m['detected_positive'] for m in recordings),
                    sum(m['false_alarms'] for m in recordings),sum(m['total_unsure'] for m in recordings),key)
        chosen=min(eligible or list(candidates),key=ranking);c=candidates[chosen]
        save(a.output/'candidate-predictions.json',predictions)
        save(a.output/'selection-report.json',dict(candidates=candidates,chosen=chosen,eligible_candidates=eligible,
            maximum_cloud_local_probability_difference=max(parity),selection_only=True,independent_validation=False))
        frozen=dict(candidate=chosen,head=c['head'],route=c['route'],selection_constraints_passed=c['eligible'],
            comparator_sha256=sha(Path(__file__)),heads_sha256=sha(source/'native-heads.pt'),
            encoder_sha256=sha(a.encoder),manifest_sha256=sha(context['manifest']),
            baseline_predictions_sha256=sha(context['baseline_path']),
            selection_report_sha256=sha(a.output/'selection-report.json'),
            selected_before_v12_calibration_audio=True,independent_validation=False,
            rule='Keep fixed. If no candidate is eligible, preserve diagnostics and do not call it an upgrade.')
        save(a.output/'selection-freeze.json',frozen)
        print(json.dumps(dict(selection_complete=True,chosen=chosen,constraints_passed=c['eligible'],
            eligible_candidates=len(eligible),failures=c['failures'],
            recordings={d:m['recordings'] for d,m in c['metrics'].items()})),flush=True)
    else:
        predictions={};metrics={};checks={}
        head=heads[frozen['head']]
        for domain in features:
            p=select_predictions(head,features[domain],torch.device('cpu'));base=baselines(context,domain)
            predictions[domain]={r['record']:route_reading(p[r['record']],base[r['record']],frozen['route']) for r in rows}
            metrics[domain]={};checks[domain]={}
            for role in ['selection','calibration','combined']:
                cohort=rows if role=='combined' else [r for r in rows if r['role']==role]
                b=aggregate(cohort,base);c=aggregate(cohort,predictions[domain])
                metrics[domain][role]={'app-M':b,'V12':c}
                checks[domain][role]=promotion_checks(b,c)
            checks[domain]['combined']['retain_v11_positive_detection']=metrics[domain]['combined']['V12']['recordings']['detected_positive']>=(58 if domain=='native2k' else 59)
        passed=all(v for domains in checks.values() for role in domains.values() for v in role.values())
        save(a.output/'predictions.json',predictions)
        save(a.output/'comparison.json',dict(candidate=frozen['candidate'],metrics=metrics,checks=checks,
            development_gate_passed=passed,independent_validation=False,phone_accuracy_measured=False,app_updated=False))
        save(a.output/'complete.json',dict(status='v12_comparison_complete',development_gate_passed=passed,
            comparison_sha256=sha(a.output/'comparison.json'),selection_freeze_sha256=sha(a.freeze),shipping_model_unchanged=True))
        print(json.dumps(dict(evaluation_complete=True,development_gate_passed=passed)),flush=True)
    assert files(context['app'])==context['app_files']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['select','evaluate'],required=True)
    for name in ['run','encoder','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--freeze',type=Path)
    main(p.parse_args())
