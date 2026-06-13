# sandpie — documentation

Sandpie is a browser-only LLM chat app: a static HTML **host page** plus a set of
independent JavaScript **modules**, with no build step. It's served as plain files
(`marked` / `DOMPurify` come from a CDN), and a service worker (`sandpie.js`) runs
Pyodide to sandbox tool execution.

## Start here

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the whole thing fits together: the
  `Sandpie` host contract, the event bus + catalog, the sidebar registry, load
  order & timing rules, and a step-by-step **"how to add a module."** Read this
  first; it's the high-value, non-obvious knowledge.
- **[modules/](modules/)** — one page per module (its public surface, the events
  it emits/consumes, the DOM it owns, and what it depends on).
  Start from **[modules/\_TEMPLATE.md](modules/_TEMPLATE.md)** when adding a new one.

## The host page

`sandpie.html` is the single app shell — pure markup that loads `modules/core.js`
and the rest. Edit it directly.

## Module map

| Module | Concern |
|---|---|
| [core](modules/core.md) | host contract, sidebar registry, shared state, URL routing |
| [conversations](modules/conversations.md) | messages, streaming, conversation CRUD, side panel |
| [opfs](modules/opfs.md) | OPFS filesystem + file browser + file viewer |
| [providers](modules/providers.md) | AI endpoint / key / model config |
| [dropbox](modules/dropbox.md) | Dropbox cloud sync (transport + engine) |
| [themes](modules/themes.md) | appearance / palettes |
| [console](modules/console.md) | in-app console panel + SW log relay |
| [images](modules/images.md) | image attachments |
| [notifications](modules/notifications.md) | system notifications on completion |
| [context](modules/context.md) | context + token accounting (`SandpieTokens`) |
| [artifacts](modules/artifacts.md) | HTML artifact panel |
| [agents](modules/agents.md) | agent presets |
| [tools](modules/tools.md) | tool/function schemas for the agent loop |
| [mobile](modules/mobile.md) | mobile UX (sidebar, long-press) |
| [augmentations](modules/augmentations.md) | per-conversation augmentations |

> Diagrams use [Mermaid](https://mermaid.js.org/), which GitHub renders natively —
> no build or hosting step required.
