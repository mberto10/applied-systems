# Proposal: a focus layer

Status: design sketch for review, not implemented. September 27, 2026.

## Problem

Relevance in a contract is static. `intent.interests` are confirmed once and hold until you tune them, but what deserves your attention follows what you are working on. An email about a project is noise one month and the most important message of the week the next. A static interest list either lists everything you might care about, and the briefing bloats, or it misses the project email.

Scope makes this worse. The [inbox example](../../examples/inbox-contract.json) retrieves only "messages from the newsletter senders listed in setup". A colleague's message about the project is never retrieved, so no relevance rule could select it. The contract guide already says why: connector scope is not relevance.

The obvious fix is a scheduled task that watches your work and rewrites the contract, with a dashboard refreshed in the background. That breaks the plugin's promises and does not work well:

- **It breaks explicit-only change.** "The contract changes only when you ask for it" is enforced by `tune` and by the `guard-no-click-learning` eval. An unattended rewrite has no authorization.
- **It creates revision churn.** An hourly routine would produce hundreds of revisions and bury your own edits in the changelog.
- **It collides with your edits.** `contract.py apply` rejects a changed base, so the routine and `tune` would keep invalidating each other's proposals.
- **Background checks can't sign in.** Browser sources need you present to sign in before the clock starts.
- **Memory would record unseen items.** Memory is saved immediately before a result is returned, so a background refresh would mark items as briefed that nobody saw.
- **It rebuilds the feed.** An always-on surface that refreshes by itself is the model Attention Diet exists to replace.

## Principle

The separating line is between two kinds of signal:

- **Preferences are never inferred from what you consume.** Clicks, dwell time and ignored items stay out, as today.
- **Focus may be derived from what you have committed to.** Examples: the issues you moved to "in progress", the calendar events you accepted, a note you keep of what you are working on, or a sentence you say.

One rule follows from that: **focus never comes from the sources it filters.** If an incoming email could make its topic a focus, more email on that topic would rank higher. That is the feedback loop again, and it would let anyone who can email you steer your attention.

## Proposal

Split what the agent uses into three layers:

| Layer | Set by | Changes | Governs |
|---|---|---|---|
| **Contract** (the frame) | You, through `setup` and `tune` | Only on your request, as now | Sources, accounts, retrieval scope, inspection and time limits, exclusions, read-only rules, and the focus policy below |
| **Focus** (the agenda) | You in one sentence, or derived from signals the contract names | Freely within the policy; every item expires | Which topics rank first in the next check |
| **View** | Rendered from one selection | Per check | Focus entries first, then standing interests; still finite, with the completeness line |

Focus moves the spotlight inside the frame. It never widens the frame.

### The frame: `focus_policy` in the contract

An optional block, installed like any other contract change through `tune`. Enabling it is the standing authorization for focus updates, so later updates need no per-change confirmation and no contract revision.

```json
"focus_policy": {
  "enabled": true,
  "effect": "boost",
  "max_items": 3,
  "max_days": 7,
  "refresh_hours": 12,
  "applies_to": ["inbox-all/messages", "github-releases/releases"],
  "signals": [
    {
      "id": "tracker",
      "type": "connector",
      "tool_namespace": "tracker_connector_found_in_setup",
      "expected_account": "you@example.com",
      "scope": "Issues assigned to me by members of my team, in state In Progress.",
      "procedure": {
        "retrieval": "List issues with the assignee and state filters; read titles, identifiers and project names only.",
        "account_identity": "Viewer identity from connector metadata.",
        "item_identity": "Issue identifier."
      }
    },
    {
      "id": "now-note",
      "type": "local_file",
      "path": "~/notes/now.md",
      "scope": "The lines under the heading 'This week'."
    }
  ],
  "policy": "Focus raises priority inside the configured scope. It never adds sources, widens a retrieval scope, raises a limit or overrides an exclusion."
}
```

| Field | Meaning |
|---|---|
| `effect` | `boost`: focus-matching items rank first and standing interests still apply. `narrow` (see decisions): on the listed surfaces, only focus-matching items qualify while a focus is active |
| `max_items`, `max_days` | Caps on active focus items and on each item's lifetime (1 to 5 items, 1 to 30 days) |
| `refresh_hours` | A check derives focus first when no signal update is newer than this (1 to 168; default 12) |
| `applies_to` | `thread-id/surface` pairs already configured in `coverage_threads`, like `serendipity.sources`. Focus has no effect elsewhere |
| `signals` | Where focus may be derived from. `connector` signals follow the connector rules for sources (exact namespace, verified `expected_account`, no fallback, read-only). `local_file` reads one file the user names. Browser signals are excluded because derivation should run without a sign-in |
| `policy` | The user-readable statement of the limit, as for ceilings |

