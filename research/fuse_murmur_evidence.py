"""Fixed additional-positive-evidence candidate, using only development selection.
The shipping model is retained unless native development and regression gates pass.
"""
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
import coremltools as ct
from train_audio_models import ROOT,ML,AudioClassifier,digest,save
from murmur_additive_model import AdditiveModel,add_positive_evidence
from native_murmur_gate import native
from murmur_model import metrics

class EvidenceFusion(nn.Module):
    def __init__(self):
        super().__init__();self.original=AdditiveModel();self.original.load_state_dict(torch.load(ML/'generated/murmur-phase-m/Murmur.pt',map_location='cpu',weights_only=True));self.candidate=AudioClassifier();self.candidate.load_state_dict(torch.load(ROOT/'generated/audio-v2-murmur/best.pt',map_location='cpu',weights_only=True))
    def forward(self,waveform):
        x=self.original.front(waveform);proposal,phase,timing=self.original.proposal(x)
        original=add_positive_evidence(self.original.baseline(x).softmax(1),proposal)
        candidate=self.candidate(x).softmax(1)
        combined=add_positive_evidence(original,candidate)
        return torch.where((candidate[:,1:2]>=.6),combined,original)

def main():
    out=ROOT/'generated/murmur-v3-evidence';out.mkdir(parents=True,exist_ok=True)
    protocol={'source_sha256':digest(__file__),'original_weights_sha256':digest(ML/'generated/murmur-phase-m/Murmur.pt'),'additional_weights_sha256':digest(ROOT/'generated/audio-v2-murmur/best.pt'),'rule':'For each native window, retain shipping probabilities unless candidate Present >= .60. Then raise Present to max(shipping,candidate), rescaling Absent/Unknown in their original ratio. No new threshold search.','invariants':'Present never falls; Absent never rises. Candidate evidence must be independently decisive at the existing .60 threshold.','gate':'On each native development partition: TP >= shipping, false-alarm rate <= shipping+.02, positive-as-Absent <= shipping, unsure fraction <= shipping+.05; require at least one additional TP across partitions. Consumed regression must be scored separately before any promotion.'}
    if (out/'protocol.json').exists():raise ValueError('Evidence candidate exists; preserve existing artifacts')
    save(out/'protocol.json',protocol);torch.manual_seed(20261117);torch.set_num_threads(2);model=EvidenceFusion().eval();example=torch.randn(1,1,8000)*.03
    converted=ct.convert(torch.jit.trace(model,example),inputs=[ct.TensorType(name='waveform',shape=(1,1,8000))],outputs=[ct.TensorType(name='probabilities')],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
    converted.author='Heart Echo public-data research';converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',labels='Absent,Present,Unknown',method='Fixed decisive-positive evidence addition; not a diagnosis',source_sha256=digest(__file__))
    converted.save(str(out/'Murmur.mlpackage'));errors=[]
    for amplitude in [0,.0001,.03,.3]:
        x=torch.randn_like(example)*amplitude
        with torch.inference_mode():expected=model(x).numpy();original=model.original(x)[0].numpy()
        actual=converted.predict({'waveform':x.numpy()})['probabilities'];errors.append(float(np.max(np.abs(actual-expected))));assert np.all(actual[:,1]>=original[:,1]-1e-5) and np.all(actual[:,0]<=original[:,0]+1e-5)
    assert max(errors)<.001
    save(out/'conversion.json',{'pytorch_coreml_max_difference':max(errors),'random_invariant_cases':4})
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role'] in ['selection','calibration']];requests=[{'id':r['record'],'path':str(ML/'cache/circor'/r['file'])} for r in rows]
    predictions=native(out,requests,'v3-evidence');mapping={'present':1,'absent':0,'unsure':2};original=json.loads((ROOT/'results/native-v2-murmur-development.json').read_text());report={};passed=True;added=0
    for role in ['selection','calibration']:
        group=[r for r in rows if r['role']==role];m=metrics([r['target'] for r in group],[mapping[predictions[r['record']]['reading']['finding']] for r in group]);base=original[role]['shipping'];tp=m['known_positive_cases']-m['missed_positive_as_absent']-m['positive_unsure'];oldtp=base['known_positive_cases']-base['missed_positive_as_absent']-base['positive_unsure'];added+=tp-oldtp
        gates={'detected_not_lower':tp>=oldtp,'false_alarm_bound':m['false_alarms']/m['known_negative_cases']<=base['false_alarms']/base['known_negative_cases']+.02,'negative_misses_not_higher':m['missed_positive_as_absent']<=base['missed_positive_as_absent'],'unsure_bound':m['unsure']/m['total']<=base['unsure']/base['total']+.05};passed &= all(gates.values());report[role]={'shipping':base,'candidate':m,'gates':gates}
    report['additional_positive_detections']=added;report['development_gate_passed']=bool(passed and added>0);report['protocol']=protocol
    save(ROOT/'results/murmur-v3-evidence-development.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
