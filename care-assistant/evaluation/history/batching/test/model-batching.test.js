import test from 'node:test';
import assert from 'node:assert/strict';
import { createModel } from '../src/model.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { fixtureFetch } from './fixtures.js';
const tools=()=>createTools(createDirectories({fetchImpl:fixtureFetch}));
const config={provider:'compatible',model:'synthetic-protocol-double',baseUrl:'http://localhost:4320/v1',timeoutMs:1000};
const call=(name,args,id=name)=>({id,type:'function',function:{name,arguments:JSON.stringify(args)}});
test('batched native calls execute once, retain model trace, and serial setting remains available',async()=>{
 for(const mode of ['batch','serial']) {let requests=0;const m=createModel({...config,toolMode:mode},async(url,options)=>{const body=JSON.parse(options.body);assert.equal(body.parallel_tool_calls,mode==='batch');requests++;return Response.json({choices:[{message:{role:'assistant',tool_calls:[call('search_providers',{zip:'12345',specialty:'family_medicine',limit:5}),call('search_affordable_clinics',{zip:'12345',limit:5})]}}]});});const r=await m.runTools({profile:{zip:'12345'},tools:tools()});assert.equal(requests,1);assert.equal(r.results.size,2);assert.ok(r.trace.every(t=>t.origin==='model'));}
});
test('batch still rejects changed arguments and more than four calls',async()=>{
 for(const calls of [[call('search_affordable_clinics',{zip:'99999',limit:5})],Array.from({length:5},(_,i)=>call('search_affordable_clinics',{zip:'12345',limit:5},String(i)))]) {const m=createModel(config,async()=>Response.json({choices:[{message:{role:'assistant',tool_calls:calls}}]}));await assert.rejects(m.runTools({profile:{zip:'12345'},tools:tools()}),e=>['model_changed_search','model_tool_limit'].includes(e.code));}
});
