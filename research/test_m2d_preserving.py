import unittest
import torch

from m2d_murmur import M2DMurmur,HERE
from train_m2d_preserving import preserving_loss,trainable_name,state_fingerprints


class PreservingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):torch.set_num_threads(2)

    def test_penalty_protects_true_detections_and_allows_improvement(self):
        target=torch.tensor([1])
        teacher=torch.tensor([[.05,.9,.05]])
        low=torch.tensor([[0.,0.,0.]],requires_grad=True)
        high=torch.tensor([[-3.,3.,-3.]],requires_grad=True)
        loss,ce,penalty=preserving_loss(low,target,teacher)
        _,_,better=preserving_loss(high,target,teacher)
        self.assertGreater(float(penalty),0.)
        self.assertEqual(float(better),0.)
        loss.backward();self.assertLess(float(low.grad[0,1]),0.)

    def test_false_positive_teacher_is_not_preserved_on_true_absent(self):
        logits=torch.tensor([[0.,2.,0.]],requires_grad=True)
        loss,_,penalty=preserving_loss(logits,torch.tensor([0]),torch.tensor([[.01,.98,.01]]))
        self.assertEqual(float(penalty),0.)
        loss.backward();self.assertGreater(float(logits.grad[0,1]),0.)

    def test_expert_unknown_is_protected(self):
        _,_,p=preserving_loss(torch.zeros(1,3),torch.tensor([2]),torch.tensor([[.05,.05,.9]]))
        self.assertGreater(float(p),0.)

    def test_declared_global_blend_keeps_valid_probabilities(self):
        from compare_m2d_preserving import combine
        m={'reading':{'finding':'absent','probabilities':[.8,.1,.1],'windows':2}}
        h={'reading':{'finding':'present','probabilities':[.01,.98,.01],'windows':2}}
        high=combine(h,m,'mixture_0.60')['reading']
        low=combine(h,m,'mixture_0.25')['reading']
        self.assertAlmostEqual(sum(high['probabilities']),1.)
        self.assertEqual(high['finding'],'present');self.assertEqual(low['finding'],'absent')

    def test_real_last_two_blocks_learn_while_first_ten_and_norm_stay_exact(self):
        torch.manual_seed(91)
        model=M2DMurmur(HERE/'cache/m2d-weights').eval()
        for name,p in model.named_parameters():p.requires_grad_(trainable_name(name))
        before=state_fingerprints(model,True)
        x=torch.randn(2,1,80,501)*4.2-7.1
        with torch.no_grad():teacher=model(x).softmax(1)
        optimizer=torch.optim.SGD([p for p in model.parameters() if p.requires_grad],lr=1e-4)
        loss,_,_=preserving_loss(model(x),torch.tensor([0,1]),teacher);loss.backward()
        for name,p in model.named_parameters():
            if trainable_name(name):
                self.assertIsNotNone(p.grad,name);self.assertTrue(torch.isfinite(p.grad).all(),name)
            else:self.assertIsNone(p.grad,name)
        self.assertGreater(float(model.runtime.backbone.blocks[10].mlp.fc1.weight.grad.abs().sum()),0.)
        optimizer.step();self.assertEqual(before,state_fingerprints(model,True))


if __name__=='__main__':unittest.main()
