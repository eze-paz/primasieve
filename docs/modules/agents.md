# Module: `agents.js`

> Agent presets — the Agents sidebar section.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | `window.SandpieAgents` |
| **Sidebar section** | `agentsSection` |
| **Status dot** | none |

## Public surface
`window.SandpieAgents` — the agent-presets controller surfaced in the section.

## Events
- **Emits:** none.
- **Listens:** none.

## DOM owned
`#agentsSection`.

## Depends on
- **Host:** `SandpieMenu`.

## Notes / gotchas
- Registers its section then renders ("Agents section rendered" on init).

---
_Surface verified from source; for internal implementation see `modules/agents.js`._
