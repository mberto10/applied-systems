# Installation and first run

Attention Diet includes Codex and Claude Code manifests. It needs a host that can run local Python commands and access the browser or connector selected for each source. Installing this package does not install a browser, connect accounts or start a briefing.

## Codex

Install from the public marketplace, then start a new task so Codex loads the plugin:

```sh
codex plugin marketplace add mberto10/applied-systems
codex plugin add attention-diet@applied-systems
```

For local development, register a checkout instead: `codex plugin marketplace add /absolute/path/to/applied-systems`.

Browser sources require Codex's in-app browser tools. Plain CLI access alone does not supply them. If those tools are unavailable, explicitly choose an installed [agent-browser integration](../integrations/browsers/agent-browser.md) or an available [connector](../integrations/connectors.md) during setup.

## Claude Code

Install from the public marketplace inside Claude Code, then start a new session:

```text
/plugin marketplace add mberto10/applied-systems
/plugin install attention-diet@applied-systems
```

To load a local checkout for one session instead, run `claude --plugin-dir "$PWD"` from the plugin root. Use `/attention-diet:setup`, `/attention-diet:attention-diet` and `/attention-diet:tune`, or ask in ordinary language.

The default Claude browser route requires the desktop Browser pane's `mcp__Claude_Browser__*` tools. A terminal-only Claude Code session does not supply this integration. In that environment, explicitly select an installed `agent_browser` provider with its own dedicated profile, or a supported authenticated connector. The Claude in Chrome extension does not satisfy this plugin's isolated-browser requirement. See [browser choices](../integrations/browsers/README.md).

## Prepare Python

Follow [runtime setup](../README.md#runtime-setup) from the plugin root. The documented shell commands use macOS/Linux conventions. Native Windows setup has not been verified.

Python 3.10 or later and the dependencies in `requirements.txt` are required. Node.js is needed for the Codex adapter path when selected, and for its developer tests. A model subscription or API access and any optional service subscriptions are separate from this package; a run consumes the host's normal model/tool usage.

## First briefing

1. Ask setup to configure one source, your interests and a reading-time target. Local memory and conversation output are the simplest starting choices.
2. Confirm that the selected browser or connector is available. Sign in yourself if requested during the first run. The agent verifies account identity before dependent reads.
3. Ask Attention Diet to run once. Review both the selected items and the coverage notice. An unavailable source is reported; it is not silently checked through another route.
4. Ask tune for a specific lasting change, such as excluding routine promotion. Request a proposal if you want to inspect the change before applying it.

Setup and tune do not collect a briefing. No recurring schedule is created. Contract files and briefing memory stay outside the plugin directory across updates.

## Common problems

| Symptom | What to check |
|---|---|
| Skills do not appear | The plugin is installed/enabled, and the task or session was started after installation. |
| Missing Python dependency | Run the pinned `requirements.txt` installation in the documented environment; do not skip schema validation. |
| Browser tools unavailable | The host exposes the selected integration. Choose a different supported route explicitly if needed. |
| Login or identity cannot be verified | Sign in in the selected isolated browser; do not copy credentials or a daily-use browser profile into the plugin. |
| No selected items | Read the coverage notice: no relevant new items and an inaccessible source are different outcomes. |
| An edited post is omitted | The current memory policy conservatively withholds changed captures of known public posts when novelty is uncertain. |

For a support report, include host and plugin versions, the selected provider, the command/error and a redacted reproduction. Do not attach private messages, account cookies, full run state or your personal contract by default.
