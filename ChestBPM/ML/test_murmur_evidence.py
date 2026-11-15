import unittest
import torch
from murmur_evidence_model import require_evidence


class EvidenceChecks(unittest.TestCase):
    def test_high_evidence_preserves_class_scores(self):
        p=torch.tensor([[.1,.8,.1]]);q=torch.full((1,5,194),.2)
        torch.testing.assert_close(require_evidence(p,q,torch.ones(1,194)),p)

    def test_no_evidence_moves_present_to_unsure_and_preserves_absent(self):
        p=torch.tensor([[.1,.8,.1]]);q=torch.full((1,5,194),.2)
        torch.testing.assert_close(require_evidence(p,q,torch.zeros(1,194)),torch.tensor([[.1,0.,.9]]))

    def test_all_scores_remain_normalized_and_nonnegative(self):
        torch.manual_seed(6);p=torch.randn(20,3).softmax(1);q=torch.randn(20,5,194).softmax(1);m=torch.rand(20,194)*.5
        out=require_evidence(p,q,m)
        self.assertTrue(torch.all(out>=0));torch.testing.assert_close(out.sum(1),torch.ones(20));torch.testing.assert_close(out[:,0],p[:,0]);self.assertTrue(torch.all(out[:,1]<=p[:,1]))


if __name__=='__main__':unittest.main()
