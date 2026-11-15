// Real inference through the app's JSON-schema and native-tool adapter + actual MCP.
// Default is validation ONLY. Test requires a frozen, actually-trained candidate.
import {readFile,writeFile,mkdir,access} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import assert from 'node:assert/strict';
import {createModel} from '../../src/model.js';
import {createTools} from '../../src/tools.js';
import {createMcpTools} from '../../src/tool-client.js';
import {capture} from './runtime-contract.mjs';
const args=Object.fromEntries(process.argv.slice(2).map(x=>x.replace(/^--/,'').split('=')));
const split=args.split||'validation',name=args.name||'baseline-validation';
assert.ok(['validation','test'].includes(split));assert.match(name,/^[a-z0-9-]+$/);
const root=new URL('../',import.meta.url),app=new URL('../../',import.meta.url),sha=x=>createHash('sha256').update(x).digest('hex');
async function hashFile(path){const h=createHash('sha256');for await(const chunk of createReadStream(path))h.update(chunk);return h.digest('hex');}
const lock=JSON.parse(await readFile(new URL('config/baseline-lock.json',root)));
for(const[p,h]of Object.entries(lock.hashes))assert.equal(sha(await readFile(new URL(p,app))),h,'Baseline app changed: '+p);
if(split==='test'){
 assert.ok(args['candidate-freeze'],'Do not open sealed test until candidate weights/config are frozen.');
 const f=JSON.parse(await readFile(args['candidate-freeze']));assert.equal(f.status,'candidate_frozen_after_real_training');assert.ok(f.training_proof&&f.gguf_sha256&&f.adapter_sha256);assert.equal(f.sealed_test_sha256,sha(await readFile(new URL('data/sealed-test.jsonl',root))));
 const proof=JSON.parse(await readFile(f.training_proof));assert.ok(proof.global_steps>0&&proof.changed_trainable_tensors>0);assert.equal(proof.adapter_sha256,f.adapter_sha256);
 assert.equal(f.tools_test_sha256,sha(await readFile(new URL('data/tools.test.jsonl',root))));
 assert.ok(f.adapter_path);assert.equal(await hashFile(f.adapter_path),f.adapter_sha256);
 assert.ok(f.gguf_path);assert.equal(await hashFile(f.gguf_path),f.gguf_sha256,'Candidate artifact differs from freeze');
 if(f.mode==='gguf_lora'){assert.ok(f.gguf_lora_path&&f.gguf_lora_sha256);assert.equal(await hashFile(f.gguf_lora_path),f.gguf_lora_sha256);if(args['fine-tuned']==='true')assert.equal(args['lora-sha256'],f.gguf_lora_sha256);}
}
const u=new URL(args.endpoint||'http://127.0.0.1:4320/v1');assert.ok(['127.0.0.1','localhost','[::1]'].includes(u.hostname),'This preparation runner allows local model endpoints only.');
assert.ok(args['weights-sha256'],'Supply the actual loaded GGUF SHA-256 identity.');assert.match(args['weights-sha256'],/^[a-f0-9]{64}$/);
const loraUrl=new URL(u);loraUrl.pathname='/lora-adapters';const loraResponse=await fetch(loraUrl);assert.ok(loraResponse.ok,'Runtime LoRA state unavailable');const loraState=await loraResponse.json();assert.ok(Array.isArray(loraState));const active=loraState.filter(x=>x.scale!==0);if(args['fine-tuned']==='true'){assert.equal(active.length,1,'Expected exactly one active adapter');assert.equal(active[0].scale,1);assert.match(args['lora-sha256']||'',/^[a-f0-9]{64}$/);}else assert.equal(active.length,0,'Control unexpectedly has active adapters');
const out=new URL('reports/'+name+'.json',root);try{await access(out);throw Error('Report exists; choose a distinct reproduction name.');}catch(e){if(e.code!=='ENOENT')throw e;}
const messages=(await readFile(new URL('data/'+(split==='test'?'sealed-test.jsonl':'seed.validation.jsonl'),root),'utf8')).trim().split('\n').map(JSON.parse);
const toolRows=(await readFile(new URL('data/tools.'+split+'.jsonl',root),'utf8')).trim().split('\n').map(JSON.parse);
const model=createModel({provider:'compatible',model:args.model||'care-gemma4-e4b',baseUrl:u.href,timeoutMs:45000,temperature:0,toolMode:'batch'});
const report={started_at:new Date().toISOString(),split,status:'real inference; not training',model:model.status(),gguf_sha256:args['weights-sha256'],lora_sha256:args['lora-sha256']||null,lora_state:loraState.map(x=>({id:x.id,path:x.path.split('/').at(-1),scale:x.scale})),source_hashes:lock.hashes,raw:[],tools:[],fine_tuned:args['fine-tuned']==='true',note:'Raw intent/fields before service correction. Tools use actual MCP with empty synthetic directory results, not public provider facts. Tool context and arguments remain server-constrained.'};
const save=()=>writeFile(out,JSON.stringify(report,null,2)+'\n');
for(const row of messages){const t=performance.now();const[ei,ef]=await Promise.all([capture('intent',row),capture('fields',row)]);const[a,b]=await Promise.allSettled([model.classify(row.message),model.extractFields(row.message)]);let fieldsPassed=false;if(b.status==='fulfilled')try{assert.deepEqual(b.value,ef.validated);fieldsPassed=true;}catch{}
 report.raw.push({case_id:row.case_id,intent_passed:a.status==='fulfilled'&&a.value===ei.validated,fields_passed:fieldsPassed,actual_intent:a.status==='fulfilled'?a.value:a.reason.code,actual_fields:b.status==='fulfilled'?b.value:null,field_error:b.status==='rejected'?(b.reason.code||b.reason.message):null,elapsed_ms:Math.round(performance.now()-t)});await save();console.log(JSON.stringify(report.raw.at(-1)));}
const tools=createMcpTools(createTools({searchProviders:async()=>({status:'ok',items:[]}),searchAffordableClinics:async()=>({status:'ok',items:[]}),lookupPlanNetwork:async()=>({status:'unsupported',providers:[]})}));
for(const row of toolRows){const t=performance.now();try{const r=await model.runTools({profile:row.profile,scan:row.scan,message:row.message,intent:row.intent,tools});assert.deepEqual([...r.results.keys()].sort(),row.calls.map(c=>c.name).sort());assert.ok(r.trace.every(x=>x.origin==='model'&&x.status!=='rejected_arguments'));if(row.calls.some(c=>c.name==='get_app_context'))assert.ok(r.results.get('get_app_context').sections[row.calls.find(c=>c.name==='get_app_context').arguments.topic]);report.tools.push({case_id:row.case_id,passed:true,elapsed_ms:Math.round(performance.now()-t),trace:r.trace});}catch(e){report.tools.push({case_id:row.case_id,passed:false,elapsed_ms:Math.round(performance.now()-t),error:e.code||e.message});}await save();console.log(JSON.stringify(report.tools.at(-1)));}
report.summary={raw_intents:`${report.raw.filter(x=>x.intent_passed).length}/${messages.length}`,raw_fields:`${report.raw.filter(x=>x.fields_passed).length}/${messages.length}`,constrained_tools:`${report.tools.filter(x=>x.passed).length}/${toolRows.length}`,backend_corrections:'not applied to raw scores',service_completed_calls:0};report.completed_at=new Date().toISOString();await save();console.log(JSON.stringify(report.summary));
