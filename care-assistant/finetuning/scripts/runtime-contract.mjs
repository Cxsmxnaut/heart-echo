// Capture the CURRENT app request and validate targets without changing app code,
// contacting a model, or fetching any directory data.
import assert from 'node:assert/strict';
import { createModel } from '../../src/model.js';
import { createTools } from '../../src/tools.js';
import { Profile, ScanSummary } from '../../src/schema.js';
const blank = {zip:null,payer:null,plan:null,network:null,plan_id:null,coverage_year:null,coverage_date:null,insurance_status:null,specialty:null,clear_fields:[]};
export const emptyFields = () => structuredClone(blank);
export async function capture(task, row) {
  let requests=[];
  const calls=(row.calls||[]).map((c,i)=>({id:`synthetic_call_${i}`,type:'function',function:{name:c.name,arguments:JSON.stringify(c.arguments)}}));
  const reply=task==='intent'?{role:'assistant',content:JSON.stringify({intent:row.intent})}:task==='fields'?{role:'assistant',content:JSON.stringify(row.fields)}:{role:'assistant',content:null,tool_calls:calls};
  const model=createModel({provider:'compatible',model:'synthetic-contract-validator',baseUrl:'http://127.0.0.1:1/v1',timeoutMs:1000,temperature:0,toolMode:'batch'},async(url,options)=>{requests.push(JSON.parse(options.body));return Response.json({choices:[{message:reply}]});});
  let validated;
  if(task==='intent') validated=await model.classify(row.message);
  else if(task==='fields') {assert.deepEqual(Object.keys(row.fields).sort(),Object.keys(blank).sort());validated=await model.extractFields(row.message);}
  else {
    Profile.parse(row.profile);if(row.scan)ScanSummary.parse(row.scan);
    const tools=createTools({searchProviders:async()=>({status:'ok',items:[]}),searchAffordableClinics:async()=>({status:'ok',items:[]}),lookupPlanNetwork:async()=>({status:'unsupported',providers:[]})});
    const r=await model.runTools({profile:row.profile,scan:row.scan??null,message:row.message,intent:row.intent,history:row.history||[],tools});
    assert.equal(r.trace.length,calls.length);assert.ok(r.trace.every(t=>t.origin==='model'&&t.status!=='rejected_arguments'));
    assert.equal(requests.length,1,'Seed must cover the full required batch in one response');
    const offered=requests[0].tools.map(t=>t.function.name);assert.deepEqual([...r.results.keys()].sort(),[...offered].sort());
    for(const c of calls)assert.ok(offered.includes(c.function.name));
    validated=r.trace;
  }
  const request=requests[0];
  // HF templates expect object arguments; the live OAI adapter above validates strings.
  const assistant=structuredClone(reply);
  if(assistant.tool_calls)for(const c of assistant.tool_calls)c.function.arguments=JSON.parse(c.function.arguments);
  return {request,assistant,validated};
}
