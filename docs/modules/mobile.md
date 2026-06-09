# Module: `mobile.js`

> Mobile UX — viewport detection, long-press → context menu, and the
> sidebar open/collapse behaviour.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | `isMobileViewport`, `attachLongPress`, `toggleSidebar`, `toggleSidebarCollapse` |
| **Sidebar section** | none |
| **Status dot** | none |

## Public surface
- `isMobileViewport()` — boolean.
- `attachLongPress(el, handler)` — long-press → handler (touch context menus).
- `toggleSidebar()` / `toggleSidebarCollapse()` — inline `onclick` on the hamburger,
  backdrop, and collapse/expand buttons.

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
The mobile header hamburger, the `.backdrop`, and the `<aside>` open/collapsed state.

## Depends on
- **Host:** `$`.

## Notes / gotchas
- `isMobileViewport()` gates conversations.js's side-by-side panel (disabled on
  mobile); `attachLongPress` is used on conversation-list items.

---
_Surface verified from source; for internal implementation see `modules/mobile.js`._
