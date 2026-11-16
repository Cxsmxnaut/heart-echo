"""V12: refit only M2D decision heads on exact public native audio.

The V11 encoder stays bit-identical. All fitting/statistics use training people.
This job exports the declared candidate heads; final selection happens locally
before calibration and can reject every candidate. No private profile is used.
"""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import time
import zipfile

import numpy as np
from scipy import signal
import torch
from torch import nn
from torch.nn import functional as F

from m2d_murmur import M2DMurmur,HERE,sha,offsets,decide
from train_m2d_murmur import validate_config,save,tensor_sha
from murmur_focus_metrics import aggregate

ENCODER_CHECKPOINT='e89b4a8bff063b3fed7702666f691e606737c297f14a156dae25da3624097b4e'
POSITIVE_COSTS=(2.,4.,8.,12.)
SAVE_ROUNDS=(4,8,16)


def weighted_loss(logits,labels,positive_cost):
    costs=logits.new_tensor([1.,positive_cost,4.])[labels]
    hard=(labels==0)&(logits.detach().softmax(1)[:,1]>.2)
    costs=costs*torch.where(hard,3.,1.)
    return (F.cross_entropy(logits,labels,reduction='none')*costs).sum()/costs.sum()


def windows(wave,training=False):
    if len(wave)<8000:return np.empty((0,80000),dtype=np.float32)
    x=signal.resample_poly(wave,8,1).astype(np.float32)
    if len(x)<80000:x=np.pad(x,(0,80000-len(x)))
    good=[]
    for start in offsets(len(x),training):
        crop=x[start:start+80000]
        if np.isfinite(crop).all() and np.mean(crop.astype(np.float64)**2)>=.00002**2 and np.mean(np.abs(crop)>=.999)<=.01:
            good.append(crop)
    return np.stack(good) if good else np.empty((0,80000),dtype=np.float32)


def generic_phone(wave,record):
    seed=int(hashlib.sha256(('v12-generic:'+record).encode()).hexdigest()[:8],16)
    rng=np.random.default_rng(seed)
    freq=np.fft.rfftfreq(len(wave),1/2000)
    anchors=np.array([0.,30.,80.,160.,320.,600.,950.,1000.])
    gain=np.interp(freq,anchors,rng.uniform(-6,6,len(anchors)))
    styled=np.fft.irfft(np.fft.rfft(wave)*10**(gain/20),n=len(wave))
    styled*=10**rng.uniform(-6/20,3/20)
    noise=rng.standard_normal(len(wave))
    rms=lambda a:np.sqrt(np.mean(a*a)+1e-24)
    styled+=noise/rms(noise)*rms(styled)*10**(-rng.uniform(24,36)/20)
    styled/=max(1.,float(np.max(np.abs(styled)))/.98)
    return styled.astype(np.float32)


def public_input(path,expected_config,expected_zip):
    if path.is_file():
        assert sha(path)==expected_zip,'Wrong public native archive'
        archive=zipfile.ZipFile(path)
        data=archive.read('public-config.json')
        read=archive.read
    else:
        data=(path/'public-config.json').read_bytes()
        read=lambda name:(path/name).read_bytes()
        archive=None
    assert hashlib.sha256(data).hexdigest()==expected_config
    config=json.loads(data);validate_config(config)
    assert config['rate']==2000 and config['phone_profile_included'] is False
    assert config['calibration_or_test_included'] is False and len(config['records'])==2536
    allowed={'public-config.json'}|{r['native_file'] for r in config['records']}
    assert len(allowed)==2537
    for r in config['records']:
        assert r['native_file']=='audio/'+r['record']+'.f32'
    if archive:
        assert set(archive.namelist())==allowed and len(archive.namelist())==len(allowed)
        assert all(i.file_size<2*1024**2 and (i.external_attr>>16)&0o170000!=0o120000 for i in archive.infolist())
    return config,read


def encoder_fingerprints(model):
    return {k:tensor_sha(v) for k,v in model.runtime.state_dict().items()}


def snapshot(linear,mean,var):
    return {'norm':{'running_mean':mean.cpu().clone(),'running_var':var.cpu().clone(),
                    'num_batches_tracked':torch.tensor(1,dtype=torch.long)},
            'classifier':{k:v.detach().cpu().clone() for k,v in linear.state_dict().items()}}


