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

`/next mode linear` switches the mode and keeps it until you switch again. The band's header shows the current mode.

## How it works

1. **When a turn ends**, unless it ended with a question to you or was interrupted, the mod reads the sources the mode names:
   - **GitHub:** open issues and pull requests in the current repository, through the `gh` CLI and your existing login.
   - **Linear:** your open issues, through the Linear MCP server you already have connected. No API key is stored in the plugin.

   The list is cached for five minutes.
2. **A ranker picks the steps.** By default a small model (`haiku`) gets the last exchange and the open items, and nothing else.
3. **The steps appear above the prompt.** Type `1`, `2` or `3` and press Enter to send one as written, or click one to put it in the prompt box and edit it first. `0` dismisses them; any other prompt clears them.

| Command | What it does |
|---|---|
| `/next` | Says how many steps are showing |
| `/next refresh` | Reads the sources again and picks new steps |
| `/next mode <name>` | Switches the mode |
| `/next sources` | Shows how many open items each source returned, or why it returned none |

## Context

The suggestions never enter the conversation. Claude's context only grows by what you send: a step you pick is one short prompt, and `/next` answers with one line.

The ranker runs as a separate request with its own budget:

- **`light`** (default): the last prompt and answer, each shortened to 750 characters, plus at most 12 open items per source with titles cut to 90 characters. Roughly 1,000 to 2,000 tokens, whatever the length of the session.
- **`fork`**: the session's own model over the whole cached transcript. It knows the session better, but each request is as large as the conversation. When it does not answer (for one, near the context limit), the light ranker takes over.

## Requirements

- Claude Code 2.1.287 or later, which added mods. It works in the terminal and in the desktop app's Code tab.
- For GitHub: the [`gh` CLI](https://cli.github.com/), signed in.
- For Linear: a connected Linear MCP server, such as the Linear connector on claude.ai, and permission for its `list_issues` tool. The mod reads Linear in the background, where nobody can be asked, so allow the tool once, for example in `/permissions` or under `permissions.allow` in your settings: `mcp__claude_ai_Linear__list_issues`. Without it, the mod shows a reminder once and `/next sources` names the refusal.

## Install

```text
/plugin marketplace add mberto10/applied-systems
/plugin install next-up@applied-systems
```

## Settings

| Setting | Default | What it does |
|---|---|---|
| Mode | `mixed` | `mixed`, `linear`, `github` or `conversation`; `/next mode` overrides it. |
| GitHub items | `issues-and-prs` | Open issues and pull requests, or `issues` only. |
| Linear server | empty | The Linear MCP server's name as `/mcp` lists it. Empty tries `claude.ai Linear`, `Linear` and `linear`. |
| Linear project | empty | Only issues in this project. Empty: all your open issues. |
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
