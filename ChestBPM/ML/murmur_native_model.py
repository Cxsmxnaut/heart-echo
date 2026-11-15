"""Candidate E: phase model fine-tuning with native audio and matching window gates."""
import json
from pathlib import Path
import time
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from murmur_model import ROOT, MurmurNet, FRAMES, SAMPLES, spectrum, metrics, decision, windows
from murmur_phase_model import PhaseMurmurNet
import murmur_phase_model as phase_module
from murmur_native_data import load_development, predict_native_record, CACHE
from murmur_data import digest, save

OUTPUT = ROOT / 'generated/murmur-phase-e'


def main():
    if OUTPUT.exists(): raise ValueError('E exists; refusing overwrite')
    for name in ['murmur-freeze.json', 'murmur-phase-a-freeze.json']:
        for path, expected in json.loads((ROOT / name).read_text())['sha256'].items(): assert digest(ROOT.parent.parent / path) == expected
    OUTPUT.mkdir(parents=True); torch.set_num_threads(4); torch.manual_seed(5414)
    protocol = dict(seed=5414, epochs=12, steps=100, batch=48, learning_rate=.00005,
        initialization='FrozenA, alllayersjointlyfinetuned, originalv1teacher.',
        preprocessing='PublicdevelopmentAVAudioConverterthroughunchangednativeMurmurAnalyzer.audio; cached2kHzfloat32; exactnativeRMS/clipping/fullwindowgates for selection and training starts.',
        loss='weightedrecordCE[1.1,1,1]+.25phaseCE+.2originalTeacherKL(temp2); originalphaseweights[1,2,1,2,1]. SyntheticwhiteUnknownartifactphase0.',
        selection='MaximumpositiveRecall thenbalancedRecall subjecttoselection50FPrate<=originalv1+.02,Unsure<=v1+.05,positive-asAbsent<=v1+.02. Fixed.60. No oldtestread. Calibrationisreuseddevelopment,notindependent.',
        sources={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__), ROOT/'murmur_native_data.py', CACHE/'manifest.json']})
    save(OUTPUT / 'protocol.json', protocol)
    data = load_development(); selection = [item for item in data if item[0]['role'] == 'selection']
    training = [item for item in data if item[0]['role'] == 'training' and item[0]['usable_frame_starts']]
    save(OUTPUT / 'data-audit.json', dict(training_records_used=len(training), training_records_no_usable_window=sum(item[0]['role']=='training' and not item[0]['usable_frame_starts'] for item in data), cache_manifest_sha256=digest(CACHE/'manifest.json')))
    pools = [[item for item in training if item[0]['target']==c] for c in range(3)]
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    teacher = MurmurNet(); teacher.load_state_dict(torch.load(ROOT/'generated/murmur-v1/Murmur.pt',weights_only=True)); teacher.to(device).eval()
    for p in teacher.parameters(): p.requires_grad_(False)
    truth = [r['target'] for r,_,_ in selection]
    # Verify the Python selection path against frozen native v1 on all367development records.
    old = {r['id']: r['reading'] for r in map(json.loads,(ROOT/'results/murmur-v1/validation-native.ndjson').open())}
    parity = []; baseline_p = []
    for r,x,_ in data:
        if r['role']=='training': continue
        p = predict_native_record(teacher,r,x,device); native=old[r['record']]
        assert len([s for s in windows(r['sample_count']) if s//40 in set(r['usable_frame_starts'])]) == native['windows']
        error = float(np.max(np.abs(p-native['probabilities']))); assert error < .0001,(r['record'],error)
        assert ['absent','present','unsure'][decision(p)] == native['finding']
        parity.append(error)
        if r['role']=='selection': baseline_p.append(p)
    save(OUTPUT/'native-parity.json',dict(records=len(parity),maximum_probability_difference=max(parity),all_window_counts_and_decisions_match=True))
    print('Native v1 parity verified:',len(parity),'records, maximum difference',max(parity),flush=True)
    reference=metrics(truth,[decision(p) for p in baseline_p])
    model=PhaseMurmurNet();model.load_state_dict(torch.load(ROOT/'generated/murmur-phase-a/Murmur.pt',weights_only=True));model.to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.00005,weight_decay=.001);rng=np.random.default_rng(5414);history=[];best=(-1.,-1.)
    def rates(m):return np.array([m['false_alarms']/m['known_negative_cases'],m['unsure']/m['total'],m['missed_positive_as_absent']/m['known_positive_cases']])
    for epoch in range(13):
        began=time.perf_counter();model.train();losses=[]
        for _ in range(100 if epoch else 0):
            xs,ys,qs=[],[],[]
            for j in range(48):
                y=j%3;r,x,q=pools[y][int(rng.integers(len(pools[y])))];start=int(rng.choice(r['usable_frame_starts']))
                a=x[:,start:start+FRAMES].copy();q=q[start:start+FRAMES].copy()
                a+=rng.uniform(-2,2);a+=rng.normal(0,.12,a.shape)
                if rng.random()<.25:
                    f=int(rng.integers(29));a[f:f+3]=a.mean()
                if j>=42:y=2;a=spectrum(rng.normal(0,.03,SAMPLES).astype(np.float32));q=np.zeros(FRAMES,dtype=np.int64)
                xs.append(a);ys.append(y);qs.append(q)
            x=torch.from_numpy(np.stack(xs).astype(np.float32)).to(device);y=torch.tensor(ys,device=device);q=torch.from_numpy(np.stack(qs)).to(device)
            optimizer.zero_grad(set_to_none=True);logits,phases=model.outputs(x)
            ce=F.cross_entropy(logits,y,weight=torch.tensor([1.1,1.,1.],device=device));ph=F.cross_entropy(phases,q,weight=torch.tensor([1.,2.,1.,2.,1.],device=device),ignore_index=-100)
            with torch.no_grad():old_logits=teacher(x[:42])
            kl=F.kl_div(F.log_softmax(logits[:42]/2,1),F.softmax(old_logits/2,1),reduction='batchmean')*4
            loss=ce+.25*ph+.2*kl;loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);optimizer.step();losses.append([float(v.detach().cpu()) for v in [ce,ph,kl]])
        model.eval();result=metrics(truth,[decision(predict_native_record(model,r,x,device)) for r,x,_ in selection]);eligible=bool(np.all(rates(result)<=rates(reference)+[.02,.05,.02]+np.array([1e-12]*3)))
        row=dict(epoch=epoch,selection=result,eligible=eligible,seconds=time.perf_counter()-began,losses=np.mean(losses,0).tolist() if losses else None);history.append(row);print(json.dumps(row),flush=True)
        score=(result['decisive_sensitivity'],result['balanced_recall'])
        if eligible and score>best:best=score;torch.save({k:v.cpu() for k,v in model.state_dict().items()},OUTPUT/'Murmur.pt')
        save(OUTPUT/'training.json',dict(protocol=protocol,baseline=reference,history=history,device=str(device)))
    # Reuse the frozen, verified architecture exporter with a new isolated output path.
    phase_module.OUTPUT=OUTPUT;phase_module.export()


if __name__=='__main__':main()
