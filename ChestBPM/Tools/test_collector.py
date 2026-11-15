import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collect_study import validate_archive, merge_rows, main


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
