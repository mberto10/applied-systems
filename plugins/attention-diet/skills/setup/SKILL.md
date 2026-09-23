---
name: setup
description: Create and install a personal attention contract from the user's sources, interests and limits. Use for a first or additional diet; reuse existing answers and defaults.
---

# Set up an attention contract

Configure one contract without collecting source content or starting a briefing. Reuse the user's answers and established source procedures. Tool documentation and non-content connection metadata may be inspected.

`SCRIPTS` is [../../scripts](../../scripts), relative to this installed skill. `PYTHON` is the absolute path to `~/.cache/attention-diet-venv/bin/python`. Try the helper directly; read [runtime setup](../../README.md#runtime-setup) only if the environment or dependencies are missing.

## Establish what is missing

1. Run `PYTHON SCRIPTS/contract.py list`. Its purpose/source summaries identify existing diets without extra file reads. If an existing contract covers this request, use [tune](../tune/SKILL.md); create a separate diet only when requested.
2. Ask only for unresolved sources/surfaces, interests/exclusions, and reading or collection limits that matter to this request. Reuse prior answers. Group at most three questions; never ask for JSON, technical IDs or a fixed number of interests.
3. Use the [template](../../templates/attention-contract.json) defaults unless the user specifies otherwise: local memory, conversation output, a two-minute read, a ten-minute check, thirty inspected items per surface, five selected per thread, sequential collection and no surprise slot. Summarize defaults briefly; do not present them as confirmed preferences or turn each into a question. Split service allowances within the overall ceiling. Preserve an explicit browser choice; otherwise `host_default` resolves to Codex's in-app browser or the Claude Browser pane. Other hosts need a supported explicit provider.
4. Before keeping a browser route, check that its tools exist in this session: `mcp__Claude_Browser__*` for the Claude Browser pane, the in-app browser tools for Codex, the `agent-browser` command for `agent_browser`. A terminal-only Claude Code session has no Browser pane. If the resolved browser is missing, say so and ask whether to use `agent_browser`, a connector, or keep the choice for a host that has it. Never substitute a route silently.

## Configure the sources

Read only [describing a source](../../docs/contract-guide.md#describing-a-source) when adding sources. Replace the placeholder source with confirmed services, surfaces, actual entry URLs or connector targets, selection rules and source procedures. Update dependent service budgets and output caps together. Mark public material explicitly; private communication remains the default. Record `expected_account` when the user specifies a sign-in.

Use source documentation or previously established observations. Put live checks for account identity, navigation and read-state effects in the procedure as conditions to verify before dependent reads on the first run; do not claim setup verified a live interface. Unknown entry URLs, unavailable tool capabilities or an unspecified retrieval scope are gaps to resolve, never guesses.

Load only the requested branch: [connector configuration](../../integrations/connectors.md) for connectors, [Supermemory setup](../../integrations/memory/supermemory-setup.md) for that memory provider, or [specialized changes](../tune/references/specialized-changes.md) for other output, parallelism or surprise settings. Local memory needs no provider guide. Keep isolation, read-only access and no fallback; never retain credentials or placeholder instructions.

## Prepare and install

Send only changes from the template to `PYTHON SCRIPTS/contract.py prepare --new --id ID --input -`. The helper sets revision 1 and the matching local-memory directory. Input uses JSON Patch (`add`, `replace`, `remove`):

```json
{"reason":"The user's requested diet","patch":[
  {"op":"replace","path":"/intent/purpose","value":"The confirmed purpose"}
]}
```

This is the input shape, not a complete setup: also replace the template's placeholder interests and source configuration. Use array indices from the template; `/-` appends. Preparation validates the complete result and stores one private proposal. Correct errors in the patch; do not weaken validation or manually copy files and increment revisions.

Inspect the returned changes against the request. If creating this contract is already authorized and no substantive choice is unresolved, run `PYTHON SCRIPTS/contract.py apply --proposal TOKEN`, adding `--default` for the first diet or when requested. For a proposal-only request, show the choices and await approval before applying. `apply` rechecks validity, refuses an existing contract that appeared meanwhile, writes the changelog and removes the proposal. `discard --proposal TOKEN` removes a declined proposal.

Return the installed path and a short description of the configured scope and defaults. Mention any unresolved limitation. Start a briefing only if the user asked for it.
