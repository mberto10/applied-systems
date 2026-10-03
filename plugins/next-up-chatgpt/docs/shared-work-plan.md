# Next up: a shared, live work plan

Date: 2026-10-03
Status: product draft. Max confirmed the intent below; the interaction rules, tool contracts and delivery sequence are proposals for discussion, not implemented features or adopted technical decisions.

Implementation update · 2026-10-03: v0.4.0 implements the board-owned progress loop (slice 1), including Plan/Now views, direct edits, result evidence, run acknowledgment and stale-result retention. See [tool workflow](progress-tools.md). The source bindings and native host run-control described below remain proposed.

## Intent

One orchestrator conversation is where Max directs the work. A persistent panel beside it shows the goal, the steps, their acceptance criteria, and progress. Codex can develop the plan, work against it, and record results through tools. Max can inspect and change that same plan while work continues.

A centrally configured source can be a Markdown document, a Linear project or GitHub issues. Different panel views show the same underlying work. The plan remains useful outside the conversation and survives long runs and context changes.

The product should answer four questions without reading the transcript:

1. What are we trying to achieve?
2. What is being worked on, and what will happen next?
3. Which acceptance criteria are satisfied, and what supports that assessment?
4. What changed, and has Codex incorporated my latest edit?

## Example experience

Max: “Here is the website goal. Develop the plan and work through it.”

Codex creates steps and explicit acceptance criteria in the selected plan. They immediately appear in the panel. Planning and execution follow the scope of Max's request: a request to draft does not start execution; an instruction to proceed does not require another routine approval click.

Codex starts “Improve onboarding.” The panel marks the step active and shows its current action. After implementing keyboard navigation and checking it, Codex records a result for that criterion. Its checkbox ticks, and its evidence is available on selection. A subjective criterion can remain “Needs your review” without preventing independent work elsewhere.

While Codex works, Max adds “The empty state explains how to add the first item.” The panel saves the new criterion and immediately shows “Plan changed · waiting for Codex to acknowledge.” At its next supported checkpoint Codex reads the change, acknowledges the new revision, and adjusts its work. The panel then says “Following your latest changes.”

If Max changes the criterion currently being checked, a late result against the old wording cannot complete the new criterion. The result is retained as history, and Codex receives a conflict that tells it what changed.

## One plan, several views

Keep the compact visual direction of the current panel. A task is a row, not a large card. Show acceptance criteria beneath the selected or expanded task, with evidence one click away. Preserve selection, expansion and scroll when progress arrives.

Separate **source selection** from **view selection**. Markdown, Linear and GitHub describe where work lives; Plan, Now and Changes describe how to look at it.

| View | Purpose | Contents |
| --- | --- | --- |
| Plan | Understand scope and completion | Goal → steps → acceptance criteria; dependencies and criterion counts |
| Now | Follow and steer the current run | Active step, current action, Up next, blockers and decisions needing Max |
| Changes | Understand revisions and results | Human and agent edits, evidence, source sync outcomes, acknowledged revision |

Initial UI: Plan and Now; Changes can begin as a small activity drawer. Search and filters remain available. Source/project selection belongs in a compact header rather than competing with the task hierarchy.

Illustrative panel, not a claim about native host support:

```text
Website refresh                 Plan ▾
plan.md · Following your latest changes

GOAL
New visitors can start without help.

▾ Improve onboarding          Active · 1/3
  ✓ Keyboard navigation works        Evidence ↗
  ○ Empty state explains the first action
  ◇ Welcome copy is clear            Your review
▸ Prepare release                       0/2

NOW
Checking the empty state
Last update 12 seconds ago

UP NEXT
Prepare release

Plan updated by Max · acknowledged by Codex
```

An elapsed time is the age of an update, not proof that the process is alive. A stale run shows “No recent update,” rather than indefinitely claiming that Codex is working.

## Completion has meaning

Model the goal, executable steps, and acceptance criteria separately. A nested subtask is work to perform; a criterion is a condition that must hold. Ordinary prose or an arbitrary source checkbox must not silently become an acceptance criterion.

| Object | Proposed states | Meaning |
| --- | --- | --- |
| Step | Planned, active, blocked, needs review, done, canceled | Work lifecycle; canceled does not count as completed |
| Criterion | Pending, satisfied, failed, needs review, waived | Whether the current criterion has been met |
| Run | Idle, working, waiting, paused, finished, interrupted, unknown | Agent activity, independent of plan completion |
| Source sync | Current, pending, conflict, unavailable | Whether the displayed state agrees with its owning source |

Each result records the criterion ID and revision, actor, time, method and evidence. Methods can include an automated check, agent inspection or human judgment. A green tick means a recorded satisfaction result, not that every result was independently verified. Display who assessed it and how. Codex can record inspectable evidence; the store can validate its shape and revision but cannot prove the assertion merely because a tool was called.

Proposed default: every required criterion must be satisfied, and required child steps must be done, before a step can become done. A waiver needs an explicit human decision and stays visible. Criteria requiring human review cannot be satisfied on Max's behalf. Reopening or materially changing a criterion invalidates the relevant completion and prompts reassessment; old evidence remains in history.