def select_predictions(head,records,device):
    weight=head['classifier']['weight'].to(device);bias=head['classifier']['bias'].to(device)
    mean=head['norm']['running_mean'].to(device);std=(head['norm']['running_var'].to(device)+1e-5).sqrt()
    values={}
    with torch.inference_mode():
        for r in records:
            if not len(r['embedding']):p=np.array([0.,0.,1.])
            else:
                x=torch.from_numpy(r['embedding']).to(device)
                p=F.linear((x-mean)/std,weight,bias).mean(0).softmax(0).cpu().numpy()
            values[r['record']]={'reading':{'probabilities':p.tolist(),'finding':decide(p),'windows':len(r['embedding'])}}
    return values


def train(args):
    os.umask(0o077);torch.set_num_threads(2);torch.manual_seed(20261115)
    if args.output.exists():raise ValueError('Preserve existing runs')
    config,read=public_input(args.bundle,args.config_sha,args.bundle_sha)
    if not torch.cuda.is_available():raise RuntimeError('CUDA GPU required')
    args.output.mkdir(parents=True)
    protocol=dict(encoder_checkpoint_sha256=ENCODER_CHECKPOINT,encoder_frozen=True,
        confidence_threshold=.60,positive_costs=list(POSITIVE_COSTS),unknown_cost=4.,
        hard_negative='True absent with detached Present probability>.2 receives3x loss weight',
        optimizer='AdamW lr3e-4 weight_decay.05;16epochs per head; batch256; float32',
        retained_rounds=list(SAVE_ROUNDS),normalization='Mean/population variance of training embeddings only; epsilon1e-5',
        augmentation='Deterministic generic EQ<=6dB, gain -6..3dB, synthesized noise SNR24..36dB; no private profile',
        private_audio_included=False,private_profile_included=False,calibration_or_test_loaded=False,
        config_sha256=args.config_sha,bundle_sha256=args.bundle_sha,
        source_sha256={n:sha(HERE/n) for n in ['m2d_murmur.py','train_m2d_murmur.py','murmur_focus_metrics.py','train_m2d_native_heads.py']},
        environment=dict(torch=torch.__version__,gpu=torch.cuda.get_device_name(0)),
        evidence='Reused development only; this is head refinement, not new encoder training or independent phone validation')
    save(args.output/'protocol.json',protocol)
    if zipfile.is_zipfile(args.checkpoint_archive) and args.checkpoint_archive.suffix=='.zip':
        with zipfile.ZipFile(args.checkpoint_archive) as source:
            raw=source.read('artifacts/M2D.pt')
    else:raw=args.checkpoint_archive.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==ENCODER_CHECKPOINT
    state=torch.load(io.BytesIO(raw),map_location='cpu',weights_only=True);del raw
    device=torch.device('cuda:0')
    model=M2DMurmur(args.cache).eval();model.load_state_dict(state);del state
    model.requires_grad_(False);model.to(device)
    before=encoder_fingerprints(model)
    training=[];labels=[];selection=[];audit=[]
    for i,r in enumerate(config['records'],1):
        raw=read(r['native_file']);assert hashlib.sha256(raw).hexdigest()==r['native_sha256']
        wave=np.frombuffer(raw,dtype='<f4').copy()
        assert len(wave)==r['samples'] and np.isfinite(wave).all()
        variants=[wave,generic_phone(wave,r['record'])] if r['role']=='training' else [wave]
        counts=[]
        for variant in variants:
            crops=windows(variant,r['role']=='training');parts=[]
            with torch.inference_mode():
                for start in range(0,len(crops),16):
                    mel=model.features(torch.from_numpy(crops[start:start+16]).to(device))
                    embedding=model.runtime.encode_lms(model.runtime.normalize_batch(mel)).mean(1)
                    parts.append(embedding.cpu().numpy())
            embedded=np.concatenate(parts) if parts else np.empty((0,3840),dtype=np.float32)
            counts.append(len(embedded))
            if r['role']=='training':
                if len(embedded):training.append(embedded);labels.extend([r['target']]*len(embedded))
            else:selection.append(dict(r,embedding=embedded))
        audit.append(dict(record=r['record'],role=r['role'],windows=counts,native_sha256=r['native_sha256']))
        if i%100==0:print(json.dumps(dict(stage='public_embeddings',records=i,total=len(config['records']))),flush=True)
    assert len(selection)==180 and {r['group'] for r in selection}.isdisjoint({r['group'] for r in config['records'] if r['role']=='training'})
    features=torch.from_numpy(np.concatenate(training)).to(device);del training
    targets=torch.tensor(labels,dtype=torch.long,device=device)
    counts=torch.bincount(targets,minlength=3).cpu().tolist();assert min(counts)>0
    mean=features.mean(0);var=features.var(0,unbiased=False).clamp_min(1e-8)
    normalized=(features-mean)/(var+1e-5).sqrt();del features
    save(args.output/'data-audit.json',dict(training_records=2356,selection_records=180,training_windows=len(labels),
        training_class_counts=counts,records=audit,persons_disjoint=True,training_only_normalization=True))
    old_weight=model.classifier.weight.detach().clone();old_bias=model.classifier.bias.detach().clone()
    old_mean=model.norm.running_mean;old_std=(model.norm.running_var+model.norm.eps).sqrt()
    initial_weight=old_weight*((var+1e-5).sqrt()/old_std)
    initial_bias=old_bias+old_weight@((mean-old_mean)/old_std)
    heads={};history=[]
    control=nn.Linear(3840,3).to(device)
    with torch.no_grad():control.weight.copy_(old_weight);control.bias.copy_(old_bias)
    heads['normalization_only']=snapshot(control,mean,var)
    for cost in POSITIVE_COSTS:
        linear=nn.Linear(3840,3).to(device)
        with torch.no_grad():linear.weight.copy_(initial_weight);linear.bias.copy_(initial_bias)
        optimizer=torch.optim.AdamW(linear.parameters(),lr=3e-4,weight_decay=.05)
        generator=torch.Generator().manual_seed(20261115)
        for epoch in range(1,17):
            began=time.perf_counter();order=torch.randperm(len(labels),generator=generator).to(device);losses=[]
            for start in range(0,len(labels),256):
                index=order[start:start+256];optimizer.zero_grad(set_to_none=True)
                loss=weighted_loss(linear(normalized[index]),targets[index],cost)
                if not torch.isfinite(loss):raise ValueError('Nonfinite head loss')
                loss.backward();optimizer.step();losses.append(float(loss.detach().cpu()))
            row=dict(positive_cost=cost,epoch=epoch,loss=float(np.mean(losses)),seconds=time.perf_counter()-began)
            if epoch in SAVE_ROUNDS:
                name=f'positive_cost_{int(cost)}_epoch_{epoch}'
                heads[name]=snapshot(linear,mean,var)
                p=select_predictions(heads[name],selection,device)
                row['selection']=aggregate(selection,p)['recordings']
            history.append(row);print(json.dumps(dict(stage='head_training',**row)),flush=True)
    assert encoder_fingerprints(model)==before,'The encoder changed during head-only fitting'
    assert len(heads)==13
    for name,head in heads.items():
        assert all(torch.isfinite(v).all() for group in head.values() for v in group.values())
        if name!='normalization_only':
            assert not torch.equal(head['classifier']['weight'],initial_weight.cpu())
            assert not torch.equal(head['classifier']['bias'],initial_bias.cpu())
    torch.save(heads,args.output/'native-heads.pt')
    predictions={name:select_predictions(head,selection,device) for name,head in heads.items()}
    save(args.output/'selection-predictions.json',predictions);save(args.output/'history.json',history)
    proof=dict(status='native_head_training_complete',encoder_unchanged=True,encoder_fingerprints=before,
        candidate_heads=13,trained_checkpoints=12,training_cost_runs=4,normalization_control=1,epochs_per_cost=16,
        heads_sha256=sha(args.output/'native-heads.pt'),protocol_sha256=sha(args.output/'protocol.json'),
        calibration_or_test_loaded=False,private_audio_used=False,private_profile_used=False)
    save(args.output/'complete.json',proof)
    print(json.dumps(dict(complete=True,candidate_heads=13,encoder_unchanged=True)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['bundle','checkpoint-archive','output','cache']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--config-sha',required=True);p.add_argument('--bundle-sha',required=True)
    args=p.parse_args()
    try:train(args)
    finally:
        if args.output.exists():
            with zipfile.ZipFile(args.output.parent/'heart-m2d-native-heads.zip','w',zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(args.output.rglob('*')):
                    if path.is_file():archive.write(path,'artifacts/'+str(path.relative_to(args.output)))
