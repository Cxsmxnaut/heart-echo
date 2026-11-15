// Seen development scenarios only. Does not edit selected/frozen implementation.
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createModel} from '../src/model.js';
import {createTools} from '../src/tools.js';
import {createMcpTools} from '../src/tool-client.js';
import {createDirectories} from '../src/directories.js';
import {fixtureFetch,syntheticInsurance} from '../test/fixtures.js';
const report={started_at:new Date().toISOString(),experimental:true,deployed:false,note:'Seen scenarios only; adapter requests parallel native tool calls and asks for one batch. Frozen production source/configuration untouched. Handler still bounds at most four calls and validates every argument before MCP.',cases:[]};
let requests=[];
const model=createModel(undefined,async(url,options)=>{
 const body=JSON.parse(options.body);
 body.parallel_tool_calls=true;
 if(body.tools)body.messages[0].content+=' For this experimental batch, emit all required independent function calls together in one assistant response when possible.';
 const start=performance.now();const r=await fetch(url,{...options,body:JSON.stringify(body)});
 // Clone only to count tool calls; never record reasoning/content.
 const raw=await r.clone().json();requests.push({elapsed_ms:Math.round(performance.now()-start),native_calls:raw.choices?.[0]?.message?.tool_calls?.map(c=>c.function?.name)||[]});return r;
});
for(const s of [
{id:'seen_full_plan',profile:{zip:'12345',specialty:'family_medicine',insurance:{...syntheticInsurance,coverage_date:'2027-04-22'}},expected:['search_providers','search_affordable_clinics','lookup_plan_network']},
{id:'seen_uninsured',profile:{zip:'12345',specialty:'family_medicine',insurance:{status:'uninsured'}},expected:['search_providers','search_affordable_clinics']}
]){requests=[];const t=performance.now();try{const tools=createMcpTools(createTools(createDirectories({fetchImpl:fixtureFetch})));const r=await model.runTools({profile:s.profile,scan:null,message:'Find care using my confirmed details.',intent:'find_care',tools});const missing=s.expected.filter(n=>!r.results.has(n));assert.equal(missing.length,0);report.cases.push({id:s.id,completed:true,one_batch:requests.length===1&&requests[0].native_calls.length===s.expected.length,elapsed_ms:Math.round(performance.now()-t),model_requests:requests,trace:r.trace});}catch(e){report.cases.push({id:s.id,completed:false,error:e.code||e.message,elapsed_ms:Math.round(performance.now()-t),model_requests:requests});}await writeFile(new URL('./results.batching-experiment.json',import.meta.url),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report.cases.at(-1)));}
report.completed_at=new Date().toISOString();await writeFile(new URL('./results.batching-experiment.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
