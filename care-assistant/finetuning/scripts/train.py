"""UNEXECUTED NVIDIA recipe. No network/model import without explicit route + --execute.
Uses the same current system prompts and native tools in prepared task records.
Never reads test data or previous evaluation cases.
"""
import argparse, hashlib, importlib.metadata, json, math, os, platform, subprocess, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''): h.update(block)
    return h.hexdigest()

def read_json(path): return json.loads(Path(path).read_text())
def check_source():
    lock = read_json(ROOT/'config/baseline-lock.json')
    for p, h in lock['hashes'].items():
        if digest(ROOT.parent/p) != h: raise RuntimeError('App baseline changed: '+p)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--compute-route', choices=['kaggle-nvidia', 'colab-nvidia', 'existing-nvidia'])
    parser.add_argument('--environment-lock', type=Path)
    parser.add_argument('--run-id', default='seed-qlora-001')
    args = parser.parse_args()
    cfg = read_json(ROOT/'config/train.json')
    if not args.execute:
        print(json.dumps({'status':'PREPARATION ONLY — no imports, downloads or training', 'route_required':True, 'config':cfg}, indent=2)); return
    if not args.compute_route or not args.environment_lock:
        parser.error('An authorized NVIDIA route and its reviewed environment lock are required.')
    if platform.system() != 'Linux': raise RuntimeError('This NVIDIA recipe is not validated for this OS. Mac-only support needs a separate confirmed recipe.')
    if not args.run_id.replace('-','').isalnum(): raise ValueError('Use an alphanumeric run ID.')
    check_source()
    validation = read_json(ROOT/'reports/data-validation.json')
    assert validation['passed']
    env_lock = read_json(args.environment_lock)
    assert env_lock['compute_route'] == args.compute_route and env_lock['pip_check_passed'] is True
    assert env_lock['status'] == 'resolved_on_selected_gpu'
    assert env_lock['python'] == platform.python_version(), 'Python version drift'
    run = ROOT/'runs'/args.run_id
    run.mkdir(parents=True, exist_ok=False)  # Never overwrite a run/adapter.
    # These imports may initialize CUDA/download components; only occur past the gate.
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')  # Process-local, one GPU only.
    os.environ.setdefault('HF_HOME', str(ROOT/'model-cache'))
    os.environ.update(WANDB_DISABLED='true', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')
    from unsloth import FastModel
    import torch
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq, TrainerCallback
    from trl import SFTTrainer, SFTConfig
    assert torch.cuda.is_available(), 'NVIDIA CUDA GPU required'
    assert torch.cuda.device_count()==1, 'Expose exactly one authorized GPU to this process'
    assert torch.cuda.get_device_properties(0).total_memory >= 10*1024**3, 'At least 10 GiB VRAM; 16+ recommended with headroom'
    # Refuse drift from the reviewed GPU environment, rather than silently updating.
    for package, version in env_lock['critical_versions'].items():
        assert importlib.metadata.version(package) == version, package+' version drift'
    pins = read_json(ROOT/'config/upstream-pins.json')['sources']
    base = pins[cfg['model_key']]
    assert len(base['revision']) == 40
    model, processor = FastModel.from_pretrained(model_name=base['model_id'], revision=base['revision'], max_seq_length=cfg['max_seq_length'], load_in_4bit=True, full_finetuning=False, use_gradient_checkpointing='unsloth')
    assert getattr(model.config, '_commit_hash', None) == base['revision'], 'Loaded base revision not established; inspect before any training'
    tok = getattr(processor, 'tokenizer', processor)
    # Keep the pinned model's native template. Do not substitute ChatML/manual calls.
    template = getattr(processor,'chat_template',None) or tok.chat_template
    if isinstance(template,dict): template = template.get('default',next(iter(template.values())))
    assert '<|turn>' in template and 'tool_calls' in template, 'Native Gemma/tool template required'
    (run/'native-template.jinja').write_text(template)
    def encode(records):
        out=[]; lengths=[]
        for row in records:
            options = dict(tokenize=False, enable_thinking=False)
            if row.get('tools'): options['tools'] = row['tools']
            prefix = processor.apply_chat_template(row['messages'][:-1], add_generation_prompt=True, **options)
            full = processor.apply_chat_template(row['messages'], add_generation_prompt=False, **options)
            assert full.startswith(prefix), 'Assistant prefix mismatch; review native template before training'
            if row['task']=='tools': assert '<|tool_call>' in full, 'Tools were not natively rendered'
            encoded = tok(full, add_special_tokens=False, return_offsets_mapping=True)
            ids=encoded['input_ids']; assert len(ids)<=cfg['max_seq_length'], 'Overlong seed; never silently truncate target'
            assert ids.count(tok.bos_token_id)==1, 'BOS duplicated or missing'
            labels=[t if end>len(prefix) else -100 for t,(start,end) in zip(ids,encoded['offset_mapping'])]
            assert 0<sum(t!=-100 for t in labels)<len(ids), 'Mask must isolate a nonempty assistant completion'
            out.append({'input_ids':ids,'attention_mask':encoded['attention_mask'],'labels':labels});lengths.append(len(ids))
        return Dataset.from_list(out),lengths
    # Explicit allowlist: there is intentionally no test loader here.
    train_path=ROOT/'data/compiled.train.jsonl';val_path=ROOT/'data/compiled.validation.jsonl'
    train_rows=[json.loads(s) for s in train_path.read_text().splitlines()]; val_rows=[json.loads(s) for s in val_path.read_text().splitlines()]
    assert all(r['split']=='train' for r in train_rows) and all(r['split']=='validation' for r in val_rows)
    data_lock=read_json(ROOT/'config/baseline-lock.json')['compiled_hashes']
    assert digest(train_path)==data_lock['train'] and digest(val_path)==data_lock['validation'], 'Prepared training data changed after validation'
    assert len(train_rows)<=cfg['maximum_training_records']
    train_data,train_lengths=encode(train_rows);val_data,val_lengths=encode(val_rows)
    model = FastModel.get_peft_model(model, finetune_vision_layers=False, finetune_language_layers=True, finetune_attention_modules=True, finetune_mlp_modules=True, r=cfg['lora_rank'], lora_alpha=cfg['lora_alpha'], lora_dropout=cfg['lora_dropout'], bias='none', random_state=cfg['seed'])
    trainable=[(n,p) for n,p in model.named_parameters() if p.requires_grad]
    assert trainable and all('lora_' in n and not any(t in n.lower() for t in ['vision','audio','embed_tokens']) for n,p in trainable), 'Unexpected non-text or base trainable tensor'
    def tensors(): return {n:hashlib.sha256(p.detach().float().cpu().contiguous().numpy().tobytes()).hexdigest() for n,p in trainable}
    before=tensors();started=time.monotonic()
    class Budget(TrainerCallback):
        def on_step_end(self,args,state,control,**kwargs):
            if state.global_step>=cfg['maximum_optimizer_steps'] or time.monotonic()-started>cfg['maximum_runtime_seconds']: control.should_training_stop=True
    use_bf16=torch.cuda.is_bf16_supported()
    trainer=SFTTrainer(model=model, processing_class=tok, train_dataset=train_data, eval_dataset=val_data, data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100), callbacks=[Budget()], args=SFTConfig(output_dir=str(run/'checkpoints'), per_device_train_batch_size=cfg['micro_batch'], per_device_eval_batch_size=1, gradient_accumulation_steps=cfg['gradient_accumulation'], num_train_epochs=cfg['num_train_epochs'], max_steps=-1, learning_rate=cfg['learning_rate'], warmup_ratio=cfg['warmup_ratio'], weight_decay=cfg['weight_decay'], max_grad_norm=cfg['max_grad_norm'], optim='adamw_8bit', lr_scheduler_type='linear', seed=cfg['seed'], bf16=use_bf16, fp16=not use_bf16, report_to='none', push_to_hub=False, logging_steps=1, eval_strategy='epoch', save_strategy='no', packing=False, max_length=cfg['max_seq_length'], dataset_kwargs={'skip_prepare_dataset':True}))
    # Do not force config.use_cache=False: Gemma 4 shared KV needs upstream fixes.
    initial={'training_script_sha256':digest(__file__),'requirements_sha256':digest(ROOT/'requirements.candidate.txt'),'recipe_sha256':digest(ROOT/'config/train.json'),'status':'training_started_not_yet_proven','base':base,'recipe':cfg,'runtime_gpu':{'name':torch.cuda.get_device_name(0),'vram_bytes':torch.cuda.get_device_properties(0).total_memory,'cuda':torch.version.cuda},'environment':env_lock,'source_hashes':validation['source_hashes'],'train_sha256':digest(train_path),'validation_sha256':digest(val_path),'test_loaded':False,'before_trainable_tensor_sha256':before,'max_train_tokens':max(train_lengths),'max_validation_tokens':max(val_lengths),'template_sha256':hashlib.sha256(template.encode()).hexdigest()}
    (run/'started.json').write_text(json.dumps(initial,indent=2)+'\n')
    stats=trainer.train();assert all(torch.isfinite(p).all().item() for n,p in trainable), 'Non-finite adapter tensor';after=tensors();changed=[n for n in before if before[n]!=after[n]]
    assert trainer.state.global_step>0 and changed, 'No real optimizer updates/tensor change'
    adapter=run/'adapter'
    model.peft_config['default'].revision=base['revision']
    model.peft_config['default'].base_model_name_or_path=base['model_id']
    model.save_pretrained(adapter,safe_serialization=True);processor.save_pretrained(adapter)
    from safetensors.torch import load_file
    saved=load_file(str(adapter/'adapter_model.safetensors'))
    assert any('lora_B' in n and torch.count_nonzero(t).item()>0 for n,t in saved.items()), 'Saved adapter has no updated B tensor'
    proof={**initial,'status':'weights_updated_adapter_saved_NOT_heldout_or_GGUF_validated','global_steps':trainer.state.global_step,'changed_trainable_tensors':len(changed),'after_trainable_tensor_sha256':after,'adapter_sha256':digest(adapter/'adapter_model.safetensors'),'adapter_config_sha256':digest(adapter/'adapter_config.json'),'saved_tokenizer_metadata_sha256':{p.name:digest(p) for p in adapter.iterdir() if p.is_file() and p.suffix!='.safetensors'},'elapsed_seconds':round(time.monotonic()-started,3),'train_metrics':stats.metrics,'heldout_inference_proven':False,'export_executed':False}
    (run/'training-complete.json').write_text(json.dumps(proof,indent=2)+'\n')
    print('Adapter saved with tensor-change evidence. This does NOT prove held-out improvement or a working GGUF export.')

if __name__=='__main__': main()
