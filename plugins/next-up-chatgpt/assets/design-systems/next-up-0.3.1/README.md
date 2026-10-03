# Next up compact panel foundation · 0.3.1

Project-local authored fork of the neutral starter 0.2.0, introduced on 2026-10-03 in response to Max rejecting the initial interface. This is a proposed product-specific design correction, not a saved personal preference or a claimed approved shared brand system. The original starter asset remains unchanged.

## Guidance

Use a compact desktop utility-panel composition: one small heading, a source switcher, personal next actions, and the source outline. Content leads; import forms and diagnostics use disclosure. Reserve accent for selection/focus and primary actions. Keep row metadata secondary. No decorative cards around every task.

## API

The starter's existing `cd-*` primitives and semantic tokens remain available. Apply `class="cd-system" data-density="compact"` once; `data-theme="light|dark"` remains host-controlled. The compact variant owns a 13px body, 11px metadata, 16px heading, 32px desktop controls, neutral secondary/quiet buttons, and the local violet focus/action accent. Fine-pointer icon targets must be at least 28px; coarse-pointer controls use 44px. Page composition consumes these tokens through `cd-custom-*` classes without redefining the foundation.

Native controls and disclosures own keyboard behavior. Source choices are ordinary buttons with `aria-pressed`, not an ARIA tab widget. Preserve visible focus, readable text, explicit action labels, and screen-reader names for icon-only controls. Hide neither errors nor unavailable-host explanations.

## Checks

Load only this foundation in the panel; keep inline cards on their existing independent stylesheet. Check 320px and 400px widths, dark/light themes, keyboard disclosure and selection, source switching, item details, and sending. Preserve the existing 13 protocol/data tests. Visual approval remains with the user.
