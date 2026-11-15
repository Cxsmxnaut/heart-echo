import { z } from 'zod';
import { createDirectories } from './directories.js';
import { providerInput, clinicInput, planInput, contextInput } from './schema.js';
import { APP_CONTEXT } from './knowledge.js';

export function createTools(directories = createDirectories()) {
  const specs = [
    ['search_providers', 'Search CMS NPPES for provider identities/practices in an exact US ZIP. Does not verify insurance, availability, diagnosis, or need for a specialist.', providerInput, a => directories.searchProviders(a)],
    ['lookup_plan_network', 'Look up an exact payer, plan and network. The Health Plan Medicare can return evidenced plan/network/practice links for a requested year; other payers only return CMS catalog candidates. Never verifies member eligibility, benefits, or cost.', planInput, a => directories.lookupPlanNetwork(a)],
    ['search_affordable_clinics', 'Search active HRSA-listed health center sites in an exact ZIP. Services vary. Ask the clinic about sliding fees; no guaranteed free care, prices, or insurance participation.', clinicInput, a => directories.searchAffordableClinics(a)],
    ['get_app_context', 'Retrieve the versioned app facts about experimental BPM/sound timing, limitations, privacy, and insurance.', contextInput, a => Promise.resolve({ version: APP_CONTEXT.version, source: APP_CONTEXT.source, sections: a.topic === 'all' ? APP_CONTEXT : { [a.topic]: APP_CONTEXT[a.topic] } })],
  ];
  const entries = specs.map(([name, description, schema, execute]) => ({ name, description, schema, execute }));
  const map = new Map(entries.map(t => [t.name, t]));
  return {
    entries,
    definitions: entries.map(t => ({ type: 'function', function: { name: t.name, description: t.description, parameters: z.toJSONSchema(t.schema, { target: 'draft-7' }) } })),
    async call(name, args) {
      const tool = map.get(name);
      if (!tool) throw new Error('unknown_tool');
      return tool.execute(tool.schema.parse(args));
    },
  };
}
