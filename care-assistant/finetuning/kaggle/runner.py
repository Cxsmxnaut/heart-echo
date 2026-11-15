"""Kaggle-only bootstrap; called by the private self-contained notebook.
No account/API calls or publication. Never reads sealed test data.
"""
import argparse, csv, datetime, hashlib, json, os, platform, shutil, subprocess, sys, time, urllib.request, venv, zipfile
from pathlib import Path
GIB=1024**3
APP=Path(__file__).resolve().parents[2]
FT=APP/'finetuning'
SCRATCH=Path('/tmp/chest-bpm-e4b-pilot')
ARTIFACTS=FT/'runs'
PYTHON=SCRATCH/'venv/bin/python'
RUN=ARTIFACTS/'kaggle-seed-001'
ENV={**os.environ,'CUDA_VISIBLE_DEVICES':'0','HF_HOME':str(SCRATCH/'hf'),'HF_HUB_CACHE':str(SCRATCH/'hf/hub'),'PIP_CACHE_DIR':str(SCRATCH/'pip-cache'),'WANDB_DISABLED':'true','HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1','TOKENIZERS_PARALLELISM':'false','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'}
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(2**20),b''):h.update(block)
 return h.hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,obj):
 ARTIFACTS.mkdir(parents=True,exist_ok=True);(ARTIFACTS/name).write_text(json.dumps(obj,indent=2)+'\n')
