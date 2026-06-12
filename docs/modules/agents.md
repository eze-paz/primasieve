# Module: `agents.js`

> Modular **background automations** defined by OPFS config files. Each agent is
> `agents/<id>.md` (frontmatter config + prompt body); they run a zero-shot prompt
> *between* turns when a trigger fires. Editable in the sidebar **and** by the
> main LLM via the file tools. Ships one default agent: a **memory distiller**.

| | |
|---|---|
| **Load type** | `type="module"` (deferred, `?v=` cache-bust) |
| **Global namespace** | `window.SandpieAgents` |
| **Sidebar section** | `agentsSection` |
| **Status dot** | none |

## Public surface
`window.SandpieAgents`: `loadAgents()` (re-scan `agents/`), `runNow(id)`,
`stopAll()`, `agents` (getter — parsed registry), `_internals` (parsing/sink/run
helpers, for tests).

## Config: `agents/<id>.md`
The filesystem is the registry (no hardcoded list). `id` = filename
(lowercase `[a-z0-9][a-z0-9_-]*`). Frontmatter = config; the body = the prompt
(multi-line, no escaping). Both the sidebar editor and the assistant's
`read_file`/`write_file`/`edit_file` tools edit these files — one source of truth.

```
---
name: Memory distiller       # display name
enabled: false               # opt-in (the toggle / LLM rewrites this line)
every_messages: 10           # trigger: fire every N messages
at_context_pct:              # trigger: fire at >= P% of the context window
every_minutes:               # trigger: fire every M minutes (best-effort)
input: since_last_run        # since_last_run | conversation | last_<n>
sink: memory                 # memory | note | append:<path>
model:                       # optional model override
---
<the prompt>
```
- **Triggers** (OR of those set) are evaluated on `generation:complete`. `at_context_pct` uses `SandpieTokens`.
- **Input** — the conversation slice the agent sees (`since_last_run` uses a per-(agent,conversation) cursor in `localStorage`).
- **Sinks** — `memory` parses a `{topic,note}` JSON result → appends `memory/<topic>.md`; `append:<path>` appends raw output to a file; `note` just surfaces the output in the sidebar.
- **Validation** — malformed agents (no frontmatter / no prompt / no trigger / unknown sink / bad filename) are flagged in the UI and never run (their enable checkbox is disabled).

## UI (`#agentsBody`)
Lists each agent with an **enable toggle**, trigger+sink summary, status, and
**Edit / Run now / Delete**. **Edit** opens a textarea on the raw `.md` (config +
prompt — generic to any field), **Save** writes the file. **+ New agent**
scaffolds `agents/new_agent.md`. External edits (e.g. the assistant tuning a file)
live-refresh the list via the `file:changed` listener (unless mid-edit).

## Guardrails
Opt-in (off by default); idle-only (runs on `generation:complete`, skips while `Sandpie.isGenerating()`); single-flight; gated (cursor so a span isn't reprocessed; a failed call retries); **loop-proof** (direct non-streaming `runPrompt` — never the SW stream — emits no `generation:complete`; agents write to `memory/`/append paths, never `agents/`); cancellable; failure-isolated.

## Events
- **Emits:** `file:changed` (agent file writes via toggle/save/scaffold, and `memory/`/append-sink writes), `file:deleted` (agent delete).
- **Listens:** `generation:complete` (trigger tick; skips aborted turns), `file:changed` (re-render when an `agents/` file changes externally).

## DOM owned
`#agentsSection` (badge = count of enabled, valid agents), `#agentsBody`, `#agentNew`.

## Depends on
- **Host:** `SandpieMenu`, `Sandpie.events`, `Sandpie.isGenerating()`, `Sandpie.api()`, `Sandpie.refreshFiles()`, `opfs` (read/write/remove/listDir/exists), shared globals (`messages`, `activeConvId`), `localStorage`.
- **Other modules (runtime):** `SandpieTokens` (the `at_context_pct` trigger), `SandpieProviders.getActive()` (temperature), and the provider inputs (`#endpoint`/`#apiKey`/`#model`) for the background completion.

## Notes / gotchas
- **Recall is separate.** Agents *write* `memory/`; making the model *use* it (an always-present memory index) is a later slice. The model can already reach memory + agent configs via `read_file`/`search`.
- Memory is **domain-keyed** and distinct from `skills/` (task-keyed, authored) by design.
- Background runs make their own model calls — surfaced and off by default.

---
_Surface verified from source; for internal implementation see `modules/agents.js`._
