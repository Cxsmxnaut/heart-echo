"""Selection-only conservative probability calibration of frozen phase candidate A."""
import json
from pathlib import Path
import coremltools as ct
import numpy as np
import torch
from torch import nn
from murmur_model import ROOT, Frontend, SAMPLES, metrics, decision
from murmur_phase_model import PhaseMurmurNet
from murmur_data import digest, save

OUTPUT = ROOT / 'generated/murmur-phase-d'


class ConservativePhaseModel(nn.Module):
    def __init__(self, alpha):
        super().__init__(); self.front = Frontend(); self.classifier = PhaseMurmurNet(); self.alpha = alpha
        self.register_buffer('unknown_prior', torch.tensor([[0., 0., 1.]]))

    def forward(self, waveform):
        logits, phase = self.classifier.outputs(self.front(waveform))
        return (1 - self.alpha) * logits.softmax(1) + self.alpha * self.unknown_prior, phase.softmax(1)


def main():
    if OUTPUT.exists(): raise ValueError('D exists; refusing overwrite')
    for name in ['murmur-freeze.json', 'murmur-phase-a-freeze.json']:
        for path, expected in json.loads((ROOT / name).read_text())['sha256'].items(): assert digest(ROOT.parent.parent / path) == expected
    rows = json.loads((ROOT / 'results/murmur-phase-a/selection-predictions.json').read_text())
    summary = json.loads((ROOT / 'results/murmur-phase-a/selection-summary.json').read_text()); baseline = summary['baseline']
    grid = []; best = None
    for alpha in [0, .025, .05, .075, .1, .125, .15, .2]:
        m = metrics([r['target'] for r in rows], [decision((1 - alpha) * np.array(r['probabilities']) + alpha * np.array([0, 0, 1])) for r in rows])
        eligible = m['false_alarms'] <= baseline['false_alarms'] and m['unsure'] / m['total'] <= baseline['unsure'] / baseline['total'] + .05 and m['missed_positive_as_absent'] <= baseline['missed_positive_as_absent']
        grid.append(dict(alpha=alpha, metrics=m, eligible=eligible))
        score = (m['decisive_sensitivity'], -m['false_alarms'], -m['unsure'])
        if eligible and (best is None or score > best[0]): best = (score, alpha)
    assert best is not None; alpha = best[1]; assert alpha == .025
    OUTPUT.mkdir(parents=True); torch.set_num_threads(1); torch.manual_seed(4414)
    save(OUTPUT / 'protocol.json', dict(alpha=alpha, grid=grid,
        method='p_out=(1-alpha)*p_A+alpha*[0,0,1]. Linear mapping commutes with native window averaging; all silence/clipping gates unchanged.',
        selection='Exploratory selection-only8point alpha grid. Match original native selection false-alarm COUNT, do not increase positive-asAbsent, unsure increase<=5pp; maximize positive detection then fewerFP then fewerUnsure. Fixed before D calibration/test evaluation.',
        evidence='A calibration already informed architecture research; all development is reused. Original test will be retrospective regression only. No independent validation claim.',
        source_sha256=digest(Path(__file__)), selection_input_sha256=digest(ROOT / 'results/murmur-phase-a/selection-predictions.json')))
    model = ConservativePhaseModel(alpha); model.classifier.load_state_dict(torch.load(ROOT / 'generated/murmur-phase-a/Murmur.pt', weights_only=True)); model.eval()
    torch.save(model.state_dict(), OUTPUT / 'Murmur.pt')
    names = ['probabilities', 'phase_probabilities']
    converted = ct.convert(torch.jit.trace(model, torch.randn(1, 1, SAMPLES) * .03), inputs=[ct.TensorType(name='waveform', shape=(1, 1, SAMPLES))], outputs=[ct.TensorType(name=n) for n in names], minimum_deployment_target=ct.target.iOS17, compute_precision=ct.precision.FLOAT32)
    converted.author = 'Chest BPM public-data research'; converted.short_description = 'Conservative phase-supervised murmur research model; not a diagnosis.'
    converted.user_defined_metadata.update(feature_schema='chestbpm-murmur-wave-2k-v1', labels='Absent,Present,Unknown', phase_labels='noise,S1,systole,S2,diastole', dataset='https://doi.org/10.13026/tshs-mw03', weights_sha256=digest(OUTPUT / 'Murmur.pt'))
    converted.save(str(OUTPUT / 'Murmur.mlpackage')); errors = []
    for scale in [0, .0001, .01, .3]:
        x = torch.randn(1, 1, SAMPLES) * scale
        with torch.inference_mode(): expected = model(x)
        actual = converted.predict({'waveform': x.numpy()}); errors.append([float(np.max(np.abs(v.numpy() - actual[n]))) for v, n in zip(expected, names)])
    assert np.max(errors) < .001, errors
    save(OUTPUT / 'conversion.json', dict(maximum_probability_differences=np.max(errors, 0).tolist(), examples=4)); print('Native D conversion passed', errors, flush=True)


if __name__ == '__main__': main()
