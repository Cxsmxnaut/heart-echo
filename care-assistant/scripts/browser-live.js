import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
const base = process.env.CARE_BASE_URL || 'http://127.0.0.1:4318';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = []; page.on('pageerror', e => errors.push(e.message));
const checks = [];
const model_observations = [];
async function send(message) {
  await page.getByLabel('Your message').fill(message);
  const response = page.waitForResponse(r => r.url() === `${base}/api/chat` && r.request().method() === 'POST', { timeout: 120000 });
  await page.getByLabel('Your message').press('Enter'); const r = await response; expect(r.ok()).toBeTruthy();
  const data = await r.json(); await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'false'); model_observations.push({ stage: data.stage, model: data.model, backend_adjustments: data.backend_adjustments, tool_trace: data.tool_trace }); return data;
}
try {
  await page.goto(base); await expect(page.getByRole('log')).toContainText('What is your five-digit US ZIP code?'); await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'false');
  const a = await send('What does my heart sound scan measure?'); expect(a.message).toContain('microphone audio'); expect(a.stage).toBe('scan_explanation');
  const b = await send('My ZIP code is 94303.'); expect(b.stage).toBe('ask_plan');
  const c = await send('I have no insurance. Please find primary care in 94303.'); expect(c.stage).toBe('results'); await expect(page.locator('.provider-card')).not.toHaveCount(0);
  if (c.model.mode === 'guided_fallback') await expect(page.locator('#model-fallback')).toBeVisible();
  checks.push({ name: 'Browser task: app question → ZIP → insurance → live care results', passed: true, model: c.model.model, response_mode: c.model.mode, all_searches_selected_by_model: c.tool_trace.filter(t => t.origin === 'model' && t.name.startsWith('search_')).length === 2, tool_trace: [...a.tool_trace, ...c.tool_trace], live_cards: await page.locator('.provider-card').count() });
  await page.getByLabel('Insurance', { exact: true }).selectOption('insured');
  await page.getByLabel('Insurer / payer').fill('The Health Plan'); await page.getByLabel('Full plan name').fill('The Health Plan SecureCare Integrity Plan 3 (HMO)');
  await page.getByLabel('Network name').fill('THPWV Medicare Network'); await page.getByLabel('Public CMS plan ID').fill('H3672-014-000'); await page.getByLabel('Plan year').fill('2027'); await page.getByLabel('US ZIP code').fill('26003');
  const response = page.waitForResponse(r => r.url() === `${base}/api/chat` && r.request().method() === 'POST', { timeout: 120000 }); await page.getByRole('button', { name: 'Find care options' }).click();
  const p = await (await response).json(); await expect(page.locator('#results')).toHaveAttribute('aria-busy', 'false'); expect(p.results.lookup_plan_network.status).toBe('matched_directory'); expect(p.results.lookup_plan_network.providers.length).toBeGreaterThan(0);
  model_observations.push({ stage: p.stage, model: p.model, backend_adjustments: p.backend_adjustments, tool_trace: p.tool_trace });
  if (p.model.mode === 'guided_fallback') await expect(page.locator('#model-fallback')).toBeVisible();
  await expect(page.locator('.plan-panel')).toContainText('2027'); await expect(page.locator('.card-status.linked')).not.toHaveCount(0);
  checks.push({ name: 'Browser form: explicit future plan year and real payer-linked practice cards', passed: true, response_mode: p.model.mode, all_calls_selected_by_model: p.tool_trace.every(t => t.origin === 'model'), effective_date: p.results.lookup_plan_network.effective_date, plan_period: p.results.lookup_plan_network.plan_period, tool_trace: p.tool_trace });
  const why = await send('Why did you suggest these?'); expect(why.stage).toBe('explain_results'); expect(why.tool_trace).toEqual([]); await expect(page.locator('.category-caution')).toContainText('not confirmed');
  checks.push({ name: 'Why follow-up explains saved live cards and visibly qualifies the unverified category', passed: true, mode: why.model.mode, results_reused: why.results_reused });
  await mkdir(new URL('../test-results/', import.meta.url), { recursive: true });
  await page.screenshot({ path: new URL('../test-results/live-desktop.png', import.meta.url).pathname, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole('button', { name: 'Jump to chat ↓' }).click(); await expect(page.getByLabel('Your message')).toBeFocused(); await expect(page.getByLabel('Your message')).toBeInViewport();
  await page.screenshot({ path: new URL('../test-results/live-mobile.png', import.meta.url).pathname, fullPage: true });
  checks.push({ name: 'Live payer results at 390px with no horizontal overflow', passed: true });
  expect(errors).toEqual([]);
  await writeFile(new URL('../docs/browser-live-results.json', import.meta.url), JSON.stringify({ tested_at: new Date().toISOString(), mode: 'isolated Chrome; actual local Gemma 4; real MCP; LIVE public sources; synthetic user scenario only; UI completion and raw model success reported separately', passed: true, checks, model_observations }, null, 2) + '\n');
  console.log(JSON.stringify({ passed: true, checks }, null, 2));
} catch (e) {
  await writeFile(new URL('../docs/browser-live-results.json', import.meta.url), JSON.stringify({ tested_at: new Date().toISOString(), mode: 'actual local model and LIVE public sources, synthetic user scenario', passed: false, error: e.message, checks, model_observations }, null, 2) + '\n'); throw e;
} finally { await browser.close(); }
