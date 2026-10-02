# Next up

A Claude Code mod that suggests what to do next. When a turn ends with an answer, it proposes up to three next prompts above the prompt box: a continuation of the current work, or an open GitHub issue, pull request or Linear issue that fits it.

```text
Next up · type a number and Enter to send it, or click one to edit it first
1: Add tests for the anchor fix               #12
2: Review the onboarding copy                 ENG-42
3: Split the release notes by component       continue
dismiss
```

## How it works

1. **When a turn ends**, unless it ended with a question to you or was interrupted, the mod reads your open work:
   - **GitHub:** open issues and pull requests in the current repository, through the `gh` CLI and your existing login.
   - **Linear:** your open issues, through the Linear MCP server you already have connected. No API key is stored in the plugin.

   The list is cached for five minutes.
2. **One question over the session's own transcript** picks the steps (`$.model.fork`). It uses the session's model, and most of the request is served from the prompt cache.
3. **The steps appear above the prompt.** Type `1`, `2` or `3` and press Enter to send one as written, or click one to put it in the prompt box and edit it first. `0` dismisses them; any other prompt clears them.

`/next` lists the current steps, and `/next refresh` reads GitHub and Linear again.

## Requirements

- Claude Code 2.1.287 or later, which added mods. It works in the terminal and in the desktop app's Code tab.
- For GitHub: the [`gh` CLI](https://cli.github.com/), signed in.
- For Linear: a connected Linear MCP server, such as the Linear connector on claude.ai.

## Install

```text
/plugin marketplace add mberto10/applied-systems
/plugin install next-up@applied-systems
```

## Settings

| Setting | Default | What it does |
|---|---|---|
| GitHub | `issues-and-prs` | Open issues and pull requests, `issues` only, or `off`. |
| Linear | `mine` | Your open Linear issues, or `off`. |
| Linear server | empty | The Linear MCP server's name as `/mcp` lists it. Empty tries `claude.ai Linear`, `Linear` and `linear`. |
| Linear project | empty | Only issues in this project. Empty: all your open issues. |

## What it sends where

Issue titles, states and identifiers go to the model as part of the question that picks the steps, the same way they would if you asked Claude to read your issues. The mod writes nothing to GitHub or Linear. A step only takes effect when you send it, and then Claude works under your normal permissions.

## Limits

- Each finished turn costs one extra model request, mostly cache reads.
- While steps are showing, a prompt that is only `1`, `2` or `3` sends that step instead.
- Mods are new and their API may change between Claude Code releases.

## Development

`claude plugin validate plugins/next-up` checks the manifest and hooks module; `claude plugin test plugins/next-up` runs the tests. To work on it live, run `claude --plugin-dir plugins/next-up`; saving a file reloads it.

## License

[MIT](LICENSE).
