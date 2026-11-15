"""Evaluate frozen M2D on the existing public development people, locally.

Source audio preserves the paper's input bandwidth. The main app comparison
uses exactly the existing native 2kHz audio and frozen V10 phone simulations.
All conditions use five-second M2D windows and fixed .60 confidence. The app M
keeps its existing four-second windows/mean-probability rule. This compares
methods, not an architecture-only change, and is not independent validation.
"""
import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
from scipy import signal
import soundfile as sf
import torch

from m2d_murmur import M2DMurmur, RATE, SAMPLES, offsets, sha, decide, HERE
from murmur_focus_metrics import aggregate,promotion_checks
from phone_style import assert_person_split


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def files(path):
    return {str(p.relative_to(path)):sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def predict(model,audio,rate,device):
    # Keep the app's minimum available audio duration, even though the published
    # M2D training crop is5s and legitimate4..5s recordings require padding.
    if len(audio)<4*rate:
        return dict(reading=dict(finding='unsure',probabilities=[0.,0.,1.],windows=0))
    divisor=math.gcd(rate,RATE)
    if rate!=RATE:
        audio=signal.resample_poly(audio,RATE//divisor,rate//divisor).astype(np.float32)
    if len(audio)<SAMPLES:
        audio=np.pad(audio,(0,SAMPLES-len(audio)))
    crops=[]
    for start in offsets(len(audio)):
        x=audio[start:start+SAMPLES]
        if (np.isfinite(x).all() and np.mean(x.astype(np.float64)**2)>=.00002**2
                and np.mean(np.abs(x)>=.999)<=.01):
            crops.append(x)
    logits=[]
    with torch.inference_mode():
        for start in range(0,len(crops),8):
            wave=torch.from_numpy(np.stack(crops[start:start+8])).to(device)
            logits.append(model(model.features(wave)).float().cpu())
    p=torch.cat(logits).mean(0).softmax(0).numpy() if logits else np.array([0.,0.,1.])
    return dict(reading=dict(finding=decide(p),probabilities=p.tolist(),windows=len(crops)))


def main(args):
    os.umask(0o077);torch.set_num_threads(2)
    output=args.output.resolve()
    if output.exists():
        raise ValueError('Preserve completed/partial evaluations; choose a new output directory')
    source=args.source.resolve()
    joint=json.loads(args.comparison_freeze.read_text())
    assert sha(Path(__file__))==joint['evaluator_sha256'],'Use the same frozen evaluator for both arms'
    matching=[entry for entry in joint['models'].values() if Path(entry['source_directory']).resolve()==source]
    assert len(matching)==1
    assert sha(source/'M2D.pt')==matching[0]['weights_sha256']
    complete=json.loads((source/'complete.json').read_text())
    assert complete['status']=='m2d_training_complete'
    assert sha(source/'protocol.json')==complete['protocol_sha256']
    protocol=json.loads((source/'protocol.json').read_text())
    assert sha(source/'M2D.pt')==complete['proof']['weights_sha256']
    for name,expected in protocol['source_sha256'].items():
        assert sha(HERE/name)==expected,name
    assert complete['proof']['changed_transformer_blocks']==list(range(12))
    ml=HERE.parent/'ChestBPM/ML'
    manifest=ml/'murmur-phase-manifest.json'
    all_rows=[r for r in json.loads(manifest.read_text())['records'] if r['role']!='test']
    assert_person_split(all_rows)
    rows=[r for r in all_rows if r['role'] in ['selection','calibration']]
    assert len(rows)==367
    native_cache=ml/'generated/murmur-native-development'
    native_manifest=json.loads((native_cache/'manifest.json').read_text())
    assert native_manifest['phase_manifest_sha256']==sha(manifest)
    native={r['record']:r for r in native_manifest['records']}
    v10=HERE/'generated/murmur-v10-two-stage/local-adapter'
    v10summary=json.loads((v10/'summary.json').read_text())
    assert sha(v10/'native-predictions.json')==v10summary['artifacts_sha256']['local-adapter/native-predictions.json']
    old=json.loads((v10/'native-predictions.json').read_text())
    oldfreeze=json.loads((v10/'native-freeze.json').read_text())
    v10protocol=json.loads((v10/'protocol.json').read_text())
    assert sha(args.profile)==v10protocol['profile_sha256']
    styled_requests={r['id']:r['path'] for r in json.loads((v10/'native-styled-requests.json').read_text())}
    expected=json.loads((HERE/'results/murmur-focus-baseline-freeze.json').read_text())
    app=HERE.parent/'HeartEcho/Models/Murmur.mlpackage'
    reader=HERE.parent/'HeartEcho/Engine/MurmurAnalysis.swift'
    assert files(app)==expected['model_files']
    assert sha(reader)==oldfreeze['sources']['MurmurAnalysis.swift']
    output.mkdir(parents=True)
    freeze=dict(weights_sha256=sha(source/'M2D.pt'),protocol_sha256=sha(source/'protocol.json'),
        joint_selection_freeze_sha256=sha(args.comparison_freeze),
        joint_selection_choice=joint['chosen_by_selection_only'],
        evaluator_sha256=sha(Path(__file__)),cohort_manifest_sha256=sha(manifest),
        baseline_predictions_sha256=sha(v10/'native-predictions.json'),
        baseline_model_files=files(app),native_reader_sha256=sha(reader),profile_sha256=sha(args.profile),
        threshold=.60,calibration_audio_not_loaded_in_this_process_before_freeze=True,
        both_candidate_weights_jointly_frozen_before_m2d_calibration=joint['frozen_before_this_run_calibration_audio'],
        conditions=['source16k','native2k','styled'],independent_validation=False,
        limits=['Reused development people; frozen phone simulations include local unlabeled statistics.',
                'M2D uses5s windows/mean logits; M retains4s windows/mean probabilities.',
                'Public-source condition also preserves source bandwidth; native2k is the main app comparison.',
                'NTT research evaluation only; this run does not authorize app distribution.'])
    save(output/'evaluation-freeze.json',freeze)
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model=M2DMurmur(args.cache)
    model.load_state_dict(torch.load(source/'M2D.pt',map_location='cpu',weights_only=True))
    model.to(device).eval()
    predictions={domain:{} for domain in freeze['conditions']}
    input_hashes={domain:{} for domain in freeze['conditions']}
    for index,r in enumerate(rows,1):
        original=ml/'cache/circor'/r['file']
        assert sha(original)==r['sha256']
        info=sf.info(original)
        wave,rate=sf.read(original,frames=int(info.samplerate*60),dtype='float32')
        predictions['source16k'][r['record']]=predict(model,wave,rate,device)
        input_hashes['source16k'][r['record']]=sha(original)
        path=native_cache/'audio'/(r['record']+'.f32')
        assert sha(path)==native[r['record']]['native_audio_sha256']
        audio=np.fromfile(path,dtype='<f4')
        assert len(audio)==native[r['record']]['samples']
        predictions['native2k'][r['record']]=predict(model,audio,2000,device)
        input_hashes['native2k'][r['record']]=sha(path)
        styled=Path(styled_requests[r['record']])
        assert sha(styled)==oldfreeze['input_sha256']['styled'][r['record']]
        wave,rate=sf.read(styled,dtype='float32')
        assert rate==2000 and len(wave)==len(audio)
        predictions['styled'][r['record']]=predict(model,wave,rate,device)
        input_hashes['styled'][r['record']]=sha(styled)
        if index%50==0:
            save(output/'partial-predictions.json',predictions)
            print(json.dumps(dict(records_evaluated=index,total=len(rows),conditions=3)),flush=True)
    save(output/'predictions.json',predictions)
    save(output/'input-fingerprints.json',input_hashes)
    remote=json.loads((source/'selection-predictions.json').read_text())
    differences=[];changed_windows=[]
    for r in rows:
        if r['role']!='selection':
            continue
        a=remote[r['record']]['reading'];b=predictions['source16k'][r['record']]['reading']
        if a['windows']!=b['windows']:
            changed_windows.append(r['record'])
            continue
        differences.append(float(np.max(np.abs(np.asarray(a['probabilities'])-b['probabilities']))))
    if not differences or max(differences)>=.001:
        raise ValueError('Local/cloud source-input predictions differ; investigate before interpreting results')
    report=dict(roles={},evidence=freeze['limits'],app_updated=False,
        clinical_phone_accuracy_measured=False,engineering_model_integration_tested=False,
        cloud_local_parity=dict(compared_recordings=len(differences),
            maximum_probability_difference=max(differences),passed=True,
            recordings_with_windows_removed_by_local_quality_gate=changed_windows))
    passed=True;added=0
    for role in ['selection','calibration']:
        cohort=[r for r in rows if r['role']==role]
        report['roles'][role]={}
        report['roles'][role]['source16k']=dict(M2D=aggregate(cohort,predictions['source16k']))
        for domain,old_domain in [('native2k','clean'),('styled','styled')]:
            a=aggregate(cohort,old[old_domain]['app-M'])
            b=aggregate(cohort,predictions[domain])
            checks=promotion_checks(a,b)
            passed &= all(checks.values())
            added += b['recordings']['detected_positive']-a['recordings']['detected_positive']
            report['roles'][role][domain]=dict(results={'app-M':a,'M2D':b},strict_checks=checks)
    report.update(strict_development_gate_passed=bool(passed and added>0),
        decision='research_improvement_requires_independent_validation_and_deployment_license' if passed and added>0
        else 'retain_app_M; M2D did not pass strict development comparison')
    assert files(app)==expected['model_files']
    save(output/'comparison.json',report)
    save(output/'complete.json',dict(status='m2d_comparison_complete',decision=report['decision'],
        model_weights_sha256=sha(source/'M2D.pt'),comparison_sha256=sha(output/'comparison.json'),
        predictions_sha256=sha(output/'predictions.json'),shipping_model_unchanged=True))
    print(json.dumps(dict(complete=True,decision=report['decision'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=HERE/'cache/m2d-weights')
    parser.add_argument('--profile',type=Path,default=HERE/'generated/murmur-v9-phone-style/phone-profile.json')
    parser.add_argument('--comparison-freeze',type=Path,default=HERE/'generated/murmur-v11-m2d/joint-selection-freeze.json')
    main(parser.parse_args())
