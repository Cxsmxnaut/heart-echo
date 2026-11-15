import { randomUUID } from 'node:crypto';
import { ChatRequest, hasExactPlan } from './schema.js';
import { explainScan, scanState, emergencyMention, EMERGENCY, APP_CONTEXT } from './knowledge.js';
import { createTools } from './tools.js';
import { createModel } from './model.js';
import { supportsHealthPlan } from './healthplan.js';
import { conversationUpdate, mergeProfile, missingInsurance, planQuestion, resultReasons } from './conversation.js';
export { mergeProfile } from './conversation.js';
export function extractGuided(message) { return conversationUpdate(message).profile; }
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const isSearch = message => /\b(find|search|look for|show)\b[^.!?]{0,65}\b(care|providers?|clinics?|doctors?|options)\b/i.test(message);
const explicitMedicalQuestion = message => /\b(afib|murmur|cholesterol|ldl|hdl|diagnos\w*|heart disease)\b/i.test(message);
// This catches common personal details, but cannot reliably detect every kind of sensitive text.
const privateGeminiMessage = message => /\b(?:my|mine|i(?:['’]m|['’]ve|['’]d)?|me)\b[^.!?]{0,100}\b(?:health|heart|chest|hurt\w*|murmur|pain|breath\w*|symptom|palpitations?|dizz\w*|faint\w*|pressure|medical|medication|condition|diagnos\w*|recording|result|scan|bpm|pulse|doctor)\b|\bi\s+(?:have|feel|felt|experienced|take|was diagnosed)\b|\bmy\s+(?:name|age|address|birthday|birthdate|phone|email)\b|\b(?:recording|result|scan)\b|\b\d{2,3}\s*(?:bpm|beats per minute)\b|\b\d{5}(?:-\d{4})?\b|\b[^\s@]+@[^\s@]+\.[^\s@]+\b|\b(?:\+?\d[\d\s().-]{7,}\d)\b/i.test(message);
const personalHealthWords = /\b(?:heart|murmur|pain|breath\w*|symptoms?|palpitations?|dizz\w*|faint\w*|medication|diagnos\w*|recording|result|scan|bpm|pulse)\b/i;

// The model receives only a generic workflow description when a turn contains
// location, insurance, recording, or other likely personal information.
function geminiPrompt({ request, response, update, previousStage, profileChanged, explicitCare, insurerNotSupported }) {
  const question = /^\s*(?:what|why|how|where|when|who|can|could|would|is|does|do)\b/i.test(request.message) || request.message.trim().endsWith('?');
  const personalHealthStatement = personalHealthWords.test(request.message) && !/^\s*(?:what|why|how|where|when|who|can|could|would|is|does|do|explain|describe)\b/i.test(request.message);
  const privateTurn = privateGeminiMessage(request.message) || personalHealthStatement || !!update.profile.zip || !!update.profile.insurance || update.clear_fields.length > 0 || (previousStage === 'ask_plan' && !question);
  const personalConcern = privateTurn && personalHealthWords.test(request.message) && !explicitCare && !update.profile.insurance;
  if (personalConcern) return 'A person raised a private health or recording concern. Their details and result are unavailable to you. Give a natural, general reply, explain that you cannot assess their personal result, and suggest a clinician when appropriate. Do not ask for private health details.';
  let workflow = '';
  if (response.stage === 'results') {
    const items = Object.values(response.results || {}).reduce((n, group) => n + (group.items?.length || 0) + (group.providers?.length || 0), 0);
    const sourceFailed = Object.values(response.results || {}).some(group => group.status === 'error');
    workflow = items ? 'A public-directory search returned care cards shown separately in the app. Invite the person to review them; do not invent or name a provider, address, contact detail, availability, price, or coverage.' : 'A public-directory search returned no cards. Say that no listings came back, suggest trying another ZIP or an official directory, and do not claim that no care exists.';
    if (sourceFailed) workflow += ' At least one directory was unavailable; mention that briefly.';
    if (insurerNotSupported) workflow += ' The app cannot verify coverage for the insurer mentioned. Clearly say coverage is unverified and suggest checking with the insurer and clinic.';
  } else if (response.stage === 'ask_location_correction') {
    workflow = 'The person gave more than one location. Ask which ZIP they want to use. You do not know either ZIP; do not guess or invent one.';
  } else if (response.stage === 'ask_location' && explicitCare) {
    workflow = 'The person wants help finding care, and no location has been supplied. Ask for a five-digit US ZIP.';
  } else if (response.stage === 'ask_plan' && (privateTurn || profileChanged || !question)) {
    workflow = update.profile.insurance?.payer ? 'The person supplied an insurer. Acknowledge it without naming it and ask for the full plan name and network, or offer to skip insurance. Do not promise to find in-network providers.' : 'The person provided a location or is responding to an insurance question. Ask whether they want to share an insurer or skip insurance. Do not ask for the ZIP again or claim that sharing insurance can find in-network providers.';
  } else if (response.stage === 'explain_results' && privateTurn) {
    workflow = 'The person asked about earlier care options. Explain generally that the app uses public directory entries and does not verify appointments, benefits, or prices. You cannot see their specific results.';
  }
  if (privateTurn) return `${workflow || 'A person sent a message containing details that are not available to you. Respond naturally and ask a brief clarifying question without requesting private health or identifying details.'} Never claim to know the details that were withheld.`;
  return workflow ? `${request.message}\n\nPrivate-safe app context: ${workflow}` : request.message;
}

function unsafeGeminiReply(text) {
  const diagnosis = /\byou (?:definitely |certainly |clearly )?(?:have|do not have|don['’]t have) (?:a |an )?(?:murmur|heart disease|heart condition|arrhythmia)\b/gi;
  for (const match of text.matchAll(diagnosis)) {
    const clause = text.slice(0, match.index).split(/[.!?\n]/).at(-1);
    if (!/\b(?:cannot|can['’]t|unable to|not|don['’]t|doesn['’]t|whether|if|unless)\b/i.test(clause)) return true;
  }
  return /\byour (?:heart|result|scan) (?:is|proves|confirms) (?:healthy|normal|safe|a diagnosis)\b|\b(?:coverage|insurance) (?:is|will be) (?:guaranteed|confirmed|covered)\b|\b(?:these|the|this|listed|all|your)\s+(?:providers?|clinics?|doctors?)\s+(?:accept|take|are in.network)\s+(?:your\s+)?(?:insurance|plan|coverage)\b|\b(?:find|locate|show|list|match)\b[^.!?]{0,45}\bin[ -]network\b/i.test(text);
}
function asksForPrivateHealth(text) {
  return /\b(?:do you (?:have|experience)|are you (?:experiencing|having)|have you been diagnosed|what are your symptoms|(?:did|has) (?:a|your) (?:doctor|clinician|provider) (?:recently )?(?:mention|diagnose)|(?:tell|share with) me (?:about |your )?(?:your )?(?:symptoms?|diagnosis|medical history|recording|result))\b/i.test(text);
}

export function createService({ tools = createTools(), model = createModel(), clock = Date.now, ttlMs = 1800000 } = {}) {
  const sessions = new Map(); const active = new Set();
  function prune() { for (const [id, s] of sessions) if (clock() - s.touched > ttlMs) sessions.delete(id); }
  return {
    model, deleteSession(id) { sessions.delete(id); },
    async chat(raw) {
      const request = ChatRequest.parse(raw); prune(); const id = request.session_id || randomUUID();
      if (request.session_id && !sessions.has(id)) return { error: 'session_expired', status: 410 };
      if (active.has(id)) return { error: 'request_in_progress', status: 409 };
      if (!sessions.has(id) && sessions.size >= 100) return { error: 'demo_capacity', status: 503 };
      active.add(id);
      const s = sessions.get(id) || { profile: {}, scan: null, history: [], geminiHistory: [], lastResults: {}, touched: clock() };
      try {
        const adjustments = []; let modelError; let usedModel = false; let intent = 'other';
        const update = conversationUpdate(request.message, s.profile, { awaitingPayer: s.lastStage === 'ask_plan' }); let extracted = {}; let modelClears = [];
        const urgent = emergencyMention(request.message);
        if (request.message && model.configured && !urgent && model.provider !== 'gemini') {
          try {
            const out = await model.extract(request.message, { profile: s.profile }); usedModel = true; intent = out.intent;
            extracted = { ...(out.zip ? { zip: out.zip } : {}), ...(out.insurance ? { insurance: out.insurance } : {}), ...(out.specialty ? { specialty: out.specialty } : {}) }; modelClears = out.clear_fields || [];
            if (out.insurance?.status === 'unknown' && update.clear_fields.length && s.profile.insurance?.status === 'insured') { delete extracted.insurance; adjustments.push('Kept confirmed insurance labels while clearing only the named unknown field.'); }
          } catch (e) { modelError = e.code || 'model_failed'; adjustments.push('Used the guided update because model extraction failed validation.'); }
        }
        const clears = [...new Set([...modelClears, ...update.clear_fields, ...(request.clear_fields || [])])];
        if (usedModel) {
          for (const [key, value] of Object.entries(update.profile)) {
            if (['coverage_preference', 'care_preference'].includes(key)) continue;
            if (key === 'insurance') { for (const [field, supplied] of Object.entries(value)) if (extracted.insurance?.[field] !== supplied) adjustments.push(`Guided correction applied to insurance.${field}.`); }
            else if (extracted[key] !== value) adjustments.push(`Guided correction applied to ${key}.`);
          }
          for (const field of update.clear_fields) if (!modelClears.includes(field)) adjustments.push(`Guided correction cleared ${field}.`);
        }
        const previous = structuredClone(s.profile);
        if (update.ambiguity && !request.profile?.zip) { if (extracted.zip) adjustments.push('Asked which ZIP was intended rather than choosing among ambiguous numbers.'); delete extracted.zip; }
        let next = mergeProfile(s.profile, {}, clears); next = mergeProfile(next, extracted);
        if (update.profile.zip && extracted.zip && update.profile.zip !== extracted.zip) adjustments.push('Used the ZIP explicitly named as the replacement.');
        next = mergeProfile(mergeProfile(next, update.profile), request.profile || {});
        if (!request.profile?.specialty && next.specialty === 'cardiology' && /\b(no|not|don.t|do not|avoid|without)\b[^.;\n]{0,45}cardiolog/i.test(request.message)) { next.specialty = 'family_medicine'; adjustments.push('Respected declined cardiology.'); }
        if (clears.includes('network') || clears.includes('plan')) next.coverage_preference = 'skip';
        const profileChanged = !same(previous, next); s.profile = next; if (profileChanged) s.lastResults = {};
        let scanChanged = false;
        if (request.scan !== undefined) { scanChanged = !same(request.scan, s.scan); s.scan = request.scan; }
        if (update.intent) { if (intent !== update.intent && usedModel) adjustments.push(`Used the explicit ${update.intent} request.`); intent = update.intent; }
        if (request.action === 'search' || isSearch(request.message)) intent = 'find_care';
        if (request.action === 'affordable') { s.profile.care_preference = 'affordable'; intent = 'cheaper_options'; }
        if (request.action === 'why') intent = 'explain_results';
        if (/\b(privacy|training|trained|recordings? used|store my|save my)\b/i.test(request.message)) intent = 'app_help';
        if (/\b(how (?:do i|to|can i)|watch|gemma|two (?:models|ai)|which (?:model|ai))\b/i.test(request.message) && !explicitMedicalQuestion(request.message)) intent = 'app_help';
        const capabilityQuestion = /\b(what|how)\b[^?]{0,65}\b(app|chest bpm|scan)\b[^?]{0,45}\b(measure|work|estimate|do)\b|\bwhat can (?:the app|chest bpm)\b/i.test(request.message);
        const diagnosisQuestion = /\b(afib|murmur|cholesterol|ldl|hdl|diagnos\w*|heart disease|healthy heart|normal scan)\b/i.test(request.message);
        const explicitCare = ['search', 'affordable'].includes(request.action) || isSearch(request.message);
        const insurerNotSupported = model.provider === 'gemini' && s.profile.insurance?.status === 'insured' && !!s.profile.insurance?.payer && !supportsHealthPlan(s.profile.insurance);
        if (!explicitCare && ((intent !== 'app_help' && /unclear|noisy|background noise|recording quality/i.test(request.message)) || diagnosisQuestion || capabilityQuestion)) intent = 'explain_scan';
        if (request.action === 'explain') intent = 'explain_scan';
        if (intent === 'cheaper_options') s.profile.care_preference = 'affordable';
        if (profileChanged && intent === 'other') { if (usedModel) adjustments.push('Treated the confirmed detail change as a care-search follow-up.'); intent = 'find_care'; }
        const response = { session_id: id, profile: s.profile, scan: s.scan, scan_state: scanState(s.scan, clock()), scan_changed: scanChanged, scan_explanation: explainScan(s.scan, clock()), model: model.status(), app_context_version: APP_CONTEXT.version, results: s.lastResults, results_reused: !!Object.keys(s.lastResults).length, tool_trace: [], backend_adjustments: adjustments, emergency: EMERGENCY };
        const remember = () => s.profile.zip ? `I’m keeping ZIP ${s.profile.zip}${s.profile.specialty ? ` and your ${s.profile.specialty.replaceAll('_', ' ')} choice` : ''}.` : 'What is your five-digit US ZIP code?';
        async function appFacts(topic) {
          if (!model.configured || modelError || model.provider === 'gemini') return;
          try { const r = await model.runTools({ profile: s.profile, scan: s.scan, message: request.message, tools, intent: topic }); response.tool_trace.push(...r.trace); response.model.elapsed_ms = r.elapsed_ms; usedModel ||= r.trace.some(t => t.origin === 'model'); }
          catch (e) { modelError = e.code || 'model_failed'; }
        }
        let message;
        if (urgent) { response.stage = 'urgent_help'; message = EMERGENCY.text; response.results = {}; }
        else if (update.ambiguity && !request.profile?.zip) { response.stage = 'ask_location_correction'; message = `Which ZIP should I use: ${update.ambiguity.candidates.join(' or ')}? I have not changed your confirmed location.`; }
        else if (intent === 'explain_results') {
          response.stage = 'explain_results';
          message = Object.keys(s.lastResults).length ? `These are directory options in your exact ZIP ${s.profile.zip}${s.profile.care_preference === 'affordable' ? ', with health centers first because you asked about cost' : `, using your ${(s.profile.specialty || 'primary care').replaceAll('_', ' ')} choice`}. Each card explains its source and match. ${s.profile.insurance?.status === 'uninsured' ? 'For self-pay, ask about sliding fees and an estimate before booking.' : 'Payer-listed links appear only where the exact plan, network, practice and year are supported; other coverage is unverified.'} They were not selected because a scan diagnosed anything.` : `There are no current results to explain${profileChanged ? ' after that correction' : ''}. ${remember()} Choose “Find care” when you’re ready.`;
        } else if (intent === 'explain_scan') {
          response.stage = 'scan_explanation'; await appFacts('explain_scan'); message = capabilityQuestion ? `${APP_CONTEXT.measurement[0]} ${APP_CONTEXT.measurement[1]}` : response.scan_explanation;
          if (!s.profile.zip) message += ' Care search works even without a clear scan.';
        } else if (intent === 'app_help') {
          response.stage = 'app_help'; await appFacts('app_help');
          const topic = /gemma|two (?:models|ai)|which (?:model|ai)|trained model/i.test(request.message) ? 'models' : /watch/i.test(request.message) ? 'watch' : /retry|try again|unclear|noise/i.test(request.message) ? 'retry' : /how|position|microphone|start/i.test(request.message) ? 'getting_started' : /privacy|data|record|train|store|save/i.test(request.message) ? 'privacy' : 'insurance';
          message = APP_CONTEXT[topic].join(' ');
        } else if (!s.profile.zip) {
          response.stage = 'ask_location'; message = request.message ? 'What is your five-digit US ZIP code? That’s enough location detail to find care.' : 'I’m Chest BPM’s care assistant. I can explain your timing estimate and help you find care. The app does not diagnose heart disease. What is your five-digit US ZIP code?';
        } else if (!s.profile.insurance && !explicitCare && intent !== 'cheaper_options' && s.profile.coverage_preference !== 'skip') {
          response.stage = 'ask_plan'; message = planQuestion(s.profile);
        } else if (s.profile.insurance?.status === 'insured' && !hasExactPlan(s.profile.insurance) && s.profile.coverage_preference !== 'skip' && !explicitCare && intent !== 'cheaper_options' && !insurerNotSupported) {
          response.stage = 'ask_plan'; message = planQuestion(s.profile);
        } else if (intent === 'other' && request.message && !profileChanged) {
          response.stage = 'ready'; message = `You’re welcome. ${remember()} You can ask about your scan, change your details, or choose “Find care.”`;
        } else {
          response.stage = 'results'; const affordable = s.profile.care_preference === 'affordable' || intent === 'cheaper_options';
          const needed = [...(!affordable ? [['search_providers', { zip: s.profile.zip, specialty: s.profile.specialty || 'family_medicine', limit: 5 }]] : []), ['search_affordable_clinics', { zip: s.profile.zip, limit: 5 }], ...(!affordable && s.profile.coverage_preference !== 'skip' && s.profile.insurance?.status === 'insured' && !insurerNotSupported ? [['lookup_plan_network', { insurance: s.profile.insurance, zip: s.profile.zip }]] : [])];
          let results = new Map();
          if (model.configured && !modelError && model.provider !== 'gemini') {
            try { const r = await model.runTools({ profile: s.profile, scan: s.scan, message: request.message, tools, history: s.history, intent: affordable ? 'cheaper_options' : 'find_care' }); results = r.results; response.tool_trace.push(...r.trace); response.model.elapsed_ms = r.elapsed_ms; usedModel ||= r.trace.some(t => t.origin === 'model'); }
            catch (e) { modelError = e.code || 'model_failed'; }
          }
          results = new Map([...results].filter(([name]) => needed.some(([n]) => n === name)));
          const missing = needed.filter(([name]) => !results.has(name));
          if (missing.length && model.configured && !modelError && model.provider !== 'gemini') modelError = 'model_incomplete_tools';
          const completed = await Promise.allSettled(missing.map(async ([name, args]) => [name, await tools.call(name, args)]));
          for (let i = 0; i < completed.length; i++) {
            const r = completed[i]; const name = missing[i][0]; const value = r.status === 'fulfilled' ? r.value[1] : { status: 'error', error: 'directory_unavailable', items: [] };
            results.set(name, value); response.tool_trace.push({ name, status: value.status, origin: 'service' }); if (model.configured && model.provider !== 'gemini') adjustments.push(`The service completed ${name}; this is not a model tool-use success.`);
          }
          s.lastResults = resultReasons(s.profile, Object.fromEntries(results)); response.results = s.lastResults; response.results_reused = false;
          const records = Object.values(response.results); const plan = response.results.lookup_plan_network;
          response.counts = { category_listings: response.results.search_providers?.items?.length || 0, health_centers: response.results.search_affordable_clinics?.items?.length || 0, other_plan_practices: plan?.providers?.length || 0 };
          const count = records.reduce((n, r) => n + (r.items?.filter(i => i.kind).length || 0) + (r.providers?.length || 0), 0);
          message = count ? `Here are ${count} care listings in ZIP ${s.profile.zip}.` : `No listings came back for this exact ZIP ${s.profile.zip}. Try another nearby ZIP or an official directory below.`;
          if (records.some(r => r.status === 'error')) message += ' One source is unavailable; that does not mean no care exists.';
          if (affordable || s.profile.insurance?.status === 'uninsured') message += ' Ask about self-pay, sliding-fee eligibility, and an estimate. I can’t rank prices or promise free care.';
          else if (plan?.status === 'matched_directory') message += ` Payer-listed practices are linked to your requested ${plan.coverage_year} plan. Confirm benefits and appointments before booking.`;
          else if (plan?.status === 'unsupported') message += ' This source could not establish the exact plan, network and year. That does not mean out of network.';
          else if (s.profile.insurance?.status === 'insured') message += insurerNotSupported ? ' This service cannot verify coverage with the insurer you named. Confirm coverage with your insurer and the clinic.' : ' Coverage is unverified; add missing plan details or confirm with the insurer.';
        }
        if (model.provider === 'gemini' && request.message && !urgent && model.configured) {
            try {
              const prompt = geminiPrompt({ request, response, update, previousStage: s.lastStage, profileChanged, explicitCare, insurerNotSupported });
              let answer = await model.reply(prompt, s.geminiHistory || []);
              if (unsafeGeminiReply(answer) || asksForPrivateHealth(answer)) {
                answer = await model.reply(`${prompt}\n\nRespond generally and do not ask the person for any personal health details or assert a diagnosis or coverage.`, s.geminiHistory || []);
              }
              if (unsafeGeminiReply(answer) || asksForPrivateHealth(answer)) throw Object.assign(Error(), { code: 'model_unsafe_response' });
              message = answer; usedModel = true;
              if (insurerNotSupported && response.stage === 'results' && !/\b(?:unverified|cannot verify|can.t verify|confirm|check)\b/i.test(answer)) message += ' Insurance coverage is unverified; confirm it with your insurer and the clinic.';
              s.geminiHistory = [...(s.geminiHistory || []), { role: 'user', text: prompt }, { role: 'model', text: answer }].slice(-6);
            } catch (e) {
              modelError = e.code || 'model_failed';
              if (!explicitCare && !profileChanged && !['results', 'ask_plan', 'ask_location_correction', 'explain_results'].includes(response.stage)) {
                message = modelError === 'model_http_429' ? 'Gemini has reached its current request limit. Please try again later.' : 'The AI could not respond right now. Please try again.';
              }
            }
        }
        response.clarification = s.profile.insurance?.status === 'insured' && !hasExactPlan(s.profile.insurance) && !insurerNotSupported ? { optional: true, missing: missingInsurance(s.profile), message: planQuestion(s.profile) } : null;
        response.model = modelError ? { ...model.status(), mode: 'guided_fallback', error: modelError, note: 'The model was unavailable or its output failed validation. Guided help and public directory results remain available.' } : { ...response.model, ...model.status() };
        response.model.used_this_turn = usedModel; response.model.backend_corrected = adjustments.length > 0; response.message = message;
        s.lastStage = response.stage;
        s.history.push(...(request.message ? [{ role: 'user', content: request.message }] : []), { role: 'assistant', content: message });
        s.history = s.history.slice(-8); s.touched = clock(); sessions.set(id, s); return response;
      } finally { active.delete(id); }
    },
  };
}
