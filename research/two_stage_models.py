"""Standard CNN6/ResNet18 comparisons and a separate bounded phone adapter.

PANNs: Qiuqiang Kong et al., MIT code / CC BY 4.0 pretrained weights.
ResNet18 topology/weights: TorchVision, BSD-3-Clause; mono spectrogram adaptation.
See third_party licenses. These adaptations do not reproduce a published score.
"""
from pathlib import Path
import hashlib
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
NFFT, HOP, RATE = 256, 40, 2000
WEIGHTS = HERE / 'cache/panns-review/Cnn6_mAP=0.343.pth'
WEIGHT_SHA = '8a17541944f2623a2a0164e072ac2f915dcedca99968083cc44bfbc7eb682275'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def banks():
    window = np.hanning(NFFT + 1)[:-1]
    phase = 2 * np.pi * np.arange(129)[:, None] * np.arange(NFFT)[None] / NFFT
    fourier = np.concatenate([np.cos(phase), -np.sin(phase)]) * window
    return fourier.astype(np.float32), None, window


class ConvBlock(nn.Module):
    def __init__(self, a, b):
        super().__init__()
        self.conv1 = nn.Conv2d(a, b, 5, padding=2, bias=False)
        self.bn1 = nn.BatchNorm2d(b)

    def forward(self, x):
        return F.avg_pool2d(F.relu(self.bn1(self.conv1(x))), (2, 2))


class Cnn6Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.bn0 = nn.BatchNorm2d(64)
        self.conv_block1 = ConvBlock(1, 64); self.conv_block2 = ConvBlock(64, 128)
        self.conv_block3 = ConvBlock(128, 256); self.conv_block4 = ConvBlock(256, 512)
        self.fc1 = nn.Linear(512, 512)
        self.fc_audioset = nn.Identity()

BANDS = 64
FRAMES = 194


