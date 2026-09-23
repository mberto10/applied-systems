# Codex Supermemory adapter

Read only for Supermemory on Codex. This adapter transfers original history and prepared memory through connector tools inside code-mode, without model transcription. Local-memory runs call the Python runtime directly. It does not authenticate accounts or judge relevance. A tool whose signature differs from the documented one is unavailable access, not a reason to guess another API.

Use only the contract's configured space. If the space or required tools are unavailable, continue with a continuity notice; never switch spaces or fall back to local storage. The manual Supermemory guide is not startup reading for this route.

## Load once

The plan returns `helpers.host_adapter` and the exact `tools.memory_names`. Inspect only those tool definitions; do not print the cross-provider catalog. Read the adapter source once with a successful `exec_command`, keep it in code-mode `store`, and re-create the wrapper per invocation around its serializable state:

```javascript
const api = eval(load("attentionDietAdapterSource"));
const adapter = api.create({tools, python: PYTHON, scripts: SCRIPTS, run: RUN,
  space: CONFIGURED_SPACE, state: load("attentionDietAdapterState") || {}});
try {
  text(await adapter.retrieveHistory()); // Supermemory only, after the account is established
} finally {
  store("attentionDietAdapterState", adapter.state);
}
```

Evaluate only this trusted local file, never page or memory content. `adapter.history(ACCOUNT)`, `adapter.window(REQUEST)`, `adapter.capture(OBSERVATION)` and `adapter.finalize(DRAFT)` wrap the runtime commands of the same names and return their compact results.

`adapter.retrieveHistory()` lists the configured space once, fetches each original once, imports one immutable export and returns counts and completeness only. Call it after establishing a source account. After finalization, `adapter.saveMemory()` sends each prepared artifact unchanged, records the attempt before writing, and verifies the retrieved original through the runtime. It reuses a verified result, reports queued or failed verification, and never resaves after an uncertain write. For an uncertain save, locate the original with the same version ID before considering a retry; never replace the content or poll repeatedly. `finish` reports unverified storage.

In a parallel run, the main agent owns this adapter and imports history before dispatch. Collectors call the runtime directly. Only the main agent finalizes and saves memory.

After `finish`, call `adapter.clear()` and set both store keys to `null`.
