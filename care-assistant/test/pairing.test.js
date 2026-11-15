import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp } from '../src/server.js';
import { createService } from '../src/service.js';
import { createModel } from '../src/model.js';
function app() { return createApp({ service: createService({ model: createModel({ provider: 'guided' }) }), apiToken: 'synthetic-test-token', pairingCode: '123456', allowedHosts: ['synthetic.local'] }); }
test('LAN host requires paired token even with a matching browser origin', async () => {
  const a = app();
  assert.equal((await request(a).post('/api/chat').set('Host','synthetic.local').set('Origin','http://synthetic.local').send({})).status, 401);
  assert.equal((await request(a).post('/api/chat').set('Host','synthetic.local').set('Authorization','Bearer synthetic-test-token').send({})).status, 200);
  assert.equal((await request(a).get('/api/health').set('Host','evil.invalid')).status, 403);
});
test('pairing accepts the same local hostname regardless of letter case', async () => {
  const a = createApp({ service: createService({ model: createModel({ provider: 'guided' }) }), apiToken: 'synthetic-test-token', pairingCode: '123456', allowedHosts: ['My-Mac.local'] });
  assert.equal((await request(a).post('/api/pair').set('Host', 'my-mac.local').send({ code: '123456' })).status, 200);
  assert.equal((await request(a).post('/api/pair').set('Host', 'MY-MAC.LOCAL').send({ code: '123456' })).status, 200);
  assert.equal((await request(a).post('/api/pair').set('Host', 'other-mac.local').send({ code: '123456' })).status, 403);
});
test('pairing validates code, returns token only on success, and limits guesses', async () => {
  const a=app();
  const bad=await request(a).post('/api/pair').set('Host','synthetic.local').send({code:'000000'});
  assert.equal(bad.status,401);assert.equal(bad.body.token,undefined);
  const good=await request(a).post('/api/pair').set('Host','synthetic.local').send({code:'123456'});
  assert.equal(good.status,200);assert.equal(good.body.token,'synthetic-test-token');
  for(let i=0;i<3;i++) await request(a).post('/api/pair').set('Host','synthetic.local').send({code:'000000'});
  assert.equal((await request(a).post('/api/pair').set('Host','synthetic.local').send({code:'123456'})).status,429);
});
