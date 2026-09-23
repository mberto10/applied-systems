# Proposal: remember where the last check stopped

Status: design sketch for review, not implemented. September 22, 2026.

## Problem

Memory stores only item versions that entered a briefing. A new check therefore starts at the top of each surface again, re-reads and re-judges the items it rejected last time, and spends its inspection ceiling on them. On a busy surface, genuinely new items further down can fall outside the ceiling. `novelty_boundary` exists for "stop where earlier coverage begins", but it depends on the agent asserting `covered_range_verified`, and nothing stored lets it prove that, so it is rarely usable.

## Proposal

Keep one small **bookmark** per contract, account and surface: the newest item the last complete check inspected.

```json
{"thread_id": "source-1", "surface": "items", "identifier": "https://example.org/items/981",
 "occurred_at": "2026-09-22T07:14:00+00:00", "check": "run-id", "saved_at": "2026-09-22T07:20:11+00:00"}
```

- **Only for ordered surfaces.** A surface opts in with a new optional contract field, `collection.<surface>.order: "newest_first"`, set by setup or tune when the procedure documents chronological order. Algorithmic feeds never get a bookmark.
- **Handed out with the window.** `runtime.py window` returns the surface's bookmark. The agent reads from the top as today.
- **Verified by the runtime, not asserted.** When a capture includes the bookmarked identifier, or an item whose `occurred_at` is older than the bookmark's, the runtime itself accepts `novelty_boundary`. The surface is reported as `checked`: everything since the last check was read. Pinned items are excluded by the procedure, as today.
- **Advanced only after complete coverage.** At finalize, the bookmark moves to this check's newest inspected item only if the surface reached the old bookmark or a verified list end. If the check hit its item or time ceiling first, the old bookmark stays, so no gap can open between the two checks. The coverage line stays partial, as today.
- **Written on quiet checks too.** A check that selects nothing still advances the bookmark. This changes the README statement "a quiet run writes nothing".

## Storage and privacy

The bookmark is stored locally, per device, beside briefing memory: `~/.local/state/attention-diet/<contract>/bookmarks/<scope>.json`, mode 0600. The scope is hashed like memory filenames. It holds one identifier and one timestamp, never text. Supermemory contracts keep bookmarks locally too; a device without one simply reads from the top, as now.

## What changes

| Part | Change |
|---|---|
| Contract schema | optional `order` per collection surface (1.3 → 1.4, backward compatible) |
| `briefing_memory.py` | read and write bookmarks |
| `runtime.py` | return the bookmark with `window`; set the boundary when it is observed; advance at finalize |
| `surface_coverage.py` | accept the runtime-verified boundary |
| Run skill | one paragraph: stop at the bookmark, never skip ahead to it |
| Docs | data handling, README memory section, article sentence on memory if kept |

Tests: bookmark reached → checked and advanced; ceiling first → partial and not advanced; bookmark item deleted → timestamp fallback; pinned item above the bookmark; algorithmic surface ignored; quiet check advances.

## Expected effect

Repeat checks read roughly what is new since the last check instead of a fixed ceiling, so cost follows activity. "Checked" becomes the normal result for ordered surfaces.

## Decisions needed

1. Local only, or also stored with Supermemory for use across devices?
2. Opt-in per surface through `order`, as proposed, or inferred from the procedure text?
3. Is the quiet-check write acceptable, given the current "a quiet run writes nothing" promise?
