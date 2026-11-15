"""Candidate G: require weakly supervised between-sound murmur evidence."""
import json
from pathlib import Path
import coremltools as ct
import numpy as np
import torch
from torch import nn
from murmur_model import ROOT, Frontend, FRAMES, SAMPLES
from murmur_timing_model import TimingMurmurNet
from murmur_phase_data import PHASE_MANIFEST
from murmur_data import digest, save

OUTPUT=ROOT/'generated/murmur-phase-g'


def require_evidence(probabilities, phases, murmur):
    weights=phases[:,[2,4]]
    score=((weights*murmur[:,None]).sum(2)/weights.sum(2).clamp_min(1e-6)).amax(1)
    gate=(score/.4).clamp(max=1)
    removed=probabilities[:,1]*(1-gate)
    return torch.stack([probabilities[:,0],probabilities[:,1]-removed,probabilities[:,2]+removed],1)


class EvidenceModel(nn.Module):
    def __init__(self):
        super().__init__();self.front=Frontend();self.classifier=TimingMurmurNet()

    def forward(self,waveform):
        logits,phase,murmur=self.classifier.joint(self.front(waveform));q=phase.softmax(1);m=murmur.sigmoid()
        return require_evidence(logits.softmax(1),q,m),q,m


def main():
    if OUTPUT.exists():raise ValueError('G exists; refusing overwrite')
    for name in ['murmur-freeze.json','murmur-phase-c-freeze.json']:
        for path,expected in json.loads((ROOT/name).read_text())['sha256'].items():assert digest(ROOT.parent.parent/path)==expected
    OUTPUT.mkdir(parents=True);torch.set_num_threads(1);torch.manual_seed(6414)
    model=EvidenceModel();model.classifier.load_state_dict(torch.load(ROOT/'generated/murmur-phase-c/Murmur.pt',weights_only=True));model.eval()
    rows=[r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role']=='training'];audit=[]
    for label in [0,1,2]:
        for r in sorted([r for r in rows if r['target']==label],key=lambda r:r['record'])[:100]:
            x=torch.from_numpy(np.load(ROOT/'generated/murmur-v1/features'/(r['record']+'.npy'))[:,:FRAMES])[None]
            with torch.inference_mode():
                _,q,t=model.classifier.joint(x);q=q.softmax(1)[:,[2,4]];score=((q*t.sigmoid()[:,None]).sum(2)/q.sum(2)).amax().item()
            audit.append(dict(record=r['record'],target=label,evidence=score))
    save(OUTPUT/'training-evidence-audit.json',audit)
    save(OUTPUT/'protocol.json',dict(method='C classPresent probability scaled by min(1,evidence/.4); removed mass moves toUnknown, Absent unchanged. Evidence=max(phaseweightedmean frameMurmur in systole,diastole). Predicted phases only.',
        choice='Singlefixed.4knot basedon first100alphabeticTRAININGrecords/class evidence: positive25thpercentile~.400,normalmedian~.208. No G selection/calibration/test results accessed to choose knot. Trainingquantiles exploratory,notvalidation. No other knots searched.',
        comparability='Same2ppFP,5ppUnsure,2pppositive-asAbsent limits; must improve detections. C calibration already development. No clinical/phone accuracy claim.',source_sha256=digest(Path(__file__))))
    torch.save(model.state_dict(),OUTPUT/'Murmur.pt');names=['probabilities','phase_probabilities','murmur_timing']
    converted=ct.convert(torch.jit.trace(model,torch.randn(1,1,SAMPLES)*.03),inputs=[ct.TensorType(name='waveform',shape=(1,1,SAMPLES))],outputs=[ct.TensorType(name=n) for n in names],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
    converted.author='Chest BPM public-data research';converted.short_description='Phase and between-sound murmur evidence; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',labels='Absent,Present,Unknown',phase_labels='noise,S1,systole,S2,diastole',dataset='https://doi.org/10.13026/tshs-mw03',weights_sha256=digest(OUTPUT/'Murmur.pt'))
    converted.save(str(OUTPUT/'Murmur.mlpackage'));errors=[]
    for scale in [0,.0001,.01,.3]:
        x=torch.randn(1,1,SAMPLES)*scale
        with torch.inference_mode():expected=model(x)
        actual=converted.predict({'waveform':x.numpy()});errors.append([float(np.max(np.abs(v.numpy()-actual[n]))) for v,n in zip(expected,names)])
    assert np.max(errors)<.001,errors
    save(OUTPUT/'conversion.json',dict(maximum_probability_differences=np.max(errors,0).tolist(),examples=4));print('Native G conversion passed',errors,flush=True)


if __name__=='__main__':main()
