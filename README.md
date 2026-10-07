# Applied Systems

Working systems from [Applied Attention](https://appliedattention.substack.com/), packaged so you can install, inspect and adapt them. The articles explain the reasoning; this repository holds the code.

It is also a plugin marketplace for **Claude Code** and **Codex**.

## Plugins

| Plugin | What it does | Version |
|---|---|---|
| [Attention Diet](plugins/attention-diet/) | One attention contract for the sources you choose, such as the newsletters and alerts in your inbox, and one short briefing that ends. Read-only by design, with explicit limits and memory of what you already saw. | 0.6.0 |
| [Next up](plugins/next-up/) | A Claude Code mod: when a turn ends, up to three next prompts above the prompt box, from the conversation, GitHub or Linear, or all of them. Claude Code only. | 0.1.1 |
| [Linear tree](plugins/linear-tree/) | A Claude Code mod: a Linear project as a tree and a flowchart in a side pane, with progress, search, shortcuts and markers on the issues agents are working on. Claude Code only. | 0.1.0 |
| [Next up for ChatGPT](plugins/next-up-chatgpt/) | Shared work plans with acceptance criteria and agent progress tools, plus Markdown/Linear/GitHub source snapshots. Requires a private MCP server. | 0.4.1 |

## Install

**Claude Code**

```text
/plugin marketplace add mberto10/applied-systems
/plugin install attention-diet@applied-systems
/plugin install next-up@applied-systems
/plugin install linear-tree@applied-systems
```

**Codex**

```sh
codex plugin marketplace add mberto10/applied-systems
codex plugin add attention-diet@applied-systems
codex plugin add next-up-chatgpt@applied-systems
```

Next up for ChatGPT is a separate plugin from the Claude Code mod. Its [setup and update guide](plugins/next-up-chatgpt/README.md#update-an-existing-installation) covers the required local MCP server and refreshing the connected tools. Native panel placement in Codex remains to be verified. The Next up and Linear tree mods require Claude Code 2.1.287 or later.

Start a new session afterwards so the skills load. Each plugin's README covers its own requirements; Attention Diet needs Python 3.10 or later and a supported browser or connector for each source.

## Layout

```text
plugins/<name>/                    one folder per plugin, with its own README, CHANGELOG and LICENSE
.claude-plugin/marketplace.json    marketplace for Claude Code
.agents/plugins/marketplace.json   marketplace for Codex
```

Releases are tagged per plugin, for example `attention-diet-v0.6.0`. Questions and problems: [open an issue](https://github.com/mberto10/applied-systems/issues).

## License

[MIT](LICENSE).
