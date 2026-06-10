# Module: `tools.js`

> The tool/function **schemas** the agent loop exposes to the model (e.g.
> `run_python`, `show_artifact`).

| | |
|---|---|
| **Load type** | `classic` |
| **Global namespace** | `toolDefs()` (bare global) |
| **Sidebar section** | none |
| **Status dot** | none |

## Public surface
- `toolDefs()` — returns the array of tool/function definitions (built from an
  internal `tools` map): `run_python`, `write_file`, `edit_file`, `read_file`,
  `list_files`, `search`, `show_artifact`, `load_skill`, `load_image`.

## Tools
- **`read_file(path, offset?, limit?)`**, **`list_files(path?, pattern?, recursive?)`**,
  **`search(pattern, path?, include?, files_only?, ignore_case?)`** — plain-JS
  read / browse / grep over OPFS, executed in the SW (`sandpie.js` →
  `tool_read_file` / `tool_list_files` / `tool_search`). They run **without
  Pyodide**, so they're instant and can't crash the interpreter the way
  `run_python` can — the tool descriptions tell the model to prefer them for
  reading/listing/searching and keep `run_python` for computation. Design split:
  `search` is **content-only** (regex → `path:line: text`); finding files **by
  name** is folded into `list_files` (`pattern` glob + `recursive`), so each tool
  has one job and one return shape. `read_file` output is line-numbered and pages
  via `offset`/`limit`. All cap output at ~28 KB with a "page for more" note,
  skip binary (NUL-sniffed) and >2 MB files, and `search` skips `/_conversations`
  unless `path` targets it. Shared SW helpers: `normFilesPath`, `globToRegExp`,
  `opfsCollect`.
- `load_skill(name)` — loads a skill's instructions so the **model** decides when a
  skill applies (see `context.js`). Defined here, executed in the service worker
  (`sandpie.js → tool_load_skill`, dispatched from `runTool`), which reads
  `skills/<name>/SKILL.md` directly (the folder name *is* the skill name — no index
  lookup), strips the frontmatter, and returns the body as the tool result. The
  name is validated (also blocks path traversal). The schema only matters for the
  model's *decision*; resolution + read happen SW-side.

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
None.

## Depends on
- Nothing host-side (pure definitions).

## Notes / gotchas
- Consumed by **conversations.js `buildAgentConfig()`**, which passes `toolDefs()`
  into the request sent to the service-worker agent. A natural future candidate for
  a `registerTool()` registry (see ARCHITECTURE §4) so modules can contribute tools.

---
_Surface verified from source; for internal implementation see `modules/tools.js`._
