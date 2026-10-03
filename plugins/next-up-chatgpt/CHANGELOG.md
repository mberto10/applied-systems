# Changelog

## 0.4.1 · 2026-10-03

- Publishable marketplace package for the shared-plan prototype, with updated discovery text and an explicit upgrade/real-plugin test guide.
- New version and panel resource URI so existing local 0.4.0 installations can distinguish the update.
- Include a synthetic preview image; omit private live-host screenshots.

## 0.4.0 · 2026-10-03

- Board-owned shared plans with goals, steps, typed acceptance criteria and inspectable evidence.
- Plan / Now / Sources views; direct plan edits, run acknowledgment and recent history.
- Seven MCP tools for scoped progress, result recording, activity and durable event reads.
- Atomic writes, operation deduplication, stale-result retention, completion gates and independent definition revisions.
- Local protocol demo with synthetic progress. Live file/provider write-back and native Codex placement remain out of scope for this slice.

## 0.3.1 · 2026-10-03

- Redesign after author feedback: compact source switcher, tighter outline rows, restrained controls, status icons, and an inline personal queue.
- Dedicated compact panel foundation, preserving the original starter asset.
- Human-readable default action prompts; selected-item references remain in model context.
- Conversation-side preview with test controls behind disclosure.


## 0.3.0 · 2026-10-03

- Dedicated work panel with Markdown, Linear, GitHub and Suggestions modes.
- Hierarchical browsing, search/status/assignee filters, source details and editable action prompts.
- Cross-source Up next queue with reordering and preserved missing references.
- Durable private SQLite workboards with optimistic revisions and persistent delivery protection.
- Structural Markdown imports, verified issue-snapshot schema and explicit completeness/hierarchy limits.
- Browser preview backed by the real MCP server, with isolated sample source controls.
- Direct provider refresh and native ChatGPT right-side placement remain unverified/unimplemented as documented.


## 0.2.0 · 2026-10-02

- Conversation entrypoint “Suggested next steps,” with an empty state and explicit request/refresh.
- Isolated ephemeral panel state and in-place model updates through panel context.
- Preserved inline cards, prompt editing, and duplicate-send protection.
- Eight integration checks pass, including panel isolation and entrypoint metadata.

## 0.1.0 · 2026-10-02

- Stateless MCP renderer for up to three contextual continuation buttons.
- Prompt preview/edit, dismissal, and explicit send with duplicate protection.
- Skill for conversation suggestions and verified Linear context through existing tools.
- Local protocol preview, tests, and private ChatGPT connection instructions.
