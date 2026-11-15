"""Transfer-learn audio models on public training/development data only.

The prior test sets have been inspected. They are regression evidence, never fresh
validation. Checkpoints are selected without loading their audio or predictions.
"""
import argparse, csv, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy import signal
import torch
from torch import nn
from torch.nn import functional as F
ROOT=Path(__file__).resolve().parent; ML=ROOT.parent/'ChestBPM/ML'
sys.path.insert(0,str(ML))
from murmur_model import MurmurNet, Frontend, spectrum, FRAMES, SAMPLES, windows, metrics, decision

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')

def audio_feature(path):
    # Cache only public derived spectra, never private capture paths.
    path=Path(path).resolve(); assert path.is_relative_to((ROOT/'cache').resolve())
    cache=ROOT/'generated/audio-features';cache.mkdir(parents=True,exist_ok=True)
    target=cache/(hashlib.sha256(str(path.relative_to(ROOT/'cache')).encode()).hexdigest()[:24]+'.npy')
    if target.exists():return np.load(target).astype(np.float32)
    info=sf.info(path);x,rate=sf.read(path,frames=int(info.samplerate*60));x=x.mean(1) if x.ndim>1 else x
    x=signal.resample_poly(x,2000//math.gcd(2000,rate),rate//math.gcd(2000,rate)).astype(np.float32)
    if len(x)<SAMPLES:x=np.pad(x,(0,SAMPLES-len(x)))
    a=spectrum(x);np.save(target,a.astype(np.float16));return a

def crop(x,rng=None,augment=False):
    if x.shape[1]<FRAMES:x=np.pad(x,((0,0),(0,FRAMES-x.shape[1])),mode='edge')
    start=int(rng.integers(x.shape[1]-FRAMES+1)) if rng is not None else (x.shape[1]-FRAMES)//2
    a=x[:,start:start+FRAMES].copy()
    if augment:
        # Training-only bounded spectral tilt/attenuation simulate device response
        # variation; these are synthetic perturbations, not validated phone audio.
        a+=rng.uniform(-2,2)+np.linspace(-1,1,len(a))[:,None]*rng.uniform(-2.5,2.5)
        a+=rng.normal(0,.12,a.shape)
        if rng.random()<.35:
            first=int(rng.integers(len(a)-3));a[first:first+3]=a.mean()
        if rng.random()<.2:
            first=int(rng.integers(FRAMES-12));a[:,first:first+12]=a.mean()
    return a

class AudioEncoder(nn.Module):
    def __init__(self):
        super().__init__();base=MurmurNet();base.load_state_dict(torch.load(ML/'generated/murmur-v1/Murmur.pt',map_location='cpu',weights_only=True));self.layers=base.layers
    def forward(self,x):
        m=x.mean((1,2),keepdim=True);x=(x-m)/((x-m).square().mean((1,2),keepdim=True)+1).sqrt()
        x=self.layers(x);return torch.cat([x.mean(2),x.amax(2)],1)

class AudioClassifier(nn.Module):
    def __init__(self,labels=3,bag=False):
        super().__init__();self.encoder=AudioEncoder();self.bag=bag
        self.attention=nn.Linear(128,1) if bag else nn.Identity()
        self.head=nn.Sequential(nn.LayerNorm(256 if bag else 128),nn.Dropout(.35),nn.Linear(256 if bag else 128,64),nn.ReLU(),nn.Dropout(.25),nn.Linear(64,labels))
    def forward(self,x):
        if self.bag:
            batch,recordings,bins,frames=x.shape;h=self.encoder(x.reshape(batch*recordings,bins,frames)).reshape(batch,recordings,128)
            a=self.attention(h).softmax(1);h=torch.cat([(h*a).sum(1),h.amax(1)],1)
        else:h=self.encoder(x)
        return self.head(h)

class ExportAudio(nn.Module):
    def __init__(self,model):super().__init__();self.front=Frontend();self.model=model
    def forward(self,waveform):return self.model(self.front(waveform)).softmax(1)


def murmur_data():
    rows=json.loads((ML/'murmur-phase-manifest.json').read_text())['records'];data=[]
    for r in rows:
        if r['role']=='test':continue
        file=ML/'generated/murmur-v1/features'/(r['record']+'.npy')
        assert file.exists(),file
        data.append(dict(id=r['record'],group=r['group'],role=r['role'],target=r['target'],x=np.load(file)))
    return data

def abnormal_data():
    data=[]
    for reference in sorted((ROOT/'cache/physionet2016').glob('training-*/REFERENCE_withSQI.csv')):
        source=reference.parent.name[-1]
        if source=='f':continue
        for name,label,quality in csv.reader(reference.open()):
            data.append(dict(id=name,group=source,role='selection' if source=='b' else 'training',target=2 if quality=='0' else int(label=='1'),x=audio_feature(reference.parent/(name+'.wav'))))
    return data

def valves_data():
    audited=json.loads((ROOT/'results/bmd-results.json').read_text())['audit'];allowed=set(audited['train_patients'])
    patients=sorted(allowed,key=lambda p:hashlib.sha256(('heartecho-valves-development-20261115:'+p).encode()).hexdigest());selection=set(patients[-18:])
    rows=list(csv.DictReader((ROOT/'cache/bmd/train.csv').open()));data=[]
    for r in rows:
        if r['patient_id'] not in allowed:continue
        data.append(dict(id=r['patient_id'],group=r['patient_id'],role='selection' if r['patient_id'] in selection else 'training',target=[int(r[k]) for k in ['AS','AR','MR','MS']],x=[audio_feature(ROOT/'cache/bmd/train'/(r[f'recording_{j}']+'.wav')) for j in range(1,9)]))
    return data

def predict(model,data,device,bag):
    model.eval();prob=[]
    with torch.inference_mode():
        for r in data:
            if bag:
                # Fixed crops throughout each recording; average patient predictions.
                patient=[]
                for q in [.1,.5,.9]:
                    xs=[]
                    for a in r['x']:
                        start=int((a.shape[1]-FRAMES)*q);xs.append(a[:,start:start+FRAMES])
                    patient.append(model(torch.tensor(np.stack(xs)[None],device=device)).sigmoid().cpu().numpy()[0])
                p=np.mean(patient,0)
            else:
                a=r['x'];starts=range(0,max(1,a.shape[1]-FRAMES+1),FRAMES);xs=[a[:,s:s+FRAMES] for s in starts if a[:,s:s+FRAMES].shape[1]==FRAMES]
                xs.append(a[:,-FRAMES:]);p=model(torch.tensor(np.stack(xs),device=device)).softmax(1).cpu().numpy().mean(0)
            prob.append(p)
    return np.stack(prob)

def classification_metrics(y,p,bag):
    if not bag:return metrics(y,[decision(r) for r in p])
    y=np.array(y);pred=p>=.5;per={}
    for j,name in enumerate(['AS','AR','MR','MS']):
        tp=int(np.sum((y[:,j]==1)&pred[:,j]));fn=int(np.sum((y[:,j]==1)&~pred[:,j]));fp=int(np.sum((y[:,j]==0)&pred[:,j]));tn=int(np.sum((y[:,j]==0)&~pred[:,j]));per[name]=dict(tp=tp,fn=fn,fp=fp,tn=tn,f1=2*tp/max(2*tp+fp+fn,1),balanced_recall=.5*(tp/max(tp+fn,1)+tn/max(tn+fp,1)))
    return dict(per_condition=per,macro_f1=float(np.mean([v['f1'] for v in per.values()])),macro_balanced_recall=float(np.mean([v['balanced_recall'] for v in per.values()])),exact_patient_match=float(np.mean(np.all(pred==y,1))))

def train(task,epochs=20,steps=70):
    bag=task=='valves';out=ROOT/'generated'/('audio-v2-'+task);out.mkdir(parents=True,exist_ok=True)
    if (out/'complete.json').exists():raise ValueError('Completed run exists; preserve it instead of overwriting')
    torch.manual_seed(20261115);np.random.seed(20261115);torch.set_num_threads(2)
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    protocol=dict(task=task,epochs=epochs,steps=steps,batch=4 if bag else 36,seed=20261115,source_sha256=digest(__file__),initial_weights_sha256=digest(ML/'generated/murmur-v1/Murmur.pt'),selection='Selection partition only; fixed .5 multi-label/.6 three-class thresholds. Max macro-balanced recall, then F1/balanced recall. No test source loaded. Prior tests are consumed regression sets.',features='Original 32-bin log-mel 25..950Hz, 4 seconds; training-only spectral tilt, masking and noise.',optimizer='AdamW encoder lr 0.00003, heads lr 0.0005; encoder frozen first 4 epochs; weight decay .01',scope='Independent research candidates. Not yet promoted to the app. Synthetic EQ augmentation is not phone validation.')
    protocol_path=out/'protocol.json'
    if protocol_path.exists():raise ValueError('Run already started; inspect its live handle/checkpoint before restarting')
    save(protocol_path,protocol)
    print(json.dumps({'stage':'prepare','task':task,'device':str(device)}),flush=True)
    data={'murmur':murmur_data,'abnormal':abnormal_data,'valves':valves_data}[task]()
    training=[r for r in data if r['role']=='training'];selection=[r for r in data if r['role']=='selection']
    assert not set(r['group'] for r in training)&set(r['group'] for r in selection)
    save(out/'split.json',{role:[{'id':r['id'],'group':r['group'],'target':r['target']} for r in data if r['role']==role] for role in ['training','selection','calibration']})
    model=AudioClassifier(4 if bag else 3,bag).to(device);optimizer=torch.optim.AdamW([{'params':model.encoder.parameters(),'lr':3e-5},{'params':list(model.head.parameters())+list(model.attention.parameters()),'lr':5e-4}],weight_decay=.01)
    rng=np.random.default_rng(20261115);best=(-1.,-1.);history=[]
    pools=[[r for r in training if r['target']==i] for i in range(3)] if not bag else None
    pos=None
    if bag:
        y=np.array([r['target'] for r in training]);pos=torch.tensor(np.clip((len(y)-y.sum(0))/np.maximum(y.sum(0),1),.5,5),dtype=torch.float32,device=device)
    for epoch in range(epochs+1):
        began=time.perf_counter();model.train();losses=[]
        for p in model.encoder.parameters():p.requires_grad_(epoch>4)
        for step in range(steps if epoch else 0):
            if bag:batch=[training[int(rng.integers(len(training)))] for _ in range(4)];xs=np.stack([[crop(a,rng,True) for a in r['x']] for r in batch]);ys=np.array([r['target'] for r in batch],dtype=np.float32)
            else:
                batch=[pools[j%3][int(rng.integers(len(pools[j%3])))] for j in range(36)];xs=np.stack([crop(r['x'],rng,True) for r in batch]);ys=np.array([r['target'] for r in batch])
            x=torch.tensor(xs,dtype=torch.float32,device=device);y=torch.tensor(ys,device=device)
            optimizer.zero_grad(set_to_none=True);logits=model(x);loss=F.binary_cross_entropy_with_logits(logits,y,pos_weight=pos) if bag else F.cross_entropy(logits,y)
            loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);optimizer.step();losses.append(float(loss.detach().cpu()))
        probabilities=predict(model,selection,device,bag);result=classification_metrics([r['target'] for r in selection],probabilities,bag)
        score=(result['macro_balanced_recall'],result['macro_f1']) if bag else (result['balanced_recall'],result['decisive_sensitivity'])
        row=dict(epoch=epoch,loss=float(np.mean(losses)) if losses else None,selection=result,seconds=time.perf_counter()-began);history.append(row)
        print(json.dumps(row),flush=True)
        if score>best:
            best=score;torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},out/'best.pt');save(out/'selected.json',row)
        # Recoverable checkpoint is separate from the selected model.
        torch.save({'epoch':epoch,'state':{k:v.detach().cpu() for k,v in model.state_dict().items()}},out/'last.pt');save(out/'history.json',history)
    model.load_state_dict(torch.load(out/'best.pt',map_location=device,weights_only=True));model.eval()
    complete=dict(protocol=protocol,model_sha256=digest(out/'best.pt'),selected=json.loads((out/'selected.json').read_text()),training_examples=len(training),selection_examples=len(selection),source_sha256=digest(__file__))
    save(out/'complete.json',complete)
    print(json.dumps({'stage':'complete','task':task,'best':best}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('task',choices=['murmur','abnormal','valves']);parser.add_argument('--epochs',type=int,default=20);parser.add_argument('--steps',type=int,default=70);a=parser.parse_args();train(a.task,a.epochs,a.steps)
