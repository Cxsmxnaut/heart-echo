import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createServer, request as httpRequest } from 'node:http';
import { mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const script = fileURLToPath(new URL('../scripts/start-judge.js', import.meta.url));
const fakeKey = 'SYNTHETIC_JUDGE_KEY_DO_NOT_SEND_123456789';
const inherited = {
  ...process.env,
  GEMINI_API_KEY: fakeKey, GOOGLE_API_KEY: fakeKey,
  LLM_PROVIDER: 'compatible', LLM_MODEL: 'synthetic-model', LLM_API_KEY: fakeKey,
  LLM_BASE_URL: 'http://127.0.0.1:1/v1', CARE_API_TOKEN: fakeKey,
  CARE_PAIRING_CODE: '123456', CARE_ALLOWED_HOSTS: 'untrusted.example',
  PORT: '1', START_MODEL: '1',
};

async function workspace(t) {
  const directory = await mkdtemp(join(tmpdir(), 'heartecho-judge-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const files = {
    '.env': `LLM_PROVIDER=compatible\nLLM_API_KEY=${fakeKey}\n`,
    '.env.gemini.local': `GEMINI_API_KEY=${fakeKey}\n`,
    '.demo-pairing.local.json': '{"synthetic":"must remain unchanged"}\n',
  };
  for (const [name, text] of Object.entries(files)) await writeFile(join(directory, name), text);
  return { directory, files };
}

async function launch(t, entry, args, cwd) {
  const child = spawn(process.execPath, [entry, ...args], { cwd, env: inherited, stdio: ['ignore', 'pipe', 'pipe'] });
  let stdout = '', stderr = '', settled = false;
  const exited = new Promise(resolve => child.once('close', (code, signal) => resolve({ code, signal })));
  let resolveReady, rejectReady;
  const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
  const timer = setTimeout(() => {
    if (!settled) { settled = true; rejectReady(Error('Judge demo did not become ready.')); }
  }, 15000);
  child.stdout.on('data', chunk => {
    stdout += String(chunk);
    const match = stdout.match(/^HEART_ECHO_JUDGE_READY (.+)$/m);
    if (match && !settled) {
      settled = true; clearTimeout(timer); resolveReady(JSON.parse(match[1]));
    }
  });
  child.stderr.on('data', chunk => { stderr += String(chunk); });
  child.once('error', () => {
    if (!settled) { settled = true; clearTimeout(timer); rejectReady(Error('Judge demo process could not start.')); }
  });
  exited.then(({ code }) => {
    if (!settled) { settled = true; clearTimeout(timer); rejectReady(Error(`Judge demo stopped before readiness (${code}). ${stderr}`)); }
  });
  t.after(async () => {
    clearTimeout(timer);
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
    const force = setTimeout(() => child.kill('SIGKILL'), 5000);
    force.unref();
    const result = await exited; clearTimeout(force);
    assert.equal(result.code, 0, 'The owned judge process shuts down normally');
    assert.equal(result.signal, null);
    assert.ok(!stdout.includes(fakeKey) && !stderr.includes(fakeKey), 'No inherited key reaches startup output');
  });
  const connection = await ready;
  return { ...connection, output: () => stdout };
}

async function chat(url, message) {
  const response = await fetch(url + '/api/v1/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: url },
    body: JSON.stringify({ message }), signal: AbortSignal.timeout(5000),
  });
  assert.equal(response.status, 200);
  return response.json();
}

test('judge CLI forces guided mode despite inherited keys and leaves local settings untouched', { timeout: 25000 }, async t => {
  const { directory, files } = await workspace(t);
  const connection = await launch(t, script, ['--no-open', '--port', '0'], directory);
  assert.equal(connection.mode, 'guided');
  assert.equal(connection.bind, '127.0.0.1');
  assert.equal(connection.directories, 'live_public_sources');
  assert.match(connection.output(), /no generated AI replies/i);
  const health = await (await fetch(connection.url + '/api/health')).json();
  assert.equal(health.model.mode, 'guided');
  assert.equal(health.model.configured, false);
  assert.notEqual(health.model.provider, 'gemini');
  const reply = await chat(connection.url, 'Hi');
  assert.equal(reply.model.mode, 'guided');
  assert.equal(reply.model.configured, false);
  assert.equal(reply.stage, 'ask_location');
  assert.equal((await fetch(connection.url + '/api/demo-connection')).status, 404);
  assert.equal((await fetch(connection.url + '/api/pair', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: connection.url },
    body: JSON.stringify({ code: '123456' }),
  })).status, 404);
  const untrustedHostStatus = await new Promise((resolve, reject) => {
    const request = httpRequest(connection.url + '/api/health', { headers: { Host: 'untrusted.example' } }, response => {
      response.resume(); response.on('end', () => resolve(response.statusCode));
    });
    request.on('error', reject); request.setTimeout(5000, () => request.destroy(Error('HTTP test timed out'))); request.end();
  });
  assert.equal(untrustedHostStatus, 403);
  assert.deepEqual((await readdir(directory)).sort(), Object.keys(files).sort());
  for (const [name, text] of Object.entries(files)) assert.equal(await readFile(join(directory, name), 'utf8'), text);
});

