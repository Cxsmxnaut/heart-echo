import json
from pathlib import Path
import tempfile
import unittest

import replay_diagnostics as replay


class ReplayChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'capture.ndjson'
        self.rows = [dict(event='microphone_started', sampleRate=48000), dict(event='test_started', test='test')]

    def frame(self, sequence, samples, envelope=None):
        d = dict(signal=dict(totalSamples=samples, clippingFraction=0))
        if envelope is not None:
            d.update(envelope=envelope, brightness=[0.25] * len(envelope))
        return dict(event='estimate', test='test', sequence=sequence, time=sequence * 500,
                    elapsed=sequence * 0.5, estimate=dict(seconds=(samples // 240 + 1) / 200,
                    level=-40, periodicity=0, diagnostics=d))

    def write(self):
        self.path.write_text(''.join(json.dumps(r) + '\n' for r in self.rows))

    def test_future_overlapping_trace_recovers_earlier_frame_without_watch_input(self):
        self.rows += [self.frame(1, 480), self.frame(2, 960, [0.1, 0.2, 0.3, 0.4, 0.5])]
        self.rows[-1]['watch'] = dict(bpm=140)
        self.write()
        _, frames, restored, _ = replay.reconstruct(self.path)
        self.assertEqual(len(frames), 2)
        self.assertEqual(restored[0]['envelope'], [0.1, 0.2, 0.3])
        self.assertEqual(restored[1]['envelope'], [0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertTrue(all('watch' not in r for r in restored))

    def test_conflicting_overlap_is_rejected(self):
        self.rows += [self.frame(1, 480, [0.1, 0.2, 0.3]), self.frame(2, 960, [0.9, 0.2, 0.3, 0.4, 0.5])]
        self.write()
        with self.assertRaisesRegex(ValueError, 'Overlapping traces differ'):
            replay.reconstruct(self.path)

    def test_unrecoverable_tail_is_reported_not_invented(self):
        self.rows += [self.frame(1, 480, [0.1, 0.2, 0.3]), self.frame(2, 960)]
        self.write()
        _, frames, restored, _ = replay.reconstruct(self.path)
        self.assertEqual((len(frames), len(restored)), (2, 1))

    def test_missing_initial_smoothing_state_is_rejected(self):
        self.rows += [self.frame(1, 480), self.frame(2, 48000 * 9, [0.1] * 1600)]
        self.write()
        with self.assertRaisesRegex(ValueError, 'Missing initial frames'):
            replay.reconstruct(self.path)

    def test_comparison_separates_recovered_values_common_values_and_unsure(self):
        frames = [dict(time=1000, elapsed=10, seconds=8, previous=70, candidate=70),
                  dict(time=2000, elapsed=11, seconds=8, candidate=74),
                  dict(time=3000, elapsed=12, seconds=8)]
        pairs = [dict(time=1000, watch=72), dict(time=2000, watch=72), dict(time=3000, watch=72), dict(time=10000, watch=72)]
        stats, _ = replay.evaluate(frames, pairs)
        self.assertEqual((stats['previous']['count'], stats['candidate']['count'], stats['common_pairs']), (1, 2, 1))
        self.assertEqual(stats['candidate']['mean_absolute_difference'], 2)
        self.assertEqual(stats['newly_returned_pairs']['count'], 1)
        self.assertEqual((stats['changed_existing_returns'], stats['unmatched_pairs']), (0, 1))


if __name__ == '__main__':
    unittest.main()
