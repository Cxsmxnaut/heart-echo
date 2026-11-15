import test from 'node:test';
import assert from 'node:assert/strict';
import { createService, mergeProfile } from '../src/service.js';
import { ScanSummary } from '../src/schema.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { createModel, validateExtraction } from '../src/model.js';
import { createMcpTools } from '../src/tool-client.js';
import { fixtureFetch, syntheticScan } from './fixtures.js';
const tools = () => createTools(createDirectories({ fetchImpl: fixtureFetch }));
const guided = () => createModel({ provider: 'guided' });
test('guided conversation asks location then exact plan and works with no scan', async () => {
  const service = createService({ tools: tools(), model: guided() }); const a = await service.chat({}); assert.equal(a.stage, 'ask_location'); assert.match(a.message, /does not diagnose/);
  const b = await service.chat({ session_id: a.session_id, message: '12345' }); assert.equal(b.stage, 'ask_plan');
  const c = await service.chat({ session_id: a.session_id, message: 'I am uninsured' }); assert.equal(c.stage, 'results'); assert.equal(c.results.search_providers.items.length, 1); assert.equal(c.model.mode, 'guided');
});
test('noisy scan stays non-diagnostic and still allows care search', async () => {
  const r = await createService({ tools: tools(), model: guided() }).chat({ scan: { ...syntheticScan, quality: 'unclear', estimated_bpm: null }, profile: { zip: '12345', insurance: { status: 'unknown' } }, action: 'search' });
  assert.equal(r.stage, 'results'); assert.match(r.scan_explanation, /no usable BPM/); assert.equal(r.results.search_providers.items.length, 1);
});
test('high BPM never selects a specialist or diagnoses AFib', async () => {
  const r = await createService({ tools: tools(), model: guided() }).chat({ scan: { ...syntheticScan, estimated_bpm: 180 }, profile: { zip: '12345', insurance: { status: 'unknown' } }, action: 'search' });
  assert.equal(r.results.search_providers.items[0].specialty, 'Family Medicine'); assert.match(r.scan_explanation, /does not diagnose/); assert.notEqual(r.profile.specialty, 'cardiology');
});
test('diagnosis questions get limitations, not diagnosis', async () => {
  const r = await createService({ tools: tools(), model: guided() }).chat({ message: 'Do I have AFib?', scan: syntheticScan }); assert.equal(r.stage, 'scan_explanation'); assert.match(r.message, /does not diagnose/);
});
test('mentioning or declining cardiology does not select it in guided mode', async () => {
  const s = createService({ tools: tools(), model: guided() });
  const a = await s.chat({ message: 'Do I need cardiology?', profile: { zip: '12345', insurance: { status: 'unknown' } }, action: 'search' }); assert.notEqual(a.profile.specialty, 'cardiology');
  const b = await s.chat({ session_id: a.session_id, message: 'Do not choose cardiology; I want primary care.', action: 'search' }); assert.equal(b.profile.specialty, 'family_medicine');
});
test('urgent symptom mention interrupts routine directory flow', async () => {
  const r = await createService({ tools: tools(), model: guided() }).chat({ message: 'I have chest pain and cannot breathe', profile: { zip: '12345' } }); assert.equal(r.stage, 'urgent_help'); assert.match(r.message, /911 now/); assert.deepEqual(r.results, {});
});
test('strict scan contract excludes diagnoses, raw recordings and noisy BPM', () => {
  for (const x of [{ ...syntheticScan, diagnosis: 'AFib' }, { ...syntheticScan, audio: 'private' }, { ...syntheticScan, quality: 'unclear' }, { ...syntheticScan, estimated_bpm: Infinity }, { ...syntheticScan, schema_version: '2.0' }]) assert.equal(ScanSummary.safeParse(x).success, false);
});
test('changing payer clears old plan/network and changing plan clears old network/ID', () => {
  const old = { insurance: { status: 'insured', payer: 'A', plan: 'A Plan', network: 'A Net', plan_id: 'H0000-001-000' } };
  assert.deepEqual(mergeProfile(old, { insurance: { status: 'insured', payer: 'B' } }).insurance, { status: 'insured', payer: 'B' });
  assert.equal(mergeProfile(old, { insurance: { status: 'insured', plan: 'B Plan' } }).insurance.network, undefined);
});
test('fabricated model extraction of a network or ZIP is rejected', () => {
  const base = { zip: null, insurance: null, specialty: null, intent: 'find_care' };
  assert.throws(() => validateExtraction({ ...base, zip: '99999' }, 'Find care in 12345'));
  assert.throws(() => validateExtraction({ ...base, insurance: { status: 'insured', payer: 'Aetna', network: 'Invented Net' } }, 'I have Aetna'));
  assert.throws(() => validateExtraction({ ...base, specialty: 'cardiology' }, 'My scan is 180 BPM'));
});
test('model adapter executes a synthetic protocol tool call and discards invented prose', async () => {
  let step = 0; const fetchImpl = async () => Response.json({ choices: [{ message: step++ === 0 ? { role: 'assistant', content: null, tool_calls: [{ id: 'a', type: 'function', function: { name: 'search_providers', arguments: '{"zip":"12345","specialty":"family_medicine"}' } }] } : { role: 'assistant', content: 'Fake Provider is definitely covered' } }] });
  const model = createModel({ provider: 'compatible', model: 'synthetic-protocol-double', baseUrl: 'http://localhost:4320/v1', timeoutMs: 1000 }, fetchImpl);
  const r = await model.runTools({ profile: { zip: '12345' }, scan: null, message: 'find care', tools: tools() }); assert.equal(r.results.get('search_providers').items[0].name, 'SYNTHETIC PROVIDER'); assert.equal(r.trace[0].origin, 'model'); assert.equal(r.message, undefined);
});
test('model cannot override user ZIP or exact plan, or execute an arbitrary tool', async () => {
  for (const [name, args] of [['search_providers', { zip: '99999', specialty: 'family_medicine' }], ['lookup_plan_network', { insurance: { status: 'insured', payer: 'invented', plan: 'invented', network: 'invented' } }], ['fetch_url', { url: 'https://evil.invalid' }]]) {
    const model = createModel({ provider: 'compatible', model: 'synthetic-protocol-double', baseUrl: 'http://localhost:4320/v1', timeoutMs: 1000 }, async () => Response.json({ choices: [{ message: { role: 'assistant', tool_calls: [{ id: 'x', type: 'function', function: { name, arguments: JSON.stringify(args) } }] } }] }));
    await assert.rejects(model.runTools({ profile: { zip: '12345' }, scan: null, message: 'find', tools: tools() }));
  }
});
test('model failure is visible and the deterministic public-data path still works', async () => {
  const model = { configured: true, status: () => ({ mode: 'llm', model: 'synthetic-double' }), extract: async () => { throw Object.assign(Error(), { code: 'model_timeout' }); } };
  const r = await createService({ tools: tools(), model }).chat({ message: '12345', profile: { zip: '12345', insurance: { status: 'unknown' } }, action: 'search' }); assert.equal(r.stage, 'results'); assert.equal(r.model.mode, 'guided_fallback'); assert.equal(r.model.error, 'model_timeout'); assert.equal(r.results.search_providers.items.length, 1);
});
test('expired sessions are removed and cannot be reused', async () => {
  let now = 0; const s = createService({ tools: tools(), model: guided(), clock: () => now, ttlMs: 10 }); const a = await s.chat({}); now = 11; const b = await s.chat({ session_id: a.session_id }); assert.equal(b.status, 410);
});
test('actual MCP in-memory transport lists and executes the same validated public tools', async () => {
  const client = createMcpTools(tools()); const r = await client.call('search_providers', { zip: '12345' }); assert.equal(r.items[0].name, 'SYNTHETIC PROVIDER'); await assert.rejects(client.call('fetch_url', { url: 'https://evil.invalid' })); await assert.rejects(client.call('search_providers', { zip: 'bad' }));
});
