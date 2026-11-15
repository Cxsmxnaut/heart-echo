"""V7: one frequency-axis adaptation of the fixed V6 encoder experiment.

Expand the 17 existing bands centered <=1kHz to the same 64-band encoder grid.
Keep the original FFT/time resolution, encoder weights and classifier unchanged.
"""
import json,time
import numpy as np
import torch
from torch.nn import functional as F
from panns_murmur_features import ROOT,ML,CACHE,WEIGHTS,WEIGHT_SHA,sha,save,FrozenFrontend,Cnn6Encoder,windows,HOP

OUT=ROOT/'generated/murmur-v7-heartband-probe'

def expand_heart_band(spectrum):
    # Same time grid. This resizes existing information; it adds no bandwidth.
    return F.interpolate(spectrum[:,:,:,:17],size=(spectrum.shape[2],64),mode='bilinear',align_corners=False)

class HeartBandFrontend(FrozenFrontend):
    def forward(self,x):return expand_heart_band(super().forward(x))

def main():
    assert sha(WEIGHTS)==WEIGHT_SHA
    assert not OUT.exists(),'Preserve prior/running experiments'
    v6=ROOT/'generated/murmur-v6-pretrained-probe'
    prior=json.loads((v6/'protocol.json').read_text())
    assert sha(ROOT/'panns_murmur_features.py')==prior['source_sha256']
    OUT.mkdir(parents=True)
    protocol={**prior,'hypothesis':'Does expanding the available heart-frequency bands across the fixed encoder grid improve V6?','controlled_factor':'Only frontend frequency-axis packing differs from V6. Retain the17 existing mel bands centered at or below1kHz; resize to64 bands. FFT, time grid, input audio, encoder weights/seed, classifier, scaling, weights, C, threshold and evaluation unchanged. Both pretrained and random arms retained. No extra information is created.','source_sha256':sha(__file__),'classifier_source_sha256':sha(ROOT/'fit_panns_heartband_probe.py'),'v6_feature_source_sha256':sha(ROOT/'panns_murmur_features.py'),'v6_classifier_source_sha256':sha(ROOT/'fit_panns_murmur_probe.py'),'prior_protocol_sha256':sha(v6/'protocol.json'),'retained_bands':17,'source_band_cutoff_hz':1000.,'note':'Reused development; fixed frequency adaptation only. Not independent or phone validation. Do not infer that pretrained weights are adapted to clinical use.'}
    save(OUT/'protocol.json',protocol)
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role']!='test']
    provenance={r['record']:r for r in json.loads((CACHE/'manifest.json').read_text())['records']}
    torch.set_num_threads(2);torch.manual_seed(protocol['seed'])
    state=torch.load(WEIGHTS,map_location='cpu',weights_only=True)['model']
    mel=state['logmel_extractor.melW'].numpy();frequencies=np.linspace(0,16000,513)
    centers=(mel*frequencies[:,None]).sum(0)/mel.sum(0)
    assert np.flatnonzero(centers<=1000).tolist()==list(range(17))
    encoder_state={k:v for k,v in state.items() if not k.startswith(('spectrogram_extractor.','logmel_extractor.'))}
    pretrained=Cnn6Encoder();pretrained.load_state_dict(encoder_state,strict=True)
    torch.manual_seed(protocol['seed']);random=Cnn6Encoder()
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    front=HeartBandFrontend(state).eval().to(device)
    models={'pretrained':pretrained.eval().to(device),'random':random.eval().to(device)}
    features={name:[] for name in models};indices=[];offset=0;began=time.monotonic()
    with torch.inference_mode():
        for number,r in enumerate(rows,1):
            info=provenance[r['record']];raw=CACHE/'audio'/(r['record']+'.f32')
            assert sha(raw)==info['native_audio_sha256'] and info['source_sha256']==r['sha256']
            audio=np.fromfile(raw,dtype='<f4');usable=set(info['usable_frame_starts'])
            starts=[s for s in windows(len(audio)) if s//HOP in usable]
            indices.append({'record':r['record'],'offset':offset,'windows':len(starts)});offset+=len(starts)
            for first in range(0,len(starts),8):
                batch=torch.from_numpy(np.stack([audio[s:s+8000] for s in starts[first:first+8]]))[:,None].to(device)
                spectrum=front(batch)
                for name,model in models.items():features[name].append(model(spectrum).cpu().numpy())
            if number%100==0:print(json.dumps({'records':number,'total':len(rows),'windows':offset,'seconds':time.monotonic()-began}),flush=True)
    assert indices==json.loads((v6/'records.json').read_text()),'All V6/V7 input windows must match'
    for name,parts in features.items():
        values=np.concatenate(parts);assert values.shape==(offset,512) and np.isfinite(values).all()
        np.save(OUT/(name+'-features.npy'),values)
    save(OUT/'records.json',indices)
    save(OUT/'features-complete.json',{'records':len(rows),'windows':offset,'seconds':time.monotonic()-began,'source_sha256':sha(__file__),'files_sha256':{name:sha(OUT/name) for name in ['pretrained-features.npy','random-features.npy','records.json','protocol.json']}})
    print('FEATURES COMPLETE',flush=True)

if __name__=='__main__':main()
