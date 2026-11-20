# Integrations

Integrations describe how the agent uses tools its host supplies, plus two bundled routes: a reader for public RSS and Atom feeds, and a collector for public posts through treg. A bundled decision-model helper can score what any route collects. None of them is a credential store. The attention contract selects them independently:

| Choice | Where it is set | Guides |
|---|---|---|
| How a source is reached | Each thread's `access` | [Browsers](browsers/README.md), [connected tools](connectors.md), [feeds](feeds.md) or [treg](treg.md) |
| Who scores collected entries | `curation` (optional) | [Decision models](decision-models.md) |
| Where "already briefed" is remembered | `memory_context` | [Briefing memory](memory/README.md) |
| Remote memory transfer | Supermemory on Codex only | [Codex adapter](codex-adapter.md) |

During a run the startup plan names the few guides the contract actually selects, alongside the shared rules in the [run skill](../skills/attention-diet/SKILL.md). Setup and tune use the guides above to configure a route. Every route feeds the same filter, selection record and memory format.
