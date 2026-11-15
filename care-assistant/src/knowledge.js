export const APP_CONTEXT = Object.freeze({
  version: '1.2.0',
  source: 'docs/app-knowledge.v1.json',
  measurement: [
    'Chest BPM uses microphone audio and an on-device model to estimate beats per minute (BPM) and repeating heart-sound timing. The moving sound trace is not an ECG.',
    'Heart Echo also runs a separate experimental murmur sound classifier on the iPhone. It does not diagnose AFib, valve conditions, cholesterol levels, or heart disease. A usable timing estimate is not a healthy-heart result and does not decide whether you need a specialist.',
    'Noise, movement, and recording quality can affect an estimate. An unclear scan does not establish a medical problem. You can search for care with no scan.',
  ],
  getting_started: [
    'Record in the Chest BPM iPhone app, not this care page. Allow microphone access, remove the phone case, and gently rest the bottom microphone against bare skin at the suggested chest position.',
    'Stay still in a quiet room with your arms supported. Breathe normally; do not hold your breath or press harder. Wait about 6–8 seconds after moving for the timing estimate to settle. Through-shirt accuracy has not been established.',
  ],
  retry: [
    'An unclear recording is not a diagnosis. In the iPhone app, try a quieter room, keep the phone steady, and try the next suggested position. Wait for the new estimate to settle.',
    'The app can replay recent sound after stopping recording. The care page does not record or replay audio. You can look for care even if retrying does not give a usable estimate.',
  ],
  watch: [
    'An Apple Watch is optional. Its reading is a separate comparison, never an input used to calculate the iPhone estimate. The iPhone estimates BPM independently from microphone audio.',
    'The care assistant does not need Watch readings, identifiers, comparisons or diagnostic logs.',
  ],
  models: [
    'There are two separate AI roles: on-device audio analysis and care navigation. The iPhone’s trained sound-timing model estimates BPM and a separate audio-only model looks for murmur-like patterns. The care service can use a local model or Google Gemini.',
    'The care service runs through this Mac, not on the iPhone. If Gemini is selected, general chat is sent to Google. This browser page does not record heart sounds. Public directory searches need internet, and the Watch is not required.',
  ],
  privacy: [
    'This demo accepts a small scan summary, ZIP code, and insurance plan/network labels. Do not enter member IDs, insurance passwords, names, private recordings, or private health files.',
    'Chat sessions live in server memory for up to 30 minutes of inactivity and disappear on restart. The browser keeps the session ID in memory only. There is no training pipeline or conversation database.',
    'Directory requests send ZIP/specialty or plan name to public sources. When Gemini is selected, general chat goes to Google, but the recorded result is not sent to Gemini. Google may use free-tier messages to improve its products; do not send personal or health information to the free tier.',
  ],
  insurance: [
    'NPPES identifies providers and practice locations. It does not verify exact insurance-plan participation, appointment availability, benefits, or cost.',
    'A CMS plan-name search can find catalog candidates. A matching name alone does not verify the payer, network, service area, or participation of a provider at a practice.',
    'Confirm the exact plan/network and practice address with both the insurer and clinic. Ask about new patients, referrals, benefits, and an estimate of your share of the cost.',
  ],
});

export const EMERGENCY = {
  text: 'If you have chest pain, severe trouble breathing, fainting, or think you may be having a heart attack, call 911 now. Do not wait for a scan or directory search. This demo cannot assess emergencies.',
  source_url: 'https://www.nhlbi.nih.gov/health/heart-attack/symptoms',
};

