# Supermemory setup

Used by the `setup` and `tune` skills, not during a run. See [briefing memory](README.md) for what is stored and the [run procedure](supermemory.md) for retrieval and saving.

## Required operations

Discover tool names in the exact provider namespace first, then inspect only these definitions. Do not print a cross-provider tool catalog. A connector that offers only semantic recall is insufficient.

| Operation | Tool |
|---|---|
| Resolve an accessible space | `list_spaces` |
| List original documents with pagination | `list_documents` |
| Retrieve an original document with its processing status | `get_document` |
| Save an exact artifact | `add_memory` with `action: "save"` |

Map equivalent tools only when their documented capabilities match. A successful connection alone does not show that records can be stored and retrieved. Where account inspection is available, use it to confirm identity and write access.

## Configure the contract

Resolve the user's chosen space with `list_spaces` and store its returned key, not its display name:

```json
"memory_context": {
  "provider": "supermemory",
  "space": "<returned-space-key>",
  "purpose": "avoid_repeating_previously_briefed_items",
  "on_unavailable": "continue_with_notice"
}
```

Remove the local `directory` field, keep the contract ID and install the change as a normal revision. A dedicated space keeps retrieval small. Use a space the user selected; never invent a key or assume the connector can create one. If the setup cannot be verified, report what is missing instead of installing a guess or choosing local storage.

## Testing and removal

Test a save and retrieve round trip with a clearly labelled synthetic record under its own contract ID and account key, outside real briefing history. Do not upload source content to test access.

`add_memory(action: "forget")` does not reliably delete an original document: it can match extracted memories while the stored artifact remains. Remove or correct a record through a documented document-management operation or the service's own interface, and verify against the document listing. If no such operation exists, tell the user which artifact remains. Never widen a forget request to unrelated memories.
