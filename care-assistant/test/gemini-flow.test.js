import test from 'node:test';
import assert from 'node:assert/strict';
import { createService } from '../src/service.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { fixtureFetch } from './fixtures.js';
import { conversationUpdate } from '../src/conversation.js';

function harness(reply = async () => 'A naturally generated answer.') {
  const prompts = [];
  const model = { provider: 'gemini', configured: true, status: () => ({ mode: 'llm', provider: 'gemini', model: 'synthetic' }), reply: async (message, history) => { prompts.push({ message, history }); return reply(message, history); } };
  return { prompts, service: createService({ model, tools: createTools(createDirectories({ fetchImpl: fixtureFetch })) }) };
}

test('natural insurer replies are stored as supplied and never inferred from symptoms', () => {
  const context = { awaitingPayer: true };
  assert.equal(conversationUpdate('I have Synthetic Healthcare', {}, context).profile.insurance.payer, 'Synthetic Healthcare');
  assert.equal(conversationUpdate('Sinthetic Healthcare', {}, context).profile.insurance.payer, 'Sinthetic Healthcare');
  assert.equal(conversationUpdate('My insurance is Synthetic Healthcare').profile.insurance.payer, 'Synthetic Healthcare');
  assert.equal(conversationUpdate('I have palpitations', {}, context).profile.insurance, undefined);
  assert.equal(conversationUpdate('I have no idea', {}, context).profile.insurance, undefined);
});

test('the whole care conversation gets generated replies without sending location or insurer to Gemini', async () => {
  const { prompts, service } = harness();
  const a = await service.chat({ message: 'Hello!' });
  assert.equal(a.model.used_this_turn, true); assert.equal(a.message, 'A naturally generated answer.');
  const b = await service.chat({ session_id: a.session_id, message: 'Find me care' });
  assert.equal(b.stage, 'ask_location'); assert.equal(b.model.used_this_turn, true);
  const c = await service.chat({ session_id: a.session_id, message: 'My ZIP is 12345' });
  assert.equal(c.stage, 'ask_plan'); assert.equal(c.model.used_this_turn, true);
  const d = await service.chat({ session_id: a.session_id, message: 'I have Sinthetic Healthcare' });
  assert.equal(d.profile.insurance.payer, 'Sinthetic Healthcare');
  assert.equal(d.stage, 'results'); assert.equal(d.model.used_this_turn, true);
  assert.equal(d.results.search_providers.items.length, 1);
  assert.match(d.message, /coverage is unverified/i);
  assert.ok(!JSON.stringify(prompts).includes('12345'));
  assert.ok(!JSON.stringify(prompts).includes('Sinthetic Healthcare'));
  const e = await service.chat({ session_id: a.session_id, message: 'What is a heart murmur?' });
  assert.equal(e.model.used_this_turn, true); assert.match(prompts.at(-1).message, /what is a heart murmur/i);
  const f = await service.chat({ session_id: a.session_id, message: 'What does my recording mean?' });
  assert.equal(f.model.used_this_turn, true); assert.ok(!prompts.at(-1).message.includes('my recording'));
});

test('a general question while insurance is pending is answered instead of restarting the insurance prompt', async () => {
  const { prompts, service } = harness();
  const a = await service.chat({ message: '12345' });
  assert.equal(a.stage, 'ask_plan');
  const b = await service.chat({ session_id: a.session_id, message: 'What can you help me with?' });
  assert.equal(b.model.used_this_turn, true);
  assert.equal(prompts.at(-1).message, 'What can you help me with?');
});

test('dangerous model claims fall back to safe app wording', async () => {
  const { service } = harness(async () => 'You have a murmur.');
  const r = await service.chat({ message: 'What does my recording mean?' });
  assert.equal(r.model.mode, 'guided_fallback');
  assert.equal(r.model.used_this_turn, false);
  assert.doesNotMatch(r.message, /you have a murmur/i);
});

test('a disclaimer about not knowing a diagnosis remains a conversational answer', async () => {
  const { service, prompts } = harness(async () => "I can't tell whether you have a murmur. A clinician can help assess your recording.");
  const r = await service.chat({ message: 'What does my recording mean?' });
  assert.equal(r.model.used_this_turn, true);
  assert.equal(prompts.length, 1);
  assert.match(r.message, /can't tell whether you have a murmur/i);
});

test('a reply requesting personal health details is retried without exposing those details', async () => {
  let count = 0;
  const { service, prompts } = harness(async () => ++count === 1 ? 'Did a doctor recently mention a murmur to you?' : 'Would you like general questions to ask a clinician?');
  const r = await service.chat({ message: 'What is a heart murmur?' });
  assert.equal(count, 2); assert.equal(r.model.used_this_turn, true);
  assert.match(r.message, /general questions/i);
  assert.match(prompts[1].message, /do not ask.*personal health/i);
});

test('invented claims of insurance coverage fall back instead of being shown', async () => {
  const { service } = harness(async () => 'These providers accept your insurance.');
  const a = await service.chat({ message: 'My ZIP is 12345' });
  const b = await service.chat({ session_id: a.session_id, message: 'I have Synthetic Healthcare' });
  assert.equal(b.stage, 'results'); assert.equal(b.model.mode, 'guided_fallback');
  assert.doesNotMatch(b.message, /providers accept your insurance/i);
  assert.match(b.message, /cannot verify coverage/i);
});

test('an inaccurate promise to find in-network providers is retried', async () => {
  let count = 0;
  const { service } = harness(async () => ++count === 1 ? 'Share your insurer so I can find in-network options.' : 'Would you like to share an insurer, or skip insurance for now?');
  const r = await service.chat({ message: 'My ZIP is 12345' });
  assert.equal(count, 2); assert.equal(r.model.used_this_turn, true);
  assert.doesNotMatch(r.message, /find in-network/i);
});

test('personal health statements are generalized and urgent chest pain stays local', async () => {
  const { service, prompts } = harness();
  const a = await service.chat({ message: 'Murmur detected in the recording.' });
  assert.equal(a.model.used_this_turn, true);
  assert.ok(!prompts[0].message.includes('Murmur detected in the recording'));
  const count = prompts.length;
  const b = await service.chat({ message: 'My chest hurts right now.' });
  assert.equal(b.stage, 'urgent_help'); assert.equal(prompts.length, count);
});
