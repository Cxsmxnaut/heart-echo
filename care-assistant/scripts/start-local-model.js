import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { selectedArtifact, selectedCareAdapter } from './model-artifacts.js';
const root = fileURLToPath(new URL('../', import.meta.url));
const selected = selectedArtifact();
const adapter = selectedCareAdapter();
if (adapter) {
  let bytes;
  try { bytes = await readFile(root + adapter.path); }
  catch { throw Error('The trained care adapter is missing. Restore it, or set CARE_MODEL_ADAPTER=off to use the base model.'); }
  if (createHash('sha256').update(bytes).digest('hex') !== adapter.sha256) throw Error('The trained care adapter did not match its recorded fingerprint.');
}
const processHandle = spawn(root + '.cache/runtime/llama-b12248/llama-server', [
  '-m', root + selected.path, '--alias', selected.alias, '--host', '127.0.0.1', '--port', process.env.MODEL_PORT || '4320',
  ...(adapter ? ['--lora', root + adapter.path] : []),
  '-c', '8192', '-np', '1', '-t', '2', '-tb', '2', '--cache-ram', '0', '--jinja', '--reasoning', 'off', '--reasoning-budget', '0', '--no-webui', '--log-disable',
], { cwd: root, stdio: 'inherit' });
processHandle.on('error', () => { console.error('Local runtime is missing or could not start. Run npm run model:setup, or configure another endpoint.'); process.exitCode = 1; });
processHandle.on('exit', code => { process.exitCode = code ?? 0; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => processHandle.kill(signal));
console.log(`Local ${adapter ? 'trained care adapter' : 'base model'} requested on http://127.0.0.1:${process.env.MODEL_PORT || '4320'}. Check /health for readiness. Ctrl+C stops this process only.`);
