"""Freeze actual trained/converted artifacts before any held-out model inference."""
import hashlib,json,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[1];app=root.parent
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
proof_path=root/'runs/kaggle-artifacts-v1/kaggle-seed-001/training-complete.json';proof=json.loads(proof_path.read_text())
assert proof['global_steps']>0 and proof['changed_trainable_tensors']>0 and proof['test_loaded'] is False
adapter=proof_path.parent/'adapter/adapter_model.safetensors';assert sha(adapter)==proof['adapter_sha256']
base=app/'.cache/models/e4b/gemma-4-E4B-it-Q4_K_M.gguf';base_hash=sha(base);assert base_hash=='85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87'
lora=root/'exports/care-e4b-seed001-lora-f16.gguf';lora_hash=sha(lora);assert lora_hash=='513abc53c84f42116bec06877c6691de83d6c224e921f15039315121fc9ea6e3'
relative=lambda p:str(p.relative_to(app))
lock=json.loads((root/'config/baseline-lock.json').read_text())
for p,h in lock['hashes'].items():assert sha(app/p)==h,p
r={'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'candidate_frozen_after_real_training','mode':'gguf_lora','training_proof':relative(proof_path),'adapter_path':relative(adapter),'adapter_sha256':proof['adapter_sha256'],'gguf_path':relative(base),'gguf_sha256':base_hash,'gguf_lora_path':relative(lora),'gguf_lora_sha256':lora_hash,'sealed_test_sha256':sha(root/'data/sealed-test.jsonl'),'tools_test_sha256':sha(root/'data/tools.test.jsonl'),'source_hashes':lock['hashes'],'runtime':{'tag':'b12248','binary_sha256':sha(app/'.cache/runtime/llama-b12248/llama-server'),'source':json.loads((root/'config/lora-export-source.json').read_text())},'decoding':{'model_alias':'care-gemma4-e4b','temperature':0,'top_p':0.95,'top_k':64,'thinking':False,'reasoning':'off','reasoning_budget':0,'context':8192,'parallel_slots':1,'threads':2,'batch_threads':2,'cache_ram':0,'tool_mode':'batch','lora_scale':1},'training_base':proof['base'],'packaging_note':'Training uses pinned bnb4bit. Runtime comparison uses the EXACT SAME existing Q4_K_M GGUF with LoRA disabled/enabled; conversion config is a normalized copy dropping only quantization_config, not changed EOS/geometry. No full base merge or retuning.','selection':'One fixed seed adapter. No tuning on sealed test; report all first outcomes. No serving-default adoption.'}
p=root/'config/candidate-seed001-freeze.json';assert not p.exists(),'Keep first candidate freeze immutable';p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'base_sha256':base_hash,'lora_sha256':lora_hash,'source_unchanged':True},indent=2))
