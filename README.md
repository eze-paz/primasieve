# Sandpie

A browser-based LLM agent workspace with local Python execution, Dropbox sync, and multimodal support.

## Architecture

### 01 System Architecture

=============================================================================
sandpie-sw end-to-end flow
=============================================================================
The system is fan-shaped: the page boots → registers a Service Worker → the
user sends a message → the page POSTs to a same-origin /sandpie-agent path
that the SW intercepts → the SW runs the full LLM agent loop (stream upstream,
dispatch tool calls, recurse) → the SW emits NDJSON events back to the page
→ the page renders each event into the conversation's bubble host.
When editing, find the step that owns the concern you're touching and read
the surrounding section banner. State that lives in one step must not be
mutated from another.
─────────────────────────────────────────────────────────────────────────────
PAGE LIFECYCLE                                                  (this file)
─────────────────────────────────────────────────────────────────────────────
P0  HTML parses → marked.js + DOMPurify <script src> load → this inline
<script> runs.
P1  Globals init: convStreams (Map), activeConvId, cachedManifests,
localProxyMode, providers, ... .
P2  navigator.serviceWorker.register('./sandpie.js'); _swReady waits
for controllerchange so first /sandpie-agent POST is intercepted.
P3  init() → loadProviders, restore active conv, mountConv,
refreshFileList, refreshWelcome, refreshConversationList.
P4  await sync() pulls Dropbox if connected (no-op otherwise).
─────────────────────────────────────────────────────────────────────────────
USER SEND                                                       (this file)
─────────────────────────────────────────────────────────────────────────────
U1  <form onsubmit> → handleSubmit().
U2  handleSubmit reads $('input'), calls enqueueForActive(text).
U3  enqueueForActive: ensureActiveConv → ensureStream(id) → mountConv if
host detached → stream.queue.push(text) → processQueueFor(s).
U4  processQueueFor: while queue non-empty → await sendSingle(text,
stream). Resets queueAborted on entry, sets isProcessing.
─────────────────────────────────────────────────────────────────────────────
ONE ROUND — PAGE SIDE                                           (this file)
─────────────────────────────────────────────────────────────────────────────
R1  sendSingle builds config: { url, headers, model,
systemPrompt: buildSystemPrompt(), messages, tools: toolDefs(),
proxyBase, origin, dbxTokens, convId }.
R2  await _swReady; POST ./sandpie-agent with the config as body.
R3  Read response body line-by-line, JSON.parse each NDJSON line, dispatch
to handleEvent(ev).
─────────────────────────────────────────────────────────────────────────────
ONE ROUND — SW SIDE                                          (sandpie.js)
─────────────────────────────────────────────────────────────────────────────
S1  fetch event on /sandpie-agent → handleAgent(req).
S2  ReadableStream.start → runAgent(config, ctx) with ctx.emit pushing
events back to the page.
S3  runAgent loop:
emit round_start
streamOneRound(url, headers, body, ctx):
fetch upstream LLM with stream=true
for each SSE delta: accumulate, emit { type:'delta', delta }
return { content, tool_calls }
emit round_end
if no tool_calls: emit message_added (asst only), break
emit message_added (asst with tool_calls)
for each tc:
emit tool_started
runTool(name, args, ctx) → tool_run_python / tool_fetch_file / ...
emit tool_result (+ artifacts)
emit message_added (tool)
next round
emit agent_done
─────────────────────────────────────────────────────────────────────────────
EVENT DISPATCH — PAGE SIDE                                      (this file)
─────────────────────────────────────────────────────────────────────────────
All per-round render state is owned by `RoundRenderer` (a single object
constructed at the top of sendSingle). handleEvent dispatches events into
the renderer's methods — it does NOT touch render state directly.
E1  round_start    → renderer.startRound()
E2  delta          → renderer.applyDelta(ev.delta)
├─ content delta → typewriter into reply
└─ tool_call delta → bubble, then typewriter for
args via toolPending / toolDisplayed / drainTick
E3  round_end      → renderer.endRound() — schedules ')' append after
the args drain completes (NOT before, otherwise the
paren jumps ahead of still-typing args).
E4  message_added  → renderer.bindMessage(msg) — convMessages.push,
bindBubble to wire the rewind/copy menu.
E5  tool_started   → renderer.markToolStarted(tcId) — in-flight class +
flavor ticker.
E6  tool_result    → renderer.markToolDone(tcId, result, artifacts) —
renderTcDone, append tool-result bubble, render
artifacts.
E7  agent_done     → renderer.finalize(); break read loop.
E8  error          → addMsg('err', ...). renderer.finalize() in finally.
─────────────────────────────────────────────────────────────────────────────
POST-STREAM                                                     (this file)
─────────────────────────────────────────────────────────────────────────────
F1  remove abort listener, stream.requestId = null.
F2  releaseWakeLock, endTotalTimer, setStreamSending(false).
F3  await saveConv(convId) — persist messages + artifacts to OPFS.
F4  await sync() — Dropbox push of dirty conv files (no-op if not
connected).
F6  processQueueFor loops back to U4 if more queued, else returns.
─────────────────────────────────────────────────────────────────────────────
TOOL EXECUTION                                               (sandpie.js)
─────────────────────────────────────────────────────────────────────────────
T1  run_python    → initPyodide (lazy) → mountNativeFS → exec → syncfs()
T2  fetch_file    → Dropbox download via SW dbx helper
─────────────────────────────────────────────────────────────────────────────
SW LIFECYCLE                                                 (sandpie.js)
─────────────────────────────────────────────────────────────────────────────
W1  install  → skipWaiting()
W2  activate → clients.claim() so first page load is controlled without
a reload
W3  ~30s idle → SW terminates. Next /sandpie-agent fetch re-boots it.
Pyodide reinitializes lazily on next run_python.
=============================================================================

