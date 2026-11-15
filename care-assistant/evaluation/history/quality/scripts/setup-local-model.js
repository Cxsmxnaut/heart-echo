import { mkdir, access, rename, statfs, writeFile } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { selectedArtifact } from './model-artifacts.js';

const root = fileURLToPath(new URL('../', import.meta.url));
if (process.platform !== 'darwin' || process.arch !== 'arm64') throw Error('This pinned runtime is for Apple Silicon macOS. Configure another compatible endpoint on other systems.');
const selected = selectedArtifact();
const minimumGiB = selected.alias.endsWith('e4b') ? 16 : 12;
if (os.totalmem() < minimumGiB * 1024 ** 3) throw Error(`This model setup expects at least ${minimumGiB} GiB RAM. Select E2B or another endpoint on smaller machines.`);
await mkdir(new URL('../.cache/runtime/', import.meta.url), { recursive: true }); await mkdir(new URL('../.cache/models/', import.meta.url), { recursive: true });
async function run(command, args) { await new Promise((resolve, reject) => { const p = spawn(command, args, { cwd: root, stdio: 'inherit' }); p.on('error', reject); p.on('exit', code => code === 0 ? resolve() : reject(Error(`${command} exited ${code}`))); }); }
async function checksum(path) { const hash = createHash('sha256'); for await (const data of createReadStream(path)) hash.update(data); return hash.digest('hex'); }
const files = [
  { path: '.cache/runtime/llama.tar.gz', url: 'https://github.com/ggml-org/llama.cpp/releases/download/b12248/llama-b12248-bin-macos-arm64.tar.gz', sha256: '7f643b4d35803ccc69270302f3368d9e8a40f56f74ef5a266e6f686d9dc7d3c6' },
  selected,
];
for (const file of files) {
  const target = root + file.path;
  await mkdir(dirname(target), { recursive: true });
  let exists = true; try { await access(target); } catch { exists = false; }
  if (!exists) {
    const disk = await statfs(root); if (disk.bavail * disk.bsize < 5 * 1024 ** 3) throw Error('Keep at least 5 GiB free before downloading this model.');
    console.log(`Downloading public model/runtime into ${file.path}`);
    await run('curl', ['--fail', '--location', '--show-error', '--max-time', '900', '--retry', '2', file.url, '-o', `${target}.download`]);
    if (await checksum(`${target}.download`) !== file.sha256) throw Error(`Checksum mismatch: ${file.path}.download; no unverified file will be used.`);
    await rename(`${target}.download`, target);
  } else if (await checksum(target) !== file.sha256) throw Error(`Checksum mismatch: ${file.path}. Inspect it before replacing it.`);
}
let extracted = true; try { await access(root + '.cache/runtime/llama-b12248/llama-server'); } catch { extracted = false; }
if (!extracted) await run('tar', ['-xzf', root + files[0].path, '-C', root + '.cache/runtime']);
await writeFile(new URL('../.cache/model-provenance.json', import.meta.url), JSON.stringify({ checked_at: new Date().toISOString(), model_license: 'Apache-2.0 as declared by upstream model/conversion', files }, null, 2));
console.log('Local model files verified. Run npm run model in a separate terminal. No account, global installation, or service was created.');
