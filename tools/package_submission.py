#!/usr/bin/env python3
"""Build/verify a reproducible public-source package without collecting local data.

Builds use Git's current tracked and nonignored untracked file list. An extracted
package can rebuild its existing manifest-listed source without Git. Verification
always works without Git and never executes anything from an archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ('HeartEcho', 'ChestBPM', 'care-assistant', 'research', 'docs', 'tools')
ROOT_FILES = {'.gitignore', 'README.md', 'CREDITS.md'}
MANIFEST = 'source-manifest.json'
FORMAT_VERSION = 1
MAX_FILE = 50 * 1024 * 1024
MAX_TOTAL = 250 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024
SAMPLE_DIRS = ('HeartEcho/Resources/MurmurSamples', 'ChestBPM/MurmurSamples')
SAMPLE_NAMES = ('absent', 'present', 'unknown')
MODEL_ROOTS = (
    'HeartEcho/Models/BeatStates.mlpackage', 'HeartEcho/Models/Murmur.mlpackage',
    'ChestBPM/ML/Models/BeatStates.mlpackage', 'ChestBPM/ML/Models/Murmur.mlpackage',
    'ChestBPM/ML/PhaseModels/Murmur.mlpackage',
)
MODEL_PARTS = ('Manifest.json', 'Data/com.apple.CoreML/model.mlmodel',
               'Data/com.apple.CoreML/weights/weight.bin')
REQUIRED = {
    '.gitignore', 'README.md', 'CREDITS.md',
    'Start Heart Echo Demo.command', 'Start Heart Echo Judge Demo.command',
    'HeartEcho/README.md', 'HeartEcho/HeartEchoApp/HeartEchoApp.swift',
    'HeartEcho/HeartEchoApp.xcodeproj/project.pbxproj',
    'HeartEcho/HeartEchoApp.xcodeproj/xcshareddata/xcschemes/HeartEchoApp.xcscheme',
    'HeartEcho/Engine/MurmurAnalysis.swift', 'HeartEcho/Tools/configure_project.py',
    'ChestBPM/README.md', 'ChestBPM/ChestBPM.xcodeproj/project.pbxproj',
    'ChestBPM/ML/PROVENANCE.txt', 'care-assistant/package.json',
    'care-assistant/package-lock.json', 'care-assistant/src/server.js',
    'care-assistant/src/service.js', 'care-assistant/src/model.js',
    'care-assistant/scripts/start-demo.js', 'care-assistant/scripts/start-judge.js',
    'care-assistant/public/index.html', 'care-assistant/.env.example',
    'docs/JUDGE_GUIDE.md', 'docs/SUBMISSION.md', 'docs/RESULTS.md',
    'research/third_party/M2D-NOTICE.md', 'tools/package_submission.py',
}
REQUIRED |= {f'{root}/{part}' for root in MODEL_ROOTS for part in MODEL_PARTS}
REQUIRED |= {f'{root}/{name}.wav' for root in SAMPLE_DIRS for name in SAMPLE_NAMES}
REQUIRED |= {f'{root}/{name}' for root in SAMPLE_DIRS for name in ('sources.json', 'LICENSE.txt')}
EXCLUDED_DIRS = {
    '.git', '.hg', '.svn', 'node_modules', '__pycache__', 'cache', 'caches',
    '.cache', 'generated', 'diagnostic-logs', 'captures', 'private',
    'deriveddata', 'xcuserdata', '.swiftpm', '.build', 'test-results',
    'playwright-report', 'integration-backup', 'previews', 'model-cache',
    'runs', 'exports',
}
EXCLUDED_SUFFIXES = {
    '.pyc', '.pyo', '.log', '.ndjson', '.f32', '.f16', '.npy', '.npz',
    '.pt', '.pth', '.ckpt', '.gguf', '.safetensors', '.onnx', '.h5', '.hdf5',
    '.pkl', '.pickle', '.joblib', '.tflite', '.mlmodelc',
    '.pem', '.key', '.p12', '.pfx', '.p8', '.mobileprovision', '.cer', '.crt',
    '.mp4', '.mov', '.m4v', '.webm', '.mp3', '.aac', '.m4a', '.caf', '.aiff', '.aif', '.flac',
    '.zip', '.tar', '.gz', '.dmg', '.ipa', '.app', '.xcresult', '.xcuserstate',
    '.tmp', '.swp', '.swo', '.bak', '.orig', '.rej',
}
SOURCE_SUFFIXES = {'.py', '.swift', '.js', '.ts', '.mjs', '.md', '.txt', '.html', '.css',
                   '.sh', '.command', '.plist', '.json', '.yml', '.yaml', '.xml', '.pbxproj', '.xcscheme'}
SECRET_PATTERNS = (
    re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----'),
    re.compile(rb'AIza[0-9A-Za-z_-]{30,}'),
    re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{25,}'),
    re.compile(rb'hf_[A-Za-z0-9]{30,}'),
)
LINK = re.compile(r'!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+["\'][^\n]*?["\'])?\s*\)')
REFERENCE = re.compile(r'^\s{0,3}\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))', re.MULTILINE)


class PackageError(ValueError):
    pass


def canonical_name(name: str) -> str:
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise PackageError('Archive/source path is not a canonical relative path.')
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise PackageError('Archive/source path contains control characters.')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in path.parts) or str(path) != name:
        raise PackageError('Archive/source path escapes or aliases the package root.')
    return name


def in_scope(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return name in ROOT_FILES or (len(parts) == 1 and name.endswith('.command')) or (len(parts) > 1 and parts[0] in CANONICAL)


def excluded_reason(name: str) -> str | None:
    path = PurePosixPath(name)
    lower = tuple(p.lower() for p in path.parts)
    if any(p in EXCLUDED_DIRS or p.startswith(('.venv', 'build')) for p in lower[:-1]):
        return 'local build/cache/capture data'
    if name.startswith('ChestBPM/ML/results/') or name.startswith('care-assistant/finetuning/kaggle/cli-run/'):
        return 'local generated output'
    if any(p.startswith('.') and p not in ('.gitignore', '.env.example') for p in path.parts):
        return 'local configuration or hidden metadata'
    if path.name.startswith('.env') and path.name != '.env.example':
        return 'credential configuration'
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return 'credential, capture, model weight, archive or generated binary'
    if path.suffix.lower() == '.wav' and name not in {f'{d}/{n}.wav' for d in SAMPLE_DIRS for n in SAMPLE_NAMES}:
        return 'unapproved audio capture'
    if path.suffix.lower() in ('.bin', '.mlmodel') and name not in {f'{d}/{p}' for d in MODEL_ROOTS for p in MODEL_PARTS}:
        return 'unapproved model weight'
    if path.suffix.lower() not in SOURCE_SUFFIXES and re.search(r'(?:^|[._-])(?:credentials?|secrets?|tokens?|profiles?)(?:[._-]|$)', path.name, re.I):
        return 'private credentials or profile'
    if path.suffix.lower() == '.json' and re.search(r'(?:^|[._-])(?:credentials?|secrets?|tokens?|profiles?|pairing)(?:[._-]|$)', path.name, re.I):
        return 'private credentials or profile'
    return None


def check_path(name: str):
    canonical_name(name)
    if not in_scope(name):
        raise PackageError('Archive contains a file outside the canonical source scope.')
    if excluded_reason(name):
        raise PackageError('Archive contains an excluded credential/capture/cache/model path.')


def source_bytes(root: Path, name: str) -> tuple[bytes, int]:
    current = root
    for part in PurePosixPath(name).parts:
        current /= part
        if current.is_symlink():
            raise PackageError('Symlinks cannot enter a submission package.')
    if not current.resolve().is_relative_to(root):
        raise PackageError('A source path escaped the repository root.')
    info = current.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
        raise PackageError('A source entry is not a regular, bounded file.')
    with current.open('rb') as handle:
        data = handle.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise PackageError('A source entry exceeded the file size limit.')
    return data, 0o755 if info.st_mode & 0o111 else 0o644


def inspect_public_text(name: str, data: bytes):
    if PurePosixPath(name).suffix.lower() in SOURCE_SUFFIXES or name.endswith('.env.example'):
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise PackageError('Possible credential material in source; matched values are not printed.')
    if name.endswith('.env.example'):
        for line in data.decode('utf-8').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip().strip('\'"')
            if re.search(r'(?:KEY|TOKEN|SECRET|PASSWORD)$', key.strip(), re.I) and value:
                if not re.match(r'(?i)(?:your[_ -]|replace|change|choose|insert|paste|example|placeholder|synthetic|dummy|demo|test|none|\$\{)', value):
                    raise PackageError('Example configuration contains a non-placeholder credential value.')


def git_snapshot(root: Path):
    try:
        top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, check=True).stdout.decode().strip()
        if Path(top).resolve() != root:
            raise subprocess.CalledProcessError(1, ['git'])
        scopes = [*CANONICAL, *sorted(ROOT_FILES), ':(glob)*.command']
        listed = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', *scopes], capture_output=True, check=True).stdout
        names = sorted({p.decode('utf-8') for p in listed.split(b'\0') if p})
        # --no-index also respects ignore rules for files once tracked by mistake.
        ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index', '-z', '--stdin'], input=b'\0'.join(n.encode() for n in names) + b'\0', capture_output=True)
        if ignored.returncode not in (0, 1):
            raise PackageError('Git could not evaluate submission ignore rules.')
        excluded = {p.decode('utf-8') for p in ignored.stdout.split(b'\0') if p}
        commit = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'], capture_output=True)
        base_commit = commit.stdout.decode().strip() if commit.returncode == 0 else None
        return [n for n in names if n not in excluded], base_commit, None
    except (OSError, subprocess.CalledProcessError):
        path = root / MANIFEST
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_MANIFEST:
            raise PackageError('Building needs a Git checkout or an extracted source-manifest.json. --verify works without Git.')
        manifest = json.loads(path.read_text())
        validate_manifest(manifest)
        # Rebuild the known public source set, including current edits. Do not
        # start collecting unrelated new local files in a non-Git extraction.
        for name, entry in manifest['files'].items():
            if name.endswith('.gitignore') and hashlib.sha256(source_bytes(root, name)[0]).hexdigest() != entry['sha256']:
                raise PackageError('Ignore rules changed. Rebuild in a Git checkout; --verify still works without Git.')
        return sorted(manifest['files']), manifest['base_commit'], manifest


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'format_version', 'project', 'base_commit', 'source_state', 'files', 'links'}:
        raise PackageError('Invalid source manifest fields.')
    if type(manifest['format_version']) is not int or manifest['format_version'] != FORMAT_VERSION or manifest['project'] != 'Heart Echo' or manifest['source_state'] != 'working_tree_snapshot':
        raise PackageError('Unsupported source manifest version/type.')
    if manifest['base_commit'] is not None and (not isinstance(manifest['base_commit'], str) or not re.fullmatch(r'[0-9a-f]{40,64}', manifest['base_commit'])):
        raise PackageError('Invalid source commit metadata.')
    entries = manifest['files']
    if not isinstance(entries, dict) or not entries or len(entries) > 5000:
        raise PackageError('Invalid manifest file list.')
    for name, entry in entries.items():
        check_path(name)
        if not isinstance(entry, dict) or set(entry) != {'sha256', 'bytes', 'mode'}:
            raise PackageError('Invalid per-file source metadata.')
        if not isinstance(entry['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
            raise PackageError('Invalid source file fingerprint.')
        if type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= MAX_FILE or entry['mode'] not in (0o644, 0o755):
            raise PackageError('Invalid source file size/mode.')
    if not isinstance(manifest['links'], dict):
        raise PackageError('Invalid relative-link metadata.')


def check_required(blobs, modes):
    if not REQUIRED <= blobs.keys():
        raise PackageError('Required app, launcher, source, model, sample or license files are missing.')
    for name in blobs:
        if name.endswith('.command') and modes[name] != 0o755:
            raise PackageError('A packaged Mac launcher is not executable.')
    for directory in SAMPLE_DIRS:
        try:
            samples = json.loads(blobs[f'{directory}/sources.json'])['samples']
            expected = {r['name']:r['bundled_sha256'] for r in samples}
        except (ValueError, TypeError, KeyError):
            raise PackageError('Public sample provenance is invalid.') from None
        for name in SAMPLE_NAMES:
            if expected.get(name) != hashlib.sha256(blobs[f'{directory}/{name}.wav']).hexdigest():
                raise PackageError('Bundled public audio does not match its declared provenance.')


def check_links(blobs):
    checked = 0
    omitted = set()
    for name, data in blobs.items():
        if not name.lower().endswith('.md'):
            continue
        text = data.decode('utf-8')
        # Examples inside code fences are instructions, not rendered links.
        text = re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1\s*$', '', text)
        for match in [*LINK.finditer(text), *REFERENCE.finditer(text)]:
            target = match.group(1) or match.group(2)
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = unquote(parsed.path)
            if path.startswith('/'):
                omitted.add((name, 'absolute-local-reference'))
                continue
            relative = posixpath.normpath(posixpath.join(str(PurePosixPath(name).parent), path))
            if relative == '.':
                checked += 1
                continue
            canonical_name(relative)
            if relative in blobs or any(p.startswith(relative.rstrip('/') + '/') for p in blobs):
                checked += 1
                continue
            folded = relative.casefold()
            if any(p.casefold() == folded or p.casefold().startswith(folded.rstrip('/') + '/') for p in blobs):
                raise PackageError(f'Case-sensitive relative source link mismatch in {name}; use the packaged capitalization.')
            if excluded_reason(relative):
                omitted.add((name, 'excluded-local-artifact'))
                continue
            raise PackageError(f'Broken relative source link in {name}.')
    return {'checked': checked, 'omitted_local_artifact_references': [list(p) for p in sorted(omitted)]}


def collect_source(root: Path):
    names, commit, embedded = git_snapshot(root)
    blobs, modes = {}, {}
    for name in names:
        canonical_name(name)
        if not in_scope(name) or excluded_reason(name):
            continue
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue  # A tracked deletion is part of the current worktree.
        check_path(name)
        data, mode = source_bytes(root, name)
        inspect_public_text(name, data)
        blobs[name] = data
        modes[name] = embedded['files'][name]['mode'] if embedded else mode
    if sum(map(len, blobs.values())) > MAX_TOTAL:
        raise PackageError('Submission source exceeded the total size limit.')
    check_required(blobs, modes)
    links = check_links(blobs)
    manifest = {
        'format_version': FORMAT_VERSION, 'project': 'Heart Echo', 'base_commit': commit,
        'source_state': 'working_tree_snapshot',
        'files': {name:{'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data), 'mode':modes[name]}
                  for name,data in sorted(blobs.items())},
        'links': links,
    }
    return blobs, modes, manifest


def verify_package(path: Path):
    if path.suffix.lower() != '.zip' or path.is_symlink():
        raise PackageError('Verification requires a regular ZIP file.')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or len(names) != len({n.casefold() for n in names}):
                raise PackageError('Duplicate or case-colliding archive paths.')
            for entry in entries:
                canonical_name(entry.filename)
                if entry.is_dir() or not stat.S_ISREG(entry.external_attr >> 16):
                    raise PackageError('Only regular archive files are permitted; no directories or symlinks.')
                if entry.file_size > (MAX_MANIFEST if entry.filename == MANIFEST else MAX_FILE):
                    raise PackageError('An archive entry exceeded its size limit.')
            if sum(entry.file_size for entry in entries) > MAX_TOTAL + MAX_MANIFEST:
                raise PackageError('Archive exceeded the total size limit.')
            if names.count(MANIFEST) != 1:
                raise PackageError('Archive needs one source-manifest.json.')
            manifest = json.loads(archive.read(MANIFEST))
            validate_manifest(manifest)
            if set(names) != set(manifest['files']) | {MANIFEST}:
                raise PackageError('Archive entries differ from the source manifest.')
            blobs, modes = {}, {}
            for name, entry in manifest['files'].items():
                check_path(name)
                info = archive.getinfo(name)
                mode = (info.external_attr >> 16) & 0o7777
                if mode != entry['mode']:
                    raise PackageError('Archive file permissions differ from the manifest.')
                data = archive.read(name)
                if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                    raise PackageError('Archive source fingerprint mismatch.')
                inspect_public_text(name, data)
                blobs[name], modes[name] = data, mode
            if archive.testzip() is not None:
                raise PackageError('Archive CRC verification failed.')
            check_required(blobs, modes)
            if check_links(blobs) != manifest['links']:
                raise PackageError('Relative-link verification differs from the manifest.')
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeError, OSError) as error:
        raise PackageError('Archive could not be read or failed integrity verification.') from error
    return {'status':'verified', 'files':len(blobs), 'source_bytes':sum(map(len, blobs.values())),
            'base_commit':manifest['base_commit'], 'relative_links_checked':manifest['links']['checked'],
            'omitted_local_artifact_references':len(manifest['links']['omitted_local_artifact_references'])}


def build_package(root: Path, output: Path):
    root = root.resolve()
    output = output.parent.resolve() / output.name
    if output.suffix.lower() != '.zip' or os.path.lexists(output):
        raise PackageError('Choose a new .zip output path; existing files are never overwritten.')
    if not output.parent.is_dir():
        raise PackageError('The output parent must be an existing regular directory.')
    blobs, modes, manifest = collect_source(root)
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    if len(manifest_data) > MAX_MANIFEST:
        raise PackageError('Source manifest exceeded its size limit.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.heartecho-source-', suffix='.zip', dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted({**blobs, MANIFEST:manifest_data}.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | modes.get(name, 0o644)) << 16
                archive.writestr(info, data, compresslevel=9)
        report = verify_package(temporary)
        # Same-directory hard linking atomically refuses a racing existing output.
        os.link(temporary, output)
        output.chmod(0o644)
        return dict(report, archive_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), archive_bytes=output.stat().st_size)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path, help='Create a new source ZIP; refuses overwrite.')
    mode.add_argument('--verify', type=Path, help='Verify an existing ZIP; no Git or extraction is required.')
    parser.add_argument('--root', type=Path, default=ROOT, help='Source root (defaults to this tool\'s repository).')
    args = parser.parse_args()
    try:
        report = verify_package(args.verify) if args.verify else build_package(args.root, args.output)
    except PackageError as error:
        parser.exit(1, f'Package refused: {error}\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
