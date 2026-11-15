import test from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { fileURLToPath } from 'node:url';
test('external stdio MCP client lists four read-only tools, reads app facts, rejects invalid ZIP', async () => {
  const transport = new StdioClientTransport({ command: process.execPath, args: [fileURLToPath(new URL('../src/mcp.js', import.meta.url))], stderr: 'pipe' });
  const client = new Client({ name: 'synthetic-stdio-test', version: '1.0' });
  try {
    await client.connect(transport); const list = await client.listTools(); assert.equal(list.tools.length, 4); assert.ok(list.tools.every(t => t.annotations.readOnlyHint));
    const r = await client.callTool({ name: 'get_app_context', arguments: { topic: 'measurement' } }); assert.match(r.content[0].text, /does not diagnose/);
    const invalid = await client.callTool({ name: 'search_providers', arguments: { zip: 'bad' } }); assert.equal(invalid.isError, true);
  } finally { await client.close(); }
});
