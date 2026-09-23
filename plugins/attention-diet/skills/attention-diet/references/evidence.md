# Evidence for stopping, overruns and changed items

Read when the [run skill](../SKILL.md) sends you here: before claiming that a surface ended, stalled, hit a source limit or reached earlier coverage; when a capture reports an overrun; or when a known item looks changed. The runtime enforces the structure; these rules say what counts as evidence.

## Availability and stopping

Set `more_available` to true, false or null. False needs observed `evidence` plus `exhaustion: {"kind":"explicit_end_marker","evidence":"Observed end marker."}`. Other supported kinds are `authoritative_total_matched` (also supply `total`, equal to the cumulative distinct inspected count) and `documented_connector_end` (state the observed result and documented semantics). Without structured evidence the runtime keeps availability unknown; a missing control or token is insufficient. `loading: true` proves no exhaustion.

Use `access_failure` for blockers, `retrieval_limit` for observed caps/restricted indexes, and `retrieval_stalled` with concrete no-progress evidence when settled retrieval attempts produce no new identities. For a stall keep availability null; it does not prove a source cap or exhaustion. Allow at most two settled no-progress attempts within the existing clock, reset after new identities, then move on. Keep a set of stable item identities across virtualized frames; DOM positions and repeated/older/pinned posts are not progress or exhaustion evidence.

A `novelty_boundary` needs `ordering_verified`, `covered_range_verified` and evidence; a known or pinned item alone proves nothing.

Identified unreadable cards remain counted and make coverage partial without blocking readable cards. Use `read_error` for attachment/video-only previews whose substance cannot be assessed; never infer their content. Keep caveats on readable but truncated selections. The renderer explains preview limitations and continuity; do not add a second equivalent withholding notice.

## Overruns

If a tool exposed more new cards than the ticket permits, retain all cards in observation order and resubmit that same ticket with `overrun: {"cause":"unbounded_observation","evidence":"Describe the actual excess observation."}` (or cause `atomic_tool_response` for an indivisible tool result). Recovery counts every identity but creates candidates only from the first permitted cards, consumes the ticket, and stops this surface. Exact recovery retries are idempotent. Never select the best cards from an oversized batch, request another allowance for the extras, or use direct capture to bypass a ticket.

## Changed captures of known items

A different capture of a known item does not establish a new event, even with the same fingerprint method. Private conversations can qualify through a new incoming ID under the established method or a source event later than the prior briefings of that item. Known public posts with changed captures remain `uncertain`: the runtime cannot yet verify edits, and a post ID or timestamp is not an override. Do not change identifiers or basis to make a withheld item qualify. Exact saved matches stay suppressed without rewriting old memory.
