// Run with node --test tests/test_codex_adapter.cjs. All providers/DOMs are fixtures.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const adapter = require('../scripts/codex_adapter.js');
const wrapped = value => ({structuredContent: value});
const getComputedStyle = element => element.style || {display: 'block', visibility: 'visible', opacity: '1'};

function fixture(options = {}) {
  const calls = [], receipts = {}, verification = {};
  const bundle = {provider: 'supermemory', space: 'fixture', artifacts: [{account_key: 'source:a',
    version_id: 'version-one', content: '---\n{"fixture":"exact"}\n---\nA “quote”, apostrophe\'s and 👀.'}]};
  const imported = [];
  const tools = {
    exec_command: async ({cmd}) => {
      calls.push(['runtime', cmd]);
      const operation = /runtime\.py' '([^']+)'/.exec(cmd)?.[1];
      // Undo only the adapter's deterministic POSIX quoting to inspect JSON in mocks.
      const input = cmd.startsWith('printf %s ') ? JSON.parse(cmd.slice(10, cmd.indexOf(' | ')).slice(1, -1).replace(/'\\''/g, "'")) : undefined;
      let value;
      if (cmd.includes('run_budget.py')) value = {remaining_seconds: options.seconds ?? 60};
      else if (operation === 'memory') {
        if (options.runtimeFailure) return {exit_code: 1, output: 'Traceback: TypeError'};
        if (options.truncated) return {exit_code: 0, output: '{"artifacts":['};
        value = bundle;
      } else if (operation === 'import-history') {
        imported.push(input); value = {imported: true, complete: input.complete, documents: input.documents.length};
      } else if (operation === 'transfer') {
        const account = input.account_key;
        if (input.action === 'begin' && !receipts[account]) {
          receipts[account] = {attempted: true, document_id: null};
          value = {...receipts[account], may_save: true};
        } else {
          if (input.action === 'ack') receipts[account].document_id = input.document_id;
          value = {...(receipts[account] || {attempted: false, document_id: null}), may_save: false,
            verification: verification[account] || {status: 'not_attempted'}};
        }
      } else if (operation === 'verify-memory') {
        const status = input.document.status !== 'done' ? 'pending' :
          input.document.content === bundle.artifacts[0].content ? 'verified' : 'failed';
        verification[input.account_key] = value = {status};
      } else value = {ok: true};
      return {exit_code: 0, output: JSON.stringify(value)};
    },
    mcp__supermemory__list_spaces: async () => { calls.push(['spaces']); return wrapped({spaces: [{containerTag: 'fixture'}]}); },
    mcp__supermemory__list_documents: async args => {
      calls.push(['list', args]);
      if (options.listFailure) throw new Error('fixture failure');
      return wrapped({documents: [{id: 'one'}, {id: args.page === 1 ? 'two' : 'one'}],
        pagination: {currentPage: args.page, totalPages: 2, limit: 50, totalItems: options.missingListedItem ? 3 : 2}});
    },
    mcp__supermemory__get_document: async ({documentId}) => {
      calls.push(['get', documentId]);
      if (options.getFailure) throw new Error('fixture failure');
      return wrapped({document: {id: documentId, status: options.pending ? 'queued' : 'done', contentTruncated: false,
        content: documentId === 'saved' ? (options.wrongContent ? 'Traceback: TypeError' : bundle.artifacts[0].content) : 'Original ' + documentId + '\n👀'}});
    },
    mcp__supermemory__add_memory: async args => {
      calls.push(['save', args]);
      if (options.uncertainSave) throw new Error('Connection lost after request');
      return wrapped({success: true, id: 'saved', containerTag: 'fixture'});
    }
  };
  const state = {};
  const make = () => adapter.create({tools, python: '/fixture/python', scripts: '/fixture/scripts', run: 'fixture-run', space: 'fixture', state});
  return {bridge: make(), make, tools, calls, bundle, imported, state};
}

test('exact discovery emits names only and excludes adjacent namespaces', () => {
  assert.deepEqual(adapter.discover([
    {name: 'mcp__supermemory__get_document', description: 'long'},
    {name: 'mcp__other__get_document'}, {name: 'mcp__mail__list'}, {name: 'mcp__mail_extra__list'}
  ], ['mail']), ['mcp__supermemory__get_document', 'mcp__mail__list']);
});
test('history originals are fetched once, imported unchanged and reused after wrapper recreation', async () => {
  const f = fixture();
  assert.deepEqual(await f.bridge.retrieveHistory(), {imported: true, complete: true, documents: 2});
  await f.make().retrieveHistory();
  assert.equal(f.calls.filter(c => c[0] === 'list').length, 2);
  assert.deepEqual(f.calls.filter(c => c[0] === 'get').map(c => c[1]), ['one', 'two']);
  assert.equal(f.imported.length, 1);
  assert.equal(f.imported[0].documents[0].content, 'Original one\n👀');
});
test('failed history pages and documents remain explicit continuity limits', async () => {
  const f = fixture({listFailure: true});
  assert.equal((await f.bridge.retrieveHistory()).complete, false);
  const g = fixture({getFailure: true});
  await g.bridge.retrieveHistory();
  assert.equal(g.imported[0].documents[0].status, 'failed');
  assert.equal(g.imported[0].documents[0].content, null);
  const h = fixture({missingListedItem: true});
  assert.equal((await h.bridge.retrieveHistory()).complete, false);
});
test('nonzero or truncated preparation output never reaches provider', async () => {
  for (const options of [{runtimeFailure: true}, {truncated: true}]) {
    const f = fixture(options);
    await assert.rejects(f.bridge.saveMemory());
    assert.equal(f.calls.filter(c => c[0] === 'save').length, 0);
  }
});
test('exact artifact is saved and verified once; repeat invocation does not upload again', async () => {
  const f = fixture();
  assert.equal((await f.bridge.saveMemory()).results[0].status, 'verified');
  await f.make().saveMemory();
  assert.equal(f.calls.filter(c => c[0] === 'save').length, 1);
  assert.equal(f.calls.find(c => c[0] === 'save')[1].content, f.bundle.artifacts[0].content);
  assert.equal(f.calls.filter(c => c[0] === 'get').length, 1);
});
test('uncertain writes, changed content and queued originals cannot become success', async () => {
  for (const [options, expected] of [[{uncertainSave: true}, 'unverified'], [{wrongContent: true}, 'failed'], [{pending: true}, 'pending']]) {
    const f = fixture(options);
    assert.equal((await f.bridge.saveMemory()).results[0].status, expected);
    await f.make().saveMemory();
    assert.equal(f.calls.filter(c => c[0] === 'save').length, 1);
  }
});
test('wrong target and malformed late artifact fail before any save', async () => {
  const f = fixture(); f.bundle.space = 'other';
  await assert.rejects(f.bridge.saveMemory());
  const g = fixture(); g.bundle.artifacts.push({content: 'Traceback'});
  await assert.rejects(g.bridge.saveMemory());
  for (const h of [f, g]) assert.equal(h.calls.filter(c => c[0] === 'save').length, 0);
});
test('quiet run and expired budget make no remote writes', async () => {
  const f = fixture(); f.bundle.artifacts = [];
  await f.bridge.saveMemory();
  assert.equal(f.calls.filter(c => c[0] === 'spaces').length, 0);
  const g = fixture({seconds: 0}); await g.bridge.saveMemory();
  assert.equal(g.calls.filter(c => c[0] === 'save').length, 0);
});
test('MCP error envelopes fail closed and state cannot cross runs', () => {
  assert.throws(() => adapter.decoded({isError: true, structuredContent: {success: true}}));
  const f = fixture();
  assert.throws(() => adapter.create({tools: f.tools, python: '/fixture/python', scripts: '/fixture/scripts',
    run: 'different-run', space: 'fixture', state: f.state}));
  f.bridge.clear(); assert.deepEqual(f.state, {});
});

function browserFixture({ids = ['1', '2', '3'], seen = [], limit = 2, loading = false, end = false, more = false} = {}) {
  const reads = [];
  const element = (text, href) => ({innerText: text, href, getClientRects: () => [{}]});
  const cards = ids.map(id => ({getClientRects: () => [{}], querySelectorAll: selector => {
    reads.push([id, selector]);
    return [selector === '.id' ? element('', 'https://x.com/Author/status/' + id) : element(selector === '.sender' ? 'Author' : 'Exact “text” ' + id + ' 👀')];
  }}));
  const document = {querySelectorAll: selector => selector === '.card' ? cards :
    (selector === '.loading' && loading || selector === '.end' && end || selector === '.more' && more) ? [element('marker')] : []};
  const fn = vm.runInNewContext(fs.readFileSync(__dirname + '/../scripts/browser_extract.js', 'utf8'), {URL, Date, document, getComputedStyle});
  const input = {window: {ticket: 'fixture', limit, seen_identifiers: seen, deadline_ms: Date.now() + 60000},
    recipe: {card_selector: '.card', identifier: {selector: '.id', attribute: 'href'},
      basis: {sender: {selector: '.sender'}, text: {selector: '.text'}},
      loading_selector: '.loading', end_selector: '.end', more_selector: '.more'}};
  return {fn, input, reads};
}
test('DOM extraction stops before reading the excess card identity/body', () => {
  const f = browserFixture(); const result = f.fn(f.input);
  assert.equal(result.cards.length, 2);
  assert.equal(result.more_available, true);
  assert.equal(f.reads.some(([id]) => id === '3'), false);
  assert.equal(result.cards[0].basis.text, 'Exact “text” 1 👀');
});
test('seen aliases and duplicate cards do not repeat body reads or consume allowance', () => {
  const f = browserFixture({ids: ['1', '2', '2', '3'], seen: ['x-status:1'], limit: 2});
  const result = f.fn(f.input);
  assert.deepEqual(Array.from(result.cards, c => c.identifier), ['https://x.com/Author/status/2', 'https://x.com/Author/status/3']);
  assert.equal(f.reads.filter(([id, selector]) => id === '1' && selector !== '.id').length, 0);
  assert.equal(f.reads.filter(([id, selector]) => id === '2' && selector === '.text').length, 1);
});
test('loading, unknown availability, exhaustion and zero allowance are distinct', () => {
  for (const [options, expected] of [[{loading: true}, null], [{ids: []}, null], [{ids: [], end: true}, false], [{limit: 0}, null]]) {
    const f = browserFixture(options); const result = f.fn(f.input);
    assert.equal(result.more_available, expected);
    assert.equal(result.cards.length, 0);
    assert.equal(f.reads.length, 0);
  }
});
test('expired windows cannot read DOM bodies', () => {
  const f = browserFixture(); f.input.window.deadline_ms = 0;
  assert.throws(() => f.fn(f.input)); assert.equal(f.reads.length, 0);
});
test('partial DOM failure counts the unreadable card and continues readable cards', () => {
  const f = browserFixture();
  f.input.recipe.basis.text = {selector: '.missing'};
  // Override the document with a first complete card and second incomplete card.
  const visible = value => ({innerText: value, getClientRects: () => [{}]});
  f.input.window.limit = 3;
  const document = {querySelectorAll: selector => selector === '.card' ? [1, 2, 3].map(id => ({
    getClientRects: () => [{}], querySelectorAll: field => field === '.id' ?
      [{...visible(''), href: 'https://x.com/A/status/' + id}] :
      field === '.missing' && id === 2 ? [] : [visible(field === '.sender' ? 'A' : 'Exact')]
  })) : []};
  const fn = vm.runInNewContext(fs.readFileSync(__dirname + '/../scripts/browser_extract.js', 'utf8'), {URL, Date, document, getComputedStyle});
  const result = fn(f.input);
  assert.equal(result.cards.length, 3);
  assert.equal(result.cards[0].basis.text, 'Exact');
  assert.equal(result.cards[1].identifier, 'https://x.com/A/status/2');
  assert.equal(result.cards[1].basis, undefined);
  assert.ok(result.cards[1].read_error);
  assert.equal(result.cards[2].basis.text, 'Exact');
  assert.equal(result.access_failure, undefined);
});
test('one allowance spans pages without rereading bodies or granting a fresh limit', () => {
  const first = browserFixture({ids: ['1', '2'], limit: 3, more: true});
  const previous = first.fn(first.input);
  const second = browserFixture({ids: ['2', '3', '4'], limit: 3});
  const result = second.fn({...second.input, previous});
  assert.deepEqual(Array.from(result.cards, c => c.identifier), [1, 2, 3].map(id => 'https://x.com/Author/status/' + id));
  assert.equal(second.reads.some(([id, field]) => id === '2' && field === '.text'), false);
  assert.equal(second.reads.some(([id]) => id === '4'), false);
  assert.equal(previous.cards.length, 2);
  assert.throws(() => second.fn({...second.input, previous: {...previous, ticket: 'stale'}}));
});
test('renewed windows accept retained native IDs and observed links as seen aliases', () => {
  const f = browserFixture({seen: ['x:post:1', 'https://twitter.com/Other/status/2'], limit: 2});
  const result = f.fn(f.input);
  assert.deepEqual(Array.from(result.cards, c => c.identifier), ['https://x.com/Author/status/3']);
});
test('observed post links can retain the existing contract native-ID convention', () => {
  const f = browserFixture(); f.input.recipe.identifier.format = 'x:post';
  assert.equal(f.fn(f.input).cards[0].identifier, 'x:post:1');
});

test('adapter → real CLI → mocked provider → original verification completes without extra working files', async () => {
  const os = require('node:os');
  const path = require('node:path');
  const {execFileSync, spawnSync} = require('node:child_process');
  const root = path.resolve(__dirname, '..');
  const python = process.env.ATTENTION_DIET_PYTHON || path.join(os.homedir(), '.cache/attention-diet-venv/bin/python');
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'attention-diet-adapter-test-'));
  const env = {...process.env, XDG_STATE_HOME: folder};
  let opened;
  const cli = (file, ...args) => JSON.parse(execFileSync(python, [path.join(root, 'scripts', file), ...args], {env, encoding: 'utf8'}));
  try {
    const contract = JSON.parse(fs.readFileSync(path.join(root, 'templates/attention-contract.json')));
    contract.memory_context = {provider: 'supermemory', space: 'fixture',
      purpose: 'avoid_repeating_previously_briefed_items', on_unavailable: 'continue_with_notice'};
    const contractPath = path.join(folder, 'contract.json');
    fs.writeFileSync(contractPath, JSON.stringify(contract));
    const plan = cli('run_plan.py', '--host', 'codex', '--contract', contractPath);
    opened = cli('runtime.py', 'start', '--contract', contractPath, '--expected-digest', plan.contract_digest);
    const documents = new Map();
    let saves = 0, reads = 0;
    const tools = {
      exec_command: async ({cmd}) => {
        const proc = spawnSync('/bin/sh', ['-c', cmd], {encoding: 'utf8', env});
        return {exit_code: proc.status, output: proc.stdout + proc.stderr};
      },
      mcp__supermemory__list_spaces: async () => wrapped({spaces: [{containerTag: 'fixture'}]}),
      mcp__supermemory__list_documents: async () => wrapped({documents: [],
        pagination: {currentPage: 1, totalPages: 0, totalItems: 0, limit: 50}}),
      mcp__supermemory__add_memory: async args => {
        saves++; documents.set('fixture-original', args.content);
        return wrapped({success: true, id: 'fixture-original', containerTag: args.containerTag});
      },
      mcp__supermemory__get_document: async ({documentId}) => {
        reads++; return wrapped({document: {id: documentId, status: 'done', contentTruncated: false, content: documents.get(documentId)}});
      }
    };
    const config = {tools, python, scripts: path.join(root, 'scripts'), run: opened.run_id, space: 'fixture'};
    const bridge = adapter.create(config);
    await bridge.retrieveHistory();
    await bridge.retrieveHistory();
    const window = await bridge.window({account_key: 'example-source:account', thread_id: 'source-1', surface: 'items', max_items: 2});
    const browser = browserFixture(); browser.input.window = window;
    const observation = browser.fn(browser.input);
    const captured = await bridge.capture(observation);
    assert.equal(captured.coverage[0].inspected_count, 2);
    const entry = JSON.parse(fs.readFileSync(path.join(root, 'examples/selection.json'))).entries[0];
    delete entry.items;
    entry.item_refs = [captured.references[0].ref];
    entry.summary = 'Literal $(printf unsafe), `printf unsafe`, pipe | and apostrophe\'s “text” 👀.';
    await bridge.finalize({title: 'Fixture briefing', overview: 'Synthetic only.', entries: [entry], notices: []});
    assert.equal(fs.readdirSync(opened.workspace).length, 4);
    const saved = await bridge.saveMemory();
    assert.equal(saved.results[0].status, 'verified');
    const prepared = JSON.parse(fs.readFileSync(path.join(opened.workspace, 'memory.json'))).artifacts[0].content;
    assert.equal(documents.get('fixture-original'), prepared);
    const statePath = path.join(folder, 'attention-diet/runs', opened.run_id + '.json');
    assert.equal(JSON.parse(fs.readFileSync(statePath)).selection.entries[0].summary, entry.summary);
    // Durable receipts prevent a second upload even after all host state is lost.
    assert.equal((await adapter.create(config).saveMemory()).results[0].status, 'verified');
    assert.equal(saves, 1); assert.equal(reads, 1);
    const finished = cli('runtime.py', 'finish', '--run', opened.run_id);
    assert.equal(finished.entries, 1);
    assert.ok(!finished.rendered.includes('storage has not been verified'));
    assert.equal(fs.existsSync(opened.workspace), false);
  } finally {
    if (opened && fs.existsSync(opened.workspace) && path.basename(opened.workspace).startsWith('attention-diet-' + opened.run_id + '-')) {
      for (const file of fs.readdirSync(opened.workspace)) fs.unlinkSync(path.join(opened.workspace, file));
      fs.rmdirSync(opened.workspace);
    }
    fs.rmSync(folder, {recursive: true, force: true});
  }
});

test('26 seen plus seven rendered with four slots never reads the three excess identities or bodies', () => {
  const f = browserFixture({ids: Array.from({length: 33}, (_, i) => String(i)),
    seen: Array.from({length: 26}, (_, i) => 'x:post:' + i), limit: 4});
  const result = f.fn(f.input);
  assert.equal(result.cards.length, 4);
  assert.equal(f.reads.filter(([, field]) => field === '.text').length, 4);
  assert.equal(f.reads.some(([id]) => Number(id) >= 30), false);
});
test('only a fresh explicit end marker emits structured exhaustion evidence', () => {
  const first = browserFixture({ids: ['1'], limit: 4, end: true});
  const previous = first.fn(first.input);
  assert.equal(previous.exhaustion.kind, 'explicit_end_marker');
  const next = browserFixture({ids: [], limit: 4, loading: true});
  const result = next.fn({...next.input, previous});
  assert.equal(result.more_available, null);
  assert.equal(result.exhaustion, undefined);
});
