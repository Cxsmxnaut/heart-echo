"""Protect the V7 frequency-only adaptation from time mixing or high-band leaks."""
import unittest
import torch
from panns_heartband_features import expand_heart_band

class HeartBandTests(unittest.TestCase):
    def test_time_order_and_constant_per_frame_are_preserved(self):
        x=torch.arange(401,dtype=torch.float32)[None,None,:,None].expand(2,1,401,64).clone()
        actual=expand_heart_band(x)
        self.assertEqual(tuple(actual.shape),(2,1,401,64))
        self.assertTrue(torch.equal(actual,x))

    def test_discarded_high_bands_cannot_change_features(self):
        torch.manual_seed(7);a=torch.randn(2,1,401,64);b=a.clone();b[:,:,:,17:]=1e6
        self.assertTrue(torch.equal(expand_heart_band(a),expand_heart_band(b)))

if __name__=='__main__':unittest.main()
