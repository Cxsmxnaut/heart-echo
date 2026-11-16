"""Package only temporary synthetic source fixtures and licensed public samples."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

TOOL = Path(__file__).with_name('package_submission.py')
spec = importlib.util.spec_from_file_location('package_submission', TOOL)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
REPO = TOOL.parents[1]


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='heartecho-source-test-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'source'
        self.root.mkdir()
        for name in package.REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}\n' if path.suffix == '.json' else 'Synthetic packaging test fixture.\n')
            if name.endswith('.command'):
                path.chmod(0o755)
        (self.root / '.gitignore').write_text(
            '.env\n.env.*\n!.env.example\nnode_modules/\ncache/\ngenerated/\n'
            'diagnostic-logs/\n*.wav\n!HeartEcho/Resources/MurmurSamples/*.wav\n'
            '!ChestBPM/MurmurSamples/*.wav\n')
        (self.root / 'care-assistant/.env.example').write_text('GEMINI_API_KEY=\nCARE_API_TOKEN=replace_with_your_token\n')
        for directory in package.SAMPLE_DIRS:
            for path in (REPO / directory).iterdir():
                if path.name in {'sources.json', 'LICENSE.txt', 'absent.wav', 'present.wav', 'unknown.wav'}:
                    shutil.copyfile(path, self.root / directory / path.name)
        (self.root / 'README.md').write_text('[Judge](docs/JUDGE_GUIDE.md)\n[Source](.)\n')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'add', '--all'], check=True, capture_output=True)

    def build(self, name='snapshot.zip'):
        output = self.directory / name
        package.build_package(self.root, output)
        return output

    def rewrite(self, original, name, change):
        output = self.directory / name
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(output, 'w') as target:
            values = [(info, source.read(info.filename)) for info in source.infolist()]
            for info, data in change(values):
                target.writestr(info, data)
        return output

    def test_current_source_new_files_public_samples_and_reproducibility(self):
        current = self.root / 'HeartEcho/HeartEchoApp/HeartEchoApp.swift'
        current.write_text('// Current working-tree change, not the indexed version.\n')
        new_source = self.root / 'HeartEcho/HeartEchoApp/NewFeature.swift'
        new_source.write_text('// Newly added source is part of the snapshot.\n')
        forbidden = [
            'care-assistant/.env', 'care-assistant/node_modules/private.js',
            'HeartEcho/diagnostic-logs/private.wav', 'research/generated/model.pt',
            'research/cache/private.json', 'research/phone-profile.json',
        ]
        for name in forbidden:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC_PRIVATE_DO_NOT_READ')
            path.chmod(0)
        # Draft root media is outside the source scope and must not be inspected.
        for name in ['personal draft.mp4', 'private preview.png']:
            path = self.root / name
            path.write_bytes(b'SYNTHETIC_PRIVATE_DO_NOT_READ')
            path.chmod(0)
        first, second = self.build(), self.build('again.zip')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        result = package.verify_package(first)
        self.assertEqual(result['status'], 'verified')
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.read('HeartEcho/HeartEchoApp/HeartEchoApp.swift'), current.read_bytes())
            self.assertIn('HeartEcho/HeartEchoApp/NewFeature.swift', archive.namelist())
            self.assertIn('HeartEcho/Resources/MurmurSamples/present.wav', archive.namelist())
            self.assertTrue(set(forbidden).isdisjoint(archive.namelist()))
            self.assertNotIn('personal draft.mp4', archive.namelist())
            self.assertNotIn('private preview.png', archive.namelist())
        before = first.read_bytes()
        with self.assertRaises(package.PackageError):
            package.build_package(self.root, first)
        self.assertEqual(first.read_bytes(), before)

    def test_symlink_and_secret_material_are_refused_without_printing_values(self):
        external = self.directory / 'synthetic-private.txt'
        external.write_text('Synthetic private content outside the source root')
        link = self.root / 'research' / 'linked.py'
        link.symlink_to(external)
        with self.assertRaisesRegex(package.PackageError, 'Symlinks'):
            self.build()
        link.unlink()
        secret = 'AIza' + 'Z' * 35
        (self.root / 'research' / 'bad.js').write_text(f'const apiKey = "{secret}";\n')
        with self.assertRaises(package.PackageError) as raised:
            self.build()
        self.assertNotIn(secret, str(raised.exception))
        self.assertFalse((self.directory / 'snapshot.zip').exists())

    def test_tampered_source_and_unsafe_archive_entries_are_refused(self):
        original = self.build()
        tampered = self.rewrite(original, 'tampered.zip', lambda values: [
            (info, data + b'changed') if info.filename == 'care-assistant/src/server.js' else (info, data)
            for info, data in values])
        with self.assertRaisesRegex(package.PackageError, 'fingerprint'):
            package.verify_package(tampered)
        def extra(values):
            info = zipfile.ZipInfo('../outside.py')
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            return [*values, (info, b'Synthetic escape attempt')]
        escaped = self.rewrite(original, 'escape.zip', extra)
        with self.assertRaises(package.PackageError):
            package.verify_package(escaped)
        def credential(values):
            info = zipfile.ZipInfo('care-assistant/.env')
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            return [*values, (info, b'SYNTHETIC_PRIVATE')]
        credential_zip = self.rewrite(original, 'credential.zip', credential)
        with self.assertRaises(package.PackageError):
            package.verify_package(credential_zip)
        def linked(values):
            for info, data in values:
                if info.filename == 'care-assistant/src/server.js':
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                yield info, data
        symlink_zip = self.rewrite(original, 'symlink.zip', linked)
        with self.assertRaisesRegex(package.PackageError, 'regular archive files'):
            package.verify_package(symlink_zip)

    def test_verification_needs_no_git_and_extracted_manifest_can_rebuild(self):
        original = self.build()
        with patch.object(package.subprocess, 'run', side_effect=AssertionError('Verification must not invoke Git')):
            self.assertEqual(package.verify_package(original)['status'], 'verified')
        extracted = self.directory / 'extracted'
        with zipfile.ZipFile(original) as archive:
            archive.extractall(extracted)
        rebuilt = self.directory / 'rebuilt.zip'
        package.build_package(extracted, rebuilt)
        self.assertEqual(original.read_bytes(), rebuilt.read_bytes())

    def test_broken_relative_links_fail_and_omitted_generated_links_are_disclosed(self):
        (self.root / 'README.md').write_text('[Missing](docs/missing.md)\n')
        with self.assertRaisesRegex(package.PackageError, 'Broken relative'):
            self.build()
        (self.root / 'README.md').write_text('[Judge](docs/JUDGE_GUIDE.md)\n[Local artifact](research/generated/result.md)\n')
        output = self.build()
        result = package.verify_package(output)
        self.assertEqual(result['relative_links_checked'], 1)
        self.assertEqual(result['omitted_local_artifact_references'], 1)

    def test_relative_links_need_exact_case_and_can_target_packaged_directories(self):
        (self.root / 'CREDITS.md').write_text('[Sources](HeartEcho/Resources/MurmurSamples/SOURCES.json)\n')
        with self.assertRaisesRegex(package.PackageError, 'Case-sensitive relative source link mismatch in CREDITS.md'):
            self.build()
        (self.root / 'CREDITS.md').write_text(
            '[Sources](HeartEcho/Resources/MurmurSamples/sources.json)\n'
            '[Sample directory](HeartEcho/Resources/MurmurSamples/)\n')
        output = self.build()
        self.assertEqual(package.verify_package(output)['status'], 'verified')


if __name__ == '__main__':
    unittest.main()
