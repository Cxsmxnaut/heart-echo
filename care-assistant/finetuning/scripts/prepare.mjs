import {readFile,writeFile,readdir,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {capture} from './runtime-contract.mjs';
const root=new URL('../',import.meta.url), app=new URL('../../',import.meta.url);
const sha=x=>createHash('sha256').update(x).digest('hex');
const load=async name=>(await readFile(new URL('data/'+name,root),'utf8')).trim().split('\n').filter(Boolean).map(x=>JSON.parse(x));
const rows=[];
for(const split of ['train','validation','test']){for(const r of await load(split==='test'?'sealed-test.jsonl':`seed.${split}.jsonl`))rows.push({...r,task:'message'});for(const r of await load(`tools.${split}.jsonl`))rows.push(r);}
const norm=s=>s.toLowerCase().replace(/\b\d+(?:-\d+)*\b/g,' <number> ').replace(/[^a-z<> ]/g,' ').replace(/\s+/g,' ').trim();
const tokens=s=>new Set(norm(s).split(' '));
const similarity=(a,b)=>{const x=tokens(a),y=tokens(b);if(Math.min(x.size,y.size)<8)return 0;return [...x].filter(t=>y.has(t)).length/new Set([...x,...y]).size;};
async function files(dir){let out=[];for(const e of await readdir(dir,{withFileTypes:true})){const p=new URL(e.name+(e.isDirectory()?'/':''),dir);if(e.isDirectory())out.push(...await files(p));else out.push(p);}return out;}
// Fingerprint old synthetic evaluation inputs; NEVER import their targets into SFT.
const seen=[],inventory=[];
function collect(x,path){if(Array.isArray(x))for(const v of x)collect(v,path);else if(x&&typeof x==='object')for(const[k,v]of Object.entries(x)){if(['message','input','text'].includes(k)&&typeof v==='string'&&v.length>15)seen.push({text:v,path});else collect(v,path);}}
for(const url of await files(new URL('evaluation/',app))){const name=fileURLToPath(url).split('/care-assistant/')[1];const bytes=await readFile(url);inventory.push({path:name,sha256:sha(bytes)});if(name.endsWith('.json')||name.endsWith('.jsonl')){try{if(name.endsWith('.jsonl'))for(const s of bytes.toString().trim().split('\n'))collect(JSON.parse(s),name);else collect(JSON.parse(bytes),name);}catch{}}
 if(name.endsWith('.js')){const text=bytes.toString();for(const m of text.matchAll(/\b(?:message|input)\s*:\s*('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")/g)){const v=m[1].slice(1,-1).replace(/\\'/g,"'").replace(/\\"/g,'"');if(v.length>15)seen.push({text:v,path:name});}}
}
const ids=new Set(),familySplit=new Map(),failures=[],seenWarnings=[],crossNear=[];
for(const r of rows){assert.ok(!ids.has(r.case_id),'Duplicate case ID');ids.add(r.case_id);assert.equal(r.synthetic,true);assert.equal(r.review.status,'agent_reviewed');assert.ok(r.review.basis.length>15);assert.ok(r.provenance.origin.includes('synthetic'));assert.ok(['train','validation','test'].includes(r.split));
 if(familySplit.has(r.family_id)&&familySplit.get(r.family_id)!==r.split)failures.push({id:r.case_id,error:'family_crosses_split'});familySplit.set(r.family_id,r.split);
 const matches=seen.filter(s=>norm(s.text)===norm(r.message)||similarity(s.text,r.message)>=0.82).map(s=>({path:s.path,input_sha256:sha(norm(s.text))}));if(matches.length){const m={id:r.case_id,split:r.split,matches:[...new Map(matches.map(x=>[x.path+x.input_sha256,x])).values()]};if(r.split==='train'||r.split==='test')failures.push({...m,error:'prior_evaluation_overlap'});else seenWarnings.push(m);}
 if(/https?:|@|\b(?:member|patient|participant)\s*(?:id|number)\s*[:=]/i.test(r.message))failures.push({id:r.case_id,error:'disallowed_data_pattern'});
}
for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++)if(rows[i].split!==rows[j].split&&(norm(rows[i].message)===norm(rows[j].message)||similarity(rows[i].message,rows[j].message)>=0.82))crossNear.push({a:rows[i].case_id,b:rows[j].case_id,error:'near_duplicate_across_splits'});
failures.push(...crossNear);
const compiled={train:[],validation:[],test:[]},contracts={};
for(const r of rows){for(const task of r.task==='message'?['intent','fields']:['tools'])try{
 const x=await capture(task,r);const record={case_id:r.case_id+':'+task,scenario_id:r.case_id,family_id:r.family_id,split:r.split,task,synthetic:true,review:r.review,provenance:r.provenance,messages:[...x.request.messages,x.assistant],...(x.request.tools?{tools:x.request.tools}:{}),...(x.request.response_format?{response_format:x.request.response_format}:{})};compiled[r.split].push(record);
 if(task!=='tools')contracts[task]={system_prompt:x.request.messages[0].content,response_format:x.request.response_format,max_tokens:x.request.max_tokens};
 }catch(e){failures.push({id:r.case_id,task,error:e.code||e.message});}}
const sourceFiles=['src/model.js','src/schema.js','src/conversation.js','src/knowledge.js','src/tools.js','src/tool-client.js','src/server.js','public/app.js','public/index.html','public/style.css','scripts/model-artifacts.js','scripts/start-local-model.js','package.json','package-lock.json'];
const hashes=Object.fromEntries(await Promise.all(sourceFiles.map(async p=>[p,sha(await readFile(new URL(p,app)))])));
const seedHashes=Object.fromEntries(await Promise.all(['seed.train.jsonl','seed.validation.jsonl','sealed-test.jsonl','tools.train.jsonl','tools.validation.jsonl','tools.test.jsonl'].map(async p=>[p,sha(await readFile(new URL('data/'+p,root)))])));
const compiledHashes=Object.fromEntries(Object.entries(compiled).map(([split,records])=>[split,sha(records.map(r=>JSON.stringify(r)).join('\n')+'\n')]));
const report={compiled_hashes:compiledHashes,checked_at:new Date().toISOString(),executed:'Local structural/grounding/schema/native-tool-protocol doubles only; NO training, model inference, tokenizer rendering, export, or tensor update.',passed:!failures.length,unique_scenarios:rows.length,unique_families:familySplit.size,counts:Object.fromEntries(Object.keys(compiled).map(s=>[s,{scenarios:rows.filter(r=>r.split===s).length,families:new Set(rows.filter(r=>r.split===s).map(r=>r.family_id)).size,task_records:compiled[s].length}])),review:'Agent-authored and agent-reviewed policy labels with rationale, not clinician or human annotation. JSON intent/fields are separate projections of the same scenario; counts are not independent paraphrases.',seen_validation_warnings:seenWarnings,failures,leakage_limits:'Family assignments are explicit and reviewed; exact/token-overlap checks cannot prove absence of semantic leakage. Previous evaluation inputs are fingerprints only, not training sources.',source_hashes:hashes,seed_hashes:seedHashes};
await mkdir(new URL('reports/',root),{recursive:true});await writeFile(new URL('reports/data-validation.json',root),JSON.stringify(report,null,2)+'\n');
await writeFile(new URL('config/seen-evaluation-inventory.json',root),JSON.stringify({status:'ALL prior evaluations are seen; never training data',files:inventory,unique_input_fingerprints:[...new Set(seen.map(x=>sha(norm(x.text))))]},null,2)+'\n');
if(failures.length){console.log(JSON.stringify({passed:false,failures},null,2));process.exitCode=1;}else{for(const split of ['train','validation','test'])await writeFile(new URL(`data/compiled.${split}.jsonl`,root),compiled[split].map(r=>JSON.stringify(r)).join('\n')+'\n');await writeFile(new URL('config/task-contract.json',root),JSON.stringify({source_hashes:hashes,tasks:contracts},null,2)+'\n');await writeFile(new URL('config/baseline-lock.json',root),JSON.stringify({created_at:new Date().toISOString(),branch:'main',revision:null,revision_note:'Repository has no HEAD commit; source hashes identify this baseline. No Graphify/runtime found.',hashes,seed_hashes:seedHashes,compiled_hashes:compiledHashes},null,2)+'\n');console.log(JSON.stringify({passed:true,counts:report.counts,unique_families:report.unique_families,seen_validation_warnings:seenWarnings.length},null,2));}
