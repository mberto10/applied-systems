# Next up: work panel extension

Date: 2026-10-03
Status: proposed implementation plan; product requirements below come from Max's request. Defaults, architecture and sequencing are recommendations, not approved implementation decisions.

Follow-on product draft: [Shared, live work plan](shared-work-plan.md) develops Max's confirmed direction toward agent-updated acceptance criteria, a central source, and concurrent human edits during orchestrated work. It describes future behavior; the read-only snapshot implementation below remains the current baseline.

## Outcome

Keep a clear, browsable overview of work beside the ChatGPT conversation. The user can explore Linear issues, GitHub issues or a hierarchical Markdown plan, choose what matters next, and start a scoped conversation action from any actionable item.

Requested: a panel on the right, distinct source modes, issues and next steps, and support for a Markdown document with a fixed hierarchy. ChatGPT controls panel placement and dimensions. Verify the conversation-panel entrypoint in the target client before investing in the full UI; a local preview does not prove right-side placement.

## Product shape

One panel, with a source selector and a shared, user-curated **Up next** list. Preserve the existing contextual suggestions as a fourth mode, **Suggestions**. Source modes are views over work; they do not execute anything on selection.

| Mode | Default outline | Important controls |
| --- | --- | --- |
| Linear | Project → issue → sub-issue, where source relationships are available | Project, assignee, state; optional team and label filters |
| GitHub | Repository → issue → sub-issue, where available | Repository, assignee, state, labels; PRs optional and separate |
| Markdown | Document → headings → nested task items | Import/replace document, search, show completed |
| Suggestions | Up to three contextual next actions | Request/refresh suggestions, add to Up next |

Dependencies are links or badges, not invented tree parents. Do not infer parentage from similar titles. When a connector does not expose hierarchy, show a flat issue list within its project/repository and identify the missing relationship data. Keep unknown status distinct from open or completed.

Proposed desktop structure (illustrative content, no real issue data):

```text
NEXT UP                          Refresh
[ Linear ▾ ]  [ Project ▾ ]
[ Search this source…                 ]

UP NEXT · 2                    Collapse
1  Review the onboarding flow       ⋯
2  Define the release checks        ⋯

PROJECT OUTLINE         Open · Mine ▾
▾ Website                         8 open
  ▾ Improve onboarding            Active
      Draft welcome copy             ○
      Review accessibility           ○
  ▸ Prepare release                  ○

──────────────────────────────────────
Review accessibility
Website › Improve onboarding
Status · assignee · priority
Description / acceptance criteria…
[Add to Up next] [Open source]
[Work on this ▾]

Updated 2 minutes ago · 24 loaded
```

Use a compact outline as the primary surface. Selected-item details open in the same panel; at narrow widths they replace the outline with a clear Back action. Keep the chosen mode, expanded branches, scroll position and selection stable during updates. Show identifiers on issue rows and metadata on selection; avoid a large card for every issue.

## Core interactions

1. **Open and orient.** Reopen the last explicitly selected workboard or choose a source and scope. The first source load requires only the missing project/repository/document. Keep each conversation's active board explicit so work does not bleed across chats.
2. **Browse.** Expand branches, search and filter without posting chat messages or invoking a model. Search loaded content and retain matching ancestors. If only part of a source has loaded, label this and offer Load more; never imply exhaustive results.
3. **Inspect.** A row click selects the item and shows its description, status, source link, hierarchy and known blockers. A disclosure arrow only expands/collapses. Use standard keyboard tree navigation and a visible focus state.
4. **Choose the next work.** Add any issue, Markdown task or suggestion to Up next. Reorder with accessible move controls, remove it, and keep a selected focus item. This list expresses user intent; suggestion refreshes never replace or reorder it.
5. **Start.** Work on this offers Plan, Investigate, Implement/work, and Review; default to the last explicit choice, initially Plan. Show an editable prompt with the exact item and scope before sending. The button sends a normal message into the current chat. Browsing and pinning never start work.
6. **Continue.** After sending, keep the panel and other items usable. Record message delivery separately from source status. Acknowledging a sent prompt does not mean work started or finished. The current all-card `settled` lock must become per-action delivery protection.
7. **Refresh.** Preserve view state and pins. Surface changed, removed or inaccessible items. Keep the last successful snapshot with an age/error indicator when a refresh fails. Do not drop pinned items silently.

