"""Cross-check serialized PANNs DFT filters against PyTorch's FFT operator."""
import unittest
import numpy as np
import torch
from torch.nn import functional as F
from panns_murmur_features import FrozenFrontend,WEIGHTS,WEIGHT_SHA,sha

class PannsFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)
        assert sha(WEIGHTS)==WEIGHT_SHA
        state=torch.load(WEIGHTS,map_location='cpu',weights_only=True)['model']
        cls.front=FrozenFrontend(state).eval()

    def test_silence_has_exact_log_floor(self):
        with torch.inference_mode():actual=self.front(torch.zeros(1,1,8000))
        self.assertEqual(tuple(actual.shape),(1,1,401,64))
        self.assertTrue(torch.equal(actual,torch.full_like(actual,-100)))

    def test_serialized_dft_matches_independent_fft(self):
        torch.manual_seed(6122);x=torch.randn(1,1,8000)*.03
        with torch.inference_mode():
            actual=self.front(x)
            expanded=F.interpolate(x,size=128000,mode='linear',align_corners=False)[:,0]
            spectrum=torch.stft(expanded,n_fft=1024,hop_length=320,win_length=1024,window=torch.hann_window(1024),center=True,pad_mode='reflect',return_complex=True)
            expected=10*torch.log10((spectrum.abs().square().transpose(1,2)@self.front.mel).clamp_min(1e-10))[:,None]
        self.assertLess(float((actual-expected).abs().max()),.002)

if __name__=='__main__':unittest.main()
