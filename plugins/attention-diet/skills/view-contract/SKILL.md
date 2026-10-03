---
name: view-contract
description: Show an attention contract as one readable local page, the user's own algorithm in plain text. Use when the user asks to see, review or share what their diet checks, leaves out, remembers and when it stops.
---

# View an attention contract

Render the contract; change nothing. Do not collect source content, read briefing memory or run a briefing. Changes go through [tune](../tune/SKILL.md).

`SCRIPTS` is [../../scripts](../../scripts), relative to this installed skill. `PYTHON` is the absolute path to `~/.cache/attention-diet-venv/bin/python`. Try the helper directly; read [runtime setup](../../README.md#runtime-setup) only if the environment or dependencies are missing.

1. If the user names no diet and several exist, run `PYTHON SCRIPTS/contract.py list` and ask which one.
2. Run `PYTHON SCRIPTS/contract_view.py render [--id ID] --out ABSOLUTE.html`. Default to `~/.local/share/attention-diet/views/<id>-contract.html`, expanded to an absolute path. The helper validates the contract, reads the changelog beside it and writes one offline page: what counts, what is left out, where it looks, when it stops, surprises, what it remembers, what it never does and the revision history, with the exact contract folded at the end.
3. Link the page and add one sentence on how to change it, for example: "Ask me to tune it, such as 'leave out event announcements'." Do not restate the whole contract in the conversation unless asked.

The page shows the user's own configuration, including sign-in names and source addresses. Before the user shares it publicly, point to `contract.py export`, which writes a copy without account names or personal paths, and render that copy with `--contract`.
