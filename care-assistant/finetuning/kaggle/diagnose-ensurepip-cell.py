# Paste into a new Kaggle cell AFTER bundle/preflight, before retrying setup.
import json, shutil, subprocess, sys
from pathlib import Path
app = Path('/kaggle/working/care-assistant-pilot/care-assistant')
art = app/'finetuning/runs'; art.mkdir(parents=True, exist_ok=True)
original = Path('/kaggle/working/care-e4b-pilot-artifacts.zip')
first = Path('/kaggle/working/care-e4b-first-setup-failure.zip')
if original.exists() and not first.exists(): shutil.copy2(original, first)
for name in ['kaggle-failure.json', 'kaggle-status.json']:
    src=art/name; dst=art/('pre-repair-'+name)
    if src.exists() and not dst.exists(): shutil.copy2(src,dst)
py = Path('/tmp/chest-bpm-e4b-pilot/venv/bin/python')
results={'kernel_python':sys.version,'kernel_executable':sys.executable,'venv_python_exists':py.exists(),'steps':[]}
for cmd in [[str(py),'-m','ensurepip','--upgrade','--default-pip'], [str(py),'-m','pip','--version']]:
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=120)
        row={'command':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    except Exception as e: row={'command':cmd,'error':repr(e)}
    results['steps'].append(row)
    print(json.dumps(row,indent=2))
out=art/'ensurepip-diagnostic.json'
if out.exists(): out=art/'ensurepip-diagnostic-retry.json'
out.write_text(json.dumps(results,indent=2)+'\n')
print('Saved diagnosis:',out,'; currently available pre-repair archive:',first)
print('No model/training package install or optimizer step was requested by this cell.')
