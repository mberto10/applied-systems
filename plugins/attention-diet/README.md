# Attention Diet

**A short briefing from the sources you choose, in a view of your own.**

Attention Diet gathers what you want to follow from several services into one **attention contract**: an editable file that says which sources to check, which topics and people matter to you, what to leave out, how much to inspect and how long the briefing should be. When you ask, the agent checks those sources against the contract and returns a finite selection with reasons and links. The check ends, and the briefing can be empty when nothing qualifies. Briefing memory keeps item versions you have already been shown out of the next one.

You choose how to read the result: in the conversation, as a local HTML list or card grid, or in a view you ask the agent to build. Changing the view never changes what was selected. The contract changes only when you ask for it; clicks never change it.

## What you can ask for

- The newsletters and saved-search alerts in your inbox (marketplaces, job boards, flat hunting) in one briefing, without working through the inbox. The [inbox example](examples/inbox-contract.json) is a starting point.
- New releases of the GitHub projects you rely on.
- Posts from a handful of accounts on an open network such as Bluesky, without the home feed or recommendations.

These are configurable uses, not bundled service integrations. Each source needs an authenticated connector or a supported browser, and a procedure that matches its actual interface. Collection can be incomplete; the briefing says what was checked and where it stopped.

**Check a service's terms before adding it as a browser source.** Most platforms built around a feed prohibit automated access in their user agreements. Connectors, which use a service's official access, and the alerts a service sends by email are the routes most services permit. You choose and are responsible for the sources in your contract.

## What you receive

This excerpt comes from the bundled fictional example. Its source link is a placeholder, not a live recommendation.

