"""V13: adapt the final two blocks with a one-sided knowledge-preservation loss."""
import argparse
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
import zipfile

import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import Dataset,DataLoader

from m2d_murmur import M2DMurmur,HERE,sha,decide
from train_m2d_murmur import save,tensor_sha
from train_m2d_native_heads import public_input,windows,generic_phone,ENCODER_CHECKPOINT
from murmur_focus_metrics import aggregate

EPOCHS=12
SNAPSHOTS=(4,8,12)


def preserving_loss(logits,labels,teacher):
    logits=logits.float();teacher=teacher.float().detach()
    costs=logits.new_tensor([1.,6.,8.])[labels]
    hard=(labels==0)&(logits.detach().softmax(1)[:,1]>.60)
    costs*=torch.where(hard,3.,1.)
    ce=(F.cross_entropy(logits,labels,reduction='none')*costs).sum()/costs.sum()
    target_teacher=teacher.gather(1,labels[:,None]).squeeze(1)
    target_logp=logits.log_softmax(1).gather(1,labels[:,None]).squeeze(1)
    protect=((labels==1)|(labels==2))&(target_teacher>=.60)
    forgetting=F.relu(target_teacher.clamp_min(1e-6).log()-target_logp).square()
    penalty=(forgetting*protect).sum()/protect.sum().clamp_min(1)
    return ce+2*penalty,ce.detach(),penalty.detach()


def trainable_name(name):
    return name.startswith(('runtime.backbone.blocks.10.','runtime.backbone.blocks.11.','classifier.'))


def state_fingerprints(model,frozen_only=False):
    return {k:tensor_sha(v) for k,v in model.state_dict().items() if not frozen_only or not trainable_name(k)}


def load_reference(path):
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as z:raw=z.read('artifacts/M2D.pt')
    else:raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==ENCODER_CHECKPOINT
    return torch.load(io.BytesIO(raw),map_location='cpu',weights_only=True)


def prepare(config,read,teacher,device,cache):
    path=cache/'training-mel.f32';path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise ValueError('Preserve partial cache')
    labels=[];reference=[];selection={'native2k':[],'generic':[]};audit=[]
    with path.open('wb') as output:
        for i,r in enumerate(config['records'],1):
            raw=read(r['native_file']);assert hashlib.sha256(raw).hexdigest()==r['native_sha256']
            wave=np.frombuffer(raw,dtype='<f4').copy()
            assert len(wave)==r['samples'] and np.isfinite(wave).all()
            counts=[]
            for domain,audio in [('native2k',wave),('generic',generic_phone(wave,r['record']))]:
                crops=windows(audio,r['role']=='training');parts=[]
                with torch.inference_mode():
                    for start in range(0,len(crops),16):
                        mel=teacher.features(torch.from_numpy(crops[start:start+16]).to(device))
                        if r['role']=='training':
                            mel.float().cpu().numpy().tofile(output)
                            reference.append(teacher(mel).float().softmax(1).cpu().numpy())
                            labels.extend([r['target']]*len(mel))
                        else:parts.append(mel.cpu().numpy())
                counts.append(len(crops))
                if r['role']=='selection':
                    selection[domain].append(dict(r,mel=np.concatenate(parts) if parts else np.empty((0,1,80,501),dtype=np.float32)))
            audit.append(dict(record=r['record'],role=r['role'],windows=counts,native_sha256=r['native_sha256']))
            if i%200==0:print(json.dumps(dict(stage='native_spectra_and_reference',recordings=i,total=len(config['records']))),flush=True)
    assert path.stat().st_size==len(labels)*80*501*4
    return path,np.asarray(labels,dtype=np.int64),np.concatenate(reference),selection,audit


class Spectra(Dataset):
    def __init__(self,path,labels,reference):
        self.x=np.memmap(path,mode='r',dtype='<f4',shape=(len(labels),1,80,501))
        self.y=labels;self.reference=reference
    def __len__(self):return len(self.y)
    def __getitem__(self,i):return torch.from_numpy(self.x[i].copy()),int(self.y[i]),torch.from_numpy(self.reference[i].copy())


