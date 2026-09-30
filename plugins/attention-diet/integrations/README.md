# Integrations

Integrations describe how the agent uses tools its host supplies, plus one bundled route: a reader for public RSS and Atom feeds. None of them is a credential store. The attention contract selects them independently:

| Choice | Where it is set | Guides |
|---|---|---|
| How a source is reached | Each thread's `access` | [Browsers](browsers/README.md), [connected tools](connectors.md) or [feeds](feeds.md) |
| Where "already briefed" is remembered | `memory_context` | [Briefing memory](memory/README.md) |
| Remote memory transfer | Supermemory on Codex only | [Codex adapter](codex-adapter.md) |

During a run the startup plan names the few guides the contract actually selects, alongside the shared rules in the [run skill](../skills/attention-diet/SKILL.md). Setup and tune use the guides above to configure a route. Every route feeds the same filter, selection record and memory format.
