"""Candidate J: train classification heads on confusing public training negatives."""
import copy
import json
from pathlib import Path
import time
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from murmur_model import ROOT,FRAMES,SAMPLES,spectrum,metrics,decision
from murmur_native_data import CACHE,load_development,predict_native_record
from murmur_timing_model import TimingMurmurNet
import murmur_timing_model as timing_module
from murmur_data import digest,save

OUTPUT=ROOT/'generated/murmur-phase-j'


def main():
    if OUTPUT.exists():raise ValueError('J exists; refusing overwrite')
    for name in ['murmur-freeze.json','murmur-phase-c-freeze.json']:
        for path,expected in json.loads((ROOT/name).read_text())['sha256'].items():assert digest(ROOT.parent.parent/path)==expected
    OUTPUT.mkdir(parents=True);torch.manual_seed(7414);torch.set_num_threads(4)
    protocol=dict(seed=7414,epochs=12,steps=100,learning_rate=.0001,batch=48,
        method='Frozen C acoustic backbone,context,phase andweakmurmur heads. Train ONLY recordclassification heads. Halfknownnegative draws from top10%trainingnegative C Present scores; otherhalf uniform. Positives/Unknown uniform.',
        loss='recordCE+.5positiveOnlyCteacherKL(temp2)+.5negativePresentPenalty(-log(1-pPresent)). No validation gradients.',
        selection='On50selectiongroups match originalv1 false-alarm COUNT, unsure<=v1+5pp,positive-asAbsent<=v1+2pp,and strictly moretruepositives. MaxpositiveRecall,thenfewerFP,thenfewerUnsure. Original native pipeline, fixed.60. Calibration reused development,oldtest unread.',
        sources={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'murmur_native_data.py',CACHE/'manifest.json']})
    save(OUTPUT/'protocol.json',protocol)
    data=load_development();training=[a for a in data if a[0]['role']=='training' and a[0]['usable_frame_starts']];selection=[a for a in data if a[0]['role']=='selection']
    pools=[[a for a in training if a[0]['target']==c] for c in range(3)]
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model=TimingMurmurNet();model.load_state_dict(torch.load(ROOT/'generated/murmur-phase-c/Murmur.pt',weights_only=True));model.to(device).eval()
    teacher=copy.deepcopy(model).eval()
    for p in teacher.parameters():p.requires_grad_(False)
    ranking=[]
    for index,(r,x,q) in enumerate(pools[0]):
        p=predict_native_record(teacher,r,x,device);ranking.append((float(p[1]),index))
    ranking.sort(reverse=True);hard=[pools[0][i] for _,i in ranking[:max(1,len(ranking)//10)]]
    save(OUTPUT/'hard-negatives.json',dict(training_only=True,records=[dict(record=pools[0][i][0]['record'],present_score=score) for score,i in ranking[:len(hard)]],all_training_negative_records=len(ranking)))
    print('Ranked training negatives:',len(ranking),'hard pool:',len(hard),flush=True)
    for name,p in model.named_parameters():p.requires_grad_(name.startswith(('head.','phase_head.','timing_head.')))
    assert all(not p.requires_grad for module in [model.layers,model.context,model.phase,model.murmur] for p in module.parameters())
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.0001,weight_decay=.001)
    baseline=json.loads((ROOT/'results/murmur-phase-c/selection-summary.json').read_text())['baseline'];truth=[r['target'] for r,_,_ in selection]
    rng=np.random.default_rng(7414);history=[];best=(-1.,-999,-999)
    for epoch in range(13):
        began=time.perf_counter();model.train();losses=[]
        for _ in range(100 if epoch else 0):
            xs,ys=[],[]
            for j in range(48):
                y=j%3;pool=hard if y==0 and j%2==0 else pools[y];r,x,q=pool[int(rng.integers(len(pool)))];start=int(rng.choice(r['usable_frame_starts']));a=x[:,start:start+FRAMES].copy()
                a+=rng.normal(0,.12,a.shape)
                if j>=42:y=2;a=spectrum(rng.normal(0,.03,SAMPLES).astype(np.float32))
                xs.append(a);ys.append(y)
            x=torch.from_numpy(np.stack(xs).astype(np.float32)).to(device);y=torch.tensor(ys,device=device);optimizer.zero_grad(set_to_none=True);logits=model(x)
            ce=F.cross_entropy(logits,y)
            with torch.no_grad():original=teacher(x[y==1])
            kl=F.kl_div(F.log_softmax(logits[y==1]/2,1),F.softmax(original/2,1),reduction='batchmean')*4
            negative=-torch.log1p(-logits[y==0].softmax(1)[:,1].clamp(max=1-1e-6)).mean()
            loss=ce+.5*kl+.5*negative;loss.backward();nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],2);optimizer.step();losses.append([float(v.detach().cpu()) for v in [ce,kl,negative]])
        model.eval();m=metrics(truth,[decision(predict_native_record(model,r,x,device)) for r,x,_ in selection])
        eligible=m['false_alarms']<=baseline['false_alarms'] and m['unsure']/m['total']<=baseline['unsure']/baseline['total']+.05 and m['missed_positive_as_absent']/m['known_positive_cases']<=baseline['missed_positive_as_absent']/baseline['known_positive_cases']+.02 and m['decisive_sensitivity']>baseline['decisive_sensitivity']
        row=dict(epoch=epoch,selection=m,eligible=eligible,seconds=time.perf_counter()-began,losses=np.mean(losses,0).tolist() if losses else None);history.append(row);print(json.dumps(row),flush=True)
        score=(m['decisive_sensitivity'],-m['false_alarms'],-m['unsure'])
        if eligible and score>best:best=score;torch.save({k:v.cpu() for k,v in model.state_dict().items()},OUTPUT/'Murmur.pt')
        save(OUTPUT/'training.json',dict(protocol=protocol,history=history,baseline=baseline,device=str(device)))
    if not (OUTPUT/'Murmur.pt').exists():print('No eligible improved checkpoint; no model exported.',flush=True);return
    # Frozen C architecture/export checks, isolated J artifacts.
    timing_module.OUTPUT=OUTPUT;timing_module.export()


if __name__=='__main__':main()
