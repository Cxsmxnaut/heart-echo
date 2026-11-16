// Isolated, keyless review mode. Do not load local env/pairing files here.
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const usage = 'Usage: npm run judge -- [--no-open] [--port 0..65535]\n' +
  'Starts guided directory mode on this computer. No AI key or model download is used.\n' +
  'Use --port 0 for an automatically assigned port and --no-open for headless review.';

export function judgeOptions(args) {
  const options = { port: 4318, openBrowser: true, help: false };
  for (let index = 0; index < args.length; index++) {
    const argument = args[index];
    if (argument === '--no-open') options.openBrowser = false;
    else if (argument === '--help' || argument === '-h') options.help = true;
    else if (argument === '--port' || argument.startsWith('--port=')) {
      const value = argument === '--port' ? args[++index] : argument.slice(7);
      if (!/^\d{1,5}$/.test(value || '') || Number(value) > 65535) throw Error('Choose a port from 0 to 65535.');
      options.port = Number(value);
    } else throw Error(`Unknown option. ${usage}`);
  }
  return options;
}

async function judgeApp(tools) {
  const [{ createApp }, { createService }, { createModel }, { createMcpTools },
    { createTools }, { createDirectories }] = await Promise.all([
    import('../src/server.js'), import('../src/service.js'), import('../src/model.js'),
    import('../src/tool-client.js'), import('../src/tools.js'), import('../src/directories.js'),
  ]);
  // Explicit injection defeats inherited keys and the normal provider selection.
  // Directory tools remain live and use the same validated MCP path as the app.
  const model = createModel({ provider: 'guided' });
  const service = createService({ model, tools: tools ?? createMcpTools(createTools(createDirectories({ timeoutMs: 12000 }))) });
  return createApp({ service, apiToken: '', pairingCode: '', allowedHosts: [], demoConnection: null });
}

function listen(app, port) {
  const server = createServer(app);
  return new Promise((resolve, reject) => {
    const failed = error => reject(error);
    server.once('error', failed);
    server.listen(port, '127.0.0.1', () => {
      server.removeListener('error', failed);
      resolve(server);
    });
  });
}

function openPage(url) {
  const command = process.platform === 'darwin' ? ['open', url]
    : process.platform === 'win32' ? ['cmd', '/c', 'start', '', url] : ['xdg-open', url];
  const browser = spawn(command[0], command.slice(1), { stdio: 'ignore' });
  browser.on('error', () => console.log('The browser could not open automatically. Open the local URL above.'));
  browser.unref();
}

export async function startJudgeDemo({ port = 4318, openBrowser = true, tools, log = console.log } = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw Error('Choose a port from 0 to 65535.');
  const app = await judgeApp(tools);
  let server;
  try { server = await listen(app, port); }
  catch (error) {
    if (error.code !== 'EADDRINUSE' || port === 0) throw error;
    log(`Port ${port} is in use. Choosing a free port; the existing service was left running.`);
    server = await listen(app, 0);
  }
  const url = `http://127.0.0.1:${server.address().port}`;
  let stopping;
  function close() {
    stopping ??= new Promise(resolve => {
      const timer = setTimeout(() => server.closeAllConnections(), 1000);
      timer.unref();
      server.close(() => { clearTimeout(timer); resolve(); });
      server.closeIdleConnections();
    });
    return stopping;
  }
  log(`Heart Echo judge demo is ready at ${url}`);
  log('Guided directory mode: no generated AI replies. Public directory searches need internet.');
  log('This review server is available only on this computer. Control-C stops it.');
  log(`HEART_ECHO_JUDGE_READY ${JSON.stringify({ url, mode: 'guided', bind: '127.0.0.1', directories: tools ? 'injected_test_tools' : 'live_public_sources' })}`);
  if (openBrowser) openPage(url);
  return { server, url, close };
}

async function main() {
  if (Number(process.versions.node.split('.')[0]) < 22) {
    console.error('Heart Echo judge mode needs Node.js 22 or newer. Install it, then run npm ci in care-assistant.');
    process.exitCode = 1; return;
  }
  try {
    const options = judgeOptions(process.argv.slice(2));
    if (options.help) { console.log(usage); return; }
    const demo = await startJudgeDemo(options);
    let stopping = false;
    const stop = async () => {
      if (stopping) return;
      stopping = true;
      await demo.close();
      process.exit(0);
    };
    process.once('SIGINT', stop);
    process.once('SIGTERM', stop);
  } catch (error) {
    if (error.code === 'ERR_MODULE_NOT_FOUND') {
      console.error('Judge demo dependencies are missing. Run npm ci in care-assistant, then npm run judge.');
    } else if (error.message?.startsWith('Choose a port') || error.message?.startsWith('Unknown option')) {
      console.error(error.message);
    } else {
      console.error('The judge demo could not start. Check that Node.js 22+ and npm ci are available, then try --port 0.');
    }
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
