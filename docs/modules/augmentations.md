# Module: `augmentations.js`

> Optional per-conversation augmentations — relevance hints and conversation
> metadata (scripts / files touched).

| | |
|---|---|
| **Load type** | `classic`, `defer` (loaded last, `?v=2`) |
| **Global namespace** | `window.SandpieAugmentations` |
| **Sidebar section** | none |
| **Status dot** | none |

## Public surface
`window.SandpieAugmentations`:
- `showRelevance(text, convId)` — surface relevance hints for the drafted message.
- `getConvMeta(convId)` — per-conversation metadata accumulator (e.g. `scripts` /
  `files` touched).

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
Relevance hint UI near the composer (when active).

## Depends on
- **Host:** shared state (`activeConvId`).

## Notes / gotchas
- Self-initializes defensively (`window.SandpieAugmentations ||= {}`), so callers
  in conversations.js guard with `.catch(() => {})` and it degrades to a no-op when
  absent.

---
_Surface verified from source; for internal implementation see `modules/augmentations.js`._