---

### 05 Sync Engine

============================================================
Sync engine — Dropbox is the source of truth.
============================================================
Replaces the older dbxIndex + manifest split (three sources of truth,
four entry points, drift between them). One state map, one cloud
listing, one sync function.
Shape: syncState[relPath] = {
rev,           // Dropbox content_hash. Drives "did cloud change?".
size,          // Cloud size in bytes. Drives lazy-hydration decision.
hydrated,      // true = file in OPFS; false = placeholder.
syncedMtime,   // OPFS mtime as of last successful sync (0 if not
// hydrated). Drives "did local change?".
}

---

### 07 Context Manifests

============================================================
Context manifests — sandpie_*.md files anywhere in OPFS get auto-loaded
into the system prompt. Convention: a manifest is a short markdown note
describing what's in its folder and pointing at other key docs (skills,
prompts, project READMEs). LLM gets oriented without searching.
============================================================

---

### 04 Dual Pane State

=============================================================================
SidePanel — controller for the dual-conversation view.
=============================================================================
State model (single source of truth lives in this object):
left      = $('messages')      — primary DOM panel, ALWAYS the host for
activeConvId's conv when activeIsRight is
false, swaps with right on flip()
right     = $('messagesSide')  — secondary DOM panel, shown iff isOpen
_sideId   = string | null      — conv mounted in the inactive panel
_activeIsRight = bool          — which physical panel currently owns
activeConvId. Flips on flip().
Public API (everything else in the file goes through THESE four methods —
no caller touches body classes or DOM panels directly):
open(id)            — mount conv `id` into the right panel (lazy-loads
from OPFS if needed). No-op if id is the active
conv or already in the side panel.
close()             — unmount the side conv; collapse the right panel.
flip()              — swap which side is active. Conv hosts STAY in
their pane; only the activeConvId↔sideId labels
and the active-left/active-right body class swap.
notifyDeleted(id)   — called by deleteConv to clear references if the
deleted conv was on the side.
Read-only accessors:
isOpen, sideId, activeIsRight, activeMountTarget()
Invariant: every public method ends by calling _render(), which derives
body.side-open / body.active-left / body.active-right from current state.
That's the single place DOM/CSS sync happens — no scattered classList
toggles elsewhere.
Mobile (<=768px): CSS hides the right panel; buildConvLi suppresses the
"View in side panel" menu item; the drop handler early-returns. The
controller itself is viewport-agnostic — it'll happily track state for
a panel that's CSS-hidden, and the user gets it back on resize.
=============================================================================

---

### 03 Rendering Lifecycle

