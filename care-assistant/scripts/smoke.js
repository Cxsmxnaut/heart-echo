import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { createDirectories } from '../src/directories.js';
import { createMcpTools } from '../src/tool-client.js';
import { createModel } from '../src/model.js';
import { createService } from '../src/service.js';

// All input is a synthetic demonstration scenario. Directory records are LIVE public data.
const report = { started_at: new Date().toISOString(), data: 'live public directories; synthetic user/scans only', checks: [] };
const d = createDirectories();
for (const [name, run] of [
  ['NPPES exact ZIP', () => d.searchProviders({ zip: '94303' })],
  ['HRSA exact ZIP', () => d.searchAffordableClinics({ zip: '94303' })],
  ['CMS unsupported plan remains unverified', () => d.lookupPlanNetwork({ insurance: { status: 'insured', payer: 'Synthetic Payer', plan: 'Synthetic nonexistent test plan 891', network: 'Synthetic Network' } })],
  ['The Health Plan 2027 exact directory chain', () => d.lookupPlanNetwork({ zip: '26003', insurance: { status: 'insured', payer: 'The Health Plan', plan: 'The Health Plan SecureCare Integrity Plan 3 (HMO)', network: 'THPWV Medicare Network', plan_id: 'H3672-014-000', coverage_year: 2027 } })],
  ['The Health Plan 2026 rejects future plan', () => d.lookupPlanNetwork({ zip: '26003', insurance: { status: 'insured', payer: 'The Health Plan', plan: 'The Health Plan SecureCare Integrity Plan 3 (HMO)', network: 'THPWV Medicare Network', plan_id: 'H3672-014-000', coverage_year: 2026 } })],
]) {
  const start = performance.now();
  try {
    const r = await run(); assert.notEqual(r.status, 'error');
    if (name.includes('2027')) { assert.equal(r.status, 'matched_directory'); assert.ok(r.providers.length > 0); assert.ok(r.providers.every(p => p.evidence.length >= 6)); }
    if (name.includes('2026')) { assert.equal(r.status, 'unsupported'); assert.equal(r.providers.length, 0); }
    if (name.includes('CMS unsupported')) assert.equal(r.network_status, 'unverified');
    report.checks.push({ name, passed: true, status: r.status, items: r.items?.length || 0, linked_practices: r.providers?.length || 0, elapsed_ms: Math.round(performance.now() - start), source_url: r.source_url, retrieved_at: r.retrieved_at });
  } catch (e) { report.checks.push({ name, passed: false, error: e.code || e.message }); }
  console.log(JSON.stringify(report.checks.at(-1)));
}
const model = createModel();
if (model.configured) {
  const service = createService({ tools: createMcpTools(), model }); const start = performance.now();
  try {
    const a = await service.chat({ message: 'What does my heart sound scan measure?' }); assert.equal(a.model.mode, 'llm'); assert.ok(a.tool_trace.some(t => t.origin === 'model' && t.name === 'get_app_context'));
    const b = await service.chat({ session_id: a.session_id, message: 'Find primary care in ZIP 94303. I have no insurance.' });
    assert.equal(b.stage, 'results'); assert.equal(b.model.mode, 'llm'); assert.ok(b.tool_trace.some(t => t.origin === 'model' && t.name.startsWith('search_')));
    assert.ok(b.results.search_providers.items.length + b.results.search_affordable_clinics.items.length > 0);
    report.checks.push({ name: 'Real model conversation + MCP execution + live directory results', passed: true, model: model.status().model, elapsed_ms: Math.round(performance.now() - start), turns: 2, tool_trace: [...a.tool_trace, ...b.tool_trace] });
  } catch (e) { report.checks.push({ name: 'Real model conversation + MCP execution + live directory results', passed: false, error: e.code || e.message }); }
} else report.checks.push({ name: 'Real model conversation', passed: false, error: 'model_not_configured: set LLM_PROVIDER=compatible, LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY if required.' });
console.log(JSON.stringify(report.checks.at(-1)));
report.passed = report.checks.every(c => c.passed); report.completed_at = new Date().toISOString();
await writeFile(new URL('../docs/live-smoke-results.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
if (!report.passed) process.exitCode = 1;
