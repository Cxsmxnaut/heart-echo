"""Reproduce the single pasteable cell from preserved v1 and current bootstrap."""
from pathlib import Path
import ast,base64,hashlib,io,json,zipfile,zlib
root=Path(__file__).resolve().parents[1];kg=root/'kaggle'
n=json.loads((kg/'care-e4b-qlora-private.ipynb').read_text());payload=None
for c in n['cells']:
 if c['cell_type']=='code':
  for a in ast.parse(''.join(c['source'])).body:
   if isinstance(a,ast.Assign) and isinstance(a.targets[0],ast.Name) and a.targets[0].id=='BUNDLE_BASE64':payload=ast.literal_eval(a.value)
assert payload
with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload))) as z:old=z.read('care-assistant/finetuning/kaggle/runner.py').decode()
oldline=" if not PYTHON.exists():venv.EnvBuilder(with_pip=True).create(SCRATCH/'venv')"
newline=" from bootstrap_env import ensure_environment\n ensure_environment(SCRATCH, ARTIFACTS, json.loads((FT/'config/bootstrap-pins.json').read_text()), ENV)"
assert old.count(oldline)==1;new=old.replace(oldline,newline);assert new==(kg/'runner.py').read_text()
sha=lambda x:hashlib.sha256(x).hexdigest()
helper=(kg/'bootstrap_env.py').read_bytes();encoded=base64.b64encode(zlib.compress(helper,9)).decode();pins=json.loads((root/'config/bootstrap-pins.json').read_text())
cell="""# Diagnose before repair; preserve available snapshot; never claim the overwritten first ZIP was saved.\nimport base64, hashlib, importlib.util, json, zlib\nfrom pathlib import Path\napp=Path('/kaggle/working/care-assistant-pilot/care-assistant')\nassert app.is_dir() and Path('/kaggle/working').is_dir()\nrunner=app/'finetuning/kaggle/runner.py'\nsource=runner.read_text(); current=hashlib.sha256(source.encode()).hexdigest()\n"""
cell+='assert current in '+repr([sha(old.encode()),sha(new.encode())])+", 'Unexpected runner edits; stop and inspect'\n"
cell+='helper_source=zlib.decompress(base64.b64decode('+repr(encoded)+'))\nassert hashlib.sha256(helper_source).hexdigest()=='+repr(sha(helper))+'\n'
cell+='pins='+repr(pins)+'\n'
cell+="""helper=app/'finetuning/kaggle/bootstrap_env.py'; helper.write_bytes(helper_source)\n(app/'finetuning/config/bootstrap-pins.json').write_text(json.dumps(pins,indent=2)+'\\n')\nspec=importlib.util.spec_from_file_location('care_bootstrap_repair',helper)\nrepair=importlib.util.module_from_spec(spec); spec.loader.exec_module(repair)\nrepair.ensure_environment(Path('/tmp/chest-bpm-e4b-pilot'),app/'finetuning/runs',pins,force_diagnostics=True)\n"""
cell+='if current=='+repr(sha(old.encode()))+':\n    source=source.replace('+repr(oldline)+','+repr(newline)+')\n    runner.write_text(source)\n'
cell+='assert hashlib.sha256(runner.read_bytes()).hexdigest()=='+repr(sha(new.encode()))+'\n'
cell+="""print('Bootstrap-only patch verified; resuming the original pinned setup.')\n# Do NOT rerun the old embedded-bundle extraction: it would restore the old runner.\nstage('setup')\n"""
(kg/'repair-ensurepip-cell.py').write_text(cell)
p=root/'reports/kaggle-bootstrap-repair.json';r=json.loads(p.read_text());r.update(helper_sha256=sha(helper),repair_cell_sha256=sha(cell.encode()),repair_cell_bytes=len(cell.encode()),patched_runner_sha256=sha(new.encode()));p.write_text(json.dumps(r,indent=2)+'\n')
print('Repair cell rebuilt:',len(cell.encode()),'bytes; model/training pins unchanged.')
