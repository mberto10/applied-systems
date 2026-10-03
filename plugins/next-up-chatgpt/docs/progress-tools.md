# Shared plan tools · v0.4.0

Local private prototype, 2026-10-03. These tools store a plan on a workboard. They do not mutate imported snapshots, files or provider issues. The panel is a client of the same MCP server; no native Codex panel or execution-control integration is claimed.

## Working loop

1. Open/reopen a board with `open_next_steps_panel`, retaining its `panel_id`.
2. `read_work_plan` returns the plan and the ten latest events. An empty board has revision 0 and definitionRevision 0. Limits: 50 steps, 200 criteria. `read_work_events` provides bounded, chronological history via a cursor; continue while `has_more`.
3. `apply_plan_patch` takes `panel_id`, a fresh UUID `operation_id`, `expected_definition_revision`, and `patches`. Supported patches: goal, add_step, edit_step, add_criterion, edit_criterion. IDs must be stable and unique across steps and criteria. No removal, dependencies or nested steps yet.
4. Read the result; start a controlling run with `acknowledge_plan_changes`, using `run_id` and the exact `expected_definition_revision` actually read. Follow the user's scope: creating a plan or acknowledging it does not authorize execution.
5. Use `report_work_activity` for meaningful actions/checkpoints. It reports activity; it cannot start or stop a process. The UI labels reports older than two minutes as stale.
6. Record a result with `record_criterion_result`, passing `criterion_id`, `expected_criterion_revision`, `outcome` (satisfied/failed/needs_review), `method` (automated_check/agent_inspection) and concrete `evidence`. Never invent verification. Link paths/commands/results in the evidence text as useful; the UI renders it as plain text.
7. `set_step_state` takes the current plan `expected_revision`, run ID, step ID, state and note. Done requires all criteria satisfied. A step without criteria requires a completion note, but makes no claim about acceptance checks.
8. Before further work or completion, read/acknowledge new definition revisions. An active run cannot quietly be replaced by a second run. Finish, interrupt or pause the first before assigning a different ID. This is coordination bookkeeping, not authenticated worker ownership or a stop guarantee.

Example `patches` value for a new plan:

```json
[
  { "type": "goal", "text": "New visitors can start without help." },
  { "type": "add_step", "id": "onboarding", "title": "Improve onboarding", "criteria": [
    { "id": "keyboard", "title": "Keyboard navigation works" },
    { "id": "empty-state", "title": "Empty state explains the first action" }
  ] }
]
```

## Concurrent edits and retry

Definition revision changes only when the plan is edited; plan revision also changes on progress/activity. An open editor therefore tolerates activity updates. Concurrent definition edits reject the old patch atomically, preserving the editor's text. The user can inspect/reconcile and reopen it against the new revision. There is no automatic merge of conflicting wording.

Editing a criterion invalidates its result and increments its revision. Editing a step invalidates its criteria. Changing the goal invalidates all acceptance results. Adding a criterion reopens a completed parent step. Historical evidence stays in the event log.

A result for an old criterion revision commits only a history event and returns `outcome.status = criterion_changed`, with the current criterion revision. It does not satisfy the new criterion. This is an explicit outcome, not a transport error. Completion against an unacknowledged plan fails.

All mutations require an operation UUID. Retry an uncertain request with exactly the same ID and arguments. The server returns `replayed: true` with the original operation outcome and current plan, without another event. Reusing an ID with different arguments fails. UI saves retain their operation for a retry; changing the text after an uncertain save requires inspecting the current plan first.

Evidence and actors are not verified identity attestations: this private deployment labels operations as tool calls. A caller-supplied run ID is a coordination reference. Human-review criteria cannot be marked satisfied by the result tool; a trusted human-approval path remains future work. Do not remove a human-review requirement merely to complete a task.

## Boundaries and storage

The existing private SQLite database now also holds work_plans, work_events and work_operations. Startup creates the new tables without rewriting existing boards. Plan state, evidence, history and deduplication survive restart. History is paginated but not pruned yet. Keep evidence relevant and avoid placing secrets in it. The shared-plan view polls every three seconds while visible; it is not a provider refresh or an agent wakeup.

Remaining work: linked Markdown with safe write-back/recovery, source ownership/mapping, provider adapters, native host panel/tool installation verification, trusted human approval, removal/dependencies/nested steps, and execution interruption. No automatic source synchronization or claimed process health.
