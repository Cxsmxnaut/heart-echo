import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSetupServer } from '../scripts/setup-gemini.js';

test('Gemini key setup only accepts same-origin local forms and saves privately', async t => {
  const dir = await mkdtemp(join(tmpdir(), 'heartecho-setup-test-'));
  const destination = join(dir, '.env.gemini.local');
  let saved = 0; const server = createSetupServer({ destination, onSaved: () => saved++ });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await new Promise(resolve => server.close(resolve)); await rm(dir, { recursive: true }); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const options = { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: base }, body: new URLSearchParams({ key: 'AQ.synthetic_key_1234567890123456' }) };
  assert.equal((await fetch(base)).status, 200);
  assert.equal((await fetch(base + '/save', { ...options, headers: { ...options.headers, Origin: 'http://attacker.invalid' } })).status, 403);
  assert.equal((await fetch(base + '/save', options)).status, 200);
  assert.equal((await stat(destination)).mode & 0o777, 0o600);
  assert.equal(await readFile(destination, 'utf8'), 'GEMINI_API_KEY=AQ.synthetic_key_1234567890123456\n');
  assert.equal(saved, 1);
});

test('Gemini key setup refuses to replace a symbolic link', async t => {
  const dir = await mkdtemp(join(tmpdir(), 'heartecho-setup-link-'));
  const target = join(dir, 'target'); const destination = join(dir, '.env.gemini.local');
  await writeFile(target, 'keep'); await symlink(target, destination);
  const server = createSetupServer({ destination }); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await new Promise(resolve => server.close(resolve)); await rm(dir, { recursive: true }); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const response = await fetch(base + '/save', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: base }, body: new URLSearchParams({ key: 'synthetic_key_1234567890123456' }) });
  assert.equal(response.status, 500); assert.equal(await readFile(target, 'utf8'), 'keep');
});
