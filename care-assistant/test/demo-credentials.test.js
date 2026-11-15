import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, statSync, writeFileSync, symlinkSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadDemoCredentials } from '../src/demo-credentials.js';

test('a demo restart preserves the phone pairing in an owner-only file', t => {
  const dir = mkdtempSync(join(tmpdir(), 'care-pairing-')); t.after(() => rmSync(dir, { recursive: true }));
  const path = join(dir, 'pairing');
  const first = loadDemoCredentials(path);
  assert.deepEqual(loadDemoCredentials(path), first);
  assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.match(first.apiToken, /^[a-f0-9]{64}$/);
  assert.match(first.pairingCode, /^[0-9]{6}$/);
});

test('pairing refuses symlinks, broadly readable files and invalid credentials', t => {
  const dir = mkdtempSync(join(tmpdir(), 'care-pairing-')); t.after(() => rmSync(dir, { recursive: true }));
  const path = join(dir, 'pairing'); loadDemoCredentials(path);
  symlinkSync(path, join(dir, 'link'));
  assert.throws(() => loadDemoCredentials(join(dir, 'link')));
  chmodSync(path, 0o644); assert.throws(() => loadDemoCredentials(path));
  chmodSync(path, 0o600); writeFileSync(path, '{}'); assert.throws(() => loadDemoCredentials(path));
});
