import test from 'node:test';
import assert from 'node:assert/strict';
import { selectedCareAdapter } from '../scripts/model-artifacts.js';

test('the E4B care demo selects its trained adapter by default', () => {
  const adapter = selectedCareAdapter({});
  assert.match(adapter.path, /care-e4b-seed001-lora-f16\.gguf$/);
  assert.equal(adapter.sha256, '513abc53c84f42116bec06877c6691de83d6c224e921f15039315121fc9ea6e3');
});

test('base and E2B options do not load the incompatible adapter', () => {
  assert.equal(selectedCareAdapter({ CARE_MODEL_ADAPTER: 'off' }), null);
  assert.equal(selectedCareAdapter({ MODEL_VARIANT: 'e2b' }), null);
  assert.throws(() => selectedCareAdapter({ MODEL_VARIANT: 'e2b', CARE_MODEL_ADAPTER: 'trained' }), /requires the E4B/);
  assert.throws(() => selectedCareAdapter({ CARE_MODEL_ADAPTER: 'unknown' }), /must be trained or off/);
});
