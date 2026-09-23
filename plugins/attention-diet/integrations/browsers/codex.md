# Codex in-app browser

Use only when the plan resolves `codex_in_app`. The [run skill](../../skills/attention-diet/SKILL.md) holds the rules shared by every browser, including bounded reading. The in-app browser comes from the Codex app's bundled Browser plugin; if its runtime is missing, as in some CLI or editor sessions, report the dependency and do not substitute desktop automation.

## The browser

In the browser runtime, read the packaged documentation once, then select the in-app browser explicitly by its type:

```javascript
const browser = await agent.browsers.get("iab");
const tab = await browser.tabs.new();
await tab.goto(entryUrl);
```

Never use `agent.browsers.getDefault()` or `getForUrl()`, and never a browser whose type is `extension` or `cdp`: those drive the user's everyday Chrome and are not isolated. Reuse one task-owned tab per service. Keep it in the background; to let the user sign in, show it with `await (await browser.capabilities.get("visibility")).set(true)`. The installed documentation is authoritative for syntax (checked against Browser plugin 26.915); these rules still apply if it changes.

Agent-created tabs close when the turn ends. If you end the turn to wait for a sign-in, call `await tab.markHandoff()` first so the tab survives; the in-app browser keeps the sign-in for later runs.

## Reading

After navigation, wait within the allowance for an observed content locator or an explicit empty/error state. `tab.playwright.domSnapshot()` returns the whole DOM: use it to learn a page's structure, not to read a list longer than the current window, because every card it exposes counts as inspected. For lists, run the [bounded extraction helper](../../skills/attention-diet/references/browser-extraction.md) through `tab.playwright.evaluate`, which runs in a read-only page scope. Use screenshots only when text is insufficient. Never read hidden application state or guess selectors or endpoints.

The browser and command tools have separate runtimes. Retain observations in the browser runtime and emit only identifiers plus eligible candidate bases for capture.

## Finish

Close task-owned tabs with `await tab.close()`, preserving sign-in. Do not mark them deliverable.
