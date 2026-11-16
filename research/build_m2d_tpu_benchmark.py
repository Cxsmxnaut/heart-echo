"""Build a private M2D TPU speed probe with no audio or clinical metadata."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

HERE=Path(__file__).resolve().parent


def main(args):
    output=args.output
    if output.exists():
        raise ValueError('Preserve benchmark submissions')
    blobs={name:(HERE/name).read_bytes() for name in ['m2d_murmur.py','benchmark_m2d_tpu.py']}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in blobs.items()}
    encoded={name:base64.b64encode(zlib.compress(data)).decode() for name,data in blobs.items()}
    backend_install=('subprocess.run([sys.executable,"-m","pip","install","torch==2.11.0",'
        '"torch_tpu==0.3.0","libtpu==0.0.53",'
        '"--extra-index-url","https://download.pytorch.org/whl/cpu"],check=True,timeout=remaining_time())\n') if args.install_tpu_backend else ''
    if args.legacy_xla:
        backend_install=('subprocess.run([sys.executable,"-m","pip","uninstall","-y","torch_tpu"],'
            'check=False,timeout=remaining_time())\n'
            'subprocess.run([sys.executable,"-m","pip","install",'
            '"torch==2.9.0+cpu","torchvision==0.24.0+cpu","torch_xla==2.9.0","libtpu==0.0.21.1",'
            '"--extra-index-url","https://download.pytorch.org/whl/cpu"],check=True,timeout=remaining_time())\n'
            'import os\nos.environ["PJRT_DEVICE"]="TPU"\n')
    deadline=args.deadline_epoch
    timer=('def remaining_time():\n'
           ' remaining='+str(deadline)+'-time.time()\n'
           ' if remaining<=0: raise TimeoutError("Bounded TPU setup window ended")\n'
           ' return max(1,int(remaining))\n') if deadline else 'def remaining_time(): return 1800\n'
    probe=('import importlib.util,os,glob\n'
           'hardware={"stage":"environment_probe","python":sys.version.split()[0],'
           '"tpu_vm_image":os.environ.get("ISTPUVM")=="1",'
           '"visible_accel_devices":len(glob.glob("/dev/accel*")), '
           '"visible_vfio_devices":len(glob.glob("/dev/vfio/[0-9]*")), '
           '"preinstalled_backends":[m for m in ["torch_xla","torch_tpu"] if importlib.util.find_spec(m)]}\n'
           'print(hardware,flush=True)\n'
           'pathlib.Path("/kaggle/working/tpu-environment-probe.json").write_text(__import__("json").dumps(hardware,indent=2))\n'
           'if not hardware["preinstalled_backends"] and not hardware["visible_accel_devices"] and not hardware["visible_vfio_devices"]:\n'
           ' raise RuntimeError("No visible TPU hardware or preinstalled backend; stop before installing packages")\n') if args.preinstalled_only else ''
    code=('import pathlib,subprocess,sys,base64,zlib,hashlib,time\n'+timer+probe+backend_install+
          'subprocess.run([sys.executable,"-m","pip","install","--no-deps",'
          '"timm==1.0.22","einops==0.8.1","nnAudio==0.3.3"],check=True,timeout=remaining_time())\n'
          'src=pathlib.Path("/kaggle/working/source");src.mkdir(exist_ok=False)\n'
          'blobs='+repr(encoded)+'\nexpected='+repr(hashes)+'\n'
          'for name,encoded in blobs.items():\n'
          ' data=zlib.decompress(base64.b64decode(encoded))\n'
          ' assert hashlib.sha256(data).hexdigest()==expected[name]\n'
          ' (src/name).write_bytes(data)\n'
          'subprocess.run([sys.executable,"-u",str(src/"benchmark_m2d_tpu.py")],check=True,'
          'timeout=remaining_time())\n')
    notebook=dict(nbformat=4,nbformat_minor=5,
        metadata={'kernelspec':{'display_name':'Python3','language':'python','name':'python3'}},
        cells=[dict(cell_type='markdown',metadata={},source=['# Private synthetic M2D TPU speed probe\n',
              'No audio, patient metadata, private profile, clinical score or exported model.\n']),
               dict(cell_type='code',execution_count=None,metadata={},outputs=[],source=code.splitlines(keepends=True))])
    metadata=dict(id=args.kernel_id,title=args.title,
        code_file='m2d-tpu-speed.ipynb',language='python',kernel_type='notebook',is_private=True,
        enable_gpu=False,enable_tpu=True,enable_internet=True,dataset_sources=[],competition_sources=[],
        kernel_sources=[],model_sources=[],machine_shape='TpuV5E8',docker_image_pinning_type='latest')
    output.mkdir(parents=True)
    (output/'m2d-tpu-speed.ipynb').write_text(json.dumps(notebook,indent=1)+'\n')
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (output/'upload-audit.json').write_text(json.dumps(dict(files_sha256=hashes,
        synthetic_only=True,audio_uploaded=False,patient_metadata_uploaded=False,model_exported=False),indent=2)+'\n')
    print(json.dumps(dict(output=str(output),synthetic_only=True,files=list(blobs))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'generated/murmur-v11-m2d/tpu-benchmark')
    parser.add_argument('--install-tpu-backend',action='store_true')
    parser.add_argument('--deadline-epoch',type=int)
    parser.add_argument('--legacy-xla',action='store_true')
    parser.add_argument('--preinstalled-only',action='store_true',
                        help='Fail fast if the allocated image exposes neither TPU devices nor a backend')
    parser.add_argument('--kernel-id',default='bhavithlolakapuri/heart-echo-m2d-tpu-speed')
    parser.add_argument('--title',default='Heart Echo M2D TPU Speed')
    main(parser.parse_args())
