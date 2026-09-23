# Command-line helpers

The skills call these helpers for you. This reference is for development, diagnostics and hand edits.

```sh
AD_PYTHON="$HOME/.cache/attention-diet-venv/bin/python"

# A run
"$AD_PYTHON" scripts/runtime.py plan --host codex --id CONTRACT_ID
"$AD_PYTHON" scripts/runtime.py start --contract FILE --expected-digest DIGEST [--parallel]
"$AD_PYTHON" scripts/runtime.py history --run RUN --account ACCOUNT
"$AD_PYTHON" scripts/runtime.py window --run RUN --input -          # then capture-window
"$AD_PYTHON" scripts/runtime.py capture --run RUN --input -
"$AD_PYTHON" scripts/runtime.py finalize --run RUN --input -
"$AD_PYTHON" scripts/runtime.py finish --run RUN [--out ABSOLUTE.html]

# Supermemory only
"$AD_PYTHON" scripts/runtime.py import-history --run RUN --input -
"$AD_PYTHON" scripts/runtime.py memory --run RUN
"$AD_PYTHON" scripts/runtime.py verify-memory --run RUN --input -
"$AD_PYTHON" scripts/runtime.py transfer --run RUN --input -       # Codex adapter: upload receipts (begin | ack | status)

# Contracts: resolve once, prepare a small edit, then apply the proposal
"$AD_PYTHON" scripts/contract.py prepare --new --id NEW_ID --input -
"$AD_PYTHON" scripts/contract.py prepare --id ID --expected-digest DIGEST --input -
"$AD_PYTHON" scripts/contract.py apply --proposal TOKEN [--default]
"$AD_PYTHON" scripts/contract.py discard --proposal TOKEN
"$AD_PYTHON" scripts/contract.py list | resolve | validate --contract FILE
"$AD_PYTHON" scripts/contract.py diff --old CURRENT --contract PROPOSED
"$AD_PYTHON" scripts/contract.py install --contract FILE [--default]
"$AD_PYTHON" scripts/contract.py export --id ID --out FILE
"$AD_PYTHON" scripts/contract.py remove --id ID
```

Installation keeps replaced revisions and, for a hand-edited file, adds a changelog line. Removal archives the contract and leaves its memory. `export` writes a template-shaped copy without account lists, identities or personal paths, for sharing. `run_budget.py`, `surface_coverage.py`, `briefing.py` and `briefing_memory.py` expose the runtime's parts for diagnostics only; the skills call `runtime.py` and `contract.py`, and `briefing.py render` for view previews.

## Development

```sh
~/.cache/attention-diet-venv/bin/python -m unittest discover -s tests
node --test tests/test_codex_adapter.cjs
~/.cache/attention-diet-venv/bin/python scripts/briefing.py render --contract templates/attention-contract.json --input examples/selection.json --interface discovery_html --out output/discovery.html
~/.cache/attention-diet-venv/bin/python scripts/briefing.py render --contract templates/attention-contract.json --input examples/selection.json --interface briefing_html --template interfaces/html/example-view.html --out output/focus.html
```

The example selection is fictional. Rendering never collects sources or writes memory. [example-view.html](../interfaces/html/example-view.html) shows a view built from `$data`; see [your own view](contract-guide.md#your-own-view). Behaviour tests for Claude Code live in [evals](../evals/README.md).
