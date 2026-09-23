# Contract guide

A contract is one JSON file you own at `~/.config/attention-diet/contracts/<id>/attention_contract.json`. Create it with the `setup` skill and change it with the `tune` skill. The skills use `contract.py prepare` and `apply` to handle proposals, revisions and the changelog; explicit instructions to apply a precise lasting change need no second confirmation. To edit by hand, copy it, change the copy, raise `revision` by one and run `contract.py install --contract PROPOSED`. Leave the installed file alone until then, so the previous revision can be compared and archived.

The plugin ships one [contract template](../templates/attention-contract.json) with one generic source block. Setup adapts that block and adds further coverage threads as needed. The template treats content as private until you say otherwise. [attention-contract.schema.json](../schemas/attention-contract.schema.json) defines the structure for validation and editor completion; `contract.py validate --contract FILE` adds the checks between fields.

| Block | Question it answers | Notes |
|---|---|---|
| `id`, `revision`, `previous_ids` | Which contract is this, and which history does it continue? | Revisions go up by exactly one. Rename with `previous_ids`. |
| `intent` | What is this diet for, and what is cut entirely? | `interests` are confirmed by you, never inferred. `excluded` applies to every source during selection, on top of each thread's own `exclude`. |
| `coverage_threads[]` | Which service, which surfaces, which rules? | Threads on the same service share its time budget. `surfaces` and `excluded_surfaces` must not overlap. `content` marks public posts or private communication. `expected_account` pins the sign-in. |
| Per-thread `access` | How is this source reached? | An isolated browser provider, or a connector tool namespace. See [integrations](../integrations/README.md). |
| `serendipity` (optional) | May I be shown something outside my interests? | Off unless `enabled`. `max_items` 0 to 3. `sources` are thread/surface pairs already configured. |
| `memory_context` | Where is "already briefed" remembered? | `local` with a `directory`, or `supermemory` with a resolved `space` key. See [briefing memory](../integrations/memory/README.md). |
| `run_limits` | How long may a check run? | The runtime measures the minutes. Service allowances must fit inside `elapsed_minutes`, unless the contract permits parallel collection, where they may overlap. |
| `composition` | What do I get back? | Interface, template, sections, reading target, item ceilings. |
| `execution` | When and how does it run? | Once, when you ask. Scheduling is rejected until it is designed. Optional `parallelism` `{"mode": "when_independent", "max_workers": 2}` lets a host with subagents read one source service per collector at the same time; otherwise, and by default, sources are read one after the other. |

## Preparing changes

`contract.py list` returns compact purpose/source summaries. `resolve [--id ID]` returns the full validated contract and its digest in one response.

`prepare --id ID --expected-digest DIGEST --input -` accepts `{reason, patch}`. `patch` uses the JSON Patch `add`, `replace` and `remove` operations, with JSON Pointer paths; `/-` appends to arrays, `~1` escapes a slash and `~0` escapes a tilde in a key. Supply a value except for remove. Parent paths must exist. The helper owns `id` and `revision` and rejects edits to them. For a new diet, `prepare --new --id ID --input -` starts from the bundled template with revision 1 and a matching local-memory directory, and refuses an existing ID.

Preparation validates without installing, stores a private proposal under the configuration directory and returns its token plus changes to individual fields. The diff aligns source and interest objects by stable ID, so an exclusion edit does not repeat the whole source list. Diff paths describe the displayed before/after documents; the diff is for review, not a patch to replay.

`apply --proposal TOKEN [--default]` checks that the base is unchanged, validates again, archives the previous revision, installs atomically, appends the user's reason and changed paths to the changelog, and removes the proposal. Competing edits cannot overwrite one another. If installation succeeds but bookkeeping fails, retrying the same pending token completes that bookkeeping without incrementing the revision again. `discard --proposal TOKEN` deletes a declined proposal without modifying the contract or recording the correction. The old file-based install command remains available for manual edits.

## Fields you cannot loosen

`account_actions`, `access.fallback`, `composition.delivery`, `execution.mode` and `execution.schedule_enabled` have fixed values. Browser access also fixes `session: isolated` and `external_session_reuse: false`. No access type authorizes changing anything in an account or falling back to another route. Never put tokens, passwords or executable commands in a contract.

## Describing a source

The plugin has no built-in knowledge of any service. Service keys are opaque, and no code dispatches on them. Each thread carries its own `procedure`, written from source documentation or previously established interface observations:

