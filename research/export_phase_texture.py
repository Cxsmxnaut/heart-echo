"""Export V4 and verify native development behavior before any promotion."""
import json
import numpy as np
import torch
from torch import nn
import coremltools as ct
from train_audio_models import ROOT,ML,digest,save
from train_phase_texture import TexturePhaseNet
from murmur_model import Frontend,metrics
from native_murmur_gate import native

class WaveTexture(nn.Module):
    def __init__(self,classifier):super().__init__();self.front=Frontend();self.classifier=classifier
    def forward(self,waveform):
        logits,phase,timing=self.classifier.joint(self.front(waveform));return logits.softmax(1),phase.softmax(1),timing.sigmoid()

def main():
    out=ROOT/'generated/murmur-v4-texture';complete=json.loads((out/'complete.json').read_text())
    assert complete['eligible_checkpoint'],'No eligible model may proceed to promotion'
    assert digest(out/'best.pt')==complete['weights_sha256']
    model=TexturePhaseNet();model.load_state_dict(torch.load(out/'best.pt',map_location='cpu',weights_only=True));wrapped=WaveTexture(model).eval();torch.set_num_threads(2);torch.manual_seed(20261120)
    example=torch.randn(1,1,8000)*.03;names=['probabilities','phase_probabilities','murmur_timing']
    converted=ct.convert(torch.jit.trace(wrapped,example),inputs=[ct.TensorType(name='waveform',shape=(1,1,8000))],outputs=[ct.TensorType(name=k) for k in names],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
    converted.author='Heart Echo public-data research';converted.short_description='Frequency/time texture with phase and weak murmur timing supervision; research only.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1',labels='Absent,Present,Unknown',phase_labels='noise,S1,systole,S2,diastole',model_revision='Texture phase V4 · 2026-11-15',weights_sha256=digest(out/'best.pt'),source_sha256=digest(ROOT/'train_phase_texture.py'),dataset='https://doi.org/10.13026/tshs-mw03')
    converted.save(str(out/'Murmur.mlpackage'));errors=[]
    for amplitude in [0,.0001,.03,.3]:
        x=torch.randn_like(example)*amplitude
        with torch.inference_mode():expected=wrapped(x)
        actual=converted.predict({'waveform':x.numpy()});errors.append([float(np.max(np.abs(v.numpy()-actual[n]))) for v,n in zip(expected,names)])
    assert np.max(errors)<.001,errors
    save(out/'native-conversion.json',{'maximum_absolute_differences':np.max(errors,0).tolist(),'cases':len(errors),'weights_sha256':digest(out/'best.pt')})
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role'] in ['selection','calibration']];requests=[{'id':r['record'],'path':str(ML/'cache/circor'/r['file'])} for r in rows];predictions=native(out,requests,'v4-texture')
    mapping={'present':1,'absent':0,'unsure':2};base=json.loads((ROOT/'results/native-v2-murmur-development.json').read_text());report={};passed=True;added=0
    for role in ['selection','calibration']:
        group=[r for r in rows if r['role']==role];m=metrics([r['target'] for r in group],[mapping[predictions[r['record']]['reading']['finding']] for r in group]);b=base[role]['shipping'];tp=m['known_positive_cases']-m['positive_unsure']-m['missed_positive_as_absent'];oldtp=b['known_positive_cases']-b['positive_unsure']-b['missed_positive_as_absent'];added+=tp-oldtp
        gates={'detected_not_lower':tp>=oldtp,'false_alarm_bound':m['false_alarms']/m['known_negative_cases']<=b['false_alarms']/b['known_negative_cases']+.02,'negative_misses_not_higher':m['missed_positive_as_absent']<=b['missed_positive_as_absent'],'unsure_bound':m['unsure']/m['total']<=b['unsure']/b['total']+.05};passed &= all(gates.values());report[role]={'shipping':b,'candidate':m,'gates':gates}
    report['development_gate_passed']=bool(passed and added>0);report['additional_positive_detections']=added;report['conversion']=json.loads((out/'native-conversion.json').read_text());report['note']='Reused development partitions; neither clinical nor phone validation. No regression data used in checkpoint selection.'
    save(ROOT/'results/murmur-v4-native-development.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