def evaluate(model,records,device):
    predictions={}
    with torch.inference_mode():
        for r in records:
            logits=[]
            for start in range(0,len(r['mel']),16):
                logits.append(model(torch.from_numpy(r['mel'][start:start+16]).to(device)).float().cpu())
            p=torch.cat(logits).mean(0).softmax(0).numpy() if logits else np.array([0.,0.,1.])
            predictions[r['record']]={'reading':{'finding':decide(p),'probabilities':p.tolist(),'windows':len(r['mel'])}}
    return aggregate(records,predictions),predictions


def train(a):
    os.umask(0o077);torch.set_num_threads(2);torch.manual_seed(20261116)
    if a.output.exists():raise ValueError('Preserve completed/partial runs')
    config,read=public_input(a.bundle,a.config_sha,a.bundle_sha)
    assert torch.cuda.is_available(),'CUDA GPU required'
    a.output.mkdir(parents=True)
    protocol=dict(epochs=EPOCHS,retained_epochs=list(SNAPSHOTS),batch_size=32,
        initializer_sha256=ENCODER_CHECKPOINT,trainable='Only transformer blocks10/11 and classifier',
        normalization='Original global/BN statistics frozen; model stays in eval mode; gradients enabled only for listed tensors',
        learning_rates={'last_two_blocks':1e-5,'classifier':3e-5},weight_decay=.0001,
        scheduler='One-round warmup, cosine to.05 of base learning rates',gradient_norm_clip=1.,
        loss='Raw-logit weightedCE costs1/6/8;3x hard false-Present above.60 on true absent;2x one-sided log-probability floor on recognized true present/unknown',
        teacher='Frozen V11; floor only on true present/unknown labels with reference probability>=.60; no penalty when student improves',
        input='Exact public native2k->16k,5s/2.5s training stride; same generic augmentation asV12',
        config_sha256=a.config_sha,bundle_sha256=a.bundle_sha,
        private_audio_included=False,private_profile_included=False,calibration_or_test_loaded=False,
        source_sha256={n:sha(HERE/n) for n in ['m2d_murmur.py','train_m2d_murmur.py','murmur_focus_metrics.py','train_m2d_native_heads.py','train_m2d_preserving.py']},
        environment={'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0)},
        evidence='Reused development; no independent clinical phone validation, no app update')
    save(a.output/'protocol.json',protocol)
    device=torch.device('cuda:0');state=load_reference(a.checkpoint)
    teacher=M2DMurmur(a.cache/'upstream').eval();teacher.load_state_dict(state)
    teacher.requires_grad_(False);teacher.to(device)
    teacher_before=state_fingerprints(teacher)
    path,labels,reference,selection,audit=prepare(config,read,teacher,device,a.cache)
    assert reference.shape==(len(labels),3) and np.isfinite(reference).all()
    assert teacher_before==state_fingerprints(teacher),'Frozen reference changed'
    assert len(selection['native2k'])==len(selection['generic'])==180
    del teacher
    model=M2DMurmur(a.cache/'upstream').eval();model.load_state_dict(state);del state
    for name,p in model.named_parameters():p.requires_grad_(trainable_name(name))
    model.to(device);frozen=state_fingerprints(model,True)
    initial={k:tensor_sha(v) for k,v in model.named_parameters() if v.requires_grad}
    assert any(k.startswith('runtime.backbone.blocks.10.') for k in initial)
    assert all(trainable_name(k) for k in initial)
    save(a.output/'frozen-initial-sha.json',dict(frozen=frozen,trainable=initial))
    counts=np.bincount(labels,minlength=3).tolist();assert min(counts)>0
    save(a.output/'data-audit.json',dict(training_records=2356,selection_records=180,training_windows=len(labels),training_class_counts=counts,
        teacher_probabilities_from_training_only=True,persons_disjoint=True,records=audit))
    dataset=Spectra(path,labels,reference)
    loader=DataLoader(dataset,batch_size=32,shuffle=True,num_workers=0,pin_memory=True,
                      generator=torch.Generator().manual_seed(20261116))
    blocks=[p for n,p in model.named_parameters() if p.requires_grad and not n.startswith('classifier.')]
    classifier=[p for n,p in model.named_parameters() if p.requires_grad and n.startswith('classifier.')]
    optimizer=torch.optim.AdamW([{'params':blocks,'lr':1e-5,'base_lr':1e-5},
        {'params':classifier,'lr':3e-5,'base_lr':3e-5}],weight_decay=.0001)
    scaler=torch.amp.GradScaler('cuda');history=[];proofs={};batches=0
    for epoch in range(1,EPOCHS+1):
        began=time.perf_counter();losses=[];penalties=[]
        # eval mode intentionally freezes BN/dropout while autograd updates the listed parameters.
        model.eval()
        for step,(mel,target,reference_p) in enumerate(loader):
            phase=(epoch-1)+(step+1)/len(loader)
            factor=phase if phase<1 else .05+.95*.5*(1+math.cos(math.pi*(phase-1)/(EPOCHS-1)))
            for group in optimizer.param_groups:group['lr']=group['base_lr']*factor
            mel=mel.to(device,non_blocking=True);target=target.to(device);reference_p=reference_p.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.float16):loss,ce,penalty=preserving_loss(model(mel),target,reference_p)
            if not torch.isfinite(loss):raise ValueError('Nonfinite preservation loss')
            scaler.scale(loss).backward();scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.)
            scaler.step(optimizer);scaler.update();batches+=1
            losses.append(float(loss.detach().cpu()));penalties.append(float(penalty.cpu()))
            if step%200==0:print(json.dumps(dict(stage='preserving_training',epoch=epoch,step=step+1,steps=len(loader),loss=losses[-1])),flush=True)
        row=dict(epoch=epoch,loss=float(np.mean(losses)),forgetting_penalty=float(np.mean(penalties)),seconds=time.perf_counter()-began,batch_attempts=batches)
        if epoch in SNAPSHOTS:
            assert state_fingerprints(model,True)==frozen,'Frozen features/normalization changed'
            state={k:v.detach().cpu() for k,v in model.state_dict().items()}
            assert all(torch.isfinite(v).all() for v in state.values())
            changed=[k for k,h in initial.items() if tensor_sha(state[k])!=h]
            changed_blocks=sorted({int(k.split('.')[3]) for k in changed if k.startswith('runtime.backbone.blocks.')})
            assert changed_blocks==[10,11] and 'classifier.weight' in changed
            weight_path=a.output/f'M2D-epoch{epoch}.pt';torch.save(state,weight_path);del state
            predictions={};row['selection']={}
            for domain,records in selection.items():
                result,pred=evaluate(model,records,device);predictions[domain]=pred;row['selection'][domain]=result['recordings']
            save(a.output/f'selection-epoch{epoch}.json',predictions)
            proofs[str(epoch)]=dict(weights_sha256=sha(weight_path),changed_transformer_blocks=changed_blocks,
                changed_parameter_tensors=len(changed),frozen_tensors_unchanged=True,all_tensors_finite=True)
        history.append(row);save(a.output/'history.json',history);print(json.dumps(dict(stage='preserving_epoch_complete',**row)),flush=True)
    save(a.output/'complete.json',dict(status='preserving_training_complete',epochs=EPOCHS,batch_attempts=batches,
        snapshots=proofs,protocol_sha256=sha(a.output/'protocol.json'),private_audio_used=False,private_profile_used=False,
        calibration_or_test_loaded=False,app_updated=False))
    print(json.dumps(dict(complete=True,snapshots=list(proofs),frozen_first_ten_blocks=True)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['bundle','checkpoint','output','cache']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--config-sha',required=True);p.add_argument('--bundle-sha',required=True)
    a=p.parse_args()
    try:train(a)
    finally:
        if a.output.exists():
            with zipfile.ZipFile(a.output.parent/'heart-m2d-preserving.zip','w',zipfile.ZIP_DEFLATED) as z:
                for path in sorted(a.output.rglob('*')):
                    if path.is_file():z.write(path,'artifacts/'+str(path.relative_to(a.output)))
