# Applied Systems

Working systems from [Applied Attention](https://appliedattention.substack.com/), packaged so you can install, inspect and adapt them. The articles explain the reasoning; this repository holds the code.

It is also a plugin marketplace for **Claude Code** and **Codex**.

## Plugins

| Plugin | What it does | Version |
|---|---|---|
| [Attention Diet](plugins/attention-diet/) | One attention contract for the sources you choose, such as the newsletters and alerts in your inbox, and one short briefing that ends. Read-only by design, with explicit limits and memory of what you already saw. | 0.6.0 |

## Install

**Claude Code**

```text
/plugin marketplace add mberto10/applied-systems
/plugin install attention-diet@applied-systems
```

**Codex**

```sh
codex plugin marketplace add mberto10/applied-systems
codex plugin add attention-diet@applied-systems
```

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
