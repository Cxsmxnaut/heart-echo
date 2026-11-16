"""Build the private public-only learned-attention experiment with source hashes."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
FILES = [
    'm2d_murmur.py', 'm2d_attention.py', 'train_m2d_murmur.py',
    'train_m2d_native_heads.py', 'train_m2d_preserving.py',
    'murmur_focus_metrics.py', 'train_m2d_attention.py',
]


def build(output, bundle):
    if output.exists():
        raise ValueError('Preserve submitted sources')
    audit = json.loads((bundle / 'bundle-audit.json').read_text())
    assert audit['status'] == 'bundle_verified' and audit['records'] == 2536
    assert all(audit[k] is False for k in ['private_audio_included', 'private_profile_included', 'calibration_or_test_included'])
    archive = '39a0b6e5f686a3af946887446ef5a6d5c7fe8c755294980a7dafc1d38674f855'
    base = 'e89b4a8bff063b3fed7702666f691e606737c297f14a156dae25da3624097b4e'
    blobs = {n:(HERE / n).read_bytes() for n in FILES}
    for name, data in blobs.items():
        ast.parse(data, filename=name)
    hashes = {n:hashlib.sha256(b).hexdigest() for n,b in blobs.items()}
    encoded = {n:base64.b64encode(zlib.compress(b)).decode() for n,b in blobs.items()}
    code = ('import pathlib,subprocess,sys,torch,base64,zlib,hashlib\n'
        'assert torch.cuda.is_available(),"CUDA GPU required"\n'
        'subprocess.run([sys.executable,"-m","pip","install","--no-deps",'
        '"timm==1.0.22","einops==0.8.1","nnAudio==0.3.3"],check=True)\n'
        'def sha(p):\n'
        ' h=hashlib.sha256()\n'
        ' with p.open("rb") as f:\n'
        '  while b:=f.read(1024*1024):h.update(b)\n'
        ' return h.hexdigest()\n'
        'inp=pathlib.Path("/kaggle/input")\n'
        'bundles=[p for p in inp.rglob("public-native.zip") if sha(p)==' + repr(audit['zip_sha256']) + ']\n'
        'if not bundles:bundles=[p.parent for p in inp.rglob("public-config.json") if sha(p)==' + repr(audit['public_config_sha256']) + ']\n'
        'assert len(bundles)==1,"Expected verified public native input"\n'
        'weights=[p for p in inp.rglob("heart-m2d-stage.zip") if sha(p)==' + repr(archive) + ']\n'
        'if not weights:weights=[p for p in inp.rglob("M2D.pt") if sha(p)==' + repr(base) + ']\n'
        'assert len(weights)==1,"Expected verified frozen V11 initializer"\n'
        'root=pathlib.Path("/kaggle/working/heart-m2d-attention-run");root.mkdir(exist_ok=False)\n'
        'src=root/"source";src.mkdir()\nblobs=' + repr(encoded) + '\nexpected=' + repr(hashes) + '\n'
        'for name,value in blobs.items():\n'
        ' data=zlib.decompress(base64.b64decode(value));assert hashlib.sha256(data).hexdigest()==expected[name]\n'
        ' (src/name).write_bytes(data)\n'
        'subprocess.run([sys.executable,"-u",str(src/"train_m2d_attention.py"),'
        '"--bundle",str(bundles[0]),"--checkpoint",str(weights[0]),'
        '"--config-sha",' + repr(audit['public_config_sha256']) + ',"--bundle-sha",' + repr(audit['zip_sha256']) + ','
        '"--output",str(root/"artifacts"),"--cache","/kaggle/temp/m2d-attention-cache"],check=True)\n')
    ast.parse(code)
    notebook = dict(nbformat=4, nbformat_minor=5,
        metadata={'kernelspec':{'display_name':'Python3', 'language':'python', 'name':'python3'}},
        cells=[dict(id='scope', cell_type='markdown', metadata={}, source=[
            '# Private M2D learned attention experiment\n',
            'Matched mean/attention heads; same frozen encoder, normalization, data, loss and batches.\n',
            'Public training/selection only. No personal audio/profile, calibration/test, or app update.\n']),
            dict(id='run', cell_type='code', execution_count=None, metadata={}, outputs=[],
                 source=code.splitlines(keepends=True))])
    metadata = dict(id='bhavithlolakapuri/heart-echo-m2d-attention-v15',
        title='Heart Echo M2D Attention V15', code_file='m2d-attention.ipynb',
        language='python', kernel_type='notebook', is_private=True, enable_gpu=True,
        enable_internet=True, dataset_sources=['bhavithlolakapuri/heart-echo-native-public-v12'],
        kernel_sources=['bhavithlolakapuri/heart-echo-m2d-released-v11'],
        competition_sources=[], model_sources=[])
    output.mkdir(parents=True)
    path = output / 'm2d-attention.ipynb'
    path.write_text(json.dumps(notebook, indent=1) + '\n')
    (output / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    report = dict(files_sha256=hashes, notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        base_checkpoint_sha256=base, base_archive_sha256=archive,
        bundle_sha256=audit['zip_sha256'], config_sha256=audit['public_config_sha256'],
        private_audio_included=False, private_profile_included=False, calibration_or_test_included=False)
    (output / 'upload-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(output=str(output), public_audio_only=True, source_files=FILES)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--bundle-directory', type=Path, required=True)
    a = p.parse_args()
    build(a.output, a.bundle_directory)
