"""Authorized temporary sequential benchmark. Stops only verified care model,
loads ONE base model at a time, and restores original serving model in finally.
No .env/default/source changes. No retraining or tuning on test scores.
"""
from pathlib import Path
import datetime,json,os,signal,socket,subprocess,time,urllib.request,shutil
APP=Path(__file__).resolve().parents[2];FT=APP/'finetuning';os.chdir(APP)
RUN=FT/'runs/benchmark-seed001';RUN.mkdir(exist_ok=False)
freeze=json.loads((FT/'config/candidate-seed001-freeze.json').read_text())
BINARY='.cache/runtime/llama-b12248/llama-server';BASE=freeze['gguf_path'];LORA=freeze['gguf_lora_path']
COMMON=[BINARY,'-m',BASE,'--alias','care-gemma4-e4b','--host','127.0.0.1','-c','8192','-np','1','-t','2','-tb','2','--cache-ram','0','--jinja','--reasoning','off','--reasoning-budget','0','--no-webui','--log-disable']
report={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hardware':'Apple M4, arm64 macOS, 16GiB RAM; shared machine','policy':'Exactly one E4B loaded. Same base GGUF/runtime/decoding; LoRA off/on only. Serving baseline restored in finally; no adoption.','stages':[]}
model=None;web=None;restored=None

def save(): (FT/'reports/sequential-benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
def fetch(url):
 with urllib.request.urlopen(url,timeout=5) as r:return json.load(r)
def ready(port,process,limit=90):
 end=time.monotonic()+limit
 while time.monotonic()<end:
  if process.poll() is not None:raise RuntimeError('Model/web process exited before readiness; inspect own log')
  try:
   if fetch(f'http://127.0.0.1:{port}/health').get('status')=='ok':return
  except Exception:pass
  time.sleep(1)
 raise TimeoutError('Model readiness exceeded bound')
def stop(process):
 if process and process.poll() is None:
  process.terminate()
  try:process.wait(timeout=20)
  except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
def stage(name,argv,env=None,timeout=900):
 print('Starting '+name,flush=True);start=time.monotonic()
 with (RUN/(name+'.log')).open('w') as log:p=subprocess.run(argv,cwd=APP,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 report['stages'].append({'name':name,'exit_code':p.returncode,'seconds':round(time.monotonic()-start,3)});save();print('Finished '+name+' exit='+str(p.returncode),flush=True)
 if p.returncode:raise RuntimeError(name+' failed; first failure preserved')
# Validate ownership/ports BEFORE stopping anything.
with socket.socket() as s:assert s.connect_ex(('127.0.0.1',4324))!=0,'Evaluation port is occupied'
pids=subprocess.check_output(['lsof','-nP','-t','-iTCP:4320','-sTCP:LISTEN'],text=True).split();assert len(pids)==1
pid=int(pids[0]);cmd=subprocess.check_output(['/bin/ps','-p',str(pid),'-o','command='],text=True).strip();cwd=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True)
assert 'llama-server' in cmd and 'care-gemma4-e4b' in cmd and BASE in cmd and '--lora' not in cmd and ('n'+str(APP)) in cwd,'Refuse to stop unverified process'
report['previous_model_pid']=pid;save()
try:
 os.kill(pid,signal.SIGTERM)
 for _ in range(30):
  with socket.socket() as s:
   if s.connect_ex(('127.0.0.1',4320))!=0:break
  time.sleep(1)
 else:raise RuntimeError('Original model did not stop')
 for variant in ['control','candidate']:
  argv=COMMON+['--port','4324']+(['--lora',LORA] if variant=='candidate' else [])
  with (RUN/(variant+'-server.log')).open('w') as log:model=subprocess.Popen(argv,cwd=APP,stdout=log,stderr=subprocess.STDOUT)
  ready(4324,model);active=fetch('http://127.0.0.1:4324/lora-adapters');assert len(active)==(1 if variant=='candidate' else 0)
  if variant=='candidate':assert active[0]['scale']==1
  report[variant+'_runtime']={'pid':model.pid,'args':argv,'lora_state':[{'id':x['id'],'path':Path(x['path']).name,'scale':x['scale']} for x in active]};save();print(variant+' ready',flush=True)
  for split in ['validation','test']:
   args=['node','finetuning/scripts/evaluate.mjs','--name=seed001-'+variant+'-'+split,'--split='+split,'--endpoint=http://127.0.0.1:4324/v1','--model=care-gemma4-e4b','--weights-sha256='+freeze['gguf_sha256'],'--candidate-freeze=finetuning/config/candidate-seed001-freeze.json','--fine-tuned='+('true' if variant=='candidate' else 'false')]
   if variant=='candidate':args+=['--lora-sha256='+freeze['gguf_lora_sha256']]
   stage(variant+'-'+split,args)
  stage(variant+'-e2e',['node','finetuning/scripts/e2e-regression.mjs',variant])
  if variant=='candidate':
   ready_file=RUN/'web-ready.json'
   with (RUN/'candidate-web.log').open('w') as log:web=subprocess.Popen(['node','finetuning/scripts/serve-eval.mjs',str(ready_file)],cwd=APP,stdout=log,stderr=subprocess.STDOUT)
   for _ in range(30):
    if ready_file.exists():break
    if web.poll() is not None:raise RuntimeError('Evaluation web process exited')
    time.sleep(1)
   url=json.loads(ready_file.read_text())['url'];work=APP/'.cache/benchmark-seed001';(work/'scripts').mkdir(parents=True);(work/'docs').mkdir();(work/'test-results').mkdir();shutil.copyfile(APP/'scripts/browser-live.js',work/'scripts/browser-live.js')
   env={**os.environ,'CARE_BASE_URL':url};stage('candidate-browser-live',['node',str(work/'scripts/browser-live.js')],env=env,timeout=600)
   shutil.copyfile(work/'docs/browser-live-results.json',FT/'reports/seed001-candidate-browser-live.json');stop(web);web=None
  stop(model);model=None
 report['benchmark_completed']=True
except Exception as e:
 report['benchmark_completed']=False;report['error']=type(e).__name__+': '+str(e);save();print(report['error'],flush=True)
finally:
 stop(web);stop(model)
 # The same baseline base/alias/flags, only normal serving port restored.
 with (RUN/'restored-baseline-server.log').open('w') as log:restored=subprocess.Popen(COMMON+['--port','4320'],cwd=APP,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  ready(4320,restored);assert fetch('http://127.0.0.1:4320/lora-adapters')==[];report['baseline_restored']=True;report['restored_model_pid']=restored.pid;print('Original baseline restored on4320 with no adapter',flush=True)
 except Exception as e:report['baseline_restored']=False;report['restore_error']=str(e);print('RESTORE NEEDS ATTENTION: '+str(e),flush=True)
 report['ended_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
