"""One fixed equal-probability ensemble; no new training or threshold search."""
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
import coremltools as ct
from beat_model import BeatNet

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'generated/beat-ensemble'


class Ensemble(nn.Module):
    def __init__(self):
        super().__init__(); self.original = BeatNet(); self.adapted = BeatNet()

    def forward(self, x):
        probabilities = .5 * (torch.softmax(self.original(x), dim=1) + torch.softmax(self.adapted(x), dim=1))
        return torch.log(probabilities.clamp_min(1e-9))


def main():
    if (OUTPUT / 'BeatStates.mlpackage').exists(): raise ValueError('Ensemble exists; refusing overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True); torch.set_num_threads(1); torch.manual_seed(1814)
    original = ROOT / 'generated/BeatStates.pt'; adapted = ROOT / 'generated/beat-adapt/BeatStates.pt'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == json.loads((ROOT / 'results/beat-training.json').read_text())['model_sha256']
    model = Ensemble(); model.original.load_state_dict(torch.load(original, map_location='cpu', weights_only=True))
    model.adapted.load_state_dict(torch.load(adapted, map_location='cpu', weights_only=True)); model.eval()
    torch.save(model.state_dict(), OUTPUT / 'BeatStates.pt')
    (OUTPUT / 'protocol.json').write_text(json.dumps(dict(method='Equalmeanoforiginalandadaptedclassprobabilities;logmeanreturnedtoexistingnative5stateABI.',
        original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(), adapted_sha256=hashlib.sha256(adapted.read_bytes()).hexdigest(),
        selection='Singlefixed50/50combination;noalternativemixtureweightssearched;24heldoutpatientsremainunread.',
        diagnosis='Sound-state research only; no disease predictions.'), indent=2) + '\n')
    converted = ct.convert(torch.jit.trace(model, torch.randn(1, 8, 200)),
        inputs=[ct.TensorType(name='features', shape=(1, 8, 200))], outputs=[ct.TensorType(name='logits')],
        minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM; public sound-state research'
    converted.short_description = 'Experimental paired sound-state networks; no diagnostic output.'
    converted.user_defined_metadata['feature_schema'] = 'chestbpm-energy-v1'
    converted.user_defined_metadata['weights_sha256'] = hashlib.sha256((OUTPUT / 'BeatStates.pt').read_bytes()).hexdigest()
    converted.user_defined_metadata['dataset'] = 'https://doi.org/10.13026/tshs-mw03'
    converted.save(str(OUTPUT / 'BeatStates.mlpackage')); errors = []
    for _ in range(8):
        x = torch.randn(1, 8, 200)
        with torch.inference_mode(): expected = model(x).numpy()
        actual = converted.predict({'features': x.numpy()})['logits']; errors.append(float(np.max(np.abs(actual - expected))))
    assert max(errors) < .001, errors
    (OUTPUT / 'conversion.json').write_text(json.dumps(dict(maximum_logit_error=max(errors), examples=8), indent=2) + '\n')
    print('Fixedensembleconversionpassed:', max(errors))


if __name__ == '__main__': main()
