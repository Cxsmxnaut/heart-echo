import unittest
import torch
from murmur_additive_model import add_positive_evidence


class AdditiveChecks(unittest.TestCase):
    def test_fusion_preserves_normalization_and_confidence_bounds(self):
        torch.manual_seed(9);base=torch.randn(300,3).softmax(1);proposal=torch.randn(300,3).softmax(1);out=add_positive_evidence(base,proposal)
        self.assertTrue(torch.all(out>=0));torch.testing.assert_close(out.sum(1),torch.ones(300))
        self.assertTrue(torch.all(out[:,1]>=base[:,1]));self.assertTrue(torch.all(out[:,1]>=proposal[:,1]))
        self.assertTrue(torch.all(out[:,0]<=base[:,0]+1e-7));self.assertTrue(torch.all(out[:,2]<=base[:,2]+1e-7))

    def test_no_extra_positive_evidence_keeps_baseline(self):
        base=torch.tensor([[.8,.1,.1]]);proposal=torch.tensor([[.5,.05,.45]])
        torch.testing.assert_close(add_positive_evidence(base,proposal),base)

    def test_extreme_baseline_and_proposal_remain_finite(self):
        base=torch.eye(3);proposal=torch.tensor([[0.,1.,0.]]).repeat(3,1);out=add_positive_evidence(base,proposal)
        self.assertTrue(torch.isfinite(out).all());torch.testing.assert_close(out,proposal)

    def test_window_averages_cannot_increase_absent_score(self):
        torch.manual_seed(10);base=torch.randn(5,3).softmax(1);proposal=torch.randn(5,3).softmax(1);out=add_positive_evidence(base,proposal)
        self.assertLessEqual(float(out[:,0].mean()),float(base[:,0].mean())+1e-7)


if __name__=='__main__':unittest.main()
