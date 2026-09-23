# Specialized contract changes

Read only the relevant section when the requested change needs it. Ordinary relevance or length edits need no additional guide.

## Output

For a bundled view, change `composition.interface`, `format`, `template` and `template_path_base` together:

| Interface | Format | Template (plugin_root) |
|---|---|---|
| `agent_summary` | `markdown` | `./interfaces/agent-summary/template.md` |
| `briefing_html` | `html` | `./interfaces/html/template.html` |
| `discovery_html` | `html` | `./interfaces/html/template.html` |

For a custom view, follow [your own view](../../../docs/contract-guide.md#your-own-view). Write a new file beside the contract, preserving the existing view; use `template_path_base: contract_dir`. Build from `$data`, retain `$notices`, place source values with `textContent`, and include the required offline Content-Security-Policy. Preview with fictional content before applying:

```text
PYTHON SCRIPTS/briefing.py render --contract PLUGIN/templates/attention-contract.json --input PLUGIN/examples/selection.json --interface briefing_html --template NEW_TEMPLATE --out PREVIEW.html
```

`PLUGIN` is the plugin root. Show the preview; fix rendering errors before preparing the contract patch. A custom view changes presentation, not selection. If declined, remove only the new files created for this proposal.

## Parallel collection

Only when requested, add `execution.parallelism: {"mode":"when_independent","max_workers":2}`. Remove it for sequential collection. Service allowances must fit inside the overall time limit in sequential mode; do not raise that limit silently. Parallelism requires separate source services and a capable host and promises no speedup.

## Surprise slot

Use `serendipity.enabled` and `max_items` (0–3). If absent, start from the template block; when enabling, select explicit already-authorized thread/surface pairs and keep the configured sample share. No extra access is granted. A surprise candidate must pass every test and stay outside listed interests and exclusions. Enable only on request.

## Memory

Read [memory providers](../../../integrations/memory/README.md) only when changing provider. For Supermemory, use its [setup guide](../../../integrations/memory/supermemory-setup.md) to resolve the chosen accessible space key and required operations; remove local `directory`. For local memory, replace `space` with the chosen directory. Preserve contract/account identities and warn about the actual continuity change. No history is copied without an explicit migration request.
