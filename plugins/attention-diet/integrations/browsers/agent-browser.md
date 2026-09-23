# agent-browser integration

Read when the plan resolves a thread to `agent_browser`. The [run skill](../../skills/attention-diet/SKILL.md) holds the rules shared by every browser. This provider runs the local agent-browser CLI. It requires an installed executable and browser runtime; the plugin does not install them or attach to an existing browser automatically. Check the installed version and help for the flags below before source access. If required options or a usable visible browser are missing, report the dependency.

## Establish the session

Use a new task-owned session ID for each service, such as `ad-<random-run-id>-<service>`. Retain the same ID for every command for that service. Never use the default session or enumerate other sessions to find a sign-in.

Use an absolute persistent profile path dedicated to this contract and service: `~/.local/state/attention-diet/browser-profiles/<contract-id>/<service>`, expanded before passing it to the CLI. Create the directory privately (owner-only) when absent. Reuse only a profile previously created for this integration; if provenance is uncertain, stop instead of adopting it. Do not copy, symlink or point to an everyday browser profile. Do not launch two tasks against the same profile concurrently; a busy/locked profile makes that service unavailable.

A `--profile` name can copy an existing Chrome profile, whereas an absolute directory path supplies separate persistent storage. Always pass the dedicated absolute path. A session isolates a locally launched browser; a session name combined with CDP attachment does not provide that isolation. These distinctions are documented in [Sessions](https://agent-browser.dev/sessions).

Create a private temporary JSON config containing `{}` outside the repository and plugin cache. Every invocation must use this explicit `--config` file and a child environment with all inherited `AGENT_BROWSER_*` settings removed. Do not alter the user's environment or config files. This avoids inherited auto-connect, remote provider, profile, state, plugin or launch settings. The config and environment precedence are documented in [Configuration](https://agent-browser.dev/configuration).

For example, resolve `binary`, `config`, `session` and `profile` as above, then invoke commands as an argument list:

```python
import os
import subprocess

def browser(*command):
    return subprocess.run(
        [binary, "--config", str(config), "--session", session,
         "--profile", str(profile), "--headed", *command],
        env={k: v for k, v in os.environ.items()
             if not k.startswith("AGENT_BROWSER_")},
        check=True, capture_output=True, text=True,
    ).stdout
```

Keep that launch context consistent in every shell/tool invocation; do not rely on variables surviving between tool calls. Never add `--cdp`, `--auto-connect`, a cloud provider, imported `--state`, credential-vault login, extensions or extra launch scripts. If launching reports an unexpected attachment or an ignored isolation option, stop before reading source content.

## Read and navigate

Open the configured URL with `browser("open", source_url)`. Use the headed window for the user's own sign-in; do not fill credential fields. Verify the account through the source's UI. The dedicated profile can retain that sign-in for later runs.

Use `snapshot` for page text and previews; `snapshot -i` focuses on interactive elements and is insufficient by itself for message or article contents. Read observed elements with `get text`, and use fresh snapshot references for navigation or loading more items. A click can return before the page updates. Use a bounded wait for the expected visible change, such as observed loading controls disappearing, the destination URL or expected text, before taking a new snapshot and counting additional items. Derive the wait condition from the observed page and source procedure; never invent item content. Keep waits and command timeouts within the remaining collection budget. If a wait fails, inspect the current state and report the actual limit rather than claiming the results are exhausted. Consult the installed help and [Commands](https://agent-browser.dev/commands) for exact syntax. A `click` is permitted only when its observed target and the contract's procedure establish an allowed navigation/expansion action. Apply read-state protection independently of pagination.

If a snapshot or text result is truncated, collect a permitted narrower observation or record the inspection limit. Do not use hidden authenticated APIs or page scripts to bypass the source procedure. The CLI's ability to type, submit, evaluate code or change settings does not authorize those actions.

## Finish

After finalizing the result, run `browser("close")` with the same explicit config, session, profile and environment. Close only that task's session, then remove its temporary config. Keep the dedicated profile for its next run. Do not sign out, clear storage or delete the profile. A failed close should be reported as a leftover task session, not followed by killing unrelated browser processes.
