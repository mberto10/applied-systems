# Direct capture

Use this alternative for connector results or observations already in batch form. Collection rules live in [the run skill](../SKILL.md); this file only specifies the input shape.

`runtime.py capture --run RUN --input -` accepts:

```json
{"account_key":"service:verified-account",
 "items":[{"ref":"c1","thread_id":"T","surface":"S","identifier":"eligible-id",
           "basis":{"sender":"Observed sender","text":"Exact observed text"}}],
 "surfaces":[{"thread_id":"T","surface":"S","identifiers":["eligible-id","rejected-id"],
              "more_available":true,"evidence":"Observed pagination in the configured scope."}]}
```

Give eligible candidates unique references. Send all inspected identifiers, including rejected and unreadable items; the runtime deduplicates and counts them. Use `inspection_errors` on a surface for observed unreadable-card explanations. The other availability/read-state fields and novelty results are the same as bounded capture. The runtime measures overruns and excludes overflow identities from candidates in observation order; obtain an allowance before a bounded read, or use the preceding coverage result's remaining limits. Never slice observations after exceeding a ceiling.

Direct capture rejects a surface with an outstanding window: submit through `capture-window`, using explicit overrun recovery when needed. Direct batches commit atomically. After an overrun, additional observations can be accounted for but cannot become candidates or reopen that surface. Use the main skill’s structured `exhaustion` evidence for an end claim and `retrieval_stalled` for observed lack of progress. Include `unreadable_identifiers` alongside `inspection_errors` when individual unreadable identities are known.
