"""Freeze selected candidates before loading previously consumed regression data."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
from train_audio_models import ROOT,ML,AudioClassifier,audio_feature,predict,classification_metrics,digest,save

def evaluate(task):
    bag=task=='valves';out=ROOT/'generated'/('audio-v2-'+task);complete=json.loads((out/'complete.json').read_text());assert complete['model_sha256']==digest(out/'best.pt')
    freeze={'complete_sha256':digest(out/'complete.json'),'weights_sha256':digest(out/'best.pt'),'training_source_sha256':digest(ROOT/'train_audio_models.py'),'evaluation_source_sha256':digest(__file__),'test_status':'Previously inspected regression data; not fresh independent evaluation. Candidate selected on development only.'}
    path=ROOT/'results'/('audio-v2-'+task+'-freeze.json')
    if path.exists():assert json.loads(path.read_text())==freeze
    else:save(path,freeze)
    model=AudioClassifier(4 if bag else 3,bag);model.load_state_dict(torch.load(out/'best.pt',map_location='cpu',weights_only=True));model.eval();torch.set_num_threads(2);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu');model.to(device)
    data=[]
    if bag:
        baseline=json.loads((ROOT/'results/bmd-results.json').read_text());allowed=set(baseline['audit']['test_patients'])
        for r in csv.DictReader((ROOT/'cache/bmd/train.csv').open()):
            if r['patient_id'] in allowed:data.append(dict(id=r['patient_id'],target=[int(r[k]) for k in ['AS','AR','MR','MS']],x=[audio_feature(ROOT/'cache/bmd/train'/(r[f'recording_{j}']+'.wav')) for j in range(1,9)]))
    elif task=='abnormal':
        root=ROOT/'cache/physionet2016/training-f'
        for name,label,quality in csv.reader((root/'REFERENCE_withSQI.csv').open()):data.append(dict(id=name,target=2 if quality=='0' else int(label=='1'),x=audio_feature(root/(name+'.wav'))))
    else:
        for r in json.loads((ML/'murmur-manifest.json').read_text())['records']:
            if r['split']=='test':
                import soundfile as sf
                from scipy import signal
                from murmur_model import spectrum
                path=ML/'cache/circor'/r['file'];assert digest(path)==r['sha256'];x,rate=sf.read(path);x=signal.resample_poly(x,2000,rate).astype(np.float32)
                data.append(dict(id=r['record'],group=r['group'],target=r['target'],x=spectrum(x[:120000])))
    p=predict(model,data,device,bag);y=[r['target'] for r in data];metrics=classification_metrics(y,p,bag)
    records=[{'id':r['id'],'target':r['target'],'probabilities':q.tolist()} for r,q in zip(data,p)]
    report={'freeze':freeze,'development':complete['selected'],'regression':metrics,'cases':len(data),'records':records,'model_role':'Research candidate; promotion requires checking errors, uncertainty and native conversion. Small/consumed test sets do not establish clinical or phone accuracy.'}
    if bag:report['prior_random_forest']={k:v['model'] for k,v in baseline['per_condition'].items()}
    save(ROOT/'results'/('audio-v2-'+task+'-results.json'),report);print(json.dumps({'task':task,'regression':metrics},indent=2),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('task',choices=['valves','abnormal','murmur']);evaluate(parser.parse_args().task)