Show source facts separately from assistant recommendations and user priorities. Mark blocked issues visibly, but allow deliberate investigation of a blocker. Do not manufacture a completion percentage from an incomplete source listing.

## Markdown contract

The document owns its hierarchy and order. Parse Markdown structurally; never ask a model to reconstruct its outline. Proposed supported format:

```markdown
# Website plan

## Onboarding

- [ ] Review the welcome flow <!-- next-up:welcome-review -->
  - [ ] Check empty states <!-- next-up:empty-states -->
  - [ ] Check keyboard access <!-- next-up:keyboard -->
- [x] Collect examples <!-- next-up:examples -->

## Release

- [ ] Define release checks <!-- next-up:release-checks -->
```

- Headings establish sections; nested task-list indentation establishes task parentage; checkboxes supply completion. Preserve source order and wording.
- Ordinary paragraphs and non-task lists remain description content under the relevant section/task, never become implicit executable work. Fenced examples do not become tasks. A section can be inspected or deliberately used as scope, but its descendants do not start automatically.
- Optional explicit IDs support stable pins across edits. Without IDs, use document identity plus heading/task path and duplicate occurrence; label matching across structural edits as uncertain rather than transferring a pin to the wrong task. Do not add IDs to the user's document silently.
- First delivery supports pasted Markdown and importing a selected `.md` file as a versioned snapshot. The panel names the document, import time and source revision/hash. A later explicit reimport replaces that snapshot and reconciles pins.
- Cloud ChatGPT cannot watch an arbitrary local path. Live linked documents require a separately configured source adapter with access to that file or repository. File references from a host are not assumed to be local filesystem paths.
- Initial source content is read-only. Checkbox changes happen in the source and appear on refresh/reimport. Pinning and ordering Up next remain editable. Future write-back needs source revisions and conflict handling.
- Treat content as data: disable raw HTML execution, validate links, cap size/depth, and never execute instructions merely because they occur in an imported document.

## Data access: two explicit stages

### A. Existing connectors, populated through the conversation

Reuse the connected Linear/GitHub tools. ChatGPT reads the requested scope and supplies a structured snapshot to the panel through Next up tools. Verify the actual connector schemas and pagination during implementation; adapters must expose missing capabilities rather than claiming parity.

Once loaded, browsing/search/filtering of the snapshot is immediate and does not use the model. **Fetch latest** explicitly requests a chat turn to read sources and update the panel. A check for a new panel revision only detects snapshots already supplied to Next up; it is not a Linear/GitHub refresh.

This is the first useful release because it uses existing connections. It is not the finished version of independent source refresh.

### B. Direct source adapters for independent browsing and refresh

For the intended direct experience, let the Next up backend read Linear/GitHub through separately authorized provider integrations. Do not assume it inherits ChatGPT connector credentials. The UI calls Next up tools; the backend performs pagination, source search, lazy child loading and refresh without a chat turn. Credentials stay server-side.

Ship Linear first, GitHub second. Support manual refresh and bounded refresh while the panel is visible, with backoff/rate-limit handling. Source updates do not require model calls; generating suggested next actions remains an explicit model interaction. There is no assumed after-every-turn host hook.

## State and architecture

Keep the existing inline renderer compatible. Build a dedicated panel resource and frontend instead of continuing to generate the panel by replacing the card's `<body>` tag.

- **Source adapters:** normalize connector snapshots, direct provider reads and Markdown parsing to a shared outline. Preserve provider IDs, URLs, native status and provenance.
- **Workboard store:** persist source bindings, snapshots, pinned order and explicit preferences across server restarts. For the private single-user prototype, use a local SQLite store owned by that deployment. Before any shared deployment, bind access to authenticated users and enforce ownership on every operation; random board references are not an account boundary.
- **Panel session:** binds a conversation-visible panel reference to an explicitly chosen board. Avoid dependence on an undocumented ChatGPT conversation ID. Sharing a board between conversations is deliberate, not an automatic global default.
- **View state:** expansion, selection and scroll stay local to the panel, optionally restored with host widget state. Saved filters and board selection belong in durable storage if promised across sessions.
- **Outline node:** stable ID, source identity, kind, title, optional parent, source order, native/normalized status, optional assignee/priority/link, description, source revision and fetched time. Store dependency edges separately. Unknown fields remain unknown.
- **Pinned entry:** board ID, node/source reference or explicit custom prompt, position and chosen action. Source completion, user focus and message delivery are separate fields.
- **Updates:** use board/snapshot revisions and reject stale replacements. Paginate/chunk imports within the current HTTP payload limit; validate cycles, orphan references and duplicate IDs. Older refreshes must not overwrite newer ones.
- **Model context:** publish only active source, selected item, relevant ancestor scope, pins and board reference. Keep bulk listings out of repeated conversation context. Source refresh through the model still has a context cost; do not claim otherwise.

