"""Evaluate V3 on consumed source-F regression only after source-B selection."""
import csv,json
import numpy as np
import soundfile as sf
import torch
from train_audio_models import ROOT,audio_feature,classification_metrics,digest,save
from train_source_balanced import SourceBalancedClassifier,predict_native_windows
out=ROOT/'generated/audio-v3-abnormal';complete=json.loads((out/'complete.json').read_text());assert complete['model_sha256']==digest(out/'best.pt')
freeze={'complete_sha256':digest(out/'complete.json'),'training_source_sha256':digest(ROOT/'train_source_balanced.py'),'evaluation_source_sha256':digest(__file__),'weights_sha256':digest(out/'best.pt'),'test_status':'Source F already inspected with the first random forest. Retrospective regression; no fresh or patient-independent claim.'}
p=ROOT/'results/audio-v3-abnormal-freeze.json'
if p.exists():assert json.loads(p.read_text())==freeze
else:save(p,freeze)
data=[];root=ROOT/'cache/physionet2016/training-f'
for name,label,quality in csv.reader((root/'REFERENCE_withSQI.csv').open()):
 path=root/(name+'.wav');info=sf.info(path);data.append({'id':name,'target':2 if quality=='0' else int(label=='1'),'sample_count':int(min(info.frames,info.samplerate*60)*2000/info.samplerate),'x':audio_feature(path)})
device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu');torch.set_num_threads(2);model=SourceBalancedClassifier();model.load_state_dict(torch.load(out/'best.pt',map_location='cpu',weights_only=True));model.to(device).eval();prob=predict_native_windows(model,data,device);result=classification_metrics([r['target'] for r in data],prob,False)
report={'freeze':freeze,'development':complete['selected'],'regression':result,'records':[{'id':r['id'],'target':r['target'],'scores':p.tolist()} for r,p in zip(data,prob)],'limits':'Source-held-out, not proven patient-independent. Unknown is not normal. Uncertainty counts must accompany sensitivity/specificity. No phone accuracy claim.'};save(ROOT/'results/audio-v3-abnormal-results.json',report);print(json.dumps(result,indent=2))
