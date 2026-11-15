import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { createApp } from '../src/server.js';
import { createService } from '../src/service.js';
import { createModel } from '../src/model.js';
import { createMcpTools } from '../src/tool-client.js';
import { createTools } from '../src/tools.js';
import { createDirectories } from '../src/directories.js';
import { fixtureFetch } from '../test/fixtures.js';

// Isolated Chrome process and synthetic fixtures. Never attaches to personal tabs.
let mode = 'ok';
let releaseInitial;
let initialGate = new Promise(resolve => { releaseInitial = resolve; });
const fetchImpl = async u => {
  if (initialGate) await initialGate;
  await new Promise(r => setTimeout(r, 150));
  if (mode === 'error') return new Response('', { status: 503 });
  if (mode === 'empty') return Response.json(String(u).includes('npiregistry') ? { result_count: 0, results: [] } : { features: [] });
  if (mode === 'long') {
    const source = await (await fixtureFetch(u)).json();
    if (source.results) { const one = source.results[0]; return Response.json({ result_count: 5, results: Array.from({ length: 5 }, (_, i) => ({ ...one, number: String(1234567800 + i), basic: { ...one.basic, last_name: `PROVIDER ${i + 1}` } })) }); }
    if (source.features) { const one = source.features[0].attributes; return Response.json({ features: Array.from({ length: 5 }, (_, i) => ({ attributes: { ...one, OBJECTID: i + 1, SITE_NM: `SYNTHETIC CLINIC ${i + 1}` } })) }); }
  }
  return fixtureFetch(u);
};
const service = createService({ tools: createMcpTools(createTools(createDirectories({ fetchImpl }))), model: createModel({ provider: 'guided' }) });
const server = await new Promise(resolve => { const s = createApp({ service }).listen(0, '127.0.0.1', () => resolve(s)); });
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = []; page.on('pageerror', e => errors.push(e.message));
const checks = [];
try {
  await page.goto(base); await expect(page.locator('#model-badge')).toHaveText('Guided help available');
  await expect(page.getByRole('log')).toContainText('What is your five-digit US ZIP code?');
  await page.getByLabel('US ZIP code').fill('12345'); await page.getByLabel('US ZIP code').press('Tab');
  await expect(page.getByLabel('Insurance', { exact: true })).toBeFocused(); checks.push('Keyboard focus follows labeled form inputs');
  await page.getByRole('button', { name: 'Find care options' }).click();
  await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'true'); await expect(page.getByRole('button', { name: 'Find care options' })).toBeDisabled();
  releaseInitial(); initialGate = null;
  await expect(page.locator('.provider-card')).toHaveCount(2); await expect(page.locator('.provider-card').first()).toContainText('SYNTHETIC PROVIDER');
  await expect(page.locator('.card-status').first()).toHaveText('Directory listing · contact to confirm'); checks.push('Loading state and source-backed synthetic provider/clinic cards');
  await page.getByLabel('Try a synthetic example').selectOption('unclear'); await page.getByRole('button', { name: 'Explain this scan' }).click();
  await expect(page.getByRole('log')).toContainText('no usable BPM estimate'); checks.push('Noisy scan explained without diagnosis');
  await page.getByLabel('Your message').fill('12345'); await page.getByLabel('Your message').press('Enter');
  await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'false'); await expect(page.getByLabel('Your message')).toHaveValue(''); checks.push('Enter sends chat message');
  await page.screenshot({ path: new URL('../test-results/desktop.png', import.meta.url).pathname, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.conversation')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (overflow) throw Error('Mobile page overflows horizontally');
  await page.screenshot({ path: new URL('../test-results/mobile.png', import.meta.url).pathname, fullPage: true }); checks.push('390px mobile layout has no horizontal overflow');
  await expect(page.locator('.source-date').first()).toContainText('Retrieved'); await expect(page.locator('.reason').first()).toContainText('12345'); await expect(page.getByRole('link', { name: 'Directions ↗' })).toHaveCount(2); checks.push('Visible source/date, actual match reasons, and directions');
  const beforeWhy = await page.locator('.provider-card').count(); await page.getByRole('button', { name: 'Why these options?' }).click(); await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'false'); await expect(page.getByRole('log')).toContainText('They were not selected because a scan diagnosed anything'); await expect(page.locator('.provider-card')).toHaveCount(beforeWhy); checks.push('Why follow-up retains the current cards');
  await page.getByRole('button', { name: 'Clear scan', exact: true }).click(); await expect(page.locator('#scan-origin')).toHaveText('No scan'); checks.push('Clear scan removes the attached synthetic snapshot');
  mode = 'long'; await page.getByRole('button', { name: 'Find care options' }).click(); await expect(page.locator('.provider-card')).toHaveCount(10);
  await page.getByRole('button', { name: 'Jump to chat ↓' }).click(); await expect(page.getByLabel('Your message')).toBeFocused(); await expect(page.getByLabel('Your message')).toBeInViewport();
  await page.getByLabel('Your message').fill('Why did you suggest these?'); await page.getByLabel('Your message').press('Enter'); await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'false'); await expect(page.locator('.provider-card')).toHaveCount(10); checks.push('Mobile jump control reaches and sends a follow-up after ten result cards');
  mode = 'empty'; await page.getByRole('button', { name: 'Find care options' }).click(); await expect(page.locator('.empty-state')).toHaveCount(2); await expect(page.locator('.fallbacks')).toContainText('HRSA Find a Health Center'); checks.push('Empty results offer official directory fallback');
  mode = 'error'; await page.getByRole('button', { name: 'Find care options' }).click(); await expect(page.locator('.empty-state').first()).toContainText('unavailable'); checks.push('Upstream failure is not displayed as no providers');
  await page.getByRole('button', { name: 'Clear everything' }).click(); await expect(page.getByLabel('US ZIP code')).toHaveValue(''); await expect(page.locator('#scan-origin')).toHaveText('No scan'); await expect(page.locator('.provider-card')).toHaveCount(0); await expect(page.locator('.message')).toHaveCount(1); checks.push('Full reset clears chat, profile, results and scan');
  const deletedIDs = []; await page.route('**/api/session/*', route => { deletedIDs.push(route.request().url()); return route.fulfill({ status: 503, body: '' }); });
  await page.getByRole('button', { name: 'Clear everything' }).click(); await expect(page.locator('#clear-warning')).toBeVisible(); const failedID = deletedIDs[0]; await page.unroute('**/api/session/*');
  const retries = []; page.on('request', r => { if (r.method() === 'DELETE') retries.push(r.url()); }); await page.getByRole('button', { name: 'Clear everything' }).click(); await expect(page.locator('#clear-warning')).toBeHidden(); if (!retries.includes(failedID)) throw Error('Failed server deletion ID was lost'); checks.push('Failed server deletion stays visible and retries the same session ID');
  await page.route('**/api/chat', async route => { const body = await service.chat(route.request().postDataJSON()); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...body, model: { mode: 'guided_fallback', model: 'synthetic-private-technical-identifier', error: 'model_unavailable' } }) }); });
  await page.getByLabel('Your message').fill('hello'); await page.getByRole('button', { name: 'Send message' }).click(); await expect(page.locator('#model-fallback')).toBeVisible(); await expect(page.locator('#model-badge')).toHaveText('Guided help available'); await expect(page.locator('#model-badge')).not.toContainText('model_unavailable'); await page.unroute('**/api/chat'); checks.push('Model outage uses plain-language guided help with codes behind details');
  await page.route('**/api/chat', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Synthetic service failure. Try again.' }) }));
  await page.getByLabel('Your message').fill('hello'); await page.getByRole('button', { name: 'Send message' }).click(); await expect(page.getByRole('alert')).toContainText('Synthetic service failure'); checks.push('Request error is visible and controls recover');
  if (errors.length) throw Error(errors.join('; ')); checks.push('No browser JavaScript errors');
  await mkdir(new URL('../docs/', import.meta.url), { recursive: true });
  await writeFile(new URL('../docs/browser-test-results.json', import.meta.url), JSON.stringify({ tested_at: new Date().toISOString(), mode: 'isolated Chrome; synthetic fixtures; real backend/MCP; guided mode', passed: true, checks }, null, 2) + '\n');
  console.log(JSON.stringify({ passed: true, checks }, null, 2));
} finally { releaseInitial(); await browser.close(); await new Promise(resolve => server.close(resolve)); }
