# Module: `dropbox.js`

> Dropbox **cloud sync** — the `dbx*` transport (OAuth + HTTP) plus the sync
> engine. Registers itself as the host's optional sync provider.

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | `window.dbx*` transport helpers + an internal sync-engine IIFE |
| **Sidebar section** | `cloudSection` |
| **Status dot** | `dbxDot` (`ok` connected / `err` error) |

## Public surface
- **Transport (`window.dbx*`):** the Dropbox HTTP client (OAuth tokens, upload /
  download / list / delete-batch, …).
- **Capability:** registers a provider via **`Sandpie.registerSyncProvider({ sync,
  fileStatus, getState, isConnected, initialSyncDone })`** — this is how the rest
  of the app reaches cloud sync (never by referencing dropbox.js directly).

## Events
- **Emits:** none directly.
- **Listens:** `file:changed`, `file:deleted` — the sync engine marks the local
  dirty-set / removes the cloud copy in response.

## DOM owned
`#cloudSection` (Connect/Disconnect button `#dbxToggleBtn`, sync status), `#dbxDot`.

## Depends on
- **Host:** `Sandpie.registerSyncProvider`, `Sandpie.events`, `SandpieMenu`, `Sandpie.opfs`.
- **Service worker:** handles `opfs-deleted-by-python` / `sw-opfs-changed` messages
  to keep the dirty-set in step with Pyodide-side file changes.

## Notes / gotchas
- Event-driven sync: a dirty-set push on `file:changed` and a cursor-delta pull,
  with a periodic full-scan safety net.
- Bulk download is **read-only** — it must never write back to Dropbox.

---
_Surface verified from source; for internal implementation see `modules/dropbox.js`._
