"""Allowlisted public-only Kaggle notebook; private phone data never enters it."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
FILES = ['two_stage_models.py', 'train_public_backbones.py', 'murmur_focus_metrics.py']


def build(output):
    if output.exists():
        raise ValueError('Preserve existing submitted notebooks; use a fresh output directory')
    output.mkdir(parents=True)
    manifest = HERE.parent / 'ChestBPM/ML/murmur-phase-manifest.json'
    keys = ['record', 'group', 'patient_target', 'target', 'role', 'file', 'sha256']
    rows = [{k: r[k] for k in keys} for r in json.loads(manifest.read_text())['records']
            if r['role'] in ['training', 'selection']]
    assert len(rows) == 2536
    roles = {}
    for row in rows:
        assert roles.setdefault(row['group'], row['role']) == row['role']
    config = dict(public_only=True, private_audio_included=False,
                  dataset='CirCor DigiScope 1.0.3', dataset_url='https://physionet.org/content/circor-heart-sound/1.0.3/',
                  source_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), records=rows)
    blobs = {name: (HERE / name).read_bytes() for name in FILES}
    blobs['public-config.json'] = json.dumps(config, separators=(',', ':')).encode()
    for name in ['PANNs-LICENSE.MIT', 'TorchVision-LICENSE.BSD']:
        blobs[name] = (HERE / 'third_party' / name).read_bytes()
    encoded = {name: base64.b64encode(zlib.compress(value)).decode() for name, value in blobs.items()}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in blobs.items()}
    source = ('import base64, zlib, hashlib, pathlib, subprocess, sys, torch\n'
              'assert torch.cuda.is_available(), "A CUDA GPU is required; do not silently train on CPU"\n'
              'root=pathlib.Path("/kaggle/working/heart-public-run")\n'
              'root.mkdir(exist_ok=False)\n'
              'src=root/"source";src.mkdir()\n'
              'blobs=' + repr(encoded) + '\n'
              'expected=' + repr(hashes) + '\n'
              'for name, encoded in blobs.items():\n'
              ' data=zlib.decompress(base64.b64decode(encoded))\n'
              ' assert hashlib.sha256(data).hexdigest()==expected[name]\n'
              ' (src/name).write_bytes(data)\n'
              'print({"gpu":torch.cuda.get_device_name(0),"public_only":True,"private_audio_uploaded":False},flush=True)\n'
              'subprocess.run([sys.executable,"-u",str(src/"train_public_backbones.py"),'
              '"--config",str(src/"public-config.json"),"--output",str(root/"artifacts"),'
              '"--epochs","40","--steps","120"],check=True)\n')
    notebook = {'nbformat': 4, 'nbformat_minor': 5,
                'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}},
                'cells': [{'cell_type': 'markdown', 'metadata': {}, 'source': [
                    '# Heart Echo: public backbone comparison\n',
                    'Private notebook. Only public training/selection data and public pretrained weights.\n',
                    'No private recordings, phone profiles, calibration/test audio or app update.\n']},
                    {'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [],
                     'source': source.splitlines(keepends=True)}]}
    (output / 'heart-public-backbones.ipynb').write_text(json.dumps(notebook, indent=1) + '\n')
    metadata = dict(id='bhavithlolakapuri/heart-echo-public-backbone-comparison',
                    title='Heart Echo Public Backbone Comparison', code_file='heart-public-backbones.ipynb',
                    language='python', kernel_type='notebook', is_private=True,
                    enable_gpu=True, enable_internet=True, dataset_sources=[], competition_sources=[],
                    kernel_sources=[], model_sources=[])
    (output / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    proof = dict(files_sha256=hashes, public_records=len(rows), private_audio_included=False,
                 phone_profile_included=False, calibration_or_test_included=False,
                 notebook_sha256=hashlib.sha256((output / metadata['code_file']).read_bytes()).hexdigest())
    (output / 'upload-audit.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({k: v for k, v in proof.items() if k != 'files_sha256'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
