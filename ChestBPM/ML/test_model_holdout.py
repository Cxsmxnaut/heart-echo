import unittest
import numpy as np
from model_holdout import bpm_reference


def annotated(times):
    labels = np.full(12000, 4, dtype=np.int8)
    for t in times: labels[round(t * 1000):round(t * 1000) + 60] = 1
    return labels


class HoldoutReferenceChecks(unittest.TestCase):
    def test_known_regular_rate(self):
        labels = annotated(range(12))
        self.assertEqual(bpm_reference(labels, 8.1, False), (60, 'available'))
        self.assertEqual(bpm_reference(labels, 8.1, True), (60, 'available'))

    def test_irregularity_is_not_an_annotation_quality_failure(self):
        labels = annotated([0, .6, 1.5, 2.2, 3.8, 4.4, 5.1, 8])
        value, quality = bpm_reference(labels, 5.2, True)
        self.assertEqual(quality, 'available'); self.assertAlmostEqual(value, 240 / 3.6)

    def test_unknown_annotation_gap_is_not_bridged(self):
        labels = annotated(range(12)); labels[3500:3600] = 0
        self.assertEqual(bpm_reference(labels, 8.1, False)[1], 'unknown_annotation_gap')

    def test_incomplete_event_history_stays_missing(self):
        self.assertEqual(bpm_reference(annotated([1, 2]), 6, True)[1], 'insufficient_events')


if __name__ == '__main__': unittest.main()
