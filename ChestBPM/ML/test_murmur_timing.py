import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import torch
from torch.nn import functional as F
from murmur_model import FRAMES
from murmur_phase_model import PhaseMurmurNet
from murmur_timing_model import TimingMurmurNet, WaveTimingModel
from murmur_timing_data import timing_targets


class TimingChecks(unittest.TestCase):
    def setUp(self): torch.manual_seed(4); torch.set_num_threads(1)

    def fixture(self, target, systolic='Early-systolic', diastolic='nan'):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        root = Path(folder.name); p = root / 'cache/circor/labels.tsv'; p.parent.mkdir(parents=True)
        p.write_text('0 .1 1\n.1 .5 2\n.5 .6 3\n.6 1 4\n1 1.3 0\n')
        r = dict(target=target, systolic_timing=systolic, diastolic_timing=diastolic, annotation='labels.tsv', annotation_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        with patch('murmur_phase_data.ROOT', root), patch('murmur_timing_data.ROOT', root): return timing_targets(r, 65)

    def test_early_timing_and_unannotated_frames(self):
        q, t = self.fixture(1); centers = (np.arange(65) * 40 + 128) / 2000
        self.assertTrue(np.all(t[(centers >= .1) & (centers < .3)] == 1))
        self.assertTrue(np.all(t[(centers >= .3) & (centers < .5)] == 0))
        self.assertTrue(np.all(t[np.isin(q, [-100, 1, 3])] == -100))

    def test_unknown_and_missing_timing_are_masked(self):
        self.assertTrue(np.all(self.fixture(2)[1] == -100))
        self.assertTrue(np.all(self.fixture(1, 'nan')[1] == -100))

    def test_absent_has_only_annotated_negative_targets(self):
        q, t = self.fixture(0)
        self.assertTrue(np.all(t[q != -100] == 0)); self.assertTrue(np.all(t[q == -100] == -100))

    def test_initial_residuals_preserve_phase_candidate(self):
        a = PhaseMurmurNet().eval(); c = TimingMurmurNet().eval(); c.load_state_dict(a.state_dict(), strict=False)
        x = torch.randn(2, 32, FRAMES)
        with torch.no_grad(): torch.testing.assert_close(a(x), c(x), rtol=0, atol=0)

    def test_timing_loss_reaches_shared_audio_features(self):
        model = TimingMurmurNet(); p, q, t = model.joint(torch.randn(2, 32, FRAMES))
        F.binary_cross_entropy_with_logits(t, torch.ones_like(t)).backward()
        self.assertGreater(float(model.murmur.weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.layers[0].weight.grad.abs().sum()), 0)

    def test_waveform_output_shapes(self):
        with torch.no_grad(): p, q, t = WaveTimingModel(TimingMurmurNet().eval()).eval()(torch.zeros(1, 1, 8000))
        self.assertEqual(tuple(t.shape), (1, FRAMES)); self.assertTrue(torch.isfinite(t).all())
        torch.testing.assert_close(p.sum(1), torch.ones(1)); torch.testing.assert_close(q.sum(1), torch.ones(1, FRAMES))


if __name__ == '__main__': unittest.main()
