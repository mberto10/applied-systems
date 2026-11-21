# Changelog

Contracts stay on `attention-diet-contract/1.3` and memory records on `attention-summary/1.0` throughout; no migration is needed. 0.7 adds an optional access type, so a contract that uses `feed` needs 0.7 or later, and one that uses `treg` or `curation` needs 0.8 or later.

## 0.9.0 · Unreleased

- treg surfaces can watch accounts: `handles` with `{handle}` makes one call per account, and with `{from_handles}` one X search per group of accounts. `skip_replies` drops replies; entries are interleaved across calls and a failed call no longer stops the others.
- `scripts/import_following.py` prepares a contract revision that sets a surface's handles to the accounts you follow on X.
- A thread may set its own `interests`, which replace the contract's in the decision model's questions. The evidence rubric is asked only of `public_posts` threads.
- The short list and the front page show only the run's date and time above the title. Coverage, costs and helper remarks fold behind one Details control; unavailable sources and memory warnings stay visible. An empty list shows no overview and no Reasons toggle.
- New example, `examples/gmail-contract.json`: Gmail through the connector, keeping what needs a reply, someone waiting or a deadline, curated by Jev. The connector guide gains a Gmail section.

## 0.8.0 · Unreleased

**Views and test runs**
- Two new interfaces: `needs_you_html`, a short list of what passed with filters by section and source that work without scripts, and `front_page_html`, an edition with a lead story, second stories and rows for videos, posts and articles. Both are offline pages under the same Content-Security-Policy as the other HTML views; `scripts/views.py` builds their bodies from the selection data.
- `scripts/test_run.py` tries a contract while it is being written: it reads its feed and treg surfaces, scores them with the contract's decision model and writes `test-run.json` and an HTML preview in the contract's view. Nothing is remembered; browser and connector sources are listed as skipped.

Collection and curation become separate steps: a helper collects entries in one shape, a decision model scores them against the contract, and code decides.

**treg**
- New `treg` access type: each surface names one [treg](https://treg.to) catalog call in `treg_calls` (exact catalog id, query, `window_hours`), for public posts on X, Reddit, TikTok, YouTube, Hacker News and more, without a browser or platform sign-in.
- `scripts/treg_source.py fetch` runs only the contract's catalog ids through the signed-in `treg` CLI, finds the rows in any vendor's answer, drops rows outside the window, already seen or listed twice, and returns entries with a fixed-length basis. Engagement counts stay outside the basis, so a changed like count is not a new post. Each call's charge is returned.
- treg threads must be `public_posts`; a search reads one page, so a treg surface is a sample.
- New example, `examples/treg-contract.json`: X posts about building with agents, curated by Jev.

**Decision models**
- New optional `curation` section. `scripts/decide.py score` asks one question per interest, one per exclusion and one evidence rubric (echo, claim, first-hand) about each entry, and decides include, drop or undecided in code from `include_at`, `exclude_at` and `min_evidence`.
- Providers: `jev` (TypeSafe AI through treg), `perplexity` and `openai` (native Decisions APIs), and `claude` (the local CLI, prompted estimates). Keys come from the environment, never the contract.
- `decide.py questions` shows what the contract asks. Nothing learns from reading or clicks; thresholds change only through tune.

## 0.7.0 · Unreleased

**Feeds**
- New `feed` access type: a surface reads an RSS 2.0, RSS 1.0 or Atom feed named in `feed_urls`, with no browser, sign-in or host tool. Writers, newsletters, video channels, podcasts, preprint servers and many public institutions publish feeds.
- `scripts/feed.py fetch` takes the URL from the contract, reads at most 5 MB over plain https, refuses redirects away from https and documents that declare entities, and returns at most the window's number of unseen entries with a fixed-length plain-text basis, so an unchanged entry compares equal across runs.
- Feed threads must be marked `public_posts`; the run plan routes them to [integrations/feeds.md](integrations/feeds.md) with the account key `feed:public`.
- New example, `examples/feeds-contract.json`: writers, channels and podcasts you follow.

**Viewing a contract**
- New `view-contract` skill and `scripts/contract_view.py render`: one offline page showing what counts, what is left out, where the agent looks, when a check stops, surprises, what is remembered, what never happens, and the revision history from the changelog, with the exact contract folded at the end. Read-only.

**Earlier documentation changes**

- README leads with the attention contract, the finite check and your own view; examples are inbox newsletters and alerts, GitHub releases and selected accounts on an open network.
- The terms caution moves up: most platforms built around a feed prohibit automated access, so connectors, APIs and email alerts come first.
- New connector example, `examples/inbox-contract.json`, next to the browser sample.

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
