"""Murmur V8: V4 plus one fixed distillation term from the frozen app baseline.
Only original CirCor training groups fit weights; selection/calibration are reused
research development sets. No PASCAL or old final-test audio enters training.
"""
import json,time,sys
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from torch import nn
from torch.nn import functional as F
from train_audio_models import ROOT,ML,crop,digest,save
from murmur_model import FRAMES,HOP,BINS,spectrum,metrics,decision,windows
from murmur_timing_data import timing_targets

from train_phase_texture import TexturePhaseNet, predict
from murmur_additive_model import AdditiveModel, add_positive_evidence


def train():
    out=ROOT/'generated/murmur-v8-distillation';out.mkdir(parents=True,exist_ok=True)
    if (out/'protocol.json').exists():raise ValueError('Existing run must be preserved, not restarted')
    torch.manual_seed(20261118);torch.set_num_threads(2);rng=np.random.default_rng(20261118);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    protocol={'source_sha256':digest(__file__),'architecture_source_sha256':digest(ROOT/'train_phase_texture.py'),'single_change':'Only add .20 * temperature2 KL distillation from the frozen M app baseline to V4 loss. V4 architecture, original8Absent/8Present/14Unknown batch, seed, initialization, data, augmentation, optimizer, epochs, steps, threshold and checkpoint rule unchanged.','epochs':32,'steps_per_epoch':90,'batch':30,'seed':20261118,'architecture':'2D local frequency/time convolutions, frequency pooling, temporal context, 5-state phase head, weak murmur timing head, phase-weighted recording classifier','loss':'classification CE + .30 masked phase CE + .35 masked weak timing BCE + .20 temperature2 baseline KL' ,'sampling':'Original V4: eight real crops per class plus six synthetic white-noise Unknown controls. Same gain/tilt and masks. No PASCAL training.','selection':'Max positive detection, then balanced recall, at fixed .60, subject to shipping-model source-selection FP rate +.02, positive-as-Absent not higher, unsure fraction +.05. If no eligible checkpoint, retain best balanced recall for research only.','phase_targets':'Original public semi-supervised phase boundaries; source state0 masked. Weak early/mid/late/holo timing from metadata, not expert dense murmur annotation.','evidence':'All development partitions reused. Final tests already consumed; later regression is not fresh validation.'}
    teacher_weights=ML/'generated/murmur-phase-m/Murmur.pt'
    assert digest(teacher_weights)==json.loads((ROOT/'results/murmur-focus-decision.json').read_text())['baseline_weights_sha256']
    protocol.update(teacher_weights_sha256=digest(teacher_weights),teacher_source_sha256=digest(ML/'murmur_additive_model.py'),control_v4_protocol_sha256=digest(ROOT/'generated/murmur-v4-texture/protocol.json'),distillation_weight=.20,temperature=2.,teacher_scope='Frozen prior app model; selected in historical research. All development and historical test evidence is reused. No new regression audio or predictions read for this experiment.')
    save(out/'protocol.json',protocol);rows=json.loads((ML/'murmur-phase-manifest.json').read_text())['records'];data=[]
    for r in rows:
        if r['role']=='test':continue
        x=np.load(ML/'generated/murmur-v1/features'/(r['record']+'.npy'));phase,timing=timing_targets(r,x.shape[1]);info=sf.info(ML/'cache/circor'/r['file'])
        data.append(dict(r,x=x,phase_targets=phase,timing_targets=timing,sample_count=int(np.ceil(min(info.frames,info.samplerate*60)*2000/info.samplerate))))
    pools=[[r for r in data if r['role']=='training' and r['target']==c] for c in range(3)];validation=[r for r in data if r['role']=='selection'];baseline=json.loads((ROOT/'results/native-v2-murmur-development.json').read_text())['selection']['shipping']
    save(out/'split.json',{role:[r['record'] for r in data if r['role']==role] for role in ['training','selection','calibration']})
    model=TexturePhaseNet().to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=.01);history=[];best=(-1.,-1.);best_unconstrained=-1.
    # Teacher construction must not advance the student's original RNG streams.
    cpu_rng=torch.get_rng_state();mps_rng=torch.mps.get_rng_state() if device.type=='mps' else None
    teacher=AdditiveModel();teacher.load_state_dict(torch.load(teacher_weights,map_location='cpu',weights_only=True));teacher.to(device).eval()
    for parameter in teacher.parameters():parameter.requires_grad_(False)
    torch.set_rng_state(cpu_rng)
    if mps_rng is not None:torch.mps.set_rng_state(mps_rng)
    for epoch in range(33):
        began=time.perf_counter();model.train();losses=[]
        for step in range(90 if epoch else 0):
            xs=[];ys=[];qs=[];ts=[]
            for j in range(30):
                label=j%3;r=pools[label][int(rng.integers(len(pools[label])))];start=int(rng.integers(r['x'].shape[1]-FRAMES+1));a=r['x'][:,start:start+FRAMES].copy();q=r['phase_targets'][start:start+FRAMES].copy();t=r['timing_targets'][start:start+FRAMES].copy()
                a+=rng.uniform(-2,2)+np.linspace(-1,1,BINS)[:,None]*rng.uniform(-2,2);a+=rng.normal(0,.1,a.shape)
                if rng.random()<.25:
                    k=int(rng.integers(BINS-3));a[k:k+3]=a.mean()
                if j>=24:
                    label=2;a=spectrum(rng.normal(0,.03,8000).astype(np.float32));q=np.zeros(FRAMES,dtype=np.int64);t=np.zeros(FRAMES,dtype=np.float32)
                xs.append(a);ys.append(label);qs.append(q);ts.append(t)
            x=torch.tensor(np.stack(xs),dtype=torch.float32,device=device);y=torch.tensor(ys,device=device);q=torch.tensor(np.stack(qs),device=device);t=torch.tensor(np.stack(ts),device=device)
            optimizer.zero_grad(set_to_none=True);logits,phase,timing=model.joint(x);ce=F.cross_entropy(logits,y);ph=F.cross_entropy(phase,q,ignore_index=-100);mask=t!=-100;weak=F.binary_cross_entropy_with_logits(timing[mask],t[mask],pos_weight=torch.tensor(2.,device=device))
            with torch.no_grad():
                proposal,_,_=teacher.proposal(x)
                teacher_p=add_positive_evidence(teacher.baseline(x).softmax(1),proposal)
                soft_teacher=(teacher_p.clamp_min(1e-7).log()/2).softmax(1)
            distillation=F.kl_div((logits/2).log_softmax(1),soft_teacher,reduction='batchmean')*4
            loss=ce+.3*ph+.35*weak+.20*distillation
            loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);optimizer.step();losses.append(float(loss.detach().cpu()))
        p=predict(model,validation,device);result=metrics([r['target'] for r in validation],[decision(v) for v in p]);eligible=result['false_alarms']/result['known_negative_cases']<=baseline['false_alarms']/baseline['known_negative_cases']+.02 and result['missed_positive_as_absent']<=baseline['missed_positive_as_absent'] and result['unsure']/result['total']<=baseline['unsure']/baseline['total']+.05
        score=(result['decisive_sensitivity'],result['balanced_recall']);row={'epoch':epoch,'loss':float(np.mean(losses)) if losses else None,'selection':result,'eligible':eligible,'seconds':time.perf_counter()-began};history.append(row);print(json.dumps(row),flush=True)
        if result['balanced_recall']>best_unconstrained:best_unconstrained=result['balanced_recall'];torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},out/'research-best.pt');save(out/'research-selected.json',row)
        if eligible and score>best:best=score;torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},out/'best.pt');save(out/'selected.json',row)
        save(out/'history.json',history)
    save(out/'complete.json',{'protocol':protocol,'eligible_checkpoint':(out/'best.pt').exists(),'selected':json.loads((out/'selected.json').read_text()) if (out/'selected.json').exists() else None,'research_selected':json.loads((out/'research-selected.json').read_text()),'weights_sha256':digest(out/'best.pt') if (out/'best.pt').exists() else None,'research_weights_sha256':digest(out/'research-best.pt')});print('COMPLETE',best,flush=True)
if __name__=='__main__':train()
