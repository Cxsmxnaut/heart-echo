import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from poll_diagnostics import copy_audio, summary


class PollChecks(unittest.TestCase):
    def test_rejects_log_paths_outside_audio_directory(self):
        with tempfile.TemporaryDirectory() as root, patch('poll_diagnostics.subprocess.run') as command:
            errors = copy_audio([dict(event='audio_saved', audioFile='../../private.wav')], 'phone', 'app', Path(root))
            self.assertEqual(errors, []); command.assert_not_called()

    def test_audio_copy_failure_does_not_leave_a_completed_file(self):
        with tempfile.TemporaryDirectory() as root, patch('poll_diagnostics.subprocess.run') as command:
            command.return_value.returncode = 1; command.return_value.stderr = 'connection lost'
            name = 'Audio/12345678-1234-1234-1234-123456789ABC.wav'
            errors = copy_audio([dict(event='audio_saved', audioFile=name)], 'phone', 'app', Path(root))
            self.assertEqual(len(errors), 1); self.assertFalse((Path(root) / name).exists())

    def test_summary_keeps_participant_rejections_and_processing_overruns(self):
        rows = [dict(event='test_started', test='B1', participant='B', condition='Off chest'),
                dict(event='estimate', test='B1', processingMS=510, elapsed=8,
                     estimate=dict(seconds=8, diagnostics=dict(enhanced=dict(reason='model_detected_noise'))))]
        result = summary(rows)
        self.assertEqual(result['participant'], 'B'); self.assertEqual(result['accepted_frames'], 0)
        self.assertEqual(result['neural_reasons'], {'model_detected_noise': 1})
        self.assertEqual(result['processing_ms']['over_500_ms'], 1)


if __name__ == '__main__': unittest.main()
