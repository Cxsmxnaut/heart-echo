// Synthetic example only. Existing iPhone/Watch audio capture remains untouched.
// A future native integration sends this same JSON over a separately configured API.
import { readFile } from 'node:fs/promises';
const scan = JSON.parse(await readFile(new URL('./scan-handoff.json', import.meta.url), 'utf8'));
const response = await fetch(`${process.env.CARE_BASE_URL || 'http://127.0.0.1:4318'}/api/v1/chat`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', ...(process.env.CARE_API_TOKEN ? { Authorization: `Bearer ${process.env.CARE_API_TOKEN}` } : {}) },
  body: JSON.stringify({ scan, action: 'explain' }),
});
if (!response.ok) throw Error(`Care assistant returned HTTP ${response.status}`);
const result = await response.json();
console.log(JSON.stringify({ session_id: result.session_id, explanation: result.scan_explanation, model: result.model }, null, 2));
