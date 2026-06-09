# Module: `context.js`

> Context management + **token accounting** (`SandpieTokens`): per-conversation and
> weekly usage, surfaced in the Context sidebar section.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | `window.SandpieTokens` |
| **Sidebar section** | `contextSection` (with a usage badge) |
| **Status dot** | none |

## Public surface
`SandpieTokens` — conversation + weekly token accounting; backs **`Sandpie.tokens`**.
Real counts come from the provider's `usage` object; falls back to a chars/4
estimate. The per-provider context-window denominator is set in the provider modal.
Exposes `notify()` (re-render) among others.

## Events
- **Emits:** none.
- **Listens:** **`tokens:record`** (`{convId, usage}`) — accumulate usage for the
  conversation + the rolling weekly total.

## DOM owned
`#contextSection` (and updates its summary badge via `SandpieMenu.updateBadge`).

## Depends on
- **Host:** `Sandpie.events`, `SandpieMenu`, shared state (`activeConvId`,
  `convStreams`), `localStorage` (weekly totals).

## Notes / gotchas
- `SandpieTokens` lives here (not in a separate `tokens.js`); conversations.js calls
  `SandpieTokens.notify()` when the active conversation changes.

---
_Surface verified from source; for internal implementation see `modules/context.js`._
