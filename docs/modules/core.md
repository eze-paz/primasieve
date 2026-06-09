# Module: `core.js`

> The host layer: the `Sandpie` contract, the `SandpieMenu` sidebar registry, the
> shared conversation state, URL routing, and page-chrome glue. Loaded first.

| | |
|---|---|
| **Load type** | `classic` — **first** script after the CDN libs |
| **Global namespace** | `window.Sandpie`, `window.SandpieMenu`, and bare globals `$`, `api`, `messages`, `convStreams`, `convLastViewed`, `activeConvId`, `isLocalhost` |
| **Sidebar section** | none (it *provides* `SandpieMenu`) |
| **Status dot** | none |

## Public surface
- **`window.Sandpie`** — the host contract (see [ARCHITECTURE §2](../ARCHITECTURE.md#2-the-host-contract--windowsandpie)).
- **`window.SandpieMenu`** — `add` / `remove` / `get` / `updateBadge` / `list` (see [§5](../ARCHITECTURE.md#5-sidebar--sandpiemenu)).
- **`$(id)`** — `document.getElementById`.
- **`api(url)`** — routes an API URL through the remote proxy, local `/proxy/`, or direct.
- **Shared state** — `messages`, `convStreams`, `convLastViewed`, `activeConvId` (read by several modules; reassigned by conversations.js).

## Events
- **Emits:** `sync:provider-changed` (when `registerSyncProvider` installs/clears a provider).
- **Listens:** none.

## DOM owned
- Inserts registered sections into `<aside>` (via `SandpieMenu`).
- Suppresses the browser's default PWA install prompt.
- Fills the sidebar footer `#versionDisplay` from `version.txt` (on `DOMContentLoaded`).

## Depends on
- **Host:** nothing — it *is* the base.
- **Other modules (lazy, at call-time only):** the contract's getters resolve
  `opfs` (opfs.js), `addMsg`/`anyStreamGenerating`/`refreshConversationList`
  (conversations.js), and `SandpieTokens` (context.js).

## Notes / gotchas
- **Must be classic, not a module** — its top-level `const`/`let`/`function`
  declarations must be *bare globals* every other script reads by name.
- **Must load first**, but its module-backed refs are lazy getters, so the
  modules that back them can load afterward.

---
_Surface verified from source; for internal implementation see `modules/core.js`._
