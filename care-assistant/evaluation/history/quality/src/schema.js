import { z } from 'zod';

export const Zip = z.string().regex(/^\d{5}$/, 'Enter a five-digit US ZIP code.');
const label = z.string().trim().min(1).max(160);
export const ScanSummary = z.object({
  schema_version: z.enum(['1.0', '1.1']),
  measurement: z.literal('experimental_heart_sound_timing'),
  quality: z.enum(['usable', 'unclear', 'unavailable']),
  estimated_bpm: z.number().finite().min(20).max(300).nullable(),
  duration_seconds: z.number().finite().positive().max(300).optional(),
  captured_at: z.iso.datetime().optional(),
  analysis_window_seconds: z.number().finite().positive().max(30).optional(),
  synthetic: z.boolean(),
  timing_counters: z.object({ pattern_bpm: z.number().finite().min(20).max(300).optional(), cycle_bpm: z.number().finite().min(20).max(300).optional() }).strict().optional(),
}).strict().superRefine((s, ctx) => {
  if (s.quality !== 'usable' && s.estimated_bpm !== null)
    ctx.addIssue({ code: 'custom', message: 'Unclear/unavailable scans must have null estimated_bpm.' });
  if (s.quality === 'usable' && s.estimated_bpm === null)
    ctx.addIssue({ code: 'custom', message: 'Usable scans require estimated_bpm.' });
  if (s.schema_version === '1.0' && s.timing_counters) ctx.addIssue({ code: 'custom', message: 'Timing counters require schema version 1.1.' });
  if (s.schema_version === '1.0' && s.analysis_window_seconds) ctx.addIssue({ code: 'custom', message: 'Analysis window requires schema version 1.1.' });
  if (s.schema_version === '1.1' && s.duration_seconds !== undefined) ctx.addIssue({ code: 'custom', message: 'Use analysis_window_seconds for the rolling analysis window in version 1.1.' });
  if (s.quality !== 'usable' && s.timing_counters) ctx.addIssue({ code: 'custom', message: 'Unclear/unavailable summaries must omit timing counters.' });
});
export const Insurance = z.object({
  status: z.enum(['insured', 'uninsured', 'unknown']),
  payer: label.optional(), plan: label.optional(), network: label.optional(),
  plan_id: z.string().regex(/^H\d{4}-\d{3}-\d{3}$/, 'Use a public CMS plan ID, not a member ID.').optional(),
  coverage_year: z.number().int().min(2020).max(2100).optional(),
  coverage_date: z.iso.date().optional(),
}).strict();
export const Specialty = z.enum(['family_medicine', 'internal_medicine', 'cardiology']);
export const ClearField = z.enum(['zip', 'specialty', 'payer', 'plan', 'network', 'plan_id', 'coverage_year', 'coverage_date']);
export const Profile = z.object({ zip: Zip.optional(), insurance: Insurance.optional(), specialty: Specialty.optional(), care_preference: z.enum(['all', 'affordable']).optional(), coverage_preference: z.enum(['check_if_possible', 'skip']).optional() }).strict();
export const ChatRequest = z.object({
  session_id: z.string().uuid().optional(),
  message: z.string().trim().max(2000).default(''),
  profile: Profile.optional(),
  scan: ScanSummary.nullable().optional(),
  clear_fields: z.array(ClearField).max(8).optional(),
  action: z.enum(['message', 'search', 'explain', 'affordable', 'why']).default('message'),
}).strict();
export const providerInput = z.object({ zip: Zip, specialty: Specialty.default('family_medicine'), limit: z.number().int().min(1).max(8).default(5) }).strict();
export const clinicInput = z.object({ zip: Zip, limit: z.number().int().min(1).max(8).default(5) }).strict();
export const planInput = z.object({ insurance: Insurance, zip: Zip.optional() }).strict();
export const contextInput = z.object({ topic: z.enum(['measurement', 'getting_started', 'retry', 'watch', 'models', 'privacy', 'insurance', 'all']).default('all') }).strict();
export function hasExactPlan(insurance) {
  return insurance?.status === 'insured' && !!insurance.payer && !!insurance.plan && !!insurance.network;
}
export function publicValidation(error) {
  return error.issues?.map(i => ({ path: i.path.join('.'), message: i.message })) ?? [];
}
export function scanJsonSchema() {
  return { ...z.toJSONSchema(ScanSummary), $id: 'urn:chest-bpm:scan-summary:1.1',
    allOf: [
      { if: { properties: { quality: { const: 'usable' } } }, then: { properties: { estimated_bpm: { type: 'number', minimum: 20, maximum: 300 } } }, else: { properties: { estimated_bpm: { type: 'null' } }, not: { required: ['timing_counters'] } } },
      { if: { properties: { schema_version: { const: '1.1' } } }, then: { not: { required: ['duration_seconds'] } }, else: { not: { anyOf: [{ required: ['timing_counters'] }, { required: ['analysis_window_seconds'] }] } } },
    ] };
}
