import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { pathToFileURL } from 'node:url';
import { createTools } from './tools.js';

export function createMcpServer(tools = createTools()) {
  const server = new McpServer({ name: 'chest-bpm-care', version: '0.1.0' });
  for (const t of tools.entries) {
    server.registerTool(t.name, { description: t.description, inputSchema: t.schema.shape,
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true } }, async args => {
      try { const result = await tools.call(t.name, args); return { content: [{ type: 'text', text: JSON.stringify(result) }], isError: result.status === 'error' }; }
      catch { return { content: [{ type: 'text', text: JSON.stringify({ status: 'error', error: 'invalid_tool_arguments' }) }], isError: true }; }
    });
  }
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await createMcpServer().connect(new StdioServerTransport());
}
