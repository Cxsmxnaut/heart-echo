"""Reproduce adapter-only GGUF conversion. Never loads/dequantizes full base weights.
Uses verified official b12248 source + a COPY of pinned training config with only
quantization_config omitted. Original PEFT adapter/config are not edited.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
APP=Path(__file__).resolve().parents[2];FT=APP/'finetuning'
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert not a.out.exists(),'Preserve existing output; choose another reproduction filename'
manifest=json.loads((FT/'config/lora-export-source.json').read_text());source=APP/manifest['source_path'];converter=source/'convert_lora_to_gguf.py'
sha=lambda x:hashlib.file_digest(Path(x).open('rb'),'sha256').hexdigest()
assert sha(converter)==manifest['converter_sha256']
run=FT/'runs/kaggle-artifacts-v1/kaggle-seed-001';proof=json.loads((run/'training-complete.json').read_text());assert proof['global_steps']>0;assert sha(run/'adapter/adapter_model.safetensors')==proof['adapter_sha256']
config=FT/'exports/base-config/config.json'
assert sha(config)==json.loads((FT/'reports/lora-config-normalization.json').read_text())['source_config_sha256'],'Use pinned verified original config, not an HF redirect or moving main'
original=json.loads(config.read_text());copy=dict(original);assert copy.pop('quantization_config')['quant_method']=='bitsandbytes'
normalized=FT/'exports/base-config-lora-only/config.json';normalized.parent.mkdir(exist_ok=True);normalized.write_text(json.dumps(copy,indent=2)+'\n');assert {k:v for k,v in original.items() if k!='quantization_config'}==json.loads(normalized.read_text())
a.out.parent.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,str(converter),'--base',str(normalized.parent),'--outtype','f16','--outfile',str(a.out),str(run/'adapter')],cwd=APP,check=True)
print(json.dumps({'output':str(a.out),'bytes':a.out.stat().st_size,'sha256':sha(a.out),'adapter_original_sha256':proof['adapter_sha256'],'base_weights_loaded':False},indent=2))
