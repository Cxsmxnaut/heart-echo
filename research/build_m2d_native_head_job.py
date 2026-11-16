"""Build one private V12 GPU job from an explicit source/input allowlist."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

HERE=Path(__file__).resolve().parent
FILES=['m2d_murmur.py','train_m2d_murmur.py','murmur_focus_metrics.py','train_m2d_native_heads.py']


def build(output,bundle_directory):
    if output.exists():raise ValueError('Preserve existing notebook submissions')
    audit=json.loads((bundle_directory/'bundle-audit.json').read_text())
    assert audit['status']=='bundle_verified' and audit['training']==2356 and audit['selection']==180
    assert not any(audit[k] for k in ['private_audio_included','private_profile_included','calibration_or_test_included'])
    archive_sha='39a0b6e5f686a3af946887446ef5a6d5c7fe8c755294980a7dafc1d38674f855'
    blobs={name:(HERE/name).read_bytes() for name in FILES}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in blobs.items()}
    encoded={name:base64.b64encode(zlib.compress(data)).decode() for name,data in blobs.items()}
    code=('import pathlib,subprocess,sys,torch,base64,zlib,hashlib\n'
          'assert torch.cuda.is_available(),"CUDA GPU required"\n'
          'subprocess.run([sys.executable,"-m","pip","install","--no-deps",'
          '"timm==1.0.22","einops==0.8.1","nnAudio==0.3.3"],check=True)\n'
          'def sha(path):\n'
          ' h=hashlib.sha256()\n'
          ' with path.open("rb") as f:\n'
          '  while block:=f.read(1024*1024):h.update(block)\n'
          ' return h.hexdigest()\n'
          'inp=pathlib.Path("/kaggle/input")\n'
          'bundles=[p for p in inp.rglob("public-native.zip") if sha(p)=='+repr(audit['zip_sha256'])+']\n'
          'if not bundles:\n'
          ' bundles=[p.parent for p in inp.rglob("public-config.json") if sha(p)=='+repr(audit['public_config_sha256'])+']\n'
          'assert len(bundles)==1,"Expected exactly the verified public native input"\n'
          'weights=[p for p in inp.rglob("heart-m2d-stage.zip") if sha(p)=='+repr(archive_sha)+']\n'
          'if not weights:\n'
          ' weights=[p for p in inp.rglob("M2D.pt") if sha(p)=="e89b4a8bff063b3fed7702666f691e606737c297f14a156dae25da3624097b4e"]\n'
          'assert len(weights)==1,"Expected exactly the verified V11 encoder artifact"\n'
          'root=pathlib.Path("/kaggle/working/heart-m2d-native-head-run");root.mkdir(exist_ok=False)\n'
          'src=root/"source";src.mkdir()\n'
          'blobs='+repr(encoded)+'\nexpected='+repr(hashes)+'\n'
          'for name,value in blobs.items():\n'
          ' data=zlib.decompress(base64.b64decode(value))\n'
          ' assert hashlib.sha256(data).hexdigest()==expected[name]\n'
          ' (src/name).write_bytes(data)\n'
          'subprocess.run([sys.executable,"-u",str(src/"train_m2d_native_heads.py"),'
          '"--bundle",str(bundles[0]),"--checkpoint-archive",str(weights[0]),'
          '"--config-sha",'+repr(audit['public_config_sha256'])+','
          '"--bundle-sha",'+repr(audit['zip_sha256'])+','
          '"--output",str(root/"artifacts"),"--cache","/kaggle/temp/m2d-native-head-cache"],check=True)\n')
    notebook=dict(nbformat=4,nbformat_minor=5,metadata={'kernelspec':{'display_name':'Python3','language':'python','name':'python3'}},
        cells=[dict(id='scope',cell_type='markdown',metadata={},source=[
            '# Private M2D native decision-head refinement\n',
            'Exact public native audio only. Frozen V11 encoder. Training/selection people separated.\n',
            'No private recording/profile, calibration/test data, app update or phone-accuracy claim.\n']),
            dict(id='train',cell_type='code',execution_count=None,metadata={},outputs=[],source=code.splitlines(keepends=True))])
    metadata=dict(id='bhavithlolakapuri/heart-echo-m2d-native-head-v12',title='Heart Echo M2D Native Head V12',
        code_file='m2d-native-head.ipynb',language='python',kernel_type='notebook',is_private=True,
        enable_gpu=True,enable_internet=True,
        dataset_sources=['bhavithlolakapuri/heart-echo-native-public-v12'],
        kernel_sources=['bhavithlolakapuri/heart-echo-m2d-released-v11'],competition_sources=[],model_sources=[])
    output.mkdir(parents=True)
    path=output/'m2d-native-head.ipynb';path.write_text(json.dumps(notebook,indent=1)+'\n')
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    result=dict(files_sha256=hashes,notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        public_native_zip_sha256=audit['zip_sha256'],public_config_sha256=audit['public_config_sha256'],
        base_artifact_archive_sha256=archive_sha,private_audio_included=False,private_profile_included=False,
        calibration_or_test_included=False,source_builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'upload-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(output),public_audio_only=True,source_files=FILES)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--bundle-directory',type=Path,required=True)
    a=p.parse_args();build(a.output,a.bundle_directory)
