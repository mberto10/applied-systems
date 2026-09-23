# Optional repeated DOM extraction

Ordinary documented browser observations need no helper when they bound what is read. Near a ceiling, use this helper or an equivalent read that stops before extracting excess text; reading all cards and slicing the output is not bounded extraction. Load `helpers.browser_extract` only when a repeated, observed DOM structure makes it useful. Read its source once and define the function in CUA using the supported tool API. It uses no network or hidden state. Do not load the Codex memory adapter for this.

In the Claude Browser pane, send the helper's source followed by the call to `mcp__Claude_Browser__javascript_tool` and keep the returned JSON; the Codex steps below show the same flow with a persistent browser runtime.

Keep `scope`, `recipe` and `observation` in the browser runtime. Ground selectors in observed DOM, then:

```javascript
const previousCount = observation?.cards.length || 0;
observation = await ownedTab.playwright.evaluate(attentionDietExtract, {
  window: scope, recipe, previous: observation
});
nodeRepl.write({cards: observation.cards.slice(previousCount),
  more_available: observation.more_available, access_failure: observation.access_failure});
```

Start with `observation` undefined for a new ticket. A recipe supplies `card_selector`, `identifier: {selector, attribute: "href"}` and `basis: {sender: {selector}, text: {selector}}`. Optional `loading_selector`, `error_selector`, `more_selector` and `end_selector` must also be observed. `identifier.format: "x:post"` preserves that existing native-ID convention when reading X status links. Use `incoming_id` or absolute `occurred_at` only when the existing comparison method and observed DOM support them.

For another page within the same allowance, pass the preceding observation as `previous`; all prior cards consume the same limit and repeats are skipped. Check the deadline before navigation. The helper stops before excess cards, retains identified unreadable cards with `read_error`, and continues readable ones. An unidentified card or expired deadline stops extraction. Never substitute guessed text.

After judging relevance, project the retained observation inside CUA:

```javascript
const payload = {...observation, next_max_items: nextBatchSize,
  cards: observation.cards.map(card => eligibleIds.has(card.identifier) && card.basis
    ? card : {identifier: card.identifier, ...(card.read_error ? {read_error: card.read_error} : {})})};
nodeRepl.write(payload);
```

`eligibleIds` records your relevance decisions from the observed text; `nextBatchSize` respects remaining contract sublimits. Transfer this candidate-only payload to `runtime.py capture-window`. Keep the full original until capture succeeds. After success, add all observed IDs to `scope.seen_identifiers`, merge a non-null `next_window` into scope, and reset `observation`. Never drop identities or errors or rewrite candidate bases. If an ordinary tool response already exposed excess cards, use the main skill’s explicit overrun recovery with the original ticket and original order. Merely rendered cards that this helper did not read are not an overrun. Do not extract extra bodies just to inventory them. Only an exact recovery retry may reuse a consumed ticket. The documented CUA and command runtimes have no direct object channel; this reduces the handoff rather than claiming to eliminate it. Clear retained source text at cleanup.
