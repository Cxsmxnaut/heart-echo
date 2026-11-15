"""V3 normal/abnormal candidate: source-balanced sampling and per-band normalization.
Chosen after reviewing source-B development failure in V2, before any V2/V3
source-F evaluation. The old random-forest source-F result is already known.
"""
import json,time
from collections import defaultdict
import numpy as np
import torch
import soundfile as sf
from torch import nn
from torch.nn import functional as F
from train_audio_models import ROOT,AudioClassifier,AudioEncoder,abnormal_data,crop,classification_metrics,digest,save
from murmur_model import FRAMES, HOP, windows

class BandEncoder(AudioEncoder):
    def forward(self,x):
        mean=x.mean(2,keepdim=True);x=(x-mean)/((x-mean).square().mean(2,keepdim=True)+1).sqrt()
        h=self.layers(x);return torch.cat([h.mean(2),h.amax(2)],1)
class SourceBalancedClassifier(AudioClassifier):
    def __init__(self):super().__init__();self.encoder=BandEncoder()

def predict_native_windows(model,data,device):
    model.eval();probabilities=[]
    with torch.inference_mode():
        for r in data:
            starts=[s//HOP for s in windows(r['sample_count'])]
            x=np.stack([r['x'][:,s:s+FRAMES] for s in starts])
            probabilities.append(model(torch.tensor(x,device=device)).softmax(1).cpu().numpy().mean(0))
    return np.stack(probabilities)

def train():
    out=ROOT/'generated/audio-v3-abnormal';out.mkdir(parents=True,exist_ok=True)
    if (out/'protocol.json').exists():raise ValueError('Run exists; inspect its existing process instead of restarting')
    protocol={'epochs':32,'steps':90,'batch':36,'seed':20261116,'source_sha256':digest(__file__),'train_sources':['a','c','d','e'],'selection_source':'b','regression_source':'f, not loaded by training','change':'Sample each class equally, then sample available acquisition sources uniformly within class; normalize each spectral band across time to reduce constant device frequency response. Preserve within-band temporal texture.','selection':'Max mean normal and abnormal recall, then three-class balanced recall at fixed .60. No test tuning.','limits':'No patient map available. Source holdout is not patient independence. New source-balanced objective was chosen using source-B development failures only.'}
    save(out/'protocol.json',protocol);torch.manual_seed(20261116);torch.set_num_threads(2);rng=np.random.default_rng(20261116);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    data=abnormal_data()
    for r in data:
        info=sf.info(ROOT/'cache/physionet2016'/('training-'+r['group'])/(r['id']+'.wav'));r['sample_count']=int(min(info.frames,info.samplerate*60)*2000/info.samplerate)
    training=[r for r in data if r['role']=='training'];validation=[r for r in data if r['role']=='selection'];pools=[defaultdict(list) for _ in range(3)]
    for r in training:pools[r['target']][r['group']].append(r)
    save(out/'split.json',{role:[{'id':r['id'],'source':r['group'],'target':r['target']} for r in data if r['role']==role] for role in ['training','selection']})
    model=SourceBalancedClassifier().to(device);optimizer=torch.optim.AdamW([{'params':model.encoder.parameters(),'lr':5e-5},{'params':model.head.parameters(),'lr':5e-4}],weight_decay=.01);best=(-1.,-1.);history=[]
    for epoch in range(33):
        began=time.perf_counter();model.train();losses=[]
        for p in model.encoder.parameters():p.requires_grad_(epoch>3)
        for step in range(90 if epoch else 0):
            batch=[]
            for j in range(36):
                sources=sorted(pools[j%3]);source=sources[int(rng.integers(len(sources)))];records=pools[j%3][source];batch.append(records[int(rng.integers(len(records)))])
            x=torch.tensor(np.stack([crop(r['x'],rng,True) for r in batch]),device=device);y=torch.tensor([r['target'] for r in batch],device=device)
            optimizer.zero_grad(set_to_none=True);loss=F.cross_entropy(model(x),y);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);optimizer.step();losses.append(float(loss.detach().cpu()))
        p=predict_native_windows(model,validation,device);result=classification_metrics([r['target'] for r in validation],p,False);score=(float(np.mean(result['recall'][:2])),result['balanced_recall'])
        row={'epoch':epoch,'loss':float(np.mean(losses)) if losses else None,'selection':result,'seconds':time.perf_counter()-began};history.append(row);print(json.dumps(row),flush=True)
        if score>best:best=score;torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},out/'best.pt');save(out/'selected.json',row)
        save(out/'history.json',history)
    save(out/'complete.json',{'protocol':protocol,'model_sha256':digest(out/'best.pt'),'selected':json.loads((out/'selected.json').read_text()),'training_examples':len(training),'selection_examples':len(validation)});print('COMPLETE',best,flush=True)
if __name__=='__main__':train()