def command(args,name,timeout=1800):
 ARTIFACTS.mkdir(parents=True,exist_ok=True);SCRATCH.mkdir(exist_ok=True)
 print('Running stage:',name,flush=True)
 with (ARTIFACTS/(name+'.log')).open('w') as log:
  result=subprocess.run([str(a) for a in args],cwd=SCRATCH,env=ENV,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 if result.returncode:raise RuntimeError(f'{name} failed (exit {result.returncode}); inspect saved {name}.log. No automatic package/model substitution.')
 print('Finished stage:',name,flush=True)
def package_outputs(status):
 if not Path('/kaggle/working').exists():return None
 save('kaggle-status.json',{'checked_at':now(),'status':status,'heldout_runtime_comparison_completed':False,'default_model_changed':False})
 files=[]
 for p in ARTIFACTS.rglob('*'):
  if p.is_file() and p.suffix not in ['.zip','.gguf'] and 'checkpoints' not in p.parts:files.append(p)
 assert sum(p.stat().st_size for p in files)<2*GIB,'Unexpectedly large output; do not save base weights/caches as notebook output'
 out=Path('/kaggle/working/care-e4b-pilot-artifacts.zip')
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for p in files:z.write(p,p.relative_to(ARTIFACTS))
 print('Saved private output archive:',out,'bytes:',out.stat().st_size,flush=True)
 return out

def preflight():
 assert platform.system()=='Linux' and Path('/kaggle/working').is_dir(),'Run this notebook in Kaggle Linux, not on the Mac'
 assert APP.is_relative_to(Path('/kaggle/working')),'Source/workspace must be under /kaggle/working'
 assert sys.version_info[:2] in [(3,10),(3,11),(3,12),(3,13)],'Review wheel support for this Python version before installing'
 ARTIFACTS.mkdir(parents=True,exist_ok=True);SCRATCH.mkdir(exist_ok=True)
 result=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.total,memory.free,compute_cap,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
 gpus=list(csv.reader(result.stdout.strip().splitlines()));assert gpus,'Enable GPU in Session options'
 first=[s.strip() for s in gpus[0]];index,name,total,free,cap,driver=first
 assert index=='0','Review assigned GPU indices before selecting device'
 assert float(cap)>=7.5,'This pinned CUDA/Triton route needs T4/L4 or newer; P100/TPU are not this recipe'
 assert float(total)>=10*1024 and float(free)>=10*1024,'Need at least 10 GiB free on ONE GPU; two T4 cards do not pool their memory'
 # A conservative driver gate for the explicitly selected CUDA 12.8 wheels.
 assert int(driver.split('.')[0])>=570,'Driver is older than this conservative cu128 recipe gate; stop and review the image, do not silently change pins'
 mem={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
 assert mem['MemAvailable']>=12*GIB,'Need 12 GiB available host RAM for this pilot; export is a separate resource check'
 assert shutil.disk_usage(SCRATCH).free>=25*GIB,'Need 25 GiB scratch free for isolated packages/cache/base weights'
 assert shutil.disk_usage('/kaggle/working').free>=2*GIB,'Need room for adapter and proof outputs'
 pins=json.loads((FT/'config/upstream-pins.json').read_text())['sources']['bnb_model']
 request=urllib.request.Request(pins['url']+'/revision/'+pins['revision'],headers={'User-Agent':'care-assistant-kaggle-preflight'})
 with urllib.request.urlopen(request,timeout=30) as r:metadata=json.load(r)
 assert metadata['sha']==pins['revision'],'Pinned public model metadata moved unexpectedly'
 report={'checked_at':now(),'status':'passed_before_install_NOT_TRAINED','python':platform.python_version(),'system':platform.platform(),'selected_gpu':{'index':0,'name':name,'total_MiB':float(total),'free_MiB':float(free),'compute_capability':cap,'driver':driver},'assigned_gpu_count':len(gpus),'visible_gpu_count_for_training':1,'host_available_bytes':mem['MemAvailable'],'scratch_free_bytes':shutil.disk_usage(SCRATCH).free,'working_free_bytes':shutil.disk_usage('/kaggle/working').free,'internet_public_metadata_check':True,'model_revision':pins['revision'],'cache_policy':'All large packages/model caches in /tmp, not saved outputs','privacy_note':'Notebook must remain private in UI; runtime cannot prove UI sharing settings'}
 save('kaggle-preflight.json',report);print(json.dumps(report,indent=2))

def setup():
 assert json.loads((ARTIFACTS/'kaggle-preflight.json').read_text())['status'].startswith('passed_')
 from bootstrap_env import ensure_environment
 ensure_environment(SCRATCH, ARTIFACTS, json.loads((FT/'config/bootstrap-pins.json').read_text()), ENV)
 # Isolated venv avoids changing Kaggle's shared preinstalled environment.
 command([PYTHON,'-m','pip','install','--no-cache-dir','torch==2.11.0','torchvision==0.26.0','--index-url','https://download.pytorch.org/whl/cu128'],'01-cuda-packages')
 command([PYTHON,'-m','pip','install','--no-cache-dir','--report',ARTIFACTS/'pip-install-report.json','-r',FT/'requirements.candidate.txt'],'02-training-packages')
 command([PYTHON,'-m','pip','check'],'03-pip-check')
 smoke="""from unsloth import FastModel
import torch
import transformers, trl, bitsandbytes
assert torch.cuda.is_available() and torch.cuda.device_count()==1
assert torch.cuda.get_device_capability(0)>=(7,5)
a=torch.ones((16,16),device='cuda'); assert torch.isfinite(a@a).all().item()
assert hasattr(FastModel,'get_peft_model')
print('CUDA/import smoke passed; no model weights loaded by this check')
"""
 command([PYTHON,'-c',smoke],'04-cuda-imports')
 command([PYTHON,FT/'scripts/lock-environment.py','--compute-route','kaggle-nvidia','--output',ARTIFACTS/'kaggle-environment.json'],'05-lock-environment')
 assert shutil.disk_usage(SCRATCH).free>=12*GIB,'Insufficient scratch left for model download; no training started'
 save('kaggle-setup.json',{'checked_at':now(),'status':'environment_resolved_NOT_TRAINED','environment_lock':'kaggle-environment.json','training_code_sha256':sha(FT/'scripts/train.py')})
 package_outputs('environment_ready_training_not_started')

def train():
 assert json.loads((ARTIFACTS/'kaggle-setup.json').read_text())['status']=='environment_resolved_NOT_TRAINED'
 assert not RUN.exists(),'Run directory already exists. Do not train again to save outputs; use the package stage/Quick Save.'
 command([PYTHON,FT/'scripts/train.py','--execute','--compute-route','kaggle-nvidia','--environment-lock',ARTIFACTS/'kaggle-environment.json','--run-id','kaggle-seed-001'],'06-train',timeout=2400)
 proof=json.loads((RUN/'training-complete.json').read_text());assert proof['global_steps']>0 and proof['changed_trainable_tensors']>0
 assert proof['adapter_sha256']==sha(RUN/'adapter/adapter_model.safetensors')
 assert proof['test_loaded'] is False and proof['export_executed'] is False
 package_outputs('adapter_saved_weight_updates_verified_GGUF_and_heldout_eval_PENDING')
 print('Adapter and change proof saved. No claim of held-out improvement or working GGUF export. Keep baseline enabled.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['preflight','setup','train','package']);a=p.parse_args()
 try:
  {'preflight':preflight,'setup':setup,'train':train,'package':lambda:package_outputs('manual_package_inspect_training_proof_for_status')}[a.stage]()
 except Exception as e:
  save('kaggle-failure.json',{'checked_at':now(),'stage':a.stage,'error':type(e).__name__+': '+str(e),'training_success_claimed':False})
  package_outputs('failed_'+a.stage+'_inspect_logs_NO_SUCCESS_CLAIM')
  raise
