# Changelog

## 0.1.0 · 2026-10-02

First public release.

- Up to three next prompts above the prompt box when a turn ends, from the conversation, open GitHub issues and pull requests (`gh`) and your open Linear issues (Linear MCP server).
- Modes: `mixed`, `linear`, `github` and `conversation`, set in the settings or with `/next mode`.
- A light ranker by default: a small model reads the last exchange and a capped list of open items, never the transcript. A `fork` ranker over the cached transcript is optional and falls back to the light one.
- Type a number and Enter to send a step, or click it to edit it first; `/next`, `/next refresh` and `/next sources`, which names why a source returned nothing.
- A one-time reminder when the Linear tool is not allowed in your permissions.
