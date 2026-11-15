import express from 'express';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { timingSafeEqual } from 'node:crypto';
import { createService } from './service.js';
import { ScanSummary, publicValidation, scanJsonSchema } from './schema.js';
import { explainScan } from './knowledge.js';
import { z } from 'zod';
import { createMcpTools } from './tool-client.js';

const publicDir = fileURLToPath(new URL('../public/', import.meta.url));
export function createApp({ service = createService({ tools: createMcpTools() }), apiToken = process.env.CARE_API_TOKEN || '' } = {}) {
  const app = express(); app.disable('x-powered-by');
  const buckets = new Map();
  app.use((req, res, next) => {
    res.set({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" });
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(req.hostname)) return res.status(403).json({ error: 'local_host_required' });
    const origin = req.get('origin');
    if (origin && origin !== `${req.protocol}://${req.get('host')}`) return res.status(403).json({ error: 'same_origin_required' });
    if (req.path.startsWith('/api') && !['GET', 'HEAD'].includes(req.method)) {
      if (!origin && apiToken) {
        const supplied = Buffer.from(req.get('authorization') || ''); const expected = Buffer.from(`Bearer ${apiToken}`);
        if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return res.status(401).json({ error: 'api_token_required' });
      }
      if (!req.is('application/json') && req.method !== 'DELETE') return res.status(415).json({ error: 'json_required' });
      const key = req.ip; const time = Date.now();
      for (const [k, v] of buckets) if (time - v.start > 60000) buckets.delete(k);
      const bucket = buckets.get(key) ?? { start: time, count: 0 }; bucket.count++; buckets.set(key, bucket);
      if (bucket.count > 30) return res.status(429).json({ error: 'rate_limited', message: 'Please wait a minute before trying again.' });
    }
    next();
  });
  app.use(express.json({ limit: '16kb', strict: true }));
  app.get('/api/health', (req, res) => res.json({ status: 'ok', version: '0.3.0', model: service.model.status(), storage: 'memory_only_30_minutes' }));
  app.get('/api/v1/scan-summary/schema', (req, res) => res.json(scanJsonSchema()));
  app.post('/api/v1/scan-summary', (req, res) => { const scan = ScanSummary.parse(req.body); res.json({ scan, explanation: explainScan(scan) }); });
  app.post(['/api/chat', '/api/v1/chat'], async (req, res, next) => {
    try { const r = await service.chat(req.body); res.status(r.error ? r.status || 400 : 200).json(r); } catch (e) { next(e); }
  });
  app.delete('/api/session/:id', (req, res) => { service.deleteSession(req.params.id); res.status(204).end(); });
  app.use(express.static(publicDir, { etag: false, maxAge: 0 }));
  app.use('/api', (req, res) => res.status(404).json({ error: 'unknown_route' }));
  app.use((error, req, res, next) => {
    if (error instanceof z.ZodError) return res.status(400).json({ error: 'invalid_input', fields: publicValidation(error) });
    if (error.type === 'entity.too.large') return res.status(413).json({ error: 'request_too_large' });
    if (error.type === 'entity.parse.failed') return res.status(400).json({ error: 'invalid_json' });
    // Never log request bodies, model messages, tokens, or upstream error bodies.
    res.status(500).json({ error: 'request_failed', message: 'The request could not be completed. Please try again.' });
  });
  return app;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.PORT || 4318);
  const server = createApp().listen(port, '127.0.0.1', error => { if (!error) console.log(`Care assistant: http://127.0.0.1:${port}`); });
  server.on('error', e => { console.error(e.code === 'EADDRINUSE' ? 'Port is in use. Choose a different PORT.' : 'Server could not start.'); process.exitCode = 1; });
}