test('judge subprocess runs the real care/MCP flow with explicitly injected synthetic directories and no model fetch', { timeout: 25000 }, async t => {
  const { directory } = await workspace(t);
  const entry = join(directory, 'fixture-judge.mjs');
  const moduleUrl = relative => JSON.stringify(new URL(relative, import.meta.url).href);
  await writeFile(entry, `
import { startJudgeDemo } from ${JSON.stringify(pathToFileURL(script).href)};
import { createMcpTools } from ${moduleUrl('../src/tool-client.js')};
import { createTools } from ${moduleUrl('../src/tools.js')};
import { createDirectories } from ${moduleUrl('../src/directories.js')};
import { fixtureFetch } from ${moduleUrl('./fixtures.js')};
globalThis.fetch = () => { throw Error('Unexpected outbound/model request in fixture judge mode'); };
const tools = createMcpTools(createTools(createDirectories({ fetchImpl: fixtureFetch, timeoutMs: 500 })));
const demo = await startJudgeDemo({ port: 0, openBrowser: false, tools });
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => { await demo.close(); process.exit(0); });
`);
  const connection = await launch(t, entry, [], directory);
  assert.equal(connection.directories, 'injected_test_tools');
  const result = await chat(connection.url, 'Find care in 12345');
  assert.equal(result.stage, 'results');
  assert.equal(result.model.mode, 'guided');
  assert.equal(result.model.configured, false);
  const text = JSON.stringify(result.results);
  assert.match(text, /SYNTHETIC PROVIDER/);
  assert.match(text, /SYNTHETIC HEALTH CENTER/);
  assert.ok(result.tool_trace.length >= 2);
  assert.ok(result.tool_trace.every(item => item.origin !== 'model'));
});

test('judge startup chooses a free port and never stops the service already using its preferred port', { timeout: 25000 }, async t => {
  const { directory } = await workspace(t);
  const existing = createServer((req, res) => res.end('Existing service remains running'));
  await new Promise(resolve => existing.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => existing.close(resolve)));
  const occupied = existing.address().port;
  const connection = await launch(t, script, ['--no-open', '--port', String(occupied)], directory);
  assert.notEqual(Number(new URL(connection.url).port), occupied);
  assert.match(connection.output(), /existing service was left running/i);
  assert.equal(await (await fetch(`http://127.0.0.1:${occupied}`)).text(), 'Existing service remains running');
});

test('judge help and invalid arguments finish without starting a server', () => {
  const help = spawnSync(process.execPath, [script, '--help'], { env: inherited, encoding: 'utf8', timeout: 5000 });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /no AI key or model download/i);
  assert.doesNotMatch(help.stdout, /HEART_ECHO_JUDGE_READY/);
  const bad = spawnSync(process.execPath, [script, '--no-open', '--port', '-1'], { env: inherited, encoding: 'utf8', timeout: 5000 });
  assert.equal(bad.status, 1);
  assert.match(bad.stderr, /Choose a port from 0 to 65535/);
  assert.doesNotMatch(bad.stdout, /HEART_ECHO_JUDGE_READY/);
});
