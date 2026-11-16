import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { createService } from '../src/service.js';
import { createModel } from '../src/model.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { fixtureFetch } from './fixtures.js';

const search = { message: 'Find care', action: 'search', profile: { zip: '12345', coverage_preference: 'skip' } };
const tools = () => createTools(createDirectories({ fetchImpl: fixtureFetch }));
const config = { provider: 'gemini', model: 'synthetic-primary', fallbackModel: 'synthetic-backup', apiKey: 'synthetic-key', timeoutMs: 1000 };
const modelWith = reply => ({ provider: 'gemini', configured: true, status: () => ({ mode: 'llm', provider: 'gemini' }), reply });
const textResponse = text => Response.json({ candidates: [{ content: { parts: [{ text }] } }] });

test('a stalled reply returns validated cards and releases the chat without accepting a late answer', { timeout: 2000 }, async () => {
  let completeFirst;
  const calls = [];
  const model = modelWith(async (message, history, { signal }) => {
    calls.push({ message, history: structuredClone(history), signal });
    if (calls.length === 1) return new Promise(resolve => { completeFirst = resolve; });
    return 'You can review the directory cards and contact a clinic.';
  });
  const service = createService({ model, tools: tools(), geminiReplyTimeoutMs: 25 });
  const response = await service.chat(search);
  assert.equal(response.model.error, 'model_timeout');
  assert.equal(response.model.mode, 'guided_fallback');
  assert.equal(response.model.used_this_turn, false);
  assert.equal(response.results.search_providers.items.length, 1);
  assert.equal(response.results.search_affordable_clinics.items.length, 1);
  assert.match(response.message, /care listings/i);
  assert.equal(calls[0].signal.aborted, true);

  completeFirst('A stale generated answer that must never enter the conversation.');
  await delay(0);
  const next = await service.chat({ session_id: response.session_id, message: 'Thanks' });
  assert.equal(next.error, undefined);
  assert.equal(next.model.used_this_turn, true);
  assert.doesNotMatch(JSON.stringify(calls[1].history), /stale generated answer/);
  assert.equal(calls.length, 2);
});

test('the safety retry shares the original wording deadline and abort signal', { timeout: 2000 }, async () => {
  const signals = [];
  const model = modelWith(async (_message, _history, { signal }) => {
    signals.push(signal);
    if (signals.length === 1) return 'These providers accept your insurance.';
    return new Promise(() => {});
  });
  const response = await createService({ model, tools: tools(), geminiReplyTimeoutMs: 25 }).chat(search);
  assert.equal(signals.length, 2);
  assert.equal(signals[0], signals[1]);
  assert.equal(signals[0].aborted, true);
  assert.equal(response.model.error, 'model_timeout');
  assert.equal(response.model.used_this_turn, false);
  assert.doesNotMatch(response.message, /providers accept your insurance/i);
  assert.equal(response.results.search_providers.items.length, 1);
});

test('primary and fallback Gemini fetches use the same deadline signal and both stop within the service budget', { timeout: 2000 }, async () => {
  const signals = [];
  const model = createModel(config, async (_url, { signal }) => {
    signals.push(signal);
    if (signals.length === 1) return new Response('', { status: 503 });
    return new Promise((_, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
  });
  const response = await createService({ model, tools: tools(), geminiReplyTimeoutMs: 25 }).chat(search);
  assert.equal(signals.length, 2);
  assert.equal(signals[0], signals[1]);
  assert.equal(signals[1].aborted, true);
  assert.equal(response.model.error, 'model_timeout');
  assert.equal(response.model.used_this_turn, false);
  assert.equal(response.model.last_success_at, null);
  assert.equal(response.results.search_providers.items.length, 1);
});

test('an upstream reply arriving after the deadline cannot start a fallback or mark the model successful', { timeout: 2000 }, async () => {
  let finish;
  let requests = 0;
  const model = createModel(config, async () => {
    requests++;
    return new Promise(resolve => { finish = resolve; });
  });
  const response = await createService({ model, tools: tools(), geminiReplyTimeoutMs: 25 }).chat(search);
  assert.equal(response.model.error, 'model_timeout');
  finish(new Response('', { status: 503 }));
  await delay(0);
  assert.equal(requests, 1);
  assert.equal(model.status().last_success_at, null);
});

test('a shorter configured upstream timeout still applies inside the shared wording budget', { timeout: 2000 }, async () => {
  const model = createModel({ ...config, timeoutMs: 15 }, async (_url, { signal }) => new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  const response = await createService({ model, tools: tools(), geminiReplyTimeoutMs: 250 }).chat(search);
  assert.equal(response.model.error, 'model_timeout');
  assert.equal(response.model.used_this_turn, false);
  assert.equal(response.results.search_affordable_clinics.items.length, 1);
});

test('successful wording clears the service deadline instead of aborting after the reply', { timeout: 2000 }, async () => {
  let signal;
  const model = modelWith(async (_message, _history, options) => {
    signal = options.signal;
    return 'Review the directory cards and contact the clinic to confirm details.';
  });
  const response = await createService({ model, tools: tools(), geminiReplyTimeoutMs: 20 }).chat(search);
  assert.equal(response.model.used_this_turn, true);
  assert.equal(response.model.mode, 'llm');
  await delay(40);
  assert.equal(signal.aborted, false);
});

test('an already expired external deadline prevents any Gemini network request', async () => {
  const controller = new AbortController();
  controller.abort(new DOMException('Expired', 'TimeoutError'));
  let requests = 0;
  const model = createModel(config, async () => { requests++; return textResponse('Hello.'); });
  await assert.rejects(model.reply('Hello', [], { signal: controller.signal }), { code: 'model_timeout' });
  assert.equal(requests, 0);
});
