import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { createMcpServer } from './mcp.js';
import { createTools } from './tools.js';

// The web backend uses the same real MCP boundary as an external stdio client,
// over an in-memory transport so no extra daemon/process is needed per request.
export function createMcpTools(implementations = createTools()) {
  let ready;
  async function connect() {
    const server = createMcpServer(implementations);
    const client = new Client({ name: 'care-web-backend', version: '0.1.0' });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
    return client;
  }
  return {
    entries: implementations.entries,
    definitions: implementations.definitions,
    async call(name, args) {
      // Validate before crossing MCP and again inside the server.
      const spec = implementations.entries.find(t => t.name === name);
      if (!spec) throw new Error('unknown_tool');
      const validated = spec.schema.parse(args);
      ready ??= connect();
      const client = await ready;
      const result = await client.callTool({ name, arguments: validated });
      const text = result.content?.find(c => c.type === 'text')?.text;
      if (!text) throw new Error('invalid_mcp_result');
      return JSON.parse(text);
    },
  };
}
