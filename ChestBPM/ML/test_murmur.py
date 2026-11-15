import json
import unittest

import numpy as np
import torch

from murmur_model import Frontend, SAMPLES, spectrum, decision, metrics, windows
from murmur_data import MANIFEST


class MurmurChecks(unittest.TestCase):
    def test_export_frontend_matches_training_fft(self):
        torch.set_num_threads(1)
        for scale in [0, .00001, .03, .8]:
            x = (np.random.default_rng(31).normal(size=SAMPLES) * scale).astype(np.float32)
            actual = Frontend()(torch.from_numpy(x)[None, None]).numpy()[0]
            expected = spectrum(x)
            self.assertTrue(np.all(np.isfinite(actual)))
            np.testing.assert_allclose(actual, expected, atol=.0001, rtol=.0001)

    def test_incomplete_or_uncertain_is_not_absent(self):
        self.assertEqual(decision([.4, .4, .2]), 2)
        self.assertEqual(decision([.1, .1, .8]), 2)
        self.assertEqual(decision([.1, .8, .1]), 1)
        self.assertEqual(decision([.8, .1, .1]), 0)

    def test_missed_positives_and_unsure_are_separate(self):
        x = metrics([1, 1, 1, 0, 0, 2], [0, 2, 1, 1, 0, 2])
        self.assertEqual((x['missed_positive_as_absent'], x['positive_unsure'], x['false_alarms']), (1, 1, 1))
        self.assertAlmostEqual(x['decisive_sensitivity'], 1 / 3)

    def test_window_clock_matches_native_frame_grid(self):
        self.assertEqual(windows(7999), [])
        self.assertEqual(windows(8000), [0])
        self.assertEqual(windows(40000), [0, 8000, 16000, 24000, 32000])
        self.assertEqual(windows(16019), [0, 8000])

    def test_final_patients_never_enter_development(self):
        m = json.loads(MANIFEST.read_text()); by_group = {}
        for r in m['records']: by_group.setdefault(r['group'], set()).add(r['split'])
        self.assertTrue(all(len(x) == 1 for x in by_group.values()))
        test = {g for g, x in by_group.items() if x == {'test'}}
        self.assertEqual(len(test), 120)
        self.assertFalse(test.intersection(m['previous_audio_groups']))


if __name__ == '__main__': unittest.main()
