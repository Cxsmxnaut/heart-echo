// One local process owns the model, care server and Bonjour registration.
// Secrets stay in memory; no public tunnel or global configuration is created.
import { spawn, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { loadDemoCredentials } from '../src/demo-credentials.js';
import { networkInterfaces } from 'node:os';
import { loadEnvFile } from 'node:process';
import { createApp } from '../src/server.js';
try { loadEnvFile(new URL('../.env.gemini.local', import.meta.url)); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
const port = Number(process.env.PORT || 4318);
const hostname = `${execFileSync('scutil', ['--get', 'LocalHostName'], { encoding: 'utf8' }).trim()}.local`;
const addresses = Object.values(networkInterfaces()).flat().filter(x => x.family === 'IPv4' && !x.internal).map(x => x.address);
const children = [];
const endpoint = `http://${hostname}:${port}`;
const { apiToken, pairingCode } = loadDemoCredentials(fileURLToPath(new URL('../.demo-pairing.local.json', import.meta.url)));
const server = createApp({ apiToken, pairingCode, allowedHosts: [hostname, ...addresses], demoConnection: { endpoint, note: 'Same trusted Wi-Fi only. Summary and chat travel to this Mac; audio stays on the phone.' } }).listen(port, '0.0.0.0', () => {
  console.log(`Heart Echo demo ready. Pair the iPhone from http://127.0.0.1:${port}/connect.html`);
  children.push(spawn('dns-sd', ['-R', 'Heart Echo Care', '_heartecho._tcp', 'local', String(port)], { stdio: 'ignore' }));
  if (process.env.OPEN_DEMO !== '0') spawn('open', [`http://127.0.0.1:${port}/connect.html`], { stdio: 'ignore' });
});
server.on('error', e => { console.error(e.code === 'EADDRINUSE' ? 'Demo port is already in use; no existing process was stopped.' : 'Demo server failed.'); process.exitCode = 1; });
if (process.env.START_MODEL !== '0' && !process.env.GEMINI_API_KEY && !process.env.GOOGLE_API_KEY) children.push(spawn(process.execPath, ['--env-file-if-exists=.env', 'scripts/start-local-model.js'], { stdio: 'inherit', env: process.env }));
function close() { for (const child of children) child.kill('SIGTERM'); server.close(); }
process.on('SIGINT', close); process.on('SIGTERM', close);
