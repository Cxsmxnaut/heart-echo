"""Check the real pretrained backbone, frozen layers and public-data boundary."""
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import torch
from torch.nn import functional as F

from m2d_murmur import M2DMurmur,offsets,decide,SAMPLES,HERE
from train_m2d_murmur import validate_config,prepare
from evaluate_m2d_murmur import predict
from train_m2d_release import released_loss


class M2DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_published_five_second_windows_and_overlap(self):
        self.assertEqual(offsets(SAMPLES-100),[0])
        self.assertEqual(offsets(SAMPLES),[0])
        self.assertEqual(offsets(200000),[0,80000])
        self.assertEqual(offsets(200000,training=True),[0,40000,80000,120000])

    def test_private_and_cross_partition_records_rejected_before_network(self):
        for role in ['calibration','test']:
            config=dict(public_only=True,private_audio_included=False,records=[dict(role=role,group='A')])
            with patch('train_m2d_murmur.download') as fetch:
                with self.assertRaises(ValueError):
                    prepare(config,Path('/unused'),None,None)
                fetch.assert_not_called()
        rows=[dict(role=role,group='A',file='training_data/1_AV.wav') for role in ['training','selection']]
        with self.assertRaises(ValueError):
            validate_config(dict(public_only=True,private_audio_included=False,records=rows))
        with self.assertRaises(ValueError):
            validate_config(dict(public_only=False,private_audio_included=True,records=[]))

    def test_unsure_threshold_and_unknown_stay_visible(self):
        self.assertEqual(decide(np.array([.4,.5,.1])),'unsure')
        self.assertEqual(decide(np.array([.05,.85,.1])),'present')
        self.assertEqual(decide(np.array([.05,.05,.9])),'unsure')

    def test_invalid_audio_never_receives_a_definite_finding(self):
        for wave in [np.zeros(80000,dtype=np.float32),np.ones(80000,dtype=np.float32),
                     np.full(80000,np.nan,dtype=np.float32),np.full(63999,.01,dtype=np.float32)]:
            result=predict(None,wave,16000,torch.device('cpu'))['reading']
            self.assertEqual(result['finding'],'unsure')
            self.assertEqual(result['windows'],0)

    def test_recording_combines_logits_before_softmax(self):
        class Fixed(torch.nn.Module):
            def features(self,wave):
                return wave
            def forward(self,wave):
                a=torch.tensor([6.,0.,0.]).expand(len(wave),-1)
                b=torch.tensor([0.,5.,0.]).expand(len(wave),-1)
                return torch.where((wave[:,:1]>.015),b,a)
        audio=np.r_[np.full(80000,.01,dtype=np.float32),np.full(80000,.02,dtype=np.float32)]
        result=predict(Fixed(),audio,16000,torch.device('cpu'))['reading']
        expected=np.exp([3.,2.5,0.]);expected/=expected.sum()
        np.testing.assert_allclose(result['probabilities'],expected,atol=1e-7)
        self.assertEqual(result['windows'],2)

    def test_released_loss_matches_pinned_evar_patch_and_keeps_gradients(self):
        logits=torch.tensor([[2.,1.,0.],[0.,1.,2.]],requires_grad=True)
        targets=torch.tensor([0,2]);weights=torch.tensor([.5,1.,2.],dtype=torch.float64)
        actual=released_loss(logits,targets,weights)
        probabilities=logits.detach().softmax(1)
        expected=-(F.log_softmax(probabilities,1)[torch.arange(2),targets]*weights[targets]).mean()
        torch.testing.assert_close(actual,expected)
        actual.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertGreater(float(logits.grad.abs().sum()),0.)

    def test_real_m2d_backbone_learns_with_frozen_patch_and_position(self):
        model=M2DMurmur(HERE/'cache/m2d-weights').train()
        self.assertEqual(model.classifier.in_features,3840)
        with torch.no_grad():
            mel=model.features(torch.randn(2,80000)*.01)
        self.assertEqual(tuple(mel.shape),(2,1,80,501))
        self.assertTrue(torch.isfinite(mel).all())
        output=model(mel)
        self.assertEqual(tuple(output.shape),(2,3))
        F.cross_entropy(output,torch.tensor([0,1])).backward()
        for block in model.runtime.backbone.blocks:
            gradient=block.attn.qkv.weight.grad
            self.assertIsNotNone(gradient)
            self.assertTrue(torch.isfinite(gradient).all())
            self.assertGreater(float(gradient.abs().sum()),0.)
        self.assertFalse(model.runtime.backbone.pos_embed.requires_grad)
        self.assertTrue(all(not p.requires_grad for p in model.runtime.backbone.patch_embed.parameters()))


if __name__=='__main__':
    unittest.main()
