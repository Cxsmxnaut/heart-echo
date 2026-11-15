// Entirely synthetic records for deterministic tests; never shown as live data.
export const syntheticInsurance = { status: 'insured', payer: 'The Health Plan', plan: 'Synthetic Demonstration HMO', network: 'Synthetic Medicare Network', plan_id: 'H0000-001-000', coverage_year: 2027 };
export const syntheticScan = { schema_version: '1.0', measurement: 'experimental_heart_sound_timing', quality: 'usable', estimated_bpm: 74, synthetic: true };
export const nppesFixture = { result_count: 1, results: [{ number: '1234567893', basic: { status: 'A', first_name: 'SYNTHETIC', last_name: 'PROVIDER', last_updated: '2026-01-01' }, addresses: [{ address_purpose: 'LOCATION', country_code: 'US', postal_code: '123450000', address_1: '100 SYNTHETIC WAY', city: 'SYNTHETIC CITY', state: 'NY', telephone_number: '202-555-0100' }], taxonomies: [{ primary: true, desc: 'Family Medicine' }] }] };
export const hrsaFixture = { features: [{ attributes: { OBJECTID: 1, SITE_NM: 'SYNTHETIC HEALTH CENTER', SITE_ADDRESS: '200 SYNTHETIC WAY', SITE_CITY: 'SYNTHETIC CITY', SITE_STATE_ABBR: 'NY', SITE_ZIP_CD: '12345-0000', SITE_PHONE_NUM: '202-555-0101', SITE_URL: 'javascript:alert(1)', HCC_STATUS_DESC: 'Active' } }] };
export function payerFixture(url) {
  const u = new URL(url); const path = u.pathname;
  const resource = (resourceType, id, data) => ({ resourceType, id, ...data });
  if (path.endsWith('/InsurancePlan')) return { resourceType: 'Bundle', entry: [{ resource: resource('InsurancePlan', 'synthetic-plan', { status: 'active', name: syntheticInsurance.plan, identifier: [{ system: 'http://cms.gov/medicare/ma-plan-id', value: syntheticInsurance.plan_id }], period: { start: '2027-01-01', end: '2027-12-31' }, ownedBy: { reference: 'Organization/synthetic-payer' }, network: [{ reference: 'Organization/synthetic-network' }] }) }] };
  if (path.endsWith('/Organization/synthetic-payer')) return resource('Organization', 'synthetic-payer', { active: true, name: 'The Health Plan' });
  if (path.endsWith('/Organization/synthetic-network')) return resource('Organization', 'synthetic-network', { active: true, name: syntheticInsurance.network, partOf: { reference: 'Organization/synthetic-payer' } });
  if (path.endsWith('/PractitionerRole')) return { resourceType: 'Bundle', entry: [
    { resource: resource('PractitionerRole', 'synthetic-role', { active: true, period: { start: '2026-01-01', end: '2028-01-01' }, extension: [{ url: 'http://hl7.org/fhir/us/davinci-pdex-plan-net/StructureDefinition/network-reference', valueReference: { reference: 'Organization/synthetic-network' } }], practitioner: { reference: 'Practitioner/synthetic-person' }, location: [{ reference: 'Location/synthetic-location' }], telecom: [{ system: 'phone', value: '202-555-0100' }] }) },
    { resource: resource('Practitioner', 'synthetic-person', { active: true, name: [{ text: 'SYNTHETIC PROVIDER' }] }) },
    { resource: resource('Location', 'synthetic-location', { status: 'active', address: { country: 'USA', postalCode: '12345', line: ['100 SYNTHETIC WAY'], city: 'SYNTHETIC CITY', state: 'NY' } }) },
  ] };
  throw new Error('unexpected_fixture_request');
}
export function fixtureFetch(url) {
  const u = new URL(url);
  const body = u.hostname === 'npiregistry.cms.hhs.gov' ? nppesFixture : u.hostname === 'gisportal.hrsa.gov' ? hrsaFixture : u.hostname === 'api.thehealthplanfhir.com' ? payerFixture(u) : { resourceType: 'Bundle', type: 'searchset' };
  return Promise.resolve(Response.json(structuredClone(body)));
}
