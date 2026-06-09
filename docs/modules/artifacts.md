# Module: `artifacts.js`

> Renders HTML **artifacts** in a side panel (sandboxed `iframe`) — the
> `show_artifact` tool's output.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | `window.SandpieArtifacts` + `renderArtifact`, `closeArtifactPanel` |
| **Sidebar section** | `artifactsSection` |
| **Status dot** | none |

## Public surface
- `renderArtifact(host, path)` — open/refresh the artifact panel for an OPFS path.
- `closeArtifactPanel()` — close it (inline `onclick` on `#artifactPanelClose`).
- `window.SandpieArtifacts` — the section/panel controller.

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
`#artifactsSection`, and the side artifact panel inside `#messagesSide`:
`#artifactPanelFrame` (the iframe), `#artifactPanelHeader`, `#artifactPanelTitle`,
`#artifactOpenLink`, `#artifactPanelClose`.

## Depends on
- **Host:** `SandpieMenu`, `Sandpie.opfs` (read the artifact file), shared state
  (`activeConvId` / `convStreams`, `typeof`-guarded), `$`.

## Notes / gotchas
- **`renderArtifact` is called by conversations.js** when re-rendering a
  `show_artifact` tool call — which is why conversations.js boots on
  `DOMContentLoaded` (artifacts.js loads *after* it).

---
_Surface verified from source; for internal implementation see `modules/artifacts.js`._
