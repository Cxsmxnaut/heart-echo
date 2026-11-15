"""Record the rejected candidate, immutable baseline and native control checks."""
import json,subprocess
from train_audio_models import ROOT,ML,digest,save
from native_murmur_gate import native

def main():
    report=json.loads((ROOT/'results/murmur-v5-native-development.json').read_text())
    assert report['decision']=='retain_baseline_reject_v5' and not report['regression_scored']
    frozen=json.loads((ROOT/'results/murmur-focus-baseline-freeze.json').read_text())
    package=ROOT.parent/'HeartEcho/Models/Murmur.mlpackage'
    assert frozen['model_files']=={str(p.relative_to(package)):digest(p) for p in sorted(package.rglob('*')) if p.is_file()}
    assert frozen['native_reader_sha256']==digest(ROOT.parent/'HeartEcho/Engine/MurmurAnalysis.swift')
    binary=ROOT/'generated/murmur-focus-checks'
    sources=[ROOT.parent/'HeartEcho/Engine/MurmurAnalysis.swift',ROOT.parent/'HeartEcho/Tools/MurmurChecks.swift']
    subprocess.run(['swiftc','-O','-module-cache-path','/tmp/heartecho-murmur-focus-modules',*map(str,sources),'-o',str(binary)],check=True)
    requests=[{'id':name,'path':str(ML/'cache/noise'/(name+'.wav'))} for name in ['speech','babble']]
    controls={}
    models=[('baseline',package.parent),('v5',ROOT/'generated/murmur-v5-sampler')]
    v8path=ROOT/'results/murmur-v8-native-development.json'
    if v8path.exists():
        v8=json.loads(v8path.read_text())
        assert v8['decision']=='retain_baseline_reject_v8' and not v8['regression_scored']
        models.append(('v8',ROOT/'generated/murmur-v8-distillation'))
    for name,directory in models:
        check=subprocess.run([str(binary),str(directory)],capture_output=True,text=True,check=True)
        noise=native(directory,requests,'focus-final-noise-'+name)
        controls[name]={'native_engineering_assertions':sum(line.startswith('PASS:') for line in check.stdout.splitlines()),'engineering_output':check.stdout,'noise_outputs':noise,'noise_decisive_errors':sum(v['reading']['finding']!='unsure' for v in noise.values()),'note':'Noise controls are engineering checks, not a signal-quality validation set.'}
    result={'decision':'Keep the existing phase-aware M app model. Reject V4 and V5.','reliability_established':False,'baseline_freeze_sha256':digest(ROOT/'results/murmur-focus-baseline-freeze.json'),'baseline_weights_sha256':digest(ML/'generated/murmur-phase-m/Murmur.pt'),'v5_weights_sha256':digest(ROOT/'generated/murmur-v5-sampler/best.pt'),'v5_evaluation_freeze_sha256':digest(ROOT/'generated/murmur-v5-sampler/evaluation-freeze.json'),'v4_diagnosis_sha256':digest(ROOT/'results/murmur-v4-diagnosis.json'),'v5_development_report_sha256':digest(ROOT/'results/murmur-v5-native-development.json'),'source_sha256':digest(__file__),'control_binary_sha256':digest(binary),'control_source_sha256':{p.name:digest(p) for p in sources},'noise_input_sha256':{r['id']:digest(r['path']) for r in requests},'controls':controls,'regression_scored_for_v5':False,'app_model_changed':False,'conversion':report['conversion'],'remaining':'Independent clinician-labeled phone evaluation and substantially better detection/coverage are still required. Development and historical test cohorts already inspected cannot provide fresh validation.'}
    for version,label in [('v6','pretrained'),('v7','heartband')]:
        path=ROOT/'results'/('murmur-'+version+'-'+label+'-probe.json')
        if not path.exists():continue
        probe=json.loads(path.read_text())
        assert probe['decision']=='retain_baseline_reject_frozen_pretrained_probe'
        assert not probe['regression_scored']
        result[version+'_development_report_sha256']=digest(path)
    result['decision']='Keep the existing phase-aware M app model. Reject V4, V5 and the completed frozen-feature probes.'
    result['conversion']={'baseline':report['conversion']['baseline'],'v5':report['conversion']['candidate']}
    if v8path.exists():
        result['decision']='Keep the existing phase-aware M app model. Reject V4, V5, V6, V7 and V8.'
        result['v8_development_report_sha256']=digest(v8path)
        result['v8_weights_sha256']=digest(ROOT/'generated/murmur-v8-distillation/best.pt')
        result['conversion']['v8']=v8['conversion']['candidate']
    save(ROOT/'results/murmur-focus-decision.json',result)
    print(json.dumps({'decision':result['decision'],'controls':{k:{x:v[x] for x in ['native_engineering_assertions','noise_decisive_errors']} for k,v in controls.items()}},indent=2))

if __name__=='__main__':main()
