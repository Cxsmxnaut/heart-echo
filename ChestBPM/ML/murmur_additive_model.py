"""Candidate M: add phase-aware positive evidence while bounding negative confidence."""
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from murmur_model import ROOT,Frontend,MurmurNet,SAMPLES
from murmur_timing_model import TimingMurmurNet
from murmur_phase_data import PHASE_MANIFEST
from murmur_native_data import CACHE
from murmur_data import digest,save

OUTPUT=ROOT/'generated/murmur-phase-m'


def add_positive_evidence(baseline,proposal):
    present=torch.maximum(baseline[:,1],proposal[:,1])
    ratio=(1-present)/(baseline[:,0]+baseline[:,2]).clamp_min(1e-12)
    return torch.stack([baseline[:,0]*ratio,present,baseline[:,2]*ratio],1)


class PhaseProposal(nn.Module):
    def __init__(self):
        super().__init__();self.sound=TimingMurmurNet()
        other=TimingMurmurNet();self.extra_heads=nn.ModuleList([other.head,other.phase_head,other.timing_head])

    def forward(self,x):
        model=self.sound;mean=x.mean(dim=(1,2),keepdim=True)
        x=(x-mean)/((x-mean).square().mean(dim=(1,2),keepdim=True)+1).sqrt()
        h=model.layers(x);h=h+model.context(h);phase=model.phase(h).softmax(1);weights=phase[:,1:]
        denominator=weights.sum(2).clamp_min(1e-6)
        contexts=(h[:,None]*weights[:,:,None]).sum(3)/denominator[:,:,None]
        murmur=model.murmur(h)[:,0].sigmoid();strength=murmur[:,None]*weights
        timing=torch.cat([strength.sum(2)/denominator,strength.amax(2)],1)
        glob=torch.cat([h.mean(2),h.amax(2)],1);ctx=contexts.flatten(1)
        a=model.head(glob)+model.phase_head(ctx)+model.timing_head(timing)
        b=self.extra_heads[0](glob)+self.extra_heads[1](ctx)+self.extra_heads[2](timing)
        return .5*(a.softmax(1)+(b/.7).softmax(1)),phase,murmur


class AdditiveModel(nn.Module):
    def __init__(self):
        super().__init__();self.front=Frontend();self.baseline=MurmurNet();self.proposal=PhaseProposal()

    def forward(self,waveform):
        x=self.front(waveform);proposal,phase,murmur=self.proposal(x)
        return add_positive_evidence(self.baseline(x).softmax(1),proposal),phase,murmur


