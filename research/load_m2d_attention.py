"""Load/run a full trained M2D attention checkpoint for research inference."""
import argparse
import json
from pathlib import Path

import soundfile as sf
import torch

from m2d_attention import M2DAttentionMurmur
from m2d_murmur import M2DMurmur, HERE, sha
from evaluate_m2d_murmur import predict


def load_model(checkpoint, cache, device):
    manifest = json.loads((checkpoint.parent / 'manifest.json').read_text())
    assert manifest['pooling'] == 'learned_attention'
    assert sha(checkpoint) == manifest['weights_sha256']
    baseline = M2DMurmur(cache).eval()
    model = M2DAttentionMurmur(baseline)
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    model.load_state_dict(state, strict=True)
    assert all(torch.isfinite(v).all() for v in state.values())
    assert model.head.pooling == 'attention'
    assert torch.count_nonzero(model.head.pool.score.weight) > 0
    return model.to(device).eval()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--audio', type=Path, required=True)
    p.add_argument('--cache', type=Path, default=HERE / 'cache/m2d-weights')
    a = p.parse_args()
    torch.set_num_threads(2)
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    model = load_model(a.checkpoint, a.cache, device)
    audio, rate = sf.read(a.audio, dtype='float32')
    if audio.ndim != 1:
        raise ValueError('Expected mono audio')
    print(json.dumps(dict(research_only=True, result=predict(model, audio[:rate * 60], rate, device))), flush=True)
