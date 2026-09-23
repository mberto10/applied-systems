# Browser integrations

A thread with `access.type: browser` names one provider. Every browser thread also fixes `session: isolated`, `external_session_reuse: false` and `fallback: none`. The rules all browsers share (a task-owned tab in a dedicated environment, user sign-in, read-only interaction, cleanup) are in the [run skill](../../skills/attention-diet/SKILL.md#access-and-evidence).

| `access.provider` | Guide | Needs |
|---|---|---|
| `codex_in_app` | [Codex](codex.md) | Codex with its in-app browser tools |
| `claude_browser` | [Claude Browser](claude.md) | Claude Code with the desktop Browser pane tools |
| `agent_browser` | [agent-browser](agent-browser.md) | The local CLI, a browser runtime and a visible window for sign-in |
| `host_default` | Resolved by the startup plan | Codex or Claude Code |

`host_default` maps Codex to `codex_in_app` and Claude Code to `claude_browser`; any other host needs an explicit provider. An explicit provider always wins. If its tools are unavailable the source is unavailable: the agent never tries the next provider, and changing provider is a contract revision through `tune`. The schema validates the choice but cannot verify that a tool exists or constrain what a browser does.

## Adding a provider

Write one guide beside these covering required capabilities, session and sign-in setup, observation and navigation commands, limits and cleanup. Add the provider ID to the contract schema, to `BROWSERS` in `scripts/run_plan.py` and to this table, and extend the validation fixtures. It must satisfy the shared access rules; a working browser command alone is not enough. Source names and relevance rules never belong in a provider guide.
