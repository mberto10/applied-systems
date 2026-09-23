# Collecting in parallel

Read before starting a parallel run offered by the plan.

Sources are independent, so two can be read at the same time. Do this only when the plan reports `execution.mode: parallel_permitted`, your host lets you start subagents, and every service is reached through its own tab, session or connector. Otherwise collect one source after the other; nothing else changes.

Collectors work on **the same run** with the same `window`, `capture-window` and `capture` commands, so observations are recorded directly. They return draft selections to the coordinator.

1. Use the single run started by the [run skill](../SKILL.md) with `--parallel`, after the sign-in and account checks that precede `start`. Collectors open their own tab in the same isolated browser session or connector and re-establish the account from its UI or metadata; they ask the user to sign in again only if that session was lost. With Supermemory, follow the selected memory guide to establish the source account and import history before dispatching collectors.
2. Start one collector per entry in `execution.collectors`, at most `max_workers` at a time, all in one message so they run concurrently. Give each one `PYTHON`, `SCRIPTS`, the run ID, the contract path, its `service` and `thread_ids`, its `guides` to read once, and this task:

   > You are a collector for one Attention Diet run that is already started. Collect only the threads you were given, following the collection and selection rules in the run skill, until every one of your surfaces reports `stop` or a capture result says `stop`. Use only a tab or session you create for this service, and begin every `ref` you choose with your service key so it cannot collide with another collector's. Do not call plan, start, finalize, memory or finish, do not start agents, and do not open any other source. Return only JSON: `{"entries": [...], "surprise": [...], "note": "..."}`. `entries` are draft entries in the finalize shape, with `item_refs`, for `new` candidates that meet the selection rules of your threads, within their ceilings. `surprise` holds at most one candidate entry for the surprise slot, if your threads are among its sources. `note` is one line about anything the user must know, such as a sign-in that is needed.

3. Assemble the returned drafts using the run skill's selection and combination rules, apply `max_items_by_thread` and choose at most `serendipity.max_items` from the surprise candidates. Then finalize and finish as described in the run skill.

A collector that fails or is interrupted loses nothing it captured, and `finalize` reports its unfinished surfaces as stopped early or not checked. If it captured nothing and time remains, collect that source yourself. Never start a second collector for a service, and never let two collectors share a tab.
