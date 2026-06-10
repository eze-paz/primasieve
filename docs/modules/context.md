# Module: `context.js`

> Context management: **token accounting** (`SandpieTokens`) and **skills**
> (`SandpieContext`) — an enforced skill index that the **model** loads from on
> demand via the `load_skill` tool. Both surfaced in the Context sidebar section.

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
  conversations.js on every send: the index table + an instruction to call
  `load_skill`. `''` when `skills/index.md` doesn't exist. Never injects bodies.
- `inspect(convMessages)` → `{exists, skills, errors, loaded}` with per-skill
  `SKILL.md` existence checks (sidebar view).
- `scaffold()` — create a template `skills/index.md` (emits `file:changed`).
- `subscribe(cb)` / `lastState()` — sidebar re-render hook.

## Skills contract
The trigger is **the model's judgment, not a keyword match** — chosen for
reliable dynamic context (synonyms like "ship it to prod" and intent expressed in
an assistant turn both work; a literal matcher covers neither).

- **Index:** `skills/index.md` — one markdown table, enforced header
  `| Skill | When to use | Path |`. Rows before the header are ignored; every
  malformed row is skipped **and reported** (sidebar + a capped note in the
  prompt so the model can self-repair). Name = `[a-z0-9][a-z0-9_-]*`, unique; a
  non-empty "when to use" description; Path = folder relative to OPFS root (a
  leading `/files/` or `/` is tolerated and stripped) containing `SKILL.md`.
- **Awareness (always):** the index table (name + clipped description + path)
  and a "call `load_skill` when a request matches a description, by intent not
  wording" instruction go into every system prompt. Cheap; lets the model know
  what's loadable without reading any bodies.
- **Selection (model):** the model calls the `load_skill` tool
  (`tools.js` def → `sandpie.js` exec); the SW returns the chosen `SKILL.md` as a
  tool result, capped by the loop's `truncateToolResult`. The body lands in the
  conversation, not the system prompt. Cost: one tool round-trip when a skill is
  first needed.
- **No reload:** skills already pulled this conversation are detected from prior
  `load_skill` tool calls in the history and marked `(already loaded above)` in
  the index so the model doesn't re-fetch them.
- **Freshness:** the index is read from OPFS at send time — no cache.

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
  resolves paths straight from `skills/index.md`, so it keeps working even if
  context.js is absent — it just won't be advertised in the system prompt.
- The skills sidebar re-renders on section open and after every send
  (`skillBlock` → internal `notify`); it is *not* live on external OPFS edits.

---
_Surface verified from source; for internal implementation see `modules/context.js`._
