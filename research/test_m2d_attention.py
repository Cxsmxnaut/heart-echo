import unittest
from pathlib import Path
import tempfile

import numpy as np
import torch
from torch import nn

from m2d_attention import TemporalAttentionPool, M2DDecisionHead, M2DAttentionMurmur
from m2d_murmur import HERE, M2DMurmur
from train_m2d_murmur import tensor_sha


class AttentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_uniform_initialization_matches_mean_and_masks_padding(self):
        torch.manual_seed(7)
        pool = TemporalAttentionPool(8, 4)
        x = torch.randn(3, 5, 8)
        pooled, weights = pool(x, return_weights=True)
        torch.testing.assert_close(pooled, x.mean(1), atol=1e-6, rtol=1e-6)
        torch.testing.assert_close(weights, torch.full((3, 5), .2))
        mask = torch.tensor([[True, True, False, False, False]] * 3)
        y, w = pool(x, mask=mask, return_weights=True)
        torch.testing.assert_close(y, x[:, :2].mean(1))
        self.assertEqual(float(w[:, 2:].sum()), 0.)
        with self.assertRaises(ValueError):
            pool(x, mask=torch.zeros(3, 5, dtype=torch.bool))

    def test_attention_learns_sparse_evidence_with_a_fixed_classifier(self):
        torch.manual_seed(19)
        pool = TemporalAttentionPool(8, 8)
        # The positive event appears in one of eight frames; other frames are
        # distractors. This checks actual learning, not just the output shape.
        x = torch.randn(16, 8, 8) * .05
        labels = torch.tensor([0, 1] * 8)
        x[:, :, 0] -= 1.
        for i in range(1, 16, 2):
            x[i, i % 8, 0] = 4.
            x[i, i % 8, 1] = 2.
        optimizer = torch.optim.Adam(pool.parameters(), lr=.03)
        def objective():
            z = pool(x)[:, 0]
            return nn.functional.cross_entropy(torch.stack([-z, z], dim=1), labels)
        initial = float(objective().detach())
        before = {k: v.clone() for k, v in pool.state_dict().items()}
        for _ in range(60):
            optimizer.zero_grad(); loss = objective(); loss.backward(); optimizer.step()
        self.assertLess(float(objective().detach()), initial * .5)
        _, weights = pool(x, return_weights=True)
        for i in range(1, 16, 2):
            self.assertGreater(float(weights[i, i % 8].detach()), .5)
        for k, value in pool.state_dict().items():
            self.assertTrue(torch.isfinite(value).all(), k)
            self.assertFalse(torch.equal(value, before[k]), k)

    def test_head_train_mode_keeps_normalization_fixed(self):
        norm = nn.BatchNorm1d(3840, affine=False)
        frozen_classifier = nn.Linear(3840, 3).requires_grad_(False)
        head = M2DDecisionHead(norm, frozen_classifier).train()
        before = {k: v.clone() for k, v in head.norm.state_dict().items()}
        head(torch.randn(2, 4, 3840)).sum().backward()
        self.assertFalse(head.norm.training)
        self.assertIsNotNone(head.classifier.weight.grad)
        for k, value in head.norm.state_dict().items():
            self.assertTrue(torch.equal(value, before[k]), k)

    def test_training_cache_preserves_time_frames_and_label_alignment(self):
        from train_m2d_attention import TimeFeatures
        frames = (np.arange(3 * 32 * 3840, dtype=np.float32) % 13).reshape(3, 32, 3840).astype('<f2')
        labels = np.array([1, 0, 2])
        reference = np.array([[.1, .8, .1], [.9, .05, .05], [.05, .05, .9]], dtype=np.float32)
        with tempfile.TemporaryDirectory(prefix='m2d-attention-test-') as directory:
            path = Path(directory) / 'frames.f16'
            frames.tofile(path)
            dataset = TimeFeatures(path, labels, reference, 32)
            for index in [2, 0, 1]:
                value, target, teacher = dataset[index]
                self.assertEqual(value.shape, (32, 3840))
                self.assertEqual(value.dtype, torch.float16)
                self.assertEqual(target, labels[index])
                torch.testing.assert_close(value, torch.from_numpy(frames[index]))
                torch.testing.assert_close(teacher, torch.from_numpy(reference[index]))

    def test_real_m2d_attention_path_matches_then_learns_and_reloads(self):
        torch.manual_seed(71)
        baseline = M2DMurmur(HERE / 'cache/m2d-weights').eval()
        path = HERE / 'generated/murmur-v11-m2d/released-source-stage/artifacts/M2D.pt'
        baseline.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
        model = M2DAttentionMurmur(baseline).train()
        self.assertEqual(model.head.pooling, 'attention')
        frozen = {k: tensor_sha(v) for k, v in model.runtime.state_dict().items()}
        norm = {k: tensor_sha(v) for k, v in model.head.norm.state_dict().items()}
        x = torch.randn(2, 1, 80, 501) * 4.2 - 7.1
        with torch.no_grad():
            expected = baseline(x)
            actual, weights = model(x, return_weights=True)
        torch.testing.assert_close(actual, expected, atol=2e-5, rtol=1e-5)
        self.assertGreater(weights.shape[1], 1)
        optimizer = torch.optim.Adam(model.head.parameters(), lr=.001)
        for _ in range(3):
            optimizer.zero_grad()
            nn.functional.cross_entropy(model(x), torch.tensor([0, 1])).backward()
            self.assertTrue(all(p.grad is None for p in model.runtime.parameters()))
            optimizer.step()
        self.assertGreater(float(model.head.pool.score.weight.abs().sum()), 0.)
        self.assertGreater(float(model.head.pool.project.weight.grad.abs().sum()), 0.)
        self.assertEqual(frozen, {k: tensor_sha(v) for k, v in model.runtime.state_dict().items()})
        self.assertEqual(norm, {k: tensor_sha(v) for k, v in model.head.norm.state_dict().items()})
        clone = M2DAttentionMurmur(baseline).eval()
        clone.head.load_state_dict(model.head.state_dict())
        model.eval()
        with torch.no_grad():
            torch.testing.assert_close(model(x), clone(x), atol=0, rtol=0)


if __name__ == '__main__':
    unittest.main()
