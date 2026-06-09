# Module: `providers.js`

> AI provider configuration — endpoints, API keys, models, and per-provider
> limits — with a provider modal and chip menu.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | `window.SandpieProviders` |
| **Sidebar section** | `aiSection` |
| **Status dot** | `aiDot` (lit when an endpoint + key are set) |

## Public surface
`SandpieProviders`: `getActive`, `load`, `apply`, `list`, `activeId`,
`openModal` / `closeModal` / `saveModal`, `showMenu` / `hideMenu`,
`editFromMenu` / `duplicateFromMenu` / `deleteFromMenu`, `updateHint`, `refreshDot`.

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
`#aiSection`, the provider modal `#providerModal` (+ its `#modal*` inputs), the chip
context menu `#chipContextMenu`, and the `#aiDot` status dot. Reads/writes the
hidden host inputs `#endpoint`, `#model`, `#apiKey`, `#proxyUrl` (which
`core.js`'s `api()` and conversations.js's `buildAgentConfig` read).

## Depends on
- **Host:** `SandpieMenu`, `$`.

## Notes / gotchas
- The provider modal + chip-menu markup is currently static in the host page
  (a candidate to inject from here so the module owns its full DOM).
- The active provider's `maxTokens` / `temperature` / context window feed
  `buildAgentConfig` in conversations.js.

---
_Surface verified from source; for internal implementation see `modules/providers.js`._
