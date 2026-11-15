import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collect_study import validate_archive, merge_rows, main, collect_audio


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.path = self.root / 'archive.ndjson'; self.rows = [dict(run='run', sequence=i, event='test') for i in range(1, 4)]
        self.path.write_text(''.join(json.dumps(r) + '\n' for r in self.rows))
        self.expected = dict(run='run', rows=3, bytes=self.path.stat().st_size)

    def test_complete_closed_archive(self):
        self.assertEqual(validate_archive(self.path, self.expected), self.rows)

    def test_missing_sequence_is_rejected(self):
        self.path.write_text(json.dumps(self.rows[0]) + '\n' + json.dumps(self.rows[2]) + '\n')
        with self.assertRaises(ValueError): validate_archive(self.path, self.expected)

    def test_partial_archive_is_rejected(self):
        with self.path.open('a') as out: out.write('{"run":')
        with self.assertRaises(ValueError): validate_archive(self.path, self.expected)

    def test_manifest_mismatch_is_rejected(self):
        with self.assertRaises(ValueError): validate_archive(self.path, dict(self.expected, rows=4))

    def test_retries_do_not_duplicate_events(self):
        seen = set(); out = self.root / 'captured.ndjson'
        self.assertEqual(merge_rows(out, self.rows, seen), 3)
        self.assertEqual(merge_rows(out, self.rows, seen), 0)
        self.assertEqual(len(out.read_text().splitlines()), 3)

    def test_deleted_audio_is_not_downloaded_and_local_copy_removed(self):
        name = 'Audio/12345678-1234-1234-1234-123456789abc.wav'
        rows = [dict(event='audio_saved', audioFile=name), dict(event='audio_deleted', audioFile=name)]
        (self.root / 'captured.ndjson').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        target = self.root / name; target.parent.mkdir(); target.write_bytes(b'old')
        calls = []
        def copy(device, bundle, source, target, *args):
            calls.append(source); target.write_text(json.dumps([name]))
        with patch('collect_study.copy_file', side_effect=copy):
            self.assertEqual(collect_audio('device', 'app.veritas.heartecho', self.root), [])
        self.assertEqual(calls, ['Documents/Diagnostics/audio-deleted.json'])
        self.assertFalse(target.exists())

    def test_missing_deletion_manifest_blocks_audio_downloads(self):
        with patch('collect_study.copy_file', side_effect=RuntimeError('unavailable')) as copy:
            self.assertEqual(len(collect_audio('device', 'app.veritas.heartecho', self.root)), 1)
            self.assertEqual(copy.call_count, 1)

    def test_manifest_alone_removes_local_audio_without_a_logged_delete_event(self):
        name = 'Audio/12345678-1234-1234-1234-123456789abc.wav'
        target = self.root / name; target.parent.mkdir(); target.write_bytes(b'old')
        with patch('collect_study.copy_file', side_effect=lambda device, bundle, source, dest: dest.write_text(json.dumps([name]))):
            self.assertEqual(collect_audio('device', 'app.veritas.heartecho', self.root), [])
        self.assertFalse(target.exists())

    def test_unsafe_deletion_manifest_is_rejected(self):
        with patch('collect_study.copy_file', side_effect=lambda device, bundle, source, dest: dest.write_text(json.dumps(['../../unrelated.wav']))):
            self.assertEqual(len(collect_audio('device', 'app.veritas.heartecho', self.root)), 1)

    def run_collector(self, arguments, stop_after=None, advance=1):
        clock = [0]; polls = []

        def copy(device, bundle, source, target):
            polls.append(source)
            if stop_after and len(polls) > stop_after: raise KeyboardInterrupt
            target.write_text(json.dumps(dict(time=0, state='recording')))

        def sleep(_): clock[0] += advance

        with patch('sys.argv', ['collector', '--device', 'test', '--output', str(self.root), *arguments]), \
             patch('collect_study.copy_file', side_effect=copy), \
             patch('collect_study.time.monotonic', side_effect=lambda: clock[0]), \
             patch('collect_study.time.sleep', side_effect=sleep), patch('builtins.print'):
            try: main()
            except KeyboardInterrupt:
                if not stop_after: raise
        return polls

    def test_default_and_zero_keep_collecting_past_one_hour(self):
        for arguments in ([], ['--wait', '0']):
            with self.subTest(arguments=arguments):
                polls = self.run_collector(arguments, stop_after=2, advance=4000)
                self.assertEqual(len(polls), 3)
                self.assertTrue(json.loads((self.root / 'summary.json').read_text())['connection_ok'])
                self.assertFalse((self.root / 'summary.json.tmp').exists())

    def test_explicit_duration_still_stops(self):
        self.assertEqual(len(self.run_collector(['--wait', '2'], advance=1)), 2)


if __name__ == '__main__': unittest.main()
