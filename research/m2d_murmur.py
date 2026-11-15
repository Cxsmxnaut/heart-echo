"""Research wrapper around the authors' unchanged, pinned M2D portable runtime.

Reference: Niizumi et al., IEEE EMBC 2024, arxiv.org/abs/2404.17107.
Upstream is under NTT's non-commercial internal-evaluation license, not MIT.
The upstream source and pretrained weights stay in ignored research caches.
"""
import hashlib
import importlib.util
from pathlib import Path
import time
import urllib.request
import zipfile

import torch
from torch import nn

HERE = Path(__file__).resolve().parent
REVISION = '3d0c4de9447c404a8d3f9f37e04f53bc902e09b3'
RUNTIME_SHA = 'b64d94a18b558c0643b1bba578f215629e3dd00656284a8cbf992fbc2f563ee2'
ARCHIVE_SHA = 'c7573e6f32c00ec6646e70ec2a15b92aea7ab0d58cd43b9c3a5a70cbecd0948c'
PRETRAINED_SHA = 'b1505cd866d3c334923b9b8fd51224ccaf81821c4529246e1bfb0e865b338be2'
WEIGHT_FOLDER = 'm2d_vit_base-80x608p16x16-220930-mr7_enconly'
RATE, SAMPLES, STRIDE = 16000, 80000, 40000


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download(url, path, expected):
    path = Path(path)
    if path.exists():
        if sha(path) != expected:
            raise ValueError('Existing public file checksum mismatch: ' + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.download')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as target:
                while block := source.read(1024 * 1024):
                    target.write(block)
            if sha(temporary) != expected:
                raise ValueError('Downloaded public file checksum mismatch: ' + path.name)
            temporary.replace(path)
            return
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def setup(cache):
    """Retrieve only pinned public artifacts; never inspect private recordings."""
    cache = Path(cache)
    runtime = cache / 'portable_m2d.py'
    download(f'https://raw.githubusercontent.com/nttcslab/m2d/{REVISION}/examples/portable_m2d.py',
             runtime, RUNTIME_SHA)
    weights = cache / WEIGHT_FOLDER / 'checkpoint-300.pth'
    if not weights.exists():
        archive = cache / 'official-v0.1.0.zip'
        download('https://github.com/nttcslab/m2d/releases/download/v0.1.0/' + WEIGHT_FOLDER + '.zip',
                 archive, ARCHIVE_SHA)
        member = WEIGHT_FOLDER + '/checkpoint-300.pth'
        with zipfile.ZipFile(archive) as source:
            if source.testzip() is not None:
                raise ValueError('Corrupted pretrained archive')
            weights.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as data, weights.open('wb') as target:
                while block := data.read(1024 * 1024):
                    target.write(block)
    if sha(weights) != PRETRAINED_SHA:
        raise ValueError('Unexpected M2D checkpoint')
    return runtime, weights


def runtime_module(path):
    if sha(path) != RUNTIME_SHA:
        raise ValueError('Unexpected upstream M2D source')
    spec = importlib.util.spec_from_file_location('heart_echo_pinned_m2d_runtime', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class M2DMurmur(nn.Module):
    """85M-parameter M2D encoder + EVAR-style normalization/linear head.

    Input is the authors' unnormalized log-mel spectrum, B x 1 x 80 x 501.
    Patch embedding and fixed positional embeddings remain frozen. All twelve
    transformer blocks learn; this is not a frozen-feature probe.
    """
    def __init__(self, cache):
        super().__init__()
        runtime_path, weight_path = setup(cache)
        upstream = runtime_module(runtime_path)
        self.runtime = upstream.PortableM2D(str(weight_path), cfg=upstream.Config(), freeze_embed=True)
        self.runtime.backbone.pos_embed.requires_grad_(False)
        self.norm = nn.BatchNorm1d(3840, affine=False)
        self.classifier = nn.Linear(3840, 3)
        nn.init.normal_(self.classifier.weight, std=.01)
        nn.init.zeros_(self.classifier.bias)

    def features(self, wave):
        with torch.no_grad():
            return self.runtime.to_log_mel_spec(wave)

    def forward(self, log_mel):
        x = self.runtime.normalize_batch(log_mel)
        x = self.runtime.encode_lms(x).mean(1)
        return self.classifier(self.norm(x))


def decide(probabilities, threshold=.60):
    best = int(probabilities.argmax())
    return ['absent', 'present', 'unsure'][best if probabilities[best] >= threshold else 2]


def offsets(count, training=False):
    """Published five-second windows, overlapping only during training."""
    if count < SAMPLES:
        return [0]
    return list(range(0, count - SAMPLES + 1, STRIDE if training else SAMPLES))
