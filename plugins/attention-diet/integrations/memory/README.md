# Briefing memory

Memory answers one question: was this version of this item already brought to the user's attention? It lets a later briefing omit what has not changed. Preferences live in the attention contract, never here. Memory does not track whether the user read or handled an item, and holds no pending lists, reminders or acknowledgement requests.

This is reference material for setup, tuning and diagnostics. During a run the [run skill](../../skills/attention-diet/SKILL.md) and the runtime handle memory; with local storage there is nothing further to read.

## Choosing a provider

| `memory_context.provider` | Storage | Needs |
|---|---|---|
| `local` (default) | Files under the configured `directory` | An absolute or `~/` path outside the repository and plugin cache |
| `supermemory` | Documents in a chosen space | A connector that can list, retrieve and save original documents. See [setup](supermemory-setup.md) and the [run procedure](supermemory.md) |

Both store the same record and use the same comparison. Both use `purpose: avoid_repeating_previously_briefed_items` and `on_unavailable: continue_with_notice`. A malformed configuration is an error to report, not a reason to choose the other provider. Switching providers changes where history lives and copies nothing: move existing records only on an explicit migration request, preserving version IDs, timestamps, predecessor links and account scope. Hosts and browsers can share a history when they reach the same location and keep the same identity conventions.

## What is saved

One short record per service account represented in a finalized briefing, defined by the [memory-record schema](../../schemas/memory-record.schema.json) and shown in [example-record.json](example-record.json):

| Data | Purpose |
|---|---|
| Contract ID and revision, account key | Keep histories in the right scope |
| Version ID, creation time, predecessor | Provenance and continuity |
| Included item versions: service, identifier, fingerprint, method, source time when known | What was included, and whether a later version differs |
| A short summary and a coverage note | Context for the next run. The coverage note is not a novelty cutoff |
| Optional surprise slot and topic | Avoid repeating surprise topics |

Only included item versions are saved. Source bodies, screenshots, browsing logs, rejected candidates and credentials never are. A quiet run writes nothing and leaves history intact. Local records are owner-only Markdown files with JSON front matter, written atomically under `directory/summaries/`; a version ID is never overwritten with different content.

## Scope and continuity

History follows the contract's `id` and its `previous_ids`, so a renamed contract keeps what it already briefed. It is scoped per service account: the account key comes from the source procedure and must stay stable, because a changed spelling starts an empty history. Change `id`, `directory` or `space` only through a deliberate contract revision.

Each run compares candidates with every saved version, not just the latest record, so an item included several runs ago stays suppressed while unchanged. Missing or incomplete history yields a continuity notice; it never proves that everything observed is new.

A changed text fingerprint alone does not prove a new event. The same method label does not establish consistent author presentation, text components or inspection depth. Private communication can qualify through a different incoming-event ID under the established `incoming-id/v1` method, or an observed source event later than every prior briefing containing that item. Observation time is never source-event evidence.

For `public_posts` threads, any changed capture of a known identity remains uncertain and stays out of the briefing. The current schema cannot establish a comparable, substantive edit; neither a changed incoming-ID basis nor a later timestamp overrides that limitation. This can withhold genuine edits until explicit edit evidence is supported. Unseen post identities remain eligible, and exact matches against any saved version remain suppressed. The runtime applies this policy per thread, including when a service has both public and private threads. The diagnostic `compare` command uses the contract's public services conservatively because its input has no thread references.

Old records without a documented method remain usable for exact matches. Never re-show old items to seed a new format, convert hashes, or assign a method to an old record whose basis cannot be reproduced. Keep the procedure's canonical author representation and body/link/media inclusion consistent; do not rewrite history when capture conventions change.

## Timing

The selection is finalized first and memory is saved immediately before the response is returned. The host offers no hook that couples the write to the display, so an interruption in between can leave a record for a briefing the user never saw. If that is known to have happened, correct that version explicitly; do not build a delivery state machine or ask for acknowledgements. If saving fails, the briefing is still delivered with a continuity notice.

## Diagnostics

[briefing_memory.py](../../scripts/briefing_memory.py) exposes the pieces the runtime uses: `validate`, `load` (add `--full` for item versions), `compare`, `fingerprint`, `fingerprint-batch`, `render` and `save`. They take `--contract`, `--account` and, for Supermemory, `--documents EXPORT`.
