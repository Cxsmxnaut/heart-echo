"""Build a private, public-data-only M2D research notebook from an allowlist."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

HERE=Path(__file__).resolve().parent
FILES=['m2d_murmur.py','train_m2d_murmur.py','murmur_focus_metrics.py']


def build(output,released=False):
    if output.exists():
        raise ValueError('Preserve submitted notebook sources; choose a fresh output directory')
    manifest=HERE.parent/'ChestBPM/ML/murmur-phase-manifest.json'
    keys=['record','group','patient_target','target','role','file','sha256']
    rows=[{k:r[k] for k in keys} for r in json.loads(manifest.read_text())['records']
          if r['role'] in ['training','selection']]
    if len(rows)!=2536:
        raise ValueError('Unexpected public cohort; review before uploading')
    seen={}
    for r in rows:
        if seen.setdefault(r['group'],r['role'])!=r['role']:
            raise ValueError('Person crosses partitions')
    config=dict(public_only=True,private_audio_included=False,
                dataset='CirCor DigiScope1.0.3',records=rows,
                source_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    names=FILES+(['train_m2d_release.py'] if released else [])
    trainer='train_m2d_release.py' if released else 'train_m2d_murmur.py'
    blobs={name:(HERE/name).read_bytes() for name in names}
    blobs['public-config.json']=json.dumps(config,separators=(',',':')).encode()
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in blobs.items()}
    encoded={name:base64.b64encode(zlib.compress(data)).decode() for name,data in blobs.items()}
    code=('import base64,zlib,hashlib,pathlib,subprocess,sys,torch\n'
          'assert torch.cuda.is_available(),"CUDA GPU required for full M2D training"\n'
          'subprocess.run([sys.executable,"-m","pip","install","--no-deps",'
          '"timm==1.0.22","einops==0.8.1","nnAudio==0.3.3"],check=True)\n'
          'import timm,torchvision,nnAudio\n'
          'print({"gpu":torch.cuda.get_device_name(0),"torch":torch.__version__,"timm":timm.__version__,"private_audio_uploaded":False},flush=True)\n'
          'root=pathlib.Path("/kaggle/working/heart-m2d-run");root.mkdir(exist_ok=False)\n'
          'src=root/"source";src.mkdir()\n'
          'blobs='+repr(encoded)+'\n'
          'expected='+repr(hashes)+'\n'
          'for name,encoded in blobs.items():\n'
          ' data=zlib.decompress(base64.b64decode(encoded))\n'
          ' assert hashlib.sha256(data).hexdigest()==expected[name]\n'
          ' (src/name).write_bytes(data)\n'
          'subprocess.run([sys.executable,"-u",str(src/'+repr(trainer)+'),'
          '"--config",str(src/"public-config.json"),"--output",str(root/"artifacts"),'
          '"--cache","/kaggle/temp/heart-m2d-cache"],check=True)\n')
    notebook=dict(nbformat=4,nbformat_minor=5,
        metadata={'kernelspec':{'display_name':'Python3','language':'python','name':'python3'}},
        cells=[dict(cell_type='markdown',metadata={},source=[
            '# M2D public murmur comparison\n',
            'Private non-commercial internal evaluation. Public training/selection only.\n',
            'No private audio, phone profile, calibration/test recording or app update.\n',
            'NTT runtime/checkpoint fetched unchanged from pinned public sources.\n']),
            dict(cell_type='code',execution_count=None,metadata={},outputs=[],source=code.splitlines(keepends=True))])
    metadata=dict(id='bhavithlolakapuri/'+('heart-echo-m2d-released-v11' if released else 'heart-echo-m2d-murmur-v11'),
        title='Heart Echo M2D Released V11' if released else 'Heart Echo M2D Murmur V11',
        code_file='heart-m2d.ipynb',language='python',kernel_type='notebook',is_private=True,
        enable_gpu=True,enable_internet=True,dataset_sources=[],competition_sources=[],kernel_sources=[],model_sources=[])
    output.mkdir(parents=True)
    (output/'heart-m2d.ipynb').write_text(json.dumps(notebook,indent=1)+'\n')
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    audit=dict(files_sha256=hashes,public_records=len(rows),private_audio_included=False,
        phone_profile_included=False,calibration_or_test_included=False,
        notebook_sha256=hashlib.sha256((output/'heart-m2d.ipynb').read_bytes()).hexdigest())
    (output/'upload-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k!='files_sha256'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--released-recipe',action='store_true')
    args=parser.parse_args()
    build(args.output,args.released_recipe)
