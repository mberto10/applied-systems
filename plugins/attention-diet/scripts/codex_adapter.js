/* Pure host module: evaluate once in Codex code-mode, inject only the documented
 * tools object. No network, credentials, filesystem library or browser fallback.
 * Keep returned run state with host store/load and clear it at finish. Original
 * documents stay inside each transfer call. Node exports support offline tests. */
(function () {
  const operations = ['list_spaces', 'list_documents', 'get_document', 'add_memory'];
  const names = operations.map(op => 'mcp__supermemory__' + op);
  const requireValue = (condition, message) => { if (!condition) throw new Error(message); };
  const quote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
  function decoded(result) {
    requireValue(result && !result.isError, 'Connector reported an error');
    if (result.structuredContent) return result.structuredContent;
    const blocks = (result.content || []).filter(c => c.type === 'text');
    requireValue(blocks.length === 1, 'Expected one complete structured connector response');
    return JSON.parse(blocks[0].text);
  }
  function discover(catalog, namespaces = []) {
    // Return names only. Signatures are inspected separately for just these names.
    return catalog.filter(t => names.includes(t.name) || namespaces.some(ns =>
      t.name.startsWith((ns.startsWith('mcp__') ? ns : 'mcp__' + ns) + '__'))).map(t => t.name);
  }
  function create({tools, python, scripts, run, space, state = {}}) {
    requireValue(typeof tools.exec_command === 'function', 'Codex command tool is unavailable');
    const binding = JSON.stringify([run, space || null, python, scripts]);
    requireValue(!state.binding || state.binding === binding, 'Adapter state belongs to another run/target');
    state.binding = binding;
    async function command(file, args, payload, maximum = 16000) {
      let cmd = [python, scripts + '/' + file, ...args].map(quote).join(' ');
      if (payload !== undefined) cmd = 'printf %s ' + quote(JSON.stringify(payload)) + ' | ' + cmd + ' --input -';
      const result = await tools.exec_command({cmd, max_output_tokens: maximum});
      requireValue(result.exit_code === 0 && !result.session_id, 'Runtime failed or is unfinished; no provider write');
      const value = JSON.parse(result.output); // Truncation and error output fail closed.
      requireValue(value && typeof value === 'object' && !value.error, 'Runtime returned an invalid result');
      return value;
    }
    const runtime = (op, payload, extra = []) => command('runtime.py', [op, '--run', run, ...extra], payload);
    async function provider(op, args) {
      const name = 'mcp__supermemory__' + op;
      requireValue(typeof tools[name] === 'function', 'Required connector operation is unavailable: ' + name);
      return decoded(await tools[name](args));
    }
    async function deadline() {
      const report = await command('run_budget.py', ['check', '--run', run]);
      return Date.now() + report.remaining_seconds * 1000;
    }
    async function checkSpace() {
      requireValue(typeof space === 'string' && space.length > 0, 'An explicit configured space is required');
      if (!state.spaceChecked) {
        const result = await provider('list_spaces', {});
        requireValue(Array.isArray(result.spaces) && result.spaces.some(s => s.containerTag === space), 'Configured space unavailable');
        state.spaceChecked = true;
      }
    }
    async function retrieveHistory() {
      if (state.historyImported) return state.historyImported;
      await checkSpace();
      const until = await deadline();
      const documents = Object.create(null);
      const exportData = {space, complete: false, documents: []};
      let page = 1, totalPages, totalItems;
      try {
        while (Date.now() < until) {
          const result = await provider('list_documents', {containerTag: space, page, limit: 50});
          const pagination = result.pagination;
          requireValue(Array.isArray(result.documents) && pagination && pagination.currentPage === page &&
            Number.isInteger(pagination.totalPages) && pagination.totalPages >= 0 &&
            Number.isInteger(pagination.totalItems) && pagination.totalItems >= 0, 'Invalid history pagination');
          requireValue(totalPages === undefined || totalPages === pagination.totalPages && totalItems === pagination.totalItems,
            'History changed during pagination');
          totalPages = pagination.totalPages;
          totalItems = pagination.totalItems;
          for (const entry of result.documents) {
            requireValue(typeof entry.id === 'string' && entry.id.length > 0, 'Missing original document ID');
            if (Object.hasOwn(documents, entry.id)) continue;
            requireValue(Date.now() < until, 'History retrieval reached the run deadline');
            let document;
            try {
              document = (await provider('get_document', {documentId: entry.id})).document;
              requireValue(document && document.id === entry.id && typeof document.status === 'string' &&
                typeof document.contentTruncated === 'boolean' &&
                (document.content === null || typeof document.content === 'string'), 'Invalid original document');
            } catch (_) {
              document = {id: entry.id, status: 'failed', contentTruncated: true, content: null};
            }
            documents[entry.id] = {id: document.id, status: document.status,
              contentTruncated: document.contentTruncated, content: document.content};
          }
          if (page >= totalPages) { exportData.complete = Object.keys(documents).length === totalItems; break; }
          page++;
        }
      } catch (_) { /* Incomplete history is exported as such, never as empty success. */ }
      exportData.documents = Object.values(documents);
      // Originals move directly from connector to helper, never through a model rewrite.
      state.historyImported = await runtime('import-history', exportData);
      return state.historyImported;
    }
    async function saveMemory() {
      const batch = await runtime('memory');
      if (Array.isArray(batch.saved)) return {saved: batch.saved.length, provider: 'local'};
      requireValue(batch.provider === 'supermemory' && batch.space === space && Array.isArray(batch.artifacts), 'Wrong memory target/bundle');
      // Validate the whole successful prepared bundle before any remote call.
      for (const artifact of batch.artifacts) requireValue(artifact && typeof artifact.content === 'string' &&
        artifact.content.startsWith('---\n') && typeof artifact.account_key === 'string' && typeof artifact.version_id === 'string',
        'Malformed prepared artifact');
      if (!batch.artifacts.length) return {provider: 'supermemory', results: []};
      await checkSpace();
      for (const name of names) requireValue(typeof tools[name] === 'function', 'Required memory tool unavailable');
      const until = await deadline();
      const results = [];
      for (const artifact of batch.artifacts) {
        const account_key = artifact.account_key;
        let receipt = await runtime('transfer', {action: 'status', account_key});
        if (receipt.verification.status === 'verified') {
          results.push({account_key, status: 'verified'}); continue;
        }
        if (Date.now() >= until) { results.push({account_key, status: 'unverified'}); continue; }
        try {
          if (!receipt.attempted) {
            receipt = await runtime('transfer', {action: 'begin', account_key});
            if (receipt.may_save) {
              const saved = await provider('add_memory', {action: 'save', containerTag: space, content: artifact.content});
              requireValue(saved.success === true && saved.containerTag === space && typeof saved.id === 'string' && saved.id.length > 0,
                'Save result is uncertain; do not retry');
              receipt = await runtime('transfer', {action: 'ack', account_key, document_id: saved.id});
            }
          }
          requireValue(receipt.document_id, 'Prior save is uncertain; locate its version before any manual retry');
          requireValue(Date.now() < until, 'No time remains for verification');
          const original = (await provider('get_document', {documentId: receipt.document_id})).document;
          requireValue(original && original.id === receipt.document_id, 'Verification returned a different original');
          results.push({account_key, ...await runtime('verify-memory', {account_key, document: original})});
        } catch (_) {
          results.push({account_key, status: 'unverified', notice: 'Storage attempt could not be verified; no automatic resave.'});
        }
      }
      return {provider: 'supermemory', results};
    }
    return {state, retrieveHistory, saveMemory,
      history: account => runtime('history', undefined, ['--account', account]),
      window: request => runtime('window', request),
      capture: observation => runtime('capture-window', observation),
      finalize: draft => runtime('finalize', draft),
      clear: () => { for (const key of Object.keys(state)) delete state[key]; }};
  }
  const api = {create, discover, decoded};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  return api;
})()
