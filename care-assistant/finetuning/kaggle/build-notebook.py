"""Build self-contained PRIVATE Kaggle import, no upload or execution."""
import base64,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
bundle=ROOT/'runs/preparation-bundle.zip'
encoded=base64.b64encode(bundle.read_bytes()).decode();expected=hashlib.sha256(bundle.read_bytes()).hexdigest()
with zipfile.ZipFile(bundle) as z:names=sorted(z.namelist())
assert all(not any(s in n for s in ['.env','sealed-test','compiled.test','tools.test','evaluation/','.cache/','node_modules/']) for n in names)
cells=[]
def cell(kind,text):
 c={'cell_type':kind,'id':hashlib.sha256(text.encode()).hexdigest()[:10],'metadata':{},'source':text.splitlines(keepends=True)}
 if kind=='code':c.update(execution_count=None,outputs=[])
 cells.append(c)
cell('markdown','''# Chest BPM — private E4B QLoRA seed pilot\nKeep this notebook **Private / Only you**. User-authorized Kaggle GPU route; no paid compute or public publishing. This notebook embeds only allowlisted app source and synthetic train/validation data. **No sealed final test, secrets, private chats/audio/member data or provider listings.**\n\nEnable Internet and a free T4/L4 GPU in Session options before running. Only device 0 is used. It preflights resources, installs an isolated pinned environment, then runs one bounded pilot. Nothing changes the working Mac demo. Actual GPU/package compatibility is not yet verified.\n\nSave Version → Save & Run All once for a fresh durable run, or run cells interactively and Quick Save **with outputs** afterward. Do not rerun training merely to save outputs. Download the final artifacts ZIP and confirm saved outputs before stopping the GPU session. A saved adapter alone is not proof of held-out improvement.\n''')
bootstrap='''import base64, hashlib, json, subprocess, sys, zipfile, io\nfrom pathlib import Path, PurePosixPath\nassert Path('/kaggle/working').is_dir(), 'Run this imported private notebook on Kaggle, not on the Mac'\n'''
bootstrap+='BUNDLE_SHA256 = '+repr(expected)+'\n'
bootstrap+='BUNDLE_BASE64 = '+repr(encoded)+'\n'
bootstrap+='ALLOWED = '+repr(names)+'\n'
bootstrap+='''raw = base64.b64decode(BUNDLE_BASE64)\nassert hashlib.sha256(raw).hexdigest() == BUNDLE_SHA256, 'Embedded bundle checksum mismatch'\nworkspace = Path('/kaggle/working/care-assistant-pilot')\nworkspace.mkdir(exist_ok=True)\nwith zipfile.ZipFile(io.BytesIO(raw)) as z:\n    assert sorted(z.namelist()) == ALLOWED\n    for name in z.namelist():\n        path = PurePosixPath(name)\n        assert not path.is_absolute() and '..' not in path.parts\n        assert not any(s in name for s in ['.env', 'sealed-test', 'compiled.test', 'tools.test', 'evaluation/', '.cache/', 'node_modules/'])\n    z.extractall(workspace)\napp = workspace / 'care-assistant'\nrunner = app / 'finetuning/kaggle/runner.py'\nassert runner.is_file()\nprint('Verified allowlisted bundle:', BUNDLE_SHA256, 'files:', len(ALLOWED))\nprint('Only synthetic train/validation are present. Final test content is absent.')\ndef stage(name):\n    subprocess.run([sys.executable, str(runner), name], check=True)\n'''
cell('code',bootstrap)
cell('markdown','''## 1. Preflight — no package/model download\nChecks Internet/public model metadata, assigned GPU, memory, driver and scratch/output headroom. A failure saves a no-success status. Fix the actual environment/access issue before continuing; do not switch to paid compute.\n''')
cell('code',"stage('preflight')\n")
cell('markdown','''## 2. Isolated environment\nInstalls pinned CUDA/training packages under `/tmp`, checks dependencies/imports/CUDA and saves the resolved environment lock. Does not modify Kaggle's preinstalled Python environment. The large model cache also stays in scratch rather than saved outputs. Stop and inspect logs if it fails.\n''')
cell('code',"stage('setup')\n")
cell('markdown','''## 3. One authorized bounded training run\nThis downloads the pinned public 4-bit base on Kaggle, verifies native template/assistant masks, trains text LoRA only, and saves the adapter plus tensor-change evidence. Train/validation only: sealed test content is absent. Existing run directories are not overwritten. There is no publishing, full-model export or default-model swap.\n''')
cell('code',"stage('train')\n")
cell('markdown','''## 4. Save and retrieve actual outputs\nDownload `/kaggle/working/care-e4b-pilot-artifacts.zip`. Inspect `training-complete.json` and adapter hashes. Successful weight updates are **not** a held-out/GGUF quality result. The matched-base/adapted llama.cpp b12248 evaluation described in EXPORT.md remains required before any adoption.\n\nConfirm the private saved notebook version includes output files, then stop its GPU session. If stages fail, inspect the saved status/log archive; do not claim a trained adapter. Use `stage('package')` only to repackage existing outputs, not to retrain.\n''')
cell('code',"from IPython.display import FileLink, display\noutput = Path('/kaggle/working/care-e4b-pilot-artifacts.zip')\nassert output.is_file(), 'No output archive: inspect failed stage/logs'\ndisplay(FileLink(str(output)))\n")
notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'kaggle':{'isInternetEnabled':True,'isGpuEnabled':True,'accelerator':'nvidiaTeslaT4'},'care_assistant':{'private_required':True,'bundle_sha256':expected,'sealed_test_embedded':False,'training_executed':False}},'nbformat':4,'nbformat_minor':5}
name=sys.argv[1] if len(sys.argv)>1 else 'care-e4b-qlora-private.ipynb'
assert Path(name).name==name and name.endswith('.ipynb')
out=ROOT/'kaggle'/name;out.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n')
metadata={'id':'__EXISTING_KAGGLE_OWNER__/chest-bpm-e4b-qlora-pilot','title':'Chest BPM E4B QLoRA private pilot','code_file':out.name,'language':'python','kernel_type':'notebook','is_private':True,'enable_gpu':True,'enable_internet':True,'dataset_sources':[],'competition_sources':[],'kernel_sources':[],'model_sources':[]}
(ROOT/'kaggle/kernel-metadata.template.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({'notebook':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'embedded_bundle_sha256':expected,'sealed_test_embedded':False,'uploaded':False,'training_executed':False},indent=2))