> **Attention overview**
>
> One relevant item from the configured source.
>
> **A practical method:** A fictional discussion describes a repeatable method and its limitations. It addresses a topic specified in the contract. [Source](https://example.org/items/1)
>
> *1 selected item · 1 of 1 source area visited.* Example-source: 30 items checked; inspection limit reached.
>
> *To change what reaches you, ask Attention Diet to tune your contract, for example: “fewer posts like this”.*

Use Markdown in the conversation, a local HTML list or a card grid. A check can return no selected items. See [how to preview the example](docs/commands.md#development) without signing into a source.

## Install

**Claude Code** (desktop app for the built-in Browser pane):

```text
/plugin marketplace add mberto10/applied-systems
/plugin install attention-diet@applied-systems
```

**Codex** (app, for the in-app browser):

```sh
codex plugin marketplace add mberto10/applied-systems
codex plugin add attention-diet@applied-systems
```

Browser sources need the Claude Code desktop app (Browser pane) or the Codex app (in-app browser). In a terminal-only session, choose the agent-browser CLI or a connector during setup.

Then prepare Python once; see [runtime setup](#runtime-setup). The [installation guide](docs/installation.md) covers browser requirements per host and common problems. Start a new session after installing so the skills load.

## First check

Ask the agent, one request at a time:

```text
Set up Attention Diet: a two-minute briefing from the sources I choose.
Check my sources once.
From now on, show me fewer promotional posts.
```

`setup` asks only for missing choices and creates your contract at `~/.config/attention-diet/contracts/<id>/attention_contract.json`, outside the plugin so updates preserve it. Setup never collects source content. Its [template](templates/attention-contract.json) supplies defaults. Two filled-in examples show both kinds of source: [the inbox example](examples/inbox-contract.json) reads newsletters and alerts through a mail connector, and [the sample contract](examples/sample-contract.json) reads a public community page in a browser. In the inbox example, `tool_namespace` and `expected_account` are placeholders: setup fills in the exact connector it finds in your session and your mailbox address.

For a check, sign in yourself in the selected isolated browser if needed, or use the configured connected account. The agent checks the permitted areas and returns one overview. `tune` applies a precisely authorized lasting correction, presents a focused diff when you ask for a proposal, and shows what your contract contains. Clicking or ignoring an item never changes your interests.

## How the parts fit together

| Part | Role |
|---|---|
| [Attention contract](docs/contract-guide.md) | Yours. Sources, relevance, exclusions, limits, memory and presentation |
| [Source access](integrations/README.md) | An isolated browser or a connected tool, chosen per source. Procedures the agent follows, not bundled drivers |
| Runtime | Keeps time, counts what was inspected, compares it with earlier briefings, validates, renders and saves |
| [Briefing memory](integrations/memory/README.md) | Which item versions were already shown. Local files or Supermemory |
| [Interfaces](docs/contract-guide.md#output) | One selection as Markdown in the conversation, a dense HTML list, an HTML card grid, or a view of your own |

The agent reads sources and judges relevance. The Python helpers do what a model does unreliably: measure time, count distinct items, fingerprint and compare versions, enforce the contract's structure and escape source text. They do not launch browsers, supply connectors, intercept tool calls or confirm that an observation is true. Sources need no service-specific code: a new source is a contract edit. The only service-specific rule normalises X post links, so one post is counted once. See the [architecture](docs/architecture.md).

## Requirements

- An agent host that can run the local Python helpers and the selected integrations.
- For browser sources, one supported [browser integration](integrations/browsers/README.md): Codex's in-app browser, the Claude Browser pane, or the local agent-browser CLI. Each is a dedicated environment with its own sign-in; your everyday browser session is never used.
- For connector sources, authenticated tools with verifiable identity, scoped retrieval and known read-state behaviour. The plugin bundles no connectors and manages no credentials.
- Python 3.10 or later with `requirements.txt`.
- A writable local memory directory, or a Supermemory connector that can list, retrieve and save original documents.

| Setting | Choices |
|---|---|
| Per-source `access.provider` (`type: browser`) | `codex_in_app`, `claude_browser`, `agent_browser`, `host_default` |
| Per-source `access.tool_namespace` (`type: connector`) | An exact available tool family, discovered during setup and never guessed |
| `memory_context.provider` | `local` (default) or `supermemory` |

`host_default` maps Codex to its in-app browser and Claude Code to the Claude Browser pane. A source never switches routes by itself: a missing integration is reported, not replaced. Local memory is fully handled by the runtime. With Supermemory the agent transfers records through the connector; Codex does this through an [executable adapter](integrations/codex-adapter.md), while other hosts pass the documents through the conversation.

## Runtime setup

Use a dedicated Python environment outside the plugin directory so plugin updates preserve it. If it is missing, the agent sets it up on first use with these steps. To prepare it yourself, run them from the plugin folder (in a clone of this repository, `plugins/attention-diet`):

```sh
python3 -m venv ~/.cache/attention-diet-venv
~/.cache/attention-diet-venv/bin/python -m pip install -r requirements.txt
~/.cache/attention-diet-venv/bin/python scripts/contract.py list
```

Agents reuse this environment and call its Python by absolute path, because shell activation does not carry over between tool calls. If dependencies are missing, the helpers say so before any collection; validation is never skipped. Schemas are bundled and nothing is fetched at run time.

## Sources and coverage

Add a source by describing it in the contract: its access route, surfaces, entry URLs or connector targets, selection rules and [procedure](docs/contract-guide.md#describing-a-source). Its procedure still has to match the interface or connector you actually observed.

Each surface is scanned or sampled. Collection stops only at a supported boundary: exhausted results, a contract ceiling, an access failure, a documented retrieval limit, or evidence that the rest was already covered. Output limits apply separately, so finding enough entries never ends inspection early. Every briefing carries a completeness line and brief coverage notices grouped by service, with consequential read-state and memory warnings, so "nothing new" stays distinguishable from "could not look".

## Memory and several contracts

Memory records the item versions included in finalized briefings, with a short summary and a coverage note. It does not track whether you read or handled them, and it holds no source bodies, browsing logs or rejected candidates. A quiet run writes nothing. Each run compares candidates with every saved version. Known public posts with changed captures are withheld when a substantive edit cannot be established; genuine edits may therefore be omitted. Different posts about the same story still need editorial comparison. Missing history yields a continuity notice, never a claim that everything is new.

History is scoped by contract and service account. You can keep several contracts, such as work and personal, and select one by ID or set a default. `expected_account` pins a source to one sign-in; the agent checks it before reading anything private. An optional surprise slot allows a few labelled items outside your interests, within sources and limits the contract already grants. It is off by default.

## Interaction boundaries

Runs observe and navigate: no replies, invitation decisions, reactions, follows or settings changes. Viewing a page can still have effects on the service's side, such as marking an automatically selected item as read; the contract's read-state procedure governs inspection, and uncertain effects are disclosed. The validator rejects a contract that permits outbound actions. Compliance during a run depends on the agent following its instructions and on the host's own controls.

Source content is processed by the agent's model provider. With Supermemory, included-item summaries and identifying metadata are stored in the configured space. Each invocation produces one overview in the current conversation, as Markdown or a link to a local HTML file. Nothing is scheduled, hosted or delivered elsewhere. See [data handling](docs/data-handling.md) for local records, temporary run files, browser profiles and external providers.

## Collecting in parallel

Sources are independent, so a host that can start subagents may read two at once. Set `execution.parallelism` to `{"mode": "when_independent", "max_workers": 2}`. The agent then starts the run with `--parallel` and gives each source service to one collector. Collectors have no handoff format: they capture into the same run with the same commands, so whatever a collector observed is recorded even if it is interrupted, and the main agent selects, finalizes and saves once. Source clocks run side by side under the one overall time limit, so service allowances may overlap.

This saves time only where the host really runs the collectors and their browser tabs concurrently. Where it does not, the result is the same briefing in the usual time. Without subagents, or with a single source, collection is sequential.

## More

- [Contract guide](docs/contract-guide.md): every field, describing a source, writing selection rules, your own view.
- [Architecture](docs/architecture.md) and [command-line helpers](docs/commands.md).
- [Data handling](docs/data-handling.md): what is stored where, and what reaches which provider.
- [Evals](evals/README.md): behaviour tests with `claude plugin eval`.
- [Changelog](CHANGELOG.md).

Written alongside the [Applied Attention](https://appliedattention.substack.com/) article on Attention Diet. Issues and questions: [github.com/mberto10/applied-systems/issues](https://github.com/mberto10/applied-systems/issues).

## Licence

[MIT](LICENSE).
