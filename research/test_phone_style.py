"""Check meaningful augmentation invariants and exclusion/partition boundaries."""
import unittest
import numpy as np
from phone_style import fit_profile, transform, eligible_today, assert_person_split


class PhoneStyleTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(81)
        t = np.arange(12000) / 2000
        self.heart = (np.exp(-((t - 2) / .05) ** 2) + .6 * np.exp(-((t - 2.3) / .05) ** 2)) * np.sin(2 * np.pi * 80 * t)
        self.profile = fit_profile([self.heart], [self.heart * .02], [self.rng.normal(0, .002, len(t))])

    def test_no_time_warp_or_large_peak_shift(self):
        y = transform(self.heart, self.profile, np.random.default_rng(8))
        self.assertEqual(y.shape, self.heart.shape)
        self.assertLess(abs(int(np.argmax(np.abs(y))) - int(np.argmax(np.abs(self.heart)))), 8)
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertLessEqual(float(np.max(np.abs(y))), .951)

    def test_identity_spectrum_and_bounded_extreme_response(self):
        self.assertLess(float(np.max(np.abs(self.profile['response_db']))), 1e-7)
        noise = self.rng.normal(size=12000)
        profile = fit_profile([self.heart], [noise], [noise])
        self.assertLessEqual(float(np.max(np.abs(profile['response_db']))), 6.)

    def test_deterministic_and_no_private_cycle_in_noise(self):
        a = transform(self.heart, self.profile, np.random.default_rng(9))
        b = transform(self.heart, self.profile, np.random.default_rng(9))
        np.testing.assert_array_equal(a, b)
        self.assertNotIn('audio', self.profile)

    def test_silent_or_invalid_fit_is_rejected(self):
        for invalid in [np.zeros(12000), np.full(12000, np.nan), np.zeros((12000, 2))]:
            with self.assertRaises(ValueError):
                fit_profile([self.heart], [invalid], [self.heart])

    def test_case_on_and_unconfirmed_clips_never_enter_fit(self):
        rows = [{'id': 'first', 'case_on': True, 'excluded': True},
                {'id': 'second', 'case_on': False, 'excluded': False},
                {'id': 'unconfirmed', 'excluded': False}]
        self.assertEqual([r['id'] for r in eligible_today({'records': rows})], ['second'])

    def test_person_leakage_and_test_access_rejected(self):
        with self.assertRaises(ValueError):
            assert_person_split([{'group': 'A', 'role': 'training'}, {'group': 'A', 'role': 'selection'}])
        with self.assertRaises(ValueError):
            assert_person_split([{'group': 'A', 'role': 'test'}])


if __name__ == '__main__':
    unittest.main()
