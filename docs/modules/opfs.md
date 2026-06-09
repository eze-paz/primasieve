# Module: `opfs.js`

> The OPFS filesystem primitives, the sidebar **file browser**, and the **file
> viewer** (image / video / audio / text / PDF preview).

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | `window.opfs` (the fs object) + many `window.*` helpers |
| **Sidebar section** | none (drives the static `#filesSection`) |
| **Status dot** | none |

## Public surface
- **`window.opfs`** — `read` / `readBytes` / `write` / `remove` / `resolveDir` / `listDir` / `lastModified` / `currentPath` / `refreshFileList` / `openFile` / `closeFile` / …
- **Helpers:** `refreshFileList`, `createNewFolder` / `createNewFile`, `uploadEntry`, `opfsCurrentPath`, `opfsJoin`, `opfsUp`, `openFileViewer` / `closeFileViewer`, `showContextMenu` / `closeCtxMenu`, `opfsLastModified`, `getFileSize` / `getFolderSize` / `formatSize`, `initFileBrowser`.
- Backs `Sandpie.opfs`, `Sandpie.opfsMtime`, `Sandpie.refreshFiles`, `Sandpie.openFilePath`.

## Events
- **Emits:** `file:changed` (write / save / upload), `file:deleted` (delete).
- **Listens:** none. (Reads `Sandpie.syncProvider()` / `initialSyncDone()` to show sync badges + the empty/Loading state.)

## DOM owned
`#fileList`, `#opfsPath`, the file-viewer overlay (`.file-viewer`), and the generic
context menu (`showContextMenu`). Holds the preview-type sets `IMAGE_EXTS` /
`VIDEO_EXTS` / `AUDIO_EXTS` / `TEXT_PREVIEW_CAP`.

## Depends on
- **Host:** `Sandpie.events`, `Sandpie.syncProvider()` / `initialSyncDone()`.
- **Browser:** `navigator.storage.getDirectory()` (OPFS), the service worker (posts `opfs-changed`).

## Notes / gotchas
- The file-browser DOM wiring is in `initFileBrowser()`, **deferred to
  `DOMContentLoaded`** — opfs.js loads in `<head>` before `#fileList` / `#opfsPath`
  exist.
- Manages its own `window.markedPromise` for lazy markdown in the viewer.

---
_Surface verified from source; for internal implementation see `modules/opfs.js`._
