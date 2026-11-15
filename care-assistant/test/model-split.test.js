import test from 'node:test';
import assert from 'node:assert/strict';
import { createModel } from '../src/model.js';
const empty = { zip: null, payer: null, plan: null, network: null, plan_id: null, coverage_year: null, coverage_date: null, insurance_status: null, specialty: null, clear_fields: [] };
const config = { provider: 'compatible', model: 'synthetic-protocol-double', baseUrl: 'http://127.0.0.1:4320/v1', timeoutMs: 1000, temperature: 0 };
test('intent and fields are independent small model tasks, then combined without rule correction', async () => {
  const requests = [];
  const model = createModel(config, async (url, options) => {
    const body = JSON.parse(options.body); requests.push(body);
    return Response.json({ choices: [{ message: { role: 'assistant', content: JSON.stringify(body.response_format.json_schema.name === 'care_intent' ? { intent: 'cheaper_options' } : empty) } }] });
  });
  const r = await model.extract('Show lower-cost clinics.'); assert.equal(r.intent, 'cheaper_options'); assert.equal(r.insurance, null); assert.equal(requests.length, 2);
  const intent = requests.find(r => r.response_format.json_schema.name === 'care_intent'); const fields = requests.find(r => r.response_format.json_schema.name === 'care_details');
  assert.deepEqual(Object.keys(intent.response_format.json_schema.schema.properties), ['intent']); assert.equal(fields.response_format.json_schema.schema.properties.intent, undefined); assert.equal(intent.max_tokens, 48); assert.equal(fields.chat_template_kwargs.enable_thinking, false);
});
test('raw wrong intent remains wrong for evaluation; backend corrections are separate', async () => {
  const model = createModel(config, async (url, options) => { const body = JSON.parse(options.body); return Response.json({ choices: [{ message: { role: 'assistant', content: JSON.stringify(body.response_format.json_schema.name === 'care_intent' ? { intent: 'other' } : empty) } }] }); });
  assert.equal((await model.extract('Find affordable care.')).intent, 'other');
});
test('split field extraction still rejects invented plan labels', async () => {
  const model = createModel(config, async () => Response.json({ choices: [{ message: { role: 'assistant', content: JSON.stringify({ ...empty, insurance_status: 'insured', payer: 'Invented Payer', network: 'Invented Network' }) } }] }));
  await assert.rejects(model.extractFields('Find care in my ZIP.'), error => error.code === 'model_invented_plan');
});
