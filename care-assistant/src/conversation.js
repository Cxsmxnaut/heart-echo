import { Profile } from './schema.js';

const UNKNOWN = /\b(don[’']?t know|do not know|not sure|can[’']?t recall|cannot recall|unknown|unsure|forget|forgot)\b/i;
const FIELD_WORDS = { payer: /insurer|payer|insurance company/i, plan: /plan(?: name)?|product/i, network: /network/i, plan_id: /plan (?:id|identifier)/i, coverage_year: /(?:plan|coverage) year/i, coverage_date: /(?:coverage|effective) date/i };
export function conversationUpdate(message, previous = {}, context = {}) {
  const profile = {}; const clear_fields = []; let intent;
  // Explicit corrections win over a model's choice between two ZIPs in the text.
  const replacement = message.match(/\breplace\s+\d{5}\s+with\s+(\d{5})\b/i)?.[1];
  const correction = message.match(/\b(?:actually[,:]?\s+(?:use\s+)?|(?:use|switch to|change (?:my )?(?:zip(?: code)? )?to)\s+)(?:zip(?: code)?\s*)?(\d{5})\b/i)?.[1];
  const labelled = message.match(/\b(?:my |current |new )?(?:zip(?: code)?|postal code)\s*(?:is|:|=)?\s*(\d{5})\b/i)?.[1];
  const numbers = [...new Set(message.match(/\b\d{5}\b/g) || [])];
  const zip = replacement || correction || labelled || (numbers.length === 1 ? numbers[0] : undefined);
  const ambiguity = !zip && numbers.length > 1 ? { field: 'zip', candidates: numbers } : null;
  if (zip) profile.zip = zip;
  const insurance = {};
  for (const key of ['payer', 'plan', 'network']) {
    const value = message.match(new RegExp(`(?:^|[;\\n])\\s*${key}\\s*:\\s*([^;\\n]+)`, 'i'))?.[1]?.trim();
    if (value && !UNKNOWN.test(value)) insurance[key] = value;
  }
  // Interpret ordinary replies locally; keep the spelling supplied by the user.
  const explicitPayer = message.match(/\b(?:my\s+)?(?:insurance(?: company)?|insurer)\s+(?:is|through|with)\s+([^;.!?\n]+)/i)?.[1];
  const waitingForPayer = context.awaitingPayer && !previous.insurance?.payer;
  const afterPayerQuestion = waitingForPayer
    ? message.match(/^\s*(?:i\s+(?:have|use)|i(?:'m| am)\s+(?:insured|covered)\s+(?:by|with|through))\s+([^;.!?\n]+)/i)?.[1]
    : undefined;
  const barePayer = waitingForPayer && !/[?;\n\d]/.test(message) && !/^\s*(?:yes|no|skip|what|why|how|where|when|who|please|i\b|my\b)/i.test(message) ? message.trim().replace(/[.!]+$/, '') : undefined;
  const payer = (explicitPayer || afterPayerQuestion || barePayer)?.trim();
  if (!insurance.payer && payer && payer.length <= 160 && !UNKNOWN.test(payer) && !/\b(?:pain|symptoms?|chest|heart|palpitations?|question|appointment|no insurance|no idea)\b/i.test(payer)) insurance.payer = payer;
  for (const key of ['plan', 'network']) {
    const value = message.match(new RegExp(`\\b(?:my\\s+)?${key}(?: name)?\\s+(?:is|called)\\s+([^;.!?\\n]+)`, 'i'))?.[1]?.trim();
    if (!insurance[key] && value && !UNKNOWN.test(value) && value.length <= 160) insurance[key] = value;
  }
  const year = message.match(/\b(?:plan year|coverage year|year|instead use|change (?:it|that|the year) to)\s*(?:to|is|:)?\s*(20\d{2})\b/i)?.[1] || (previous.insurance ? message.match(/\b(?:actually[, ]*)?use\s+(20\d{2})\b/i)?.[1] : undefined);
  if (year) insurance.coverage_year = Number(year);
  const date = message.match(/\b(?:coverage date|effective date)\s*:?\s*(\d{4}-\d{2}-\d{2})\b/i)?.[1];
  if (date) insurance.coverage_date = date;
  for (const clause of message.split(/[;.!?\n]/)) {
    if (!UNKNOWN.test(clause) && !/\b(clear|remove|forget|leave blank)\b/i.test(clause)) continue;
    for (const [field, words] of Object.entries(FIELD_WORDS)) {
      const target = words.source;
      if (new RegExp(`(?:${UNKNOWN.source}|\\bclear|\\bremove|\\bforget)\\s+(?:my |the |which |what |exact )?(?:${target})`, 'i').test(clause) || new RegExp(`(?:${target})\\s+(?:(?:name |details? )?(?:is |are )?(?:unknown|not known|uncertain)|(?:I )?(?:don't|do not) know)`, 'i').test(clause)) clear_fields.push(field);
    }
  }
  if (/\b(uninsured|no insurance|without insurance|don[’']?t have insurance|do not have insurance)\b/i.test(message)) {
    profile.insurance = { status: 'uninsured' }; profile.coverage_preference = 'skip';
  } else if (/\b(skip|decline|rather not|prefer not|don[’']?t want to|do not want to)\b[^.;\n]{0,45}\b(insurance|coverage|plan details)\b|^\s*(skip|not sure|i don[’']?t know)\s*[.!]?\s*$/i.test(message)) {
    profile.coverage_preference = 'skip'; if (!previous.insurance) profile.insurance = { status: 'unknown' };
  } else if (Object.keys(insurance).length) {
    profile.insurance = { status: 'insured', ...insurance }; profile.coverage_preference = 'check_if_possible';
  }
  if (clear_fields.includes('network') || clear_fields.includes('plan')) profile.coverage_preference = 'skip';
  const declinedCardiology = /\b(no|not|don.t|do not|avoid|without)\b[^.;\n]{0,45}cardiolog/i.test(message);
  if (/primary care|family medicine/i.test(message)) profile.specialty = 'family_medicine';
  else if (/internal medicine/i.test(message)) profile.specialty = 'internal_medicine';
  else if (/\b(choose|want|prefer|search for|find|specialty:)\s+(a\s+)?cardiolog/i.test(message) && !declinedCardiology) profile.specialty = 'cardiology';
  else if (declinedCardiology && previous.specialty === 'cardiology') profile.specialty = 'family_medicine';
  if (/\b(cheaper|affordable|low[ -]cost|sliding[ -]fee|less expensive|self[ -]pay)\b/i.test(message)) { profile.care_preference = 'affordable'; intent = 'cheaper_options'; }
  if (/\b(all options|all providers|both kinds|regular providers|show everyone)\b/i.test(message)) { profile.care_preference = 'all'; intent = 'find_care'; }
  if (/\bwhy\b.*\b(these|suggest|recommend|results|providers|clinics|options)\b|\b(reason|basis)\b.*\b(results|suggestions|these)\b/i.test(message)) intent = 'explain_results';
  if (!intent && (Object.keys(profile).length || clear_fields.length)) intent = 'find_care';
  return { profile, clear_fields: [...new Set(clear_fields)], intent, ambiguity };
}

export function mergeProfile(previous, patch = {}, clear_fields = []) {
  const next = { ...previous, ...patch };
  if (patch.insurance) {
    const p = patch.insurance; const old = previous.insurance;
    const changedPayer = p.payer && p.payer !== old?.payer;
    const changedPlan = p.plan && p.plan !== old?.plan;
    const changedNetwork = p.network && p.network !== old?.network;
    const changedYear = p.coverage_year && p.coverage_year !== old?.coverage_year;
    next.insurance = p.status !== 'insured' ? { status: p.status } : {
      ...(changedPayer ? {} : old),
      ...(changedPlan ? { network: undefined, plan_id: undefined } : {}),
      ...(changedNetwork ? { plan_id: undefined } : {}),
      ...(changedYear && !p.coverage_date ? { coverage_date: undefined } : {}), ...p,
    };
    if (p.coverage_date && !p.coverage_year) next.insurance.coverage_year = Number(p.coverage_date.slice(0, 4));
  } else if (previous.insurance) next.insurance = { ...previous.insurance };
  for (const field of clear_fields) {
    if (['zip', 'specialty'].includes(field)) delete next[field];
    else if (next.insurance) {
      delete next.insurance[field];
      if (field === 'payer') for (const k of ['plan', 'network', 'plan_id']) delete next.insurance[k];
      if (field === 'plan') for (const k of ['network', 'plan_id']) delete next.insurance[k];
      if (field === 'coverage_year') delete next.insurance.coverage_date;
    }
  }
  if (next.insurance) next.insurance = Object.fromEntries(Object.entries(next.insurance).filter(([, v]) => v !== undefined));
  return Profile.parse(next);
}

export function missingInsurance(profile) {
  return ['payer', 'plan', 'network'].filter(key => !profile.insurance?.[key]);
}
export function planQuestion(profile) {
  if (!profile.insurance) return 'Do you want to check an insurance plan? You can also choose “Skip insurance” or “No insurance” and keep looking for care.';
  const names = { payer: 'insurer', plan: 'full plan name', network: 'network name' };
  return `For a coverage check, I still need your ${missingInsurance(profile).map(k => names[k]).join(' and ')}. You can skip this and see care options now.`;
}
export function resultReasons(profile, results) {
  return Object.fromEntries(Object.entries(results).map(([tool, result]) => {
    const reason = tool === 'search_affordable_clinics' ? `HRSA lists this health-center site in ZIP ${profile.zip}. Ask about self-pay and sliding-fee options; prices and services vary.` : tool === 'search_providers' ? `This practice is listed in ZIP ${profile.zip} under your ${profile.specialty === 'cardiology' ? 'cardiology' : profile.specialty === 'internal_medicine' ? 'internal medicine' : 'primary care'} search category.` : undefined;
    const annotate = item => ({ ...item, reason: reason || `The payer’s directory links this practice to your exact plan and network for ${result.coverage_year}. Its match to your chosen care category has not been confirmed.`, category_match: tool === 'search_providers' ? 'directory_taxonomy' : 'unverified', coverage_relevant: profile.insurance?.status === 'insured' && profile.coverage_preference !== 'skip', directions_url: item.address ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(item.address)}` : null });
    return [tool, { ...result, ...(reason ? { items: (result.items || []).map(annotate) } : {}), ...(result.providers ? { providers: result.providers.map(annotate) } : {}) }];
  }));
}
