# Applied Systems

Reader-facing artifacts from [Applied Attention](https://appliedattention.substack.com/): working systems, eval contracts, dynamic workflows, and implementation notes from inside the AI shift.

This repository is the public companion surface for Applied Systems pieces. The writing explains the judgment; this repo holds the artifacts a reader can inspect, adapt, and argue with.

## Launch package

The first package supports the Applied Attention opener on custom harnesses and Claude dynamic workflows.

Planned contents:

- `dynamic-workflows/` - contract references and workflow-shape notes for dynamic workflows.
- `examples/eval-contracts/` - concrete eval-contract examples referenced by the essay.

## Status

Initial public scaffold. The first artifact package is being prepared for the launch essay and will be expanded as the essay moves through Substack formatting and QA.

## Plugins

This repository is also a plugin marketplace for Claude Code and Codex.

| Plugin | What it does |
|---|---|
| [`attention-diet`](plugins/attention-diet/) | Turns the feeds and messages you choose into one short briefing, read-only, with explicit limits and memory of what you already saw. |

Claude Code:

```text
/plugin marketplace add mberto10/applied-systems
/plugin install attention-diet@applied-systems
```

Codex:

```sh
codex plugin marketplace add mberto10/applied-systems
codex plugin add attention-diet@applied-systems
```

## License

[MIT](LICENSE).