=============================================================================
RoundRenderer — owns ALL per-round render state for one streaming exchange.
=============================================================================
One instance per sendSingle call. The dispatch layer (dispatchAgentEvent
below) is the ONLY caller of its public methods; it does not touch render
state directly. Lifecycle, matching the flow-chart event labels:
r = new RoundRenderer(host, convMessages)
r.startRound()                              // E1  round_start
r.applyDelta(ev.delta)                      // E2  delta
r.endRound()                                // E3  round_end
r.bindMessage(msg)                          // E4  message_added
r.markToolStarted(tc)                       // E5  tool_started
r.markToolDone(id, result, artifacts)       // E6  tool_result
r.finalize()                                // F2  always, from finally
Invariants:
* Bubble DOM lives in this.host only.
* drainTick is the ONLY writer of tool-arg text during a round; applyDelta
just enqueues into toolPending[i]. This is the structural reason the
typewriter can't be "skipped" by a fast-arriving delta.
* startRound() and finalize() share one private flush path
(_flushAllPending) so a fast tool that fires tool_result → next
round_start before the typewriter has finished cannot strand the prior
bubble mid-arg.
* finalize() is idempotent and safe to call from any finally regardless
of where the round/tool cycle left off.
=============================================================================

---

### 06 Service Worker Rationale

============================================================
LLM streaming via Service Worker — sibling sandpie.js owns the
upstream fetch + buffered SSE drain. The page just issues a normal
fetch to a sentinel path the SW intercepts. Why a SW instead of a
dedicated Web Worker:
* Dedicated workers freeze WITH the page (Chrome's energy-saver
freezing suspends task execution including network event handlers).
When the tab unfreezes the in-flight stream is often dead — no
bytes were read, the upstream's idle timer fired, FIN never
propagated cleanly. The Web Worker version had a watchdog to
retry past this, but at the cost of restarting the completion.
* Service workers have a separate lifecycle — they're explicitly
exempt from freezing while a fetch handler is in flight, so a
mid-stream tab freeze of 1-2 minutes is survivable: the SW keeps
draining bytes into an in-memory buffer, and the page picks up
where it left off when it unfreezes.
* Bonus: page-side code is simpler. No postMessage protocol, no
requestId multiplex — just `fetch(SW_STREAM_PATH, { body })`
and read the response body like any other SSE stream.
============================================================

---

### 02 Request Flow

=============================================================================
sendSingle — orchestrates ONE round-trip with the agent loop.
=============================================================================
Reads as a near-1:1 mapping of the flow-chart steps. Each step's concern
lives in its own helper so this function stays a thin coordinator:
[R1] buildAgentConfig  — package the SW request payload from the UI state
[R2] await _swReady    — make sure the SW is controlling this page
[R2] fetch /sandpie-agent — POST the config, SW intercepts
[R3] readAgentEvents   — NDJSON line reader, calls dispatch for each line
[E*] dispatchAgentEvent — map ev.type to the renderer's method
[F1..F5] finally       — abort cleanup, persistence, Dropbox sync
All per-round render state is in the RoundRenderer constructed at the top.

---


## Component Overview

### Service Worker (`sandpie.js`)
- Runs the LLM agent loop end-to-end
- Manages Pyodide interpreter (single shared instance)
- Handles tool dispatch: `run_python`, `fetch_file`, `show_artifact`, `load_image`
- Emits NDJSON events back to page for rendering

### Main UI (`sandpie.html`)
- Dual-pane conversation view with side-by-side comparisons
- Provider management (OpenAI, Anthropic, OpenRouter, local endpoints)
- Dropbox OAuth2 + sync engine
- OPFS file browser and artifact panel
- Image attachment with compression for LLMs

### Modules
- `modules/images.js` - Image handling (compression, OPFS storage, multimodal content)

## Data Flow

```
User sends message
  → POST /sandpie-agent (SW intercepts)
  → SW runs agent loop:
      - Stream LLM response
      - Parse tool_calls
      - Execute tools (Pyodide, Dropbox, OPFS)
      - Emit NDJSON events
  → Page renders events to bubbles
```

## Storage

- **Conversations**: OPFS `_conversations/` directory, auto-synced to Dropbox
- **Context manifests**: `sandpie_*.md` files auto-loaded into system prompt
- **Artifacts**: OPFS files served via `/opfs/<path>` endpoint

## Development

See `docs/extensibility_plan.md` for the roadmap to modular architecture.
