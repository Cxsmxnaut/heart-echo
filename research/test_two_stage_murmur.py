"""Check the separate adapter, trainable backbones and public upload boundary."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import torch
from torch import nn
from two_stage_models import (Frontend64, spectra, PhoneAdapter, AdaptedClinical,
                              make_clinical)
from train_public_backbones import prepare


class TwoStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_frontend_matches_cached_spectra(self):
        x = np.random.default_rng(4).normal(0, .02, (2, 8000)).astype(np.float32)
        with torch.inference_mode():
            actual = Frontend64()(torch.from_numpy(x[:, None])).numpy()
        np.testing.assert_allclose(actual, spectra(x), atol=1e-4, rtol=1e-5)

    def test_adapter_starts_at_identity_and_cannot_change_timing(self):
        adapter = PhoneAdapter()
        x = torch.randn(2, 64, 194)
        self.assertTrue(torch.equal(adapter(x), x))
        with torch.no_grad():
            adapter.mapping[-1].weight.fill_(10.)
        correction = adapter.correction(x)
        self.assertEqual(correction.shape, (2, 64, 1))
        self.assertLessEqual(float(correction.abs().max()), 1.500001)
        y = adapter(x)
        torch.testing.assert_close(y[:, :, 1:] - y[:, :, :-1], x[:, :, 1:] - x[:, :, :-1], atol=1e-6, rtol=1e-5)

    def test_adapter_training_preserves_all_clinical_weights_and_buffers(self):
        class Clinical(nn.Module):
            def __init__(self):
                super().__init__(); self.bn = nn.BatchNorm1d(64); self.fc = nn.Linear(64, 3)
            def forward(self, x):
                return self.fc(self.bn(x).mean(2))
        model = AdaptedClinical(Clinical()).train()
        before = copy.deepcopy(model.clinical.state_dict())
        optimizer = torch.optim.Adam(model.adapter.parameters(), lr=.01)
        x = torch.randn(4, 64, 194)
        for _ in range(3):
            optimizer.zero_grad(); model(x).square().mean().backward(); optimizer.step()
        self.assertFalse(model.clinical.training)
        self.assertTrue(all(not p.requires_grad for p in model.clinical.parameters()))
        self.assertTrue(all(torch.equal(v, model.clinical.state_dict()[k]) for k, v in before.items()))
        self.assertGreater(float(model.adapter.correction(x).abs().max()), 0.)

    def test_cnn6_pretrained_backbone_has_real_gradients(self):
        model = make_clinical('panns-cnn6', pretrained=True).train()
        loss = nn.functional.cross_entropy(model(torch.randn(2, 64, 194)), torch.tensor([0, 1]))
        loss.backward()
        gradient = model.encoder.conv_block1.conv1.weight.grad
        self.assertIsNotNone(gradient)
        self.assertTrue(torch.isfinite(gradient).all())
        self.assertGreater(float(gradient.abs().sum()), 0.)

    def test_resnet_pretrained_layout_and_three_outputs(self):
        model = make_clinical('resnet18', pretrained=True).eval()
        with torch.inference_mode():
            output = model(torch.randn(2, 64, 194))
        self.assertEqual(output.shape, (2, 3))
        self.assertTrue(torch.isfinite(output).all())

    def test_public_download_rejects_calibration_and_test_before_network(self):
        for role in ['calibration', 'test']:
            with patch('train_public_backbones.download') as fetch:
                with self.assertRaises(AssertionError):
                    prepare({'records': [{'role': role, 'group': 'A'}]}, Path('/unused'))
                fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
