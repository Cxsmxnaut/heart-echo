"""Public-only M2D fine-tuning with a frozen, person-separated comparison plan.

Uses the paper's 50 epochs, AdamW, LR .00025, batch32, five warmup epochs,
five-second windows, balanced CE and no SpecAugment/mixup. It retains our existing
groups, recording-level labels and .60 decision rule. It is not an exact paper
score reproduction: released EVAR code differs from the paper in optimizer and
loss, and the paper also used different splits and repeated seeds.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import time
import zipfile

import numpy as np
from scipy import signal
import soundfile as sf
import torch
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset
from timm.scheduler import CosineLRScheduler

from m2d_murmur import M2DMurmur, RATE, SAMPLES, offsets, download, sha, decide, HERE
from murmur_focus_metrics import aggregate


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def validate_config(config):
    if config.get('public_only') is not True or config.get('private_audio_included') is not False:
        raise ValueError('Only public data are authorized for this job')
    seen = {}
    for r in config['records']:
        if r['role'] not in ['training', 'selection']:
            raise ValueError('Calibration and test records are forbidden in training jobs')
        if seen.setdefault(r['group'], r['role']) != r['role']:
            raise ValueError('One person appears in multiple partitions')
        path = Path(r['file'])
        if path.parts[0] != 'training_data' or '..' in path.parts or path.suffix != '.wav':
            raise ValueError('Only allowlisted public WAV filenames are accepted')


def prepare(config, cache, model, device):
    validate_config(config)  # All records checked before the first network request.
    def read(r):
        path = cache / r['file']
        download('https://physionet.org/files/circor-heart-sound/1.0.3/' + r['file'], path, r['sha256'])
        info = sf.info(path)
        audio, rate = sf.read(path, frames=int(info.samplerate * 60), dtype='float32')
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError('Invalid public waveform')
        divisor = math.gcd(rate, RATE)
        audio = signal.resample_poly(audio, RATE // divisor, rate // divisor).astype(np.float32)
        if len(audio) < SAMPLES:
            audio = np.pad(audio, (0, SAMPLES - len(audio)))
        return r, audio
    rows = []
    model.eval()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, (r, audio) in enumerate(pool.map(read, config['records']), 1):
            windows = np.stack([audio[s:s + SAMPLES] for s in offsets(len(audio), r['role'] == 'training')])
            with torch.inference_mode():
                mel = model.features(torch.from_numpy(windows).to(device)).cpu().numpy()
            rows.append(dict(r, mel=mel, seconds=len(audio) / RATE))
            if index % 200 == 0:
                print(json.dumps({'public_records_prepared': index, 'total': len(config['records'])}), flush=True)
    return rows


class Crops(Dataset):
    def __init__(self, rows):
        self.rows = rows
        self.indices = [(i, j) for i, r in enumerate(rows) for j in range(len(r['mel']))]
        self.labels = np.asarray([rows[i]['target'] for i, j in self.indices])

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, index):
        i, j = self.indices[index]
        return torch.from_numpy(self.rows[i]['mel'][j]), self.rows[i]['target']


def evaluate(model, rows, device):
    model.eval(); values = {}
    with torch.inference_mode():
        for r in rows:
            logits = []
            for start in range(0, len(r['mel']), 16):
                x = torch.from_numpy(r['mel'][start:start + 16]).to(device)
                logits.append(model(x).float().cpu())
            p = torch.cat(logits).mean(0).softmax(0).numpy()
            values[r['record']] = {'reading': {'finding': decide(p), 'probabilities': p.tolist(),
                                               'windows': len(r['mel'])}}
    result = aggregate(rows, values)
    matrix = np.asarray(result['recordings']['matrix'])
    score = float(np.mean(np.diag(matrix) / np.maximum(matrix.sum(1), 1)))
    return score, result, values


def tensor_sha(value):
    return hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def train(args):
    os.umask(0o077)
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Preserve completed and partial runs; use a new output directory')
    config = json.loads(args.config.read_text()); validate_config(config)
    if not torch.cuda.is_available():
        raise RuntimeError('This full training job requires a CUDA GPU')
    output.mkdir(parents=True)
    torch.set_num_threads(2); torch.manual_seed(20261120); np.random.seed(20261120)
    torch.cuda.manual_seed_all(20261120)
    device = torch.device('cuda:0')
    protocol = dict(seed=20261120, epochs=50, batch_size=32, learning_rate=.00025,
        optimizer='AdamW betas(.9,.95), weight_decay.0001, amsgrad=True',
        scheduler='Cosine, five-epoch warmup, minimum LR1e-7',
        loss='Cross entropy on logits; class weights N/(3*class_count) from training crops only',
        training='5s audio at16k, stride2.5s; full epochs over all public training crops; no SpecAugment/mixup',
        feature='Authors unchanged pinned portable M2D; FFT400/hop160,80mel50..8000Hz,centered; norm(-7.1,4.2)',
        backbone='All12 transformer blocks train; patch and fixed positional embeddings frozen',
        selection='Highest recording-level three-class balanced recall at.60 on selection; mean5s logits; first maximum',
        threshold=.60, private_audio_included=False, phone_profile_included=False,
        calibration_or_test_loaded=False, config_sha256=sha(args.config),
        source_sha256={name:sha(HERE/name) for name in ['m2d_murmur.py','train_m2d_murmur.py','murmur_focus_metrics.py']},
        environment=dict(torch=torch.__version__,gpu=torch.cuda.get_device_name(0)),
        deviations_from_paper=['Existing linked-person split and recording-level murmur targets retained.',
          'One seeded run, not paper15-run average; selection uses our.60 recording rule.',
          'SciPy polyphase16k resampling; cap60s; original paper used Torchaudio.',
          'Paper AdamW and raw-logit CE used; released scripts default toSGD and patched loss softmaxes beforeCE.',
          'Authors portable encoder used unchanged; classifier initialized normal(std.01), as EVAR.'],
        evidence='Reused public development only; no independent phone accuracy measurement.',
        use_restriction='NTT non-commercial internal evaluation; not a production app replacement')
    save(output/'protocol.json', protocol)
    model = M2DMurmur(args.cache/'upstream').to(device)
    parameter_names = dict(model.named_parameters())
    initial = {k:tensor_sha(v) for k,v in parameter_names.items()}
    save(output/'initial-parameter-fingerprints.json', initial)
    data = prepare(config, args.cache/'public-audio', model, device)
    training = [r for r in data if r['role']=='training']
    selection = [r for r in data if r['role']=='selection']
    dataset = Crops(training)
    counts = np.bincount(dataset.labels,minlength=3)
    if (counts==0).any():
        raise ValueError('Every class must have public training examples')
    weights = torch.tensor(len(dataset)/(3*counts),dtype=torch.float32,device=device)
    generator = torch.Generator().manual_seed(protocol['seed'])
    loader = DataLoader(dataset,batch_size=32,shuffle=True,drop_last=True,num_workers=0,
                        pin_memory=True,generator=generator)
    save(output/'data-audit.json',dict(training_recordings=len(training),selection_recordings=len(selection),
        training_crops=len(dataset),training_class_counts=counts.tolist(),class_weights=weights.cpu().tolist(),
        optimizer_steps_per_epoch=len(loader),persons_disjoint=True,
        public_audio_source_sha256={r['record']:r['sha256'] for r in data}))
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.00025,
        betas=(.9,.95),weight_decay=.0001,amsgrad=True)
    scheduler = CosineLRScheduler(optimizer,t_initial=50,lr_min=1e-7,warmup_t=5,warmup_lr_init=0.)
    scaler = torch.amp.GradScaler('cuda')
    history=[]; best=-1.; optimizer_steps=0
    for epoch in range(50):
        began=time.perf_counter(); model.train(); losses=[]
        for step,(features,targets) in enumerate(loader):
            features=features.to(device,non_blocking=True); targets=targets.to(device,non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cuda',dtype=torch.float16):
                loss=F.cross_entropy(model(features),targets,weight=weights)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()
            scheduler.step(epoch+(step+1)/len(loader))
            losses.append(float(loss.detach().cpu())); optimizer_steps+=1
            if step%100==0:
                print(json.dumps(dict(epoch=epoch+1,step=step+1,steps=len(loader),
                    loss=losses[-1],lr=optimizer.param_groups[0]['lr'])),flush=True)
        score,results,predictions=evaluate(model,selection,device)
        row=dict(epoch=epoch+1,optimizer_steps=optimizer_steps,loss=float(np.mean(losses)),
                 seconds=time.perf_counter()-began,selection_score=score,selection=results['recordings'])
        if score>best:
            best=score
            temporary=output/'best.pending'
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
    changed_blocks=sorted({int(k.split('.')[3]) for k in changed if k.startswith('runtime.backbone.blocks.')})
    assert changed_blocks==list(range(12)) and all(torch.isfinite(v).all() for v in selected.values())
    proof=dict(optimizer_steps=optimizer_steps,epochs_run=50,selected= json.loads((output/'selected.json').read_text())['epoch'],
        changed_parameter_tensors=len(changed),changed_transformer_blocks=changed_blocks,
        frozen_parameter_tensors=len(frozen),all_frozen_parameters_unchanged=True,all_saved_tensors_finite=True,
        weights_sha256=sha(output/'M2D.pt'),private_audio_used=False,calibration_or_test_loaded=False)
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
