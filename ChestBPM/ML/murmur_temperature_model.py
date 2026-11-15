"""Candidate K: selection-only decision-temperature calibration of J."""
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from murmur_model import ROOT,Frontend,FRAMES,SAMPLES,windows,decision,metrics
from murmur_timing_model import TimingMurmurNet
from murmur_native_data import CACHE
from murmur_phase_data import PHASE_MANIFEST
from murmur_data import digest,save

OUTPUT=ROOT/'generated/murmur-phase-k'


class TemperatureModel(nn.Module):
    def __init__(self,temperature):
        super().__init__();self.front=Frontend();self.classifier=TimingMurmurNet();self.temperature=temperature

    def forward(self,waveform):
        logits,phase,murmur=self.classifier.joint(self.front(waveform))
        return (logits/self.temperature).softmax(1),phase.softmax(1),murmur.sigmoid()


def main():
    if OUTPUT.exists():raise ValueError('K exists; refusing overwrite')
    for name in ['murmur-freeze.json','murmur-phase-j-freeze.json']:
        for path,expected in json.loads((ROOT/name).read_text())['sha256'].items():assert digest(ROOT.parent.parent/path)==expected
    OUTPUT.mkdir(parents=True);torch.set_num_threads(4);torch.manual_seed(8414)
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model=TimingMurmurNet();model.load_state_dict(torch.load(ROOT/'generated/murmur-phase-j/Murmur.pt',weights_only=True));model.to(device).eval()
    cache=json.loads((CACHE/'manifest.json').read_text());assert cache['phase_manifest_sha256']==digest(PHASE_MANIFEST)
    selection={r['record']:r for r in json.loads(PHASE_MANIFEST.read_text())['records'] if r['role']=='selection'}
    records=[]
    for item in cache['records']:
        if item['record'] not in selection:continue
        r=dict(selection[item['record']],sample_count=item['samples'],usable_frame_starts=item['usable_frame_starts']);path=CACHE/'features'/(r['record']+'.npy')
        assert digest(path)==item['features_sha256'];records.append((r,np.load(path),None))
    assert len(records)==len(selection);cached=[]
    for r,x,_ in records:
        usable=set(r['usable_frame_starts']);starts=[s//40 for s in windows(r['sample_count']) if s//40 in usable]
        with torch.inference_mode():logits=model(torch.from_numpy(np.stack([x[:,s:s+FRAMES] for s in starts])).to(device)).cpu().numpy() if starts else None
        cached.append(dict(record=r['record'],target=r['target'],logits=logits.tolist() if logits is not None else []))
    save(OUTPUT/'selection-window-logits.json',cached)
    baseline=json.loads((ROOT/'results/murmur-phase-c/selection-summary.json').read_text())['baseline'];grid=[];best=None
    for temperature in [.5,.6,.7,.8,.9,1,1.1,1.2]:
        probabilities=[]
        for item in cached:
            a=np.asarray(item['logits'],dtype=np.float64)/temperature
            if a.size:a=np.exp(a-a.max(1,keepdims=True));p=(a/a.sum(1,keepdims=True)).mean(0)
            else:p=np.array([0.,0.,1.])
            probabilities.append(p)
        m=metrics([r['target'] for r in cached],[decision(p) for p in probabilities])
        eligible=m['false_alarms']<=baseline['false_alarms'] and m['unsure']/m['total']<=baseline['unsure']/baseline['total']+.05 and m['missed_positive_as_absent']/m['known_positive_cases']<=baseline['missed_positive_as_absent']/baseline['known_positive_cases']+.02 and m['decisive_sensitivity']>baseline['decisive_sensitivity']
        grid.append(dict(temperature=temperature,metrics=m,eligible=eligible));score=(m['decisive_sensitivity'],-m['false_alarms'],-m['unsure'],-abs(temperature-1))
        if eligible and (best is None or score>best[0]):best=(score,temperature)
    assert best is not None;temperature=best[1]
    save(OUTPUT/'protocol.json',dict(temperature=temperature,grid=grid,
        choice='Only fixed50selectiongroups choose decision temperature among[.5,.6,.7,.8,.9,1,1.1,1.2]. Matchoriginalv1FPcount1,Unsure<=v1+5pp,positive-asAbsent<=v1+2pp,strictTPgain;maxTPthenfewerFP,Unsure,closestT1. Cachedperwindowlogits from exactnativeaudio/gates, temperaturebeforeaveraging.',
        note='Exploratory decisioncontrol, not calibrated disease probability. J training/weights unchanged. No K calibration/testresults accessed for T choice. Calibration cohort reuseddevelopment,not independentvalidation.',
        source_sha256=digest(Path(__file__)),native_manifest_sha256=digest(CACHE/'manifest.json')))
    print('Selected K temperature:',temperature,grid,flush=True)
    import coremltools as ct
    torch.set_num_threads(1);wrapper=TemperatureModel(temperature);wrapper.classifier.load_state_dict(torch.load(ROOT/'generated/murmur-phase-j/Murmur.pt',weights_only=True));wrapper.eval()
    torch.save(wrapper.state_dict(),OUTPUT/'Murmur.pt');names=['probabilities','phase_probabilities','murmur_timing']
    converted=ct.convert(torch.jit.trace(wrapper,torch.randn(1,1,SAMPLES)*.03),inputs=[ct.TensorType(name='waveform',shape=(1,1,SAMPLES))],outputs=[ct.TensorType(name=n) for n in names],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
    converted.author='Chest BPM public-data research';converted.short_description='Phase-aware murmur model with hard-negative heads and decision calibration; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',labels='Absent,Present,Unknown',phase_labels='noise,S1,systole,S2,diastole',dataset='https://doi.org/10.13026/tshs-mw03',weights_sha256=digest(OUTPUT/'Murmur.pt'),decision_temperature=str(temperature))
    converted.save(str(OUTPUT/'Murmur.mlpackage'));errors=[]
    for scale in [0,.0001,.01,.3]:
        x=torch.randn(1,1,SAMPLES)*scale
        with torch.inference_mode():expected=wrapper(x)
        actual=converted.predict({'waveform':x.numpy()});errors.append([float(np.max(np.abs(v.numpy()-actual[n]))) for v,n in zip(expected,names)])
    assert np.max(errors)<.001,errors
    save(OUTPUT/'conversion.json',dict(maximum_probability_differences=np.max(errors,0).tolist(),examples=4));print('Native K conversion passed',errors,flush=True)


if __name__=='__main__':main()
