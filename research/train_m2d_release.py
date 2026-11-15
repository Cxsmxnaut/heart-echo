"""M2D arm following the released optimizer/loss rather than paper prose.

The official pinned batch command defaults to SGD(momentum=.9,weight_decay=0).
Its WeightedCE patch applies softmax before weighted soft-target cross entropy.
Both choices are reproduced here, despite differing from the paper description.
Shared data, model, seed, selection rule and 50-epoch schedule match the first arm.
CUDA mixed precision is a computational adaptation; this is not a bitwise replay.
"""
import argparse
import json
import os
from pathlib import Path
import time
import zipfile

import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import DataLoader
from timm.scheduler import CosineLRScheduler

from m2d_murmur import M2DMurmur,HERE,sha
from train_m2d_murmur import save,validate_config,prepare,Crops,evaluate,tensor_sha


def released_loss(logits,targets,weights):
    return F.cross_entropy(logits.float().softmax(1),F.one_hot(targets,3).float(),weight=weights)


def train(args):
    os.umask(0o077);output=args.output.resolve()
    if output.exists():
        raise ValueError('Preserve completed and partial runs')
    config=json.loads(args.config.read_text());validate_config(config)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU required')
    output.mkdir(parents=True)
    torch.set_num_threads(2);torch.manual_seed(20261120);np.random.seed(20261120)
    torch.cuda.manual_seed_all(20261120);device=torch.device('cuda:0')
    protocol=dict(seed=20261120,epochs=50,batch_size=32,learning_rate=.00025,
        variant='released_code_optimizer_and_loss',
        optimizer='SGD momentum.9 weight_decay0, as released default',
        loss='Released WeightedCE: softmax(logits) -> weighted soft-target CE; double class weights N/(3*count)',
        scheduler='Cosine, five-epoch warmup, minimum LR1e-7',
        training='Same public5s16k windows/2.5s stride; all12blocks fine-tuned; no augmentation',
        selection='Highest recording-level three-class balanced recall at.60 on selection; mean5s logits; first maximum',
        threshold=.60,private_audio_included=False,phone_profile_included=False,calibration_or_test_loaded=False,
        config_sha256=sha(args.config),
        source_sha256={name:sha(HERE/name) for name in ['m2d_murmur.py','train_m2d_murmur.py','train_m2d_release.py','murmur_focus_metrics.py']},
        environment=dict(torch=torch.__version__,gpu=torch.cuda.get_device_name(0)),
        deviations_from_original=['Existing linked-person split and recording-level murmur targets.',
          'One seeded run; recording selection at.60 rather than validation-window accuracy.',
          'Unchanged authors portable encoder; SciPy16k resampling,cap60s; CUDA mixed precision.',
          'Second arm declared after first5 paper-arm epochs; no calibration outcome inspected.'],
        evidence='Reused public development; no independent clinical phone validation.',
        use_restriction='NTT non-commercial internal evaluation; not a production app replacement')
    save(output/'protocol.json',protocol)
    model=M2DMurmur(args.cache/'upstream').to(device)
    parameter_names=dict(model.named_parameters())
    initial={k:tensor_sha(v) for k,v in parameter_names.items()}
    save(output/'initial-parameter-fingerprints.json',initial)
    data=prepare(config,args.cache/'public-audio',model,device)
    training=[r for r in data if r['role']=='training'];selection=[r for r in data if r['role']=='selection']
    dataset=Crops(training);counts=np.bincount(dataset.labels,minlength=3)
    if (counts==0).any():
        raise ValueError('Missing public training class')
    weights=torch.tensor(len(dataset)/(3*counts),dtype=torch.float64,device=device)
    generator=torch.Generator().manual_seed(protocol['seed'])
    loader=DataLoader(dataset,batch_size=32,shuffle=True,drop_last=True,num_workers=0,pin_memory=True,generator=generator)
    save(output/'data-audit.json',dict(training_recordings=len(training),selection_recordings=len(selection),
        training_crops=len(dataset),training_class_counts=counts.tolist(),class_weights=weights.cpu().tolist(),
        optimizer_steps_per_epoch=len(loader),persons_disjoint=True,
        public_audio_source_sha256={r['record']:r['sha256'] for r in data}))
    optimizer=torch.optim.SGD([p for p in model.parameters() if p.requires_grad],lr=.00025,momentum=.9,weight_decay=0.)
    scheduler=CosineLRScheduler(optimizer,t_initial=50,lr_min=1e-7,warmup_t=5,warmup_lr_init=0.)
    scaler=torch.amp.GradScaler('cuda');history=[];best=-1.;steps=0
    for epoch in range(50):
        began=time.perf_counter();model.train();losses=[]
        for step,(features,targets) in enumerate(loader):
            features=features.to(device,non_blocking=True);targets=targets.to(device,non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.float16):
                loss=released_loss(model(features),targets,weights)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite released-recipe loss')
            scaler.scale(loss).backward();scaler.step(optimizer);scaler.update()
            scheduler.step(epoch+(step+1)/len(loader));steps+=1
            losses.append(float(loss.detach().cpu()))
            if step%100==0:
                print(json.dumps(dict(epoch=epoch+1,step=step+1,steps=len(loader),loss=losses[-1],
                    lr=optimizer.param_groups[0]['lr'])),flush=True)
        score,results,predictions=evaluate(model,selection,device)
        row=dict(epoch=epoch+1,optimizer_steps=steps,loss=float(np.mean(losses)),seconds=time.perf_counter()-began,
            selection_score=score,selection=results['recordings'])
        if score>best:
            best=score;temporary=output/'best.pending'
            torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},temporary)
            temporary.replace(output/'M2D.pt')
            save(output/'selected.json',dict(epoch=epoch+1,score=score,results=results))
            save(output/'selection-predictions.json',predictions)
        history.append(row);save(output/'history.json',history)
        print(json.dumps(row),flush=True)
    selected=torch.load(output/'M2D.pt',map_location='cpu',weights_only=True)
    changed=[k for k in initial if tensor_sha(selected[k])!=initial[k]]
    frozen=[k for k,p in parameter_names.items() if not p.requires_grad]
    assert all(tensor_sha(selected[k])==initial[k] for k in frozen)
    blocks=sorted({int(k.split('.')[3]) for k in changed if k.startswith('runtime.backbone.blocks.')})
    assert blocks==list(range(12)) and all(torch.isfinite(v).all() for v in selected.values())
    proof=dict(optimizer_steps=steps,epochs_run=50,selected=json.loads((output/'selected.json').read_text())['epoch'],
        changed_parameter_tensors=len(changed),changed_transformer_blocks=blocks,frozen_parameter_tensors=len(frozen),
        all_frozen_parameters_unchanged=True,all_saved_tensors_finite=True,weights_sha256=sha(output/'M2D.pt'),
        private_audio_used=False,calibration_or_test_loaded=False)
    save(output/'training-proof.json',proof)
    save(output/'complete.json',dict(status='m2d_training_complete',proof=proof,protocol_sha256=sha(output/'protocol.json')))
    print(json.dumps(dict(complete=True,proof=proof)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args()
    try:
        train(args)
    finally:
        if args.output.exists():
            with zipfile.ZipFile(args.output.parent/'heart-m2d-stage.zip','w',zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(args.output.rglob('*')):
                    if path.is_file() and path.name!='best.pending':
                        archive.write(path,'artifacts/'+str(path.relative_to(args.output)))
