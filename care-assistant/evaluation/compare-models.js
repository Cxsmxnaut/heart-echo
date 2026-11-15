import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createModel } from '../src/model.js';
import { createService } from '../src/service.js';
import { createTools } from '../src/tools.js';
import { createMcpTools } from '../src/tool-client.js';
import { createDirectories } from '../src/directories.js';
import { fixtureFetch, syntheticInsurance } from '../test/fixtures.js';
const args = Object.fromEntries(process.argv.slice(2).map(s => s.replace(/^--/, '').split('=')));
const name = args.name || 'e2b-split-t0'; if (!/^[a-z0-9-]+$/.test(name)) throw Error('Invalid report name');
const model = createModel({ provider: 'compatible', model: args.model || 'care-gemma4-e2b', baseUrl: args.endpoint || 'http://127.0.0.1:4320/v1', timeoutMs: 45000, temperature: Number(args.temperature || 0) });
const seen = JSON.parse(await readFile(new URL('./pass2-final-scenarios.json', import.meta.url))).extraction;
// Previously seen final cases are now explicitly DEVELOPMENT data. One label
// changes to reflect the product definition: declining details continues care.
const data = [...seen.map(s => ({ ...s, intent: s.id === 'p2_decline_coverage_info' ? 'find_care' : s.intent })),
  { id: 'dev_neighborhood_search', message: 'Could you find a primary care doctor in 11215?', expected: { zip: '11215', specialty: 'family_medicine' }, intent: 'find_care' },
  { id: 'dev_forgot_plan', message: 'I forgot my plan name.', expected: { insurance: null, clear_fields: ['plan'] }, intent: 'find_care' },
  { id: 'dev_cannot_afford_visit', message: 'I cannot afford a regular doctor visit. Where can I get lower-cost care?', expected: { zip: null, insurance: null }, intent: 'cheaper_options' },
  { id: 'dev_partial_labels', message: 'plan: Mock Garden Plus; network: Mock Wide', expected: { insurance: { plan: 'Mock Garden Plus', network: 'Mock Wide' } }, intent: 'find_care' },
  { id: 'dev_explicit_coverage_year', message: 'Please check my coverage for 2028.', expected: { insurance: { coverage_year: 2028 } }, intent: 'find_care' },
  { id: 'dev_unclear_meaning', message: 'The result says unclear. Does that mean I am sick?', expected: { specialty: null }, intent: 'explain_scan' },
  { id: 'dev_selection_reason', message: 'How did you pick that clinic for me?', expected: { zip: null, insurance: null }, intent: 'explain_results' },
  { id: 'dev_thanks', message: 'Thanks for your help.', expected: { zip: null, insurance: null, specialty: null }, intent: 'other' },
].slice(0, Number(args.limit || 24));
const context = { profile: { zip: '12345', specialty: 'family_medicine', insurance: { ...syntheticInsurance, coverage_date: '2027-04-22' } } };
const report = { name, started_at: new Date().toISOString(), data_status: 'development, includes seen pass2 final cases; not held out', raw_model: model.status(), temperature: Number(args.temperature || 0), source_sha256: createHash('sha256').update(await readFile(new URL('../src/model.js', import.meta.url))).digest('hex'), extraction: [], journeys: [] };
function diff(expected, actual, path = '') { const failed = []; for (const [k, v] of Object.entries(expected)) { const p = path ? `${path}.${k}` : k; if (Array.isArray(v)) { if (!v.every(x => actual?.[k]?.includes(x))) failed.push(p); } else if (v && typeof v === 'object') failed.push(...diff(v, actual?.[k], p)); else if (actual?.[k] !== v) failed.push(p); } return failed; }
const save = () => writeFile(new URL(`./results.dev.${name}.json`, import.meta.url), JSON.stringify(report, null, 2) + '\n');
for (const s of data) {
  const start = performance.now();
  // Evaluate each task independently so an intent failure does not mask fields.
  const [a, b] = await Promise.allSettled([model.classify(s.message), model.extractFields(s.message)]);
  const fieldsFailures = b.status === 'fulfilled' ? diff(s.expected, b.value) : [b.reason.code || b.reason.message];
  if (b.status === 'fulfilled') for (const p of s.absent || []) if (p.split('.').reduce((o, k) => o?.[k], b.value) != null) fieldsFailures.push(p);
  const row = { id: s.id, intent_passed: a.status === 'fulfilled' && a.value === s.intent, fields_passed: !fieldsFailures.length, actual_intent: a.status === 'fulfilled' ? a.value : a.reason.code, expected_intent: s.intent, field_failures: fieldsFailures, elapsed_ms: Math.round(performance.now() - start) };
  report.extraction.push(row); await save(); console.log(JSON.stringify(row));
}
if (!args.rawonly) {
  const tools = createMcpTools(createTools(createDirectories({ fetchImpl: fixtureFetch })));
  const service = createService({ model, tools }); const turns = []; const start = performance.now();
  let r = await service.chat({ profile: context.profile, action: 'explain' }); const id = r.session_id;
  for (const message of ["I can't recall the network name.", 'Only health centers with possible sliding discounts, please.', 'Why are these clinics on the list?']) {
    r = await service.chat({ session_id: id, message }); turns.push({ message, stage: r.stage, preference: r.profile.care_preference, mode: r.model.mode, adjustments: r.backend_adjustments, trace: r.tool_trace });
  }
  report.journeys.push({ id: 'development_cost_continuity', completed: r.stage === 'explain_results' && r.profile.care_preference === 'affordable', elapsed_ms: Math.round(performance.now() - start), turns });
}
const times = report.extraction.map(r => r.elapsed_ms).sort((a,b)=>a-b);
report.summary = { intents: `${report.extraction.filter(r=>r.intent_passed).length}/${data.length}`, fields: `${report.extraction.filter(r=>r.fields_passed).length}/${data.length}`, combined: `${report.extraction.filter(r=>r.intent_passed&&r.fields_passed).length}/${data.length}`, median_ms: times[Math.floor(times.length/2)], rejected_fields: report.extraction.filter(r=>r.field_failures.some(x=>x.startsWith('model_'))).length, guided_turns: report.journeys.flatMap(j=>j.turns).filter(t=>t.mode==='guided_fallback').length, corrected_turns: report.journeys.flatMap(j=>j.turns).filter(t=>t.adjustments?.length).length };
report.completed_at = new Date().toISOString(); await save(); console.log(JSON.stringify(report.summary));