// Conservative keyword help, not a symptom classifier or a medical triage system.
export function emergencyMention(text) {
  // Only a current, affirmative report interrupts this turn. This deliberately
  // makes no attempt at diagnosis/triage and never inspects prior chat warnings.
  return text.split(/[.!?;\n]/).some(clause => {
    if (/\b(no |not |without |den(?:y|ies|ied)|had |last (?:year|week|month)|used to |if |hypothetical|example|footer|warning|why does|what if)\b/i.test(clause)) return false;
    return /\b(i (?:have|am having|feel)|i[’']?m having|right now|currently)\b[^.;\n]{0,55}\b(chest (pain|pressure)|trouble breathing|shortness of breath|fainting|heart attack)\b|\bmy chest (?:hurts|aches|is hurting)\b|\bpain in my chest\b|\bi (?:can[’']?t|cannot) breathe\b/i.test(clause);
  });
}

export function scanState(scan, now = Date.now()) {
  if (!scan) return { kind: 'absent', synthetic: false, freshness: 'unknown', title: 'No scan attached', detail: 'You can find care without a recording.' };
  const age = scan.captured_at ? now - Date.parse(scan.captured_at) : null;
  const freshness = age === null ? 'unknown' : age < -300000 ? 'future' : age > 30 * 60 * 1000 ? 'older' : 'recent';
  return { kind: scan.quality, synthetic: scan.synthetic, freshness, captured_at: scan.captured_at ?? null, murmur: scan.murmur ?? null,
    title: scan.murmur ? murmurTitle(scan.murmur.finding) : scan.quality === 'usable' ? `${Math.round(scan.estimated_bpm)} BPM · experimental estimate` : 'No usable BPM estimate',
    detail: scan.quality === 'usable' ? 'A timing estimate, not a healthy-heart result.' : scan.quality === 'unclear' ? 'This recording did not give a clear timing estimate. Care search still works.' : 'No accepted estimate is available. Care search still works.' };
}
function murmurTitle(finding) { return finding === 'present' ? 'Murmur-like pattern' : finding === 'absent' ? 'Not detected in this recording' : 'Unsure'; }
function explainMurmur(scan) {
  if (!scan.murmur) return '';
  const meaning = scan.murmur.finding === 'present' ? 'The on-device model found a murmur-like sound pattern. It cannot identify the cause or severity.' : scan.murmur.finding === 'absent' ? 'A murmur was not detected in this recording. This does not rule out a murmur elsewhere or heart disease.' : 'The model could not give a clear murmur result. Unsure does not mean absent.';
  return ` ${meaning} Model: ${scan.murmur.model_revision}. BPM and murmur analysis are independent. Phone murmur accuracy has not been established.`;
}
export function explainScan(scan, now = Date.now()) {
  if (!scan) return 'No scan is attached. You can find care without one. Chest BPM estimates BPM and heart-sound timing; it does not diagnose heart disease.';
  const prefix = scan.synthetic ? 'Synthetic example. ' : '';
  const freshness = scanState(scan, now).freshness;
  const timing = freshness === 'older' ? ' This is an earlier snapshot, not a current reading.' : freshness === 'future' ? ' Its timestamp is ahead of this server; check the capture time.' : '';
  if (scan.schema_version === '1.2') {
    const source = scan.recording_source === 'public_example' ? 'Public stethoscope example; this is not your heart recording. ' : scan.recording_source === 'import' ? 'Imported recording. ' : '';
    const bpm = scan.quality === 'usable' ? `The supplied timing estimate is ${Math.round(scan.estimated_bpm)} BPM. It does not establish heart health.` : 'No usable BPM estimate is attached. This does not change the murmur finding.';
    return `${prefix}${source}${bpm}${explainMurmur(scan)}${timing} You can find care with any result or without a scan. This project is a prototype and is not medical advice.`;
  }
  if (scan.quality !== 'usable') return `${prefix}This scan has no usable BPM estimate. Noise or movement can affect sound timing; an unclear result does not establish a medical problem.${timing} You can still find care.`;
  return `${prefix}The supplied scan estimates ${Math.round(scan.estimated_bpm)} BPM (beats per minute) from sound timing. Usable timing does not mean a healthy heart, and it does not diagnose AFib, murmurs, or heart disease.${timing}`;
}
