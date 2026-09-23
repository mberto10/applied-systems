// Evaluate this function in the documented read-only page scope. All selectors
// must come from an observed DOM; this file contains no service routing/selectors.
(function attentionDietExtract({window: scope, recipe, previous}) {
  if (!scope || !Number.isInteger(scope.limit) || scope.limit < 0 || Date.now() >= scope.deadline_ms)
    throw new Error('Observation window is missing, invalid or expired');
  if (!recipe || !recipe.identifier || !recipe.basis ||
      !(recipe.basis.incoming_id || recipe.basis.sender && recipe.basis.text))
    throw new Error('Recipe needs an observed identity and the existing complete fingerprint basis');
  if (previous && (previous.ticket !== scope.ticket || !Array.isArray(previous.cards) || previous.cards.length > scope.limit))
    throw new Error('Previous observations belong to another window or exceed its allowance');
  const key = value => {
    const opaque = /^x:post:(\d+)$/.exec(value);
    if (opaque) return 'x-status:' + opaque[1];
    try {
      const u = new URL(value);
      const match = /^\/[^/]+\/status\/(\d+)(?:\/(?:analytics|photo\/\d+|video\/\d+))?\/?$/.exec(u.pathname);
      if (u.protocol === 'https:' && ['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'].includes(u.hostname) && match)
        return 'x-status:' + match[1];
    } catch (_) { /* Native IDs need not be URLs. */ }
    return value;
  };
  const visible = element => {
    if (!element || element.getClientRects().length === 0) return false;
    for (let current = element; current; current = current.parentElement) {
      const style = getComputedStyle(current);
      if (style.display === 'none' || ['hidden', 'collapse'].includes(style.visibility) || style.opacity === '0') return false;
    }
    return true;
  };
  const exists = selector => !!selector && [...document.querySelectorAll(selector)].some(visible);
  const read = (card, field) => {
    const elements = field.selector ? [...card.querySelectorAll(field.selector)].filter(visible) : [card];
    if (elements.length !== 1) throw new Error('Observed field must resolve to one visible element');
    const el = elements[0];
    const value = field.attribute === 'href' ? el.href : field.attribute ? el.getAttribute(field.attribute) : el.innerText;
    if (typeof value !== 'string' || !value.trim()) throw new Error('Missing observed identity/text');
    return value; // Never trim, summarize or append counters to fingerprint text.
  };
  // Resolve marker selectors before body reads, so a bad selector cannot discard
  // earlier observations. This entire extraction is synchronous/read-only.
  const markers = {loading: exists(recipe.loading_selector), error: exists(recipe.error_selector),
                   more: exists(recipe.more_selector), end: exists(recipe.end_selector)};
  const result = {...previous, ticket: scope.ticket, cards: [...(previous?.cards || [])],
    more_available: null, loading: markers.loading, evidence: ''};
  delete result.exhaustion;
  if (markers.error) result.access_failure = 'Observed source error state.';
  if (result.access_failure || result.loading || scope.limit === 0) return result;
  const seen = new Set([...scope.seen_identifiers.map(key), ...result.cards.map(c => key(c.identifier))]);
  let bounded = false;
  for (const card of document.querySelectorAll(recipe.card_selector)) {
    if (!visible(card)) continue;
    // Stop before reading an additional identity or body, not after slicing output.
    if (result.cards.length >= scope.limit) { bounded = true; break; }
    let identifier;
    if (Date.now() >= scope.deadline_ms) {
      result.access_failure = 'Observation window expired during extraction.';
      return result;
    }
    try {
      identifier = read(card, recipe.identifier);
      const identity = key(identifier.trim());
      if (seen.has(identity)) continue;
      if (recipe.identifier.format === 'x:post') {
        if (!/^x-status:\d+$/.test(identity)) throw new Error('Observed link is not a post identity');
        identifier = 'x:post:' + identity.slice('x-status:'.length);
      } else if (recipe.identifier.format && recipe.identifier.format !== 'as_observed') {
        throw new Error('Unsupported identity format');
      }
      seen.add(identity);
    } catch (_) {
      // Without an identity the inspected count cannot be established; stop here.
      result.access_failure = 'A card could not be identified; reported identity counts are a lower bound.';
      return result;
    }
    try {
      const basis = {};
      for (const [name, field] of Object.entries(recipe.basis)) {
        if (Date.now() >= scope.deadline_ms) throw new Error('Observation window expired during extraction');
        basis[name] = read(card, field);
      }
      result.cards.push({identifier, basis});
    } catch (_) {
      result.cards.push({identifier, read_error: 'An identified card had missing or ambiguous text and was withheld.'});
      if (Date.now() >= scope.deadline_ms) {
        result.access_failure = 'Observation window expired during extraction.';
        return result;
      }
      // A malformed card does not prevent inspecting other identified cards.
    }
  }
  if (bounded || markers.more) result.more_available = true;
  else if (markers.end) {
    result.more_available = false;
    result.evidence = 'Observed explicit end marker in the configured scope.';
    result.exhaustion = {kind: 'explicit_end_marker', evidence: result.evidence};
  }
  // A missing next control or an empty card list never establishes exhaustion.
  return result;
})