Proposed tool responsibilities: open/reopen board; import/replace a versioned source snapshot; list/query nodes; retrieve item details; pin/reorder/remove items; refresh an authorized source; supply contextual suggestions. Separate UI-only reads from model-facing operations. Every mutation validates board ownership, item identity and expected revision as applicable.

Retain send rejection, uncertain-delivery and duplicate protection from v0.2.0. Persist each dispatch attempt independently. If delivery is uncertain, do not retry automatically; keep browsing available and offer prompt inspection. Sending a prompt must not imply changing issue state, closing a ticket, committing code or publishing work.

## Delivery sequence and exit criteria

| Step | Deliverable | Exit criterion |
| --- | --- | --- |
| 1. Host proof | Dedicated panel entrypoint with a small fixture tree | Opens beside a real ChatGPT conversation; selection/context and one explicit send work; resizing is usable |
| 2. Shared outline + Markdown | Tree, detail view, source selector, Up next, Markdown parser/import, persistent private workboard | Preserves heading/task order and pins across reimport/restart; browsing sends no messages |
| 3. Connector-fed Linear + GitHub | Source normalization, filters, pagination/completeness indicators, explicit chat-driven fetch | A real scoped project/repository loads accurately; IDs/statuses and available hierarchy match source data |
| 4. Direct source access | Authorized Linear and GitHub adapters, tool-driven refresh/search/lazy loading | Refreshes source data without a model turn; revoked access and partial failures leave understandable state |
| 5. Daily-use validation | Selected-item prompt quality, keyboard/narrow layouts, stale state and concurrent update checks | All source modes usable in the target ChatGPT client; no cross-board leakage or duplicate sends |

Steps 1–3 establish an end-to-end usable version. Step 4 completes the independent refresh experience. Keep Suggestions and existing inline cards working throughout.

Tests should cover hierarchy/order parsing, duplicate titles, document replacement, missing/partial relationship data, source pagination, stale revision conflicts, persistence/ownership, pin reconciliation, and duplicate/uncertain delivery. Verify the real host separately from the protocol preview. Use synthetic fixtures for automated tests and a scoped read-only project/repository for live source verification.

## Scope defaults and decisions for implementation

Recommended defaults: read-only source browsing, user-curated Up next, conversation-scoped board selection, manual source refresh initially, preserved Markdown hierarchy, and no automatic execution or issue-status mutation. A mixed-source overview can be added later; cross-source pins already cover the main need without a crowded fourth source tree.

The main implementation decisions still open are the preferred first live Linear project/GitHub repository, where a linked Markdown document would live if snapshot import is insufficient, and whether independent provider access should move earlier than Step 3. None blocks building the panel and Markdown vertical slice.

## Evidence and limits

Inspected 2026-10-03: `server/app.mjs`, `server/index.mjs`, `web/card.html`, `web/card.mjs`, plugin metadata, suggestion skill, tests, README and validation record. Existing v0.2.0 has an ephemeral panel, three-step schema, no source fetcher, and no hierarchical model. Its ChatGPT inline send was previously recorded as verified; native panel placement was not. This planning task did not rerun live integration checks or modify implementation files. Existing uncommitted work was preserved.

Official documentation read 2026-10-03:

- [Plugin extensions](https://developers.openai.com/plugins/build/extensions): conversation panels, host surfaces and model/app context. Supports the panel approach; does not establish an after-turn hook or fixed geometry.
- [MCP UI and state](https://developers.openai.com/plugins/build/chatgpt-ui): UI messaging/context, source-of-truth separation and durable storage. Supports a custom hierarchical interface; the tree and adapters described here are proposed implementation work.

Next unresolved decision: validate the target host's right-side panel behavior, then implement the shared outline with a Markdown import as the first complete slice.
