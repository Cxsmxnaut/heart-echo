const $ = id => document.getElementById(id);
let sessionId; let scan = null; let scanPending = true; let busy = false;
const pendingDeletes = new Set();
$('coverage-year').value = new Date().getFullYear();
if (window.matchMedia('(max-width: 720px)').matches) document.querySelector('.details-panel').open = false;
function element(tag, text, className) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (className) e.className = className; return e; }
function link(label, href) { const a = element('a', label); try { const u = new URL(href); if (!['https:', 'http:', 'tel:'].includes(u.protocol)) return element('span', label); a.href = u.href; if (u.protocol !== 'tel:') { a.target = '_blank'; a.rel = 'noopener noreferrer'; } } catch { return element('span', label); } return a; }
function addMessage(role, text) { const e = element('article', undefined, `message ${role}`); e.append(element('div', role === 'user' ? 'You' : 'Chest BPM assistant', 'speaker'), element('p', text)); $('messages').append(e); }
function setBusy(value) { busy = value; document.querySelectorAll('button,input,select').forEach(e => { e.disabled = value; }); $('results').setAttribute('aria-busy', String(value)); $('request-status').textContent = value ? 'Checking your details and official sources. This may take a moment…' : ''; }
function profileFromForm() {
  const status = $('insurance-status').value; const insurance = { status };
  if (status === 'insured') {
    for (const field of ['payer', 'plan', 'network']) if ($(field).value.trim()) insurance[field] = $(field).value.trim();
    if ($('plan-id').value.trim()) insurance.plan_id = $('plan-id').value.trim();
    if ($('coverage-year').value) insurance.coverage_year = Number($('coverage-year').value);
  }
  return { ...($('zip').value ? { zip: $('zip').value } : {}), insurance, specialty: $('specialty').value, coverage_preference: status === 'insured' ? 'check_if_possible' : 'skip' };
}
function updateProfile(profile) {
  $('zip').value = profile.zip || '';
  $('specialty').value = profile.specialty || 'family_medicine';
  if (profile.insurance) {
    $('insurance-status').value = profile.insurance.status;
    for (const key of ['payer', 'plan', 'network']) $(key).value = profile.insurance[key] || '';
    $('plan-id').value = profile.insurance.plan_id || '';
    $('coverage-year').value = profile.insurance.coverage_year || new Date().getFullYear();
  }
  $('plan-fields').hidden = $('insurance-status').value !== 'insured';
}
function sourceDetails(card, parent) {
  const details = element('details'); details.append(element('summary', 'Evidence & limits'));
  details.append(element('p', card.network_basis || card.match_basis || 'Participation has not been verified.'));
  if (card.retrieved_at) details.append(element('p', `Retrieved: ${new Date(card.retrieved_at).toLocaleString()}. This is the retrieval time, not the plan’s effective date.`));
  if (card.source_updated_at) details.append(element('p', `Source record updated: ${card.source_updated_at}`));
  if (card.plan_period) details.append(element('p', `Plan period: ${card.plan_period.start?.slice(0, 10)} to ${card.plan_period.end?.slice(0, 10)}.`));
  if (card.effective_date) details.append(element('p', `Requested effective date: ${card.effective_date}`));
  if (card.note) details.append(element('p', card.note));
  if (card.evidence?.length) { const list = element('ul', undefined, 'evidence-list'); for (const item of card.evidence) { const li = element('li'); li.append(link(item.relation.replaceAll('_', ' '), item.url)); list.append(li); } details.append(list); }
  parent.append(details);
}
function providerCard(card) {
  const e = element('article', undefined, 'provider-card');
  e.append(element('span', card.network_status === 'directory_linked' ? 'Plan directory-listed · confirm details' : card.coverage_relevant ? 'Network unverified' : 'Directory listing · contact to confirm', `card-status ${card.network_status === 'directory_linked' ? 'linked' : ''}`));
  e.append(element('h3', card.name), element('p', card.specialty), element('p', card.address));
  if (card.kind === 'payer_directory_provider') e.append(element('p', 'Match to your chosen care category is not confirmed.', 'category-caution'));
  if (card.reason) e.append(element('p', card.reason, 'reason'));
  const links = element('div', undefined, 'card-links');
  if (card.phone) { const digits = card.phone.replace(/[^+0-9]/g, ''); if (digits) links.append(link(card.phone, `tel:${digits}`)); }
  else links.append(element('span', 'Phone not listed'));
  links.append(link(`${card.source} ↗`, card.source_url));
  if (card.website) links.append(link('Website ↗', card.website));
  if (card.directions_url) links.append(link('Directions ↗', card.directions_url));
  e.append(links);
  const source = element('p', undefined, 'source-date'); source.append(link(card.source, card.source_url), document.createTextNode(` · Retrieved ${new Date(card.retrieved_at).toLocaleDateString()}`));
  if (card.source_updated_at) source.append(document.createTextNode(` · Source updated ${String(card.source_updated_at).slice(0, 10)}`));
  e.append(source); sourceDetails(card, e); return e;
}
function group(title, result, items = result?.items) {
  if (!result) return;
  const g = element('section', undefined, 'results-group'); const header = element('div', undefined, 'results-title'); header.append(element('h3', title), element('span', `${items?.length || 0} shown`)); g.append(header);
  if (result.location_basis) g.append(element('p', result.location_basis, 'result-note'));
  if (items?.length) { const cards = element('div', undefined, 'cards'); cards.append(...items.map(providerCard)); g.append(cards); }
  else g.append(element('div', result.status === 'error' ? 'This source is unavailable right now. Try again or use its official directory below.' : 'No matching listings returned for this exact ZIP. Try a nearby ZIP or the official directory. This does not mean no care exists.', 'empty-state'));
  $('results').append(g);
}
function renderResults(results) {
  $('results').replaceChildren();
  if (!Object.keys(results).length) return;
  const plan = results.lookup_plan_network;
  if (plan) {
    const g = element('section', undefined, 'results-group'); const p = element('div', undefined, 'plan-panel');
    const future = plan.coverage_year > new Date().getFullYear();
    p.append(element('p', plan.status === 'matched_directory' ? `${future ? 'Future plan' : 'Plan'} directory-listed · ${plan.coverage_year}` : 'Coverage not confirmed', 'plan-summary'));
    if (plan.plan_name) p.append(element('p', `${plan.plan_name} · ${plan.plan_id || ''} · ${plan.network_name || ''}`));
    p.append(element('p', plan.status === 'matched_directory' ? 'The directory supports this plan and network for the requested year. Confirm benefits, cost and appointments before booking.' : plan.status === 'needs_details' ? 'Some exact plan details are still missing. Care search can continue without them.' : plan.status === 'error' ? 'The plan source is unavailable. Try again or check with the insurer.' : 'This source did not establish the exact plan, network and year. That does not mean out of network.'));
    if (plan.source_url) p.append(link('Open plan-directory source ↗', plan.source_url));
    sourceDetails(plan, p);
    for (const candidate of plan.items || []) { const d = element('details'); d.append(element('summary', `Catalog candidate: ${candidate.name}${candidate.plan_id ? ` · ${candidate.plan_id}` : ''}`)); if (candidate.period) d.append(element('p', `Effective ${candidate.period.start?.slice(0, 10)} to ${candidate.period.end?.slice(0, 10)}. Candidate only.`)); d.append(link('Candidate source ↗', candidate.source_url)); p.append(d); }
    g.append(p); $('results').append(g);
    if (plan.providers?.length) { const note = { ...plan, location_basis: 'Other plan-listed practices. Match to your chosen care category is not confirmed; these are not verified specialty matches.' }; group(`Other plan-listed practices · ${plan.coverage_year}`, note, plan.providers); }
  }
  group('Practices in your chosen category', results.search_providers);
  group('Health centers · ask about self-pay & sliding fees', results.search_affordable_clinics);
  const fallbacks = element('div', undefined, 'fallbacks');
  const links = new Map(); for (const r of Object.values(results)) for (const f of r.fallbacks || []) links.set(f.url, f.label);
  for (const [url, label] of links) fallbacks.append(link(`${label} ↗`, url)); $('results').append(fallbacks);
}
async function request(body, userLabel) {
  if (busy) return;
  $('error').hidden = true; if (userLabel) addMessage('user', userLabel); setBusy(true);
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 180000);
  try {
    const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal, body: JSON.stringify({ ...(sessionId ? { session_id: sessionId } : {}), ...(scanPending ? { scan } : {}), ...body }) });
    const data = await r.json();
    if (!r.ok) { if (r.status === 410) sessionId = undefined; throw new Error(data.fields?.map(f => f.message).join(' ') || data.message || (r.status === 410 ? 'This chat expired. Send your request again to start a new chat.' : 'The request failed. Please try again.')); }
    sessionId = data.session_id; updateProfile(data.profile); addMessage('assistant', data.message); renderResults(data.results);
    scan = data.scan; scanPending = false;
    $('scan-summary').textContent = `${data.scan_state.title}. ${data.scan_state.detail}`;
    $('scan-origin').textContent = !scan ? 'No scan' : scan.synthetic ? 'Synthetic example' : 'Attached summary';
    $('scan-age').textContent = data.scan_state.freshness === 'older' ? 'Earlier snapshot · not a current reading' : data.scan_state.freshness === 'future' ? 'Timestamp is ahead of this server · check the capture time' : scan && data.scan_state.freshness === 'unknown' ? 'Capture time not supplied' : scan?.captured_at ? `Captured ${new Date(scan.captured_at).toLocaleString()}` : '';
    $('model-badge').textContent = data.model.mode === 'llm' ? data.model.last_success_at ? 'Local care assistant available' : 'Local care assistant configured' : 'Guided help available';
    $('model-fallback').hidden = data.model.mode !== 'guided_fallback';
    $('technical-status').textContent = JSON.stringify({ model: data.model, tool_trace: data.tool_trace, backend_adjustments: data.backend_adjustments, app_context_version: data.app_context_version }, null, 2);
    $('model-badge').classList.toggle('live', data.model.mode === 'llm'); $('model-badge').title = data.model.note;
    if (data.stage === 'results') $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { $('error').textContent = e.name === 'AbortError' ? 'This request took too long. Try again. The sources may be busy.' : e.message; $('error').hidden = false; }
  finally { clearTimeout(timer); setBusy(false); }
}
$('insurance-status').addEventListener('change', () => { $('plan-fields').hidden = $('insurance-status').value !== 'insured'; });
$('care-form').addEventListener('submit', e => { e.preventDefault(); const clear_fields = $('insurance-status').value === 'insured' ? ['payer', 'plan', 'network'].filter(f => !$(f).value.trim()) : []; request({ action: 'search', profile: profileFromForm(), clear_fields }, `Find care in ${$('zip').value}.`); });
$('chat-form').addEventListener('submit', e => { e.preventDefault(); const message = $('message').value.trim(); if (!message || busy) return; $('message').value = ''; request({ message }, message); });
$('message').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('chat-form').requestSubmit(); } });
$('scan-scenario').addEventListener('change', () => { const v = $('scan-scenario').value; const usable = ['usable', 'older'].includes(v); scan = v === 'none' ? null : { schema_version: '1.1', measurement: 'experimental_heart_sound_timing', quality: usable ? 'usable' : 'unclear', estimated_bpm: usable ? 74 : null, synthetic: true, captured_at: new Date(Date.now() - (v === 'older' ? 86400000 : 0)).toISOString() }; scanPending = true; $('scan-origin').textContent = scan ? 'Synthetic example' : 'No scan'; $('scan-age').textContent = v === 'older' ? 'Earlier snapshot · not a current reading' : ''; $('scan-summary').textContent = v === 'none' ? 'No scan attached. Care search still works.' : usable ? 'Synthetic example · 74 BPM. A timing estimate, not a healthy-heart result.' : 'Synthetic example · unclear recording. No usable BPM estimate.'; });
$('clear-scan').addEventListener('click', () => { scan = null; scanPending = true; $('scan-scenario').value = 'none'; request({ scan: null, action: 'explain' }, 'Clear my attached scan summary.'); });
$('quick-actions').addEventListener('click', e => { const action = e.target.dataset.action; if (action) request({ action }, action === 'why' ? 'Why did you show these options?' : 'Show lower-cost options.'); });
$('skip-insurance').addEventListener('click', () => request({ message: 'Skip insurance details.', profile: { coverage_preference: 'skip' }, action: 'search' }, 'Skip insurance details and continue.'));
$('app-help').addEventListener('click', () => request({ message: 'How do I take a reading in the iPhone app?' }, 'How do I take a reading in Chest BPM?'));
$('jump-chat').addEventListener('click', () => { $('message').focus({ preventScroll: true }); $('chat-form').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
$('explain').addEventListener('click', () => request({ action: 'explain' }, 'Explain my scan context.'));
$('reset').addEventListener('click', async () => {
  if (busy) return; setBusy(true);
  if (sessionId) pendingDeletes.add(sessionId);
  await Promise.all([...pendingDeletes].map(async id => { try { const r = await fetch(`/api/session/${id}`, { method: 'DELETE' }); if (r.ok) pendingDeletes.delete(id); } catch {} }));
  sessionId = undefined; scan = null; scanPending = true; $('scan-scenario').value = 'none'; $('messages').replaceChildren(); $('results').replaceChildren(); $('message').value = ''; $('care-form').reset(); $('coverage-year').value = new Date().getFullYear(); $('plan-fields').hidden = true;
  $('clear-warning').hidden = !pendingDeletes.size; $('clear-warning').textContent = pendingDeletes.size ? 'This page is cleared. A previous server chat could not be deleted. Tap Clear everything to retry; otherwise it expires after inactivity.' : '';
  setBusy(false); await request({ scan: null });
});
await request({});
