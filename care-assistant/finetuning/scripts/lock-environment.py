"""Run only in the chosen NVIDIA environment AFTER its dependencies resolve.
Reads package/GPU metadata; does not train or download a model.
"""
import argparse, importlib.metadata as md, json, platform, re, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--compute-route',choices=['kaggle-nvidia','colab-nvidia','existing-nvidia'],required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
assert platform.system()=='Linux','NVIDIA/Linux candidate recipe only'
root=Path(__file__).resolve().parents[1]
pins=json.loads((root/'config/upstream-pins.json').read_text())['sources']
check=subprocess.run([sys.executable,'-m','pip','check'],text=True,capture_output=True);assert check.returncode==0,check.stdout+check.stderr
expected=json.loads((root/'config/candidate-package-pins.json').read_text())['packages']
versions={k:md.version(k) for k in expected}
for name, actual in versions.items(): assert actual.split('+')[0]==expected[name]['version'],name+' differs from candidate pin'
for name,key in [('unsloth','unsloth'),('unsloth-zoo','unsloth_zoo')]:
 direct=json.loads(md.distribution(name).read_text('direct_url.json'));assert direct['vcs_info']['commit_id']==pins[key]['revision'],name+' source revision mismatch';versions[name]=md.version(name)
gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
freeze=subprocess.run([sys.executable,'-m','pip','freeze','--all'],capture_output=True,text=True,check=True).stdout
assert not re.search(r'https?://[^/\s]+@|(?:token|password|api_key)=',freeze,re.I),'Review environment for embedded credentials before storing'
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps({'status':'resolved_on_selected_gpu','compute_route':args.compute_route,'python':platform.python_version(),'gpu':gpu,'pip_check_passed':True,'critical_versions':versions,'pip_freeze':freeze,'note':'Dependencies resolved on this GPU route; training/template/export still require execution checks.'},indent=2)+'\n')
print('Environment metadata locked; no model downloaded/trained by this command.')
