"""Build a LOCAL allowlisted transfer zip; never uploads. Excludes test/evals/secrets."""
import hashlib,json,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];app=root.parent
lock=json.loads((root/'config/baseline-lock.json').read_text())
allowed=list(lock['hashes'])+[str(p.relative_to(app)) for p in (root/'scripts').glob('*.py')]
allowed += ['finetuning/kaggle/runner.py','finetuning/kaggle/bootstrap_env.py','finetuning/config/bootstrap-pins.json','finetuning/kaggle/README.md','finetuning/config/kaggle-upstream-check.json']
allowed += ['src/mcp.js','src/directories.js','src/healthplan.js','finetuning/scripts/evaluate.mjs','finetuning/scripts/runtime-contract.mjs','finetuning/data/seed.validation.jsonl','finetuning/data/tools.validation.jsonl']
allowed += ['finetuning/'+p for p in ['requirements.candidate.txt','README.md','EXPORT.md','config/train.json','config/upstream-pins.json','config/candidate-package-pins.json','config/baseline-lock.json','config/task-contract.json','reports/data-validation.json','data/compiled.train.jsonl','data/compiled.validation.jsonl']]
assert all(not any(part in p for part in ['.env','test.jsonl','evaluation/','node_modules/','.cache/']) for p in allowed)
out=root/'runs/preparation-bundle.zip';out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(set(allowed)):
  data=(app/p).read_bytes();info=zipfile.ZipInfo('care-assistant/'+p,date_time=(2026,11,14,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
print(json.dumps({'status':'local only, NOT uploaded','file':str(out),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'files':len(set(allowed)),'test_data_included':False},indent=2))