def main():
    if OUTPUT.exists():raise ValueError('M exists; refusing overwrite')
    for name in ['murmur-freeze.json','murmur-phase-k-freeze.json']:
        for path,expected in json.loads((ROOT/name).read_text())['sha256'].items():assert digest(ROOT.parent.parent/path)==expected
    assert json.loads((ROOT/'generated/murmur-phase-k/protocol.json').read_text())['temperature']==.7
    OUTPUT.mkdir(parents=True);torch.manual_seed(9414);torch.set_num_threads(1)
    c=torch.load(ROOT/'generated/murmur-phase-c/Murmur.pt',weights_only=True);j=torch.load(ROOT/'generated/murmur-phase-j/Murmur.pt',weights_only=True)
    frozen=[k for k in c if not k.startswith(('head.','phase_head.','timing_head.'))];assert all(torch.equal(c[k],j[k]) for k in frozen)
    model=AdditiveModel();model.baseline.load_state_dict(torch.load(ROOT/'generated/murmur-v1/Murmur.pt',weights_only=True));model.proposal.sound.load_state_dict(c)
    reference_j=TimingMurmurNet();reference_j.load_state_dict(j);reference_j.eval()
    for dst,src in zip(model.proposal.extra_heads,[reference_j.head,reference_j.phase_head,reference_j.timing_head]):dst.load_state_dict(src.state_dict())
    model.eval();reference_c=TimingMurmurNet();reference_c.load_state_dict(c);reference_c.eval()
    save(OUTPUT/'protocol.json',dict(method='Phaseproposal=singlefixed50/50probabilitymean C andK. C/Kshareidenticalfrozen acousticfeatures, computedonce. AddproposalPositive tooriginalv1 via max; distribute remainingmass inoriginalAbsent/Unknown ratio.',
        invariants='Perwindowandrecord:Present>=v1,Absent<=v1,Unknown<=v1; normalizednonnegative. ExistingconfidentPresent retained; no new confidentAbsent. Knownv1 falsealarmscanremain. NewFP/Unsure muststaywithinpresetlimits.',
        choice='Exploratoryarchitecture chosenusingdevelopment only. Cachedmeanapproximation selection25TP1FP60Unsure vs19,1,60;calibration24TP4FP58Unsure vs23,3,57. Perwindowfusionisnonlinear,so actualnativeevaluationrequired. No newfusionweights/thresholdssearched.',
        regression_gate='Beforeold120groupregression: candidatefixedfromdevelopment. RequireoldtestTP>v1,FPincrease<=2pp,Unsureincrease<=5pp,noincreasepositive-asAbsent. ReportpatientresultsandUnknownerrors. Oldtestispreviouslyinspectedregression,notindependentvalidation.',
        source_sha256=digest(Path(__file__)),shared_frozen_tensors_verified=len(frozen),phase_source='C explicit4phasesandweaktiming; Jclassificationheadhardnegativefinetune; Kdecisiontemperature.7selectedonselectiononly.'))
    examples=[torch.randn(1,1,SAMPLES)*scale for scale in [0,.0001,.01,.3]]
    records=[r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role']=='selection']
    for label in [0,1,2]:
        r=sorted([r for r in records if r['target']==label],key=lambda r:r['record'])[0]
        examples.append(torch.from_numpy(np.fromfile(CACHE/'audio'/(r['record']+'.f32'),dtype='<f4')[:SAMPLES].copy())[None,None])
    shared_errors=[]
    for x in examples:
        with torch.inference_mode():
            features=model.front(x);a,phase,murmur=reference_c.joint(features);b=reference_j(features)
            expected=add_positive_evidence(model.baseline(features).softmax(1),.5*(a.softmax(1)+(b/.7).softmax(1)))
            actual=model(x)[0];shared_errors.append(float((expected-actual).abs().max()))
    assert max(shared_errors)<1e-6,shared_errors
    torch.save(model.state_dict(),OUTPUT/'Murmur.pt')
    import coremltools as ct
    names=['probabilities','phase_probabilities','murmur_timing']
    converted=ct.convert(torch.jit.trace(model,examples[2]),inputs=[ct.TensorType(name='waveform',shape=(1,1,SAMPLES))],outputs=[ct.TensorType(name=n) for n in names],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
    converted.author='Chest BPM public-data research';converted.short_description='Adds phase-aware murmur evidence to the preserved baseline; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',labels='Absent,Present,Unknown',phase_labels='noise,S1,systole,S2,diastole',dataset='https://doi.org/10.13026/tshs-mw03',weights_sha256=digest(OUTPUT/'Murmur.pt'))
    converted.save(str(OUTPUT/'Murmur.mlpackage'));errors=[]
    for x in examples:
        with torch.inference_mode():expected=model(x)
        actual=converted.predict({'waveform':x.numpy()});errors.append([float(np.max(np.abs(v.numpy()-actual[n]))) for v,n in zip(expected,names)])
    assert np.max(errors)<.001,errors
    save(OUTPUT/'conversion.json',dict(maximum_probability_differences=np.max(errors,0).tolist(),examples=len(examples),shared_vs_independent_maximum_difference=max(shared_errors),real_selection_examples=3));print('Native M conversion/shared-path checks passed',np.max(errors,0),flush=True)


if __name__=='__main__':main()
