import { writeFile } from 'node:fs/promises';
import { scanJsonSchema } from '../src/schema.js';
import { APP_CONTEXT } from '../src/knowledge.js';
await writeFile(new URL('../docs/scan-summary.v1.schema.json', import.meta.url), JSON.stringify(scanJsonSchema(), null, 2) + '\n');
await writeFile(new URL('../docs/scan-summary.v1.1.schema.json', import.meta.url), JSON.stringify(scanJsonSchema(), null, 2) + '\n');
await writeFile(new URL('../docs/app-knowledge.v1.json', import.meta.url), JSON.stringify(APP_CONTEXT, null, 2) + '\n');
