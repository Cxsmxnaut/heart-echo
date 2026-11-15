import test from 'node:test';
import assert from 'node:assert/strict';
import { createService } from '../src/service.js';
import { conversationUpdate, mergeProfile } from '../src/conversation.js';
import { createModel } from '../src/model.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { ScanSummary } from '../src/schema.js';
import { scanState, emergencyMention } from '../src/knowledge.js';
import { fixtureFetch, syntheticInsurance, syntheticScan } from './fixtures.js';
function harness(model = createModel({ provider: 'guided' })) {
  let calls = 0; const core = createTools(createDirectories({ fetchImpl: async (...args) => { calls++; return fixtureFetch(...args); } }));
  return { service: createService({ tools: core, model }), count: () => calls };
}
const profile = { zip: '12345', specialty: 'internal_medicine', insurance: { ...syntheticInsurance, coverage_date: '2027-06-15' } };
test('capabilities answer explains the microphone/model/timing even when scan absent', async () => {
  const r = await harness().service.chat({ message: 'What does my heart sound scan measure?' });
  assert.equal(r.stage, 'scan_explanation'); assert.match(r.message, /microphone audio/); assert.match(r.message, /on-device model/); assert.doesNotMatch(r.message, /^No scan/);
});
test('single-field unknown network clears only network and retains payer/plan/year/date/category/ZIP', async () => {
  const { service } = harness(); const a = await service.chat({ profile, action: 'search' });
  const b = await service.chat({ session_id: a.session_id, message: 'I don’t know my network.' });
  assert.equal(b.profile.insurance.payer, profile.insurance.payer); assert.equal(b.profile.insurance.plan, profile.insurance.plan); assert.equal(b.profile.insurance.coverage_year, 2027); assert.equal(b.profile.insurance.coverage_date, '2027-06-15'); assert.equal(b.profile.insurance.network, undefined); assert.equal(b.profile.specialty, 'internal_medicine'); assert.equal(b.stage, 'results');
});
test('known insurer mentioned before unknown network is not cleared', () => {
  const u = conversationUpdate('My insurer is Humana, but I don’t know my network.', profile);
  assert.deepEqual(u.clear_fields, ['network']);
});
test('missing-network question names only the missing field', async () => {
  const r = await harness().service.chat({ profile: { zip: '12345', insurance: { status: 'insured', payer: 'Synthetic Payer', plan: 'Synthetic Plan' } } });
  assert.equal(r.stage, 'ask_plan'); assert.match(r.message, /need your network name/); assert.doesNotMatch(r.message, /need your insurer|need your full plan/);
});
test('no-insurance and cheaper follow-ups preserve other confirmed preferences', async () => {
  const { service } = harness(); const a = await service.chat({ profile, action: 'search' });
  const b = await service.chat({ session_id: a.session_id, message: 'I have no insurance now.' });
  assert.deepEqual(b.profile.insurance, { status: 'uninsured' }); assert.equal(b.profile.specialty, 'internal_medicine'); assert.match(b.message, /self-pay/); assert.doesNotMatch(b.message, /network unverified/i);
  const c = await service.chat({ session_id: a.session_id, message: 'Show cheaper options.' });
  assert.equal(c.profile.zip, '12345'); assert.equal(c.profile.specialty, 'internal_medicine'); assert.equal(c.profile.care_preference, 'affordable'); assert.deepEqual(c.tool_trace.map(t => t.name), ['search_affordable_clinics']); assert.match(c.message, /can’t rank prices/);
});
test('why explains saved results without a directory refresh', async () => {
  const { service, count } = harness(); const a = await service.chat({ profile: { zip: '12345', insurance: { status: 'uninsured' }, specialty: 'family_medicine' }, action: 'search' }); const before = count();
  const b = await service.chat({ session_id: a.session_id, message: 'Why did you suggest these?' });
  assert.equal(b.stage, 'explain_results'); assert.equal(count(), before); assert.equal(b.results_reused, true); assert.match(b.message, /12345/); assert.match(b.message, /family medicine/); assert.ok(b.results.search_providers.items[0].reason); assert.ok(b.results.search_providers.items[0].directions_url.startsWith('https://www.google.com/maps/dir/'));
});
test('explicit current/replacement ZIP wins over old ZIP or five-digit street number', () => {
  for (const message of ['I used 12345 before; my ZIP is 94303', 'My street number is 12345; ZIP code: 94303', 'Replace 12345 with 94303', 'Actually use ZIP 94303']) assert.equal(conversationUpdate(message, profile).profile.zip, '94303');
});
test('ambiguous five-digit numbers trigger a question instead of overwriting confirmed ZIP', async () => {
  const { service } = harness(); const a = await service.chat({ profile, action: 'search' });
  const b = await service.chat({ session_id: a.session_id, message: 'Maybe 94303 or 60614' }); assert.equal(b.stage, 'ask_location_correction'); assert.equal(b.profile.zip, '12345'); assert.deepEqual(b.tool_trace, []);
});
test('year-only correction clears incompatible old date and retains plan/network/ID', () => {
  const p = mergeProfile(profile, { insurance: { status: 'insured', coverage_year: 2026 } });
  assert.equal(p.insurance.coverage_date, undefined); assert.equal(p.insurance.plan_id, syntheticInsurance.plan_id); assert.equal(p.insurance.network, syntheticInsurance.network);
});
test('conversational year correction rejects the future plan and never silently changes year back', async () => {
  const { service } = harness(); const a = await service.chat({ profile, action: 'search' });
  const b = await service.chat({ session_id: a.session_id, message: 'Actually use 2026.' }); assert.equal(b.profile.insurance.coverage_year, 2026); assert.equal(b.profile.insurance.coverage_date, undefined); assert.equal(b.results.lookup_plan_network.status, 'unsupported'); assert.deepEqual(b.results.lookup_plan_network.providers, []);
});
test('skip insurance keeps supplied labels but does not fetch or claim coverage', async () => {
  const { service } = harness(); const a = await service.chat({ profile, action: 'search' });
  const b = await service.chat({ session_id: a.session_id, message: 'I would rather not share insurance details.' }); assert.equal(b.profile.coverage_preference, 'skip'); assert.equal(b.profile.insurance.plan, syntheticInsurance.plan); assert.equal(b.results.lookup_plan_network, undefined);
});
test('new/changed/cleared scan updates active context without changing care preferences', async () => {
  const { service } = harness(); const a = await service.chat({ profile, scan: syntheticScan, action: 'search' });
  const b = await service.chat({ session_id: a.session_id, scan: { ...syntheticScan, quality: 'unclear', estimated_bpm: null }, action: 'explain' }); assert.equal(b.scan_changed, true); assert.match(b.scan_explanation, /no usable BPM/); assert.equal(b.scan.estimated_bpm, null); assert.deepEqual(b.profile, a.profile);
  const c = await service.chat({ session_id: a.session_id, scan: null, action: 'explain' }); assert.equal(c.scan_state.kind, 'absent'); assert.equal(c.scan, null);
});
test('stale/unknown/future capture time is explicit; rounded BPM keeps full numeric API value', async () => {
  const old = { ...syntheticScan, estimated_bpm: 74.3333333333333, captured_at: '2020-01-01T00:00:00Z' };
  const r = await harness().service.chat({ scan: old, action: 'explain' }); assert.match(r.scan_explanation, /74 BPM/); assert.doesNotMatch(r.scan_explanation, /74\.333/); assert.equal(r.scan.estimated_bpm, old.estimated_bpm); assert.equal(r.scan_state.freshness, 'older'); assert.match(r.scan_explanation, /earlier snapshot/);
  assert.equal(scanState(syntheticScan).freshness, 'unknown'); assert.equal(scanState({ ...old, captured_at: '2099-01-01T00:00:00Z' }).freshness, 'future');
});
test('v1.1 analysis window differs from recording duration; absent timestamp remains absent', () => {
  const s = { ...syntheticScan, schema_version: '1.1', analysis_window_seconds: 8, timing_counters: { pattern_bpm: 148, cycle_bpm: 74 } }; assert.equal(ScanSummary.safeParse(s).success, true);
  assert.equal(ScanSummary.safeParse({ ...s, duration_seconds: 90 }).success, false); assert.equal(ScanSummary.safeParse({ ...s, quality: 'unclear', estimated_bpm: null }).success, false);
});
test('negated/historical/hypothetical symptoms do not interrupt routine care', async () => {
  for (const message of ['I have no chest pain. Find care in 12345.', 'I had chest pain last year. Find care.', 'Why does the footer mention chest pain?', 'What if someone has chest pain?']) assert.equal(emergencyMention(message), false);
  const { service } = harness(); const a = await service.chat({ message: 'I have chest pain right now.' }); assert.equal(a.stage, 'urgent_help');
  const b = await service.chat({ session_id: a.session_id, message: 'Find primary care in 12345. No insurance.' }); assert.equal(b.stage, 'results'); assert.doesNotMatch(b.message, /911/);
});
test('model unavailable gives explicit fallback and still completes the directory task', async () => {
  const model = { configured: true, status: () => ({ mode: 'llm', model: 'synthetic-unavailable' }), extract: async () => { throw Object.assign(Error(), { code: 'model_unavailable' }); } };
  const r = await harness(model).service.chat({ message: 'Find care in 12345. No insurance.' }); assert.equal(r.stage, 'results'); assert.equal(r.model.mode, 'guided_fallback'); assert.equal(r.model.used_this_turn, false); assert.ok(r.backend_adjustments.length);
});
test('missing model tool calls are visibly fallback, never counted as model completion', async () => {
  const model = { configured: true, status: () => ({ mode: 'llm' }), runTools: async () => ({ results: new Map(), trace: [], elapsed_ms: 1 }) };
  const r = await harness(model).service.chat({ profile: { zip: '12345', insurance: { status: 'unknown' } }, action: 'search' }); assert.equal(r.model.mode, 'guided_fallback'); assert.equal(r.model.error, 'model_incomplete_tools'); assert.ok(r.tool_trace.every(t => t.origin === 'service'));
});
test('payer-listed general-practice card never becomes a confirmed cardiology match', async () => {
  const r = await harness().service.chat({ profile: { ...profile, specialty: 'cardiology' }, action: 'search' });
  const card = r.results.lookup_plan_network.providers[0]; assert.equal(card.category_match, 'unverified'); assert.match(card.reason, /category has not been confirmed/); assert.equal(r.counts.category_listings, 0); assert.equal(r.counts.other_plan_practices, 1);
});
test('help explains distinct model roles, optional Watch, recording on iPhone and retry', async () => {
  const { service } = harness();
  const a = await service.chat({ message: 'Which AI is Gemma, and which model estimates BPM?' }); assert.equal(a.stage, 'app_help'); assert.match(a.message, /two separate AI roles/); assert.match(a.message, /Mac, not on the iPhone/);
  const b = await service.chat({ message: 'How do I take a reading in the iPhone app?' }); assert.match(b.message, /bare skin/); assert.match(b.message, /Breathe normally/);
  const c = await service.chat({ message: 'Do I need an Apple Watch?' }); assert.match(c.message, /optional/); assert.match(c.message, /never an input/);
});