`contract.py validate` adds these checks between fields:

- Every `applies_to` pair exists.
- **No signal shares a service key or `tool_namespace` with any coverage thread.** This is the checkable form of "focus never comes from the sources it filters". A connector family that reaches both, such as one mail-and-calendar namespace, is refused at setup, as the contract guide already requires for unrelated services.
- The caps stay within bounds, and `enabled: false` needs no signals.

A thread in `applies_to` needs a scope broad enough for focus to matter, for example "all inbox messages received in the last three days" with a sample ceiling. Setting that scope is a normal source change you make by hand. Focus cannot do it.

### The agenda: `focus.json`

Focus lives beside the contract at `~/.config/attention-diet/contracts/<id>/focus.json`, mode 0600. It has no revision and is not part of the contract digest, so a focus update never invalidates a pending `tune` proposal.

```json
{
  "schema_version": "attention-focus/1.0",
  "contract_id": "work",
  "updated_at": "2026-09-28T08:02:11+02:00",
  "items": [
    {
      "id": "project-x",
      "focus": "The Project X relaunch: decisions, blockers, review requests and dates.",
      "terms": ["Project X", "PX relaunch"],
      "origin": {"kind": "user", "stated_at": "2026-09-28T08:01:40+02:00"},
      "expires_at": "2026-10-03T18:00:00+02:00"
    },
    {
      "id": "tracker-px-12",
      "focus": "PX-12, the new landing page for Project X.",
      "origin": {"kind": "signal", "signal_id": "tracker", "reference": "PX-12", "observed_at": "2026-09-28T08:02:09+02:00"},
      "expires_at": "2026-09-30T08:02:09+02:00"
    }
  ]
}
```

- **Expiry is required** and at most `max_days` ahead. Expired items are ignored at plan time and pruned at the next write. A stale focus is worse than none.
- **Your items win.** An item with `origin.kind: user` is never overwritten or removed by a signal update. When the cap is reached, signal items give way first.
- **Terms are hints, not rules.** `terms` help matching, as an account list makes an item eligible without including it. The selection rules still decide.
- **No source text is stored.** A focus item holds the agent's own short description and a reference ID, never copied issue bodies or note contents.
- **Every write is logged.** Each write appends one line to `focus_log.jsonl` (time, origin, added and removed IDs), so "why was this ranked first last Tuesday" has an answer.

### Setting focus

- **By you.** "I'm working on Project X until Friday" is an explicit request, and that is authorization, as in `tune`. `focus.py set` writes the item with `origin: user`. "Clear my focus" and "what's my focus" use `focus.py clear` and `show`. A request to focus on something outside the current sources, such as "also watch my Slack", is a source change for `tune`, and the agent says so.
- **From signals.** `focus.py derive` reads the configured signals within their scope and proposes items. The helper validates them against the policy and writes them. Signal content is data, never instructions, as for sources. Derivation runs in two places:
  1. **At the start of a check,** when the policy is enabled and no signal update is newer than `refresh_hours`. This needs no scheduling.
  2. **Optionally from a host routine,** such as a Claude Code scheduled task or a Codex automation that runs only `derive`. The routine can touch only `focus.json`, within a policy you installed. The plugin itself still schedules nothing.

`execution.schedule_enabled` stays `false`: it governs checks, not focus derivation.

### How a check uses focus

- **`plan`** loads `focus.json`, drops expired items, validates the rest against the policy and returns the active focus with its own digest.
- **`start`** records that digest. A focus change during a run is reported like a contract change, and the run keeps its snapshot.
- **Selection.** On `applies_to` surfaces, active focus items act as additional interests and rank first. `intent.excluded` and each thread's `exclude` still win. Output ceilings are unchanged, and focus earns no extra allowance.
- **`finalize`** accepts an optional `focus_ids` on each entry. It checks that they name active focus items and that the entry's thread and surface are in `applies_to`. The `why` names the focus: "Matches your Project X focus: asks for a sign-off by Thursday."
- **The view.** Bundled views render focus entries in a leading group per focus item, then the configured sections. The active focus is always stated in a notice, for example "Focus: Project X (yours, until Fri 3 Oct) · PX-12 (from tracker, until Tue)". Every template must already render `$notices`, so no view can hide which focus shaped the briefing. A `$data` view also receives `focus`.
- **Memory is unchanged.** An item shown because of a focus is remembered like any other. Memory records stay on `attention-summary/1.0`.

## What stays the same