def mel_bank():
    hz_to_mel = lambda x: 2595 * np.log10(1 + x / 700)
    edges = 700 * (10 ** (np.linspace(hz_to_mel(25), hz_to_mel(950), BANDS + 2) / 2595) - 1)
    hz = np.arange(NFFT // 2 + 1) * RATE / NFFT
    return np.stack([np.maximum(0, np.minimum((hz - a) / (b - a), (c - hz) / (c - b)))
                     for a, b, c in zip(edges, edges[1:], edges[2:])]).astype(np.float32)


MEL = mel_bank()
WINDOW = banks()[2]


def spectra(waves):
    x = np.asarray(waves)
    if x.ndim == 1:
        x = x[None]
    frames = np.lib.stride_tricks.sliding_window_view(x, NFFT, axis=-1)[..., ::HOP, :]
    power = np.abs(np.fft.rfft(frames * WINDOW, axis=-1)) ** 2
    return np.log(np.maximum(np.einsum('mf,ntf->nmt', MEL, power, optimize=False), 1e-10)).astype(np.float32)


class Frontend64(nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer('fourier', torch.from_numpy(banks()[0][:, None]))
        self.register_buffer('mel', torch.from_numpy(MEL[:, :, None]))

    def forward(self, wave):
        parts = F.conv1d(wave, self.fourier, stride=HOP)
        power = parts[:, :129].square() + parts[:, 129:].square()
        return F.conv1d(power, self.mel).clamp_min(1e-10).log()


def normalize(x):
    centered = x - x.mean((1, 2), keepdim=True)
    return centered / (centered.square().mean((1, 2), keepdim=True) + 1).sqrt()


class Cnn6Murmur(nn.Module):
    def __init__(self, pretrained=False):
        super().__init__()
        self.encoder = Cnn6Encoder()
        self.encoder.fc_audioset = nn.Identity()
        self.classifier = nn.Linear(512, 3)
        if pretrained:
            assert sha(WEIGHTS) == WEIGHT_SHA
            state = torch.load(WEIGHTS, map_location='cpu', weights_only=True)['model']
            selected = {k: v for k, v in state.items() if not k.startswith(
                ('spectrogram_extractor.', 'logmel_extractor.', 'fc_audioset.'))}
            self.encoder.load_state_dict(selected, strict=True)
            for layer in self.encoder.modules():
                if isinstance(layer, nn.BatchNorm2d):
                    layer.reset_running_stats()

    def forward(self, x):
        e = self.encoder
        x = normalize(x).transpose(1, 2)[:, None]
        x = e.bn0(x.transpose(1, 3)).transpose(1, 3)
        for block in [e.conv_block1, e.conv_block2, e.conv_block3, e.conv_block4]:
            x = F.dropout(block(x), .2, self.training)
        x = x.mean(3)
        x = F.dropout(x.amax(2) + x.mean(2), .5, self.training)
        return self.classifier(F.dropout(F.relu(e.fc1(x)), .5, self.training))


def conv3(a, b, stride=1):
    return nn.Conv2d(a, b, 3, stride=stride, padding=1, bias=False)


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, a, b, stride=1):
        super().__init__()
        self.conv1 = conv3(a, b, stride); self.bn1 = nn.BatchNorm2d(b)
        self.conv2 = conv3(b, b); self.bn2 = nn.BatchNorm2d(b)
        self.downsample = (nn.Sequential(nn.Conv2d(a, b, 1, stride=stride, bias=False), nn.BatchNorm2d(b))
                           if stride != 1 or a != b else None)

    def forward(self, x):
        residual = x if self.downsample is None else self.downsample(x)
        x = F.relu(self.bn1(self.conv1(x)))
        return F.relu(self.bn2(self.conv2(x)) + residual)


class ResNet18Murmur(nn.Module):
    def __init__(self, pretrained=False):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 64, 7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
        self.layer1 = nn.Sequential(BasicBlock(64, 64), BasicBlock(64, 64))
        self.layer2 = nn.Sequential(BasicBlock(64, 128, 2), BasicBlock(128, 128))
        self.layer3 = nn.Sequential(BasicBlock(128, 256, 2), BasicBlock(256, 256))
        self.layer4 = nn.Sequential(BasicBlock(256, 512, 2), BasicBlock(512, 512))
        self.classifier = nn.Linear(512, 3)
        for layer in self.modules():
            if isinstance(layer, nn.Conv2d):
                nn.init.kaiming_normal_(layer.weight, mode='fan_out', nonlinearity='relu')
        if pretrained:
            path = HERE / 'cache/resnet-review/resnet18-f37072fd.pth'
            assert sha(path).startswith('f37072fd')
            state = torch.load(path, map_location='cpu', weights_only=True)
            state['conv1.weight'] = state['conv1.weight'].mean(1, keepdim=True)
            state = {k: v for k, v in state.items() if not k.startswith('fc.')}
            result = self.load_state_dict(state, strict=False)
            assert set(result.missing_keys) == {'classifier.weight', 'classifier.bias'}
            assert not result.unexpected_keys
            for layer in self.modules():
                if isinstance(layer, nn.BatchNorm2d):
                    layer.reset_running_stats()

    def forward(self, x):
        x = normalize(x)[:, None]
        x = self.maxpool(F.relu(self.bn1(self.conv1(x))))
        for block in [self.layer1, self.layer2, self.layer3, self.layer4]:
            x = block(x)
        return self.classifier(x.mean((2, 3)))


def make_clinical(name, pretrained=False):
    return {'panns-cnn6': Cnn6Murmur, 'resnet18': ResNet18Murmur}[name](pretrained=pretrained)


class PhoneAdapter(nn.Module):
    """Learn at most +/-6.5dB of spectral correction, constant across time.

    It can reweight existing frequencies; it cannot invent a new heartbeat cycle.
    """
    def __init__(self):
        super().__init__()
        self.mapping = nn.Sequential(nn.Linear(128, 32), nn.SiLU(), nn.Linear(32, BANDS))
        nn.init.zeros_(self.mapping[-1].weight); nn.init.zeros_(self.mapping[-1].bias)

    def correction(self, x):
        context = normalize(x)
        mean = context.mean(2)
        deviation = (context - mean[:, :, None]).square().mean(2).clamp_min(1e-8).sqrt()
        return 1.5 * self.mapping(torch.cat([mean, deviation], 1)).tanh()[:, :, None]

    def forward(self, x):
        return x + self.correction(x)


class AdaptedClinical(nn.Module):
    def __init__(self, clinical, adapter=None):
        super().__init__(); self.clinical = clinical; self.adapter = adapter or PhoneAdapter()
        for parameter in self.clinical.parameters():
            parameter.requires_grad_(False)
        self.clinical.eval()

    def train(self, mode=True):
        super().train(mode); self.clinical.eval()
        return self

    def forward(self, features):
        return self.clinical(self.adapter(features))


class WaveClassifier(nn.Module):
    def __init__(self, classifier):
        super().__init__(); self.front = Frontend64(); self.classifier = classifier

    def forward(self, waveform):
        return self.classifier(self.front(waveform)).softmax(1)
