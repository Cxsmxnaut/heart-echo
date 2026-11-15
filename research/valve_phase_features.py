"""Public BMD-HS patient features from our frozen CirCor phase/timing encoder.
No filename tokens, patient IDs or diagnosis metadata enter the feature vectors.
"""
import argparse,csv,json
import numpy as np
import soundfile as sf
import torch
from train_audio_models import ROOT,ML,audio_feature,digest,save
from murmur_timing_model import TimingMurmurNet
from murmur_model import FRAMES,HOP,windows

def features(role):
    output=ROOT/'generated/valves-v3-phase';output.mkdir(parents=True,exist_ok=True)
    weights=ML/'generated/murmur-phase-c/Murmur.pt'
    protocol={'encoder_weights_sha256':digest(weights),'source_sha256':digest(__file__),'method':'For each of eight positions, average 4-second window phase-weighted acoustic contexts (4x64), global mean/max (128), and weak murmur strength by phase (8); preserve fixed acquisition order. 3136 dimensions per patient.','cohort':'Original 86 training patients only until classifier/protocol freeze. Original 22 test patients are consumed retrospective regression. No private/Watch recordings.','inputs':'Audio only; posture/site ordering is fixed by public recording_1..8 metadata; disease filename tokens and patient identifiers are never inputs.'}
    pp=output/'feature-protocol.json'
    if pp.exists():assert json.loads(pp.read_text())==protocol
    else:save(pp,protocol)
    audit=json.loads((ROOT/'results/bmd-results.json').read_text())['audit'];allowed=set(audit['train_patients' if role=='training' else 'test_patients'])
    if role=='regression':assert (output/'classifier-freeze.json').exists(),'Freeze classifier before reading regression audio'
    model=TimingMurmurNet();model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True));model.eval();torch.set_num_threads(2);device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu');model.to(device)
    patients=[];x=[];y=[]
    for row in csv.DictReader((ROOT/'cache/bmd/train.csv').open()):
        if row['patient_id'] not in allowed:continue
        bag=[]
        for j in range(1,9):
            file=ROOT/'cache/bmd/train'/(row[f'recording_{j}']+'.wav');a=audio_feature(file);info=sf.info(file);count=int(np.ceil(min(info.frames,info.samplerate*60)*2000/info.samplerate));starts=[s//HOP for s in windows(count)];v=torch.tensor(np.stack([a[:,s:s+FRAMES] for s in starts]),device=device)
            with torch.inference_mode():
                m=v.mean((1,2),keepdim=True);v=(v-m)/((v-m).square().mean((1,2),keepdim=True)+1).sqrt();h=model.layers(v);h=h+model.context(h);phase=model.phase(h).softmax(1)[:,1:];denom=phase.sum(2).clamp_min(1e-6);contexts=(h[:,None]*phase[:,:,None]).sum(3)/denom[:,:,None];strength=model.murmur(h)[:,0].sigmoid()[:,None]*phase
                f=torch.cat([h.mean(2),h.amax(2),contexts.flatten(1),strength.sum(2)/denom,strength.amax(2)],1).mean(0).cpu().numpy();bag.append(f)
        patients.append(row['patient_id']);x.append(np.concatenate(bag));y.append([int(row[k]) for k in ['AS','AR','MR','MS']])
    np.savez_compressed(output/(role+'.npz'),patients=np.array(patients),x=np.stack(x),y=np.array(y));print(role,len(x),np.stack(x).shape,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('role',choices=['training','regression']);features(p.parse_args().role)
