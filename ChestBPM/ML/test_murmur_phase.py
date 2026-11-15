import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch
from torch.nn import functional as F

from murmur_model import MurmurNet, FRAMES
from murmur_phase_model import PhaseMurmurNet, WavePhaseModel
from murmur_phase_data import targets, PHASE_MANIFEST


class PhaseChecks(unittest.TestCase):
    def setUp(self): torch.manual_seed(11); torch.set_num_threads(1)

    def test_initial_candidate_preserves_baseline_classification(self):
        baseline = MurmurNet().eval(); model = PhaseMurmurNet(baseline).eval()
        x = torch.randn(2, 32, FRAMES)
        with torch.no_grad():
            expected = baseline(x); actual, phases = model.outputs(x)
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        self.assertEqual(tuple(phases.shape), (2, 5, FRAMES))

    def test_phase_supervision_supplies_gradients(self):
        model = PhaseMurmurNet(); x = torch.randn(2, 32, FRAMES)
        _, phase = model.outputs(x)
        q = torch.arange(FRAMES)[None].repeat(2, 1) % 4 + 1
        F.cross_entropy(phase, q).backward()
        self.assertGreater(float(model.phase.weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.layers[0].weight.grad.abs().sum()), 0)

    def test_predicted_phase_context_can_change_murmur_output(self):
        model = PhaseMurmurNet().eval(); torch.nn.init.normal_(model.phase_head[-1].weight, std=.1)
        x = torch.randn(2, 32, FRAMES)
        with torch.no_grad():
            a = model(x); model.phase.weight.normal_(std=3); b = model(x)
        self.assertGreater(float((a - b).abs().max()), 1e-6)

    def test_annotated_frame_centers_and_unknown_mask(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cache/circor/labels.tsv'; path.parent.mkdir(parents=True)
            path.write_text('0 0 28\n0 .1 1\n.1 .2 2\n.2 .3 3\n.3 .4 4\n.4 .8 0\n')
            r = dict(annotation='labels.tsv', annotation_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            with patch('murmur_phase_data.ROOT', Path(folder)): q = targets(r, 30)
            np.testing.assert_array_equal(q[:2], [1, 1])
            self.assertEqual(set(q), {-100, 1, 2, 3, 4})
            self.assertTrue(np.all(q[(np.arange(30) * 40 + 128) / 2000 >= .4] == -100))

    def test_selection_calibration_and_test_do_not_share_people(self):
        data = json.loads(PHASE_MANIFEST.read_text()); groups = {}
        for r in data['records']: groups.setdefault(r['group'], set()).add(r['role'])
        self.assertTrue(all(len(x) == 1 for x in groups.values()))
        for role, count in [('training', 652), ('selection', 50), ('calibration', 50), ('test', 120)]:
            self.assertEqual(sum(x == {role} for x in groups.values()), count)

    def test_export_wrapper_returns_valid_class_and_phase_scores(self):
        model = WavePhaseModel(PhaseMurmurNet().eval()).eval()
        with torch.no_grad(): p, q = model(torch.zeros(1, 1, 8000))
        self.assertTrue(torch.isfinite(p).all() and torch.isfinite(q).all())
        torch.testing.assert_close(p.sum(1), torch.ones(1))
        torch.testing.assert_close(q.sum(1), torch.ones(1, FRAMES))


if __name__ == '__main__': unittest.main()
