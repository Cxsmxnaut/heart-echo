import { readFile, writeFile } from 'node:fs/promises';
import { createModel } from '../src/model.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { createMcpTools } from '../src/tool-client.js';
import { fixtureFetch, syntheticInsurance, syntheticScan } from '../test/fixtures.js';
import { createService } from '../src/service.js';
import { createHash } from 'node:crypto';

const model = createModel();
if (!model.configured) { console.error('A real model is required. Set LLM_PROVIDER=compatible, LLM_BASE_URL, LLM_MODEL (and LLM_API_KEY if needed).'); process.exit(1); }
const finalSuite = process.argv.includes('--final');
const suite = finalSuite ? 'final-held-out.json' : 'held-out.json';
const scenarios = JSON.parse(await readFile(new URL(`./${suite}`, import.meta.url), 'utf8'));
const promptSource = await readFile(new URL('../src/model.js', import.meta.url));
const report = { tested_at: new Date().toISOString(), suite, source_sha256: createHash('sha256').update(promptSource).digest('hex'), model: model.status(), model_is_fine_tuned: false, data: `${finalSuite ? 'fresh held-out' : 'development/regression'} synthetic scenarios, synthetic directory fixtures; real inference and real MCP transport`, extraction: [], tools: [], backend: [] };
function differences(expected, actual, path = '') {
  const failures = [];
  for (const [key, value] of Object.entries(expected)) {
    const k = path ? `${path}.${key}` : key;
    if (value && typeof value === 'object') failures.push(...differences(value, actual?.[key], k));
    else if (actual?.[key] !== value) failures.push({ field: k, expected: value, actual: actual?.[key] ?? null });
  }
  return failures;
}
for (const s of scenarios) {
  const start = performance.now();
  try {
    const actual = await model.extract(s.message); const failures = differences(s.expected, actual);
    for (const key of s.absent_insurance || []) if (actual.insurance?.[key]) failures.push({ field: `insurance.${key}`, expected: 'absent', actual: actual.insurance[key] });
    report.extraction.push({ id: s.id, passed: failures.length === 0, elapsed_ms: Math.round(performance.now() - start), failures });
  } catch (e) { report.extraction.push({ id: s.id, passed: false, elapsed_ms: Math.round(performance.now() - start), error: e.code || e.message }); }
  console.log(JSON.stringify(report.extraction.at(-1)));
}
const tools = createMcpTools(createTools(createDirectories({ fetchImpl: fixtureFetch })));
const developmentTools = [
  { id: 'app_capabilities_tool', intent: 'app_help', profile: {}, scan: syntheticScan, message: 'Explain what the app can measure.', required: ['get_app_context'] },
  { id: 'uninsured_care_tools', profile: { zip: '12345', insurance: { status: 'uninsured' }, specialty: 'family_medicine' }, scan: null, message: 'Search providers and affordable clinics using my confirmed details.', required: ['search_providers', 'search_affordable_clinics'] },
  { id: 'exact_plan_tools', profile: { zip: '12345', insurance: syntheticInsurance, specialty: 'family_medicine' }, scan: { ...syntheticScan, quality: 'unclear', estimated_bpm: null }, message: 'Search providers, affordable clinics, and my exact plan/network using the confirmed profile.', required: ['search_providers', 'search_affordable_clinics', 'lookup_plan_network'] },
];
const freshTools = [
  { id: 'fresh_help_without_scan', intent: 'app_help', profile: {}, scan: null, message: 'Retrieve the app facts so I can understand the insurance-check limits.', required: ['get_app_context'] },
  { id: 'fresh_unknown_insurance_empty_zip', profile: { zip: '54321', insurance: { status: 'unknown' }, specialty: 'internal_medicine' }, scan: null, message: 'Please check both provider identities and health centers with these confirmed search settings.', required: ['search_providers', 'search_affordable_clinics'] },
  { id: 'fresh_future_payer_unavailable_scan', profile: { zip: '12345', insurance: syntheticInsurance, specialty: 'family_medicine' }, scan: { ...syntheticScan, quality: 'unavailable', estimated_bpm: null }, message: 'Use the confirmed future-year insurance details to check the network and find both kinds of care listings.', required: ['search_providers', 'search_affordable_clinics', 'lookup_plan_network'] },
];
for (const s of finalSuite ? freshTools : developmentTools) {
  try { const r = await model.runTools({ ...s, tools }); const missing = s.required.filter(n => !r.results.has(n)); report.tools.push({ id: s.id, passed: !missing.length, missing, elapsed_ms: r.elapsed_ms, tool_trace: r.trace }); }
  catch (e) { report.tools.push({ id: s.id, passed: false, error: e.code || e.message }); }
  console.log(JSON.stringify(report.tools.at(-1)));
}
// Separate backend checks: a raw-model failure may safely fall back, but is never
// counted as a successful raw inference. These are fresh composed scenarios.
if (finalSuite) {
  const check = async (id, run) => { try { const detail = await run(); report.backend.push({ id, passed: true, ...detail }); } catch (e) { report.backend.push({ id, passed: false, error: e.code || e.message }); } };
  const assert = (condition, error) => { if (!condition) throw Error(error); };
  const service = createService({ tools, model });
  await check('fresh_absent_scan_and_partial_insurance', async () => {
    const r = await service.chat({ message: 'My ZIP is 12345 and my insurer is Mock Glacier. I have no idea which plan.', profile: { zip: '12345', insurance: { status: 'insured', payer: 'Mock Glacier' } } });
    assert(r.stage === 'ask_plan', 'must_ask_for_exact_plan'); assert(!r.profile.insurance.network, 'must_not_invent_network'); return { mode: r.model.mode, raw_model_error: r.model.error ?? null, stage: r.stage };
  });
  await check('fresh_current_year_rejects_future_payer_record', async () => {
    const r = await tools.call('lookup_plan_network', { insurance: { ...syntheticInsurance, coverage_year: 2026 }, zip: '12345' }); assert(r.status === 'unsupported' && r.providers.length === 0, 'wrong_year_match'); return { status: r.status };
  });
  await check('fresh_plan_change_does_not_reuse_old_network', async () => {
    const a = await service.chat({ profile: { zip: '12345', insurance: syntheticInsurance } });
    const b = await service.chat({ session_id: a.session_id, profile: { insurance: { status: 'insured', plan: 'Different Synthetic Plan' } } });
    assert(b.stage === 'ask_plan' && !b.profile.insurance.network && !b.profile.insurance.plan_id, 'stale_network_retained'); return { stage: b.stage };
  });
  await check('fresh_noisy_scan_with_directory_failure', async () => {
    const broken = createMcpTools(createTools(createDirectories({ fetchImpl: async () => { throw new DOMException('synthetic timeout', 'TimeoutError'); } })));
    const s = createService({ tools: broken, model });
    const r = await s.chat({ scan: { ...syntheticScan, quality: 'unclear', estimated_bpm: null }, profile: { zip: '12345', insurance: { status: 'uninsured' } }, action: 'search' });
    assert(r.stage === 'results', 'search_must_work_without_usable_scan'); assert(r.results.search_providers.status === 'error' && !r.results.search_providers.items.length, 'failure_must_not_invent_provider'); return { mode: r.model.mode, raw_model_error: r.model.error ?? null, directory_status: 'error' };
  });
  await check('fresh_invented_plan_tool_call_rejected', async () => {
    const injectedModel = createModel({ provider: 'compatible', model: 'explicitly-synthetic-protocol-double', baseUrl: 'http://localhost:4320/v1', timeoutMs: 1000 }, async () => Response.json({ choices: [{ message: { role: 'assistant', tool_calls: [{ id: 'bad', type: 'function', function: { name: 'lookup_plan_network', arguments: JSON.stringify({ insurance: { ...syntheticInsurance, network: 'Invented network' }, zip: '12345' }) } }] } }] }));
    try { await injectedModel.runTools({ tools, profile: { zip: '12345', insurance: syntheticInsurance }, message: 'find care' }); } catch (e) { assert(e.code === 'model_changed_plan', 'wrong_rejection'); return { synthetic_adversarial_double: true, rejected: e.code }; } throw Error('invented_plan_accepted');
  });
}
report.extraction_score = `${report.extraction.filter(r => r.passed).length}/${report.extraction.length}`;
report.tool_score = `${report.tools.filter(r => r.passed).length}/${report.tools.length}`;
const elapsed = report.extraction.map(r => r.elapsed_ms).sort((a, b) => a - b); report.extraction_median_ms = elapsed[Math.floor(elapsed.length / 2)];
await writeFile(new URL(finalSuite ? './results.final-held-out.json' : './results.local.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ extraction_score: report.extraction_score, tool_score: report.tool_score, extraction_median_ms: report.extraction_median_ms }));
if ([...report.extraction, ...report.tools, ...report.backend].some(r => !r.passed)) process.exitCode = 1;
