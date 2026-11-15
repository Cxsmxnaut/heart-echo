import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import hashlib

import numpy as np
import soundfile as sf
from event_benchmark import runs, warp_diastole, episodes, match, score


def event(start, end, kind='S1'):
    return dict(start=start, end=end, time=(start + end) / 2, kind=kind,
                firstFrame=round(start * 100), lastFrame=round(end * 100) - 1,
                confidence=.9, meanConfidence=.8, acousticValid=True, complete=True, qualified=True)


class EventChecks(unittest.TestCase):
    def test_diastolic_warp_preserves_every_heart_sound_sample(self):
        labels = np.repeat(np.array([1, 2, 3, 4, 1, 2, 3, 4], dtype=np.int8), [60, 120, 50, 500, 60, 130, 50, 500])
        wave = np.sin(np.arange(len(labels)) * .3)
        changed, target = warp_diastole(wave, labels, np.random.default_rng(7))
        old = [(k, wave[a:b]) for a, b, k in runs(labels) if k in [1, 3]]
        new = [(k, changed[a:b]) for a, b, k in runs(target) if k in [1, 3]]
        self.assertEqual([k for k, _ in old], [k for k, _ in new])
        for (_, a), (_, b) in zip(old, new): np.testing.assert_array_equal(a, b)
        self.assertNotEqual(len(wave), len(changed))

    def test_duplicate_predictions_do_not_inflate_true_beats(self):
        pairs = match([1, 2], [.99, 1.01, 2], .05)
        self.assertEqual(len(pairs), 2); self.assertEqual(len({p[0] for p in pairs}), 2)

    def test_tolerance_boundary_is_numerically_stable(self):
        self.assertEqual(len(match([1], [1.05], .05)), 1)
        self.assertEqual(len(match([1], [1.051], .05)), 0)

    def test_fragments_join_without_creating_gap_observations(self):
        result = episodes([event(1, 1.04), event(1.06, 1.09), event(1.11, 1.14)], [])
        self.assertEqual(len(result), 1); self.assertEqual(result[0]['observedFrames'], 10)
        self.assertEqual(result[0]['parts'], 3)
        expected = (1.02 * 4 + 1.075 * 3 + 1.125 * 3) / 10
        self.assertAlmostEqual(result[0]['time'], expected)

    def test_masked_gap_and_intervening_sound_prevent_join(self):
        parts = [event(1, 1.04), event(1.06, 1.09)]
        self.assertEqual(len(episodes(parts, [[1.045, 1.055]])), 2)
        self.assertEqual(len(episodes([parts[0], event(1.045, 1.055, 'S2'), parts[1]], [])), 3)

    def test_real_irregular_intervals_are_not_smoothed_or_rejected(self):
        values = [event(t, t + .04) for t in [1, 1.7, 2.8, 3.3]]
        result = episodes(values, [])
        self.assertEqual(len(result), 4); self.assertTrue(all(e['qualified'] for e in result))
        np.testing.assert_allclose(np.diff([e['time'] for e in result]), [.7, 1.1, .5])

    def test_unknown_annotation_is_distinct_from_known_noise_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'v17').mkdir(); cases = []
            for condition in ['clean', 'noise_only']:
                audio = root / (condition + '.wav'); labels = root / (condition + '.npy')
                sf.write(audio, np.zeros(5000), 1000, subtype='PCM_16'); np.save(labels, np.zeros(5000, dtype=np.int8))
                cases.append(dict(id=condition, group='group', condition=condition, path=str(audio), labels=str(labels),
                                  audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(), labels_sha256=hashlib.sha256(labels.read_bytes()).hexdigest()))
                (root / 'v17' / (condition + '.json')).write_text(json.dumps(dict(seconds=5, coverageStart=1.2, coverageEnd=4.9,
                    events=[event(2.95, 3.05)], maskedRanges=[])))
            (root / 'references.json').write_text(json.dumps(cases))
            with contextlib.redirect_stdout(io.StringIO()): score(root, 'v17')
            rows = json.loads((root / 'scores-v17.json').read_text())['reports']
            self.assertTrue(all(r['S1']['fp'] == (1 if r['condition'] == 'noise_only' else 0) for r in rows))


if __name__ == '__main__': unittest.main()
