# Module: `notifications.js`

> System notifications when a generation finishes (browser permission + a toast),
> plus the Notifications sidebar section.

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | `SandpieNotifications` |
| **Sidebar section** | `notificationsSection` |
| **Status dot** | `notifDot` (lit only when notifications will actually fire) |

## Public surface
`SandpieNotifications`: `notifyComplete(...)`, `toggle()` (and the permission /
preference helpers behind the section UI).

## Events
- **Emits:** none.
- **Listens:** **`generation:complete`** — fires a system notification (subscribed
  in a guarded, idempotent `wireEvents()`).

## DOM owned
`#notificationsSection` (enable button + helper text), `#notifDot`.

## Depends on
- **Host:** `Sandpie.events`, `SandpieMenu`.
- **Browser:** the `Notification` API.

## Notes / gotchas
- The bare-global API (`notifyComplete` / `toggle`) is kept because the monolithic
  `sandpie.html` variants call it directly; on the modular page the page emits
  `generation:complete` instead of calling in.

---
_Surface verified from source; for internal implementation see `modules/notifications.js`._
