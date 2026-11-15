// Narrow, read-only payer adapter: The Health Plan's public Medicare Plan-Net directory.
// No arbitrary resource URLs, pagination URLs, or user-supplied FHIR queries are fetched.
export const THP_BASE = 'https://api.thehealthplanfhir.com/r4/public';
export const THP_DOCS = 'https://www.healthplan.org/patient-access-api';
const NETWORK_EXTENSION = 'http://hl7.org/fhir/us/davinci-pdex-plan-net/StructureDefinition/network-reference';
const norm = s => String(s ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
const refOK = (ref, type) => typeof ref === 'string' && new RegExp(`^${type}/[A-Za-z0-9.-]{1,64}$`).test(ref);
const covers = (period, day) => !!period?.start && !!period?.end && period.start.slice(0, 10) <= day && period.end.slice(0, 10) >= day;
function query(type, params) { const u = new URL(`${THP_BASE}/${type}`); for (const [k, v] of Object.entries(params)) u.searchParams.append(k, v); return u; }
function resources(bundle, type) {
  if (bundle.resourceType !== 'Bundle' || !Array.isArray(bundle.entry ?? [])) throw new Error('upstream_invalid_shape');
  return (bundle.entry ?? []).map(e => e.resource).filter(r => r?.resourceType === type && /^[A-Za-z0-9.-]{1,64}$/.test(r.id ?? ''));
}
export function supportsHealthPlan(insurance) { return norm(insurance?.payer) === 'the health plan'; }

export async function lookupHealthPlan({ insurance, zip }, json) {
  const retrieved_at = new Date().toISOString();
  const year = insurance.coverage_year ?? Number(retrieved_at.slice(0, 4));
  const effective_date = insurance.coverage_date ?? (year === Number(retrieved_at.slice(0, 4)) ? retrieved_at.slice(0, 10) : `${year}-01-01`);
  const source_url = String(query('InsurancePlan', { status: 'active', name: insurance.plan, _count: '100' }));
  const base = { source: 'The Health Plan public Medicare directory', source_url, documentation_url: THP_DOCS, retrieved_at, requested: insurance, coverage_year: year,
    effective_date, network_status: 'unverified', provider_participation_verified: false, items: [], providers: [],
    note: 'Directory evidence only. Confirm the plan year, practice, benefits, referrals, new-patient availability, and your cost with The Health Plan and the practice. This adapter covers this payer’s public Medicare directory only.' };
  const bundle = await json(source_url);
  const candidates = resources(bundle, 'InsurancePlan').filter(p => p.status === 'active' && norm(p.name) === norm(insurance.plan));
  base.items = candidates.map(p => ({ name: p.name, id: p.id, plan_id: p.identifier?.find(i => i.system === 'http://cms.gov/medicare/ma-plan-id')?.value ?? null, period: p.period ?? null,
    source_url: `${THP_BASE}/InsurancePlan/${p.id}`, retrieved_at, match_basis: 'exact_plan_name_only', network_status: 'unverified' }));
  if (Number(effective_date.slice(0, 4)) !== year) return { ...base, status: 'needs_details', match_basis: 'Coverage date and year conflict; no plan match was made.' };
  const matched = candidates.filter(p => covers(p.period, effective_date) && (!insurance.plan_id || p.identifier?.some(i => i.system === 'http://cms.gov/medicare/ma-plan-id' && i.value === insurance.plan_id)));
  if (matched.length !== 1) return { ...base, status: matched.length > 1 ? 'needs_details' : 'unsupported', match_basis: matched.length > 1 ? 'Multiple exact-name plans for this year. Supply the public CMS plan ID, not a member ID.' : 'No unique exact-name/public-plan-ID match for the requested year. Future/other-year candidates are not proof of current coverage.' };
  const plan = matched[0];
  if (!refOK(plan.ownedBy?.reference, 'Organization')) return { ...base, status: 'unsupported', match_basis: 'Plan owner reference missing.' };
  const owner = await json(`${THP_BASE}/${plan.ownedBy.reference}`);
  if (owner.resourceType !== 'Organization' || owner.active !== true || norm(owner.name) !== 'the health plan') return { ...base, status: 'unsupported', match_basis: 'Plan owner could not be matched.' };
  // A plan can name several networks; do not silently choose one by payer or plan name.
  const networks = [];
  for (const n of (plan.network ?? []).slice(0, 5)) {
    if (!refOK(n.reference, 'Organization')) continue;
    const network = await json(`${THP_BASE}/${n.reference}`);
    if (network.resourceType === 'Organization' && network.active === true && network.partOf?.reference === plan.ownedBy.reference && norm(network.name) === norm(insurance.network)) networks.push({ network, reference: n.reference });
  }
  if (networks.length !== 1) return { ...base, status: 'unsupported', match_basis: 'Exact network name and payer ownership were not uniquely established for this plan.' };
  const { network, reference } = networks[0];
  const chain = [
    { relation: 'exact_plan', url: `${THP_BASE}/InsurancePlan/${plan.id}` },
    { relation: 'plan_owner', url: `${THP_BASE}/${plan.ownedBy.reference}` },
    { relation: 'plan_network', url: `${THP_BASE}/${reference}` },
  ];
  const resolved = { ...base, status: 'matched_directory', plan_name: plan.name, plan_id: plan.identifier?.find(i => i.system === 'http://cms.gov/medicare/ma-plan-id')?.value, plan_period: plan.period,
    network_name: network.name, match_basis: 'Exact payer and plan name, one public plan ID/year, and exact active network linked from InsurancePlan.network; network belongs to the payer.', evidence: chain };
  if (!zip) return resolved;
  const u = query('PractitionerRole', { 'location.address-postalcode': zip, network: reference, active: 'true', '_include': 'PractitionerRole:location', _count: '8' });
  u.searchParams.append('_include', 'PractitionerRole:practitioner');
  const roles = await json(u);
  const included = new Map((roles.entry ?? []).map(e => e.resource).filter(Boolean).map(r => [`${r.resourceType}/${r.id}`, r]));
  const providers = [];
  for (const role of resources(roles, 'PractitionerRole')) {
    if (role.active !== true || !covers(role.period, effective_date) || !role.extension?.some(e => e.url === NETWORK_EXTENSION && e.valueReference?.reference === reference)) continue;
    if (!refOK(role.practitioner?.reference, 'Practitioner')) continue;
    const practitioner = included.get(role.practitioner.reference);
    if (practitioner?.resourceType !== 'Practitioner' || practitioner.active !== true) continue;
    const n = practitioner.name?.find(n => n.use === 'official') ?? practitioner.name?.[0];
    const name = n?.text || [...(n?.given ?? []), n?.family].filter(Boolean).join(' ');
    if (!name) continue;
    for (const lr of (role.location ?? []).slice(0, 5)) {
      if (!refOK(lr.reference, 'Location')) continue;
      const location = included.get(lr.reference); const address = location?.address;
      if (location?.resourceType !== 'Location' || location.status !== 'active' || !['US', 'USA'].includes(address?.country) || address.postalCode?.slice(0, 5) !== zip || !address.line?.length) continue;
      providers.push({ id: `thp:${role.id}:${location.id}`, name: name.slice(0, 300), kind: 'payer_directory_provider', specialty: (role.specialty ?? []).flatMap(s => s.coding ?? []).map(c => c.display || c.code).join(', ').slice(0, 400) || 'Confirm specialty',
        address: [...address.line, address.city, address.state, address.postalCode].filter(Boolean).join(', '), zip,
        phone: role.telecom?.find(t => t.system === 'phone')?.value ?? practitioner.telecom?.find(t => t.system === 'phone')?.value ?? null,
        source: base.source, source_url: `${THP_BASE}/PractitionerRole/${role.id}`, query_url: String(u), retrieved_at, source_updated_at: role.meta?.lastUpdated ?? null,
        network_status: 'directory_linked', network_basis: `Public directory links this practitioner role and this practice to ${network.name}, which is linked to ${plan.name}, public plan ID ${resolved.plan_id}, for ${year}. No member eligibility or cost check.`,
        plan_period: plan.period, role_period: role.period, effective_date, note: base.note,
        evidence: [...chain, { relation: 'practitioner_role_network_and_location', url: `${THP_BASE}/PractitionerRole/${role.id}` }, { relation: 'practitioner', url: `${THP_BASE}/${role.practitioner.reference}` }, { relation: 'practice_location', url: `${THP_BASE}/${lr.reference}` }] });
    }
  }
  return { ...resolved, providers: providers.slice(0, 8), provider_participation_verified: false, provider_linkage: providers.length ? 'directory_linked' : 'no_linked_results', provider_query_url: String(u),
    note: `${base.note} Linked results are not specialty-filtered or distance-ranked. No result does not mean out of network.` };
}
