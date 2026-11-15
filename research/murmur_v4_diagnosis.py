"""Paired development-only diagnosis of V4; does not read regression audio.
Preserve the shipping package and all prior candidate artifacts.
"""
import csv,json,sys,hashlib,time
from collections import Counter
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parent;ML=ROOT.parent/'ChestBPM/ML'
sys.path.insert(0,str(ML))
from murmur_model import metrics,decision,FRAMES,HOP,windows
from murmur_native_data import CACHE
from train_phase_texture import TexturePhaseNet
from native_murmur_gate import native

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def main():
    baseline=ROOT.parent/'HeartEcho/Models/Murmur.mlpackage';source=ROOT.parent/'HeartEcho/Engine/MurmurAnalysis.swift'
    frozen={'model_files':{str(p.relative_to(baseline)):sha(p) for p in sorted(baseline.rglob('*')) if p.is_file()},'native_reader_sha256':sha(source),'label_order':['Absent','Present','Unknown'],'threshold':.60,'scope':'Current app baseline; original artifacts must remain unchanged throughout murmur-only work.'}
    freeze=ROOT/'results/murmur-focus-baseline-freeze.json'
    if freeze.exists():assert json.loads(freeze.read_text())==frozen
    else:save(freeze,frozen)
    rows=json.loads((ML/'murmur-phase-manifest.json').read_text())['records'];training=[r for r in rows if r['role']=='training'];dev=[r for r in rows if r['role'] in ['selection','calibration']]
    assert not {r['group'] for r in training}&{r['group'] for r in dev}
    metadata={r['Patient ID']:r for r in csv.DictReader((ML/'cache/circor/training_data.csv').open())}
    requests=[{'id':r['record'],'path':str(ML/'cache/circor'/r['file'])} for r in dev]
    out=ROOT/'generated/murmur-focus-diagnosis';out.mkdir(parents=True,exist_ok=True)
    native_outputs={}
    for name,directory in [('baseline',baseline.parent),('v4',ROOT/'generated/murmur-v4-texture')]:
        path=out/(name+'-native-development.json')
        if path.exists():values=json.loads(path.read_text())
        else:values=native(directory,requests,'focus-diagnosis-'+name);save(path,values)
        assert set(values)=={r['record'] for r in dev};native_outputs[name]=values
    provenance={r['record']:r for r in json.loads((CACHE/'manifest.json').read_text())['records']}
    model=TexturePhaseNet();weights=ROOT/'generated/murmur-v4-texture/best.pt';model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True));model.eval();torch.set_num_threads(2)
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu');model.to(device);paired=[];difference=[]
    for r in dev:
        info=provenance[r['record']];old=np.load(ML/'generated/murmur-v1/features'/(r['record']+'.npy'));aligned=np.load(CACHE/'features'/(r['record']+'.npy'));assert sha(CACHE/'features'/(r['record']+'.npy'))==info['features_sha256']
        all_starts=[s//HOP for s in windows(info['samples'])];usable=set(info['usable_frame_starts']);starts=[s for s in all_starts if s in usable]
        predictions={}
        for name,x,positions in [('scipy_all',old,all_starts),('native_all',aligned,all_starts),('native_usable',aligned,starts)]:
            if not positions:p=np.array([0.,0.,1.])
            else:
                batch=np.stack([x[:,s:s+FRAMES] for s in positions])
                with torch.inference_mode():p=model(torch.tensor(batch,device=device)).softmax(1).cpu().numpy().mean(0)
            predictions[name]=p.tolist()
        native_p=native_outputs['v4'][r['record']]['reading']['probabilities'];delta=float(np.max(np.abs(np.array(native_p)-predictions['native_usable'])));difference.append(delta)
        row=dict(record=r['record'],group=r['group'],role=r['role'],target=r['target'],location=r['location'],age=metadata[r['patient']]['Age'],baseline=native_outputs['baseline'][r['record']]['reading'],v4=native_outputs['v4'][r['record']]['reading'],paired_probabilities=predictions,maximum_aligned_torch_coreml_difference=delta,total_windows=len(all_starts),usable_windows=len(starts));paired.append(row)
    report={'source_sha256':sha(__file__),'baseline_freeze_sha256':sha(freeze),'v4_weights_sha256':sha(weights),'training_recordings':len(training),'training_groups':len({r['group'] for r in training}),'natural_training_target_counts':dict(Counter(r['target'] for r in training)),'actual_v4_batch_target_counts':{'Absent':8,'Present':8,'Unknown_including_synthetic_noise':14},'roles':{},'false_alarm_records':[],'maximum_aligned_probability_difference':max(difference),'limitations':['Selection and calibration are reused development data.','Development error inspection informs the next candidate and cannot be called independent validation.','No cause of generalization failure is established from aggregate counts alone.']}
    mapping={'absent':0,'present':1,'unsure':2}
    for role in ['selection','calibration']:
        records=[r for r in paired if r['role']==role];truth=[r['target'] for r in records];values={}
        for name in ['baseline','v4']:values[name]=metrics(truth,[mapping[r[name]['finding']] for r in records])
        for name in ['scipy_all','native_all','native_usable']:values[name]=metrics(truth,[decision(r['paired_probabilities'][name]) for r in records])
        values['new_v4_false_alarms']=[r['record'] for r in records if r['target']==0 and r['v4']['finding']=='present' and r['baseline']['finding']!='present']
        report['roles'][role]=values
    for r in paired:
        if r['target']==0 and (r['v4']['finding']=='present' or r['baseline']['finding']=='present'):report['false_alarm_records'].append(r)
    save(out/'paired-development.json',paired);save(ROOT/'results/murmur-v4-diagnosis.json',report)
    print(json.dumps({k:report[k] for k in ['training_recordings','training_groups','natural_training_target_counts','actual_v4_batch_target_counts','maximum_aligned_probability_difference']},indent=2),flush=True)
    for role,v in report['roles'].items():print(role,{k:{z:m[z] for z in ['false_alarms','missed_positive_as_absent','positive_unsure','unsure']} for k,m in v.items() if isinstance(m,dict)},flush=True)
if __name__=='__main__':main()
