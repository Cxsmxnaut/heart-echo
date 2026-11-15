"""Freeze V5, verify Apple conversion, then evaluate reused development only.

No regression audio is loaded. A failed development gate stops promotion.
"""
import json,subprocess
from pathlib import Path
import numpy as np
import torch
import coremltools as ct
from train_audio_models import ROOT,ML,digest,save
from train_phase_texture import TexturePhaseNet
from export_phase_texture import WaveTexture
from murmur_additive_model import AdditiveModel
from murmur_native_data import CACHE
from native_murmur_gate import native
from murmur_focus_metrics import aggregate,promotion_checks,wilson

OUT=ROOT/'generated/murmur-v5-sampler'
NAMES=['probabilities','phase_probabilities','murmur_timing']

def package_hashes(path):
    return {str(p.relative_to(path)):digest(p) for p in sorted(path.rglob('*')) if p.is_file()}

def baseline_unchanged():
    frozen=json.loads((ROOT/'results/murmur-focus-baseline-freeze.json').read_text())
    assert frozen['model_files']==package_hashes(ROOT.parent/'HeartEcho/Models/Murmur.mlpackage')
    assert frozen['native_reader_sha256']==digest(ROOT.parent/'HeartEcho/Engine/MurmurAnalysis.swift')

def conversion_check(model,package,examples):
    native_model=ct.models.MLModel(str(package));errors=[]
    for x in examples:
        with torch.inference_mode():expected=model(x)
        actual=native_model.predict({'waveform':x.numpy()})
        errors.append([float(np.max(np.abs(y.numpy()-actual[n]))) for y,n in zip(expected,NAMES)])
    result={'maximum_absolute_differences':np.max(errors,axis=0).tolist(),'examples':len(examples),'real_public_development_examples':len(examples)-4,'passed':bool(np.max(errors)<.001)}
    assert result['passed'],result
    return result

def main():
    baseline_unchanged();complete=json.loads((OUT/'complete.json').read_text())
    assert complete['eligible_checkpoint']
    assert digest(OUT/'best.pt')==complete['weights_sha256']
    assert digest(ROOT/'train_murmur_v5_sampler.py')==complete['protocol']['source_sha256']
    assert digest(ROOT/'train_phase_texture.py')==complete['protocol']['architecture_source_sha256']
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role'] in ['selection','calibration']]
    torch.set_num_threads(2);torch.manual_seed(20261121)
    classifier=TexturePhaseNet();classifier.load_state_dict(torch.load(OUT/'best.pt',map_location='cpu',weights_only=True))
    model=WaveTexture(classifier).eval();package=OUT/'Murmur.mlpackage'
    if not package.exists():
        converted=ct.convert(torch.jit.trace(model,torch.randn(1,1,8000)*.03),inputs=[ct.TensorType(name='waveform',shape=(1,1,8000))],outputs=[ct.TensorType(name=n) for n in NAMES],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
        converted.author='Heart Echo public-data research'
        converted.short_description='Sampler-only V5 research candidate; not a diagnosis.'
        converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',labels='Absent,Present,Unknown',phase_labels='noise,S1,systole,S2,diastole',model_revision='Sampler V5 · 2026-11-15',weights_sha256=digest(OUT/'best.pt'))
        converted.save(str(package))
    examples=[torch.randn(1,1,8000)*scale for scale in [0,.0001,.03,.3]]
    cache={r['record']:r for r in json.loads((CACHE/'manifest.json').read_text())['records']}
    for role in ['selection','calibration']:
        for target in [0,1,2]:
            for r in sorted([r for r in rows if r['role']==role and r['target']==target],key=lambda r:r['record'])[:3]:
                path=CACHE/'audio'/(r['record']+'.f32')
                assert digest(path)==cache[r['record']]['native_audio_sha256']
                examples.append(torch.from_numpy(np.fromfile(path,dtype='<f4')[:8000].copy())[None,None])
    baseline=AdditiveModel();baseline.load_state_dict(torch.load(ML/'generated/murmur-phase-m/Murmur.pt',map_location='cpu',weights_only=True));baseline.eval()
    conversion={'candidate':conversion_check(model,package,examples),'baseline':conversion_check(baseline,ROOT.parent/'HeartEcho/Models/Murmur.mlpackage',examples)}
    save(OUT/'native-conversion.json',conversion)
    frozen={'candidate_weights_sha256':digest(OUT/'best.pt'),'package_files':package_hashes(package),'baseline_freeze_sha256':digest(ROOT/'results/murmur-focus-baseline-freeze.json'),'native_reader_sha256':digest(ROOT.parent/'HeartEcho/Engine/MurmurAnalysis.swift'),'native_executable_sha256':digest(ROOT/'generated/murmur-probe'),'evaluator_sha256':digest(__file__),'metrics_sha256':digest(ROOT/'murmur_focus_metrics.py'),'acceptance_sha256':digest(ROOT/'murmur_focus_acceptance.json'),'cohort_manifest_sha256':digest(ML/'murmur-phase-manifest.json'),'threshold':.60,'selected_epoch':complete['selected']['epoch']}
    freeze=OUT/'evaluation-freeze.json'
    if freeze.exists():assert json.loads(freeze.read_text())==frozen
    else:save(freeze,frozen)
    requests=[{'id':r['record'],'path':str(ML/'cache/circor'/r['file'])} for r in rows]
    path=OUT/'native-development.json'
    if path.exists():candidate=json.loads(path.read_text())
    else:candidate=native(OUT,requests,'v5-sampler');save(path,candidate)
    baseline_predictions=json.loads((ROOT/'generated/murmur-focus-diagnosis/baseline-native-development.json').read_text())
    assert set(candidate)==set(baseline_predictions)=={r['record'] for r in rows}
    report={'conversion':conversion,'freeze_sha256':digest(freeze),'selected_epoch':complete['selected']['epoch'],'roles':{},'limitations':['Reused development data; not independent validation.','Linked-person summaries combine available visits and are descriptive, not a validated clinical patient decision.','No phone accuracy claim. No regression scoring if development gate fails.']}
    passed=True;added=0
    for role in ['selection','calibration']:
        cohort=[r for r in rows if r['role']==role]
        a=aggregate(cohort,baseline_predictions);b=aggregate(cohort,candidate);checks=promotion_checks(a,b)
        for result in [a,b]:
            for level in ['recordings','linked_people']:
                m=result[level];m['positive_detection_wilson95_descriptive']=wilson(m['detected_positive'],m['positive_count'])
                m['ci_note']='Recording interval ignores within-person correlation; linked-person interval uses independent linked groups. Neither removes development reuse bias.'
        report['roles'][role]={'baseline':a,'candidate':b,'checks':checks}
        passed &= all(checks.values())
        added+=sum(b[level]['detected_positive']-a[level]['detected_positive'] for level in ['recordings','linked_people'])
    report.update(development_gate_passed=bool(passed and added>0),additional_positive_detections_sum_across_levels=added,decision='proceed_to_frozen_regression' if passed and added>0 else 'retain_baseline_reject_v5',regression_scored=False)
    baseline_unchanged();save(ROOT/'results/murmur-v5-native-development.json',report)
    print(json.dumps({k:report[k] for k in ['selected_epoch','development_gate_passed','decision']},indent=2),flush=True)

if __name__=='__main__':main()
