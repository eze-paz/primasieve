# Module: `context.js`

> Context management: **token accounting** (`SandpieTokens`) and **skills**
> (`SandpieContext`) — a **filesystem-derived** skill index (no registry to
> maintain) that the **model** loads from on demand via the `load_skill` tool.
> Both surfaced in the Context sidebar section.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | `window.SandpieTokens`, `window.SandpieContext` |
| **Sidebar section** | `contextSection` (usage badge + skills list) |
| **Status dot** | none |

## Public surface
`SandpieTokens` — conversation + weekly token accounting; backs **`Sandpie.tokens`**.
Real counts come from the provider's `usage` object; falls back to a chars/4
estimate. The per-provider context-window denominator is set in the provider modal.
Exposes `notify()` (re-render) among others.

`SandpieContext` — skills:
- `skillBlock(convMessages)` → string appended to the system prompt by
  conversations.js on every send: the derived index table + an instruction to
  call `load_skill`. `''` when there's no `skills/` directory. Never injects bodies.
- `inspect(convMessages)` → `{exists, skills, errors, loaded}` — same scan as
  `skillBlock`, for the sidebar.
- `scaffold()` — create one well-formed example skill (`skills/example_skill/SKILL.md`,
  emits `file:changed`) so the frontmatter format is obvious.
- `subscribe(cb)` / `lastState()` — sidebar re-render hook.

## Skills contract
Two deliberate properties: selection is **the model's judgment, not a keyword
match** (synonyms like "ship it to prod" and intent in an assistant turn both
work), and the index is **derived from the filesystem** — there is no hand-maintained
registry to drift out of sync.

- **A skill = `skills/<name>/SKILL.md`.** The folder name *is* the skill name
  (must be lowercase `[a-z0-9][a-z0-9_-]*`). Each `SKILL.md` self-describes via
  leading YAML-style frontmatter: `description` (REQUIRED — how the model decides
  to load it) and optional `name` (defaults to the folder; a mismatch is warned).
- **Discovery (deterministic):** every send, `scanSkills()` walks `skills/*/` and
  parses each `SKILL.md`'s frontmatter. Drop in a folder ⇒ it appears; no edit to
  any index. The frontmatter parser is dependency-free (scalar `key: value`,
  optional quotes, CRLF-tolerant).
- **Validation (deterministic):** a folder with no `SKILL.md`, no frontmatter, a
  bad (non-lowercase) folder name, or no `description` is **flagged** — in the
  sidebar and a capped note in the prompt — and is **not** offered to the model
  (without a description it can't know when to use it). Only fully-valid skills
  reach the prompt's table.
- **Awareness (always):** the derived table (name + clipped description) plus a
  "call `load_skill` when a request matches a description, by intent not wording"
  instruction go into every system prompt. Bodies are never injected.
- **Selection (model):** the model calls `load_skill` (`tools.js` def →
  `sandpie.js` exec). The SW reads `skills/<name>/SKILL.md` directly (folder =
  name, no index lookup), strips the frontmatter, and returns the body as a tool
  result (capped by the loop's `truncateToolResult`). Cost: one round-trip per
  skill, first time it's needed.
- **No reload:** skills already pulled this conversation are detected from prior
  `load_skill` tool calls and marked `(already loaded above)` so the model doesn't
  re-fetch them.
- **Freshness:** the filesystem is scanned at send time — no cache.

## Events
- **Emits:** `file:changed` (only from `scaffold()`).
- **Listens:** **`tokens:record`** (`{convId, usage}`) — accumulate usage for the
  conversation + the rolling weekly total.

## DOM owned
`#contextSection` (badge via `SandpieMenu.updateBadge`), `#ctxSkillCount`,
`#ctxSkillList`, `#ctxSkillErrors`, `#ctxSkillCreate`.

## Depends on
- **Host:** `Sandpie.events`, `SandpieMenu`, `opfs` (read/write/exists/remove),
  shared state (`activeConvId`, `convStreams`, `messages`), `localStorage`.

## Notes / gotchas
- `SandpieTokens` lives here (not in a separate `tokens.js`); conversations.js calls
  `SandpieTokens.notify()` when the active conversation changes.
- conversations.js consumes `SandpieContext.skillBlock` behind a `typeof` guard —
  deleting this module degrades to the plain memory prompt (acceptance test §8).
  The `load_skill` tool (tools.js + sandpie.js) is independent of this module: it
  reads `skills/<name>/SKILL.md` by convention, so it keeps working even if
  context.js is absent — it just won't be advertised in the system prompt.
- The skills sidebar re-renders on section open and after every send
  (`skillBlock` → internal `notify`); it is *not* live on external OPFS edits.

---
_Surface verified from source; for internal implementation see `modules/context.js`._
