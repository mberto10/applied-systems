import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { once } from 'node:events';
import { request } from 'node:http';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { createHttpServer } from '../server/index.mjs';
import { BoardStore } from '../server/boards.mjs';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { RESOURCE_URI } from '../server/app.mjs';

const testStore = new BoardStore(':memory:');
const testDir = mkdtempSync(join(tmpdir(), 'next-up-test-'));
const toolNames = ['render_next_steps', 'read_work_plan', 'read_work_events', 'apply_plan_patch', 'record_criterion_result', 'set_step_state', 'report_work_activity', 'acknowledge_plan_changes', 'open_next_steps_panel', 'update_next_steps_panel', 'read_next_steps_panel', 'list_workboards', 'import_work_source', 'change_workboard', 'record_work_dispatch'];
let http;
let base;
before(async () => {
  http = createHttpServer({ store: testStore });
  http.listen(0, '127.0.0.1');
  await once(http, 'listening');
  base = `http://127.0.0.1:${http.address().port}`;
});
after(async () => { await new Promise(resolve => http.close(resolve)); testStore.close(); rmSync(testDir, { recursive: true, force: true }); });
async function withClient(fn) {
  const client = new Client({ name: 'next-up-test', version: '1.0.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL(`${base}/mcp`)));
  try { return await fn(client); } finally { await client.close(); }
}
const step = { label: 'Check the result', reason: 'Verify the requested behavior.', prompt: 'Check the result against the requirements.' };

test('MCP discovery advertises renderer, panel tools, and readable HTML', async () => {
  await withClient(async client => {
    const { tools } = await client.listTools();
    assert.deepEqual(tools.map(t => t.name), toolNames);
    assert.equal(tools[0].annotations.readOnlyHint, true);
    assert.equal(tools[0]._meta.ui.resourceUri, RESOURCE_URI);
    const resource = await client.readResource({ uri: RESOURCE_URI });
    assert.equal(resource.contents[0].mimeType, 'text/html;profile=mcp-app');
    assert.match(resource.contents[0].text, /<title>Next up<\/title>/);
    assert.deepEqual(resource.contents[0]._meta.ui.csp.connectDomains, []);
  });
});

test('renderer round-trips real-shaped Linear context and a model-readable fallback', async () => {
  const args = { steps: [{ ...step, issue: { identifier: 'TEST-42', url: 'https://linear.app/example/issue/TEST-42/test-fixture' } }] };
  await withClient(async client => {
    const result = await client.callTool({ name: 'render_next_steps', arguments: args });
    assert.ok(!result.isError);
    assert.deepEqual(result.structuredContent, args);
    assert.match(result.content[0].text, /TEST-42/);
    assert.match(result.content[0].text, /Check the result against the requirements/);
  });
});

test('rejects empty/oversized/duplicate suggestions and invalid issue references', async () => {
  const invalid = [
    { steps: [] },
    { steps: Array.from({ length: 4 }, (_, i) => ({ ...step, prompt: `Step ${i}` })) },
    { steps: [step, step] },
    { steps: [{ ...step, prompt: '  ' }] },
    { steps: [{ ...step, prompt: 'x'.repeat(2001) }] },
    { steps: [{ ...step, issue: { identifier: 'TEST-42', url: 'javascript:alert(1)' } }] },
    { steps: [{ ...step, issue: { identifier: 'TEST-42', url: 'https://linear.app.evil.example/issue/TEST-42' } }] },
  ];
  await withClient(async client => {
    for (const args of invalid) {
      const result = await client.callTool({ name: 'render_next_steps', arguments: args });
      assert.equal(result.isError, true, JSON.stringify(args));
    }
  });
});

test('independent requests never mix suggestions', async () => {
  const prompts = ['Conversation A: inspect the draft.', 'Conversation B: verify the implementation.'];
  const results = await Promise.all(prompts.map(prompt => withClient(client => client.callTool({ name: 'render_next_steps', arguments: { steps: [{ ...step, prompt }] } }))));
  assert.deepEqual(results.map(r => r.structuredContent.steps[0].prompt), prompts);
});

test('HTTP boundary rejects malformed and oversized payloads and foreign origins', async () => {
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
  assert.equal((await fetch(`${base}/mcp`, { method: 'POST', headers, body: '{' })).status, 400);
  assert.equal((await fetch(`${base}/mcp`, { method: 'POST', headers, body: JSON.stringify({ value: 'x'.repeat(66000) }) })).status, 413);
  assert.equal((await fetch(`${base}/mcp`, { method: 'POST', headers: { ...headers, Origin: 'https://unrelated.example' }, body: '{}' })).status, 403);
  const status = await new Promise((resolve, reject) => {
    const req = request(`${base}/mcp`, { method: 'POST', headers: { ...headers, Host: 'unrelated.example' } }, res => {
      res.resume();
      resolve(res.statusCode);
    });
    req.on('error', reject);
    req.end('{}');
  });
  assert.equal(status, 403);
});

test('normal server exposes health but not development preview', async () => {
  assert.equal((await fetch(`${base}/healthz`)).status, 200);
  assert.equal((await fetch(base)).status, 404);
  assert.equal((await fetch(`${base}/card`)).status, 404);
  assert.equal((await fetch(`${base}/mcp`)).status, 405);
});

test('stdio mode supports the same tools for a supervised private tunnel', async () => {
  const client = new Client({ name: 'tunnel-stdio-test', version: '1.0.0' });
  const transport = new StdioClientTransport({ command: process.execPath, env: { PATH: process.env.PATH, NEXT_UP_DB: join(testDir, 'stdio.sqlite') }, args: [fileURLToPath(new URL('../server/stdio.mjs', import.meta.url))] });
  try {
    await client.connect(transport);
    assert.deepEqual((await client.listTools()).tools.map(t => t.name), toolNames);
    const result = await client.callTool({ name: 'render_next_steps', arguments: { steps: [step] } });
    assert.deepEqual(result.structuredContent.steps, [step]);
  } finally { await client.close(); }
});

 test('panel entrypoint accepts empty input and isolates independently updated panels', async () => {
  await withClient(async client => {
    const a = (await client.callTool({ name: 'open_next_steps_panel', arguments: {} })).structuredContent;
    const b = (await client.callTool({ name: 'open_next_steps_panel', arguments: {} })).structuredContent;
    assert.notEqual(a.panel_id, b.panel_id);
    await client.callTool({ name: 'update_next_steps_panel', arguments: { panel_id: a.panel_id, steps: [step] } });
    const read = async id => (await client.callTool({ name: 'read_next_steps_panel', arguments: { panel_id: id } })).structuredContent;
    assert.deepEqual((await read(a.panel_id)).steps, [step]);
    assert.deepEqual((await read(b.panel_id)).steps, []);
    assert.equal((await read(a.panel_id)).revision, 1);
    await client.callTool({ name: 'update_next_steps_panel', arguments: { panel_id: a.panel_id, steps: [step] } });
    assert.equal((await read(a.panel_id)).revision, 2);
    assert.equal((await client.callTool({ name: 'read_next_steps_panel', arguments: { panel_id: '00000000-0000-4000-8000-000000000000' } })).isError, true);
    const tool = (await client.listTools()).tools.find(t => t.name === 'open_next_steps_panel');
    assert.deepEqual(tool._meta['openai/ui'].entrypoints, [{ type: 'thread' }]);
    const resource = (await client.readResource({ uri: tool._meta.ui.resourceUri })).contents[0];
    assert.equal(resource._meta['openai/ui'].preferredDisplayMode, 'fullscreen');
    assert.match(resource.text, /id="outline"/);
  });
});

test('real MCP workboard flow imports, pins, rejects stale writes, and reserves delivery once', async () => {
  await withClient(async client => {
    const call = (name, args) => client.callTool({ name, arguments: args });
    let b = (await call('open_next_steps_panel', {title:'Integration fixture'})).structuredContent;
    b = (await call('import_work_source', {panel_id:b.panel_id,expected_revision:b.revision,source:{mode:'markdown',title:'Test plan',markdown:'# Plan\n- [ ] Review <!-- next-up:review -->'}})).structuredContent;
    b = (await call('change_workboard', {panel_id:b.panel_id,expected_revision:b.revision,action:'pin',mode:'markdown',node_id:'id:review'})).structuredContent;
    assert.equal(b.pins.length,1);
    assert.equal((await call('change_workboard', {panel_id:b.panel_id,expected_revision:0,action:'remove',key:b.pins[0].key})).isError,true);
    b = (await call('record_work_dispatch', {panel_id:b.panel_id,prompt:'Review the fixture.',outcome:'pending'})).structuredContent;
    assert.equal((await call('record_work_dispatch', {panel_id:b.panel_id,prompt:'Review the fixture.',outcome:'pending'})).isError,true);
    await call('record_work_dispatch', {panel_id:b.panel_id,prompt:'Review the fixture.',outcome:'rejected'});
    assert.ok(!(await call('record_work_dispatch', {panel_id:b.panel_id,prompt:'Review the fixture.',outcome:'pending'})).isError);
    await call('record_work_dispatch', {panel_id:b.panel_id,prompt:'Review the fixture.',outcome:'sent'});
    assert.equal((await call('record_work_dispatch', {panel_id:b.panel_id,prompt:'Review the fixture.',outcome:'pending'})).isError,true);
    b = (await call('read_next_steps_panel', {panel_id:b.panel_id})).structuredContent;
    assert.equal(b.sources.markdown.nodes[1].status,'open');
    assert.equal(b.pins.length,1);
  });
});

test('shared plan real MCP flow retains stale results without completion',async()=>{
  await withClient(async client=>{
    const {randomUUID}=await import('node:crypto');
    const b=(await client.callTool({name:'open_next_steps_panel',arguments:{}})).structuredContent;
    const call=(name,args={})=>client.callTool({name,arguments:{panel_id:b.panel_id,...args}});
    let r=await call('apply_plan_patch',{operation_id:randomUUID(),expected_definition_revision:0,patches:[{type:'add_step',id:'step',title:'Check UI',criteria:[{id:'criterion',title:'Keyboard navigation works'}]}]});assert.ok(!r.isError);
    await call('acknowledge_plan_changes',{operation_id:randomUUID(),run_id:'test',expected_definition_revision:1});
    r=await call('read_work_plan');assert.equal(r.structuredContent.plan.steps[0].criteria[0].state,'pending');
    await call('apply_plan_patch',{operation_id:randomUUID(),expected_definition_revision:r.structuredContent.plan.definitionRevision,patches:[{type:'edit_criterion',id:'criterion',title:'Keyboard and touch work'}]});
    r=await call('record_criterion_result',{operation_id:randomUUID(),run_id:'test',criterion_id:'criterion',expected_criterion_revision:1,outcome:'satisfied',method:'agent_inspection',evidence:'Checked keyboard'});
    assert.equal(r.structuredContent.outcome.status,'criterion_changed');assert.equal(r.structuredContent.plan.steps[0].criteria[0].state,'pending');
  });
});