Show “2 of 4 criteria satisfied,” not a percentage of effort. Do not aggregate incomplete provider listings into a project-wide completion claim. A task with no criteria can be tracked, but cannot claim acceptance has been checked; completing it requires an explicit result note.

## Central source and ownership

“Central” means one durable place to configure the workboard's sources and their authority. It does not mean keeping several independently editable copies and hoping they converge.

Proposed first version: one primary source per workboard. Later, one board may combine several sources, but each work item/field still has exactly one owner. Cross-source links connect items; they do not create duplicate tasks to maintain.

| Binding | Owns | Write behavior |
| --- | --- | --- |
| Linked Markdown | Goal, step/criterion wording, order and completion markers | Targeted edits to the configured file, with revision checks |
| Linear / GitHub | Native issue title, body, relationships and native issue state | Through an adapter with explicit field/state mapping and write capability |
| Workboard store | Run activity, evidence history, pins, acknowledgments, sync journal | Local durable records referring to stable source IDs |

Where a provider cannot represent the richer criterion model, choose visibly between a managed checklist section in its issue body and a board-owned criterion overlay. The overlay is labeled “Criteria managed in Next up.” Do not pretend it is provider-native data. Existing unstructured criteria can be proposed for conversion with a reviewable diff.

Source binding records scope, stable identity, read/write capabilities, mapping and latest observed revision. Read-only sources remain useful, but any local progress is explicitly separate from native issue state. Marking a local criterion satisfied does not silently close a remote issue. Once source write-back and completion mapping have been configured and authorized, routine matching updates should not demand repeated confirmation.

Provider writes use conditional updates when supported. If an adapter cannot safely detect conflicting edits, do not enable unattended body rewriting. Connector capabilities and native status mappings need investigation before implementation; this draft does not assume those APIs are available.

## Proposed Markdown format

Start with one readable, linked local file and a small explicit convention. Stable IDs survive changes in wording, order and filename. The current imported snapshot can remain supported, but a snapshot is not a live file binding.

```markdown
# Website refresh <!-- next-up:website -->

## Goal
New visitors can start without help.

## Steps
- [ ] Improve onboarding <!-- next-up:onboarding -->
  - Acceptance criteria:
    - [ ] Keyboard navigation works <!-- next-up:keyboard -->
    - [ ] Empty state explains the first action <!-- next-up:empty -->
    - [ ] Welcome copy is clear <!-- next-up:copy -->
- [ ] Prepare release <!-- next-up:release -->
  - Acceptance criteria:
    - [ ] Release checks pass <!-- next-up:checks -->
```

This is a proposed new schema, not a format already understood by the existing parser. Rich state, reviewer requirements, evidence and timestamps can live in a sidecar/store keyed by these IDs; unchecked Markdown alone does not distinguish pending, failed or needs review. The panel must expose those distinctions. An external manual tick is attributed to an external source edit with no check evidence, rather than invented test results; human-only criteria still require explicit human attribution.

Preserve unrelated prose and formatting through targeted source edits. Generate IDs when creating a new plan; show the ID insertion diff when upgrading an existing document. Duplicate or removed IDs create visible reconciliation errors. Renaming a document must not change its source identity. Invalid edits retain the last valid view with an error; they must not silently erase the plan.

## Tools for the orchestrator

Proposed responsibilities, not final API names. Use narrow operations rather than repeatedly replacing the entire plan. Both UI and agent mutations use the same validation path.

| Tool | Purpose | Essential safeguards |
| --- | --- | --- |
| `read_work_plan` | Read selected scope, revisions and changes since a cursor | Bounded results; identify partial scope |
| `apply_plan_patch` | Create or edit steps, criteria and dependencies | Stable IDs, expected revisions, explicit patch and origin |
| `record_criterion_result` | Satisfy, fail or request review of a criterion | Exact criterion revision, evidence/method and actor |
| `set_step_state` | Start, block, reopen or complete work | Enforce criterion/dependency rules; completion note |
| `report_work_activity` | Report current action, blocker or heartbeat | Run reference, timestamp; never implies completion |
| `acknowledge_plan_changes` | Record which revision the run has adopted | Explicit scope/revision; separate receipt from action |
| `read_work_events` | Resume from recent changes and results | Durable cursor and bounded history |

All mutations carry an operation ID for safe retry and the expected relevant revisions. The server assigns actor identity from the session/run, rather than accepting an arbitrary claim that an agent is Max. Return the committed change, new revisions and any source-sync outcome. Reject completion against stale criteria and return a useful diff; unrelated edits should not force a whole-board conflict.

Batch related criterion results when useful. Publish at meaningful checkpoints, not every keystroke. Keep the model's routine reads scoped to the active step, dependencies and changes; the panel can browse the full stored plan without inserting it into every prompt.

## Editing while Codex runs

