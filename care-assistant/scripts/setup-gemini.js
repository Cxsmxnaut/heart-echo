// A short-lived Mac-only page for entering a key without putting it in chat or shell history.
import { createServer } from 'node:http';
import { open, rename, lstat, unlink } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const page = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Connect Gemini to Heart Echo</title><style>body{font:17px system-ui;max-width:620px;margin:8vh auto;padding:0 24px;line-height:1.5;color:#222}input{font:inherit;width:100%;box-sizing:border-box;padding:12px}button{font:inherit;background:#bf1233;color:white;border:0;border-radius:10px;padding:12px 20px;margin-top:18px}a{color:#9b1230}</style><h1>Connect Gemini</h1><p>Paste your Google AI Studio API key below. It is stored on this Mac and used to connect to Google; it is not sent in the chat.</p><p>Google may use free-tier messages to improve its products. Do not enter personal or health information in free-tier Gemini chat. Heart Echo does not send your recorded result to Gemini.</p><p><a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Get an API key from Google AI Studio</a></p><form method="post" action="/save"><label for="key">Gemini API key</label><input id="key" name="key" type="password" autocomplete="off" required minlength="20" maxlength="200"><button type="submit">Save key on this Mac</button></form></html>`;

export function createSetupServer({ destination = fileURLToPath(new URL('../.env.gemini.local', import.meta.url)), onSaved = () => {} } = {}) {
  const server = createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const port = server.address()?.port;
    const expected = `127.0.0.1:${port}`;
    if (req.socket.remoteAddress !== '127.0.0.1' || req.headers.host !== expected) { res.writeHead(403).end('Local Mac access only.'); return; }
    if (req.method === 'GET' && req.url === '/') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end(page); return; }
    if (req.method !== 'POST' || req.url !== '/save' || req.headers.origin !== `http://${expected}` || !/^application\/x-www-form-urlencoded(?:;|$)/i.test(req.headers['content-type'] || '')) { res.writeHead(403).end('Request not allowed.'); return; }
    let body = '';
    for await (const chunk of req) { body += chunk; if (body.length > 1024) { res.writeHead(413).end('Request too large.'); return; } }
    const key = new URLSearchParams(body).get('key') || '';
    if (!/^[A-Za-z0-9_.-]{20,200}$/.test(key)) { res.writeHead(400).end('This does not look like an API key. Go back and try again.'); return; }
    const temp = `${destination}.${randomUUID()}.tmp`;
    try {
      try { const info = await lstat(destination); if (!info.isFile() || info.isSymbolicLink()) throw Error('unsafe_destination'); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      const file = await open(temp, 'wx', 0o600);
      try { await file.writeFile(`GEMINI_API_KEY=${key}\n`); } finally { await file.close(); }
      await rename(temp, destination);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end('<!doctype html><title>Key saved</title><h1>Key saved on this Mac</h1><p>Return to Codex so the connection can be tested.</p>');
      onSaved();
    } catch { await unlink(temp).catch(() => {}); res.writeHead(500).end('Could not save the key locally.'); }
  });
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = createSetupServer({ onSaved: () => console.log('Gemini key saved locally.') });
  server.listen(Number(process.env.GEMINI_SETUP_PORT || 0), '127.0.0.1', () => {
    const url = `http://127.0.0.1:${server.address().port}/`;
    console.log(`Gemini setup page: ${url}`);
    if (process.env.OPEN_SETUP !== '0' && process.platform === 'darwin') spawn('open', [url], { stdio: 'ignore' });
  });
}
