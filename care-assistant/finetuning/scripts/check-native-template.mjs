// Local template rendering/token counts only; no generation or training.
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url),base='http://127.0.0.1:4320';
const rows=(await readFile(new URL('data/compiled.train.jsonl',root),'utf8')).trim().split('\n').map(JSON.parse);
const report={checked_at:new Date().toISOString(),scope:'Training split only; llama.cpp /apply-template + /tokenize. No model generation, training or HF tokenizer download. This does not prove HF training-template parity.',cases:[]};
for(const row of rows){const messages=structuredClone(row.messages.slice(0,-1));for(const m of messages)for(const c of m.tool_calls||[])c.function.arguments=JSON.stringify(c.function.arguments);
 const r=await fetch(base+'/apply-template',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages,...(row.tools?{tools:row.tools}:{}),add_generation_prompt:true})});if(!r.ok)throw Error('apply-template HTTP '+r.status+' '+(await r.text()).slice(0,200));const {prompt}=await r.json();
 const t=await fetch(base+'/tokenize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:prompt,add_special:false})});if(!t.ok)throw Error('tokenize HTTP '+t.status);const {tokens}=await t.json();
 report.cases.push({id:row.case_id,prompt_token_count:tokens.length,completion_budget:row.task==='intent'?48:480,token_upper_bound:tokens.length+(row.task==='intent'?48:480),has_native_turn:prompt.includes('<|turn>'),...(row.task==='tools'?{has_native_tool_declaration:prompt.includes('<|tool>')}:{}),prompt_sha256:createHash('sha256').update(prompt).digest('hex')});}
report.target_rendering='Not proven: this llama.cpp apply-template endpoint rejects continuing an assistant tool-call turn. HF full-target rendering and exact completion masking remain gated pre-training checks. Initial full-target API probes returned HTTP 400; prompts below use the supported generation form.';
report.max_prompt_tokens=Math.max(...report.cases.map(x=>x.prompt_token_count));report.max_tokens=Math.max(...report.cases.map(x=>x.token_upper_bound));report.passed=report.cases.every(x=>x.has_native_turn&&x.token_upper_bound<=2048&&x.has_native_tool_declaration!==false);
await writeFile(new URL('reports/runtime-template-check.json',root),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:report.passed,cases:report.cases.length,max_tokens:report.max_tokens}));if(!report.passed)process.exitCode=1;
