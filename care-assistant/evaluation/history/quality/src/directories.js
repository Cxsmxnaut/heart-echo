import { providerInput, clinicInput, planInput, hasExactPlan } from './schema.js';
import { lookupHealthPlan, supportsHealthPlan } from './healthplan.js';

export const SOURCES = Object.freeze({
  nppes: 'https://npiregistry.cms.hhs.gov/api/',
  hrsa: 'https://gisportal.hrsa.gov/server/rest/services/HealthCareFacilities/PrimaryHealthCareFacilities_FS/MapServer/0',
  cms: 'https://directory.cms.gov/fhir',
});
export const NETWORK_NOTE = 'Network unverified. Call the insurer and this practice with your exact plan/network and this address. Directory inclusion does not establish appointment availability, benefit eligibility, or out-of-pocket cost.';
export const CLINIC_NOTE = 'Ask which services this site offers and whether you qualify for a sliding-fee discount. Discounts depend on income, family size, and clinic policies; no price is guaranteed.';
export const FALLBACKS = [
  { label: 'Search the official NPI Registry', url: 'https://npiregistry.cms.hhs.gov/' },
  { label: 'HRSA Find a Health Center', url: 'https://findahealthcenter.hrsa.gov/' },
  { label: 'CMS National Provider Directory', url: 'https://directory.cms.gov/' },
];
const taxonomy = { family_medicine: 'Family Medicine', internal_medicine: 'Internal Medicine', cardiology: 'Cardiovascular Disease' };
const now = () => new Date().toISOString();
const norm = s => String(s ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
const safeString = (s, max = 300) => typeof s === 'string' ? s.trim().slice(0, max) : '';
export function safeWebUrl(value) {
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : null; }
  catch { return null; }
}
function url(base, params) { const u = new URL(base); for (const [k, v] of Object.entries(params)) u.searchParams.set(k, String(v)); return u; }
class DirectoryError extends Error { constructor(code) { super(code); this.code = code; } }
export function createDirectories({ fetchImpl = fetch, timeoutMs = Number(process.env.UPSTREAM_TIMEOUT_MS || 12000) } = {}) {
  async function json(u) {
    try {
      const response = await fetchImpl(u, { signal: AbortSignal.timeout(timeoutMs), redirect: 'error', headers: { Accept: 'application/json', 'User-Agent': 'ChestBPM-CareAssistant/0.1 public-directory-demo' } });
      if (!response.ok) throw new DirectoryError(`upstream_http_${response.status}`);
      // Bound public response size as well as request duration.
      const reader = response.body.getReader(); let total = 0; const chunks = [];
      while (true) { const { done, value } = await reader.read(); if (done) break; total += value.length; if (total > 2_000_000) { await reader.cancel(); throw new DirectoryError('upstream_response_too_large'); } chunks.push(value); }
      const data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (data.error || data.Errors || data.resourceType === 'OperationOutcome') throw new DirectoryError('upstream_rejected_query');
      return data;
    } catch (e) {
      if (e instanceof DirectoryError) throw e;
      throw new DirectoryError(['TimeoutError', 'AbortError'].includes(e.name) ? 'upstream_timeout' : 'upstream_unavailable');
    }
  }
  function failure(error, queryUrl, source, extra = {}) {
    return { status: 'error', items: [], error: error.code || 'upstream_unavailable', source, source_url: String(queryUrl), retrieved_at: now(), network_status: 'unverified', note: NETWORK_NOTE, fallbacks: FALLBACKS, ...extra };
  }
  return {
    async searchProviders(raw) {
      const args = providerInput.parse(raw);
      const u = url(SOURCES.nppes, { version: '2.1', postal_code: args.zip, address_purpose: 'LOCATION', taxonomy_description: taxonomy[args.specialty], limit: args.limit });
      try {
        const data = await json(u); if (!Array.isArray(data.results) && data.result_count !== 0) throw new DirectoryError('upstream_invalid_shape');
        const retrieved_at = now();
        const items = (data.results ?? []).flatMap(p => {
          if (p.basic?.status !== 'A' || !/^\d{10}$/.test(String(p.number))) return [];
          const a = p.addresses?.find(a => a.address_purpose === 'LOCATION' && a.country_code === 'US' && a.postal_code?.slice(0, 5) === args.zip);
          const name = safeString(p.basic.organization_name || [p.basic.first_name, p.basic.middle_name, p.basic.last_name, p.basic.credential].filter(Boolean).join(' '));
          if (!a || !name || !a.address_1 || !p.taxonomies?.some(t => norm(t.desc) === norm(taxonomy[args.specialty]))) return [];
          return [{ id: `npi:${p.number}`, name, kind: 'provider', specialty: taxonomy[args.specialty], address: [a.address_1, a.address_2, a.city, a.state, a.postal_code].filter(Boolean).map(x => safeString(x)).join(', '), zip: args.zip, phone: safeString(a.telephone_number) || null,
            source: 'CMS NPPES', source_url: `https://npiregistry.cms.hhs.gov/provider-view/${p.number}`, query_url: String(u), retrieved_at, source_updated_at: p.basic.last_updated ?? null,
            network_status: 'unverified', network_basis: 'NPPES identity and practice location only; no plan-participation evidence.', note: NETWORK_NOTE }];
        }).slice(0, args.limit);
        return { status: items.length ? 'ok' : 'empty', items, source: 'CMS NPPES', source_url: String(u), retrieved_at, location_basis: `Exact ZIP ${args.zip}; not distance-ranked or a complete list.`, note: NETWORK_NOTE, fallbacks: FALLBACKS };
      } catch (e) { return failure(e, u, 'CMS NPPES'); }
    },
    async searchAffordableClinics(raw) {
      const args = clinicInput.parse(raw);
      const u = url(`${SOURCES.hrsa}/query`, { f: 'json', where: `SITE_ZIP_CD LIKE '${args.zip}%' AND HCC_STATUS_DESC = 'Active'`, outFields: 'OBJECTID,SITE_NM,SITE_ADDRESS,SITE_CITY,SITE_STATE_ABBR,SITE_ZIP_CD,SITE_PHONE_NUM,SITE_URL,HCC_STATUS_DESC', returnGeometry: false, resultRecordCount: args.limit, orderByFields: 'SITE_NM' });
      try {
        const data = await json(u); if (!Array.isArray(data.features)) throw new DirectoryError('upstream_invalid_shape');
        const retrieved_at = now();
        const items = data.features.flatMap(({ attributes: a }) => {
          if (!a?.SITE_NM || !a.SITE_ADDRESS || a.SITE_ZIP_CD?.slice(0, 5) !== args.zip || a.HCC_STATUS_DESC !== 'Active' || !Number.isInteger(a.OBJECTID)) return [];
          return [{ id: `hrsa:${a.OBJECTID}`, name: safeString(a.SITE_NM), kind: 'health_center', specialty: 'HRSA-listed health center site; confirm services', address: [a.SITE_ADDRESS, a.SITE_CITY, a.SITE_STATE_ABBR, a.SITE_ZIP_CD].filter(Boolean).map(x => safeString(x)).join(', '), zip: args.zip, phone: safeString(a.SITE_PHONE_NUM) || null, website: safeWebUrl(a.SITE_URL),
            source: 'HRSA Health Center Sites', source_url: `${SOURCES.hrsa}/${a.OBJECTID}?f=pjson`, query_url: String(u), retrieved_at, source_updated_at: null,
            network_status: 'unverified', network_basis: 'HRSA site listing; no exact-plan participation evidence.', note: `${CLINIC_NOTE} ${NETWORK_NOTE}` }];
        }).slice(0, args.limit);
        return { status: items.length ? 'ok' : 'empty', items, source: 'HRSA Health Center Sites', source_url: String(u), retrieved_at, location_basis: `Exact ZIP ${args.zip}; site services vary. Not distance-ranked.`, note: CLINIC_NOTE, fee_source_url: 'https://bphc.hrsa.gov/compliance/compliance-manual/chapter9', fallbacks: FALLBACKS };
      } catch (e) { return failure(e, u, 'HRSA Health Center Sites', { note: CLINIC_NOTE }); }
    },
    async lookupPlanNetwork(raw) {
      const { insurance, zip } = planInput.parse(raw);
      const base = { network_status: 'unverified', requested: insurance, provider_participation_verified: false, note: NETWORK_NOTE, fallbacks: FALLBACKS, items: [] };
      if (insurance.status !== 'insured') return { ...base, status: 'not_requested', match_basis: 'No exact insured plan supplied.' };
      if (!hasExactPlan(insurance)) return { ...base, status: 'needs_details', match_basis: 'Payer, full plan name, and network name are required; an insurer name alone is insufficient.' };
      if (supportsHealthPlan(insurance)) {
        try { return { ...await lookupHealthPlan({ insurance, zip }, json), fallbacks: FALLBACKS }; }
        catch (e) { return { ...failure(e, 'https://www.healthplan.org/patient-access-api', 'The Health Plan'), ...base, status: 'error', error: e.code || 'upstream_unavailable', match_basis: 'Payer directory unavailable; no coverage conclusion.' }; }
      }
      const u = url(`${SOURCES.cms}/InsurancePlan`, { name: insurance.plan, status: 'active', _count: 5 });
      try {
        const data = await json(u); if (data.resourceType !== 'Bundle' || (data.entry !== undefined && !Array.isArray(data.entry))) throw new DirectoryError('upstream_invalid_shape');
        const retrieved_at = now();
        const items = (data.entry ?? []).flatMap(({ resource: r }) => {
          if (r?.resourceType !== 'InsurancePlan' || !/^[A-Za-z0-9.-]{1,64}$/.test(r.id ?? '') || !r.name || r.status !== 'active') return [];
          return [{ id: r.id, name: safeString(r.name), source: 'CMS National Provider Directory', source_url: `${SOURCES.cms}/InsurancePlan/${r.id}`, retrieved_at,
            match_basis: norm(r.name) === norm(insurance.plan) ? 'exact_plan_name_only' : 'name_search_candidate',
            payer_display: safeString(r.ownedBy?.display) || null, network_displays: (r.network ?? []).map(n => safeString(n.display)).filter(Boolean).slice(0, 10),
            network_status: 'unverified', note: 'Catalog candidate only. Payer, network, service area, and provider participation have not been verified.' }];
        });
        return { ...base, status: items.length ? 'candidates' : 'unsupported', items, source: 'CMS National Provider Directory', source_url: String(u), retrieved_at,
          match_basis: items.length ? 'Plan-name search only; no provider-to-plan/practice linkage is implemented.' : 'No catalog candidate returned by this source. This does not mean the plan does not exist or that a provider is out of network.' };
      } catch (e) { return { ...failure(e, u, 'CMS National Provider Directory'), ...base, status: 'error', error: e.code, match_basis: 'Plan catalog unavailable; no coverage conclusion.' }; }
    },
  };
}
