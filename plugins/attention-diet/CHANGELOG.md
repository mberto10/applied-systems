# Changelog

Contracts stay on `attention-diet-contract/1.3` and memory records on `attention-summary/1.0` throughout; no migration is needed.

## 0.6.0 · 2026-09-23

First public release.

**Runs**
- Every source is reached and its account verified before the clock starts, so waiting for a sign-in never uses reading time.
- When asked for an account action, the agent states that checks are read-only by design and offers to list what needs a response.
- `intent.excluded` applies to every source during selection, on top of each source's own exclusions.
- The run skill keeps the main flow; evidence rules for stopping, overruns and changed items, and the surprise slot, load only when needed.
- Bundled views end with one line explaining how to change what reaches you.

**Setup and tune**
- Setup checks that the chosen browser's tools exist in the session and asks instead of installing an unusable route.
- Tune also lists your diets and shows what a contract contains, changing nothing.
- The template sets one contract-wide inspection limit; a surface's own limit can only lower it.
- A hand-edited contract installed with `contract.py install` gets a changelog line.

**Browsers and views**
- Codex and Claude browser guides match the current Codex Browser plugin and Claude Browser pane tools; long lists are read with the bounded extraction helper.
- Every HTML view, not only scripted ones, must carry the offline Content-Security-Policy.

**Other**
- One shared contract fingerprint for planning, runs and contract edits.
- Behaviour evals for `claude plugin eval` (`evals/`), MIT licence, sample contract.

## 0.5.0 · 2026-09-21

- One run script: `runtime.py plan`, `start`, `capture`, `finalize`, `finish`. A source's clock starts with its first window or capture; `finalize` closes collection and saves local memory.
- Bounded capture windows: every inspected identifier is counted, only eligible candidates send comparison text, and the next allowance can come back with the capture.
- Explicit overrun recovery; briefings distinguish samples, reached limits, retrieval stalls and verified list endings. End claims need structured evidence. New selections use schema 1.2; 1.1 selections remain readable.
- Parallel collection: collectors capture into the same run with the same commands; no worker dispatch, checkpoints or candidate handoff.
- Setup and tune prepare small JSON patches; the helper handles validation, revisions, backups, changelog and proposal cleanup.
- Removed: `memory_context.also_consult`, `contract.py compose` and `migrate`, `briefing_memory.py import-legacy`, and rendering of selection 1.0 or contract 1.2 archives. A 1.2 contract must be migrated with plugin 0.3 first.

## 0.3 and earlier

Private development versions.
