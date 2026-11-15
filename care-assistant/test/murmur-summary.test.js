import test from 'node:test';
import assert from 'node:assert/strict';
import { ScanSummary } from '../src/schema.js';
import { explainScan } from '../src/knowledge.js';
import { createService } from '../src/service.js';
import { createModel } from '../src/model.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { fixtureFetch } from './fixtures.js';
const summary = finding => ({ schema_version: '1.2', measurement: 'experimental_heart_sound_timing', quality: 'unavailable', estimated_bpm: null, synthetic: false, recording_source: 'public_example', recording_seconds: 20, murmur: { finding, model_revision: 'Phase-aware M · 2026-11-14' } });
test('a real murmur finding survives unavailable BPM and is never called healthy', () => {
  for (const finding of ['present', 'absent', 'unsure']) {
    const scan = ScanSummary.parse(summary(finding));
    const text = explainScan(scan);
    assert.match(text, /No usable BPM/); assert.match(text, /not your heart recording/);
    assert.match(text, /Phone murmur accuracy has not been established/);
    assert.match(text, finding === 'present' ? /found a murmur-like/ : finding === 'absent' ? /does not rule out/ : /Unsure does not mean absent/);
  }
});
test('summary rejects legacy extensions, raw audio, missing revision and disease diagnoses', () => {
  for (const value of [{ ...summary('present'), schema_version: '1.1' }, { ...summary('present'), waveform: [1] }, { ...summary('present'), murmur: { finding: 'present' } }, summary('aortic_stenosis')]) assert.equal(ScanSummary.safeParse(value).success, false);
});
test('unsure/no-BPM summary can search affordable care and can be cleared', async () => {
  const service = createService({ tools: createTools(createDirectories({ fetchImpl: fixtureFetch })), model: createModel({ provider: 'guided' }) });
  const r = await service.chat({ scan: summary('unsure'), action: 'affordable', profile: { zip: '12345' } });
  assert.equal(r.stage, 'results'); assert.equal(r.scan.murmur.finding, 'unsure');
  assert.equal(r.results.search_affordable_clinics.items.length, 1);
  assert.equal(r.results.search_providers, undefined);
  const cleared = await service.chat({ session_id: r.session_id, scan: null, action: 'explain' });
  assert.equal(cleared.scan, null);
});
