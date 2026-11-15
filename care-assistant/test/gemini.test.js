import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createModel, modelConfig } from '../src/model.js';
import { createService } from '../src/service.js';
import { createApp } from '../src/server.js';

const config = () => modelConfig({ GEMINI_API_KEY: 'synthetic-test-key', LLM_PROVIDER: 'compatible', LLM_MODEL: 'old-local-model' });

test('a configured Gemini key selects Google without putting the key in the URL', async () => {
  let sent;
  const model = createModel(config(), async (url, options) => {
    sent = { url, ...options, body: JSON.parse(options.body) };
    return Response.json({ candidates: [{ content: { parts: [{ text: 'I can explain care options.' }] } }] });
  });
  assert.equal(config().provider, 'gemini');
  assert.equal(await model.reply('What can you help with?'), 'I can explain care options.');
  assert.match(sent.url, /^https:\/\/generativelanguage\.googleapis\.com\//);
  assert.ok(!sent.url.includes('synthetic-test-key'));
  assert.equal(sent.headers['x-goog-api-key'], 'synthetic-test-key');
  assert.equal(sent.body.contents.at(-1).parts[0].text, 'What can you help with?');
});

test('Gemini generates a real conversational reply without receiving the attached result', async () => {
  const requests = [];
  const model = createModel(config(), async (url, options) => {
    requests.push(JSON.parse(options.body));
    return Response.json({ candidates: [{ content: { parts: [{ text: 'A murmur is a sound a clinician can check.' }] } }] });
  });
  const service = createService({ model });
  const scan = { schema_version: '1.2', measurement: 'experimental_heart_sound_timing', quality: 'usable', estimated_bpm: 173, synthetic: false, recording_source: 'microphone', recording_seconds: 20, murmur: { finding: 'present', model_revision: 'private-revision' } };
  const r = await service.chat({ message: 'What is a heart murmur?', scan });
  assert.equal(r.message, 'A murmur is a sound a clinician can check.');
  assert.equal(r.model.provider, 'gemini'); assert.equal(r.model.used_this_turn, true);
  assert.equal(requests.length, 1);
  const body = JSON.stringify(requests[0]);
  assert.ok(!body.includes('private-revision')); assert.ok(!body.includes('173'));
});

test('personal details are replaced with generic context and emergencies stay local', async () => {
  const requests = [];
  const model = createModel(config(), async (url, options) => {
    requests.push(JSON.parse(options.body));
    return Response.json({ candidates: [{ content: { parts: [{ text: 'A clinician can help with a personal concern.' }] } }] });
  });
  const service = createService({ model });
  for (const message of ['What does my heart recording mean?', 'I have palpitations.', 'My name is Alex.', '72 BPM']) {
    const r = await service.chat({ message });
    assert.equal(r.model.used_this_turn, true);
    assert.ok(!JSON.stringify(requests.at(-1)).includes(message));
  }
  const beforeEmergency = requests.length;
  const urgent = await service.chat({ message: 'I have chest pain right now.' });
  assert.equal(urgent.stage, 'urgent_help'); assert.equal(requests.length, beforeEmergency);
});

test('a later general question does not send earlier personal questions to Gemini', async () => {
  const requests = [];
  const model = createModel(config(), async (url, options) => {
    requests.push(JSON.parse(options.body));
    return Response.json({ candidates: [{ content: { parts: [{ text: 'I can help you find care.' }] } }] });
  });
  const service = createService({ model });
  const first = await service.chat({ message: 'My heart recording is unclear.' });
  const second = await service.chat({ session_id: first.session_id, message: 'What can you help with?' });
  assert.equal(second.model.used_this_turn, true);
  assert.equal(requests.length, 2);
  assert.ok(requests.every(r => !JSON.stringify(r).includes('My heart recording is unclear')));
});

test('Gemini failures do not claim that the model responded', async () => {
  const model = createModel(config(), async () => new Response('', { status: 401 }));
  const r = await createService({ model }).chat({ message: 'Hello' });
  assert.equal(r.model.used_this_turn, false); assert.equal(r.model.mode, 'guided_fallback');
  assert.match(r.message, /could not respond/i);
});

test('a free-tier limit is explained rather than presented as a model answer', async () => {
  const model = createModel(config(), async () => new Response('', { status: 429 }));
  const r = await createService({ model }).chat({ message: 'Hello' });
  assert.equal(r.model.used_this_turn, false); assert.match(r.message, /request limit/i);
});

test('a rate-limited primary model can use Flash-Lite instead', async () => {
  const requested = [];
  const model = createModel(config(), async url => {
    requested.push(url);
    if (url.includes('gemini-3.5-flash:')) return new Response('', { status: 429 });
    return Response.json({ candidates: [{ content: { parts: [{ text: 'Hello from the backup model.' }] } }] });
  });
  const r = await createService({ model }).chat({ message: 'Hello' });
  assert.equal(r.model.used_this_turn, true);
  assert.equal(r.message, 'Hello from the backup model.');
  assert.equal(r.model.last_used_model, 'gemini-3.5-flash-lite');
  assert.equal(requested.length, 2);
  assert.match(requested[1], /gemini-3\.5-flash-lite/);
});

test('pairing identifies Gemini without exposing the Google key', async () => {
  const model = createModel(config(), async () => { throw Error('not needed'); });
  const app = createApp({ service: createService({ model }), apiToken: 'synthetic-pair-token', pairingCode: '123456', allowedHosts: ['example.local'] });
  const r = await request(app).post('/api/pair').set('Host', 'example.local').send({ code: '123456' });
  assert.equal(r.status, 200); assert.equal(r.body.model_provider, 'gemini');
  assert.ok(!JSON.stringify(r.body).includes('synthetic-test-key'));
});
