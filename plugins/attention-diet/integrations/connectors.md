# Connected tools

Read when the plan lists a thread with `access.type: connector`. The host supplies authenticated tools; this plugin supplies a procedure, not an API client. The [run skill](../skills/attention-diet/SKILL.md) holds the shared rules, and the [contract guide](../docs/contract-guide.md#describing-a-source) covers configuring a connector thread.

## On every run

1. Resolve the exact `tool_namespace` and, when set, `connection_id`. Re-read the current tool signatures. Establish the account from connection metadata: a display name such as "personal" is not a stable account key, and a connection reference is not one either. Never search across connected services to find the account.
2. Identify the documented read operations for the configured `targets.<surface>.scope`. `account_actions: none` rules out sending, reacting, accepting, archiving, moving and changing labels or read state, even where the connector offers them. A tool name containing "read" says nothing about its effects. If safe previews are the only option, use them and disclose their limits.
3. Establish whether retrieval is a complete listing, a ranked search or an indexed subset, and inspect pagination and result caps. A query is a retrieval scope, not a substitute for the user's relevance rules. Never quietly narrow an inbox scan to unread items, add a date cutoff, or present a topic search as a check of the whole inbox.
4. Keep the thread's service, account and item identity conventions. Keep message and conversation IDs distinct. Use native incoming-event IDs or a documented, comparable source-text basis. An editable record needs a verified change basis; a stable record ID does not detect edits.

Fetch detail only inside the configured scope and limits, and label snippets and truncated bodies. An operation that necessarily returns private content outside the permitted scope is unsuitable: do not run it and filter afterwards. Linked pages and attachments need configured access and budget; their presence grants no browser fallback.

Interpret continuation tokens and result caps by the connector's documented semantics. An empty page that carries a token may need another page, and a missing token does not prove full coverage. For caps and restricted indexes, pass concrete `retrieval_limit` evidence and leave availability unknown when it is unknown.

Permission failures, expired connections and rate limits are access limits. Retry only a documented transient read failure while budget remains, and never repeat an identical failing call.

## Changing routes

When a source moves between a browser and a connector, keep its account keys and item identifiers, using evidence that they are equivalent. The runtime cannot discover aliases between browser links and connector IDs. If earlier inclusions might overlap and identity cannot be reconciled, hold those candidates out of the selection with one continuity notice. Never reset memory or resurface old content to seed a new format.

Do not disconnect the user's app, change its authorization or clear its authentication as cleanup.

For `more_available: false`, submit structured `exhaustion` of kind `documented_connector_end` with concrete evidence of the observed result and documented end semantics. A stopped or repeated page without that evidence is unknown availability; describe observed no-progress with `retrieval_stalled`.
