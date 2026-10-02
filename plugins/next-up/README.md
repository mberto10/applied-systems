# Next up

A Claude Code mod that suggests what to do next. When a turn ends with an answer, it proposes up to three next prompts above the prompt box: a continuation of the current work, or an open GitHub issue, pull request or Linear issue that fits it.

```text
Next up (mixed) · type a number and Enter to send it, or click one to edit it first
1: Add tests for the anchor fix               #12
2: Review the onboarding copy                 ENG-42
3: Split the release notes by component       continue
dismiss
```

## Modes

| Mode | Steps come from |
|---|---|
| `mixed` (default) | The current work, open GitHub issues and pull requests, and your open Linear issues |
| `linear` | Your open Linear issues only |
| `github` | The repository's open issues and pull requests only |
| `conversation` | The current work only; no source is read |

`/next mode linear` switches the mode for the current project. The band's header shows the current mode.

## Criteria per project

Each project keeps its own criteria in `.claude/next-up.json` at the repository's top level. Set them with commands, or edit the file:

```text
/next linear project Website, Docs     only these Linear projects
/next linear states started,unstarted  only these state types (default: started, unstarted, backlog, triage)
/next linear team Engineering
/next linear label bug
/next linear assignee any              anyone's issues, not only yours (default: me)
/next linear query onboarding          title or description contains this
/next github label good first issue
/next github assignee @me
/next github items issues              issues only, no pull requests
/next linear project off               clears a setting
```

```json
{
  "mode": "linear",
  "linear": { "projects": ["Website"], "states": ["started", "unstarted"] },
  "github": { "assignee": "@me" }
}
```

Whether to commit the file is up to you: committed, the whole team shares the criteria.

**Order.** Linear issues reach the ranker most important first: started before unstarted before backlog, then urgent, high, medium, low, no priority, then the most recently updated. GitHub lists pull requests first, then the newest issues. In `mixed` mode the ranker returns one step of each kind (a continuation, a GitHub item, a Linear item); in `linear` and `github` mode up to three of that source's items, preferring those related to the current work. Each step shows a short reason after its id.

## How it works

1. **When a turn ends**, unless it ended with a question to you or was interrupted, the mod reads the sources the mode names:
   - **GitHub:** open issues and pull requests in the current repository, through the `gh` CLI and your existing login.
   - **Linear:** your open issues, through the Linear MCP server you already have connected. No API key is stored in the plugin.

   The list is cached for five minutes. A source that does not answer within 20 seconds is skipped for that turn.
2. **A ranker picks the steps.** By default a small model (`haiku`) gets the last exchange and the open items, and nothing else.
3. **The steps appear above the prompt.** Type `1`, `2` or `3` and press Enter to send one as written, or click one to put it in the prompt box and edit it first. `0` dismisses them; any other prompt clears them.

| Command | What it does |
|---|---|
| `/next` | Says how many steps are showing |
| `/next refresh` | Reads the sources again and picks new steps |
| `/next mode <name>` | Switches the mode for this project |
| `/next linear <setting> <value>` / `/next github <setting> <value>` | Sets a criterion, see [Criteria per project](#criteria-per-project) |
| `/next config` | Shows the criteria in force |
| `/next sources` | Shows how many open items each source returned, or why it returned none |

## Context

The suggestions never enter the conversation. Claude's context only grows by what you send: a step you pick is one short prompt, and `/next` answers with one line.

The ranker runs as a separate request with its own budget:

- **`light`** (default): the last prompt and answer, each shortened to 750 characters, plus at most 12 open items per source with titles cut to 90 characters. Roughly 1,000 to 2,000 tokens, whatever the length of the session.
- **`fork`**: the session's own model over the whole cached transcript. It knows the session better, but each request is as large as the conversation. When it does not answer (for one, near the context limit), the light ranker takes over.

## Requirements

- Claude Code 2.1.287 or later, which added mods. It works in the terminal and in the desktop app's Code tab.
- For GitHub: the [`gh` CLI](https://cli.github.com/), signed in.
- For Linear: a connected Linear MCP server, such as the Linear connector on claude.ai, and permission for its `list_issues` tool. The mod finds the server by its tool, whatever the connector is called. It reads Linear in the background, where nobody can be asked, so allow the tool once in `/permissions` or under `permissions.allow` in your settings. The name depends on the app: `mcp__claude_ai_Linear__list_issues` in the terminal, `mcp__<connector id>__list_issues` in the desktop app (`/next sources` names the server it found). Without it, the mod shows a reminder once and `/next sources` names the refusal.

## Install

```text
/plugin marketplace add mberto10/applied-systems
/plugin install next-up@applied-systems
```

## Settings

| Setting | Default | What it does |
|---|---|---|
| Mode | `mixed` | `mixed`, `linear`, `github` or `conversation`; a project's `.claude/next-up.json` overrides it. |
| GitHub items | `issues-and-prs` | Open issues and pull requests, or `issues` only. |
| Linear server | empty | The Linear MCP server's name as `/mcp` lists it. Empty: the server whose `list_issues` tool is Linear's, found in the tool list, then `claude.ai Linear`, `Linear` and `linear`. |
| Linear project | empty | The default Linear project when a project's file names none. Empty: all your open issues. |
| Ranker | `light` | `light` or `fork`, see [Context](#context). |
| Light ranker model | `haiku` | An alias or a full model id. |
| Items per source | `12` | At most this many open items per source reach the ranker (up to 50). |

## What it sends where

Issue titles, states and identifiers go to the model that picks the steps, the same way they would if you asked Claude to read your issues. The mod writes nothing to GitHub or Linear. A step only takes effect when you send it, and then Claude works under your normal permissions.

## Limits

- Each finished turn costs one extra model request: a small one with the light ranker.
- While steps are showing, a prompt that is only `1`, `2` or `3` sends that step instead.
- Mods are new and their API may change between Claude Code releases.

## Development

`claude plugin validate plugins/next-up` checks the manifest and hooks module; `claude plugin test plugins/next-up` runs the tests. To work on it live, run `claude --plugin-dir plugins/next-up`; saving a file reloads it.

## License

[MIT](LICENSE).
