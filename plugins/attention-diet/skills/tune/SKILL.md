---
name: tune
description: Apply an explicitly requested lasting change to an attention contract, or prepare a precise proposal when the user wants options. Use for changes to sources, relevance, limits, output or integrations, and to show which diets exist or what a contract currently contains.
---

# Tune an attention contract

Change the user's contract, never briefing memory. Do not collect source content or run a briefing. A temporary instruction such as “skip that today” needs no revision; if lasting intent is unclear, ask once. Use the user's stated correction without inferring preferences from clicks or omissions.

`SCRIPTS` is [../../scripts](../../scripts), relative to this installed skill. `PYTHON` is the absolute path to `~/.cache/attention-diet-venv/bin/python`. Try the helper directly; read [runtime setup](../../README.md#runtime-setup) only if the environment or dependencies are missing.

## Read once and edit narrowly

`PYTHON SCRIPTS/contract.py resolve [--id ID]` returns the validated contract and its digest. Use that response; do not reread its file or load general configuration guides for a small preference edit. To answer which diets exist, use `contract.py list`. To show what a contract contains, summarize the resolved contract in plain language and change nothing.

- Relevance, exclusions or named accounts: edit the existing thread rule/list in the user's words. An exclusion meant for every source goes in `intent.excluded`, which selection applies everywhere. An account list makes an item eligible, not automatically included.
- Interests: edit `intent.interests`. Explicit “more like that” feedback on a surprise item can become an interest; it then leaves the surprise slot.
- Briefing length: edit `composition` limits. Collection time: edit `run_limits`. Source depth: `run_limits.items_per_surface` caps every surface and a surface's `collection.<surface>.max_items` can only lower it; to inspect more, raise the cap and any lower surface value together. Do not confuse inspection ceilings with output caps.
- Different sign-in: edit the source's `expected_account`; preserve its established account-key convention.
- Source/access changes: read only [describing a source](../../docs/contract-guide.md#describing-a-source) and the selected integration guide. Preserve existing service/account/item identity conventions.
- Output, parallel collection, surprise settings or memory provider changes: load [specialized changes](references/specialized-changes.md) only for that request.

Prefer replacing a rule over adding an overlapping one. An explicit replacement supersedes the old rule; ask only when the requested scope or precedence remains ambiguous. Account actions, non-isolated access, scheduling and cross-contract suppression need plugin work, not a contract workaround.

## Prepare and apply

Send the smallest JSON Patch to `PYTHON SCRIPTS/contract.py prepare --id ID --expected-digest DIGEST --input -`:

```json
{"reason":"Show at most three items from this source in future.","patch":[
  {"op":"replace","path":"/composition/max_items_by_thread/source-1","value":3}
]}
```

Use the actual keys and array indices from the resolved contract. Operations are `add`, `replace` and `remove`; `/-` appends. The helper handles revision +1, validation and the private proposal file, returning a token and changes to individual fields. Do not rewrite the full contract, manufacture a revision or copy before/after values manually.

Inspect the changes and their effect. A precise lasting edit already authorized by the user, including earlier in this conversation, can be applied without another confirmation: `PYTHON SCRIPTS/contract.py apply --proposal TOKEN`. If the user asked for a proposal or an unresolved choice remains, describe the before/after and effect on the next briefing in plain language, then wait for that decision. Show JSON paths or patches only when requested. `discard --proposal TOKEN` removes a declined proposal without retaining the correction elsewhere.

Application rejects a changed base, archives the earlier revision, installs atomically, writes a dated changelog entry and removes the proposal. A stale-base error requires resolving and preparing again; do not overwrite intervening edits. Finish with a brief description of the applied change and contract link, without an operational transcript.

Keep contract identity and memory intact during ordinary tuning. Moving memory changes continuity and copies no history; migration requires an explicit request. To undo, prepare the earlier values as a new revision, never decrement. A rename is a separate operation that must preserve `previous_ids`.
