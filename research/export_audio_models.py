"""Export selected research candidates; preserve shipping app models."""
import argparse,json
import numpy as np
import torch
import coremltools as ct
from train_audio_models import ROOT,ML,AudioClassifier,ExportAudio,digest,save

def export(task):
    out=ROOT/'generated'/('audio-v2-'+task);complete=json.loads((out/'complete.json').read_text());assert complete['model_sha256']==digest(out/'best.pt')
    model=AudioClassifier(4 if task=='valves' else 3,task=='valves');model.load_state_dict(torch.load(out/'best.pt',map_location='cpu',weights_only=True));model.eval();torch.set_num_threads(2)
    if task=='valves':
        # Each bag contains one four-second crop at each of eight acquisition positions.
        # The research evaluator averages three crops per position across 20 seconds.
        from murmur_model import Frontend
        from torch import nn
        class BagWave(nn.Module):
            def __init__(self):super().__init__();self.front=Frontend();self.classifier=model
            def forward(self,waveforms):
                f=self.front(waveforms.reshape(8,1,8000));return self.classifier(f.reshape(1,8,32,-1)).sigmoid()
        wrapped=BagWave().eval();example=torch.randn(1,8,1,8000)*.03;name='ValveResearch';input_name='waveforms';labels='AS,AR,MR,MS';schema='heartecho-valves-eight-recording-bag-v1'
    else:wrapped=ExportAudio(model).eval();example=torch.randn(1,1,8000)*.03;name='Murmur' if task=='murmur' else 'NormalAbnormal';input_name='waveform';labels='Absent,Present,Unknown' if task=='murmur' else 'Normal,Abnormal,Unknown';schema='chestbpm-murmur-wave-2k-v1' if task=='murmur' else 'heartecho-normal-abnormal-wave-2k-v1'
    destination=out/'native';destination.mkdir(exist_ok=True)
    converted=ct.convert(torch.jit.trace(wrapped,example),inputs=[ct.TensorType(name=input_name,shape=tuple(example.shape))],outputs=[ct.TensorType(name='probabilities')],minimum_deployment_target=ct.target.iOS17,compute_precision=ct.precision.FLOAT32)
    converted.author='Heart Echo public-data research';converted.short_description='Experimental sound classification; not a disease diagnosis or validated phone screening.'
    converted.user_defined_metadata.update(feature_schema=schema,labels=labels,weights_sha256=digest(out/'best.pt'),training_source_sha256=complete.get('source_sha256',digest(ROOT/'train_audio_models.py')))
    converted.save(str(destination/(name+'.mlpackage')))
    errors=[]
    for amplitude in [0.,.0001,.03,.3]:
        x=torch.randn_like(example)*amplitude
        with torch.inference_mode():expected=wrapped(x).numpy()
        actual=converted.predict({input_name:x.numpy()})['probabilities'];errors.append(float(np.max(np.abs(expected-actual))))
    assert max(errors)<.001,errors
    report={'candidate':task,'package':name+'.mlpackage','weights_sha256':digest(out/'best.pt'),'pytorch_coreml_maximum_absolute_difference':max(errors),'synthetic_conversion_cases':len(errors),'shipping_models_changed':False,'note':'Conversion parity only; not clinical or phone validation. BMD-HS candidates remain local research artifacts; no distribution authorization is claimed.'};save(out/'native-conversion.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('task',choices=['murmur','abnormal','valves']);export(parser.parse_args().task)
