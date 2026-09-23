# Data handling

This describes the local implementation, not a hosted privacy policy. The public release still needs a publisher contact and, for directory submission, the required public policy URLs.

## What is stored

| Data | Location and retention |
|---|---|
| Attention contract | By default `~/.config/attention-diet/contracts/<id>/attention_contract.json`. It can contain interests, source URLs, account identity expectations and personal paths. Revisions and a change log are retained. |
| Briefing memory | The directory selected in the contract, normally `~/.local/state/attention-diet/<id>`, or the explicitly selected Supermemory space. Records contain included-item identifiers, fingerprints, short summaries and coverage information. They do not store source bodies or rejected candidates. |
| Working run data | A run-state file under the configured state directory and a temporary `attention-diet-<run-id>-…` workspace. These can contain observations, candidate comparison text and the selection. Normal successful completion removes run state and known temporary files. Interrupted runs or explicit diagnostic retention can leave them behind. |
| Delivered result | The current conversation, plus a local HTML file if requested. These are not erased by temporary-workspace cleanup. |
| Browser sign-in | Managed by the selected browser. `agent_browser` uses a dedicated persistent profile under `~/.local/state/attention-diet/browser-profiles/<contract-id>/<service>`. That profile may contain cookies and remains after the run. |

Configuration and state roots can be overridden; the installed contract records the actual memory location. Removing a contract archives it and leaves its memory. Uninstalling the plugin is not a delete-all-data operation.

## What leaves the machine

The host's model provider processes the source material supplied to the agent. Browser and connector requests reach the selected services. If configured, Supermemory receives the briefing records described above. Host conversation history, tool logs and provider retention are governed separately by those products.

The bundled Python helpers do not implement an author-operated collection endpoint or telemetry uploader. This does not mean that model processing, browser access or optional connectors happen entirely on the machine.

## Reading and account actions

The plugin instructs the agent to observe and navigate, without sending replies, reacting, following or changing account settings. Merely opening content can still affect read status or visibility on a service. The source procedure must account for those effects and report uncertainty. These instructions rely on agent compliance and the host's controls; the Python helpers do not intercept browser or connector calls.

Sign in yourself through the chosen browser or connector. Do not put passwords, tokens or cookies in a contract, example or support report. To remove stored data, identify the configured contract/memory locations and dedicated browser profile first; deleting only the plugin folder leaves those separate records intact. Removing local data does not delete copies held in host conversations or optional remote providers.