| Field | Describes |
|---|---|
| `navigation` (browser) | How to reach each surface from its HTTPS `entry_urls` entry using visible UI |
| `retrieval` (connector) | How the available read tools express each `targets.<surface>.scope` |
| `account_identity` | How to establish the signed-in identity, and the stable account key to use |
| `read_state` | Which reads acknowledge or change state, and which list or preview views avoid it |
| `item_identity` | The stable ID or canonical link, the unit that counts as one item, and the source text used for fingerprints |
| `pagination` | How to find further results and recognize the end of the configured scope; ordering, indexing and result caps |

A browser thread needs an entry URL per surface and `navigation`. A connector thread needs a `targets` scope per surface and `retrieval`. Neither accepts the other's fields. For a connector, store the exact `tool_namespace` found in the host, and a `connection_id` only when the host exposes a stable, non-secret reference. Do not bind a source to a tool family that also reaches unrelated services, and resolve ambiguous connections before installing. Setup and tune may read documentation and non-content connection metadata, never source content. Reuse documented or previously verified procedures. Describe live checks as conditions in the procedure: before dependent reads on the first run, verify the account, observed navigation and read-state effects, then proceed only if they match. Do not claim an untested interface was verified, invent entry URLs/tool capabilities, or install a source whose retrieval scope cannot be specified. Unknown behavior must block the dependent read, rather than trigger guessed interaction or a route fallback.

`collection` sets each surface to `{"mode": "scan"}` or `{"mode": "sample", "max_items": 20}`; a scan may also set `max_items`. It limits how much is inspected. `run_limits.items_per_surface` is the contract-wide cap for every surface. Set a surface's own `max_items` only to go lower or to size a sample; the lower value always applies, so raising depth means raising the cap. `composition.max_items_by_thread` limits what is delivered, and never ends collection early.

## Writing good selection rules

- Write rules as sentences an item can be checked against: "Routine promotion is not an announcement."
- Put a kind of item you never want in an `exclude` list in your own words. Put a whole surface you never want in `excluded_surfaces`.
- Being on an account list makes someone eligible, not included. Say what earns inclusion.
- Give each ceiling a policy line saying it is not a target.
- Connector scope is not relevance: a query defines what may be retrieved, and the selection rules decide what deserves attention.

## Output

`composition.interface` selects `agent_summary` (Markdown in the conversation), `briefing_html` (a dense list to triage) or `discovery_html` (a card grid for choosing what to read). All three render the same [selected-content record](../schemas/selection.schema.json), so changing the view never collects again, changes what was selected or writes memory. Preview any of them from a saved selection:

```sh
PYTHON scripts/briefing.py render --contract FILE --input SELECTION --interface discovery_html --out PREVIEW.html
```

Every view carries a scope line, such as "5 selected items · 5 of 5 source areas visited", and brief surface descriptions grouped by service. These distinguish intentional samples, inspection/time limits, verified list endings, retrieval stalls, unreadable previews and overruns, alongside consequential read-state and memory warnings. Visited does not mean exhaustive.

### Your own view

Set `template_path_base: contract_dir` and point `composition.template` at a file beside your contract. A template may use these placeholders; `$$` is a literal dollar sign:

| Placeholder | Content |
|---|---|
| `$title`, `$overview`, `$meta` | Escaped text |
| `$content` | The rendered entries, grouped by section |
| `$notices` | Coverage and continuity notices. Required in every template |
| `$layout` | `briefing` or `discovery` (HTML) |
| `$data` | The whole selection as JSON (HTML) |

A plain template needs `$title`, `$overview`, `$content` and `$notices`. A template that uses `$data` draws the entries itself, so it needs only `$title`, `$data` and `$notices`. That is the way to a view shaped around a task: a reading queue, a one-item focus view, a filterable page. Ask the `tune` skill for one; it writes the template, previews it on the fictional example (`briefing.py render --template FILE`) and installs it as a contract revision.

`$data` belongs inside `<script type="application/json" id="attention-data">$data</script>` and holds `title`, `overview`, `created_at`, `meta`, `notices`, `sections[].entries[]` (`title`, `summary`, `why`, `caveats`, `url`, `source`, `surprise`) and `coverage[]`. It is encoded so that no source text can close the element. Two rules keep a scripted view safe. Its values are text from the web, so put them on the page with `textContent` and `setAttribute("href", …)`, never `innerHTML`. And the renderer refuses any HTML template, scripted or not, without a Content-Security-Policy meta tag containing `default-src 'none'`, so the page stays offline and even a template bug cannot send your briefing anywhere. `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'` are the only additions a view needs.

Missing files, unknown placeholders and omitted required placeholders are errors, reported before anything is delivered or saved.
