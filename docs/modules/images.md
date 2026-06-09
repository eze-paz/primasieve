# Module: `images.js`

> Image attachments for messages — the file picker, the preview chip, and
> resolving `opfs://` image refs to data URLs.

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | `SandpieImages` |
| **Sidebar section** | none |
| **Status dot** | none |

## Public surface
`SandpieImages`: `hasImage()`, `buildContent(text)` (assemble the user message
content array), `clear()`, `dataUrlFromPath(path)` (OPFS → data URL),
`setState({ dataUrl, file, opfsPath })`.

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
`#imageInput` (hidden file input), `#imagePreview` (the preview + remove button),
and the `#attachBtn` trigger.

## Depends on
- **Host:** `Sandpie.opfs` (resolving `opfs://` refs), `$`.

## Notes / gotchas
- Consumed heavily by conversations.js on submit/render; `dataUrlFromPath` is also
  used when re-rendering historical image messages.

---
_Surface verified from source; for internal implementation see `modules/images.js`._
