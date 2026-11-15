// Isolated temporary UI/backend for candidate checks; never changes .env/default.
import {writeFile} from 'node:fs/promises';
import {createApp} from '../../src/server.js';
import {createService} from '../../src/service.js';
import {createModel} from '../../src/model.js';
import {createMcpTools} from '../../src/tool-client.js';
const file=process.argv[2];if(!file)throw Error('Ready-file required');
const model=createModel({provider:'compatible',model:'care-gemma4-e4b',baseUrl:'http://127.0.0.1:4324/v1',timeoutMs:45000,temperature:0,toolMode:'batch'});
const server=createApp({service:createService({model,tools:createMcpTools()})}).listen(0,'127.0.0.1',async()=>{await writeFile(file,JSON.stringify({url:`http://127.0.0.1:${server.address().port}`}));});
for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>server.close(()=>process.exit(0)));
