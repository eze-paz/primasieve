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
  internal `tools` map): `run_python`, `write_file`, `edit_file`, `show_artifact`,
  `load_image`, `load_skill`.

## Tools
- `load_skill(name)` — loads a skill's `SKILL.md` so the **model** decides when a
  skill applies (see `context.js`). Defined here, executed in the service worker
  (`sandpie.js → tool_load_skill`, dispatched from `runTool`), which resolves
  `name → path` from `skills/index.md` (convention fallback `skills/<name>/`) and
  returns the file contents as the tool result. The schema only matters for the
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
