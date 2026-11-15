import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from ecg_validation import reference, verify


class ECGReferenceChecks(unittest.TestCase):
    def setUp(self):
        self.peaks = np.arange(31, dtype=float)

    def test_known_rate_with_small_detector_offset(self):
        for latest in [False, True]:
            self.assertEqual(reference(self.peaks, self.peaks + .02, 10.1, latest), (60, 'available'))

    def test_two_definitions_preserve_rate_changes(self):
        peaks = np.array([0, 1, 2, 3, 4, 4.5, 5, 20], dtype=float)
        self.assertEqual(reference(peaks, peaks, 5.1)[0], 60)
        self.assertEqual(reference(peaks, peaks, 5.1, True)[0], 80)

    def test_single_detector_missed_beat_is_not_filled_in(self):
        self.assertEqual(reference(self.peaks, np.delete(self.peaks, 8), 10.1)[1], 'detectors_disagree')

    def test_both_detectors_missed_beat_does_not_join_gap(self):
        missing = np.delete(self.peaks, 8)
        self.assertEqual(reference(missing, missing, 10.1)[1], 'possible_missing_ecg_beat')

    def test_extra_detected_beat_prevents_false_agreement(self):
        extra = np.sort(np.append(self.peaks, 8.3))
        self.assertEqual(reference(self.peaks, extra, 10.1)[1], 'detectors_disagree')

    def test_boundary_event_requires_both_detectors_before_now(self):
        self.assertEqual(reference(self.peaks, self.peaks + .02, 10)[1], 'detectors_disagree')

    def test_negative_context_does_not_satisfy_warmup(self):
        peaks = np.arange(-8., 31.)
        self.assertEqual(reference(peaks, peaks, 3)[1], 'insufficient_peaks')

    def test_empty_and_stale_references_remain_missing(self):
        self.assertIsNone(reference(np.array([]), np.array([]), 10)[0])
        self.assertIsNone(reference(self.peaks[:5], self.peaks[:5], 10)[0])

    def test_large_peak_disagreement_remains_missing(self):
        self.assertEqual(reference(self.peaks, self.peaks + .1, 10.1)[1], 'detectors_disagree')

    def test_changed_frozen_input_blocks_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = root / 'input'; data.write_text('before')
            (root / 'protocol.json').write_text('{}')
            (root / 'freeze.json').write_text(json.dumps({'sha256': {str(data): hashlib.sha256(data.read_bytes()).hexdigest()}}))
            self.assertEqual(verify(root), {})
            data.write_text('after')
            with self.assertRaisesRegex(ValueError, 'Frozen file changed'): verify(root)


if __name__ == '__main__': unittest.main()