1. Max edits in the panel or the bound source. The system validates and records a new revision, with the change immediately visible.
2. The run sees an outstanding change indicator. Where the host supports a verified interruption/notification mechanism, use it. Otherwise the agent reads changes at explicit checkpoints: before starting a step, before a consequential action, and before reporting completion.
3. Codex acknowledges the revision it has actually read and records whether it adjusted the plan, needs clarification or is finishing an unaffected action.
4. Results are committed only against the relevant current revisions. Conflicting results remain historical evidence without ticking the changed criterion.

Do not imply a file watcher can interrupt a model turn or undo an operation already in flight. A pause request is “Pause requested” until acknowledged; the plugin cannot guarantee immediate stop without a host execution-control capability. Changes that invalidate active work make that work visibly stale. Nonconflicting work may continue within the authorized scope.

Example conflict: Max changes “Check desktop keyboard navigation” to “Check desktop and mobile keyboard navigation.” A desktop-only result arrives with the older revision. The tool returns `criterion_changed`, preserves that result, and leaves the revised criterion incomplete. Codex can reuse the desktop evidence and perform the missing check.

Use a durable pending-write journal for source operations. A timeout means “Outcome unknown,” not “Failed, retry blindly.” Reconcile with the source before retrying. Do not show “Synced” until the source change is confirmed. File and database updates need crash recovery because they are not one atomic transaction.

## One orchestrator conversation

Bind the board deliberately to the controlling run/conversation. Its responsibility is to maintain the plan, decide the next eligible work, incorporate changes, and keep progress legible. Reopening the panel does not launch another run. Restarting after interruption resumes from durable plan state and evidence, not reconstructed transcript guesses.

Multiple workers are an optional later capability. If explicitly enabled, assign bounded tasks with their plan revisions. Workers submit results; the orchestrator resolves conflicting proposals and shared scope. A lease/claim can prevent accidental duplicate assignment, but an expired lease does not prove a worker stopped. The first slice needs only one active orchestrator and concurrent human edits.

This plan does not assume a ChatGPT panel can run inside Codex unchanged. Separate the shared store/tools from host-specific panel and execution adapters. Validate native panel placement, model tool access and progress delivery in the intended Codex client; keep the browser preview labeled as a preview until then.

## Build sequence and observable acceptance criteria

| Slice | Deliverable | Acceptance criteria |
| --- | --- | --- |
| 1. Live progress loop | Structured plan + criterion/result tools + panel updates in the local preview | Agent calls create a plan and tick an exact criterion; evidence is inspectable; invalid/stale completion is rejected; restart retains results |
| 2. Shared Markdown source | Bind one local file, panel editing, change detection and targeted write-back | External edit appears; human/agent races preserve both changes or expose a conflict; IDs survive rename/reorder; malformed input does not erase work; crash recovery reconciles pending writes |
| 3. Orchestrator in the target host | One real Codex run using the tools, visible panel and revision checkpoints | During real work Max adds a criterion; Codex acknowledges and incorporates it; stale activity and pause acknowledgment are honest; interrupted run resumes without duplicate completion |
| 4. Provider integration | One adapter end to end, then the other | Real source IDs and hierarchy preserved; write permissions and mappings explicit; source conflicts and unknown outcomes visible; no silent remote issue closure |

Run an early host feasibility spike before substantial host-specific UI work; lack of native panel support must be reported, with a browser companion as an explicit fallback. The shared tools remain valuable independently of that surface.

The demonstration should be the product's own development plan: create three steps, complete a criterion with evidence, add another criterion while work is active, reject an old result, acknowledge the change, complete the revised task, and restart without losing history. This is stronger proof than a static checklist animation.

## Decisions to refine next

Recommended starting point: local linked Markdown, one orchestrator, explicit criteria, Plan/Now views and evidence-backed progress. Preserve the current compact interface; add expressiveness through state and drill-down, not more permanently visible controls.

Open decisions:

- Target host: Codex desktop first, ChatGPT first, or shared tools with a companion panel first? The latest intent centers on Codex; recommend Codex as the first real-run validation target.
- Completion policy: recommend agent-assessed completion by default, with per-criterion human review only where specified.
- Source policy: recommend one primary source per board initially. Multiple sources can follow once identity and write-back are reliable.
- Provider order: choose the first real project/repository when the Markdown workflow proves useful.

## Relationship to the current build

Inspected locally on 2026-10-03: `server/boards.mjs`, `server/panel-tools.mjs`, the README and the original panel plan. Current v0.3.1 has persistent boards, source snapshots, revision checks and cross-source pins. It does not have typed acceptance criteria, evidence records, agent completion tools, live file bindings, provider write-back or a run-control protocol. Its model-facing read returns the board, so bounded delta reads would be new work too. Native placement remains unverified.

This draft extends the [original work-panel plan](work-panel-plan.md). Its proposed editable plan replaces that plan's read-only-source default only in the future implementation; current behavior and claims remain unchanged. No code or external source was changed for this drafting task.

Next unresolved decision: settle the first source/host combination, then refine slice 1 into a concrete data contract and interaction prototype.