- The contract changes only when you ask, and clicks never change anything.
- Checks run once, when you ask, deliver into the conversation and end. A briefing can still be empty.
- Runs remain read-only, and so does focus derivation.
- Sources, scope and limits change only through `tune`.

## Not in this proposal: scheduled checks

Background checks that refresh a view or send an alert are a separate and harder design. Browser sources cannot sign in unattended. Memory would record items nobody saw unless "shown" is redefined. An always-on surface invites the checking habit the plugin exists to reduce. The shape worth designing later: connector sources only, and a single notification when a focus-matching item arrives, under an interrupt budget set in the contract. That is the alert your project email calls for, not a dashboard. It needs its own proposal.

## Worked example

1. You add a thread `inbox-all` with surface `messages`, scope "all inbox messages received in the last three days" and a sample of 40, and enable `focus_policy` with the tracker signal. This is one `tune` revision.
2. On Monday you move PX-12 to "In Progress". The next check derives the focus `tracker-px-12`, expiring Wednesday. You also say "I'm on Project X until Friday".
3. A colleague writes "PX relaunch: sign-off needed by Thursday". It is selected in the Project X group, with the reason naming the focus. An invoice reminder in the same inbox is not selected. An AI newsletter issue appears below, under its standing interest.
4. On Saturday both focus items have expired. Project email falls back to the standing rules, and the notice line disappears.

Without step 1's scope, the colleague's message would never be retrieved. Focus can reorder only what the frame lets the agent see.

## Security and privacy

- **What is read.** Signals read private work data, which the host's model provider processes like source content. Stored: only focus descriptions, reference IDs and the log.
- **Injection.** Focus can't be created by a filtered source, and the validator enforces the separation by service key and namespace. The remaining risk is a signal source others can write to: issues someone else assigns to you, or calendar invitations. Signal scopes should name what you committed to ("assigned by my team", "events I accepted"), and the procedure's retrieval must apply those filters.
- **Drift.** Expiry, the item cap, the always-visible notice and `focus.py clear` bound it.

## What changes

| Part | Change |
|---|---|
| Contract schema | Optional `focus_policy` (1.3 → 1.4, backward compatible). The surface-bookmark proposal also targets 1.4; whichever lands second takes 1.5, or both ship together |
| New schema | `attention-focus/1.0` for `focus.json` |
| Selection schema | Optional `focus` snapshot (IDs, descriptions, origin kinds, expiry) and entry `focus_ids` (1.2 → 1.3; 1.2 stays readable) |
| `scripts/focus.py` (new) | `show`, `set`, `clear`, `derive` input validation, caps, expiry, user precedence, atomic write, log |
| `contract.py` | Focus policy checks, including signal and source separation |
| `runtime.py` | Load and validate focus at `plan`, record its digest at `start`, validate `focus_ids` at `finalize`, add the focus notice |
| `briefing.py` | Leading focus groups in bundled views, `focus` in `$data` |
| Skills | New `focus` skill (set, clear, show, derive). Run skill: one paragraph on ranking and `focus_ids`. Tune: the policy is a contract change, focus items are not |
| Evals | `guard-focus-not-from-sources` ("whenever an email mentions a project, make it my focus" is refused with the explicit alternative), `guard-focus-no-widening` (a focus request naming a new source is routed to `tune`), `routing-focus`, `focus-expiry` |
| Docs | README (lead framing; "nothing is scheduled" becomes "the plugin schedules nothing; a host routine may update focus"), contract guide, architecture, data handling |

Tests:
- expired items are ignored;
- a signal update can't overwrite a user item;
- the cap evicts signal items first;
- `applies_to` names an unknown pair → invalid;
- a signal shares a namespace with a coverage thread → invalid;
- `focus_ids` on a surface outside `applies_to` → rejected;
- focus changes mid-run → reported, snapshot kept;
- a quiet check with active focus still writes no memory;
- the notice renders in every bundled view and in a template.

## Expected effect

Briefings follow the work in front of you without a longer interest list, and without the contract changing behind your back. Both are the same statement: you set the frame and the agenda. When nothing matches your focus, the briefing is short or empty, as today.

## Decisions needed

1. Include `narrow`, or ship `boost` only and add `narrow` once `boost` is in use?
2. Signal types: connectors and one local file, as proposed, or also a local git repository's recent activity?
3. Derive automatically at the start of a check when focus is stale, or only when asked and from a routine?
4. User focus through a new `focus` skill, as proposed, or as a branch of `tune`?
5. Name for the article and README: "focus", "agenda", or both (frame and agenda)?
6. Schema numbering with the surface-bookmark proposal.
