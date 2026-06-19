# Module: `conversations.js`

> The entire conversation surface: message rendering, streaming via the SW agent,
> conversation CRUD + list, the side-by-side panel, the bubble context menu,
> markdown rendering, scroll behaviour, and boot/restore.

| | |
|---|---|
| **Load type** | `type="module"` (deferred) |
| **Global namespace** | ~30+ `window.*` functions + `window.sidePanel` |
| **Sidebar section** | none (drives the static `#convSection` + the message area) |
| **Status dot** | none |

## Public surface
Window-exposed for inline handlers, the host contract, and other modules:
- **Rendering:** `addMsg`, `bindBubble`, `renderHistoricalMessage`, `RoundRenderer` (internal), `renderTcDone`, …
- **Streams:** `ensureStream`, `activeStream`, `anyStreamGenerating`, `setStreamSending`, `startTotalTimer` / `endTotalTimer`.
- **CRUD / list:** `newConversation`, `loadConv`, `saveConv` / `saveActiveConv`, `deleteConv`, `renameConv`, `togglePinConv` / `toggleArchiveConv`, `duplicateConv`, `refreshConversationList`, `mountConv`, `convPath`.
- **Sending:** `handleSubmit`, `handleButtonClick`, `enqueueForActive`, `processQueueFor`, `sendSingle`, `buildAgentConfig`, `readAgentEvents`, `dispatchAgentEvent`.
- **Bubble menu (inline `onclick`):** `rewindFromMenu`, `copyFromMenu`.
- **Boot:** `maybeResumeFlight`, `window.sidePanel`.
- Backs `Sandpie.addMsg`, `Sandpie.isGenerating`, `Sandpie.refreshConversations`.

## Events
- **Emits:** `file:changed` (save / update / duplicate a conversation), `file:deleted` (delete), `tokens:record` (`{convId, usage}` on a stream usage event), `generation:complete` (`{convId, aborted}` after each round).
- **Listens:** none.

## DOM owned
`#messages`, `#messagesSide`, `#messagesWrap`, `#sideResizer` (side panel),
`#convList`, `#convSearch`, `#input`, `#sendBtn`, `#bubbleContextMenu`, the welcome
screen, and all message bubbles + the "thinking" / tool-call elements.

## Depends on
- **Host:** `Sandpie.opfs`, `Sandpie.events`, `Sandpie.sync()` / `syncProvider()`, `Sandpie.$`, shared state (`messages`, `convStreams`, `activeConvId`).
- **Other modules (runtime):** `SandpieImages` (attachments), `SandpieAugmentations` (relevance + conv metadata), `toolDefs()` (tools.js), `renderArtifact` / `buildToolBox` (artifacts.js), `SandpieTokens.notify()` / `SandpieContext.skillBlock(convMessages)` (context.js — skills block appended to the system prompt).

## Notes / gotchas
- **Boots on `DOMContentLoaded`**, not at module-eval — a restored message may call
  `renderArtifact` (artifacts.js loads after conversations.js).
- The agent stream runs through the service worker (`./sandpie-agent`); `RoundRenderer`
  paints deltas/tool calls live.

---
_Surface verified from source; for internal implementation see `modules/conversations.js`._
