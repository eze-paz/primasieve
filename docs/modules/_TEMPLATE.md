# Module: `<name>.js`

> One-sentence purpose.

| | |
|---|---|
| **Load type** | `classic` \| `type="module"` (deferred) \| `classic, defer` |
| **Global namespace** | `window.SandpieX` / bare globals / none |
| **Sidebar section** | `xSection` (via `SandpieMenu.add`) — or _none_ |
| **Status dot** | `xDot` — or _none_ |

## Public surface
What other code may call — the namespace methods and/or `window.*` functions this
module exposes.

## Events
- **Emits:** `event:name` (payload) — when / why.
- **Listens:** `event:name` — what it does in response.

## DOM owned
Elements this module creates, injects, or manages.

## Depends on
- **Host:** `Sandpie.x`, `SandpieMenu`, shared state (`activeConvId`, …)
- **Other modules (runtime, optional):** `SandpieY.method()` …

## Notes / gotchas
Timing, ordering, or non-obvious behaviour worth knowing.

---
_Surface verified from source; for internal implementation see `modules/<name>.js`._
