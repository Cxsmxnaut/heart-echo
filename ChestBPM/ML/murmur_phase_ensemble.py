"""One fixed probability ensemble after candidate A's calibration tradeoff failed."""
import json
from pathlib import Path

import coremltools as ct
import numpy as np
import torch
from torch import nn

from murmur_model import ROOT, Frontend, MurmurNet, SAMPLES
from murmur_phase_model import PhaseMurmurNet
from murmur_data import digest, save

OUTPUT = ROOT / 'generated/murmur-phase-b'


class PhaseEnsemble(nn.Module):
    def __init__(self):
        super().__init__(); self.front = Frontend(); self.baseline = MurmurNet(); self.phased = PhaseMurmurNet()

    def forward(self, waveform):
        x = self.front(waveform); logits, phase = self.phased.outputs(x)
        p = .5 * (torch.softmax(self.baseline(x), dim=1) + torch.softmax(logits, dim=1))
        return p, torch.softmax(phase, dim=1)


def main():
    if (OUTPUT / 'Murmur.mlpackage').exists(): raise ValueError('Ensemble exists; refusing overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True); torch.set_num_threads(1); torch.manual_seed(2414)
    baseline = ROOT / 'generated/murmur-v1/Murmur.pt'; phased = ROOT / 'generated/murmur-phase-a/Murmur.pt'
    original_freeze = json.loads((ROOT / 'murmur-freeze.json').read_text()); phase_freeze = json.loads((ROOT / 'murmur-phase-a-freeze.json').read_text())
    for data in [original_freeze, phase_freeze]:
        for path, expected in data['sha256'].items(): assert digest(ROOT.parent.parent / path) == expected
    model = PhaseEnsemble(); model.baseline.load_state_dict(torch.load(baseline, weights_only=True)); model.phased.load_state_dict(torch.load(phased, weights_only=True)); model.eval()
    torch.save(model.state_dict(), OUTPUT / 'Murmur.pt')
    save(OUTPUT / 'protocol.json', dict(method='Singlefixed50/50probabilitymean of frozenv1 andphasecandidateA; shared identicalwaveformfrontend; phaseoutputfromcandidateA.',
        baseline_sha256=digest(baseline), phase_a_sha256=digest(phased), source_sha256=digest(Path(__file__)),
        selection='CandidateA calibration had extra falsealarms. Onefixed50/50ensemble investigated; no other mixtureweightssearched. Calibrationisdevelopment/modelselectionevidence,notindependentvalidation. No oldtestregression inspected for candidatechoice.'))
    converted = ct.convert(torch.jit.trace(model, torch.randn(1, 1, SAMPLES) * .03),
        inputs=[ct.TensorType(name='waveform', shape=(1, 1, SAMPLES))],
        outputs=[ct.TensorType(name='probabilities'), ct.TensorType(name='phase_probabilities')],
        minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM; public CirCor phase-supervised research'
    converted.short_description = 'Fixed baseline/phase-aware murmur ensemble; no diagnostic output.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1', labels='Absent,Present,Unknown',
        phase_labels='noise,S1,systole,S2,diastole', dataset='https://doi.org/10.13026/tshs-mw03', weights_sha256=digest(OUTPUT / 'Murmur.pt'))
    converted.save(str(OUTPUT / 'Murmur.mlpackage')); errors = []
    for scale in [0, .0001, .01, .3]:
        x = torch.randn(1, 1, SAMPLES) * scale
        with torch.inference_mode(): expected = model(x)
        actual = converted.predict({'waveform': x.numpy()})
        errors.append([float(np.max(np.abs(e.numpy() - actual[n]))) for e, n in zip(expected, ['probabilities', 'phase_probabilities'])])
    assert np.max(errors) < .001, errors
    save(OUTPUT / 'conversion.json', dict(maximum_probability_differences=np.max(errors, axis=0).tolist(), examples=len(errors)))
    print('Fixed phase ensemble native conversion passed:', np.max(errors, axis=0), flush=True)


if __name__ == '__main__': main()
