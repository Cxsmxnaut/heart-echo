"""Controlled frozen-encoder experiment: AudioSet-pretrained versus random CNN6.

CNN6 architecture adapted from Qiuqiang Kong's MIT-licensed PANNs implementation.
See third_party/PANNs-LICENSE.MIT. Pretrained weights: CC BY 4.0, Zenodo3987831.
Only non-test public CirCor audio enters this experiment.
"""
import json,sys,time,hashlib
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parent;ML=ROOT.parent/'ChestBPM/ML'
sys.path.insert(0,str(ML))
from murmur_model import windows,HOP
from murmur_native_data import CACHE

OUT=ROOT/'generated/murmur-v6-pretrained-probe'
WEIGHTS=ROOT/'cache/panns-review/Cnn6_mAP=0.343.pth'
WEIGHT_SHA='8a17541944f2623a2a0164e072ac2f915dcedca99968083cc44bfbc7eb682275'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

class FrozenFrontend(nn.Module):
    def __init__(self,state):
        super().__init__()
        self.register_buffer('real',state['spectrogram_extractor.stft.conv_real.weight'])
        self.register_buffer('imag',state['spectrogram_extractor.stft.conv_imag.weight'])
        self.register_buffer('mel',state['logmel_extractor.melW'])
    def forward(self,x):
        # Upsampling preserves the app's information bandwidth; it creates no new signal.
        x=F.interpolate(x,size=128000,mode='linear',align_corners=False)
        x=F.pad(x,(512,512),mode='reflect')
        power=F.conv1d(x,self.real,stride=320).square()+F.conv1d(x,self.imag,stride=320).square()
        return (10*torch.log10((power.transpose(1,2)@self.mel).clamp_min(1e-10)))[:,None]

class ConvBlock(nn.Module):
    def __init__(self,source,target):
        super().__init__();self.conv1=nn.Conv2d(source,target,5,padding=2,bias=False);self.bn1=nn.BatchNorm2d(target)
    def forward(self,x):return F.avg_pool2d(F.relu(self.bn1(self.conv1(x))),(2,2))

class Cnn6Encoder(nn.Module):
    def __init__(self):
        super().__init__();self.bn0=nn.BatchNorm2d(64)
        self.conv_block1=ConvBlock(1,64);self.conv_block2=ConvBlock(64,128)
        self.conv_block3=ConvBlock(128,256);self.conv_block4=ConvBlock(256,512)
        self.fc1=nn.Linear(512,512);self.fc_audioset=nn.Linear(512,527)
        for layer in self.modules():
            if isinstance(layer,(nn.Conv2d,nn.Linear)):
                nn.init.xavier_uniform_(layer.weight)
                if layer.bias is not None:nn.init.zeros_(layer.bias)
    def forward(self,x):
        x=self.bn0(x.transpose(1,3)).transpose(1,3)
        for block in [self.conv_block1,self.conv_block2,self.conv_block3,self.conv_block4]:x=block(x)
        x=x.mean(3);return F.relu(self.fc1(x.amax(2)+x.mean(2)))

def main():
    assert sha(WEIGHTS)==WEIGHT_SHA
    assert not OUT.exists(),'Preserve completed/running experiments; never silently overwrite'
    OUT.mkdir(parents=True)
    protocol={'hypothesis':'Does an encoder pretrained on general audio provide better fixed sound features than the same randomly initialized encoder?','controlled_factor':'Encoder weights: fixed AudioSet-pretrained CNN6 versus fixed seeded random CNN6. Same waveform frontend, usable windows, three-class linear classifier, fitting weights, regularization and decision rule. No encoder fine-tuning, architecture sweep or threshold search.','seed':20261122,'threshold':.60,'classifier':'Training-only weighted feature scaling, multinomial logistic regression C=1, max_iter=2000. Each recording has equal total fitting weight within its class; classes balanced. Average window probabilities exactly as the app reader.','selection':'One fixed fit per encoder; no checkpoint/hyperparameter selection. Apply existing strict recording and linked-person promotion checks on both reused development partitions. Freeze before any regression; stop if either development gate fails.','data':'Original training groups fit classifier/scaler. Selection/calibration reused development only. No regression, PASCAL or private audio loaded.','encoder_source':'https://github.com/qiuqiangkong/audioset_tagging_cnn/tree/d2f4b8c18eab44737fcc0de1248ae21eb43f6aa4','encoder_weights_source':'https://zenodo.org/records/3987831','encoder_weights_sha256':WEIGHT_SHA,'encoder_weights_license':'CC BY 4.0; Qiuqiang Kong et al., PANNs','source_sha256':sha(__file__),'classifier_source_sha256':sha(ROOT/'fit_panns_murmur_probe.py'),'cohort_manifest_sha256':sha(ML/'murmur-phase-manifest.json'),'metrics_source_sha256':sha(ROOT/'murmur_focus_metrics.py'),'acceptance_sha256':sha(ROOT/'murmur_focus_acceptance.json'),'note':'A lightweight frozen-feature feasibility experiment, not a reproduction of the M2D/CNN14 paper and not a clinical accuracy test.'}
    save(OUT/'protocol.json',protocol)
    rows=[r for r in json.loads((ML/'murmur-phase-manifest.json').read_text())['records'] if r['role']!='test']
    provenance={r['record']:r for r in json.loads((CACHE/'manifest.json').read_text())['records']}
    torch.set_num_threads(2);torch.manual_seed(protocol['seed'])
    state=torch.load(WEIGHTS,map_location='cpu',weights_only=True)['model']
    encoder_state={k:v for k,v in state.items() if not k.startswith(('spectrogram_extractor.','logmel_extractor.'))}
    pretrained=Cnn6Encoder();pretrained.load_state_dict(encoder_state,strict=True)
    torch.manual_seed(protocol['seed']);random=Cnn6Encoder()
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    front=FrozenFrontend(state).eval().to(device)
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
    for name,parts in features.items():
        values=np.concatenate(parts);assert values.shape==(offset,512) and np.isfinite(values).all()
        np.save(OUT/(name+'-features.npy'),values)
    save(OUT/'records.json',indices)
    save(OUT/'features-complete.json',{'records':len(rows),'windows':offset,'seconds':time.monotonic()-began,'source_sha256':sha(__file__),'files_sha256':{name:sha(OUT/name) for name in ['pretrained-features.npy','random-features.npy','records.json','protocol.json']}})
    print('FEATURES COMPLETE',flush=True)

if __name__=='__main__':main()
