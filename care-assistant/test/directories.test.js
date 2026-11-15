import test from 'node:test';
import assert from 'node:assert/strict';
import { createDirectories, safeWebUrl } from '../src/directories.js';
import { fixtureFetch, nppesFixture, hrsaFixture, payerFixture, syntheticInsurance } from './fixtures.js';

test('NPPES returns only source-backed active providers at the requested practice ZIP', async () => {
  const d = createDirectories({ fetchImpl: fixtureFetch }); const r = await d.searchProviders({ zip: '12345' });
  assert.equal(r.items.length, 1); assert.equal(r.items[0].name, 'SYNTHETIC PROVIDER'); assert.equal(r.items[0].network_status, 'unverified');
  assert.match(r.items[0].source_url, /1234567893$/); assert.ok(Date.parse(r.items[0].retrieved_at));
  assert.equal((await d.searchProviders({ zip: '99999' })).items.length, 0);
});
test('inactive providers, mailing-only addresses and unrelated specialties are filtered', async () => {
  for (const mutate of [p => { p.basic.status = 'D'; }, p => { p.addresses[0].address_purpose = 'MAILING'; }, p => { p.taxonomies[0].desc = 'Dentist'; }]) {
    const x = structuredClone(nppesFixture); mutate(x.results[0]);
    const r = await createDirectories({ fetchImpl: async () => Response.json(x) }).searchProviders({ zip: '12345' }); assert.equal(r.status, 'empty'); assert.deepEqual(r.items, []);
  }
});
test('malformed upstream data never becomes an invented provider', async () => {
  for (const payload of [{}, { results: 'bad' }, { error: 'failed' }]) {
    const r = await createDirectories({ fetchImpl: async () => Response.json(payload) }).searchProviders({ zip: '12345' }); assert.equal(r.status, 'error'); assert.deepEqual(r.items, []);
  }
});
test('empty upstream results include official directory fallbacks', async () => {
  const r = await createDirectories({ fetchImpl: async () => Response.json({ result_count: 0, results: [] }) }).searchProviders({ zip: '12345' });
  assert.equal(r.status, 'empty'); assert.equal(r.items.length, 0); assert.ok(r.fallbacks.every(f => f.url.startsWith('https://')));
});
test('upstream timeout is separate from empty results and has no invented data', async () => {
  const fetchImpl = async (u, { signal }) => new Promise((resolve, reject) => { signal.addEventListener('abort', () => reject(signal.reason)); });
  const pending = createDirectories({ fetchImpl, timeoutMs: 20 }).searchProviders({ zip: '12345' });
  // AbortSignal.timeout is unref'ed; keep the test alive until it fires.
  const keepAlive = setTimeout(() => {}, 100);
  const r = await pending; clearTimeout(keepAlive); assert.equal(r.error, 'upstream_timeout'); assert.equal(r.status, 'error'); assert.deepEqual(r.items, []);
});
test('HRSA retains provenance, labels fee limitations and rejects unsafe website URLs', async () => {
  const r = await createDirectories({ fetchImpl: fixtureFetch }).searchAffordableClinics({ zip: '12345' });
  assert.equal(r.items.length, 1); assert.equal(r.items[0].website, null); assert.match(r.items[0].source_url, /MapServer\/0\/1/); assert.match(r.items[0].note, /income, family size/); assert.match(r.fee_source_url, /hrsa.gov/);
});
test('HRSA filters inactive sites and wrong ZIPs even if upstream ignores filters', async () => {
  const x = structuredClone(hrsaFixture); x.features[0].attributes.HCC_STATUS_DESC = 'Inactive';
  const d = createDirectories({ fetchImpl: async () => Response.json(x) }); assert.equal((await d.searchAffordableClinics({ zip: '12345' })).items.length, 0);
  assert.equal((await createDirectories({ fetchImpl: fixtureFetch }).searchAffordableClinics({ zip: '99999' })).items.length, 0);
});
test('heart-care search excludes sites explicitly named as dental and keeps other sites unverified', async () => {
  const x = structuredClone(hrsaFixture);
  for (const name of ['Family Dentistry', 'Mobile DENTAL Unit', 'Dentist Office']) {
    const item = structuredClone(x.features[0]); item.attributes.SITE_NM = name; x.features.push(item);
  }
  const r = await createDirectories({ fetchImpl: async () => Response.json(x) }).searchAffordableClinics({ zip: '12345' });
  assert.deepEqual(r.items.map(item => item.name), ['SYNTHETIC HEALTH CENTER']);
  assert.match(r.items[0].specialty, /confirm services/);
});
test('missing exact-plan fields never trigger a payer lookup', async () => {
  const d = createDirectories({ fetchImpl: () => { throw Error('must not fetch'); } });
  const r = await d.lookupPlanNetwork({ insurance: { status: 'insured', payer: 'Synthetic Payer' } }); assert.equal(r.status, 'needs_details'); assert.equal(r.network_status, 'unverified');
});
test('unsupported insurer/plan does not imply the plan is invalid or out of network', async () => {
  const r = await createDirectories({ fetchImpl: fixtureFetch }).lookupPlanNetwork({ insurance: { status: 'insured', payer: 'Synthetic Payer', plan: 'Synthetic Gold', network: 'Synthetic Net' } });
  assert.equal(r.status, 'unsupported'); assert.equal(r.network_status, 'unverified'); assert.match(r.match_basis, /does not mean/);
});
test('even an exact CMS plan-name candidate is not verified coverage', async () => {
  const fetchImpl = async () => Response.json({ resourceType: 'Bundle', entry: [{ resource: { resourceType: 'InsurancePlan', id: 'synthetic', name: 'Synthetic Gold', status: 'active' } }] });
  const r = await createDirectories({ fetchImpl }).lookupPlanNetwork({ insurance: { status: 'insured', payer: 'Synthetic Payer', plan: 'Synthetic Gold', network: 'Synthetic Net' } });
  assert.equal(r.items[0].match_basis, 'exact_plan_name_only'); assert.equal(r.items[0].network_status, 'unverified'); assert.equal(r.provider_participation_verified, false);
});
test('payer directory requires exact payer/plan/network, public plan ID, year, role and location evidence', async () => {
  const r = await createDirectories({ fetchImpl: fixtureFetch }).lookupPlanNetwork({ insurance: syntheticInsurance, zip: '12345' });
  assert.equal(r.status, 'matched_directory'); assert.equal(r.providers.length, 1); assert.equal(r.providers[0].network_status, 'directory_linked'); assert.equal(r.provider_participation_verified, false);
  assert.equal(r.effective_date, '2027-01-01'); assert.ok(r.providers[0].evidence.length >= 6); assert.equal(r.providers[0].plan_period.start, '2027-01-01');
});
test('same plan name and provider cannot establish coverage in the wrong year', async () => {
  const d = createDirectories({ fetchImpl: fixtureFetch });
  for (const insurance of [{ ...syntheticInsurance, coverage_year: 2026 }, { ...syntheticInsurance, coverage_year: 2028 }]) {
    const r = await d.lookupPlanNetwork({ insurance, zip: '12345' }); assert.equal(r.status, 'unsupported'); assert.deepEqual(r.providers, []); assert.equal(r.network_status, 'unverified'); assert.equal(r.items[0].period.start, '2027-01-01');
  }
});
test('default year is current year, not the future year returned by a source', async () => {
  const { coverage_year, ...insurance } = syntheticInsurance;
  const r = await createDirectories({ fetchImpl: fixtureFetch }).lookupPlanNetwork({ insurance, zip: '12345' });
  assert.equal(r.coverage_year, new Date().getUTCFullYear()); if (r.coverage_year !== 2027) assert.equal(r.status, 'unsupported');
});
test('conflicting requested date/year and wrong public plan ID cannot match', async () => {
  const d = createDirectories({ fetchImpl: fixtureFetch });
  assert.equal((await d.lookupPlanNetwork({ insurance: { ...syntheticInsurance, coverage_date: '2026-11-14' } })).status, 'needs_details');
  assert.equal((await d.lookupPlanNetwork({ insurance: { ...syntheticInsurance, plan_id: 'H0000-002-000' } })).status, 'unsupported');
});
test('wrong network, inactive role, expired role, missing link, missing practitioner, wrong address cannot produce linked provider', async () => {
  const wrong = await createDirectories({ fetchImpl: fixtureFetch }).lookupPlanNetwork({ insurance: { ...syntheticInsurance, network: 'Wrong Network' }, zip: '12345' }); assert.equal(wrong.status, 'unsupported');
  for (const mutate of [x => { x.entry[0].resource.active = false; }, x => { x.entry[0].resource.period.end = '2026-12-31'; }, x => { x.entry[0].resource.extension = []; }, x => { x.entry[1].resource.active = false; }, x => { x.entry[2].resource.address.postalCode = '99999'; }]) {
    const fetchImpl = async url => { const x = payerFixture(url); if (new URL(url).pathname.endsWith('/PractitionerRole')) mutate(x); return Response.json(x); };
    const r = await createDirectories({ fetchImpl }).lookupPlanNetwork({ insurance: syntheticInsurance, zip: '12345' }); assert.equal(r.status, 'matched_directory'); assert.equal(r.providers.length, 0);
  }
});
test('malicious FHIR reference cannot cause arbitrary URL fetching', async () => {
  const seen = []; const fetchImpl = async url => { seen.push(String(url)); const x = payerFixture(url); if (new URL(url).pathname.endsWith('/InsurancePlan')) x.entry[0].resource.ownedBy.reference = 'https://evil.invalid/steal'; return Response.json(x); };
  const r = await createDirectories({ fetchImpl }).lookupPlanNetwork({ insurance: syntheticInsurance, zip: '12345' }); assert.equal(r.status, 'unsupported'); assert.ok(seen.every(u => u.startsWith('https://api.thehealthplanfhir.com/')));
});
test('tool input blocks SQL/FHIR injection, arbitrary specialities, excessive limits and private IDs', async () => {
  const d = createDirectories({ fetchImpl: fixtureFetch });
  for (const args of [{ zip: "12345' OR 1=1" }, { zip: '12345', specialty: 'https://evil.invalid' }, { zip: '12345', limit: 1000 }, { zip: '12345', url: 'https://evil.invalid' }]) await assert.rejects(d.searchProviders(args));
  await assert.rejects(d.lookupPlanNetwork({ insurance: { ...syntheticInsurance, member_id: 'do-not-accept' } }));
  assert.equal(safeWebUrl('javascript:alert(1)'), null); assert.equal(safeWebUrl('https://user:secret@example.com'), null);
});
