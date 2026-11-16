import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
import torch
from torch import nn

from build_m2d_native_bundle import validate_rows
from train_m2d_native_heads import generic_phone,public_input,weighted_loss,windows
from compare_m2d_native_heads import route_reading


class NativeHeadTests(unittest.TestCase):
    def test_forbidden_roles_fail_before_audio_read(self):
        row=dict(record='123_AV',group='123',target=0,patient_target=0,
                 role='calibration',file='training_data/123_AV.wav')
        with self.assertRaises(ValueError):validate_rows([row])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bundle.zip'
            config=json.dumps(dict(public_only=True,private_audio_included=False,records=[row])).encode()
            with zipfile.ZipFile(path,'w') as z:z.writestr('public-config.json',config)
            digest=lambda b:hashlib.sha256(b).hexdigest()
            with self.assertRaises(ValueError):public_input(path,digest(config),digest(path.read_bytes()))

    def test_linked_person_and_path_guards(self):
        row=dict(record='123_AV',group='123',role='training',file='training_data/123_AV.wav')
        with self.assertRaises(ValueError):validate_rows([row,dict(row,record='123_MV',role='selection')])
        with self.assertRaises(ValueError):validate_rows([dict(row,file='../private.wav')])

    def test_native_quality_gates_and_deterministic_generic_augmentation(self):
        wave=(.01*np.sin(2*np.pi*80*np.arange(10000)/2000)).astype(np.float32)
        self.assertEqual(windows(wave).shape,(1,80000))
        for invalid in [wave[:7000],np.zeros(10000,dtype=np.float32),np.ones(10000,dtype=np.float32),np.full(10000,np.nan,dtype=np.float32)]:
            self.assertEqual(len(windows(invalid)),0)
        a=generic_phone(wave,'123_AV');b=generic_phone(wave,'123_AV')
        np.testing.assert_array_equal(a,b)
        self.assertEqual(a.shape,wave.shape);self.assertTrue(np.isfinite(a).all())
        self.assertLessEqual(float(np.abs(a).max()),.981)
        self.assertFalse(np.array_equal(a,generic_phone(wave,'124_AV')))

    def test_training_only_normalization_can_preserve_existing_logits(self):
        torch.manual_seed(7)
        x=torch.randn(9,3840);w=torch.randn(3,3840)*.01;b=torch.randn(3)*.01
        old_mean=torch.randn(3840);old_std=torch.rand(3840)+.1
        new_mean=torch.randn(3840);new_std=torch.rand(3840)+.1
        transformed_w=w*(new_std/old_std)
        transformed_b=b+w@((new_mean-old_mean)/old_std)
        a=nn.functional.linear((x-old_mean)/old_std,w,b)
        c=nn.functional.linear((x-new_mean)/new_std,transformed_w,transformed_b)
        torch.testing.assert_close(a,c,atol=1e-5,rtol=1e-5)

    def test_positive_cost_changes_gradient_pressure_and_loss_is_finite(self):
        labels=torch.tensor([0,0,1,2])
        logits=torch.tensor([[2.,-1.,-2.],[-1.,2.,-2.],[0.,0.,-1.],[-1.,-1.,2.]],requires_grad=True)
        low=weighted_loss(logits,labels,2.);low_grad=torch.autograd.grad(low,logits,retain_graph=True)[0]
        high=weighted_loss(logits,labels,12.);high_grad=torch.autograd.grad(high,logits)[0]
        self.assertTrue(torch.isfinite(low) and torch.isfinite(high))
        self.assertGreater(abs(float(high_grad[2,1])),abs(float(low_grad[2,1])))
        self.assertGreater(float(low_grad[1,1]),0.)

    def test_expert_routes_keep_their_declared_confidence_guards(self):
        absent={'reading':{'finding':'absent','probabilities':[.8,.1,.1]}}
        present={'reading':{'finding':'present','probabilities':[.05,.91,.04]}}
        borderline={'reading':{'finding':'present','probabilities':[.06,.89,.05]}}
        unsure={'reading':{'finding':'unsure','probabilities':[.4,.4,.2]}}
        self.assertIs(route_reading(borderline,absent,'conservative_override'),absent)
        self.assertIs(route_reading(present,absent,'conservative_override'),present)
        self.assertIs(route_reading(unsure,absent,'head'),unsure)
        self.assertIs(route_reading(unsure,absent,'fallback'),absent)
        self.assertIs(route_reading(absent,present,'preserve_positive'),present)


if __name__=='__main__':unittest.main()
