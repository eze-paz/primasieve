# Module: `console.js`

> Redirects all `console.*` output into a collapsible sidebar panel (so logs are
> visible on mobile / without DevTools), and relays service-worker logs.

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | none (self-contained IIFE; it patches `console`) |
| **Sidebar section** | `console` |
| **Status dot** | none |

## Public surface
None exported. It **hijacks** `console.log` / `warn` / `error` / `info` / `debug`
to also append to the panel, and catches `window.onerror` + `unhandledrejection`.

## Events
- **Emits:** none.
- **Listens:** none (bus). Separately, it listens for service-worker `message`
  events of type `sandpie-sw-log` and forwards them to the (hijacked) console, and
  asks the SW to flush buffered logs on load / `controllerchange`.

## DOM owned
The `console` section: `#consoleLines` (the log buffer view) and the Clear / Copy
buttons.

## Depends on
- **Host:** `SandpieMenu`.
- **Browser:** `navigator.serviceWorker`.

## Notes / gotchas
- Because it patches the global `console`, the SW-log relay's `console.log('[sw]', …)`
  is itself captured into the panel.

---
_Surface verified from source; for internal implementation see `modules/console.js`._
