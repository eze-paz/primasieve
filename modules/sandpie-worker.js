// sandpie-worker.js — Dedicated Web Worker for Pyodide + tools + agent loop.
// Replaces the service worker for all compute: Python, file tools, and the
// cloud LLM agent loop. Communicate via postMessage:
//   IN  {type:'agent', id, config}          → agent run; sends {type:'event', id, event} back
//   IN  {type:'tool', id, name, args, ...}  → single tool; sends {type:'tool_result', id, ...}
//   IN  {type:'abort', id}                  → abort a running agent
//   IN  {type:'dbx-token', ...}             → update Dropbox context
//   IN  {type:'opfs-changed', paths}        → fan out to the Pyodide worker pool (MEMFS refresh)
//   IN  {type:'opfs-removed', paths}        → fan out to the Pyodide worker pool (MEMFS drop)
//   IN  {type:'flush-logs'}                 → replay boot log buffer
//   OUT {type:'sandpie-worker-log', ...}    → console relay to page
//   OUT {type:'event', id, event}           → agent event (same NDJSON shapes as SW had)
//   OUT {type:'tool_result', id, result}    → single tool result
//   OUT {type:'forward-to-page', payload}   → relay opfs-deleted-by-python / sw-opfs-changed
// The service worker (sandpie.js) is now minimal: only /opfs/ file serving.

// ---- console relay (Worker → page) ----------------------------------------
const _logBuffer = [];
const _MAX_BUFFER = 200;
function _relayLog(level, args) {
  let text = args.map(a => {
    if (a == null) return String(a);
    if (typeof a === 'string') return a;
    if (a instanceof Error) return (a.stack || a.message || String(a));
    try { return JSON.stringify(a); } catch (_) { return String(a); }
  }).join(' ');
  const MAX_LOG_LEN = 5000;
  if (text.length > MAX_LOG_LEN) text = text.slice(0, MAX_LOG_LEN) + '…';
  const msg = { type: 'sandpie-worker-log', level, text, ts: Date.now() };
  _logBuffer.push(msg);
  if (_logBuffer.length > _MAX_BUFFER) _logBuffer.shift();
  try { self.postMessage(msg); } catch (_) {}
}
// Relay-only: worker console output reaches the page once, via postMessage
// (the page logs it as '[worker] …'). Previously every call ALSO wrote to the
// worker's native console, which Chrome surfaces in the page console too —
// so each worker log appeared twice.
console.log   = (...args) => { try { _relayLog('log',   args); } catch (_) {} };
console.warn  = (...args) => { try { _relayLog('warn',  args); } catch (_) {} };
console.error = (...args) => { try { _relayLog('error', args); } catch (_) {} };
console.info  = (...args) => { try { _relayLog('info',  args); } catch (_) {} };

self.addEventListener('error', (ev) => {
  console.error('uncaught error:', ev.message, 'at', (ev.filename || '?') + ':' + (ev.lineno || '?'), ev.error && ev.error.stack ? '\n' + ev.error.stack : '');
});
self.addEventListener('unhandledrejection', (ev) => {
  const r = ev.reason;
  console.error('unhandled rejection:', r && (r.stack || r.message) || String(r));
});

// Dropbox context pushed from the page so search (cloud leg) + hydration can call the API.
let _dbxCtx = null;
let _dbxTokenReq = null;          // in-flight lazy Dropbox token request (page round-trip)
let _dbxReqSeq = 0;

// Dehydrated-Dropbox state (opt-in JIT hydration). When on, the page stops
// bulk-downloading and pushes the cloud INDEX here; files are fetched lazily on
// first touch. See the hydration helpers further down. Default off ⇒ no change.
let _dehydrated = false;
let _dbxIndex = null;                 // { [rel]: {name,kind,path,size,rev,cloudMtime} } or null
let _dbxExempt = ['sandpie/conversations', 'sandpie/skills', 'sandpie/shared-installed', 'sandpie/shared-incoming'];   // app metadata + shared packages, always eager; sandpie/scripts|artifacts|agents|memory stay dehydratable

// Track active agent AbortControllers so abort messages can cancel them.
const _agentAborts = new Map();
// Steering: user messages sent mid-turn are buffered here per agent id and
// spliced into the running loop at the next round boundary (see runAgent).
const _agentSteers = new Map();   // id -> [content, ...]

// ═══ METACOG TRIGGERS ═══════════════════════════════════════════════════════
// Self-contained metacognition nudges (grind / reuse-a-tool / remember). To
// fully remove: delete this block + the 3 hooks in runAgent (marked METACOG) +
// the `metacog:` line in buildAgentConfig. Kill at runtime: globalThis.__noMetacog
// = true, or `>>> metacog off`. Fires via the same pendingReminder path as the
// drift/stop guards (>>> drift toggles the note's visibility). Session state is
// keyed by conversation and lives for the worker's lifetime.
const _convStats = new Map();   // convId -> stats
// One-shot metacog note per conversation: the page posts it when the NEWEST
// artifact in the convo logged console messages; consumed at the next round
// boundary (see runAgent, before the METACOG (c) nudges).
const _consoleNotes = new Map();   // convId -> {path, entries}
function _statsFor(id) {
  let s = _convStats.get(id);
  if (!s) { s = { calls: 0, since: 0, gaps: [], done: 0, shapes: new Map(),
                  remembers: 0, firedShapes: new Set(), grindArmed: 0, remindedRemember: false };
            _convStats.set(id, s); }
  return s;
}
function _shellShape(cmd) {
  if (typeof cmd !== 'string') return null;
  let c = cmd.trim();
  for (let i = 0; i < 5; i++) { const m = c.match(/^cd\s+\S+\s*(&&|;)\s*/); if (m) c = c.slice(m[0].length); else break; }
  c = c.replace(/0x[0-9a-fA-F]+/g, 'ADDR').replace(/\d+/g, 'N').replace(/\s+/g, ' ').trim();
  return c.slice(0, 120);   // structural skeleton + target file survive normalization
}
// Only inline-AUTHORING commands count toward the "reuse-a-tool" signal — a
// heredoc or `cat >` builds a throwaway probe. Re-running a saved file
// (`python foo.py`) or a test (`cargo test`) is USING a tool, not rebuilding one,
// so it must NOT trigger "save this as a script" (that was a sim false-positive).
function _isAuthoring(cmd) {
  if (typeof cmd !== 'string') return false;
  let c = cmd.trim();
  for (let i = 0; i < 5; i++) { const m = c.match(/^cd\s+\S+\s*(&&|;)\s*/); if (m) c = c.slice(m[0].length); else break; }
  return /^cat\s*>>?\s*\S/.test(c) || /<<\s*['"]?\w+/.test(c);
}
// Observe one executed tool call.
function _metacogObserve(s, name, args) {
  s.calls++; s.since++;
  if (name === 'remember') s.remembers++;
  if (name === 'shell' && _isAuthoring(args && args.command)) {
    const sh = _shellShape(args.command); if (sh) s.shapes.set(sh, (s.shapes.get(sh) || 0) + 1);
  }
}
function _median(a) { if (!a.length) return 0; const b = [...a].sort((x, y) => x - y); return b[b.length >> 1]; }
// Returns {kind,text,meta} or null. Never throws.
function _metacogReminder(s, cfg) {
  if ((typeof globalThis !== 'undefined' && globalThis.__noMetacog) || !cfg || !cfg.enabled) return null;
  // A) grind — RELATIVE to this session's own completion rhythm (no absolute magic number)
  const K = cfg.grindK || 3, FLOOR = cfg.grindFloor || 12, COLD = cfg.grindCold || 40;
  const med = _median(s.gaps);
  const grindHit = s.gaps.length >= 3
    ? (s.since > FLOOR && s.since > K * med && s.since >= s.grindArmed)
    : (s.since > COLD && s.since >= s.grindArmed);
  if (grindHit) {
    s.grindArmed = s.since + Math.max(FLOOR, K * med);   // debounce: don't re-fire until it grows again
    return { kind: 'grind', meta: { since: s.since, median: med },
      text: '<system-reminder>You have made ' + s.since + ' tool calls since your last completed todo'
        + (med ? (' — about ' + Math.round(s.since / Math.max(1, med)) + '× your usual for this task') : '')
        + '. Step back: are you genuinely converging, or is it time to change approach, build a reusable instrument, or split the problem? Judge honestly and say which.</system-reminder>' };
  }
  // B) disposable tool — exact-repeat of the same command shape (task-independent)
  for (const [sh, n] of s.shapes) {
    if (n >= (cfg.shapeN || 4) && !s.firedShapes.has(sh)) {
      s.firedShapes.add(sh);
      return { kind: 'reuse', meta: { shape: sh, n },
        text: '<system-reminder>You have rebuilt the same command ' + n + ' times: `' + sh.slice(0, 80)
          + '`. If it will recur, save it once as a reusable script under sandpie/scripts/ (or the most relevant project folder) and remember() it — then it is one call, not a rewrite, next time.</system-reminder>' };
    }
  }
  // C) remember() encouragement — once per session
  if (!s.remindedRemember && s.remembers === 0
      && s.done >= (cfg.rememberAfterDone || 3) && s.calls >= (cfg.rememberAfterCalls || 30)) {
    s.remindedRemember = true;
    return { kind: 'remember', meta: { done: s.done },
      text: '<system-reminder>You have closed ' + s.done + ' items this session but saved nothing to memory. '
        + 'If you learned anything durable and non-derivable (a root cause, a gotcha, where something lives), remember() it now so future sessions start ahead.</system-reminder>' };
  }
  return null;
}
// ═══ END METACOG ════════════════════════════════════════════════════════════

const WORKER_VERSION = '2.25.0-web-search-openrouter';
console.log('[sandpie-worker] boot — version=' + WORKER_VERSION);

// Page-visibility mirror. The worker can't read `document`, so the page forwards
// visibilitychange / Page-Lifecycle freeze into this flag. The per-turn heartbeat
// (see runAgent → _prof) reads it to split a suspension gap into "hidden" (tab
// backgrounded/frozen — the suspicion we're measuring) vs "visible" (foreground
// stall: OS sleep, GC, heavy sync compute).
let _pageHidden = false;
// Points at the CURRENT main-loop turn's _prof while a turn is running (null
// otherwise). Lets the debug ping/block handlers report whether a suspension
// heartbeat is actually live and how much it has recorded — see __ping/__debugBlock.
let _activeProf = null;

// ---- message protocol entry point ------------------------------------------
self.addEventListener('message', async (event) => {
  const data = event.data;
  if (!data) return;

  if (data.type === 'flush-logs') {
    for (const msg of _logBuffer) { try { self.postMessage(msg); } catch (_) {} }
    return;
  }

  if (data.type === 'dbx-token') {
    // pathRoot = namespace for WORKSPACE paths. It is now always null: the workspace
    // lives in the user's home namespace (no Dropbox-API-Path-Root header).
    // teamRoot  = the team-space root namespace, used ONLY to browse/search team
    // folders (e.g. /R+D+I) — a different namespace from the workspace, hence the
    // split. homeNs lets copy_to_workspace pull a team file across into it.
    _dbxCtx = { token: data.token, pathRoot: data.pathRoot || null, teamRoot: data.teamRoot || null, homeNs: data.homeNs || '', workingRoot: data.workingRoot || '', beta: !!data.beta };
    _dehydrated = !!data.dehydrated;
    _pyBroadcast(data);   // keep the Pyodide pool's sync-hydrate context in step
    return;
  }

  if (data.type === 'dbx-token-ack') {
    // Reply to a lazy token request (tool used before the page pushed the token
    // — first-login OAuth race). The page also posts 'dbx-token' itself when it
    // has one; ok:false means still unconnected, so don't keep waiting.
    if (_dbxTokenReq && _dbxTokenReq.id === data.id) {
      clearTimeout(_dbxTokenReq.timer);
      _dbxTokenReq.resolve(!!data.ok);
      _dbxTokenReq = null;
    }
    return;
  }

  if (data.type === 'dbx-index') {
    _dbxIndex = data.index || null;
    if (Array.isArray(data.exempt) && data.exempt.length) _dbxExempt = data.exempt;
    _pyBroadcast(data);
    return;
  }

  // OPFS edits made outside Python (page/SW) are fanned out to every live pool
  // worker so each interpreter's view stays coherent (lazy mode: index refresh
  // + MEMFS invalidation; eager mode: MEMFS byte copy). A newly-spawned worker
  // instead builds a fresh index / full copy at init, so it needs no back-fill.
  if (data.type === 'opfs-removed' && Array.isArray(data.paths)) {
    _pyBroadcast({ type: 'fs-removed', paths: data.paths });
    return;
  }

  if (data.type === 'opfs-changed' && Array.isArray(data.paths)) {
    for (const rel of data.paths) _pyBroadcast({ type: 'fs-changed', rel });
    return;
  }

  // Page → worker visibility mirror. Fed by visibilitychange + Page-Lifecycle
  // freeze/resume on the main thread; read by the per-turn heartbeat to label
  // suspension gaps as hidden (backgrounded) vs visible.
  if (data.type === 'visibility') {
    _pageHidden = !!data.hidden;
    return;
  }

  // DEBUG/VALIDATION: synchronously block THIS (agent) worker's event loop for
  // `ms` (capped 15s) — the same thing a throttled/frozen tab does to it, so the
  // per-turn heartbeat records a real suspension gap. Only reachable via
  // postMessage (never model-triggerable). Run it DURING an active turn:
  //   window._sandpieWorker.postMessage({type:'__debugBlock', ms:6000})
  // Pass {hidden:true} to have the gap counted as hidden-tab instead of a
  // foreground stall (it forces _pageHidden across the next heartbeat tick).
  if (data.type === '__debugBlock') {
    const ms = Math.min(Math.max((+data.ms) || 0, 0), 15000);
    const hadTurn = !!_activeProf;
    const before = _activeProf ? _activeProf.suspendMs : 0;
    const prevHidden = _pageHidden;
    if (data.hidden) _pageHidden = true;          // count the gap as hidden-tab
    const end = Date.now() + ms;
    while (Date.now() < end) { /* busy-block the event loop */ }
    console.warn('[sandpie-worker] __debugBlock: stalled event loop ' + ms + 'ms (hidden=' + !!data.hidden + ', activeTurn=' + hadTurn + ')');
    // Wait past the next heartbeat tick (fires ≤2s after unblock) so it records the
    // gap, then report back what got captured + restore the real visibility.
    setTimeout(() => {
      if (data.hidden) _pageHidden = prevHidden;
      const recorded = _activeProf ? (_activeProf.suspendMs - before) : null;
      try { self.postMessage({ type: 'debug-block-result', version: WORKER_VERSION, ms, hadActiveTurn: hadTurn, stillActive: !!_activeProf, suspendMsRecorded: recorded }); } catch (_) {}
    }, 2600);
    return;
  }

  // DEBUG: report which worker build is live and whether a suspension heartbeat is
  // currently running. window._sandpieWorker.postMessage({type:'__ping'})
  if (data.type === '__ping') {
    try { self.postMessage({ type: 'debug-pong', version: WORKER_VERSION, activeTurn: !!_activeProf, suspendMsSoFar: _activeProf ? Math.round(_activeProf.suspendMs) : null, pageHidden: _pageHidden }); } catch (_) {}
    return;
  }

  if (data.type === 'agent') {
    const { id, config } = data;
    const abortCtl = new AbortController();
    _agentAborts.set(id, abortCtl);
    const ctx = {
      emit: (ev) => { try { self.postMessage({ type: 'event', id, event: ev }); } catch (_) {} },
      signal: abortCtl.signal,
      origin: config.origin || '',
      agentId: id,
    };
    try {
      await runAgent(config, ctx);
    } catch (e) {
      ctx.emit({ type: 'error', message: (e && e.message) || String(e), status: e && e.status });
    } finally {
      _agentAborts.delete(id);
      _agentSteers.delete(id);
      _touchSinks.delete(id);   // stop routing writes to a finished run's sink
      // Terminal-path safety net: if runAgent THREW (e.g. a suspended tab's stream
      // died and exhausted retries), emit the profiling report now so the turn's
      // suspend_ms still reaches the panel instead of dying with the failed turn.
      // Idempotent — a no-op if runAgent already emitted on its normal path. Also
      // stops the heartbeat interval.
      try { if (ctx._reportTiming) ctx._reportTiming(); } catch (_) {}
      try { if (ctx._prof && ctx._prof._hbTimer) { clearInterval(ctx._prof._hbTimer); ctx._prof._hbTimer = 0; } } catch (_) {}
    }
    return;
  }

  // Steer: a user message sent while this agent's turn is still running. Buffer
  // it; runAgent drains the buffer at its next round boundary and continues the
  // loop so the model sees it without the turn having to end first.
  if (data.type === 'steer') {
    if (data.id == null) return;
    const arr = _agentSteers.get(data.id) || [];
    arr.push(data.content);
    _agentSteers.set(data.id, arr);
    return;
  }

  // Page → worker reply to a share() request (see tool_share below). Resolves the
  // deferred the tool is awaiting with the page's publish result/error.
  if (data.type === 'share-result') {
    const d = _shareReqs.get(data.id);
    if (d) { _shareReqs.delete(data.id); d.resolve({ result: data.result }); }
    return;
  }

  // Page → worker reply to an html_console request (see tool_html_console below).
  if (data.type === 'console-result') {
    const d = _consoleReqs.get(data.id);
    if (d) { _consoleReqs.delete(data.id); d.resolve({ result: data.result }); }
    return;
  }

  // Page → worker reply to a screenshot request (see tool_screenshot below).
  // Carries the whole payload — data URL, dimensions and fidelity caveats.
  if (data.type === 'screenshot-result') {
    const d = _shotReqs.get(data.id);
    if (d) { _shotReqs.delete(data.id); d.resolve(data.payload || { ok: false, error: 'empty reply' }); }
    return;
  }

  // Page → worker reply to an ask() request (see tool_ask below). Resolves the
  // deferred the tool is awaiting with the user's answers.
  if (data.type === 'ask-result') {
    const d = _askReqs.get(data.id);
    if (d) { _askReqs.delete(data.id); d.resolve({ result: data.result }); }
    return;
  }

  // Page → worker: the newest artifact in this conversation logged console
  // messages. Queue a one-shot metacog note for that conversation; runAgent
  // injects it as a system-reminder at the next round boundary.
  if (data.type === 'artifact-console-note') {
    const conv = String(data.conversation_file_name || '');
    if (conv && Array.isArray(data.entries) && data.entries.length) {
      _consoleNotes.set(conv, { path: String(data.path || ''), entries: data.entries.slice(0, 25) });
    }
    return;
  }

  if (data.type === 'tool') {
    const { id, name, args, conversation_file_name } = data;
    const ctx = { _conversation_file_name: conversation_file_name || 'unknown', emit: () => {} };
    let out;
    try { out = await runToolGuarded(name, args || {}, ctx); }
    catch (e) { out = { result: 'Error: ' + (e && e.message || e) }; }
    try {
      self.postMessage({
        type: 'tool_result',
        id,
        result: truncateToolResult((out && out.result) || ''),
        artifacts: (out && out.artifacts) || null,
      });
    } catch (_) {}
    return;
  }

  if (data.type === 'abort') {
    const ctl = _agentAborts.get(data.id);
    if (ctl) { try { ctl.abort(); } catch (_) {} }
    // Unblock the one page round-trip that isn't itself abort-aware and takes no
    // ctx: the lazy Dropbox-token wait (_ensureDbxCtx). A tool parked on it would
    // otherwise stall until the setTimeout fires — and that timeout is throttled
    // to ~1/min while the tab is hidden — before the loop could see the abort.
    // Resolving false = "not connected", so the tool returns at once and the loop
    // hits its signal check and stops.
    if (_dbxTokenReq) { try { clearTimeout(_dbxTokenReq.timer); _dbxTokenReq.resolve(false); } catch (_) {} _dbxTokenReq = null; }
    return;
  }
});

// ============================================================
// Pyodide worker pool. Python used to run inline on THIS thread, so a long or
// blocking run_python (incl. the sync-XHR dehydration fault-in) froze token
// streaming for every conversation, and runs could never overlap. Now each
// run_python is dispatched to a dedicated nested worker (pyodide-worker.js) that
// holds its own interpreter: this thread stays free (other conversations keep
// streaming) and a small pool gives real parallel execution.
// ============================================================
const PY_POOL_MAX = (() => {
  try { if (globalThis.__noPyPool) return 1; } catch (_) {}   // debug escape hatch
  // Each pool worker is a full interpreter (~150-200MB) plus a MEMFS mirror of
  // OPFS, so on memory-starved machines extra workers cause wasm OOM / tab
  // kills. navigator.deviceMemory (Chromium-only; capped at 8) <= 4 → one worker.
  const mem = (typeof navigator !== 'undefined' && navigator.deviceMemory) || 0;
  if (mem > 0 && mem <= 4) return 1;
  const n = (typeof navigator !== 'undefined' && navigator.hardwareConcurrency) || 4;
  return Math.min(3, Math.max(1, n - 1));
})();
const PY_DEFAULT_TIMEOUT_MS = 120000;   // a script with no timeout can't run past this…
const PY_MAX_TIMEOUT_MS = 600000;       // …and can't ask for more than this.
const _pyPool = [];            // [{ worker, busy, job }]
const _pyQueue = [];           // jobs waiting for a free worker
let _pyRunSeq = 0;
let _pySpawnSeq = 0;

function _pyBroadcast(msg) { for (const s of _pyPool) { try { s.worker.postMessage(msg); } catch (_) {} } }

// ── Touched-file tracking (replaces show_artifact) ─────────────────────────
// Every OPFS write in this worker — direct file tools, copy, python writes
// relayed from the pool — announces itself to the page as a
// forward-to-page/sw-opfs-changed post, STAMPED with the owning run's id
// (`payload.owner` = ctx.agentId). Intercept postMessage ONCE and route each
// write STRICTLY to the sink registered under that owner id — never a global
// "currently-armed" sink. runAgent registers ctx._filesTouched under ctx.agentId
// while it runs and emits the deduped, most-recent-last list at turn end.
//
// WHY owner-keyed, not a shared armed pointer: two conversations run concurrently
// in this single worker (main + side panel, or two open chats). A run_python
// write is relayed from the pool LONG after the tool call returned — by then a
// different conversation's tool may be executing. A shared "currently-armed"
// pointer therefore misattributed that write to whichever chat happened to be
// active (confirmed in Jordi's transcripts: two chats writing files in the same
// <15s windows). Owner-keying makes misattribution IMPOSSIBLE: a path can only
// ever land in the sink whose agentId matches the stamp. An unknown/missing owner
// is dropped (the file just doesn't surface) — it can never reach the wrong chat.
const _touchSinks = new Map();   // agentId → ctx._filesTouched (registered while the run is live)
// System paths never surface: everything under sandpie/ (conversations, memory,
// skills, helper scripts) EXCEPT the user-visible legacy sandpie/artifacts/,
// plus lab/infra trees.
const _ftExcluded = p => (p.startsWith('sandpie/') && !p.startsWith('sandpie/artifacts/'))
  || p.startsWith('looplab-runs/') || p.startsWith('.tokens');
const _postRaw = self.postMessage.bind(self);
self.postMessage = function (msg, ...rest) {
  try {
    const p = msg && msg.type === 'forward-to-page' ? msg.payload : null;
    // Strict owner routing — no path is ever recorded without a matching owner.
    if (p && p.owner != null && Array.isArray(p.paths)) {
      const sink = _touchSinks.get(p.owner);
      if (sink) {
        if (p.type === 'sw-opfs-changed') { const t = Date.now(); for (const x of p.paths) sink.set(String(x).replace(/^\/+/, ''), t); }
        else if (p.type === 'opfs-deleted-by-python') { for (const x of p.paths) sink.delete(String(x).replace(/^\/+/, '')); }
      }
    }
  } catch (_) {}
  return _postRaw(msg, ...rest);
};

// Finish a job exactly once (result / timeout / crash all race), clearing its
// deadline timer and freeing the slot.
function _pySettle(slot, job, result) {
  if (!job || job.done) return;
  job.done = true;
  if (job.timer) { clearTimeout(job.timer); job.timer = null; }
  if (job.cleanup) { try { job.cleanup(); } catch (_) {} job.cleanup = null; }
  if (slot) { slot.busy = false; slot.job = null; }
  job.resolve({ result });
}

// Kill a worker and drop it from the pool — used when a run blows its deadline
// (an infinite loop can only be stopped by terminating its interpreter) or the
// worker crashes. The next run lazily spawns a replacement.
function _pyKillSlot(slot, reason) {
  const i = _pyPool.indexOf(slot);
  if (i >= 0) _pyPool.splice(i, 1);
  try { slot.worker.terminate(); } catch (_) {}
  console.warn('[sandpie-worker] terminated pyodide-worker:', reason);
}

function _spawnPyWorker() {
  const worker = new Worker('./pyodide-worker.js?v=14', { name: 'py' + (_pySpawnSeq++) });
  const slot = { worker, busy: false, job: null };
  worker.addEventListener('message', (event) => {
    const msg = event.data; if (!msg) return;
    if (msg.type === 'python-result') {
      if (slot.job && slot.job.id === msg.id) _pySettle(slot, slot.job, msg.result);
      _pyDrainQueue();
      return;
    }
    // Relay the pool worker's page-bound messages (opfs-deleted-by-python /
    // sw-opfs-changed / worker-hydrated) and console logs on to the page.
    if (msg.type === 'forward-to-page' || msg.type === 'sandpie-worker-log') {
      // Stamp the launching run's owner on this script's file writes so the
      // interceptor attributes them to the RIGHT conversation. slot.job is the
      // ONE job running on this slot, and its writes arrive before python-result
      // frees the slot — so slot.job.owner is unambiguously this write's owner.
      try {
        const p = msg.type === 'forward-to-page' ? msg.payload : null;
        if (p && (p.type === 'sw-opfs-changed' || p.type === 'opfs-deleted-by-python')
            && p.owner == null && slot.job && slot.job.owner != null) {
          p.owner = slot.job.owner;
        }
      } catch (_) {}
      try { self.postMessage(msg); } catch (_) {}
    }
  });
  worker.addEventListener('error', (e) => {
    console.error('[sandpie-worker] pyodide-worker error:', e.message || e);
    const job = slot.job;
    _pyKillSlot(slot, 'worker error');
    if (job) _pySettle(null, job, 'Error: the Python worker crashed — ' + (e.message || 'unknown') + '. A fresh interpreter will start on the next run.');
    _pyDrainQueue();
  });
  // Bring the fresh worker up to date with current Dropbox context/index.
  if (_dbxCtx) { try { worker.postMessage({ type: 'dbx-token', token: _dbxCtx.token, pathRoot: _dbxCtx.pathRoot, teamRoot: _dbxCtx.teamRoot, homeNs: _dbxCtx.homeNs, workingRoot: _dbxCtx.workingRoot, dehydrated: _dehydrated, beta: _dbxCtx.beta }); } catch (_) {} }
  if (_dbxIndex) { try { worker.postMessage({ type: 'dbx-index', index: _dbxIndex, exempt: _dbxExempt }); } catch (_) {} }
  _pyPool.push(slot);
  return slot;
}

function _pyDrainQueue() {
  while (_pyQueue.length) {
    let slot = _pyPool.find(s => !s.busy);
    if (!slot && _pyPool.length < PY_POOL_MAX) slot = _spawnPyWorker();
    if (!slot) return;   // all workers busy and at cap — wait for a slot to free
    const job = _pyQueue.shift();
    slot.busy = true;
    slot.job = job;
    // Deadline starts now (on dispatch), so time spent queued behind other runs
    // doesn't count against the script.
    job.timer = setTimeout(() => {
      _pyKillSlot(slot, `run_python exceeded ${Math.round(job.timeoutMs / 1000)}s`);
      _pySettle(null, job, `Error: run_python timed out after ${Math.round(job.timeoutMs / 1000)}s and was killed. Its interpreter (globals, imports) is gone. If the script is genuinely long-running, pass a larger "timeout" (max ${PY_MAX_TIMEOUT_MS / 1000}s); otherwise it likely has an infinite loop or a blocking call.`);
      _pyDrainQueue();
    }, job.timeoutMs);
    try { slot.worker.postMessage({ type: 'run-python', id: job.id, path: job.path, code: job.code, args: job.args, betaProject: job.betaProject }); }
    catch (e) { _pySettle(slot, job, 'Error dispatching run_python: ' + (e && e.message || e)); }
  }
}

// Run a script on the pool; resolves with { result } (raw/untruncated, as the
// old in-process tool_run_python did — callers truncate). A run that overruns
// its deadline is killed so it can never hang the conversation.
function dispatchPython({ path, code, args, timeout, signal, owner, betaProject }) {
  let timeoutMs = PY_DEFAULT_TIMEOUT_MS;
  const t = Number(timeout);
  if (isFinite(t) && t > 0) timeoutMs = Math.min(PY_MAX_TIMEOUT_MS, Math.round(t * 1000));
  return new Promise((resolve) => {
    // owner = the agentId of the run that launched this script. The pool relays
    // this script's file writes back asynchronously; the pool-message handler
    // stamps this owner on them so they attribute to the RIGHT conversation even
    // if another chat's tool is executing by the time the write lands.
    const job = { id: 'py' + (++_pyRunSeq), path, code: code || null, args, timeoutMs, resolve, timer: null, done: false, cleanup: null, owner: owner != null ? owner : null, betaProject: betaProject || null };
    // Turn stopped → abandon the run. Pyodide can't be interrupted mid-execution,
    // so a job already running in a slot has its interpreter TERMINATED (same as a
    // deadline overrun); a still-queued job is just dropped. Either way the tool
    // returns at once instead of waiting out the (up to PY_MAX_TIMEOUT_MS) deadline.
    if (signal) {
      const onAbort = () => {
        if (job.done) return;
        const qi = _pyQueue.indexOf(job); if (qi >= 0) _pyQueue.splice(qi, 1);
        const slot = _pyPool.find(s => s.job === job);
        if (slot) _pyKillSlot(slot, 'run_python aborted (turn stopped)');
        _pySettle(slot || null, job, 'Error: run_python aborted — the turn was stopped. Its interpreter was terminated.');
        _pyDrainQueue();
      };
      if (signal.aborted) { onAbort(); return; }   // never enqueue an already-aborted turn
      signal.addEventListener('abort', onAbort, { once: true });
      job.cleanup = () => { try { signal.removeEventListener('abort', onAbort); } catch (_) {} };
    }
    _pyQueue.push(job);
    _pyDrainQueue();
  });
}

// ---- OPFS helpers ----
async function opfsRoot() { return navigator.storage.getDirectory(); }
function splitPath(p) {
  const parts = String(p).split('/').filter(Boolean);
  const name = parts.pop();
  return { parts, name };
}
async function opfsResolveDir(parts, create) {
  let dir = await opfsRoot();
  for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: !!create });
  return dir;
}
async function opfsReadBytes(path) {
  const { parts, name } = splitPath(path);
  const dir = await opfsResolveDir(parts);
  const handle = await dir.getFileHandle(name);
  return new Uint8Array(await (await handle.getFile()).arrayBuffer());
}
// /files/sandpie/ is system-only: exactly these folders may exist there (the
// boot-time allowlist prune enforces it too). Refuse to create anything else —
// a stray sandpie/<x>/ dir would be wiped on the next load anyway.
const SANDBOX_ALLOWED = new Set(['config', 'conversations', 'fonts', 'memory', 'scripts', 'secrets', 'shared-installed', 'skills', 'agents', 'shared-incoming']);
async function opfsWriteBytes(path, bytes) {
  const clean = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  if (clean === 'sandpie' || clean.startsWith('sandpie/')) {
    const seg = clean.split('/')[1] || '';
    if (!SANDBOX_ALLOWED.has(seg)) throw new Error('sandpie/ is system-only — allowed folders: ' + [...SANDBOX_ALLOWED].join(', ') + '. Write to the most relevant user folder under /files/ instead.');
  }
  const { parts, name } = splitPath(path);
  const dir = await opfsResolveDir(parts, true);
  const handle = await dir.getFileHandle(name, { create: true });
  const w = await handle.createWritable();
  await w.write(bytes);
  await w.close();
}
async function opfsWriteText(path, text) { await opfsWriteBytes(path, new TextEncoder().encode(text)); }
// ---- O(1) in-place JSONL append (moved from opfs-append-worker.js) ----
// Main-thread createWritable({keepExistingData:true}) is O(new bytes) at the API
// level but several Chromium versions swap-copy the WHOLE file on close() — a
// per-message append to a long conversation would cost O(whole file) on disk.
// FileSystemSyncAccessHandle writes in place at end-of-file (true O(1)) and is
// worker-only, so the completions worker can own conversation persistence with
// no main-thread involvement: it appends each committed message as it is
// emitted, so the on-disk transcript never lags the stream — no throttled
// 1.2s page timer to starve while hidden, no giant backlog to serialize when
// the user hits stop. A SyncAccessHandle takes an EXCLUSIVE lock, so appends to
// a given path are serialized through a per-path promise chain (the page's
// turn-end saveConv is the only other writer, and it runs after the loop ends).
const _appendEncoder = new TextEncoder();
const _appendChains = new Map();
async function opfsAppendText(path, text) {
  const { parts, name } = splitPath(path);
  const dir = await opfsResolveDir(parts, true);
  const handle = await dir.getFileHandle(name, { create: true });
  const access = await handle.createSyncAccessHandle();
  try {
    const bytes = _appendEncoder.encode(text);
    const at = access.getSize();
    let written = 0;
    while (written < bytes.length) {
      const n = access.write(bytes.subarray(written), { at: at + written });
      if (!n) throw new Error('SyncAccessHandle.write wrote 0 bytes');
      written += n;
    }
    access.flush();
  } finally {
    access.close();
  }
}
function enqueueAppend(path, text) {
  const prev = _appendChains.get(path) || Promise.resolve();
  const next = prev.catch(() => {}).then(() => opfsAppendText(path, text));
  const cleanup = next.catch(() => {}).finally(() => { if (_appendChains.get(path) === cleanup) _appendChains.delete(path); });
  _appendChains.set(path, cleanup);
  return next;
}
async function opfsReadText(path) { return new TextDecoder().decode(await opfsReadBytes(path)); }

// ============================================================
// Dehydrated Dropbox — opt-in JIT hydration
// ============================================================
// When "on-demand file access" is on, the page pushes the cloud index here and
// stops bulk-downloading. Files fault in on first touch: ASYNC for the file
// tools (read_file/load_image/list_files), and SYNCHRONOUSLY (blocking XHR) for
// Pyodide's read() during run_python — only possible in a Web Worker, since sync
// XHR (and responseType on it) is forbidden on the main thread and there is no
// SharedArrayBuffer (no cross-origin isolation in prod). The sandpie/ folder
// (conversations/agents/skills) is EXEMPT and stays on the page's eager sync. Ephemeral:
// hydrated files are recorded in an OPFS manifest and wiped on the next boot.
const _hydratedSet = new Set();       // rels hydrated this session (in-memory; the page owns persistence + flush)
const _hydrating = new Map();         // rel -> Promise (async hydration dedupe)
// Report an OPFS hydration to the page so it can record a sync-state entry
// (enables write-back of later edits) and flush the file on the next boot.
function _reportHydrated(rel) {
  try { self.postMessage({ type: 'forward-to-page', payload: { type: 'worker-hydrated', paths: [rel] } }); } catch (_) {}
}

function _relExempt(rel) {
  const r = String(rel).replace(/^\/+/, '').toLowerCase();
  return _dbxExempt.some(p => {
      const pl = String(p).toLowerCase();
      if (pl === 'sandpie/skills') {
        return r.startsWith(pl + '/') && r.split('/').pop() === 'skill.md';
      }
      return r === pl || r.startsWith(pl + '/');
    });
}
function _indexEntry(rel) {
  if (!_dehydrated || !_dbxIndex) return null;
  const r = String(rel).replace(/^\/+/, '');
  if (!r || _relExempt(r)) return null;
  const e = _dbxIndex[r];
  return (e && e.kind === 'file') ? e : null;
}
async function _opfsGetFile(rel) {
  const { parts, name } = splitPath(rel);
  const dir = await opfsResolveDir(parts);
  return (await dir.getFileHandle(name)).getFile();
}
function _cloudPathFor(rel, entry) {
  if (entry && entry.path) return entry.path;
  const root = (_dbxCtx && _dbxCtx.workingRoot) || '';
  return root + '/' + String(rel).replace(/^\/+/, '');
}
// Headers for WORKSPACE paths (home namespace — pathRoot is null in the current
// layout, so no path-root header). Pass team:true for team-space paths instead.
function _dbxHeaders(json, team) {
  const h = { Authorization: 'Bearer ' + (_dbxCtx && _dbxCtx.token) };
  if (json) h['Content-Type'] = 'application/json';
  const ns = _dbxCtx && (team ? _dbxCtx.teamRoot : _dbxCtx.pathRoot);
  if (ns) h['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: ns });
  return h;
}
// ============================================================
// BETA dbxfs — Dropbox IS the filesystem (/app-beta projects fork)
// ============================================================
// In beta the file tools operate DIRECTLY on Dropbox instead of the OPFS
// workspace: reads from anywhere in the user's Dropbox, writes/deletes limited
// by the harness to the conversation's project folder (ctx._projectRoot). OPFS
// keeps ONLY the sandpie/ app metadata (memory, skills, conversation JSONL) —
// those paths never enter this layer. Everything here uses the same CORS-open
// endpoints and the same ascii-safe Dropbox-API-Arg encoding as dropbox.js.
function _betaOn() { return !!(_dbxCtx && _dbxCtx.beta); }
// Dropbox-API-Arg is an HTTP header ⇒ must be ASCII. Escape non-ASCII as \uXXXX
// (Dropbox un-escapes server-side) or a path with accents 401s. See dropbox.js.
function _apiArg(obj) {
  return JSON.stringify(obj).replace(/[^\x00-\x7F]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}
// Auth + path-root headers for a beta call. `team` selects the namespace: the
// team-space root (so /R+D+I etc. are reachable) or the user's home namespace
// (no header). `json` adds the RPC Content-Type; content endpoints set their own.
function _betaHeaders(team, json) {
  const h = { Authorization: 'Bearer ' + (_dbxCtx && _dbxCtx.token) };
  if (json) h['Content-Type'] = 'application/json';
  const ns = team ? (_dbxCtx && _dbxCtx.teamRoot) : null;
  if (ns) h['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: ns });
  return h;
}
// fetch with pacing-lite: retry 429/5xx (and fetch-throws, which include
// CORS-masked 429s) with exponential backoff. Dropbox rate-limits hard and a
// 429 comes back WITHOUT CORS headers, surfacing as a network error.
async function _dbxFetch(url, opts, tries = 4) {
  let delay = 500;
  for (let i = 0; ; i++) {
    let res;
    try { res = await fetch(url, opts); }
    catch (e) { if (i >= tries) throw e; await new Promise(r => setTimeout(r, delay)); delay = Math.min(delay * 1.8, 8000); continue; }
    if ((res.status === 429 || res.status >= 500 || res.status === 408) && i < tries) {
      await new Promise(r => setTimeout(r, delay)); delay = Math.min(delay * 1.8, 8000); continue;
    }
    return res;
  }
}
// Metadata for an absolute Dropbox path, or null on not_found. Throws on other errors.
async function _dbxMeta(absPath, team) {
  const res = await _dbxFetch('https://api.dropboxapi.com/2/files/get_metadata', {
    method: 'POST', headers: _betaHeaders(team, true), body: JSON.stringify({ path: absPath }),
  });
  if (res.status === 409) return null;   // path/not_found
  if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('get_metadata ' + res.status + ': ' + t.slice(0, 200)); }
  return await res.json();
}
// Read-anywhere namespace fallback: try the project's namespace first, then the
// other on not_found. Returns { meta, team } or { meta: null } if truly absent.
async function _dbxMetaAnyNs(absPath, preferTeam) {
  let m = await _dbxMeta(absPath, preferTeam);
  if (m) return { meta: m, team: preferTeam };
  m = await _dbxMeta(absPath, !preferTeam);
  if (m) return { meta: m, team: !preferTeam };
  return { meta: null, team: preferTeam };
}
// Download bytes for an absolute Dropbox path (get_temporary_link → GET — the
// proven CORS path, same as hydrateAsync). `team` picks the namespace.
async function _dbxDownloadBytes(absPath, team) {
  const tl = await _dbxFetch('https://api.dropboxapi.com/2/files/get_temporary_link', {
    method: 'POST', headers: _betaHeaders(team, true), body: JSON.stringify({ path: absPath }),
  });
  if (!tl.ok) { const t = await tl.text().catch(() => ''); throw new Error('get_temporary_link ' + tl.status + ': ' + t.slice(0, 200)); }
  const link = (await tl.json()).link;
  const dl = await _dbxFetch(link, { method: 'GET' });
  if (!dl.ok) throw new Error('download ' + dl.status);
  return new Uint8Array(await dl.arrayBuffer());
}
// Upload bytes to an absolute Dropbox path (overwrite). `team` picks the namespace.
async function _dbxUpload(absPath, bytes, team) {
  const res = await _dbxFetch('https://content.dropboxapi.com/2/files/upload', {
    method: 'POST',
    headers: { ..._betaHeaders(team, false), 'Content-Type': 'application/octet-stream',
               'Dropbox-API-Arg': _apiArg({ path: absPath, mode: 'overwrite', mute: true, autorename: false }) },
    body: bytes,
  });
  if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('upload ' + res.status + ': ' + t.slice(0, 200)); }
  return await res.json();
}
// Delete an absolute Dropbox path (delete_v2, recursive for folders). not_found = no-op.
async function _dbxDelete(absPath, team) {
  const res = await _dbxFetch('https://api.dropboxapi.com/2/files/delete_v2', {
    method: 'POST', headers: _betaHeaders(team, true), body: JSON.stringify({ path: absPath }),
  });
  if (res.status === 409) return { ['.tag']: 'not_found' };
  if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('delete_v2 ' + res.status + ': ' + t.slice(0, 200)); }
  return await res.json();
}
// Create a folder (and parents implicitly via Dropbox). Ignores an existing folder.
async function _dbxMkdir(absPath, team) {
  const res = await _dbxFetch('https://api.dropboxapi.com/2/files/create_folder_v2', {
    method: 'POST', headers: _betaHeaders(team, true), body: JSON.stringify({ path: absPath, autorename: false }),
  });
  if (res.status === 409) return null;   // already exists
  if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('create_folder ' + res.status + ': ' + t.slice(0, 200)); }
  return await res.json();
}
// list_folder for an absolute Dropbox path, paginated + capped. Returns rows
// {path, kind:'file'|'directory', size, cloudMtime} with .capped. `team` picks ns.
async function _dbxListFolder(absPath, recursive, team) {
  const headers = _betaHeaders(team, true);
  const body = JSON.stringify({ path: absPath || '', recursive: !!recursive, include_mounted_folders: false, include_deleted: false, limit: 999 });
  let res = await _dbxFetch('https://api.dropboxapi.com/2/files/list_folder', { method: 'POST', headers, body });
  if (res.status === 409) { const rows = []; rows.notFound = true; return rows; }
  if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('list_folder ' + res.status + ': ' + t.slice(0, 200)); }
  let data = await res.json();
  let entries = data.entries || [];
  const LIST_CAP = recursive ? 1500 : 6000;
  while (data.has_more && entries.length < LIST_CAP) {
    res = await _dbxFetch('https://api.dropboxapi.com/2/files/list_folder/continue', { method: 'POST', headers, body: JSON.stringify({ cursor: data.cursor }) });
    if (!res.ok) break;
    data = await res.json();
    entries = entries.concat(data.entries || []);
  }
  const capped = !!data.has_more;
  if (entries.length > LIST_CAP) entries = entries.slice(0, LIST_CAP);
  const rows = entries.map(e => ({ path: e.path_display || e.path_lower, kind: e['.tag'] === 'folder' ? 'directory' : 'file', size: e.size, cloudMtime: e.client_modified }));
  rows.capped = capped;
  return rows;
}
// Copy src → dest. Same namespace: copy_v2 (cheap, server-side). Cross namespace:
// download the bytes then upload into dest (a folder-copy across namespaces is
// refused; the tool reports that).
async function _dbxCopy(srcAbs, srcTeam, destAbs, destTeam, isFolder) {
  if (srcTeam === destTeam) {
    const res = await _dbxFetch('https://api.dropboxapi.com/2/files/copy_v2', {
      method: 'POST', headers: _betaHeaders(srcTeam, true), body: JSON.stringify({ from_path: srcAbs, to_path: destAbs, autorename: true }),
    });
    if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('copy_v2 ' + res.status + ': ' + t.slice(0, 200)); }
    return (await res.json()).metadata || {};
  }
  if (isFolder) throw new Error('cross-namespace folder copy is not supported — copy individual files.');
  const bytes = await _dbxDownloadBytes(srcAbs, srcTeam);
  await _dbxUpload(destAbs, bytes, destTeam);
  return { path_display: destAbs, size: bytes.byteLength };
}
// ---- beta path resolution + write guard ----
// The conversation's project folder, with a fallback to the personal workspace
// (workingRoot) so a chat that was never assigned a project (a legacy chat, the
// "Personal" default) still works instead of hard-erroring. Returns '' only if
// Dropbox isn't resolved yet.
function _projectRootFor(ctx) {
  if (ctx && ctx._projectRoot) return String(ctx._projectRoot).replace(/\/+$/, '');
  const wr = (_dbxCtx && _dbxCtx.workingRoot) ? String(_dbxCtx.workingRoot).replace(/\/+$/, '') : '';
  return wr;
}
function _projectTeamFor(ctx) {
  // An explicit project carries its own namespace; the workspace fallback is home.
  return !!(ctx && ctx._projectRoot && ctx._projectNs === 'team');
}
// Resolve a raw tool path arg for beta. Returns one of:
//   { kind:'opfs', rel }               → sandpie/ app metadata (unchanged OPFS path)
//   { kind:'dbx', path, team, abs }     → an absolute Dropbox path (read anywhere)
//   { kind:'noproject' }               → relative path but no project AND no workspace
function _betaResolve(raw, ctx) {
  const s = String(raw == null ? '' : raw).trim();
  const relForm = s.replace(/^\/+/, '').replace(/^files\//, '');
  if (relForm === 'sandpie' || relForm.startsWith('sandpie/')) return { kind: 'opfs', rel: relForm };
  const projTeam = _projectTeamFor(ctx);
  if (s.startsWith('/')) return { kind: 'dbx', path: s.replace(/\/+$/, ''), team: projTeam, abs: true };
  const proj = _projectRootFor(ctx);
  if (!proj) return { kind: 'noproject' };
  const clean = relForm.replace(/\/+$/, '');
  return { kind: 'dbx', path: clean ? proj + '/' + clean : proj, team: projTeam, abs: false, rel: clean };
}
// Is an absolute Dropbox path inside the conversation's project folder?
function _betaUnderProject(absPath, ctx) {
  const proj = _projectRootFor(ctx).toLowerCase();
  if (!proj) return false;
  const p = String(absPath).replace(/\/+$/, '').toLowerCase();
  return p === proj || p.startsWith(proj + '/');
}
// The harness write boundary (requirement 6): writes/deletes must stay inside the
// project folder. Returns an error string to hand back to the model, or null if ok.
function _betaWriteGuard(absPath, ctx) {
  const proj = _projectRootFor(ctx);
  if (!proj) return 'Dropbox is still connecting — try again in a moment.';
  if (!_betaUnderProject(absPath, ctx)) return 'Refused: writes are limited to this conversation\'s project folder "' + proj + '". "' + absPath + '" is outside it. You can READ anywhere, but to write it elsewhere, copy it into the project first.';
  return null;
}
// Record a beta WRITE as a touched file (turn-end "created/edited" card) and ping
// the page to refresh its live Dropbox view. No OPFS write happened, so nothing to
// invalidate in the render cache here.
function _betaTouch(ctx, absPath) {
  try { if (ctx && ctx._filesTouched) ctx._filesTouched.set(absPath, Date.now()); } catch (_) {}
  try { self.postMessage({ type: 'forward-to-page', payload: { type: 'beta-fs-changed', paths: [absPath], owner: ctx && ctx.agentId } }); } catch (_) {}
}
// A beta DELETE is NOT a "created/edited" file: drop it from the touched set (in
// case it was created earlier this turn) and signal a deletion so any card is
// removed — never let a delete surface as an edit.
function _betaUntouch(ctx, absPath) {
  try { if (ctx && ctx._filesTouched) ctx._filesTouched.delete(absPath); } catch (_) {}
  try { self.postMessage({ type: 'forward-to-page', payload: { type: 'opfs-deleted-by-python', paths: [absPath], owner: ctx && ctx.agentId } }); } catch (_) {}
}

// Async hydration (file tools): get_temporary_link RPC → GET the link → OPFS.
// Mirrors dropbox.js download() — the documented CORS-enabled browser path.
async function hydrateAsync(rel) {
  const entry = _indexEntry(rel);
  if (!entry) return false;
  if (_hydrating.has(rel)) return _hydrating.get(rel);
  const job = (async () => {
    const tlRes = await fetch('https://api.dropboxapi.com/2/files/get_temporary_link', { method: 'POST', headers: _dbxHeaders(true), body: JSON.stringify({ path: _cloudPathFor(rel, entry) }) });
    if (!tlRes.ok) throw new Error('get_temporary_link ' + tlRes.status);
    const dl = await fetch((await tlRes.json()).link, { method: 'GET' });
    if (!dl.ok) throw new Error('download ' + dl.status);
    await opfsWriteBytes(rel, new Uint8Array(await dl.arrayBuffer()));
    _hydratedSet.add(rel); _reportHydrated(rel);
    return true;
  })();
  _hydrating.set(rel, job);
  try { return await job; } finally { _hydrating.delete(rel); }
}
// The synchronous run_python fault-in (blocking XHR + open() audit hook) now
// lives in pyodide-worker.js, which owns the interpreter. This worker keeps only
// the ASYNC hydration above, used by the file tools (read_file/load_image/etc).

// Build a directory listing from the cloud index (no download) for list_files.
function _indexEntriesUnder(norm, recursive) {
  if (!_dehydrated || !_dbxIndex) return [];
  const base = norm ? String(norm).replace(/^\/+|\/+$/g, '') : '';
  const basePrefix = base ? base + '/' : '';
  const bpl = basePrefix.toLowerCase();
  const out = [], dirs = new Set();
  for (const rel0 of Object.keys(_dbxIndex)) {
    const rel = rel0.replace(/^\/+/, '');
    if (_relExempt(rel)) continue;
    if (basePrefix && !rel.toLowerCase().startsWith(bpl)) continue;
    const sub = basePrefix ? rel.slice(basePrefix.length) : rel;
    if (!sub) continue;
    const slash = sub.indexOf('/');
    if (!recursive && slash >= 0) { dirs.add(basePrefix + sub.slice(0, slash)); continue; }
    const e = _dbxIndex[rel0];
    out.push({ path: rel, kind: e.kind === 'folder' ? 'directory' : 'file', size: e.size, cloudMtime: e.cloudMtime });
  }
  for (const d of dirs) out.push({ path: d, kind: 'directory' });
  return out;
}
// Flushing last session's hydrated copies is now PAGE-side (dropbox
// dehydratePurge() on boot) — it knows sync state, so it can skip files with
// unsynced edits. The worker no longer persists a manifest or wipes on boot.

// The FS.trackingDelegate write-back capture and the OPFS delete helpers now
// live in pyodide-worker.js alongside the interpreter that drives them.

// ============================================================
// Tool implementations
// ============================================================
const MAX_TOOL_RESULT_BYTES = 30 * 1024;
// Monotonic counter for fallback tool_call_ids (avoid duplicates across rounds).
let _toolCallSeq = 0;
function truncateToolResult(result) {
  if (typeof result !== 'string') { try { result = JSON.stringify(result); } catch { result = String(result); } }
  const bytes = new TextEncoder().encode(result);
  if (bytes.length <= MAX_TOOL_RESULT_BYTES) return result;
  return new TextDecoder().decode(bytes.slice(0, MAX_TOOL_RESULT_BYTES)) + "\n\n[truncated: tool result exceeded 30kB]";
}

// run_python now runs on the Pyodide worker pool (see the pool manager above).
// Dispatching to a separate thread keeps this thread free — other conversations
// keep streaming — and lets several scripts run in parallel. The pool worker
// owns file-read/hydration, capture write-back, and error formatting; it also
// posts opfs-deleted-by-python / sw-opfs-changed back through the manager relay.
async function tool_run_python({ path, code, args, timeout }, ctx) {
  // BETA REPL: `code` runs directly (no saved script). Falls back to `path` for a
  // real saved script. On /app, only `path` is offered (code is ignored).
  const hasCode = _betaOn() && typeof code === 'string' && code.trim() !== '';
  if (!path && !hasCode) return { result: _betaOn() ? 'Error: pass `code` to run Python directly, or `path` to run a saved script.' : 'Error: "path" is required. Save a script with write_file first, then call run_python with its path.' };
  // A script can write or delete any files (os.remove, doc.save, _cleanup.py, …)
  // that the worker never sees individually, so drop the whole read/refusal cache:
  // a stale "unchanged, work from your copy" stub for a file Python just rewrote or
  // deleted is exactly what sent an earlier session into a rebuild loop. The cache
  // is tiny; over-clearing only costs one honest re-emit on the next read.
  _emittedFileHashes.clear();
  // BETA: the script + its data live in the project folder on Dropbox, not OPFS.
  // Pass the project (falling back to the personal workspace for an unassigned
  // chat) so the Pyodide runner reads the entry script, faults in reads, and
  // writes outputs against <projectRoot>/… instead of the empty OPFS mount.
  let betaProject = null;
  if (_betaOn()) {
    const root = _projectRootFor(ctx);
    if (!root) return { result: 'Error: Dropbox is still connecting — try run_python again in a moment.' };
    betaProject = { root, team: _projectTeamFor(ctx) };
  }
  return dispatchPython({ path, code: hasCode ? code : null, args, timeout, signal: ctx && ctx.signal, owner: ctx && ctx.agentId, betaProject });
}

// ============================================================
// web_search / read_url — public-web access for the model (agentic: the model
// calls these as ordinary tools whenever it wants current information).
// web_search is two-tier:
//   1) PRIMARY — OpenRouter web search (Exa): config.webSearch carries
//      endpoint+key whenever any configured provider is OpenRouter. One cheap
//      non-streaming completion with the `web` plugin; the plugin's search
//      results come back as url_citation annotations and THOSE are returned
//      (title/url/snippet) — the helper model's own text is discarded, so this
//      is a pure search backend for the calling model, not RAG.
//   2) FALLBACK — the multi-engine scrape (DuckDuckGo → DDG-Lite → Brave →
//      Bing → Mojeek) through the user's own /proxy/ route, parsed with bs4 on
//      the Pyodide pool. Used when no OpenRouter key is configured, or the
//      OpenRouter call fails / returns nothing.
// read_url fetches ANY page via /proxy/ and returns its readable text.
// ============================================================
const _WEB_SEARCH_PY = `import json, re, sys, urllib.parse, asyncio
from pyodide.http import pyfetch
from bs4 import BeautifulSoup

_a = json.loads(sys.argv[1])
_QUERY = (_a.get("query") or "").strip()
_N = max(1, min(int(_a.get("n") or 8), 20))
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

def _txt(el, limit=320):
    if not el: return ""
    return " ".join(el.get_text(" ", strip=True).split())[:limit]

def _unwrap(href):
    if not href: return ""
    if href.startswith("//"): href = "https:" + href
    m = re.search(r"[?&](?:uddg|u)=([^&]+)", href)
    if m:
        try: return urllib.parse.unquote(m.group(1))
        except Exception: pass
    return href

def _looks_blocked(html):
    low = html[:5000].lower()
    return any(s in low for s in ("captcha", "challenge-form", "unusual traffic",
                                  "are you a robot", "/sorry/", "detected unusual"))

async def _fetch(url):
    resp = await asyncio.wait_for(
        pyfetch(url, headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}),
        timeout=12)
    if resp.status != 200: return None
    return await resp.string()

def _p_ddg_html(html):
    s = BeautifulSoup(html, "html.parser"); out = []
    for r in s.find_all("div", class_="result"):
        a = r.find("a", class_="result__a")
        if not a: continue
        out.append({"title": _txt(a, 200), "url": _unwrap(a.get("href", "")),
                    "snippet": _txt(r.find("a", class_="result__snippet"))})
    return out

def _p_ddg_lite(html):
    s = BeautifulSoup(html, "html.parser"); out = []
    links = s.select("a.result-link")
    snips = [_txt(td) for td in s.select("td.result-snippet")]
    for i, a in enumerate(links):
        out.append({"title": _txt(a, 200), "url": _unwrap(a.get("href", "")),
                    "snippet": snips[i] if i < len(snips) else ""})
    return out

def _p_brave(html):
    s = BeautifulSoup(html, "html.parser"); out = []
    for d in s.select("div[data-pos], div.snippet"):
        a = d.find("a", href=True)
        if not a: continue
        t = d.select_one(".title, .snippet-title, .url") or a
        out.append({"title": _txt(t, 200), "url": a.get("href", ""),
                    "snippet": _txt(d.select_one(".snippet-description, .snippet-content, p"))})
    return out

def _unwrap_bing(href):
    # bing.com/ck/a?...&u=a1<base64url>... redirect -> the real URL
    m = re.search(r"bing\\.com/ck/.*[?&]u=a1([A-Za-z0-9_-]+)", href or "")
    if not m: return href
    try:
        import base64
        raw = m.group(1); raw += "=" * (-len(raw) % 4)
        u = base64.urlsafe_b64decode(raw).decode("utf-8", "replace")
        return u if u.startswith("http") else href
    except Exception:
        return href

def _p_bing(html):
    s = BeautifulSoup(html, "html.parser"); out = []
    for li in s.select("li.b_algo"):
        a = li.select_one("h2 a") or li.find("a", href=True)
        if not a: continue
        out.append({"title": _txt(a, 200), "url": _unwrap_bing(a.get("href", "")),
                    "snippet": _txt(li.select_one(".b_caption p") or li.find("p"))})
    return out

def _p_mojeek(html):
    s = BeautifulSoup(html, "html.parser"); out = []
    for li in s.select("ul.results-standard li"):
        a = li.select_one("h2 a") or li.find("a", href=True)
        if not a: continue
        out.append({"title": _txt(a, 200), "url": a.get("href", ""),
                    "snippet": _txt(li.select_one("p.s") or li.find("p"))})
    return out

_ENGINES = [
    ("duckduckgo",      "/proxy/html.duckduckgo.com/html/?q={q}",      _p_ddg_html),
    ("duckduckgo-lite", "/proxy/lite.duckduckgo.com/lite/?q={q}",      _p_ddg_lite),
    ("brave",           "/proxy/search.brave.com/search?q={q}",        _p_brave),
    ("bing",            "/proxy/www.bing.com/search?q={q}&setlang=en", _p_bing),
    ("mojeek",          "/proxy/www.mojeek.com/search?q={q}",          _p_mojeek),
]

def _valid(r):
    u = r.get("url", "")
    return bool(r.get("title")) and u.startswith("http") and "duckduckgo.com/l/" not in u

def _dedupe(rows):
    seen = set(); out = []
    for r in rows:
        k = re.sub(r"#.*$", "", r["url"]).rstrip("/")
        if k in seen: continue
        seen.add(k); out.append(r)
    return out

async def _run():
    if not _QUERY:
        return {"error": "empty query", "results": [], "tried": []}
    q = urllib.parse.quote(_QUERY)
    tried = []
    for name, tmpl, parse in _ENGINES:
        try:
            html = await _fetch(tmpl.format(q=q))
        except Exception as e:
            tried.append("%s: fetch error (%s)" % (name, type(e).__name__)); continue
        if not html:
            tried.append("%s: no/non-200 response" % name); continue
        if _looks_blocked(html):
            tried.append("%s: blocked/captcha page" % name); continue
        try:
            rows = _dedupe([r for r in parse(html) if _valid(r)])
        except Exception as e:
            tried.append("%s: parse error (%s)" % (name, type(e).__name__)); continue
        if rows:
            return {"engine": name, "query": _QUERY, "results": rows[:_N], "tried": tried}
        tried.append("%s: 0 results" % name)
    return {"engine": None, "query": _QUERY, "results": [], "tried": tried}

_out = await _run()
print("<<<WSJSON>>>" + json.dumps(_out))
`;

const _READ_URL_PY = `import json, re, sys
from pyodide.http import pyfetch
from bs4 import BeautifulSoup

_a = json.loads(sys.argv[1])
_URL = (_a.get("url") or "").strip()
_CAP = max(500, min(int(_a.get("cap") or 8000), 40000))
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

async def _run():
    if not _URL:
        return {"error": "empty url"}
    proxied = "/proxy/" + re.sub(r"^https?://", "", _URL)
    try:
        resp = await pyfetch(proxied, headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"})
    except Exception as e:
        return {"error": "fetch error (%s)" % type(e).__name__}
    if resp.status != 200:
        return {"error": "HTTP %s" % resp.status}
    ctype = ""
    try: ctype = (resp.headers.get("content-type") or "").lower()
    except Exception: pass
    html = await resp.string()
    if "html" in ctype or "<html" in html[:2000].lower():
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript", "header", "footer", "nav",
                       "aside", "form", "svg", "iframe"]):
            t.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        body = re.sub(r"\\n{3,}", "\\n\\n", main.get_text("\\n", strip=True))
        title = soup.title.get_text(strip=True) if soup.title else _URL
    else:
        body = html
        title = _URL
    return {"url": _URL, "title": title, "text": body[:_CAP], "total": len(body)}

_r = await _run()
print("<<<WSJSON>>>" + json.dumps(_r))
`;

// Run one of the embedded web scripts on the Pyodide pool: write it under
// sandpie/scripts/ (same convention as the docx-localization helpers), dispatch
// with the JSON args as argv[1], and parse the <<<WSJSON>>> marker line out of
// the captured stdout (stderr noise like pyfetch HTTP logs may precede it).
async function _webPyRun(fileName, code, argsObj, timeoutS, ctx) {
  const path = 'sandpie/scripts/' + fileName;
  await opfsWriteBytes(path, new TextEncoder().encode(code));
  const ex = await dispatchPython({ path, args: [JSON.stringify(argsObj)], timeout: timeoutS,
                                    signal: ctx && ctx.signal, owner: ctx && ctx.agentId });
  const raw = String((ex && ex.result) || '');
  const m = raw.lastIndexOf('<<<WSJSON>>>');
  if (m < 0) throw new Error(raw.slice(0, 300) || 'no output');
  const line = raw.slice(m + 12);
  const nl = line.indexOf('\n');
  return JSON.parse(nl >= 0 ? line.slice(0, nl) : line);
}

// PRIMARY backend: OpenRouter's Exa-backed `web` plugin. One non-streaming
// completion on a cheap helper model; the plugin attaches the raw search
// results as url_citation annotations, which are returned as {title,url,
// snippet} — the helper's answer text is ignored. Returns null when no
// OpenRouter provider is configured; throws on any request failure so the
// caller can fall back to the scrape chain.
async function _webSearchOpenRouter(query, n, ctx) {
  const ws = ctx && ctx._agentConfig && ctx._agentConfig.webSearch;
  if (!ws || !ws.url || !ws.apiKey) return null;
  let signal = ctx && ctx.signal;
  try {   // cap the search call at 30s without detaching from the turn's abort
    const t = AbortSignal.timeout(30000);
    signal = signal ? AbortSignal.any([signal, t]) : t;
  } catch (_) {}
  const body = {
    model: ws.model,
    messages: [{ role: 'user', content: String(query) }],
    plugins: [{ id: 'web', max_results: n }],
    max_tokens: 64, stream: false,
    session_id: 'WebSearch:' + (ctx && ctx._sessionId),   // parent-session marker (same convention as the localizer)
  };
  const r = await fetch(ws.url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ws.apiKey },
    body: JSON.stringify(body), signal,
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    throw new Error('HTTP ' + r.status + (txt ? ' — ' + txt.replace(/\s+/g, ' ').slice(0, 200) : ''));
  }
  const j = await r.json();
  if (j && j.error) throw new Error(String((j.error && j.error.message) || JSON.stringify(j.error)).slice(0, 200));
  const msg = j && j.choices && j.choices[0] && j.choices[0].message;
  const anns = (msg && Array.isArray(msg.annotations)) ? msg.annotations : [];
  const seen = new Set(); const out = [];
  for (const a of anns) {
    const c = a && a.type === 'url_citation' && a.url_citation;
    if (!c || !c.url || !/^https?:/i.test(String(c.url))) continue;
    const k = String(c.url).replace(/#.*$/, '').replace(/\/$/, '');
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ title: String(c.title || c.url).slice(0, 200), url: String(c.url),
               snippet: String(c.content || '').replace(/\s+/g, ' ').trim().slice(0, 320) });
  }
  return out.slice(0, n);
}

function _wsFormat(query, engine, results, notes) {
  const lines = results.map((r, i) => `${i + 1}. ${r.title}\n   ${r.url}${r.snippet ? '\n   ' + r.snippet : ''}`);
  return `Web results for "${query}" (via ${engine}):\n\n${lines.join('\n\n')}`
    + (notes ? '\n\n' + notes : '')
    + `\n\nTo read a result's full page text, call read_url with its URL.`;
}

async function tool_web_search({ query, num_results }, ctx) {
  const q = String(query || '').trim();
  if (!q) return { result: 'Error: "query" is required (plain keywords).' };
  const n = Math.max(1, Math.min(parseInt(num_results, 10) || 8, 20));
  // 1) OpenRouter (Exa) — grounded results, immune to engine blocking/captchas.
  let orNote = '';
  try {
    const or = await _webSearchOpenRouter(q, n, ctx);
    if (or && or.length) return { result: _wsFormat(q, 'OpenRouter web search / Exa', or) };
    if (or) orNote = 'OpenRouter web search returned no results; fell back to direct engine scraping.';
  } catch (e) {
    if (ctx && ctx.signal && ctx.signal.aborted) return { result: 'Error: web_search aborted — the turn was stopped.' };
    orNote = 'OpenRouter web search failed (' + (((e && e.message) || String(e)).slice(0, 200)) + '); fell back to direct engine scraping.';
    try { console.warn('[web_search] ' + orNote); } catch (_) {}
  }
  // 2) Fallback: multi-engine /proxy/ scrape on the Pyodide pool.
  try {
    const data = await _webPyRun('_web_search.py', _WEB_SEARCH_PY, { query: q, n }, 75, ctx);
    if (!data.results || !data.results.length) {
      const why = (data.tried && data.tried.length) ? '\nEngines tried:\n- ' + data.tried.join('\n- ') : '';
      return { result: `No web results for "${q}".${orNote ? '\n' + orNote : ''}${why}\n(If every engine was blocked or unreachable, the /proxy/ route may be unavailable in this deployment.)` };
    }
    return { result: _wsFormat(q, data.engine, data.results, orNote) };
  } catch (e) {
    const msg = ((e && e.message) || String(e)).slice(0, 300);
    return { result: 'Error during web_search: ' + msg + (orNote ? '\n(' + orNote + ')' : '') };
  }
}

async function tool_read_url({ url, max_chars }, ctx) {
  if (!url || !String(url).trim()) return { result: 'Error: "url" is required.' };
  try {
    const data = await _webPyRun('_read_url.py', _READ_URL_PY, { url: String(url).trim(), cap: max_chars }, 60, ctx);
    if (data.error) return { result: `Could not read ${url}: ${data.error}.\n(The page is fetched via /proxy/; it may be unavailable, blocked, or non-HTML.)` };
    const head = data.title ? `# ${data.title}\n${data.url}\n\n` : `${data.url}\n\n`;
    const more = (data.total > (data.text || '').length)
      ? `\n\n…(showing ${(data.text || '').length} of ${data.total} chars; call read_url again with a larger max_chars to read more)` : '';
    return { result: head + (data.text || '') + more };
  } catch (e) {
    return { result: 'Error during read_url: ' + (((e && e.message) || String(e)).slice(0, 300)) };
  }
}

// ============================================================




// A model-managed checklist as a FLAT task list with deterministic, id-based ops
// (modelled on the Claude Agent SDK Task tools). There is NO blind full-replace
// (that let the model silently overwrite/erase the list — measured 146 vanished
// items / 80 lost completions in one session), so the checklist cannot be
// clobbered. States: pending → in_progress → completed (terminal); any open task
// → deleted (removed). Ordering is expressed by a `blockedBy` dependency list,
// NOT by nesting: a task with an open blocker cannot start. The list lives on
// ctx._todoTree (seeded from config.todos each turn) and is echoed as a 'todos:'
// payload the page renders + persists.
const _TODO_OPEN = new Set(['pending', 'in_progress']);   // stop-guard: only these keep the turn alive
const _TODO_UNSAT = new Set(['pending', 'in_progress', 'blocked']);   // dependency gate: a blocked task is not done
const _TODO_ALL = ['pending', 'in_progress', 'completed', 'blocked', 'deleted'];
function _todoNextId(tree) { let mx = 0; for (const t of tree) { const n = parseInt(t.id, 10); if (n > mx) mx = n; } return String(mx + 1); }
function _todoBlockers(t, byId) { return (Array.isArray(t.blockedBy) ? t.blockedBy : []).filter(id => { const b = byId.get(id); return b && _TODO_UNSAT.has(b.status); }); }
function _todoFlat(tree) { return tree.map(t => ({ content: t.content, status: t.status, created: t.created, completed: t.completed, blockedBy: t.blockedBy, activeForm: t.activeForm, reason: t.reason, est: t.est })); }
// Clamp a model-declared call estimate: a positive integer, capped so a wild
// guess can't render hundreds of placeholder cells. 0 = no estimate.
function _todoEst(v) { const n = Math.round(+v); return Number.isFinite(n) && n > 0 ? Math.min(n, 200) : 0; }
function _todoSummary(tree) {
  const byId = new Map(tree.map(t => [t.id, t]));
  const mark = s => s === 'completed' ? '[x]' : s === 'in_progress' ? '[~]' : s === 'blocked' ? '[!]' : s === 'deleted' ? '[-]' : '[ ]';
  return tree.filter(t => t.status !== 'deleted').map(t => {
    const open = _todoBlockers(t, byId);
    return mark(t.status) + ' ' + t.id + ' ' + t.content
      + (t.status === 'blocked' && t.reason ? ' — ' + t.reason : '')
      + (open.length ? ' (blocked by ' + open.join(', ') + ')' : '');
  }).join('\n');
}
async function tool_write_todos({ todos }, ctx) {
  const tree = (ctx && Array.isArray(ctx._todoTree)) ? ctx._todoTree : (ctx ? (ctx._todoTree = []) : []);
  const now = new Date().toISOString();
  const byId = new Map(tree.map(t => [t.id, t]));
  const openCount = () => tree.filter(t => _TODO_OPEN.has(t.status)).length;
  // Change signature (id:status:content of live tasks) — lets us detect a call
  // that changed NOTHING and answer with a state-aware reply instead of an
  // error string, so a model doesn't keep retrying an identical no-op forever.
  const _sigOf = () => tree.filter(t => t.status !== 'deleted').map(t => t.id + ':' + t.status + ':' + String(t.content || '').trim().toLowerCase().replace(/\s+/g, ' ')).sort().join('|');
  const _sigBefore = _sigOf();
  const _norm = s => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');
  // Fuzzy content match (token containment): a REWORDED resend of an existing task
  // must map to it, not create a duplicate. Measured production failure (2026-08-28):
  // the model reworded its finished plan -> exact-match missed -> the plan was
  // resurrected as pending duplicates -> the stop guard + plan-first gate trapped it
  // in a no-op write_todos loop (7 wasted ~130k-token rounds). Containment
  // (intersection over the SMALLER token set) so an abbreviated resend still matches.
  const _toks = s => { const st = new Set(); for (const w of _norm(s).split(' ')) if (w.length > 2) st.add(w); return st; };
  const _fuzzy = (content, cands) => {
    const a = _toks(content); if (!a.size) return null;
    let best = null, bs = 0;
    for (const t of cands) {
      const b = _toks(t.content); if (!b.size) continue;
      let inter = 0; for (const w of a) if (b.has(w)) inter++;
      const score = inter / Math.min(a.size, b.size);
      if (score > bs) { bs = score; best = t; }
    }
    return bs >= 0.6 ? best : null;
  };
  // Auto-advance: if nothing is in_progress, promote the first unblocked pending
  // task. Kills the mandatory extra bookkeeping round the plan-first gate used to
  // force after every completion (complete task -> gate hides tools -> model had to
  // call write_todos AGAIN just to start the next one).
  const _autoAdvance = () => {
    if (tree.some(t => t.status === 'in_progress')) return null;
    const m = new Map(tree.map(t => [t.id, t]));
    const next = tree.find(t => t.status === 'pending' && !_todoBlockers(t, m).length);
    if (!next) return null;
    next.status = 'in_progress'; delete next.completed; delete next.reason;
    return next;
  };
  // Shared closer: single-active rule, auto-advance, then a state-aware result.
  const _finish = (headline, notes) => {
    let activeSeen = false;
    for (const t of tree) { if (t.status === 'in_progress') { if (activeSeen) t.status = 'pending'; else activeSeen = true; } }
    const adv = _autoAdvance();
    if (ctx) ctx._todos = _todoFlat(tree);
    const done = tree.filter(t => t.status === 'completed').length;
    const live = tree.filter(t => t.status !== 'deleted').length;
    let out = 'todos:' + JSON.stringify(tree) + '\n' + headline + ' (' + done + ' done, ' + openCount() + ' open, ' + live + ' total):\n' + _todoSummary(tree);
    if (adv) out += '\n\nAuto-started task ' + adv.id + ' ("' + adv.content + '") — it is in_progress and your full toolset is available. Do the work now; touch the checklist again only when a status actually changes.';
    if (!openCount()) out += '\n\nChecklist COMPLETE — nothing open. Do NOT call write_todos again: deliver your final answer with respond() now (add tasks only if the user asked for genuinely new work).';
    for (const n of (notes || [])) out += '\n' + n;
    return { result: out };
  };

  if (!Array.isArray(todos)) {
    return { result: 'Error: send {"todos":[…]}. Two forms: (1) FULL LIST — items {"content":"…","status":"pending|in_progress|completed|blocked","activeForm":"…","est":N,"reason":"…"}, reconciled to the existing checklist (matched by id, then content — reworded content still matches; open tasks you omit are dropped and reported); (2) DELTA — items {"id":"…","status":"…"} with NO content flip statuses only and never drop anything (cheapest way to advance). At most ONE task in_progress; when none is, the first unblocked pending task auto-starts.' };
  }

  // ── DELTA form: every item is {id, status} with no content -> status flips only.
  //    Nothing is added, dropped, or re-typed — one status change costs ~20 output
  //    tokens instead of re-generating the whole list (~500+ tokens ≈ 5-8s decode).
  const isDelta = todos.length > 0 && todos.every(t => t && t.id != null && !(typeof t.content === 'string' && t.content.trim()));
  if (isDelta) {
    if (!tree.length) return { result: 'Error: no checklist exists yet — send the full-list form first ({"todos":[{"content":…,"status":…}]}).' };
    const notes = [];
    for (const inc of todos) {
      const ex = byId.get(String(inc.id));
      if (!ex || ex.status === 'deleted') { notes.push('Unknown id ignored: ' + String(inc.id) + '.'); continue; }
      const st = _TODO_ALL.includes(inc.status) ? inc.status : null;
      if (!st) { notes.push('Task ' + ex.id + ': invalid status ignored.'); continue; }
      if (ex.status === 'completed' && st !== 'completed') { notes.push('Task ' + ex.id + ' is already completed — left completed.'); continue; }
      ex.status = st;
      if (st === 'completed') ex.completed = now; else delete ex.completed;
      if (st === 'blocked') { const r = inc.reason ? String(inc.reason).trim() : ''; if (r) ex.reason = r; else delete ex.reason; } else delete ex.reason;
    }
    return _finish('Checklist updated', notes);
  }

  // ── FULL-LIST form. An existing checklist (even a fully completed one) is
  //    RECONCILED — never wiped and rebuilt: completed history survives, and a
  //    resend of finished work maps back to the completed tasks instead of
  //    resurrecting the plan as pending duplicates.
  if (tree.length) {
    const byContent = new Map();
    for (const t of tree) if (t.status !== 'deleted') { const k = _norm(t.content); if (!byContent.has(k)) byContent.set(k, t); }
    const matched = new Set(); const order = []; const addedIds = []; const alreadyDone = [];
    for (const inc of todos) {
      const content = inc && typeof inc.content === 'string' ? inc.content.trim() : '';
      const incStatus = _TODO_ALL.includes(inc && inc.status) ? inc.status : null;
      // A content-less {id,status} item inside a full list = inline delta on that task.
      if (!content) {
        if (inc && inc.id != null && byId.has(String(inc.id)) && byId.get(String(inc.id)).status !== 'deleted' && !matched.has(String(inc.id))) {
          const ex = byId.get(String(inc.id));
          matched.add(ex.id);
          if (incStatus && incStatus !== ex.status && !(ex.status === 'completed' && incStatus !== 'completed')) {
            ex.status = incStatus;
            if (incStatus === 'completed') ex.completed = now; else delete ex.completed;
            if (incStatus === 'blocked') { const r = inc.reason ? String(inc.reason).trim() : ''; if (r) ex.reason = r; else delete ex.reason; } else delete ex.reason;
          }
          order.push(ex);
        }
        continue;
      }
      let ex = null;
      if (inc && inc.id != null && byId.has(String(inc.id)) && byId.get(String(inc.id)).status !== 'deleted' && !matched.has(String(inc.id))) ex = byId.get(String(inc.id));
      if (!ex) { const c = byContent.get(_norm(content)); if (c && !matched.has(c.id)) ex = c; }
      if (!ex) ex = _fuzzy(content, tree.filter(t => t.status !== 'deleted' && !matched.has(t.id)));
      if (ex) {
        matched.add(ex.id);
        // Keep a completed task's recorded content — a reworded resend must not
        // rewrite history it merely paraphrased.
        if (ex.status !== 'completed') ex.content = content;
        if (inc && typeof inc.activeForm === 'string' && inc.activeForm.trim()) ex.activeForm = inc.activeForm.trim();
        { const e = _todoEst(inc && inc.est); if (e) ex.est = e; }
        // Apply the incoming status, but NEVER un-complete a completed task.
        if (incStatus && incStatus !== ex.status) {
          if (ex.status === 'completed') { alreadyDone.push(ex.id); }
          else {
            ex.status = incStatus;
            if (incStatus === 'completed') ex.completed = now; else delete ex.completed;
            if (incStatus === 'blocked') { const r = inc.reason ? String(inc.reason).trim() : ''; if (r) ex.reason = r; else delete ex.reason; } else delete ex.reason;
          }
        }
        order.push(ex);
      } else {
        const task = { id: _todoNextId(tree), content, status: incStatus || 'pending', created: now };
        if (inc && typeof inc.activeForm === 'string' && inc.activeForm.trim()) task.activeForm = inc.activeForm.trim();
        { const e = _todoEst(inc && inc.est); if (e) task.est = e; }
        if (task.status === 'completed') task.completed = now;
        if (task.status === 'blocked' && inc && inc.reason) task.reason = String(inc.reason).trim();
        tree.push(task); byId.set(task.id, task); order.push(task); addedIds.push(task.id);
      }
    }
    // A full-list replacement is authoritative: open tasks the new list omits are
    // DROPPED (marked deleted + detached from blockers) and reported, so a clobber
    // is never silent. Completed tasks stay on the record.
    const dropped = [];
    for (const t of tree) {
      if (t.status === 'deleted' || matched.has(t.id) || order.includes(t)) continue;
      if (_TODO_OPEN.has(t.status)) {
        t.status = 'deleted'; t.deleted = now;
        for (const x of tree) if (Array.isArray(x.blockedBy)) x.blockedBy = x.blockedBy.filter(id => id !== t.id);
        dropped.push(t.id);
      } else {
        order.push(t);
      }
    }
    // Rebuild in reconciled order (ids stay stable), deleted tasks kept on record.
    const deletedTasks = tree.filter(t => t.status === 'deleted');
    tree.length = 0; tree.push(...order, ...deletedTasks);
    if (!tree.filter(t => t.status !== 'deleted').length) return { result: 'Error: empty checklist — send at least one task.' };
    const notes = [];
    if (addedIds.length) notes.push('Added task(s): ' + addedIds.join(', ') + '.');
    if (alreadyDone.length) notes.push('Note: ' + alreadyDone.length + ' task(s) you sent as open are ALREADY COMPLETED (' + alreadyDone.join(', ') + ') — they stay completed; do not resend them.');
    if (dropped.length) notes.push('DROPPED ' + dropped.length + ' open task(s) this replacement omitted: ' + dropped.join(', ') + ' — send them again (full list) if you meant to keep them.');
    // State-aware no-op: nothing changed AND auto-advance has nothing to start.
    // Say precisely what the situation calls for instead of a generic scold — the
    // old "go do the actual work" reply kept a model grinding when the real state
    // was "everything is finished, deliver the answer".
    const _advPossible = !tree.some(t => t.status === 'in_progress') && tree.some(t => t.status === 'pending' && !_todoBlockers(t, new Map(tree.map(x => [x.id, x]))).length);
    if (_sigOf() === _sigBefore && !_advPossible) {
      if (ctx) ctx._todos = _todoFlat(tree);
      const active = tree.find(t => t.status === 'in_progress');
      let msg;
      if (!openCount()) msg = 'No change — and the checklist is COMPLETE (nothing open). Do NOT call write_todos again: deliver your final answer with respond() now.';
      else if (active) msg = 'No change — the checklist already matches your list. Task ' + active.id + ' ("' + active.content + '") is in_progress: do that work with your other tools, or mark it completed/blocked (delta form: {"todos":[{"id":"' + active.id + '","status":"completed"}]}). Do not resend the list.';
      else msg = 'No change — the checklist already matches your list. Every open task is blocked; unblock one, mark it deleted, or respond() with what is blocking you.';
      for (const n of notes) msg += '\n' + n;
      msg += '\nRepeating this exact call trips the LOOP GUARD.\n' + _todoSummary(tree);
      return { result: msg };
    }
    return _finish('Checklist reconciled to your list', notes);
  }

  // ── Fresh build (no checklist yet).
  // Two-pass: assign ids by position first so blockedBy can reference siblings.
  const ids = todos.map((_, i) => String(i + 1));
  todos.forEach((t, i) => {
    const content = t && typeof t.content === 'string' ? t.content.trim() : '';
    if (!content) return;
    const status = _TODO_ALL.includes(t.status) ? t.status : 'pending';
    const task = { id: ids[i], content, status, created: now };
    if (Array.isArray(t.blockedBy) && t.blockedBy.length) task.blockedBy = t.blockedBy.map(String).filter(x => ids.includes(x) && x !== ids[i]);
    if (typeof t.activeForm === 'string' && t.activeForm.trim()) task.activeForm = t.activeForm.trim();
    { const e = _todoEst(t && t.est); if (e) task.est = e; }
    if (status === 'blocked' && t && typeof t.reason === 'string' && t.reason.trim()) task.reason = t.reason.trim();
    if (status === 'completed') task.completed = now;
    tree.push(task);
  });
  // Renumber compactly (skipped-empty items leave gaps) and remap blockedBy.
  const remap = {}; tree.forEach((t, i) => { remap[t.id] = String(i + 1); });
  tree.forEach(t => { t.id = remap[t.id]; if (t.blockedBy) t.blockedBy = t.blockedBy.map(x => remap[x]).filter(Boolean); });
  if (!tree.length) return { result: 'Error: empty checklist — send at least one task.' };
  return _finish('New checklist', []);
}

// ── TODO-LAB (experiment, config.todoMode === 'claude'): faithful clone of
// Claude Code's TodoWrite — BLIND full replace, no ids, no reconcile, no fuzzy
// matching, and (in runAgent) no plan-first gate and no open-todos stop guard.
// Purpose: measure whether a given model complies with the trust-based contract
// (batch transitions, one in_progress, stop churning when done) before assuming
// it needs the guarded v2 tool. State still lands on ctx._todoTree (ids
// synthesized by position) so the page checklist renders unchanged.
async function tool_write_todos_claude({ todos }, ctx) {
  if (!Array.isArray(todos)) return { result: 'Error: todos must be an array of {content, status, activeForm}.' };
  const now = new Date().toISOString();
  const tree = todos.map((t, i) => ({
    id: String(i + 1),
    content: t && typeof t.content === 'string' ? t.content.trim() : '',
    status: _TODO_ALL.includes(t && t.status) ? t.status : 'pending',
    activeForm: (t && typeof t.activeForm === 'string' && t.activeForm.trim()) ? t.activeForm.trim() : undefined,
    created: now,
    completed: (t && t.status === 'completed') ? now : undefined,
  })).filter(t => t.content);
  if (ctx) { ctx._todoTree = tree; ctx._todos = _todoFlat(tree); }
  // Verbatim Claude Code TodoWrite acknowledgement.
  return { result: 'todos:' + JSON.stringify(tree) + '\nTodos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable' };
}

// — Scratchpad (hidden working memory) —————————————————————————————————
// Free-form text the model writes as its externalized brain: plan hypotheses,
// blockers, next steps, state that must survive compaction. Overwrite-whole,
// capped at ~4KB. Injected into the system prompt each round (ephemeral, not in
// messages) so the model always sees its working state without re-reading.
// NOT shown to the user — it replaces the drift guard's nagging.
async function tool_scratch({ text }, ctx) {
  const MAX = 4096;
  let t = String(text || '');
  if (t.length > MAX) t = t.slice(0, MAX);
  if (ctx) {
    ctx._scratchpad = t;
    ctx.emit({ type: 'scratchpad', text: t });
  }
  return { result: 'scratch:' + t.length + ' bytes stored. Re-injected each round.' };
}

// ── Deliverable localization (worker side) ──────────────────────────────────
// The model authors deliverables in ENGLISH (system directive). When the
// conversation has a localize target, show_artifact translates the deliverable's
// TEXT into the user's language so the delivered FILE matches. Fail-OPEN: on any
// error the English file is kept and shown. Text formats are handled directly;
// .docx is round-tripped through python-docx (per paragraph, so paragraph styles
// like Heading survive — intra-paragraph run formatting is not preserved).
const _LOCALIZER_MODEL = 'google/gemini-2.5-flash';
// Resolve an explicit per-deliverable `language` arg (BCP-47 / ISO code) into a
// {code,name} locale for the translator. The page's Reply selector is the
// default; this is ONLY the explicit override on a show_artifact / respond call.
function _langName(code){
  const c = String(code||'').split(/[-_]/)[0].toLowerCase();
  const m = { en:'English',ca:'Catalan',es:'Spanish',fr:'French',de:'German',it:'Italian',pt:'Portuguese',nl:'Dutch',pl:'Polish',zh:'Chinese',ja:'Japanese',ko:'Korean',ru:'Russian',ar:'Arabic',hi:'Hindi',uk:'Ukrainian',tr:'Turkish',sv:'Swedish',no:'Norwegian',da:'Danish',fi:'Finnish',el:'Greek',cs:'Czech',hu:'Hungarian',ro:'Romanian',bg:'Bulgarian',he:'Hebrew',th:'Thai',vi:'Vietnamese',id:'Indonesian',ms:'Malay' };
  return m[c] || c || 'English';
}
function _locFromOverride(code){
  if (!code || !String(code).trim()) return null;
  const cc = String(code).trim().split(/[-_]/)[0] || '';
  if (!cc) return null;
  return { code: cc, name: _langName(cc) };
}
async function _wLocalize(texts, ctx, target) {
  if (!Array.isArray(texts) || !texts.length) return texts;
  const cfg = ctx && ctx._agentConfig;
  if (!cfg || !cfg.url) return texts;
  const loc = target || (ctx && ctx._localize) || {};
  const code = String(loc.code || '').split(/[-_]/)[0].toLowerCase();
  if (!code || code === 'en') return texts;
  // gemini-2.5-flash through the provider endpoint the agent loop already uses
  // (ctx._agentConfig carries url+headers; the managed proxy injects the upstream
  // key and pins the localizer via models.json). The LLM preserves markdown/code
  // natively, so structured items need no special-casing. The per-call `target`
  // (from show_artifact's `language`) wins over the system locale, so a
  // "translate to X" task localizes each deliverable to X, ignoring the system
  // language. Fail-open to English per chunk.
  const tgt = loc.name || code;
  const sys = 'You are a professional translator. Rewrite each string in the input JSON array in fluent, correct ' + tgt + ', whatever language the input is in (translate it if it is another language; fix and clean it if it is already ' + tgt + '). Preserve meaning, tone, markdown/markup, numbers, and code verbatim. Return ONLY a JSON array of the same length and order — no prose, no code fences.';
  const CHUNK = 50;   // keep each request modest (upstream body cap ~1MB)
  const out = [];
  for (let i = 0; i < texts.length; i += CHUNK) {
    const slice = texts.slice(i, i + CHUNK);
    const body = { model: _LOCALIZER_MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: JSON.stringify(slice) }], stream: false, temperature: 0 };
    body.session_id = 'Translate:' + (ctx && ctx._sessionId);   // parent-session marker for /admin/transcripts
    let arr = null;
    try {
      const r = await fetch(cfg.url, { method: 'POST', headers: Object.assign({}, cfg.headers, { 'Content-Type': 'application/json' }), body: JSON.stringify(body), signal: ctx && ctx.signal });
      const j = await r.json();
      let content = (j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || '[]';
      content = content.replace(/^```(?:json)?/i, '').replace(/```\s*$/i, '').trim();
      arr = JSON.parse(content);
    } catch (e) { console.warn('[wLocalize] chunk failed (keeping English):', (e && e.message) || e); }
    for (let k = 0; k < slice.length; k++) out.push((arr && typeof arr[k] === 'string') ? arr[k] : slice[k]);
  }
  return out;
}
// ---- HTML text-node localization (JS pre/post pass) -------------------------
// Whole HTML documents are NEVER sent to the localizer in one piece: the model
// could truncate or rewrite markup, and a big dashboard would blow the upstream
// ~1MB body cap. Instead split on tags, collect only translatable TEXT nodes,
// batch them through _wLocalize, and reinject — tags, attributes, and
// <style>/<script>/<code>/<pre>/<svg> subtrees stay byte-identical.
const _lxHtmlSkipTags = { style: 1, script: 1, code: 1, pre: 1, svg: 1, noscript: 1, textarea: 1 };
// Decode numeric entities and the named ones LLM-authored pages actually use,
// BEFORE the translatability test — "&#9650; +55.29 &middot; +0.72%" must decode
// to "▲ +55.29 · +0.72%" (no lowercase -> skipped whole), or the entity NAMES
// themselves read as prose ("middot") and drag numeric fragments into the request.
const _lxEntNamed = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
  middot: '·', bull: '•', ndash: '–', mdash: '—', hellip: '…',
  deg: '°', times: '×', minus: '−', plusmn: '±', laquo: '«',
  raquo: '»', lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”',
  trade: '™', copy: '©', reg: '®', euro: '€', pound: '£',
  yen: '¥', cent: '¢', sect: '§', para: '¶',
  uarr: '↑', darr: '↓', rarr: '→', larr: '←' };
function _lxEntDec(s) {
  return s
    .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
    .replace(/&([a-zA-Z][a-zA-Z0-9]*);/g, (m0, n) => Object.prototype.hasOwnProperty.call(_lxEntNamed, n) ? _lxEntNamed[n] : m0);
}
// Entity-aware escape: encode < > and BARE & only — an '&' still starting a
// well-formed entity (an unknown named one the decode left alone) must not
// become '&amp;middot;' and render as literal "&middot;" text.
function _lxEntEnc(s) {
  return s.replace(/&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#x[0-9a-fA-F]+);)/g, '&amp;')
          .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function _lxHasLowerWord(t) {
  const w = String(t).split(/\s+/);
  for (let i = 0; i < w.length; i++) {
    const tok = w[i].replace(/^[^\p{L}]+/u, '');   // strip leading punctuation
    if (tok && /^\p{Ll}/u.test(tok)) return true;
  }
  return false;
}
// Graded translatability: a SHORT fragment (≤3 words) is a label/name — translate
// it only when a word BEGINS with a lowercase letter, so tickers and proper nouns
// ("Dow Jones", "WTI Crude", "GC=F") pass through untouched while single common
// words ("Gold") and real prose still translate. Numbers/symbol runs never match.
// This also keeps request size (= cost) down: most dashboard cells are skipped.
function _lxHtmlTranslatable(t) {
  const words = t.split(/\s+/).filter(Boolean);
  if (!words.length) return false;
  if (words.length === 1) return /\p{Ll}/u.test(t);
  if (words.length <= 3) return _lxHasLowerWord(t);
  return /\p{Ll}/u.test(t);
}
async function _lxTranslateHtml(html, ctx, target) {
  if (typeof html !== 'string' || !html.trim()) return html;
  const parts = html.split(/(<[^>]*>)/);
  let skip = 0;                                  // depth inside skip-tag subtrees
  const frags = [], refs = [], lead = [], trail = [];
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (!p) continue;
    if (p.charAt(0) === '<') {
      const m = p.match(/^<\s*(\/?)([a-zA-Z][a-zA-Z0-9-]*)/);
      if (m && _lxHtmlSkipTags[m[2].toLowerCase()]) {
        if (m[1]) skip = Math.max(0, skip - 1);
        else if (!/\/>\s*$/.test(p)) skip++;
      }
      continue;
    }
    if (skip) continue;
    const decoded = _lxEntDec(p);
    if (!_lxHtmlTranslatable(decoded.trim())) continue;  // numbers/tickers/short proper nouns pass through
    frags.push(decoded.trim());
    refs.push(i);
    lead.push((p.match(/^\s*/) || [''])[0]);
    trail.push((p.match(/\s*$/) || [''])[0]);
  }
  if (!frags.length) return html;
  const tr = await _wLocalize(frags, ctx, target);
  for (let k = 0; k < refs.length; k++) {
    const t = tr[k];
    if (typeof t === 'string' && t) parts[refs[k]] = lead[k] + _lxEntEnc(t) + trail[k];
  }
  return parts.join('');
}
const _DOCX_LX_EXTRACT = `import sys, json
try:
    from docx import Document
except ImportError:
    import micropip; await micropip.install('python-docx'); from docx import Document
d = Document('/files/' + sys.argv[1])
out = []
def para_text(p):
    return ''.join(r.text for r in p.runs)
for p in d.paragraphs:
    t = para_text(p)
    if t.strip(): out.append(t)
for tbl in d.tables:
    for row in tbl.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                t = para_text(p)
                if t.strip(): out.append(t)
print('<<<LXJSON>>>' + json.dumps(out, ensure_ascii=False))
`;
const _DOCX_LX_REINJECT = `import sys, json
try:
    from docx import Document
except ImportError:
    import micropip; await micropip.install('python-docx'); from docx import Document
d = Document('/files/' + sys.argv[1])
tr = json.load(open('/files/' + sys.argv[2]))
it = iter(tr)
def setp(p):
    t = ''.join(r.text for r in p.runs)
    if t.strip():
        try: nt = next(it)
        except StopIteration: return
        if p.runs:
            p.runs[0].text = nt
            for r in p.runs[1:]: r.text = ''
for p in d.paragraphs: setp(p)
for tbl in d.tables:
    for row in tbl.rows:
        for cell in row.cells:
            for p in cell.paragraphs: setp(p)
d.save('/files/' + sys.argv[1])
print('LXOK')
`;
// Does this deliverable actually need translation? Returns the resolved target
// locale, or null when the file was already authored in the target language.
// Same predicate as the respond path (_needsTx): author-in-English regime
// translates every non-English target (files are authored English); native
// regime translates only NON-fluent targets (fluent ones authored directly).
function _lxNeeded(ctx, target) {
  const loc = target || (ctx && ctx._localize);
  return _needsTx(loc, ctx) ? loc : null;
}
async function _localizeArtifact(path, ctx, target) {
  const loc = _lxNeeded(ctx, target);
  if (!loc || !loc.code) return;
  // Idempotency per (path,language): never translate the same deliverable twice
  // (a re-show, or an already-translated file), which would garble it.
  ctx._localizedArtifacts = ctx._localizedArtifacts || new Set();
  const lxKey = (target ? 'x:'+target.code : 'd:') + ':' + path;
  if (ctx._localizedArtifacts.has(lxKey)) return;
  ctx._localizedArtifacts.add(lxKey);
  const lower = String(path).toLowerCase();
  const enc = new TextEncoder(), dec = new TextDecoder();
  try {
    if (/\.html?$/.test(lower)) {
      // Whole document through _lxTranslateHtml — a JS pass that splits on tags
      // and translates ONLY text nodes (tags, attributes, <style>/<script>
      // subtrees stay byte-identical). NEVER feed HTML down the prose path
      // below: the blank-line splitter hands CSS/markup blocks to the
      // translator, which shreds the file (Jordi's 2026-08-28 dashboard).
      const text = dec.decode(await opfsReadBytes(path));
      const loc = target || (ctx && ctx._localize) || {};
      const code = String(loc.code || '').split(/[-_]/)[0].toLowerCase();
      if (!code || code === 'en') return;
      const tr = await _lxTranslateHtml(text, ctx, target);
      if (typeof tr !== 'string' || !tr || tr === text) return;
      // Off-turn safety: skip the write-back if the model edited the file meanwhile.
      try { if (dec.decode(await opfsReadBytes(path)) !== text) return; } catch (_) { return; }
      await opfsWriteBytes(path, enc.encode(tr));
      return;
    }
    if (/\.(md|markdown|txt|csv)$/.test(lower)) {
      const text = dec.decode(await opfsReadBytes(path));
      const blocks = text.split(/(\n{2,})/);   // keep separators
      const idx = [], toTr = [];
      blocks.forEach((b, i) => { if (b.trim() && !/^\s+$/.test(b)) { idx.push(i); toTr.push(b); } });
      if (!toTr.length) return;
      const tr = await _wLocalize(toTr, ctx, target);
      // Off-turn safety: the agent loop keeps running while we translated. If the
      // model edited the file meanwhile, writing back would clobber its edit —
      // skip instead (fail-open: the newer English version stays).
      try { if (dec.decode(await opfsReadBytes(path)) !== text) return; } catch (_) { return; }
      idx.forEach((bi, k) => { blocks[bi] = tr[k]; });
      await opfsWriteBytes(path, enc.encode(blocks.join('')));
      return;
    }
    if (/\.docx$/.test(lower)) {
      const sig = ctx && ctx.signal;
      await opfsWriteBytes('sandpie/scripts/_lx_extract.py', enc.encode(_DOCX_LX_EXTRACT));
      const ex = await dispatchPython({ path: 'sandpie/scripts/_lx_extract.py', args: [path], timeout: 120, signal: sig });
      const raw = String(ex && ex.result || '');
      const m = raw.indexOf('<<<LXJSON>>>');
      if (m < 0) { console.warn('[localizeArtifact] docx extract failed:', raw.slice(0, 160)); return; }
      let texts; try { texts = JSON.parse(raw.slice(m + 12).trim()); } catch (_) { return; }
      if (!Array.isArray(texts) || !texts.length) return;
      const tr = await _wLocalize(texts, ctx, target);
      await opfsWriteBytes('sandpie/scripts/_lx_tr.json', enc.encode(JSON.stringify(tr)));
      await opfsWriteBytes('sandpie/scripts/_lx_reinject.py', enc.encode(_DOCX_LX_REINJECT));
      await dispatchPython({ path: 'sandpie/scripts/_lx_reinject.py', args: [path, 'sandpie/scripts/_lx_tr.json'], timeout: 120, signal: sig });
      return;
    }
  } catch (e) { console.warn('[localizeArtifact] failed (keeping English):', (e && e.message) || e); }
}

// Off-turn deliverable localization: show_artifact used to AWAIT the whole
// translation (30-45s dead time per HTML dashboard, measured in Jordi's
// 2026-08-28 transcripts) before the turn could continue. Now the tool returns
// immediately (the artifact renders in English), the translation runs on this
// serialized queue (one at a time — the docx path shares helper files under
// sandpie/scripts/, and ordered write-backs keep re-shows deterministic), and on
// completion the page gets the same sw-opfs-changed ping the other file writers
// use, so an OPEN artifact viewer reloads with the translated file. Fail-open:
// any error just leaves the English deliverable.
let _lxQueue = Promise.resolve();
function _localizeArtifactOffTurn(path, ctx, target) {
  // No translation needed (English target, or a fluent language the model
  // authored directly)? Skip entirely — no badge, no queue slot.
  if (!_lxNeeded(ctx, target)) return;
  // Already translated (re-show)? Skip entirely — no badge flash, no queue slot.
  // Same key _localizeArtifact uses for its own idempotency guard.
  const lxKey = (target ? 'x:' + target.code : 'd:') + ':' + path;
  if (ctx && ctx._localizedArtifacts && ctx._localizedArtifacts.has(lxKey)) return;
  // Tell the page NOW (queued counts as "in progress" — the user sees the English
  // version with a translating badge until the swap), and again when finished so
  // the badge clears even when translation failed (fail-open English stays).
  self.postMessage({ type: 'artifact-localizing', path, state: 'start' });
  _lxQueue = _lxQueue.then(async () => {
    try { await _localizeArtifact(path, ctx, target); } catch (_) {}
    try { self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [path], owner: ctx && ctx.agentId } }); } catch (_) {}
    self.postMessage({ type: 'artifact-localizing', path, state: 'done' });
  });
}

async function tool_show_artifact({ path, language }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  const _saOverride = _locFromOverride(language);   // explicit per-deliverable language (eq selector)
  const clean = String(path).replace(/^\/+/, '');
  // Legacy-path fallback: user files moved from /files/<dir>/ to /files/sandpie/<dir>/,
  // so old calls like "artifacts/x.html" resolve against the new prefix too (and
  // vice versa, in case a caller double-prefixes).
  const candidates = [clean];
  if (!clean.startsWith('sandpie/')) candidates.push('sandpie/' + clean);
  else candidates.push(clean.slice('sandpie/'.length));
  for (const p of candidates) {
    let found = false;
    try { await opfsReadBytes(p); found = true; } catch (_) {}
    if (!found && _indexEntry(p)) { try { await hydrateAsync(p); found = true; } catch (_) {} }
    if (found) {
      // TRANSITIONAL SHIM — show_artifact is no longer offered to the model
      // (files it touches surface automatically at turn end; see the
      // 'files_touched' emit in runAgent). A stale session that still calls it
      // just marks the file touched; an explicit `language` override still
      // routes to the localizer so old flows keep their translated deliverable.
      if (ctx && ctx._filesTouched) ctx._filesTouched.set(p, Date.now());
      if (_saOverride && _saOverride.code) _localizeArtifactOffTurn(p, ctx, _saOverride);
      return { result: 'Noted — files you create or edit are shown to the user automatically at the end of the turn; you do not need to call show_artifact.' };
    }
  }
  return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' };
}

// Images are embedded as base64 in the NEXT model request. The upstream gateway
// (NPAW ai-balancer.npaw.com) caps the WHOLE request body at ~1 MB and that limit
// is NOT raisable, so instead of rejecting a large image we downscale + re-encode
// it to fit (see _compressImageToFit / tool_load_image).
//   • IMAGE_MAX_B64_BYTES — per image: the compress-to-fit target (base64).
//     (We no longer cap the WHOLE serialized body client-side. Providers differ in
//      request-size limits, so an oversized body is left to the provider, which
//      answers with HTTP 413; 413 is non-retryable — see RETRYABLE_STATUS below.)
const IMAGE_MAX_B64_BYTES    = 700 * 1024;   // per image: compress-to-fit target
const _fmtBytes = n => n >= 1024 * 1024 ? (n / (1024 * 1024)).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB';
// Downscale + re-encode an image (in the worker, via OffscreenCanvas) until its
// base64 size is at or under `targetB64`. The upstream gateway caps the whole
// request body near 1 MB, so a full-res photo has to be shrunk to fit. Walks
// progressively smaller max-dimensions × JPEG qualities and returns the FIRST that
// fits (so most images keep high resolution/quality), else the smallest achieved.
// Returns { bytes, mime, estB64 } or null if the image can't be decoded here (e.g.
// an SVG) — the caller then falls back to the raw bytes.
async function _compressImageToFit(rawBytes, srcMime, targetB64) {
  if (typeof OffscreenCanvas === 'undefined' || typeof createImageBitmap !== 'function') return null;
  let bmp;
  try { bmp = await createImageBitmap(new Blob([rawBytes], { type: srcMime })); }
  catch (_) { return null; }
  const DIMS = [1568, 1024, 768, 512, 384];
  const QUALS = [0.7, 0.5];
  let best = null;
  try {
    for (const maxDim of DIMS) {
      let w = bmp.width, h = bmp.height;
      if (w > maxDim || h > maxDim) {
        if (w >= h) { h = Math.max(1, Math.round(h * maxDim / w)); w = maxDim; }
        else { w = Math.max(1, Math.round(w * maxDim / h)); h = maxDim; }
      }
      const canvas = new OffscreenCanvas(w, h);
      const cx = canvas.getContext('2d');
      cx.fillStyle = '#fff';            // flatten any transparency — JPEG has no alpha
      cx.fillRect(0, 0, w, h);
      cx.drawImage(bmp, 0, 0, w, h);
      for (const q of QUALS) {
        let blob;
        try { blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: q }); }
        catch (_) { continue; }
        if (!blob) continue;
        const estB64 = Math.ceil(blob.size / 3) * 4;
        if (estB64 <= targetB64) return { bytes: new Uint8Array(await blob.arrayBuffer()), mime: 'image/jpeg', estB64 };
        if (!best || estB64 < best.estB64) best = { blob, estB64 };
      }
    }
  } finally { if (bmp && bmp.close) bmp.close(); }
  if (best) return { bytes: new Uint8Array(await best.blob.arrayBuffer()), mime: 'image/jpeg', estB64: best.estB64 };
  return null;
}

async function tool_load_image({ path }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  let clean = String(path).replace(/^\/+/, '');
  try {
    let bytes;
    if (_betaOn()) {
      const r = _betaResolve(path, ctx);
      if (r.kind === 'noproject') return { result: 'Error: "' + path + '" is project-relative but this conversation has no project folder. Use an absolute /Dropbox/path.' };
      if (r.kind === 'dbx') {
        clean = r.path;
        let ok = false;
        for (const team of (r.abs ? [r.team, !r.team] : [r.team])) {
          try { bytes = await _dbxDownloadBytes(r.path, team); ok = true; break; } catch (_) {}
        }
        if (!ok) return { result: 'Error: image not found in Dropbox: ' + r.path };
      } else {
        clean = r.rel;   // sandpie/ metadata — OPFS read below
        try { bytes = await opfsReadBytes(clean); }
        catch (miss) { if (_indexEntry(clean)) { await hydrateAsync(clean); bytes = await opfsReadBytes(clean); } else throw miss; }
      }
    } else {
      try { bytes = await opfsReadBytes(clean); }
      catch (miss) {
        if (_indexEntry(clean)) { await hydrateAsync(clean); bytes = await opfsReadBytes(clean); }
        else throw miss;
      }
    }
    const ext = (clean.split('.').pop() || '').toLowerCase();
    let mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp' }[ext] || 'application/octet-stream';
    // Estimate the base64 payload from the raw byte count. If it's over the
    // per-image target, downscale + re-encode to fit (the gateway caps the body
    // near 1 MB) rather than rejecting. SVG / undecodable → fall through raw.
    let estB64 = Math.ceil(bytes.length / 3) * 4;
    if (estB64 > IMAGE_MAX_B64_BYTES) {
      const c = await _compressImageToFit(bytes, mime, IMAGE_MAX_B64_BYTES);
      if (c) { bytes = c.bytes; mime = c.mime; estB64 = c.estB64; }
    }
    // No cumulative conversation budget: per-image compression only.
    let bin = ''; const CHUNK = 0x8000;
    for (let i = 0; i < bytes.length; i += CHUNK) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    const dataUrl = 'data:' + mime + ';base64,' + btoa(bin);
    // Vision gate (yes/no): a text-only model can't use the raw image — asking the
    // vision fallback for a caption keeps the pixels OUT of the context AND gives
    // the model text it can actually reason over. No fallback configured → explain
    // (the page already warned at attach time). Vision-capable models keep the raw
    // image (embedded in the next request as before).
    const _vis = ctx && ctx._agentConfig && ctx._agentConfig.vision;
    if (_vis && !_vis.canSee) {
      const fb = _vis.fallback;
      if (!fb || !fb.endpoint || !fb.apiKey || !fb.model) {
        return { result: 'Error: this model cannot see images and no vision fallback is configured. Attach images to a vision-capable model, or set a vision fallback in Settings \u2192 AI provider.' };
      }
      try {
        const capRes = await fetch(String(fb.endpoint).replace(/\/$/, '') + '/chat/completions', {
          method: 'POST', credentials: 'omit',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + fb.apiKey },
          body: JSON.stringify({
            model: fb.model,
            messages: [{ role: 'user', content: [
              { type: 'text', text: 'Describe this image in detail for an assistant that cannot see it. Transcribe any visible text verbatim, note layout/figures/tables, and state anything a viewer would need to reason about the image. Be factual and complete.' },
              { type: 'image_url', image_url: { url: dataUrl } },
            ] }],
            max_tokens: 2048,
          }),
          signal: (ctx && ctx.signal) || undefined,
        });
        if (!capRes.ok) {
          let txt = ''; try { txt = (await capRes.text()).slice(0, 300); } catch (_) {}
          return { result: 'Error: vision fallback captioning failed (HTTP ' + capRes.status + (txt ? ': ' + txt : '') + ').' };
        }
        const cap = await capRes.json();
        const _msg = cap && cap.choices && cap.choices[0] && cap.choices[0].message;
        // Reasoning models (e.g. MiMo V2.5) may spend the budget on chain-of-thought
        // and leave content null — the reasoning fields still hold the full caption.
        let caption = _msg && _msg.content;
        if (!caption && _msg && (Array.isArray(_msg.reasoning_details) || _msg.reasoning)) {
          caption = Array.isArray(_msg.reasoning_details)
            ? _msg.reasoning_details.map(x => (x && x.text) || '').join('\n')
            : _msg.reasoning;
        }
        if (!caption) return { result: 'Error: vision fallback returned no caption.' };
        return { result: 'image:' + clean + '\n\n(captioned via ' + fb.model + ' — this model cannot see images):\n\n' + String(caption).trim() };
      } catch (e2) {
        return { result: 'Error: vision fallback captioning request failed (' + ((e2 && e2.message) || e2) + ').' };
      }
    }
    return { result: 'image:' + clean, image: { path: clean, dataUrl } };
  } catch (e) { return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' }; }
}

// ---- share() — worker → page round-trip --------------------------------
// Sharing needs the page: Dropbox tokens and the OPFS/cloud machinery live in
// sharing.js on the main thread, not in this worker. tool_share posts a
// share-request to the page (forward-to-page relay) and awaits the reply. The
// page (conversations.js) calls SandpieSharing.publish and replies share-result.
const SHARE_TIMEOUT = 60000;
const _shareReqs = new Map();

async function tool_share(args, ctx) {
  const path = String(args.path || '').trim();
  const type = String(args.type || '').toLowerCase();
  const recips = Array.isArray(args.recipients)
    ? args.recipients.map(String).filter(Boolean)
    : (typeof args.recipients === 'string' && args.recipients.trim()
        ? args.recipients.split(',').map(s => s.trim()).filter(Boolean) : []);
  if (!path) return { result: 'Error: "path" is required (OPFS path of the file or folder to share).' };
  if (type !== 'team' && type !== 'p2p') return { result: 'Error: "type" must be "team" or "p2p".' };
  if (!recips.length) {
    return { result: 'Error: "recipients" is required — ' + (type === 'team'
      ? 'team/department folder names (e.g. ["R+D+I"]).'
      : 'recipient email addresses.') };
  }
  if (type === 'p2p' && !recips.every(r => r.includes('@'))) {
    return { result: 'Error: p2p recipients must be email addresses.' };
  }
  const id = 'share_' + Math.random().toString(36).slice(2);
  return new Promise((resolve) => {
    // Single settle point: page reply, timeout, OR abort — whichever first. Wiring
    // abort (like tool_ask) is what lets Stop unwind the turn mid-share instead of
    // hanging until the timeout (which is throttled to ~1/min while the tab is hidden).
    let settled = false;
    const finish = (out) => {
      if (settled) return; settled = true;
      clearTimeout(timer); _shareReqs.delete(id);
      if (ctx && ctx.signal) ctx.signal.removeEventListener('abort', onAbort);
      resolve(out);
    };
    const onAbort = () => finish({ result: 'Error: share aborted (turn stopped).' });
    const timer = setTimeout(() => finish({ result: 'Error: share request timed out after ' + (SHARE_TIMEOUT / 1000) + 's (the page did not reply).' }), SHARE_TIMEOUT);
    if (ctx && ctx.signal) {
      if (ctx.signal.aborted) { finish({ result: 'Error: share aborted (turn stopped).' }); return; }
      ctx.signal.addEventListener('abort', onAbort, { once: true });
    }
    _shareReqs.set(id, { resolve: finish });
    try {
      self.postMessage({ type: 'forward-to-page', payload: { type: 'share-request', id, args: { path, type, recipients: recips, pinFile: args.pinFile || undefined } } });
    } catch (e) {
      finish({ result: 'Error: could not reach the page to perform the share (' + ((e && e.message) || e) + ').' });
    }
  });
}

// ---- html_console() — worker → page round-trip -------------------------
// The artifact's console buffer lives on the PAGE (the blob-URL iframe in the
// conversation; the bootstrap injected by opfs.toUrl captures into
// window.__sandpieConsole). tool_html_console posts a console-request to the
// page (forward-to-page relay) and awaits the console-result reply.
const CONSOLE_TIMEOUT = 30000;
const _consoleReqs = new Map();
const _askReqs = new Map();   // ask tool — pending user-clarification promises

async function tool_html_console({ path }, ctx) {
  const id = 'console_' + Math.random().toString(36).slice(2);
  return new Promise((resolve) => {
    // Settle on page reply, timeout, OR abort — see tool_share for why abort is wired.
    let settled = false;
    const finish = (out) => {
      if (settled) return; settled = true;
      clearTimeout(timer); _consoleReqs.delete(id);
      if (ctx && ctx.signal) ctx.signal.removeEventListener('abort', onAbort);
      resolve(out);
    };
    const onAbort = () => finish({ result: 'Error: html_console aborted (turn stopped).' });
    const timer = setTimeout(() => finish({ result: 'Error: html_console request timed out after ' + (CONSOLE_TIMEOUT / 1000) + 's (the page did not reply).' }), CONSOLE_TIMEOUT);
    if (ctx && ctx.signal) {
      if (ctx.signal.aborted) { finish({ result: 'Error: html_console aborted (turn stopped).' }); return; }
      ctx.signal.addEventListener('abort', onAbort, { once: true });
    }
    _consoleReqs.set(id, { resolve: finish });
    try {
      self.postMessage({ type: 'forward-to-page', payload: { type: 'console-request', id, args: { path: String(path || '') } } });
    } catch (e) {
      finish({ result: 'Error: could not reach the page to read the console (' + ((e && e.message) || e) + ').' });
    }
  });
}

// ---- screenshot() — worker → page round-trip ---------------------------
// Rasterizing needs a DOM, which this worker does not have. tool_screenshot posts
// a screenshot-request to the page (forward-to-page relay); screenshot.js renders
// the artifact — offscreen at exact dimensions by default — and replies with a
// JPEG data URL plus a list of fidelity caveats. The image rides back to the model
// on the same rail load_image uses (ctx collects toolOut.image into the next
// request), so the model literally sees what it built.
const SHOT_TIMEOUT = 45000;
const _shotReqs = new Map();

// Ask the configured vision fallback to describe an image, for models that cannot
// see. Mirrors the captioning path in tool_load_image.
async function _captionImage(dataUrl, ctx, what) {
  const _vis = ctx && ctx._agentConfig && ctx._agentConfig.vision;
  const fb = _vis && _vis.fallback;
  if (!fb || !fb.endpoint || !fb.apiKey || !fb.model) {
    return 'Error: this model cannot see images and no vision fallback is configured, so the screenshot is unusable. Switch to a vision-capable model, or set a vision fallback in Settings → AI provider.';
  }
  try {
    const res = await fetch(String(fb.endpoint).replace(/\/$/, '') + '/chat/completions', {
      method: 'POST', credentials: 'omit',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + fb.apiKey },
      body: JSON.stringify({
        model: fb.model,
        messages: [{ role: 'user', content: [
          { type: 'text', text: 'This is a screenshot of ' + what + '. Describe the rendered layout precisely for a developer who cannot see it: overall structure and position of each region, alignment and spacing problems, overlapping or clipped elements, colours and contrast, and any text that is cut off. Transcribe visible text verbatim. Be factual; call out anything that looks broken.' },
          { type: 'image_url', image_url: { url: dataUrl } },
        ] }],
        max_tokens: 2048,
      }),
      signal: (ctx && ctx.signal) || undefined,
    });
    if (!res.ok) {
      let txt = ''; try { txt = (await res.text()).slice(0, 300); } catch (_) {}
      return 'Error: vision fallback captioning failed (HTTP ' + res.status + (txt ? ': ' + txt : '') + ').';
    }
    const j = await res.json();
    const m = j && j.choices && j.choices[0] && j.choices[0].message;
    let caption = m && m.content;
    if (!caption && m && (Array.isArray(m.reasoning_details) || m.reasoning)) {
      caption = Array.isArray(m.reasoning_details)
        ? m.reasoning_details.map(x => (x && x.text) || '').join('\n')
        : m.reasoning;
    }
    return caption ? String(caption).trim() : 'Error: vision fallback returned no caption.';
  } catch (e) {
    return 'Error: vision fallback captioning request failed (' + ((e && e.message) || e) + ').';
  }
}

async function tool_screenshot(args, ctx) {
  const path = String((args && args.path) || '').trim().replace(/^\/+/, '');
  if (!path) return { result: 'Error: "path" is required (OPFS path of the artifact to capture, e.g. "sandpie/artifacts/report.html").' };

  const opts = {
    width:     Math.max(0, Math.min(4096, (args && args.width) | 0)),
    height:    Math.max(0, Math.min(16384, (args && args.height) | 0)),
    full_page: !!(args && args.full_page),
    wait_ms:   Math.max(0, Math.min(10000, (args && args.wait_ms) | 0)),
    live:      !!(args && args.live),
    exact_width: !!(args && args.exact_width),
  };

  const id = 'shot_' + Math.random().toString(36).slice(2);
  const out = await new Promise((resolve) => {
    // Settle on page reply, timeout, OR abort — see tool_share for why abort is wired.
    let settled = false;
    const finish = (d) => {
      if (settled) return; settled = true;
      clearTimeout(timer); _shotReqs.delete(id);
      if (ctx && ctx.signal) ctx.signal.removeEventListener('abort', onAbort);
      resolve(d);
    };
    const onAbort = () => finish({ ok: false, error: 'screenshot aborted (turn stopped).' });
    const timer = setTimeout(() => finish({ ok: false, error: 'the page did not answer within ' + (SHOT_TIMEOUT / 1000) + 's. '
        + 'Total silence (rather than an error) almost always means sandpie.html is running cached assets older than this worker, '
        + 'so the page-side screenshot handler is missing — ask the user to hard-reload the page. '
        + 'It is NOT caused by the tab being unfocused: capture runs in an offscreen frame and works with the tab hidden.' }), SHOT_TIMEOUT);
    if (ctx && ctx.signal) {
      if (ctx.signal.aborted) { finish({ ok: false, error: 'screenshot aborted (turn stopped).' }); return; }
      ctx.signal.addEventListener('abort', onAbort, { once: true });
    }
    _shotReqs.set(id, { resolve: finish });
    try {
      // replyType lets a page that lacks this handler fail fast and explain itself
      // instead of leaving the tool to time out in silence.
      self.postMessage({ type: 'forward-to-page', payload: { type: 'screenshot-request', replyType: 'screenshot-result', id, args: { path, opts } } });
    } catch (e) {
      finish({ ok: false, error: 'could not reach the page (' + ((e && e.message) || e) + ')' });
    }
  });

  if (!out || !out.ok || !out.dataUrl) {
    return { result: 'Error: screenshot of "' + path + '" failed — ' + ((out && out.error) || 'unknown error') + '.' };
  }

  // Shrink to the per-image budget if the capture came out large (a full-page shot
  // of a long document easily exceeds it).
  let dataUrl = out.dataUrl;
  const b64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
  if (b64.length > IMAGE_MAX_B64_BYTES) {
    try {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const c = await _compressImageToFit(bytes, 'image/jpeg', IMAGE_MAX_B64_BYTES);
      if (c) {
        let s = ''; const CHUNK = 0x8000;
        for (let i = 0; i < c.bytes.length; i += CHUNK) s += String.fromCharCode.apply(null, c.bytes.subarray(i, i + CHUNK));
        dataUrl = 'data:' + c.mime + ';base64,' + btoa(s);
      }
    } catch (_) {}
  }

  const warns = Array.isArray(out.warnings) ? out.warnings : [];
  // Say WHICH surface produced the image. "The user's current view" and "a clean
  // render" support very different conclusions, and the model can't tell them apart
  // from pixels alone.
  const MODE_NOTE = {
    'side-panel': 'THE USER\'S CURRENT VIEW, captured live from the side panel — it reflects their actual state (loaded data, selected tab, scroll position, typed input). This is what they are looking at.',
    'conversation-frame': 'the live artifact card in the conversation, in whatever state it currently holds.',
    'fresh-render': 'a clean render from the file on disk, in its initial state — NOT the user\'s current view.',
  };
  let text = 'screenshot:' + path + ' (' + out.width + '×' + out.height + 'px'
    + (opts.full_page ? ', full page' : '') + ')\n\nSOURCE: ' + (MODE_NOTE[out.mode] || MODE_NOTE['fresh-render']);
  text += warns.length
    ? '\n\nFIDELITY CAVEATS — the render is faithful EXCEPT:\n- ' + warns.join('\n- ')
      + '\nTreat those areas as unverified; everything else is what the browser actually draws.'
    : '\n\nNo fidelity caveats: this is what the browser actually draws.';

  // A text-only model cannot use the pixels — caption instead, so it still gets
  // something it can reason over rather than a wasted turn.
  const _vis = ctx && ctx._agentConfig && ctx._agentConfig.vision;
  if (_vis && !_vis.canSee) {
    const caption = await _captionImage(dataUrl, ctx, 'a web page rendered from ' + path);
    return { result: text + '\n\n(described by a vision model — this model cannot see images):\n\n' + caption };
  }

  return { result: text, image: { path, dataUrl } };
}

// ---- ask() — worker → page round-trip for user clarifications -------
// The worker posts the questions to the page (forward-to-page relay), the page
// renders them as a multiple-choice card, and the user clicks an option. The
// page replies ask-result with the chosen answers, and this promise resolves.
// The loop is BLOCKED (suspended) while waiting — no new rounds until the user
// answers. If the user hits stop, ctx.signal aborts and the promise rejects.
async function tool_ask({ questions }, ctx) {
  if (!Array.isArray(questions) || !questions.length) {
    return { result: 'Error: "questions" is required (array of question objects with question + options).' };
  }
  if (questions.length > 4) {
    return { result: 'Error: maximum 4 questions per call — batch them into one ask call.' };
  }
  for (const q of questions) {
    if (!q.question || !Array.isArray(q.options) || q.options.length < 2) {
      return { result: 'Error: each question needs "question" (string) and "options" (array of 2-5 strings).' };
    }
  }
  // Sanitize. A default that isn't verbatim in options used to be a hard error,
  // which sent weaker models into a retry loop (they'd re-issue the call with a
  // slightly-reworded default and fail again). Instead COERCE: keep the model's
  // intended default by appending it as a real option when there's room (≤5),
  // otherwise fall back to the first option. Never error on a default mismatch.
  const sanitized = questions.map(q => {
    let options = q.options.slice(0, 5);
    let def = q.default;
    if (def && !options.includes(def)) {
      if (options.length < 5) options = options.concat([def]);
      else def = options[0];
    }
    return { ...q, options, default: def || options[0], allow_freeform: !!q.allow_freeform };
  });
  const id = 'ask_' + Math.random().toString(36).slice(2);
  return new Promise((resolve) => {
    // No timeout — the user can take as long as they need. But wire to abort.
    const onAbort = () => {
      _askReqs.delete(id);
      if (!resolved) { resolved = true; resolve({ result: 'Error: ask request aborted (turn stopped).' }); }
    };
    let resolved = false;
    if (ctx && ctx.signal) {
      if (ctx.signal.aborted) { onAbort(); return; }
      ctx.signal.addEventListener('abort', onAbort, { once: true });
    }
    _askReqs.set(id, { resolve: (out) => { if (!resolved) { resolved = true; resolve(out); } } });
    try {
      self.postMessage({ type: 'forward-to-page', payload: {
        type: 'ask-question', id,
        convId: (ctx && ctx._conversation_file_name) || '',
        tcId: (ctx && ctx._currentToolCallId) || '',
        args: { questions: sanitized }
      }});
    } catch (e) {
      _askReqs.delete(id); if (!resolved) { resolved = true; resolve({ result: 'Error: could not reach the page to ask (' + ((e && e.message) || e) + ').' }); }
    }
  });
}

async function tool_load_skill({ name }, ctx) {
  const n = String(name || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(n)) return { result: 'Error: invalid skill name "' + name + '". Use the exact name from the Skills section.' };
  const file = 'sandpie/skills/' + n + '/SKILL.md';
  const sharedFile = 'sandpie/shared-installed/' + n + '/SKILL.md';   // shared, installed skill package
  // Shared first: the hub copy is authoritative (it replaces same-named local
  // skills), so the model must load the same copy the skill index advertises.
  let text;
  try { text = new TextDecoder().decode(await opfsReadBytes(sharedFile)); }
  catch (e) {
    try { text = new TextDecoder().decode(await opfsReadBytes(file)); }
    catch (e2) { return { result: 'Error: no skill named "' + n + '" — neither ' + sharedFile + ' nor ' + file + ' exists.' }; }
  }
  const body = text.replace(/^﻿?---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/, '').trim();
  return { result: body || text };
}

const FILE_TOOL_CAP = 28 * 1024;
const FILE_TEXT_MAX = 2 * 1024 * 1024;
const SEARCH_SKIP_TOP = 'sandpie/conversations';

function normFilesPath(p) {
  return String(p == null ? '' : p).replace(/^\/+/, '').replace(/^files\//, '').replace(/\/+$/, '');
}

function globToRegExp(glob) {
  const g = String(glob); let re = '';
  for (let i = 0; i < g.length; i++) {
    const c = g[i];
    if (c === '*') { if (g[i + 1] === '*') { re += '.*'; i++; if (g[i + 1] === '/') i++; } else re += '[^/]*'; }
    else if (c === '?') re += '[^/]';
    else re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp('^' + re + '$', 'i');
}

async function opfsCollect(startRel, { recursive = false, includeDirs = false, max = 5000, skipTop = null } = {}) {
  const startParts = startRel ? startRel.split('/').filter(Boolean) : [];
  let startDir;
  try { startDir = await opfsResolveDir(startParts); } catch { return null; }
  const out = [];
  async function walk(dir, prefix) {
    const items = [];
    for await (const [nm, h] of dir.entries()) items.push([nm, h]);
    items.sort((a, b) => a[0].localeCompare(b[0]));
    for (const [nm, h] of items) {
      if (out.length >= max) return;
      const full = prefix ? prefix + '/' + nm : nm;
      if (h.kind === 'directory') {
        if (includeDirs) out.push({ path: full, kind: 'directory' });
        if (recursive && !(skipTop && skipTop === full)) await walk(h, full);
      } else { out.push({ path: full, kind: 'file', handle: h }); }
    }
  }
  await walk(startDir, startRel);
  return out;
}

// ── file-content dedupe ──────────────────────────────────────────────────
// Don't re-emit file content the model already has in context. Keyed
// conv|path|range → FNV-1a hash of the exact payload last emitted for that
// slice; an unchanged re-read returns a small stub pointing at the earlier
// copy instead of the bytes. Correctness needs NO write-invalidation
// bookkeeping: the hash is recomputed from the CURRENT file on every read, so
// any change (write_file, edit_file, a run_python write) hashes differently
// and re-emits in full. Cleared on mid-turn compaction — the earlier copy may
// have been summarized away, so the next read must re-emit.
const _emittedFileHashes = new Map();
// Drop every cached read/refusal hash for one path (any offset/limit range and
// the refusal-echo key). MUST run whenever a path's content could have changed
// out from under the cache — write_file, edit_file, delete_file, run_python —
// otherwise a later read_file returns "unchanged, work from your copy" for a
// file that was in fact deleted or rewritten, and the model can't recover it.
// Keys are `conv|path|suffix`; matching `|path|` is exact (a prefix like `foo`
// won't match `foobar` thanks to the trailing separator).
function _invalidateFileCache(norm) {
  if (!norm) return;
  const needle = '|' + norm + '|';
  for (const k of _emittedFileHashes.keys()) if (k.includes(needle)) _emittedFileHashes.delete(k);
}
function _fnv1a(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}

async function tool_read_file({ path, offset, limit, force, _conv }, ctx) {
  await _ensureDbxCtx();   // first-login race: token may not have reached the worker yet (hydration)
  let norm, file;
  if (_betaOn()) {
    // BETA: read directly from Dropbox — anywhere (absolute) or project-relative.
    if (!String(path || '').trim()) return { result: 'Error: path is required.' };
    const r = _betaResolve(path, ctx);
    if (r.kind === 'noproject') return { result: 'Error: "' + path + '" is a project-relative path but this conversation has no project folder. Use an absolute /Dropbox/path, or start a conversation in a project.' };
    if (r.kind === 'dbx') {
      // Reads work anywhere; for an absolute path try the project's namespace then
      // the other, so a home-ns file is reachable from a team-ns project and vice versa.
      let bytes, found = false;
      for (const team of (r.abs ? [r.team, !r.team] : [r.team])) {
        try { bytes = await _dbxDownloadBytes(r.path, team); found = true; break; } catch (_) {}
      }
      if (!found) return { result: 'Error: file not found in Dropbox: ' + r.path };
      norm = r.path;
      const decoded = new TextDecoder().decode(bytes);
      file = { size: bytes.byteLength, text: async () => decoded };
    } else {
      norm = r.rel;   // sandpie/ app metadata — falls through to OPFS below
    }
  }
  if (file === undefined) {
    norm = norm != null ? norm : normFilesPath(path);
    if (!norm) return { result: 'Error: path is required.' };
    try { file = await _opfsGetFile(norm); }
    catch {
      if (_indexEntry(norm)) {
        try { await hydrateAsync(norm); file = await _opfsGetFile(norm); }
        catch (e) { return { result: `Error: ${norm} is in Dropbox but could not be fetched: ${(e && e.message) || e}` }; }
      } else { return { result: 'Error: file not found: ' + norm }; }
    }
  }
  if (file.size > FILE_TEXT_MAX) return { result: `Error: ${norm} is ${file.size} bytes — too large to read as text. Process it with run_python instead.` };
  const text = await file.text();
  if (/\x00/.test(text.slice(0, 4096))) return { result: `Error: ${norm} looks binary. Use load_image (images) or run_python.` };
  const lines = text.split('\n'); const total = lines.length;
  let start = Number.isInteger(offset) && offset > 0 ? offset : 1;
  if (start > total) start = total;
  const lim = Number.isInteger(limit) && limit > 0 ? limit : 2000;
  const end = Math.min(total, start - 1 + lim);
  const header = `${norm} — ${total} line${total === 1 ? '' : 's'}, ${file.size} bytes` + (start > 1 || end < total ? ` (showing ${start}-${end})` : '');
  let buf = header + '\n'; let lastShown = start - 1, truncated = false;
  for (let i = start; i <= end; i++) {
    const row = i + '\t' + lines[i - 1] + '\n';
    if (buf.length + row.length > FILE_TOOL_CAP) { truncated = true; break; }
    buf += row; lastShown = i;
  }
  if (truncated) buf += `…[truncated at line ${lastShown}; call again with offset=${lastShown + 1} for more]`;
  const payload = buf.replace(/\n$/, '');
  // Dedupe: same conversation, same slice, byte-identical payload as the last
  // time we emitted it → stub instead of re-sending content already in context.
  const dedupeKey = (_conv || '') + '|' + norm + '|' + start + '|' + lastShown;
  const h = _fnv1a(payload);
  if (!force && _emittedFileHashes.get(dedupeKey) === h) {
    return { result: header + ' — UNCHANGED since the copy already in your context from an earlier read/write this conversation; not re-emitted. Work from that copy. Pass force:true only if you genuinely need it re-sent.' };
  }
  _emittedFileHashes.set(dedupeKey, h);
  return { result: payload };
}

async function tool_list_files({ path, pattern, recursive, scope }, ctx) {
  await _ensureDbxCtx();   // first-login race: token may not have reached the worker yet
  const rx = pattern ? globToRegExp(pattern) : null;
  const raw = (path == null) ? '' : String(path).trim();
  const connected = !!(_dbxCtx && _dbxCtx.token);

  // BETA: list directly from Dropbox. Default (no path) = the project root;
  // an absolute /path lists anywhere; sandpie/ falls through to the OPFS view.
  if (_betaOn() && scope !== 'workspace') {
    const r = _betaResolve(raw || (ctx && ctx._projectRoot) || '', ctx);
    if (r.kind === 'noproject') return { result: 'Error: no project folder for this conversation. Give an absolute /Dropbox/path, or start a conversation in a project.' };
    if (r.kind === 'dbx') {
      if (!connected) return { result: 'Error: Dropbox is not connected.' };
      let entries = null;
      for (const team of (r.abs ? [r.team, !r.team] : [r.team])) {
        try { const e = await _dbxListFolder(r.path, recursive, team); if (!e.notFound) { entries = e; break; } }
        catch (err) { return { result: (err && err.message) || String(err) }; }
      }
      if (entries === null) return { result: `Not found (or empty): ${r.path}` };
      // Show FULL ABSOLUTE Dropbox paths — one unambiguous path model everywhere,
      // so the model never has to guess what a relative path is relative to.
      const disp = (p) => p;
      const capped = !!entries.capped;
      const rows = rx ? entries.filter(e => rx.test(e.path) || rx.test(e.path.split('/').pop())) : entries;
      const label = r.abs ? (r.path || 'Dropbox root') : (r.rel ? r.rel + '/ (project)' : 'the project folder');
      if (!rows.length) return { result: `No ${pattern ? 'files matching "' + pattern + '"' : 'entries'} in ${label}.` };
      let buf = `${rows.length}${capped ? '+' : ''} entr${rows.length === 1 ? 'y' : 'ies'} in ${label}${pattern ? ' matching "' + pattern + '"' : ''}:\n`;
      let shown = 0, truncated = false;
      for (const e of rows) {
        let line;
        if (e.kind === 'directory') { line = disp(e.path) + '/\n'; }
        else {
          const size = e.size != null ? e.size + 'b' : '?';
          const mtime = e.cloudMtime ? '  ' + new Date(e.cloudMtime).toISOString().slice(0, 16).replace('T', ' ') : '';
          line = `${disp(e.path)}\t${size}${mtime}\n`;
        }
        if (buf.length + line.length > FILE_TOOL_CAP) { truncated = true; break; }
        buf += line; shown++;
      }
      if (truncated) buf += `…[${rows.length - shown} more not shown; narrow with path/pattern]`;
      if (capped) buf += `\n⚠ "${label}" is very large — stopped early; list a subfolder with recursive:false and drill down.`;
      return { result: buf.replace(/\n$/, '') };
    }
    // r.kind === 'opfs' → fall through to the OPFS listing below (sandpie/ view).
  }

  // `scope` decides workspace-vs-cloud (mirrors search):
  //  - 'dropbox' (or 'cloud') → list the connected Dropbox; `path` is an absolute
  //    folder, default = root.
  //  - otherwise (workspace = default) → list the working root (relative `path`);
  //    a bare "/" is the workspace root. An absolute path OUTSIDE the workspace
  //    still lists from the cloud there, so /R+D+I works without scope.
  const cloudScope = (scope === 'dropbox' || scope === 'cloud');
  let outsideRoot = false, norm = '', cloudPath = '';
  if (cloudScope) {
    outsideRoot = true;
    cloudPath = (raw === '' || raw === '/') ? '' : (raw.startsWith('/') ? raw : '/' + raw);
  } else if (raw.startsWith('/')) {
    const rel = _relUnderRoot(raw);
    if (rel == null && raw !== '/') { outsideRoot = true; cloudPath = raw; }
    else { norm = rel || ''; }
  } else {
    norm = normFilesPath(raw);
  }

  // ---- Dropbox (cloud) listing ----
  if (outsideRoot) {
    if (!connected) return { result: 'Error: a Dropbox listing needs Dropbox connected (scope:"dropbox").' };
    const cs = cloudPath.replace(/\/+$/, '');
    const label = cs || 'Dropbox root';
    let entries;
    try { entries = await _dropboxListFolder(cs, recursive); }
    catch (e) { return { result: e.message }; }
    const capped = !!entries.capped;   // the subtree was bigger than we scanned
    const rows = rx ? entries.filter(e => rx.test(e.path) || rx.test(e.path.split('/').pop())) : entries;
    if (!rows.length) return { result: `No ${pattern ? 'files matching "' + pattern + '"' : 'entries'} in ${label}.` };
    let buf = `${rows.length}${capped ? '+' : ''} entr${rows.length === 1 ? 'y' : 'ies'} in ${label}${pattern ? ' matching "' + pattern + '"' : ''}:\n`;
    let shown = 0, truncated = false;
    for (const e of rows) {
      let line;
      if (e.kind === 'directory') { line = e.path + '/\n'; }
      else {
        const size = e.size != null ? e.size + 'b' : '?';
        const mtime = e.cloudMtime ? '  ' + new Date(e.cloudMtime).toISOString().slice(0, 16).replace('T', ' ') : '';
        line = `${e.path}\t${size}${mtime}\n`;
      }
      if (buf.length + line.length > FILE_TOOL_CAP) { truncated = true; break; }
      buf += line; shown++;
    }
    if (truncated) buf += `…[${rows.length - shown} more not shown; narrow with path/pattern]`;
    if (capped) buf += `\n⚠ "${label}" is very large — stopped after ${entries.length} entries; the full subtree was NOT scanned. Don't list a big Dropbox tree recursively: list a specific subfolder with recursive:false and drill down, or use search to find files by content.`;
    return { result: buf.replace(/\n$/, '') };
  }

  // ---- INSIDE working root (or relative) → OPFS + cloud index merge ----
  let entries = await opfsCollect(norm, { recursive: !!recursive, includeDirs: !recursive, max: 4000 });
  const idxEntries = _indexEntriesUnder(norm, !!recursive);   // [] unless dehydrated mode is on
  if (entries === null && !idxEntries.length) return { result: 'Error: not a directory: ' + (norm || '/files/') };
  entries = entries || [];
  if (idxEntries.length) {
    const seen = new Set(entries.map(e => e.path));   // local (OPFS) entries win — they reflect hydration
    for (const ie of idxEntries) if (!seen.has(ie.path)) entries.push(ie);
    entries.sort((a, b) => a.path.localeCompare(b.path));
  }
  const rows = rx ? entries.filter(e => rx.test(e.path) || rx.test(e.path.split('/').pop())) : entries;
  if (!rows.length) return { result: `No ${pattern ? 'files matching "' + pattern + '"' : 'entries'} under /${norm || ''}.` };
  let buf = `${rows.length} entr${rows.length === 1 ? 'y' : 'ies'} under /${norm || ''}${pattern ? ' matching "' + pattern + '"' : ''}:\n`;
  let shown = 0, truncated = false;
  for (const e of rows) {
    let line;
    if (e.kind === 'directory') { line = e.path + '/\n'; }
    else {
      let size = '?', mtime = '';
      if (e.handle) {
        try { const f = await e.handle.getFile(); size = f.size + 'b'; mtime = '  ' + new Date(f.lastModified).toISOString().slice(0, 16).replace('T', ' '); } catch {}
      } else if (e.size != null) {            // index-only (not yet hydrated) — size/mtime from Dropbox metadata
        size = e.size + 'b';
        if (e.cloudMtime) { try { mtime = '  ' + new Date(e.cloudMtime).toISOString().slice(0, 16).replace('T', ' '); } catch {} }
      }
      line = `${e.path}\t${size}${mtime}\n`;
    }
    if (buf.length + line.length > FILE_TOOL_CAP) { truncated = true; break; }
    buf += line; shown++;
  }
  if (truncated) buf += `…[${rows.length - shown} more not shown; narrow with path/pattern]`;
  return { result: buf.replace(/\n$/, '') };
}

// ---- search (unified: local grep + Dropbox content search, path-aware) -----
// Literal words (>=3 chars) lifted from the regex, used to narrow the cloud leg
// (Dropbox search is keyword-based, not regex).
function _searchLiterals(pattern) {
  const terms = String(pattern).match(/[A-Za-z0-9_]{3,}/g) || [];
  return [...new Set(terms)].sort((a, b) => b.length - a.length).slice(0, 4);
}
// Bare file extensions from an `include` glob ("*.jpg", "**/*.md", "*.{jpg,png}",
// "*.jpg *.png") → for Dropbox search_v2's file_extensions filter. null if none.
function _globExtensions(glob) {
  if (!glob) return null;
  // Expand "PFX{a,b}" → "PFXa PFXb" first, so a comma INSIDE braces isn't treated
  // as a separator ("*.{pdf,docx}" → "*.pdf *.docx").
  const expanded = String(glob).replace(/([^\s,]*)\{([^}]*)\}/g, (_, pfx, inner) => inner.split(',').map(s => pfx + s.trim()).join(' '));
  const out = new Set();
  for (const g of expanded.split(/[\s,]+/).filter(Boolean)) {
    const m = /\.([A-Za-z0-9]+)$/.exec(g);   // require a dot so a name glob ("report_*") isn't read as an extension
    if (m) out.add(m[1].toLowerCase());
  }
  return out.size ? [...out] : null;
}
async function _opfsExists(rel) { try { await _opfsGetFile(rel); return true; } catch { return false; } }
// Working-root-relative form of a Dropbox absolute path, or null if outside it.
function _relUnderRoot(absPath) {
  const wr = ((_dbxCtx && _dbxCtx.workingRoot) || '').replace(/\/+$/, '').toLowerCase();
  const p = String(absPath).replace(/\/+$/, '');
  if (!wr) return null;
  if (p.toLowerCase() === wr) return '';
  if (p.toLowerCase().startsWith(wr + '/')) return p.slice(wr.length + 1);
  return null;
}
// Dropbox search_v2 → sorted path_display list. Throws on API error.
// `team` picks the namespace: true = the TEAM space (so /R+D+I and friends are
// reachable from a scope:"dropbox" search), false = the user's home namespace,
// which is where the workspace itself lives (the dehydrated in-workspace merge).
async function _dropboxSearchPaths(query, searchPath, filenameOnly, fileExtensions, team = true) {
  const headers = _dbxHeaders(true, team);
  // max_results max is 1000; fetch up to that so we can report a count AND
  // paginate the display. has_more ⇒ still more beyond 1000 (reported as "1000+").
  const opts = { path: searchPath || '', max_results: 1000, file_status: 'active', filename_only: !!filenameOnly };
  if (Array.isArray(fileExtensions) && fileExtensions.length) opts.file_extensions = fileExtensions;   // type filter (from `include`)
  const body = JSON.stringify({ query, options: opts });
  const res = await fetch('https://api.dropboxapi.com/2/files/search_v2', { method: 'POST', headers, body });
  if (!res.ok) { const txt = await res.text().catch(() => ''); throw new Error('Dropbox search failed (' + res.status + '): ' + txt.slice(0, 300)); }
  const data = await res.json();
  const matches = Array.isArray(data.matches) ? data.matches : [];
  const paths = matches.map(m => { const meta = m.metadata?.metadata || m.metadata || {}; return meta.path_display || meta.path_lower || ''; }).filter(Boolean);
  return { paths: paths.sort(), hasMore: !!data.has_more };
}
// Format a cloud-search result as ONE page (100 paths) + the total count + paging
// hints, so the model can page (offset) or narrow — instead of hitting a wall.
function _formatCloudPage(r, query, scope, offset) {
  const PAGE = 100;
  const total = r.paths.length;                          // capped at the 1000 fetch
  const totalStr = r.hasMore ? `${total}+` : String(total);
  const off = Math.max(0, parseInt(offset, 10) || 0);
  const page = r.paths.slice(off, off + PAGE);
  // In beta, read_file works on any Dropbox path directly (no copy-in step), so the
  // "outside your workspace" note is dropped.
  const note = _betaOn() ? '' : ' (outside your workspace — copy one in with copy_to_workspace("<path>"), then read_file/load_image it)';
  if (!page.length) return `No more cloud matches for "${query}" in ${scope} — ${totalStr} total; offset ${off} is past the end.`;
  if (total <= PAGE && off === 0) return `${total} file(s) matching "${query}" in ${scope}${note}:\n` + page.join('\n');
  const end = off + page.length;
  const hints = [];
  if (end < total) hints.push(`call search again with offset:${end} for the next ${Math.min(PAGE, total - end)}`);
  if (r.hasMore && end >= total) hints.push(`>${total} matches total — narrow the path/term to reach the rest`);
  hints.push('or narrow the path/term for fewer, more relevant matches');
  return `${totalStr} files match "${query}" in ${scope} — showing ${off + 1}-${end}${note}:\n` + page.join('\n') + `\n(${hints.join('; ')}.)`;
}
async function _dropboxListFolder(folderPath, recursive) {
  const headers = _dbxHeaders(true, true);   // team namespace — cloud browse
  const body = JSON.stringify({ path: folderPath || '', recursive: !!recursive, include_mounted_folders: false, include_deleted: false, include_has_explicit_shared_members: false, limit: 999 });
  let res = await fetch('https://api.dropboxapi.com/2/files/list_folder', { method: 'POST', headers, body });
  if (!res.ok) { const txt = await res.text().catch(() => ''); throw new Error('Dropbox list failed (' + res.status + '): ' + txt.slice(0, 300)); }
  let data = await res.json();
  let entries = data.entries || [];
  // Cap pagination. A recursive list over a large Dropbox subtree can be MILLIONS
  // of entries and would never return (the tool call hangs). Bound it to ~2-3 API
  // calls and flag it as `capped` so the caller can steer the model to narrow.
  const LIST_CAP = recursive ? 1500 : 6000;
  let capped = false;
  while (data.has_more && entries.length < LIST_CAP) {
    res = await fetch('https://api.dropboxapi.com/2/files/list_folder/continue', { method: 'POST', headers: headers, body: JSON.stringify({ cursor: data.cursor }) });
    data = await res.json();
    entries = entries.concat(data.entries || []);
  }
  if (data.has_more) capped = true;                 // more remained beyond the cap
  if (entries.length > LIST_CAP) entries = entries.slice(0, LIST_CAP);
  const rows = entries.map(e => ({
    path: e.path_display || e.path_lower,
    kind: e['.tag'] === 'folder' ? 'directory' : 'file',
    size: e.size,
    cloudMtime: e.client_modified
  }));
  rows.capped = capped;
  return rows;
}
async function _localGrep(rx, norm, include, files_only) {
  const inc = include ? globToRegExp(include) : null;
  const skipTop = norm.startsWith(SEARCH_SKIP_TOP) ? null : SEARCH_SKIP_TOP;
  const files = await opfsCollect(norm, { recursive: true, includeDirs: false, max: 6000, skipTop });
  if (files === null) return null;
  let buf = '', matches = 0, scanned = 0, truncated = false;
  const hitFiles = new Set();
  for (const f of files) {
    if (inc && !(inc.test(f.path) || inc.test(f.path.split('/').pop()))) continue;
    let text;
    try { const file = await f.handle.getFile(); if (file.size > FILE_TEXT_MAX) continue; text = await file.text(); } catch { continue; }
    if (/\x00/.test(text.slice(0, 4096))) continue;
    scanned++;
    const fl = text.split('\n');
    for (let i = 0; i < fl.length; i++) {
      if (!rx.test(fl[i])) continue;
      matches++; hitFiles.add(f.path);
      if (files_only) break;
      const row = `${f.path}:${i + 1}: ${fl[i].trim().slice(0, 300)}\n`;
      if (buf.length + row.length > FILE_TOOL_CAP) { truncated = true; break; }
      buf += row;
    }
    if (truncated) break;
  }
  return { buf, matches, scanned, truncated, hitFiles };
}

// Lazily obtain the Dropbox token from the page. The page pushes it once at load
// (pushDbxTokenToSW), but on FIRST login the OAuth code exchange completes AFTER
// that one-shot push already dead-ended on empty tokens — so without this, every
// Dropbox-needing tool reports 'not connected' until a page reload. When the
// worker lacks a token it asks the page (dbx-request-token -> dbx-token-ack) and
// waits for the push; ok:false (or timeout) means truly unconnected → error out
// as before instead of stalling.
async function _ensureDbxCtx(timeoutMs = 4000) {
  if (_dbxCtx && _dbxCtx.token) return true;
  const id = ++_dbxReqSeq;
  const p = new Promise((resolve) => {
    _dbxTokenReq = { id, resolve, timer: setTimeout(() => resolve(false), timeoutMs) };
  });
  try { self.postMessage({ type: 'dbx-request-token', id }); } catch (_) {}
  await p;
  return !!(_dbxCtx && _dbxCtx.token);
}

// Unified search. Path-aware: inside the working root it greps local files and
// (when dehydrated) merges Dropbox content-search hits for un-downloaded files;
// an absolute Dropbox path OUTSIDE the working root does a pure cloud search.
async function tool_search({ pattern, path, include, files_only, ignore_case, offset, scope }, ctx) {
  if (!pattern) return { result: 'Error: pattern (a regular expression) is required.' };
  let rx; try { rx = new RegExp(pattern, ignore_case === false ? '' : 'i'); }
  catch (e) { return { result: 'Error: invalid regex: ' + (e && e.message || e) }; }

  await _ensureDbxCtx();   // first-login race: token may not have reached the worker yet
  const connected = !!(_dbxCtx && _dbxCtx.token);

  // BETA: there is no OPFS workspace to grep. A default (non-cloud) search runs a
  // Dropbox content search scoped to the project folder; scope:"dropbox" with an
  // absolute path still searches anywhere (handled by the shared cloud leg below).
  if (_betaOn() && scope !== 'dropbox' && scope !== 'cloud') {
    const rawB = (path == null) ? '' : String(path).trim();
    if (!rawB.startsWith('/')) {   // project-scoped search
      if (!connected) return { result: 'Error: Dropbox is not connected.' };
      const proj = (ctx && ctx._projectRoot) ? String(ctx._projectRoot).replace(/\/+$/, '') : '';
      if (!proj) return { result: 'This conversation has no project folder. Use scope:"dropbox" with an absolute folder path to search Dropbox.' };
      const team = !!(ctx && ctx._projectNs === 'team');
      const lits = _searchLiterals(pattern);
      if (!lits.length) return { result: 'To search, give a keyword (≥3 chars). Dropbox search matches file NAMES + text contents by keyword (regex is reduced to its literal words).' };
      const scopePath = proj + (rawB ? '/' + rawB.replace(/^files\//, '').replace(/\/+$/, '') : '');
      const exts = _globExtensions(include);
      let r; try { r = await _dropboxSearchPaths(lits.join(' '), scopePath, false, exts, team); }
      catch (e) { return { result: (e && e.message) || String(e) }; }
      let paths = r.paths;
      if (include) { const ig = globToRegExp(include); paths = paths.filter(p => ig.test(p) || ig.test(p.split('/').pop())); }
      // Full absolute paths (see list_files) — no relative-vs-absolute ambiguity.
      const label = rawB ? rawB + '/ (project)' : 'the project folder';
      if (!paths.length) return { result: `No files found for "${lits.join(' ')}" in ${label}.` };
      return { result: _formatCloudPage({ paths, hasMore: r.hasMore }, lits.join(' '), label, offset) };
    }
    // absolute path in beta → fall through to the shared cloud leg (read-anywhere).
  }
  const wr = ((_dbxCtx && _dbxCtx.workingRoot) || '').replace(/\/+$/, '');
  const raw = (path == null) ? '' : String(path).trim();
  const relIfAbs = raw.startsWith('/') ? _relUnderRoot(raw) : undefined;

  // `scope` decides local-vs-cloud — don't infer it from the path.
  //  - 'dropbox' (or 'cloud') → search the connected Dropbox; `path` (absolute)
  //    narrows it, default = all of Dropbox. A bare "/" means the WORKSPACE root,
  //    not the cloud (consistent with read_file / list_files).
  //  - otherwise (workspace = default) → grep the working root; but an absolute
  //    path that falls OUTSIDE the workspace still cloud-searches there, so passing
  //    e.g. /R+D+I directly works without scope.
  const wantCloud = (scope === 'dropbox' || scope === 'cloud')
    || (raw.startsWith('/') && raw !== '/' && relIfAbs == null);

  if (wantCloud) {
    if (!connected) return { result: 'Error: a Dropbox (cloud) search needs Dropbox connected.' };
    let cs;
    if (scope === 'dropbox' || scope === 'cloud') cs = (raw === '' || raw === '/') ? '' : (raw.startsWith('/') ? raw : '/' + raw);
    else cs = raw;                                   // implicit: an absolute path outside the workspace
    const cloudScope = cs.replace(/\/+$/, '');
    const label = cloudScope || 'all of Dropbox';
    const lits = _searchLiterals(pattern);
    if (!lits.length) return { result: 'To search Dropbox, give a keyword (≥3 chars). Dropbox search matches file NAMES + text contents by keyword (regex is reduced to its literal words).' };
    const exts = _globExtensions(include);            // `include` → server-side file-type filter
    let r; try { r = await _dropboxSearchPaths(lits.join(' '), cloudScope, false, exts); }
    catch (e) { return { result: e.message }; }
    let paths = r.paths;
    if (include) { const ig = globToRegExp(include); paths = paths.filter(p => ig.test(p) || ig.test(p.split('/').pop())); }
    let clabel = label; if (include) clabel += ' [' + include + ']';
    if (!paths.length) return { result: `No cloud files found for "${lits.join(' ')}" in ${clabel}.` };
    return { result: _formatCloudPage({ paths, hasMore: r.hasMore }, lits.join(' '), clabel, offset) };
  }

  // WORKSPACE scope → local grep (+ dehydrated cloud merge within the workspace).
  const norm = raw.startsWith('/') ? (relIfAbs || '') : normFilesPath(raw);
  const cloudScope = wr + (norm ? '/' + norm : '');
  const local = await _localGrep(rx, norm, include, files_only);
  if (local === null) return { result: 'Error: not a directory: ' + (norm || '/files/') };
  const where = norm ? '/' + norm : '/files/';

  // Dehydrated → also surface matching cloud files not downloaded locally.
  let cloudExtra = '';
  if (_dehydrated && connected) {
    const lits = _searchLiterals(pattern);
    if (lits.length) {
      try {
        // team:false — cloudScope is under the workspace root, i.e. the home namespace.
        const r = await _dropboxSearchPaths(lits.join(' '), cloudScope, false, _globExtensions(include), false);
        const CAP = 100;
        const cloudOnly = [];
        let scanned = 0;
        for (const p of r.paths) {
          if (cloudOnly.length >= CAP || scanned >= 500) break;   // bound the per-path OPFS checks
          scanned++;
          const rel = _relUnderRoot(p);
          if (rel == null || _relExempt(rel)) continue;
          if (local.hitFiles.has(rel)) continue;        // already shown with line matches
          if (await _opfsExists(rel)) continue;          // hydrated locally → already grepped
          cloudOnly.push(rel);
        }
        if (cloudOnly.length) {
          cloudExtra = `\n\nCloud files also matching "${lits.join(' ')}" (not downloaded — open with read_file):\n` + cloudOnly.sort().join('\n');
          if (cloudOnly.length >= CAP || r.hasMore) cloudExtra += `\n(More cloud files match — narrow the path/pattern to list them all.)`;
        }
      } catch (_) { /* cloud leg is best-effort */ }
    }
  }

  if (files_only) {
    const head = local.hitFiles.size
      ? `${local.hitFiles.size} local file(s) match (scanned ${local.scanned}):\n` + [...local.hitFiles].sort().join('\n')
      : `No local files contain /${pattern}/ in ${where}. Scanned ${local.scanned}.`;
    return { result: head + cloudExtra };
  }
  if (!local.matches) return { result: `No local matches for /${pattern}/ in ${where}. Scanned ${local.scanned} files.` + cloudExtra };
  const head = `${local.matches} match${local.matches === 1 ? '' : 'es'} in ${local.hitFiles.size} file${local.hitFiles.size === 1 ? '' : 's'} (scanned ${local.scanned})${local.truncated ? ' — truncated; narrow the pattern or path' : ''}:\n`;
  return { result: head + local.buf.replace(/\n$/, '') + cloudExtra };
}

// Installed shared packages live under this root. Edits there are allowed and
// write back to the hub via sharing.js (editor write-back, rev-gated); the
// constant is still used by the fork helper to lift copies out of this area.
const SHARED_ROOT = 'sandpie/shared-installed/';

// If a destination already exists in OPFS, append _2/_3/… before the extension.
async function _opfsAutorename(rel) {
  const exists = async (r) => { try { await opfsReadBytes(r); return true; } catch (_) { return false; } };
  if (!(await exists(rel))) return rel;
  const slash = rel.lastIndexOf('/'), dir = slash >= 0 ? rel.slice(0, slash + 1) : '';
  const base = slash >= 0 ? rel.slice(slash + 1) : rel;
  const dot = base.lastIndexOf('.'), stem = dot > 0 ? base.slice(0, dot) : base, ext = dot > 0 ? base.slice(dot) : '';
  for (let i = 2; i < 1000; i++) { const cand = dir + stem + '_' + i + ext; if (!(await exists(cand))) return cand; }
  return dir + stem + '_' + base.length + ext;
}

// Fork a LOCAL workspace file (e.g. a read-only shared package) into an editable
// location. No Dropbox needed. Files only for now — folder forking arrives with
// the package registry.
async function _forkLocal(src, dest, ctx) {
  const srcRel = src.replace(/^\/+/, '').replace(/^files\//, '');
  let destRel;
  if (dest != null && String(dest).trim()) {
    destRel = String(dest).trim().replace(/^\/+/, '').replace(/^files\//, '').replace(/\/+$/, '');
  } else {
    const base = srcRel.split('/').pop();
    destRel = base;   // lift out of the managed area to the workspace root (visible — the sandbox is system-only)
  }
  if (!destRel || destRel.split('/').some(s => s === '..')) return { result: 'Error: invalid "dest".' };
  if (destRel.startsWith(SHARED_ROOT)) return { result: 'Error: "dest" cannot be inside sandpie/shared-installed/ — that area is managed by the hub sync. Pick an editable location outside it.' };
  let bytes;
  try { bytes = await opfsReadBytes(srcRel); }
  catch (_) { return { result: `Error: "${srcRel}" not found in your workspace. (If it's a folder, fork individual files — folder forking isn't supported yet.)` }; }
  destRel = await _opfsAutorename(destRel);
  try {
    await opfsWriteBytes(destRel, bytes);
    self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [destRel], owner: ctx && ctx.agentId } });
    _pyBroadcast({ type: 'fs-changed', rel: destRel });
    return { result: `Forked ${srcRel} → ${destRel} — your editable copy. Edit "${destRel}"; the shared original stays managed and keeps auto-updating.` };
  } catch (e) { return { result: `Fork failed: ${(e && e.message) || e}` }; }
}

// ---- copy_to_workspace — fork a local workspace file (e.g. a read-only shared
// package) into an editable copy, OR import a file from elsewhere in Dropbox INTO
// the working root. READ-ONLY on the source either way.
//
// The source (a team/department folder) and the destination (the workspace) are in
// DIFFERENT Dropbox namespaces now — team root vs the user's home namespace — so a
// single server-side copy_v2 can't span them with one path-root header. Instead we
// pull the bytes down into OPFS as a NEW local file; it has no sync-state entry, so
// the next sync pushes it up to the workspace. (The old code copied server-side and
// then downloaded the result anyway, so this is the same number of transfers.)
// Folders still use copy_v2, with the destination written as a namespace-relative
// "ns:<home_namespace_id>/…" path so the copy can cross namespaces server-side.
// Only offered when Dropbox is connected (gated in tools.js toolDefs).
async function tool_copy_to_workspace({ src, dest }, ctx) {
  await _ensureDbxCtx();   // first-login race: token may not have reached the worker yet (cloud import)
  const from = (src == null ? '' : String(src)).trim();
  if (!from) return { result: 'Error: "src" is required (a source path — anywhere in Dropbox — to copy into the project).' };
  // BETA: copy(src, dest) — src from anywhere in Dropbox, dest into the project
  // folder (harness-guarded). Server-side copy_v2 within a namespace, else
  // download+upload across namespaces.
  if (_betaOn()) {
    if (!_dbxCtx || !_dbxCtx.token) return { result: 'Error: Dropbox is not connected.' };
    const sres = _betaResolve(from, ctx);
    if (sres.kind === 'noproject') return { result: 'Error: "' + from + '" is project-relative but this conversation has no project folder. Give an absolute source path.' };
    if (sres.kind === 'opfs') return { result: 'Error: sandpie/ is app metadata, not a copy source. Copy a Dropbox file instead.' };
    const srcPath = sres.path;
    // Find the source and its namespace (read-anywhere: try project ns then the other).
    const sm = await _dbxMetaAnyNs(srcPath, sres.team);
    if (!sm.meta) return { result: 'Copy failed — source not found: ' + srcPath };
    const isFolder = sm.meta['.tag'] === 'folder';
    // Dest defaults to the source basename, placed in the project root.
    const destRaw = (dest != null && String(dest).trim()) ? String(dest).trim() : srcPath.split('/').filter(Boolean).pop();
    const dres = _betaResolve(destRaw, ctx);
    if (dres.kind === 'noproject') return { result: 'Error: no project folder to copy into.' };
    if (dres.kind === 'opfs') return { result: 'Error: cannot copy into sandpie/ (app metadata).' };
    const destPath = dres.path;
    const err = _betaWriteGuard(destPath, ctx);
    if (err) return { result: err };
    try {
      const meta = await _dbxCopy(srcPath, sm.team, destPath, dres.team, isFolder);
      _betaTouch(ctx, destPath);
      const finalPath = meta.path_display || destPath;
      return { result: `Copied ${isFolder ? 'folder ' : ''}into your project as ${finalPath}${(!isFolder && meta.size != null) ? ' (' + meta.size + ' bytes)' : ''}. Use read_file / run_python on it.` };
    } catch (e) { return { result: 'Copy failed: ' + ((e && e.message) || e) }; }
  }
  // Non-absolute path → a LOCAL workspace file (e.g. sandpie/shared-installed/…): fork in OPFS, no Dropbox needed.
  if (!from.startsWith('/')) return _forkLocal(from, dest, ctx);
  // Absolute path → import from elsewhere in the user's Dropbox (needs Dropbox connected).
  if (!_dbxCtx || !_dbxCtx.token) return { result: 'Error: Dropbox is not connected.' };
  const wr = (_dbxCtx.workingRoot || '').replace(/\/+$/, '');
  if (!wr) return { result: 'Error: your workspace folder is not resolved yet — try again in a moment.' };
  let rel = (dest != null && String(dest).trim())
    ? String(dest).trim().replace(/^\/+/, '').replace(/^files\//, '').replace(/\/+$/, '')
    : from.split('/').filter(Boolean).pop();
  if (!rel || rel.split('/').some(s => s === '..')) return { result: 'Error: invalid "dest".' };
  const teamHeaders = _dbxHeaders(true, true);    // source: team namespace (cloud browse)
  const homeHeaders = _dbxHeaders(true, false);   // destination: the workspace

  // What is the source? Determines file (pull bytes) vs folder (server-side copy).
  let meta = {};
  try {
    const mRes = await fetch('https://api.dropboxapi.com/2/files/get_metadata', { method: 'POST', headers: teamHeaders, body: JSON.stringify({ path: from }) });
    if (!mRes.ok) { const txt = await mRes.text().catch(() => ''); return { result: 'Copy failed — cannot read "' + from + '" (' + mRes.status + '): ' + txt.slice(0, 300) }; }
    meta = (await mRes.json().catch(() => ({}))) || {};
  } catch (e) { return { result: 'Error reaching Dropbox: ' + (e && e.message || e) }; }

  if (meta['.tag'] === 'folder') {
    const homeNs = _dbxCtx.homeNs || '';
    const toPath = (_dbxCtx.teamRoot && homeNs) ? ('ns:' + homeNs + wr + '/' + rel) : (wr + '/' + rel);
    let res;
    try { res = await fetch('https://api.dropboxapi.com/2/files/copy_v2', { method: 'POST', headers: teamHeaders, body: JSON.stringify({ from_path: from, to_path: toPath, autorename: true }) }); }
    catch (e) { return { result: 'Error reaching Dropbox: ' + (e && e.message || e) }; }
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      return { result: 'Folder copy failed (' + res.status + '): ' + txt.slice(0, 400) + '\nYour workspace is in your own Dropbox, so copying a whole team folder across is not always possible — copy the individual files you need instead.' };
    }
    const fm = ((await res.json().catch(() => ({}))) || {}).metadata || {};
    const finalRel = rel.replace(/[^/]+$/, fm.name || rel.split('/').pop());
    if (_dehydrated) {
      if (!_dbxIndex) _dbxIndex = {};
      _dbxIndex[finalRel] = { name: fm.name || finalRel.split('/').pop(), kind: 'folder', path: wr + '/' + finalRel, cloudMtime: fm.server_modified };
    }
    return { result: `Copied folder into your workspace as ${finalRel}/. Its files appear after the next sync; then use list_files / read_file on them.` };
  }

  // File: pull the bytes straight into OPFS.
  const finalRel = rel;
  try {
    const tlRes = await fetch('https://api.dropboxapi.com/2/files/get_temporary_link', { method: 'POST', headers: teamHeaders, body: JSON.stringify({ path: from }) });
    if (!tlRes.ok) { const txt = await tlRes.text().catch(() => ''); return { result: 'Copy failed — cannot download "' + from + '" (' + tlRes.status + '): ' + txt.slice(0, 300) }; }
    const dl = await fetch((await tlRes.json()).link, { method: 'GET' });
    if (!dl.ok) return { result: 'Copy failed — download returned ' + dl.status + '.' };
    await opfsWriteBytes(finalRel, new Uint8Array(await dl.arrayBuffer()));
  } catch (e) { return { result: 'Copy failed: ' + ((e && e.message) || e) }; }

  // Deliberately NOT _reportHydrated(): that would record the file as an already-
  // synced cloud copy. It must be marked DIRTY (sw-opfs-changed → syncedMtime:0),
  // like every other file writer: that is what makes the next sync UPLOAD it into
  // the workspace. Without the post the page had no sync-state entry at all, and
  // the sync's orphan cleanup (a local file absent from the cloud, no state, not
  // pending) DELETED the copy within a minute of the tool reporting success.
  try { self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [finalRel], owner: ctx && ctx.agentId } }); } catch (_) {}
  _pyBroadcast({ type: 'fs-changed', rel: finalRel });   // run_python sees it now
  return { result: `Copied into your workspace as ${finalRel}${meta.size != null ? ' (' + meta.size + ' bytes)' : ''} — ready to use now, and uploaded to your Dropbox on the next sync. Use read_file or run_python on "${finalRel}".` };
}

const KNOWN_TOOLS = ['run_python','pyodide','shell','walios','write_file','edit_file','read_file','list_files','search','web_search','read_url','copy_to_workspace','copy','show_artifact','load_skill','load_image','write_todos','scratch','spawn_subagent','share','html_console','screenshot','ask','respond'];

// ============================================================
// shell — a real terminal on the relay host, straight from the worker (no Pyodide).
// ------------------------------------------------------------
// One tool for everything: local commands, `ssh …` / `scp …` (the relay host's
// own shell + ~/.ssh do the work — nothing special here), and file writes via
// stdin. The command is sent as a bash -lc argv element so bash is the ONLY
// parser (exactly like typing at a prompt — no PowerShell, no wsl wrap, no tool
// re-splitting). Optional file/stdin content rides a separate base64 stdin field,
// so writing a file (`cat > f`, stdin=content) is escaping-proof.
function _shq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }
function _b64utf8(s) { try { return btoa(unescape(encodeURIComponent(s))); } catch (_) { return btoa(s); } }
async function tool_shell({ command, stdin, cwd, timeout }, ctx) {
  if (!command || !String(command).trim()) return { result: 'Error: "command" is required.' };
  const base = ((ctx && ctx._shellRelayUrl) || 'http://localhost:8765').replace(/\/+$/, '');
  const url = base + '/shell/exec';
  let t = Number(timeout); if (!isFinite(t) || t <= 0) t = 30; t = Math.min(300, Math.round(t));
  const cmd = cwd ? ('cd ' + _shq(cwd) + ' || exit 1\n' + command) : String(command);
  const payload = { argv: ['bash', '-lc', cmd], timeout: t };
  if (stdin != null && stdin !== '') payload.stdin = _b64utf8(String(stdin));
  const ctl = new AbortController();
  // Track WHY the fetch ends so we don't mislabel a timeout/turn-abort as a dead
  // relay. Client timeout = server deadline (t+3s) + a little slack.
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctl.abort(); }, (t + 6) * 1000);
  if (ctx && ctx.signal) { if (ctx.signal.aborted) ctl.abort(); else ctx.signal.addEventListener('abort', () => ctl.abort(), { once: true }); }
  let r;
  try {
    r = await fetch(url, { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: ctl.signal });
  } catch (e) {
    clearTimeout(timer);
    // Three distinct outcomes — don't conflate them:
    if (ctx && ctx.signal && ctx.signal.aborted && !timedOut) return { result: 'Error: command aborted (turn stopped).' };
    if (timedOut) return { result: 'Error: command did not return within ' + t + 's and was abandoned client-side — it MAY STILL BE RUNNING on the relay. Do not assume it failed. For a long job, background it so the call returns immediately: `setsid <cmd> >/tmp/job.log 2>&1 & echo $!` then poll the log with another shell call. To wait longer inline, raise "timeout" (max 300).' };
    return { result: 'Error: cannot reach the relay at ' + base + ' — it appears down. Start it in your target env (e.g. WSL): `node server.js` in the relay folder. Do NOT retry in a loop; ask the user. (' + ((e && e.message) || e) + ')' };
  }
  clearTimeout(timer);
  let data; try { data = await r.json(); } catch (_) { data = null; }
  if (!r.ok || !data) return { result: 'Error: relay HTTP ' + r.status + (data && data.error ? ' — ' + data.error : '') };
  let out = '';
  if (data.stdout) out += String(data.stdout).replace(/\n+$/, '');
  if (data.stderr) out += (out ? '\n' : '') + '--- stderr ---\n' + String(data.stderr).replace(/\n+$/, '');
  out += (out ? '\n' : '') + '[exit ' + (data.code != null ? data.code : '?') + (data.signal ? ' signal=' + data.signal : '') + ']';
  return { result: out };
}

// ── walios headless tool ────────────────────────────────────────────────────
// Runs a shell script inside the WALI wasm-OS (the /walios/ app's syscall-host
// worker, same origin). No terminal: busybox ash -c <script>, pty:false. The
// script arrives in BLOB form (<|walios|>…<|end_walios|>) parsed by
// parseWaliosBlobCalls — never JSON-escaped by the model. /root is the FULL
// origin OPFS root (same namespace as the app's /files) — persistent across
// calls, and rm there deletes real workspace files. Networking goes through
// the WISP relay (wss://<host>/wisp): wget/nc/ssh/ping work.
const WALIOS_BASE = '/walios/';
const WALIOS_BB = 'busybox.wasm?v=net4';
const WALIOS_MANIFEST = {
  busybox: WALIOS_BB, sh: WALIOS_BB, ash: WALIOS_BB, hush: WALIOS_BB,
  python: 'python.wasm', python3: 'python.wasm', lua: 'lua.wasm',
  ssh: 'ssh.wasm?v=ssl2', slogin: 'ssh.wasm?v=ssl2',
  make: 'make.wasm', gmake: 'make.wasm',
};
let _waliosWorker = null, _waliosQueue = Promise.resolve();

// pkgcache: binaries other users compiled in-tab (e.g. git) live on the server
// (/walios/pkgcache/<name>.wasm + index.json). The terminal.html page folds them
// into its manifest; the headless tool must do the same or `git` is missing.
// Cached once per worker lifetime; built-in WALIOS_MANIFEST entries always win.
let _waliosPkgM = null;
async function _waliosPkgManifest() {
  if (_waliosPkgM) return _waliosPkgM;
  try {
    const r = await fetch(WALIOS_BASE + 'pkgcache/index.json');
    const idx = r.ok ? await r.json() : null;
    const m = {};
    if (idx && Array.isArray(idx.packages))
      for (const n of idx.packages) if (!WALIOS_MANIFEST[n]) m[n] = 'pkgcache/' + n + '.wasm';
    return (_waliosPkgM = m);
  } catch (_) { return (_waliosPkgM = {}); }
}
function _waliosEnsure() {
  if (_waliosWorker) return _waliosWorker;
  const w = new Worker(WALIOS_BASE + 'wali-worker.js');
  try {   // OPFS bridge: persistent /root home (full origin OPFS root). Optional.
    const opfsSab = new SharedArrayBuffer(32 + (1 << 20));
    const opfsWorker = new Worker(WALIOS_BASE + 'opfs-worker.js');
    opfsWorker.postMessage({ t: 'sab', sab: opfsSab });
    w.postMessage({ t: 'opfs-sab', sab: opfsSab });
  } catch (_) { /* no cross-origin isolation → RAM-only VFS */ }
  try {   // WISP bridge: real TCP/UDP via the relay. Optional.
    const wispSab = new SharedArrayBuffer(32 + 65536);
    const wispWorker = new Worker(WALIOS_BASE + 'wisp-worker.js');
    wispWorker.postMessage({ t: 'sab', sab: wispSab,
      url: (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/wisp' });
    w.postMessage({ t: 'wisp-sab', sab: wispSab });
  } catch (_) { /* no cross-origin isolation → no sockets */ }
  _waliosWorker = w;
  return w;
}
async function tool_walios({ script, timeout }, ctx) {
  if (!script || !String(script).trim())
    return { result: 'Error: "script" is required — pass it as the "script" argument, or via the <|walios|>…<|end_walios|> blob form in your reply.' };
  let t = Number(timeout); if (!isFinite(t) || t <= 0) t = 120; t = Math.min(300, Math.round(t));
  let w;
  try { w = _waliosEnsure(); } catch (e) { return { result: 'Error: cannot start the walios worker: ' + ((e && e.message) || e) }; }
  const pkgM = await _waliosPkgManifest();
  return await new Promise((resolve) => {
    const chunks = []; let outLen = 0, truncated = false, done = false;
    const finish = (result) => { if (done) return; done = true; clearTimeout(timer); resolve({ result }); };
    const kill = (why) => {
      try { w.terminate(); } catch (_) {}
      _waliosWorker = null;
      let partial = chunks.join(''); if (partial.length > 65536) partial = partial.slice(0, 65536) + '\n…[truncated]';
      finish(why + (partial ? '\n--- partial output ---\n' + partial.replace(/\n+$/, '') : ''));
    };
    const timer = setTimeout(() => kill('Error: walios run exceeded ' + t + 's and was terminated (worker killed; the next call starts a fresh one).'), t * 1000);
    if (ctx && ctx.signal) {
      if (ctx.signal.aborted) return kill('Error: walios run aborted (turn stopped).');
      ctx.signal.addEventListener('abort', () => kill('Error: walios run aborted (turn stopped).'), { once: true });
    }
    w.onmessage = (ev) => {
      if (done) return;
      const m = ev.data;
      if (m.t === 'out') {
        if (m.fd === 2 && /^\[host\]/.test(m.s)) return;   // host diagnostics
        if (!truncated) { chunks.push(m.s); outLen += m.s.length; if (outLen > 65536) truncated = true; }
      } else if (m.t === 'boot') {
        try { w.postMessage({ t: 'stdin-eof' }); } catch (_) {}   // non-interactive: stdin reads get EOF
      } else if (m.t === 'exit') {
        let text = chunks.join('');
        if (truncated) text = text.slice(0, 65536) + '\n…[output truncated at 64KB]';
        text = text.replace(/\n+$/, '');
        text += (text ? '\n' : '') + '[walios exit ' + m.code + (m.ms != null ? ' · ' + Math.round(m.ms) + 'ms' : '') + ']';
        finish(text || '[no output]');
      }
    };
    w.onerror = (e) => kill('Error: walios worker crashed: ' + ((e && e.message) || e));
    w.postMessage({ t: 'run', wasm: WALIOS_BB, manifest: { ...pkgM, ...WALIOS_MANIFEST },
      tars: [['rootfs.tar.gz', '/']], opfs: '/root',
      env: { HOME: '/root', TERM: 'dumb', PATH: '/bin:/usr/bin', PS1: '', HOSTNAME: 'walios', LC_ALL: 'C.UTF-8' },
      cwd: '/root', argv: ['busybox', 'sh', '-c', String(script)], jspi: true, pty: false, cols: 120, rows: 40 });
  });
}

async function unknownTool(name) {
  const n = String(name || '').trim().toLowerCase();
  if (/^[a-z0-9][a-z0-9_-]*$/.test(n)) {
    try { await opfsReadBytes('sandpie/skills/' + n + '/SKILL.md'); return { result: 'Error: "' + name + '" is a skill, not a tool. Call load_skill({"name":"' + n + '"}) to use it.' }; } catch {}
  }
  return { result: 'Error: unknown tool "' + name + '". Available tools: ' + KNOWN_TOOLS.join(', ') + '.' };
}

// ── Repetition loop-breaker (added 2026-08-25) ─────────────────────────────
// Degenerate failure mode: a SIGTERM-killed poll left the model emitting the
// SAME no-op write_todos every round; the stop-guard forced continuation and
// ~50 identical calls burned ~176K tokens of context. Guard: remember the last
// call's name+args key AND its exact result text. THREE consecutive identical
// call+result pairs = zero progress → escalate ONCE by blocking the active
// todo (a legal stop-guard release) and returning a finish-now directive.
// Poll-style repeats (same command, growing log output) never match on result
// TEXT, so they are never punished. Pure read-only tools never trip it.
const _REP_LIMIT = 3;
const _REP_NEVER = new Set(['read_file', 'list_files', 'search', 'search_dropbox', 'recall', 'load_image']);
function _repGuardState(ctx) { return ctx._repGuard || (ctx._repGuard = { key: '', res: '', n: 0, fired: false }); }
function _todoBlockForLoop(ctx) {
  try {
    const tree = Array.isArray(ctx._todoTree) ? ctx._todoTree : [];
    if (!tree.length) return '';
    const t = tree.find(x => x.status === 'in_progress') || tree.find(x => x.status === 'pending');
    if (!t || t.status === 'blocked' || t.status === 'completed' || t.status === 'deleted') return '';
    t.status = 'blocked'; delete t.completed;
    t.reason = 'loop guard: identical no-op tool call repeated with no effect';
    ctx._todos = _todoFlat(tree);
    return t.id;
  } catch (_) { return ''; }
}
async function runTool(name, args, ctx) {
  const convFileName = ctx._conversation_file_name || 'unknown';
  switch (name) {
    case 'run_python':    return tool_run_python({...args, _conv: convFileName}, ctx);
    case 'shell':         return tool_shell(args, ctx);
    case 'walios':        return (_waliosQueue = _waliosQueue.then(() => tool_walios(args, ctx), () => tool_walios(args, ctx)));
    case 'show_artifact': return tool_show_artifact(args, ctx);
    case 'share':         return tool_share(args, ctx);
    case 'html_console':  return tool_html_console(args, ctx);
    case 'screenshot':    return tool_screenshot(args, ctx);
    case 'ask':           return tool_ask(args, ctx);
    case 'load_image':    return tool_load_image(args, ctx);
    case 'load_skill':    return tool_load_skill(args, ctx);
    case 'read_file':     return tool_read_file({...args, _conv: convFileName}, ctx);
    case 'list_files':    return tool_list_files(args, ctx);
    case 'search':        return tool_search(args, ctx);
    case 'search_dropbox':return tool_search(args, ctx);   // legacy alias → unified search
    case 'web_search':    return tool_web_search(args, ctx);
    case 'read_url':      return tool_read_url(args, ctx);
    case 'copy_to_workspace': return tool_copy_to_workspace(args, ctx);
    case 'copy':          return tool_copy_to_workspace(args, ctx);   // BETA name for copy_to_workspace
    case 'pyodide':       return tool_run_python(args, ctx);          // BETA name for run_python
    case 'write_file':    return tool_write_file({...args, _conv: convFileName}, ctx);
    case 'edit_file':     return tool_edit_file(args, ctx);
    case 'delete_file':   return tool_delete_file(args, ctx);
    case 'write_todos':   return (ctx && ctx._todoMode === 'claude') ? tool_write_todos_claude(args, ctx) : tool_write_todos(args, ctx);
    case 'scratch':       return tool_scratch(args, ctx);
    case 'spawn_subagent': return tool_spawn_subagent(args, ctx);
    case 'remember':      return tool_remember(args, ctx);
    case 'recall':        return tool_recall(args, ctx);
    // Safety net: respond is normally intercepted in runAgent's tool loop (it is
    // terminal + renders the reply bubble via a sentinel). This case only fires if
    // it is reached through the single-tool path — return a plain ack.
    case 'respond':       return { result: 'Delivered to the user.' };
    default:              return unknownTool(name);
  }
}

async function runToolGuarded(name, args, ctx) {
  if (!ctx || _REP_NEVER.has(String(name))) return runTool(name, args, ctx);
  const rg = _repGuardState(ctx);
  const key = String(name) + '\u0000' + JSON.stringify(args == null ? {} : args);
  const out = await runTool(name, args, ctx);
  const res = out && typeof out.result === 'string' ? out.result : JSON.stringify(out == null ? {} : out);
  if (key === rg.key && res === rg.res) {
    rg.n++;
    if (!rg.fired && rg.n >= _REP_LIMIT - 1) {
      rg.fired = true;
      const bid = _todoBlockForLoop(ctx);
      return { result: 'LOOP GUARD: this exact call has returned the IDENTICAL result ' + _REP_LIMIT
        + ' times in a row — nothing is progressing and another repeat cannot change anything.'
        + (bid ? (' Active task #' + bid + ' is now BLOCKED ("loop guard: identical no-op tool call"), which releases the stop-guard.')
               : '')
        + ' Finish your reply now, or switch to genuinely different work.' };
    }
    if (rg.fired) return { result: 'LOOP GUARD active: this call is a proven no-op. Finish your reply or do different work.' };
  } else {
    rg.key = key; rg.res = res; rg.n = 0;
  }
  return out;
}

// ============================================================
// Auto-retry for transient upstream errors.
// ============================================================
// 413 (Payload Too Large) is deliberately NOT retryable: resending the same
// oversized body can't shrink it, so retrying would loop. A provider that caps
// request size answers 413 and the error surfaces immediately (non-retryable).
const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504, 520, 522, 524]);
function isRetryableError(e) {
  if (!e || e.name === 'AbortError') return false;
  if (typeof e.status === 'number' && RETRYABLE_STATUS.has(e.status)) return true;
  if (e instanceof TypeError) return true;
  return false;
}
// An over-context rejection: the request exceeded the model's window. Arrives
// as HTTP 413 (some providers) OR as a mid-stream/body error — usually code 400
// — whose message says so ("maximum context length…", "context_length_exceeded",
// "reduce the length of the messages"). Both mean the same thing and take the
// same cure: compact and retry. Keyed on the MESSAGE, not just status, because
// providers disagree on the code (400/422/413) for this condition.
function isContextOverflowError(e) {
  if (!e) return false;
  if (e.status === 413) return true;
  const m = String((e && e.message) || '');
  return /context[_ ]length|maximum context|reduce the length|too many tokens|prompt is too long/i.test(m);
}
// Convert an in-stream provider error object ({code, message} — OpenRouter's
// mid-stream error event, per-choice error, or a bare JSON error body on a 200)
// into a throwable with `status` set so isRetryableError can classify it. An
// upstream connect timeout / transient failure with no usable numeric code maps
// to 502 so it retries; a genuine 4xx (bad request, key…) surfaces immediately.
function _sseErrorToThrow(errObj) {
  const code = errObj && (errObj.code ?? errObj.status);
  const msg = (errObj && (errObj.message || errObj.msg)) || 'provider reported an error mid-stream';
  const status = (typeof code === 'number' && code >= 400 && code < 600) ? code : 502;
  return Object.assign(new Error('Provider stream error: ' + msg), { status });
}
function swSleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    if (signal) signal.addEventListener('abort', () => { clearTimeout(id); reject(new DOMException('aborted', 'AbortError')); }, { once: true });
  });
}
// One-shot silent re-mint of an expired managed session token (JWT). The token
// lapses while the SSO cookie stays valid, so /auth/token — cookie-authed and
// same-origin — returns a fresh one. A same-origin worker fetch carries the
// (HttpOnly) SSO cookie automatically. Returns null if the SSO session is gone.
async function _refreshAuthToken(url) {
  try {
    const r = await fetch(url, { credentials: 'same-origin' });
    if (!r.ok) return null;
    const d = await r.json().catch(() => null);
    return (d && d.token) || null;
  } catch (_) { return null; }
}

// Shared provider-call retry: exponential backoff on transient/5xx/network
// errors (never gives up — same as a standard completion, so a 504 never drops
// the work) plus a single transparent managed-token re-mint on 401. `attemptFn`
// runs ONE call against `headers` (mutated in place on re-mint so later attempts
// reuse the fresh token) and throws on failure with Error.status set for HTTP.
// EVERY provider call routes through here — main generation, subagents (via the
// round loop), and compaction — so none of them can block a turn on a transient
// failure that the others would have retried. Throws 'aborted' if the signal fires.
async function _withProviderRetry(ctx, headers, label, attemptFn) {
  const BACKOFF_MS = [1000, 2000, 5000, 10000];
  let authRefreshed = false;   // at most one transparent token re-mint
  for (let attempt = 0; ; attempt++) {
    if (ctx.signal?.aborted) throw new Error('aborted');
    try {
      if (attempt > 0) ctx.emit({ type: 'info', message: null });
      return await attemptFn(headers);
    } catch (e) {
      if (ctx.signal?.aborted) throw e;
      // Managed session token expired → re-mint from the still-valid SSO cookie
      // and retry once. A fresh token that still 401s means the SSO session is
      // gone — surface it.
      if (e && e.status === 401 && ctx._authRefreshUrl && !authRefreshed) {
        authRefreshed = true;
        const tok = await _refreshAuthToken(ctx._authRefreshUrl);
        if (tok) {
          headers['Authorization'] = 'Bearer ' + tok;
          self.postMessage({ type: 'managed-token-refreshed', token: tok });
          continue;
        }
        ctx.emit({ type: 'session_expired', message: 'Session expired — redirecting to login…' });
      }
      // Managed provider (routed through the sandpie server): a 404 is a
      // server-side condition — a catalog/routing misconfig or a mid-deploy
      // window — never the user's fault, and the admin fix hot-reloads. Treat
      // it like a 429 and keep retrying. Personal providers keep 404 fatal:
      // there it usually means a typo'd endpoint URL that no retry can fix.
      const managed404 = !!(e && e.status === 404 && ctx._authRefreshUrl);
      if (!isRetryableError(e) && !managed404) throw e;
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
      // Flaky providers throw transient 5xx constantly and the retry usually
      // succeeds within a couple of seconds — a popup for every blip is noise.
      // Stay silent for the first two errors; surface it from the 3rd error on
      // (attempt is 0-based) or when the wait is long enough (≥10s) to explain.
      if (attempt >= 2 || delay >= 10000) {
        ctx.emit({ type: 'info', message: `${label} error (${e.status || 'network'}) — retrying in ${delay / 1000}s… (attempt ${attempt + 1})` });
      }
      await swSleep(delay, ctx.signal);
    }
  }
}

async function streamOneRoundWithRetry(reqUrl, headers, body, ctx) {
  return _withProviderRetry(ctx, headers, 'Provider', (hdrs) => {
    ctx._hermesMode = body && body._hermesMode;
    return streamOneRound(reqUrl, hdrs, body, ctx);
  });
}

function parseLeakedToolCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string' || text.indexOf('<|tool_call') === -1) return { toolCalls, stripped: text };
  const callRe = /<\|tool_call_begin\|>\s*functions\.([A-Za-z0-9_.\-]+):(\d+)\s*<\|tool_call_argument_begin\|>([\s\S]*?)<\|tool_call_end\|>/g;
  let m;
  while ((m = callRe.exec(text)) !== null) {
    const [, name, idx, rawArgs] = m;
    toolCalls.push({ id: 'call_' + (++_toolCallSeq), type: 'function', function: { name, arguments: (rawArgs || '').trim() } });
  }
  const stripped = text.replace(/<\|tool_calls_section_begin\|>[\s\S]*?<\|tool_calls_section_end\|>/g, '').replace(/<\|tool_calls_section_begin\|>[\s\S]*$/g, '').trim();
  return { toolCalls, stripped };
}

// Blob-form tool calls for write_file / edit_file. The payload rides in the
// message body as RAW text between sentinels, so the model never has to escape
// newlines / quotes / backslashes into a JSON string — the #1 tool-call failure
// mode on weaker models. We extract the raw text and build the call's arguments
// by JSON.stringify-ing it OURSELVES, so the escaping is always correct.
//   write_file:  <|write_file:PATH|>\n…content…\n<|end_write_file|>
//   edit_file:   <|edit_file:PATH|>\n<<<<<<< SEARCH\n…old…\n=======\n…new…\n>>>>>>> REPLACE\n<|end_edit_file|>
// One SEARCH/REPLACE per edit block; multiple blocks ⇒ multiple calls, in order.
function parseBlobToolCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string' || (text.indexOf('<|write_file:') === -1 && text.indexOf('<|edit_file:') === -1)) {
    return { toolCalls, stripped: text };
  }
  const blockRe = /<\|(write_file|edit_file):([^\n|]+?)(\|overwrite)?\|>([\s\S]*?)<\|end_\1\|>/g;
  const srRe = /<{5,9} SEARCH\r?\n([\s\S]*?)\r?\n={3,}\r?\n([\s\S]*?)\r?\n>{5,9} REPLACE/;
  const spans = [];   // consumed [start,end) ranges, stripped from content afterward
  let m;
  while ((m = blockRe.exec(text)) !== null) {
    const [full, kind, rawPath, owFlag, body] = m;
    const path = rawPath.trim();
    if (!path) continue;
    let args;
    if (kind === 'write_file') {
      // Drop only the single newline adjacent to each sentinel; keep the rest byte-exact.
      args = { path, content: body.replace(/^\r?\n/, '').replace(/\r?\n$/, '') };
      if (owFlag) args.overwrite = true;   // <|write_file:PATH|overwrite|> variant
    } else {
      const sr = srRe.exec(body);
      if (!sr) continue;   // malformed edit body → leave as text so the model can retry
      args = { path, old_str: sr[1], new_str: sr[2] };
    }
    toolCalls.push({ id: 'call_blob_' + (++_toolCallSeq), type: 'function', function: { name: kind, arguments: JSON.stringify(args) } });
    spans.push([m.index, m.index + full.length]);
  }
  let stripped = text;
  for (let i = spans.length - 1; i >= 0; i--) stripped = stripped.slice(0, spans[i][0]) + stripped.slice(spans[i][1]);
  return { toolCalls, stripped: stripped.trim() };
}

// Blob-form walios calls: <|walios|>\n…script…\n<|end_walios|> (or <|walios:90|>
// for a per-call timeout in seconds). The script rides as RAW text — the model
// never JSON-escapes it. Multiple blocks ⇒ multiple calls, in order.
function parseWaliosBlobCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string' || text.indexOf('<|walios') === -1) return { toolCalls, stripped: text };
  const blockRe = /<\|walios(?::(\d+))?\|>([\s\S]*?)<\|end_walios\|>/g;
  const spans = [];
  let m;
  while ((m = blockRe.exec(text)) !== null) {
    const [full, tmo, body] = m;
    const args = { script: body.replace(/^\r?\n/, '').replace(/\r?\n$/, '') };
    if (tmo) args.timeout = Number(tmo);
    toolCalls.push({ id: 'call_walios_' + (++_toolCallSeq), type: 'function', function: { name: 'walios', arguments: JSON.stringify(args) } });
    spans.push([m.index, m.index + full.length]);
  }
  let stripped = text;
  for (let i = spans.length - 1; i >= 0; i--) stripped = stripped.slice(0, spans[i][0]) + stripped.slice(spans[i][1]);
  return { toolCalls, stripped: stripped.trim() };
}

function scrubFramingTokens(s) { return typeof s === 'string' ? s.replace(/<\|[\s\S]*?\|>/g, '').replace(/<｜[\s\S]*?｜>/g, '') : s; }

function firstBalancedObject(s) {
  const start = s.indexOf('{'); if (start < 0) return null;
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < s.length; i++) {
    const c = s[i];
    if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') inStr = false; }
    else if (c === '"') inStr = true;
    else if (c === '{') depth++;
    else if (c === '}' && --depth === 0) return s.slice(start, i + 1);
  }
  return null;
}


function parseHermesToolCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string') return { toolCalls, stripped: text };
  const callRe = /<tool_call>\s*(\{[\s\S]*?\})\s*<\/tool_call>/g;
  let m;
  // idx replaced by module-scope _toolCallSeq
  while ((m = callRe.exec(text)) !== null) {
    try {
      const parsed = JSON.parse(m[1]);
      if (parsed && parsed.name) {
        toolCalls.push({
          id: 'call_hermes_' + (++_toolCallSeq),
          type: 'function',
          function: {
            name: String(parsed.name),
            arguments: JSON.stringify(parsed.arguments || {})
          }
        });
      }
    } catch (_) {}
  }
  if (toolCalls.length === 0) {
    const altRe = /<tool_call>([\s\S]*?)<\/tool_call>/g;
    while ((m = altRe.exec(text)) !== null) {
      try {
        const parsed = JSON.parse(m[1].trim());
        if (parsed && parsed.name) {
          toolCalls.push({
            id: 'call_hermes_' + (++_toolCallSeq),
            type: 'function',
            function: {
              name: String(parsed.name),
              arguments: JSON.stringify(parsed.arguments || {})
            }
          });
        }
      } catch (_) {}
    }
  }
  const stripped = text.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '').replace(/<tool_call>/g, '').replace(/<\/tool_call>/g, '').trim();
  return { toolCalls, stripped };
}

// Recovery parser for Anthropic-style function-call XML that some served models
// (e.g. GLM / DeepSeek variants) emit as TEXT instead of structured tool_calls,
// often wrapped in their own special tokens rendered with FULLWIDTH pipes, e.g.
//   <｜DSML｜tool_calls><｜DSML｜invoke name="walios"><｜DSML｜parameter name="timeout">30</｜DSML｜parameter></｜DSML｜invoke></｜DSML｜tool_calls>
// Also matches the plain <function_calls><invoke>…</invoke> shape. Framing-agnostic:
// keys on `invoke name="…"` / `parameter name="…"`, tolerating any wrapper token
// (ASCII or fullwidth) around the tag names. An invoke with no parameters yields
// {} so the call still fires (the empty-invoke leak seen live). Same class as
// parseLeakedToolCalls / parseHermesToolCalls; only runs when no real tool_calls.
function parseInvokeToolCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string' || !/\binvoke\s+name\s*=\s*"/i.test(text)) return { toolCalls, stripped: text };
  const invokeRe = /<[^>]*?\binvoke\s+name\s*=\s*"([^"]+)"[^>]*>([\s\S]*?)<\s*\/[^>]*?\binvoke\b[^>]*>/gi;
  const paramRe  = /<[^>]*?\bparameter\s+name\s*=\s*"([^"]+)"[^>]*>([\s\S]*?)<\s*\/[^>]*?\bparameter\b[^>]*>/gi;
  const spans = [];
  let m;
  while ((m = invokeRe.exec(text)) !== null) {
    const name = m[1], body = m[2] || '', args = {};
    let p; paramRe.lastIndex = 0;
    while ((p = paramRe.exec(body)) !== null) args[p[1]] = p[2].replace(/^\r?\n/, '').replace(/\r?\n$/, '');
    toolCalls.push({ id: 'call_invoke_' + (++_toolCallSeq), type: 'function', function: { name: String(name), arguments: JSON.stringify(args) } });
    spans.push([m.index, m.index + m[0].length]);
  }
  let stripped = text;
  for (let i = spans.length - 1; i >= 0; i--) stripped = stripped.slice(0, spans[i][0]) + stripped.slice(spans[i][1]);
  // Drop any leftover tool_calls / function_calls wrapper framing.
  if (spans.length) stripped = stripped.replace(/<\s*\/?\s*[^>]*?(?:tool_calls|function_calls)\b[^>]*>/gi, '').trim();
  return { toolCalls, stripped };
}

function normalizeToolArgs(raw) {
  const s0 = raw == null ? '' : String(raw);
  // Already-valid JSON short-circuits regardless of content: a legit string value
  // may itself contain "<|" (e.g. blob-written file content), which must NOT be scrubbed.
  try { JSON.parse(s0); return s0; } catch (_) {}
  const s = scrubFramingTokens(s0).trim(); if (!s) return '{}';
  const tryParse = (t) => { try { return JSON.stringify(JSON.parse(t)); } catch (_) { return null; } };
  const escStray = (t) => t.replace(/\\(?!["\\/bfnrtu])/g, '\\\\');
  let out = tryParse(s) || tryParse(escStray(s));
  if (out) return out;
  const obj = firstBalancedObject(s);
  if (obj) { out = tryParse(obj) || tryParse(escStray(obj)); if (out) return out; }
  return '{}';
}

// ── DegenerationDetector (streaming repetition-degeneration detector) ──────
// Cheap O(1)/token signals evaluated incrementally as deltas stream in, valid
// for ANY provider (every stream funnels through streamOneRound):
//   1. sliding-window DISTINCT-TRIGRAM ratio over word trigrams — healthy
//      prose/code stays >= ~0.5; a loop ("de de de de…") collapses toward 0.
//   2. consecutive IDENTICAL-LINE counter (>= 5 identical non-trivial lines).
//   3. LONG-TOKEN repeat counter (same >=20-char token 5x in a row — base64 /
//      hex / URL garbage loops).
// Validated offline against real /admin transcripts: the one real degeneration
// case (uv1hzwjo turn 15373, "de de de…" loop) trips 17% into the stream;
// 1,197 healthy texts from 14 sessions produced 0 false positives; repeated
// code blocks, numbered lists, tables, hashes and base64 blobs do NOT trip.
// Bounded window (400 trigram keys) => constant memory, ~µs per word.
class DegenerationDetector {
  constructor(opts = {}) {
    this.win = opts.window ?? 400;        // trigrams kept in the sliding window
    this.checkEvery = opts.checkEvery ?? 25; // evaluate ratio every N new trigrams
    this.ratioTrip = opts.ratioTrip ?? 0.20; // distinct-trigram ratio below this = bad
    this.lineTrip = opts.lineTrip ?? 5;      // consecutive identical non-trivial lines to trip
    this.tokTrip = opts.tokTrip ?? 5;        // same long token repeated N times in a row
    this.tokMinLen = opts.tokMinLen ?? 20;   // ...and the token must be at least this long
    this.maxPending = opts.maxPending ?? 64; // flush a pending partial word at this length
    this.minWords = opts.minWords ?? 120;    // arm the ratio check after this many words
    this.sustain = opts.sustain ?? 2;        // consecutive bad ratio-checks required to trip
    this.reset();
  }

  reset() {
    this.words = 0;            // total words seen
    this._wbuf = [];           // last 2 words (to form trigrams)
    this._tris = [];           // sliding window of trigram keys
    this._counts = new Map();  // trigram key -> count in window
    this._sinceCheck = 0;
    this._badChecks = 0;
    this._lastRatio = 1;
    this._minRatio = 1;
    this._curLine = null;      // normalized current line
    this._lineRun = 0;
    this._maxLineRun = 0;
    this._lastTok = null;      // last long token (for token-repeat counter)
    this._tokRun = 0;
    this._pending = '';        // partial word held across deltas
    this.tripped = false;
    this.reason = null;
  }

  _normLine(s) {
    return s.replace(/\s+/g, ' ').trim().toLowerCase();
  }

  push(delta) {
    if (this.tripped || !delta) return;
    // Split keeping line structure: process line fragments so the line-repeat
    // counter works incrementally across deltas.
    const parts = String(delta).split('\n');
    for (let i = 0; i < parts.length; i++) {
      if (i > 0) this._endLine();
      this._pushFragment(parts[i]);
    }
  }

  _endLine() {
    const l = this._normLine(this._curLine ?? '');
    if (l.length >= 3) {
      if (l === this._curNorm) {
        this._lineRun++;
      } else {
        this._curNorm = l;
        this._lineRun = 1;
      }
      if (this._lineRun > this._maxLineRun) this._maxLineRun = this._lineRun;
      if (this._lineRun >= this.lineTrip && !this.tripped) {
        this.tripped = true;
        this.reason = `line repeated ${this._lineRun}x: "${l.slice(0, 60)}"`;
      }
    } else {
      this._curNorm = null;
      this._lineRun = 0;
    }
    this._curLine = null;
  }

  _pushFragment(frag) {
    if (!frag) return;
    if (this._curLine === null) this._curLine = '';
    this._curLine += frag;
    // Tokenize with a pending-partial-word buffer so tokenization is
    // IDENTICAL no matter where stream deltas split words (live SSE deltas
    // arrive mid-token). A pending token is flushed early once it exceeds
    // maxPending chars — that is how no-whitespace loops (minified JSON,
    // base64) still get counted instead of buffering forever.
    let buf = this._pending + frag;
    const endsWS = /\s$/.test(buf);
    const toks = buf.split(/\s+/).filter(Boolean);
    this._pending = '';
    if (!endsWS && toks.length) {
      const last = toks.pop();
      if (last.length >= this.maxPending) {
        // Giant token (minified JSON / base64 / no-space loop): split into
        // single CHARACTERS so repetition inside it is visible to the trigram
        // window regardless of where the loop period falls.
        for (const ch of last) toks.push(ch);
      } else {
        this._pending = last; // hold back the incomplete word
      }
    }
    for (const t of toks) {
      this._tok(t);
      if (this.tripped) return;
    }
  }

  _tok(t) {
    const w = t.toLowerCase();
    // Long-token repeat counter: the same long token many times in a row
    // (base64/hex/URL garbage loops). Short words are exempt — natural
    // prose repeats them constantly.
    if (w.length >= this.tokMinLen) {
      if (w === this._lastTok) {
        this._tokRun++;
        if (this._tokRun >= this.tokTrip && !this.tripped) {
          this.tripped = true;
          this.reason = `token repeated ${this._tokRun}x: "${w.slice(0, 40)}…"`;
          return;
        }
      } else {
        this._lastTok = w;
        this._tokRun = 1;
      }
    } else {
      this._lastTok = null;
      this._tokRun = 0;
    }
    this.words++;
    this._wbuf.push(w);
    if (this._wbuf.length === 3) {
      const key = this._wbuf.join(' ');
      this._tris.push(key);
      this._counts.set(key, (this._counts.get(key) || 0) + 1);
      if (this._tris.length > this.win) {
        const old = this._tris.shift();
        const c = this._counts.get(old) - 1;
        if (c <= 0) this._counts.delete(old); else this._counts.set(old, c);
      }
      this._wbuf.shift(); // keep last 2 words so the next trigram slides
      this._sinceCheck++;
      if (this._sinceCheck >= this.checkEvery) {
        this._sinceCheck = 0;
        this._evalRatio();
      }
    }
  }

  _evalRatio() {
    const n = this._tris.length;
    if (!n || this.words < this.minWords) return;
    const ratio = this._counts.size / n;
    this._lastRatio = ratio;
    if (ratio < this._minRatio) this._minRatio = ratio;
    if (ratio < this.ratioTrip) {
      this._badChecks++;
      if (this._badChecks >= this.sustain && !this.tripped) {
        this.tripped = true;
        this.reason = `distinct-trigram ratio ${ratio.toFixed(3)} < ${this.ratioTrip} for ${this._badChecks} checks (window ${n})`;
      }
    } else {
      this._badChecks = 0;
    }
  }

  // Flush any pending partial line/word (call before final check()).
  flush() {
    if (this._pending) { const p = this._pending; this._pending = ''; this._tok(p); }
    if (this._curLine !== null) this._endLine();
  }

  // Snapshot: { tripped, reason, ratio, minRatio, maxLineRepeat, words }
  check() {
    this.flush();
    return {
      tripped: this.tripped,
      reason: this.reason,
      ratio: this._lastRatio,
      minRatio: this._minRatio,
      maxLineRepeat: this._maxLineRun,
      words: this.words,
    };
  }
}

async function streamOneRound(reqUrl, headers, body, ctx) {
  // OpenRouter prompt-cache grouping: pin a stable per-conversation session id
  // (set once in runAgent) so the re-sent prefix across tool rounds caches.
  // Applied here — the single funnel for every generation request, including the
  // 413-compaction retry — rather than only on the first-round body.
  if (ctx && ctx._sessionId) body.session_id = ctx._sessionId;
  // Conversation title for the server-side transcript capture (/admin).
  if (ctx && ctx._conversationTitle) body.conversation_title = ctx._conversationTitle;
  const payload = JSON.stringify(body);
  // We deliberately do NOT pre-block oversized bodies here: some providers cap the
  // request body (~1 MB) and reply 413, others don't. So let the provider decide and
  // surface its own 413 (handled just below; 413 is non-retryable). We still measure
  // real UTF-8 bytes to include an accurate size in the 413 diagnostic hint.
  let bytes; try { bytes = new Blob([payload]).size; } catch (_) { bytes = payload.length; }
  const res = await fetch(reqUrl, { method: 'POST', headers, body: payload, signal: ctx.signal });
  if (!res.ok) {
    const text = (await res.text()).slice(0, 300);
    if (res.status === 413) {
      // Body too large for this provider. Trigger compaction and ask the caller to retry.
      throw Object.assign(new Error('Payload Too Large'), { status: 413, payloadBytes: bytes });
    }
    throw Object.assign(new Error(res.status + ': ' + text), { status: res.status });
  }
  // If a previous attempt of THIS round already streamed deltas to the UI before
  // failing mid-stream, tell the renderer to reset so the retry doesn't append a
  // duplicate copy of the partial text. _attemptStreamed is cleared at round_start.
  if (ctx && ctx._attemptStreamed) { ctx.emit({ type: 'round_retry' }); ctx._attemptStreamed = false; }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  // TTFT split: mark when the FIRST generated token (content/reasoning/tool-call)
  // arrives; everything after it is decode. The wait before it (already inside the
  // caller's completion_ms window) is prefill. A leading role-only delta doesn't
  // count — only actual generated output starts the decode clock.
  const _pnow = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
  let _firstTokAt = 0;
  let buffer = '', content = '', reasoningText = '';
  // Degeneration detector: fresh per attempt, O(1)/token, bounded window.
  const _degen = new DegenerationDetector();
  const toolCalls = []; let usage = null, sawDone = false;
  let finishReason = null, streamErr = null;
  // Stall watchdog: a dead upstream connection can leave reader.read() pending
  // forever with no error event and no [DONE]. If no chunk arrives for STALL_MS,
  // throw a retryable 408 so _withProviderRetry re-issues the request.
  const STALL_MS = 180000;
  const readWithStall = () => {
    let timer;
    return Promise.race([
      reader.read(),
      new Promise((_, rej) => { timer = setTimeout(() => rej(Object.assign(new Error('Provider stream stalled (no data for ' + (STALL_MS / 1000) + 's)'), { status: 408 })), STALL_MS); }),
    ]).finally(() => clearTimeout(timer));
  };
  while (!sawDone && !streamErr) {
    const { done, value } = await readWithStall(); if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n'); buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6); if (data === '[DONE]') { sawDone = true; break; }
      try {
        const parsed = JSON.parse(data);
        // OpenRouter delivers mid-stream failures (upstream connect timeout, provider
        // 5xx…) as an SSE event carrying an `error` object — the HTTP status was
        // already 200 by then, so res.ok can't catch it. Without this check the error
        // is swallowed and the round returns looking like a normal short completion.
        // Throw (below, outside this swallow-all catch) so _withProviderRetry
        // backs off and retries like any other transient provider failure.
        const errObj = (parsed && parsed.error) || (parsed && parsed.choices && parsed.choices[0] && parsed.choices[0].error);
        if (errObj) { streamErr = _sseErrorToThrow(errObj); break; }
        if (parsed && parsed.usage) usage = parsed.usage;
        if (parsed && parsed.choices && parsed.choices[0] && parsed.choices[0].finish_reason) finishReason = parsed.choices[0].finish_reason;
        if (finishReason === 'error') { streamErr = _sseErrorToThrow(null); break; }
        const delta = parsed && parsed.choices && parsed.choices[0] && parsed.choices[0].delta;
        if (!delta) continue;
        if (!_firstTokAt && (delta.content || typeof delta.reasoning_content === 'string' || typeof delta.reasoning === 'string' || (delta.tool_calls && delta.tool_calls.length))) {
          _firstTokAt = _pnow();
        }
        if (delta.content) { content += delta.content; _degen.push(delta.content); }
        if (typeof delta.reasoning_content === 'string') { reasoningText += delta.reasoning_content; _degen.push(delta.reasoning_content); }
        else if (typeof delta.reasoning === 'string') { reasoningText += delta.reasoning; _degen.push(delta.reasoning); }
        if (_degen.tripped) {
          // Degeneration: the provider is looping ("de de de…", repeated lines,
          // garbage-token runs). Abort the attempt as a RETRYABLE error so
          // _withProviderRetry re-issues it (round_retry resets the partial
          // render), and tell the page so it reports the trip to the server
          // for provider attribution in /admin.
          ctx.emit({ type: 'degeneration', session_id: ctx._sessionId || null, model: body.model || null, reason: _degen.reason, words: _degen.words, ratio: _degen._minRatio });
          ctx.emit({ type: 'info', message: 'Output degeneration detected — retrying…' });
          throw Object.assign(new Error('Provider output degeneration: ' + _degen.reason), { status: 502, degeneration: true });
        }
        if (delta.tool_calls) {
          for (const tc of delta.tool_calls) {
            const i = tc.index || 0;
            if (!toolCalls[i]) toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
            if (tc.id) {
              // Defensive dedupe: if the same provider id appears twice (some
              // models reuse call ids across rounds), append a unique suffix so
              // _toolBoxEl on the page finds the correct box.
              if (typeof _seenTcIds === 'undefined') var _seenTcIds = new Set();
              if (_seenTcIds.has(tc.id)) toolCalls[i].id = tc.id + '_' + (++_toolCallSeq);
              else { toolCalls[i].id = tc.id; _seenTcIds.add(tc.id); }
            }
            if (tc.function?.name) toolCalls[i].function.name += tc.function.name;
            if (tc.function?.arguments) toolCalls[i].function.arguments += tc.function.arguments;
          }
        }
        ctx.emit({ type: 'delta', delta });
        if (ctx) ctx._attemptStreamed = true;
      } catch (_) {}
    }
  }
  try { reader.cancel(); } catch (_) {}
  // Accumulate this attempt's decode span (first token → stream end) onto the
  // turn's _prof. prefill is derived as completion_ms - decode_ms at emit, so an
  // attempt that never produced a token contributes nothing here and its whole
  // wait correctly lands in prefill.
  if (_firstTokAt && ctx && ctx._prof) {
    ctx._prof.decodeMs += (_pnow() - _firstTokAt);
    if (usage) ctx._prof.completionTokens += (usage.completion_tokens | 0);   // for the page's rate popup
  }
  if (streamErr) throw streamErr;
  // A 200 response whose body was a bare JSON error (not SSE-framed) never matches
  // the `data: ` prefix, so the loop drains it into `buffer` and we'd return an
  // empty round. Detect and surface it as a retryable provider error instead.
  if (!sawDone && !content && !toolCalls.length && !finishReason && buffer.trim()) {
    try {
      const tail = JSON.parse(buffer.trim());
      if (tail && tail.error) throw _sseErrorToThrow(tail.error);
    } catch (e) { if (e && e.status) throw e; }
  }
  // Some upstreams (seen: GMICloud via OpenRouter) report failures as a NORMAL
  // completion: the error text ("Connect timeout, please try again later.")
  // arrives as delta.content with finish_reason "stop" and no error object —
  // indistinguishable from a real answer except that usage is all zeros
  // (prompt_tokens 0 is impossible for a genuine round: the prompt was sent).
  // Treat zero-usage rounds as a transient provider failure and retry.
  if (usage && (usage.prompt_tokens | 0) === 0 && (usage.completion_tokens | 0) === 0) {
    throw _sseErrorToThrow({ code: 502, message: 'zero-usage round (upstream failure disguised as a completion): ' + String(content || '').slice(0, 200) });
  }
  let keptToolCalls = toolCalls.filter(tc => tc && tc.id && tc.function && tc.function.name);
  if (!keptToolCalls.length) {
    const blob = parseBlobToolCalls(content);
    if (blob.toolCalls.length) { keptToolCalls = blob.toolCalls; content = blob.stripped; }
  }
  if (!keptToolCalls.length) {
    const wal = parseWaliosBlobCalls(content);
    if (wal.toolCalls.length) { keptToolCalls = wal.toolCalls; content = wal.stripped; }
  }
  if (!keptToolCalls.length) {
    let parsed = parseLeakedToolCalls(content);
    if (parsed.toolCalls.length) { keptToolCalls = parsed.toolCalls; content = parsed.stripped; }
    else if (!content.trim()) { parsed = parseLeakedToolCalls(reasoningText); if (parsed.toolCalls.length) keptToolCalls = parsed.toolCalls; }
  }
  if (!keptToolCalls.length) {
    // Anthropic-style <invoke name="…"> XML leaked as text (DSML / fullwidth-pipe
    // framing) — model-agnostic, so not gated on _hermesMode.
    let inv = parseInvokeToolCalls(content);
    if (inv.toolCalls.length) { keptToolCalls = inv.toolCalls; content = inv.stripped; }
    else if (!content.trim()) { inv = parseInvokeToolCalls(reasoningText); if (inv.toolCalls.length) keptToolCalls = inv.toolCalls; }
  }
  if (!keptToolCalls.length && ctx._hermesMode) {
    const hermesParsed = parseHermesToolCalls(content);
    if (hermesParsed.toolCalls.length) { keptToolCalls = hermesParsed.toolCalls; content = hermesParsed.stripped; }
  }
  // Truncation detection: when the provider cut the response at its output-token
  // cap (finish_reason "length"), a tool call streamed mid-arguments arrives as
  // unparseable JSON. normalizeToolArgs salvages it (usually to '{}'), which makes
  // the failure invisible to the model — it sees "missing parameter" errors, blames
  // its own call, and retries the identical oversized write forever (seen live:
  // GLM via NPAW, 4000-token default cap, write_file loop). Record which calls
  // were salvaged under a length-cut so the tool loop can report the REAL cause.
  const truncatedIds = [];
  for (const tc of keptToolCalls) {
    if (!tc || !tc.function) continue;
    if (typeof tc.function.name === 'string') tc.function.name = scrubFramingTokens(tc.function.name).trim().replace(/^functions\./, '');
    const rawArgs = tc.function.arguments;
    tc.function.arguments = normalizeToolArgs(rawArgs);
    if (finishReason === 'length') {
      let rawParses = false;
      try { JSON.parse(rawArgs == null ? '' : String(rawArgs)); rawParses = true; } catch (_) {}
      if (!rawParses) truncatedIds.push(tc.id);
    }
  }
  // Per-round decode span (first generated token -> end of stream) for the live
  // tok/s readout: exact completion_tokens over decode-only time, emitted by the
  // agent loop right after this round's usage event.
  return { content, tool_calls: keptToolCalls, usage, reasoning_content: reasoningText, finish_reason: finishReason, decode_ms: _firstTokAt ? (_pnow() - _firstTokAt) : 0, truncated_tool_ids: truncatedIds };
}

// ============================================================
// Mid-turn compaction (worker-side)
// ------------------------------------------------------------
// The agentic loop can append many bulky tool results within a SINGLE turn,
// blowing past the context window long before the next user send. Page-side
// maybeAutoCompact only runs pre-send, so it can't save an in-flight turn.
// Here the worker re-estimates context at every round and, once over the
// threshold, summarizes its OWN active message slice in place: it drops the
// aged span and prepends a fresh summary (folding in any prior summary). Since
// the worker's `messages` array is already the active slice shipped by
// buildAgentConfig, previously pushed-out turns are never reintroduced.
const SP_SUMMARY_MARKER = '[Earlier conversation auto-summarized to preserve context]';

function _cmpTextOf(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(p => (p && p.type === 'text') ? (p.text || '') : '').join(' ');
  return '';
}

// Mirror of conversations.js safeSplitIndex: the kept tail must START on an
// assistant message so the leading user-role summary preserves alternation and
// never orphans a role:'tool' result from its assistant tool_calls.
function _safeSplitIndex(msgs, keepTail) {
  let split = Math.max(0, msgs.length - (keepTail || 10));
  while (split < msgs.length && (!msgs[split] || msgs[split].role !== 'assistant')) split++;
  return split;
}

// Request-funnel guard: strict providers (DeepSeek) reject histories where a
// role:'tool' message is not an immediate response to a preceding assistant
// tool_calls entry — "Messages with role 'tool' must be a response to a
// preceding message with 'tool_calls'" (400). Compaction splices, steered
// messages, or old persisted conversations can break the pairing, and lenient
// hosts mask it. Walk the outgoing history and repair BOTH directions:
//  - orphaned tool result (no open matching call) → re-shaped as a user message
//    carrying the same text, deferred until no tool_calls block is open so it
//    can't split an assistant/tool group;
//  - assistant tool_calls left unanswered before the next non-tool message →
//    synthetic '[tool result missing]' fillers so the group is complete.
function fixToolPairing(msgs) {
  const out = [];
  let open = null;          // Set of tool_call_ids awaiting their results
  let held = [];            // orphans converted to user msgs, flushed once the group closes
  const closeOpen = () => {
    if (open) for (const id of open) out.push({ role: 'tool', tool_call_id: id, content: '[tool result missing]' });
    open = null;
    if (held.length) { out.push(...held); held = []; }
  };
  for (const m of msgs) {
    if (!m) continue;
    if (m.role === 'tool') {
      const id = m.tool_call_id;
      if (open && id && open.has(id)) { out.push(m); open.delete(id); if (!open.size) { open = null; if (held.length) { out.push(...held); held = []; } } }
      else {
        const conv = { role: 'user', content: '[recovered tool result]\n' + _cmpTextOf(m.content) };
        if (open) held.push(conv); else out.push(conv);
      }
      continue;
    }
    closeOpen();
    out.push(m);
    if (m.role === 'assistant' && Array.isArray(m.tool_calls) && m.tool_calls.length) {
      open = new Set(m.tool_calls.map(tc => tc && tc.id).filter(Boolean));
      if (!open.size) open = null;
    }
  }
  closeOpen();
  return out;
}

function _cmpTranscript(messages, fromIdx, toIdx) {
  const out = [];
  for (let i = fromIdx; i < toIdx; i++) {
    const m = messages[i];
    if (!m || (m.role !== 'user' && m.role !== 'assistant')) continue;
    const t = _cmpTextOf(m.content).trim();
    if (t) out.push((m.role === 'user' ? 'USER: ' : 'ASSISTANT: ') + t);
  }
  let s = out.join('\n\n');
  const CAP = 12000;
  if (s.length > CAP) s = '…[earlier turns truncated]\n\n' + s.slice(s.length - CAP);
  return s;
}

// Non-streaming summarization call with retry/backoff (requirement: compaction
// must retry on failure). Returns the summary text, or null if it ultimately
// is aborted (returns null). On genuine failure it retries with backoff and, if
// still failing, THROWS — compaction is never silently skipped (see caller).
async function _summarizeForCompaction(config, transcript, ctx) {
  const cmp = config.compaction;
  const body = {
    model: cmp.model || config.model,
    messages: [{ role: 'system', content: cmp.prompt }, { role: 'user', content: transcript }],
    stream: false,
  };
  // No invented max_tokens: send a cap only when the provider config sets one
  // (a summary never needs more than 2048, so clamp to that when capping at all).
  if (config.maxTokens != null) body.max_tokens = Math.min(2048, config.maxTokens);
  // Same retry contract as a standard completion: backoff on transient/5xx +
  // 401 re-mint, so a 504 mid-compaction is retried (not a turn-halting failure)
  // exactly like the main generation. Abort mid-compaction → null (not a failure;
  // the caller skips the splice). A non-retryable error (e.g. an empty response)
  // propagates so maybeCompactMidTurn surfaces it as a CompactionFailure.
  try {
    return await _withProviderRetry(ctx, config.headers, 'Compaction', async (headers) => {
      const r = await fetch(config.url, { method: 'POST', headers, body: JSON.stringify(body), signal: ctx.signal });
      if (!r.ok) { const e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
      const d = await r.json();
      const txt = d && d.choices && d.choices[0] && d.choices[0].message && d.choices[0].message.content;
      if (txt && txt.trim()) return txt.trim();
      throw new Error('summarizer returned an empty response');
    });
  } catch (e) {
    if (ctx.signal && ctx.signal.aborted) return null;
    throw e;
  }
}

// ── spawn_subagent ──────────────────────────────────────────────────────────
// Delegate a bounded subtask to a FRESH agent loop in an ISOLATED context. The
// subagent is defined by sandpie/agents/<name>.md — frontmatter sets its model,
// allowed tools, and round budget; the body is its system prompt. It sees ONLY
// the caller's brief (never this conversation) and its bounded final message is
// returned to the caller as the tool result. Its rounds stream to the page
// tagged with the caller's tool-call id, so the UI nests them in a collapsible
// under the spawn_subagent box. (This replaces the old adversary_check tool —
// the adversarial reviewer is now just one agent definition among many.)
const SUBAGENT_DEFAULT_MAX_ROUNDS = 12;   // cap when the agent file omits maxRounds
const SUBAGENT_RESULT_CAP = 8000;         // bound the text returned to the parent
let _subagentSeq = 0;

// Minimal YAML-ish frontmatter parser: `key: value`, with inline arrays
// [a, b, c], quoted strings, and true/false/int coercion. Enough for agent
// definition files; not a general YAML parser.
function _parseFrontmatter(text) {
  const m = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(text);
  if (!m) return { meta: {}, body: String(text || '').trim() };
  const meta = {};
  for (const line of m[1].split(/\r?\n/)) {
    const mm = /^([A-Za-z0-9_-]+)[ \t]*:[ \t]*(.*)$/.exec(line);
    if (!mm) continue;
    let val = mm[2].trim();
    if (/^\[.*\]$/.test(val)) {
      val = val.slice(1, -1).split(',').map(s => s.trim().replace(/^["']|["']$/g, '')).filter(Boolean);
    } else {
      val = val.replace(/^["']|["']$/g, '');
      if (val === 'true') val = true; else if (val === 'false') val = false;
      else if (/^\d+$/.test(val)) val = parseInt(val, 10);
    }
    meta[mm[1]] = val;
  }
  return { meta, body: text.slice(m[0].length).trim() };
}

async function _loadAgentDef(name) {
  const n = String(name || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(n)) return { error: 'invalid agent name "' + name + '".' };
  const file = 'sandpie/agents/' + n + '.md';
  let text;
  try { text = new TextDecoder().decode(await opfsReadBytes(file)); }
  catch (e) {
    let avail = [];
    try {
      const items = await opfsCollect('sandpie/agents', { recursive: false });
      avail = (items || []).filter(x => x.kind === 'file' && /\.md$/i.test(x.path))
        .map(x => x.path.replace(/^.*\//, '').replace(/\.md$/i, ''));
    } catch (_) {}
    return { error: 'no agent "' + n + '" (looked for ' + file + ').'
      + (avail.length ? ' Available agents: ' + avail.join(', ') + '.' : ' No agent files found in sandpie/agents/.') };
  }
  const { meta, body } = _parseFrontmatter(text);
  return { meta, body, file };
}

async function tool_spawn_subagent({ agent, prompt }, ctx) {
  const cfg = ctx && ctx._agentConfig;
  if (!cfg || !cfg.url) return { result: 'Error: spawn_subagent is only available during an agent run.' };
  if ((ctx._depth || 0) >= 1) return { result: 'Error: a subagent cannot spawn further subagents — do this work directly.' };
  if (!agent) return { result: 'Error: pass {"agent":"<name>","prompt":"…"} — agent names a file sandpie/agents/<name>.md.' };
  const brief = String(prompt || '').trim();
  if (!brief) return { result: 'Error: pass a self-contained "prompt" — the subagent sees only this brief, not the conversation.' };

  const def = await _loadAgentDef(agent);
  if (def.error) return { result: 'Error: ' + def.error };

  // Filter the parent's tool set to what the agent file allows (never
  // spawn_subagent — no recursion). No `tools:` in the file ⇒ a pure
  // reasoning/summarizing agent with no tools.
  const allowedList = Array.isArray(def.meta.tools) ? def.meta.tools : (def.meta.tools ? [def.meta.tools] : []);
  const allowed = new Set(allowedList.map(String));
  const subTools = (Array.isArray(cfg.tools) ? cfg.tools : []).filter(t => {
    const nm = t && t.function && t.function.name;
    return nm && nm !== 'spawn_subagent' && allowed.has(nm);
  });

  // Subagent language rule mirrors the parent's regime. Author-in-English
  // regime (ctx._localize set) or an English session: the HARD English rule —
  // the parent's translation layer handles delivery. Native regime (a fluent
  // reply language): user-facing deliverable content is authored directly in
  // that language; internal work and the returned result stay English (the
  // result feeds the parent model, not the user).
  const _subNative = !(ctx && ctx._localize && ctx._localize.code)
    && ctx && ctx._replyLang && ctx._replyLang.code && String(ctx._replyLang.code).split(/[-_]/)[0].toLowerCase() !== 'en'
    ? ctx._replyLang : null;
  const langClause = _subNative
    ? '\n\nLANGUAGE RULE: the end user reads deliverables in ' + (_subNative.name || _subNative.code) + ', which you generate fluently. Author the BODY of any document/file written for the user directly in ' + (_subNative.name || _subNative.code) + '. Everything else — reasoning, tool arguments, code, comments, todo items, scratch notes, and your FINAL RESULT to the caller — stays in ENGLISH (your result feeds the calling agent, not the user). The language of the material you read does NOT change the language you write in.'
    : '\n\nHARD OPERATING RULE (applies to every subagent): you operate in ENGLISH at all times. Every tool argument, every file you write, every line of reasoning, every todo item, and your final result is authored in ENGLISH and nothing else. If a task looks like it is written in another language, still author all of your own work in English - the language of the material you read does NOT change the language you write in. You never generate non-English text yourself in any channel; the delivery language is handled by the caller.';
  const sysBody = def.body || ('You are a focused subagent named ' + agent + '. Do the task and report the result.');
  const outNote = (def.meta.output === 'structured')
    ? '\n\nReturn ONLY your final result in the exact structure your instructions specify — no preamble, no commentary.'
    : '\n\nYour FINAL message is returned verbatim to the caller as your result — the caller cannot see your intermediate steps, and you cannot ask follow-up questions. Make it a self-contained summary.';
  const subConfig = {
    ...cfg,
    model: def.meta.model || cfg.model,
    systemPrompt: { role: 'system', content: sysBody + outNote + langClause },
    messages: [{ role: 'user', content: brief }],
    tools: subTools,
    todos: [],
    // Own cache key: the cfg spread above would otherwise copy the parent's
    // session_id, making the subagent share the parent's prompt-cache slot.
    session_id: subId,
    maxRounds: (Number(def.meta.maxRounds) > 0) ? Number(def.meta.maxRounds) : SUBAGENT_DEFAULT_MAX_ROUNDS,
  };

  const tcId = ctx._currentToolCallId || null;
  const subId = (ctx.agentId || 'agent') + ':sub' + (++_subagentSeq);
  const subCtx = {
    emit: (ev) => ctx.emit({ type: 'subagent', tcId, subId, agent, sub: ev }),
    signal: ctx.signal,
    origin: ctx.origin,
    agentId: subId,
    _depth: (ctx._depth || 0) + 1,
    _conversation_file_name: ctx._conversation_file_name,
  };
  ctx.emit({ type: 'subagent', tcId, subId, agent, sub: { type: 'subagent_begin', agent, prompt: brief } });
  try {
    await runAgent(subConfig, subCtx);
  } catch (e) {
    if (ctx.signal && ctx.signal.aborted) return { result: 'Error: aborted.' };
    return { result: 'Error: subagent "' + agent + '" failed: ' + ((e && e.message) || e) };
  } finally {
    _touchSinks.delete(subId);   // subrun done — stop routing writes to its sink
  }
  let out = String(subCtx._finalText || '').trim();
  if (!out) out = '(subagent "' + agent + '" produced no final text)';
  if (out.length > SUBAGENT_RESULT_CAP) out = out.slice(0, SUBAGENT_RESULT_CAP) + '\n…(subagent result truncated at ' + SUBAGENT_RESULT_CAP + ' chars)';
  return { result: 'SUBAGENT (' + agent + ') RESULT:\n' + out };
}

// A compaction that was required but could not be produced. The round loop stops
// the turn on this rather than shipping an over-limit request.
class CompactionFailure extends Error {
  constructor(msg) { super(msg); this.name = 'CompactionFailure'; this.compactionFailed = true; }
}

// Called at a round boundary, given the round's REAL reported prompt_tokens.
// The single, simple condition: reported prompt_tokens ÷ context window ≥ pct →
// pause and compact before the next round. No estimate, no stored state. Mutates
// `messages` in place. When compaction is required it MUST succeed — a failure
// throws CompactionFailure so the turn halts loudly instead of silently continuing.
async function maybeCompactMidTurn(config, messages, ctx, promptTokens) {
  const cmp = config.compaction;
  if (!cmp || !cmp.enabled || !cmp.window) return;
  if (promptTokens !== null && (!promptTokens || promptTokens <= 0)) return;   // no reported number → nothing to gate on (null = forced by 413)
  if (promptTokens !== null) {
    const pct = (promptTokens / cmp.window) * 100;
    if (pct < (cmp.pct || 70)) return;
  }

  // ---- DEBUG provenance log -------------------------------------------------
  // Every mid-turn compaction logs WHY it fired: session id, conversation id,
  // title, measured context vs window, provider endpoint, and (on failure) the
  // summarizer error + HTTP status. Worker console is relayed to the page as
  // '[worker] ...', so these land in the tab's devtools console. Best-effort:
  // logging must never break compaction.
  const _cmpBase = (() => {
    let host = '';
    try { host = new URL(config.url).host; } catch (_) {}
    return {
      src: 'worker-midturn',
      session_id: ctx._sessionId || config.session_id || null,
      conv: config.conversation_file_name || null,
      title: ctx._conversationTitle || config.conversation_title || null,
      provider: (config.model || '?') + (host ? ' @ ' + host : ''),
      window: cmp.window,
    };
  })();
  const _cmpPct = promptTokens != null ? Math.round((promptTokens / cmp.window) * 100) : null;
  const _cmpReason = (promptTokens == null)
    ? 'forced: context-overflow error (413/400) - safety-net compact+retry'
    : 'threshold: reported prompt_tokens ' + promptTokens + ' >= ' + Math.round(cmp.pct || 70) + '% of window';
  const _cmpLog = (ev, extra) => {
    try { console.log('[compaction] ' + ev + ' ' + JSON.stringify({ ..._cmpBase, reason: _cmpReason, prompt_tokens: promptTokens != null ? promptTokens : null, pct: _cmpPct, ...(extra || {}) })); } catch (_) {}
  };
  _cmpLog('trigger');

  const marker = cmp.marker || SP_SUMMARY_MARKER;
  const m0 = messages[0];
  const hasSummary = !!(m0 && m0.role === 'user' && typeof m0.content === 'string' && m0.content.startsWith(marker));
  const prior = hasSummary ? m0.content.slice(marker.length).replace(/^\s*\n+/, '') : '';
  const bodyStart = hasSummary ? 1 : 0;

  const split = _safeSplitIndex(messages, cmp.keepTail || 10);
  // Can't reduce the body / no valid tail: nothing to do (not a failure — the
  // protected tail alone is already over the window; only a bigger window helps).
  if (split <= bodyStart || split >= messages.length) return;

  let transcript = _cmpTranscript(messages, bodyStart, split);
  if (!transcript.trim()) return;
  if (prior) transcript = '[Summary of the conversation so far]\n' + prior + '\n\n[New turns to fold into the summary]\n' + transcript;

  // Same UI as pre-send compaction: the .compaction-progress spinner + "Summarizing
  // earlier messages to free up context…" (page maps compaction_start/end to
  // show/hideCompactionProgress). No separate "Context over X%" info bubble.
  ctx.emit({ type: 'compaction_start' });
  let summary = null;
  try {
    summary = await _summarizeForCompaction(config, transcript, ctx);
  } catch (e) {
    ctx.emit({ type: 'compaction_end' });
    _cmpLog('failed', { error: (e && e.message) || String(e), status: (e && e.status) || null });
    throw new CompactionFailure('Context is over ' + Math.round(cmp.pct) + '% and must be compacted to continue, but summarizing the earlier turns failed: ' + ((e && e.message) || e) + '. Generation stopped.');
  }
  if (summary) {
    // Drop [0, split) — old summary + aged body — and prepend the fresh, folded summary.
    messages.splice(0, split, { role: 'user', content: marker + '\n\n' + summary });
    // The compacted-away slice may have held the only full copy of files the
    // read-dedupe stubs point at — force full re-emission on the next read.
    _emittedFileHashes.clear();
    // Tell the PAGE to advance its persisted compaction boundary. `kept` = the tail
    // messages retained (everything after the summary); since the worker's tail is
    // the newest messages, the page maps this to boundary = convMessages.length -
    // kept. Without this the page keeps the stale pre-turn boundary and the NEXT
    // send re-ships everything this turn accumulated (the "sends way more than the
    // active context" bug). `summary` is the raw folded text (no marker).
    ctx.emit({ type: 'message_compacted', kept: messages.length - 1, summary });
    _cmpLog('done', { removed: split, kept: messages.length - 1 });
  }
  ctx.emit({ type: 'compaction_end' });
}

// ============================================================
// remember — write a durable fact to sandpie/memory/<slug>.md
// ------------------------------------------------------------
// The page injects every memory file into the system prompt (SandpieMemory),
// so writing the file IS the whole operation; no index to maintain here. If a
// file with the same slug exists we preserve its `created` date and update.
function _memSlug(s) { return String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'note'; }

// Project label for a new memory → one of the real repos. Mirrors memory.js so
// injection/graph group by the same key. Strong path signals beat weak; if paths
// give nothing, fall back to content keywords. Keep in sync with memory.js.
function _projPathStrong(p) {
  if (/(^|\/)(crates|riscv-core|riscv-supervisor|riscv-harness|riscv-devices|riscv-test-harness)(\/|$)|(^|\/)riscv-vm(\/|$)|vmlinuz|oneshot_alpine|(^|\/)kernels\/|gen_dtb/i.test(p)) return 'riscv-vm';
  if (/(^|\/)(opt\/)?sandpie-server(\/|$)/.test(p)) return 'sandpie-server';
  let m = /(^|\/)skills\/([^/]+)/.exec(p); if (m) return m[2];
  m = /(^|\/)files\/projects\/([^/]+)/.exec(p); if (m) return /impag/i.test(m[2]) ? 'impagados' : m[2];
  return '';
}
function _projPathWeak(p) {
  if (/(^|\/)modules\//.test(p) || /^[^/]+\.(js|css|wasm)$/.test(p) || /coiserver|(^|\/)sandpie\.(html|css)|(^|\/)sw\.js|(^|\/)opfs\.js|univer\.js|file-viewer\.js/.test(p)) return 'sandpie';
  if (/aging_|dashboard_live|slartran|IONAPI/i.test(p)) return 'impagados';
  return '';
}
function _projKeyword(hay) {
  hay = String(hay || '').toLowerCase();
  if (/\briscv\b|\balpine\b|vmlinuz|\bdtb\b|\bmmu\b|kernel|setup_smp|clint|ebreak|udelay|\bsatp\b|\bsepc\b|oneshot|emulator|boot_alpine|c\.bnez/.test(hay)) return 'riscv-vm';
  if (/tecnec|\bcapex\b|\bopex\b|bombas.?calor/.test(hay)) return 'tecnec_proposals';
  if (/impagados|impagats|ion.?api|slartran|\baging\b|factura/.test(hay)) return 'impagados';
  if (/sandpie-server|\bnpaw\b|nginx|ai-balancer/.test(hay)) return 'sandpie-server';
  if (/sandpie|\bopfs\b|univer|logprob|compaction|second.brain|webgpu|html-editor|service.worker|\bsw\.js\b|artifact|zetaoffice|busytex|dropbox|loop.lab|arxiv|adreno|cross-origin|\bfont\b|distiller|tool_remember|worker/.test(hay)) return 'sandpie';
  return '';
}
function _projFromPaths(paths, hay) {
  const vote = (fn) => { const v = {}; for (const p of paths) { const l = fn(p); if (l) v[l] = (v[l] || 0) + 1; } return Object.entries(v).sort((a, b) => b[1] - a[1])[0]; };
  const s = vote(_projPathStrong); if (s) return s[0];
  const w = vote(_projPathWeak); if (w) return w[0];
  return _projKeyword(hay);
}

async function tool_remember({ name, description, type, body, links, project, supersedes }, ctx) {
  if (!name || !body || !String(body).trim()) return { result: 'Error: both name and body are required.' };
  // Provenance from THIS turn (back to the previous user message):
  //  - tool_calls: the [rN] result IDs (capped — was dumping the whole turn).
  //  - paths: REAL file paths from the tool CALL ARGUMENTS (args.path/src/dest +
  //    shell write-targets), NOT regexed from result text. Text-scraping produced
  //    garbage (code fragments, //, URLs, :line:col, truncations); structured args
  //    are always qualified real paths. edit/write targets outrank mere reads.
  const toolCallIds = [];
  const pathScore = new Map();   // path -> best weight seen (write/edit=2, read/other=1)
  const WRITE_TOOLS = new Set(['edit_file', 'write_file', 'apply_patch', 'create_file', 'str_replace', 'str_replace_editor']);
  const _looksPath = t => typeof t === 'string' && t && (t.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(t)) && !/^\/dev\//.test(t);
  const _addPath = (p, w) => { if (_looksPath(p)) pathScore.set(p, Math.max(pathScore.get(p) || 0, w)); };
  // Unambiguous WRITE targets from a shell command (redirects + tee), heredoc bodies stripped.
  const _shellWrites = (cmd) => {
    if (typeof cmd !== 'string' || !cmd) return;
    let scan = cmd.replace(/<<-?\s*(['"]?)(\w+)\1[\s\S]*?^[ \t]*\2[ \t]*$/gm, ' <<HD ').replace(/<<-?\s*(['"]?)\w+\1[\s\S]*$/g, ' <<HD ');
    for (const m of scan.matchAll(/\d*>>?\s*("[^"]+"|'[^']+'|[^\s|&;<>()]+)/g)) _addPath(m[1].replace(/^['"]|['"]$/g, ''), 2);
    for (const m of scan.matchAll(/\btee\s+(?:-a\s+)?("[^"]+"|'[^']+'|[^\s|&;<>()]+)/g)) _addPath(m[1].replace(/^['"]|['"]$/g, ''), 2);
  };
  if (ctx && ctx._messages) {
    for (let i = ctx._messages.length - 1; i >= 0; i--) {
      const m = ctx._messages[i];
      if (m && m.role === 'user') break; // stop at previous user turn
      if (m && m.role === 'tool' && typeof m.content === 'string') {
        const rid = /^\[r(\d+)\]/.exec(m.content);
        if (rid && !toolCallIds.includes('r' + rid[1])) toolCallIds.push('r' + rid[1]);
      }
      if (m && m.role === 'assistant' && Array.isArray(m.tool_calls)) {
        for (const tc of m.tool_calls) {
          const nm = tc && tc.function && tc.function.name;
          let a = {}; try { a = JSON.parse((tc.function && tc.function.arguments) || '{}'); } catch (_) {}
          const w = WRITE_TOOLS.has(nm) ? 2 : 1;
          _addPath(a.path, w); _addPath(a.src, w); _addPath(a.dest, w);
          if (nm === 'shell') _shellWrites(a.command);
        }
      }
    }
  }
  // Rank write>read (stable → recent-first within a tier since we walked backward); cap at 6.
  const toolPaths = [...pathScore.entries()].sort((x, y) => y[1] - x[1]).slice(0, 6).map(e => e[0]);
  // Evidence gate: project/reference facts must cite a tool result as evidence;
  // user/feedback (stable preferences, how-to-work corrections) don't require it.
  if (type !== 'user' && type !== 'feedback' && toolCallIds.length === 0)
    return { result: 'Error: remember() for project/reference facts requires at least one tool call result as evidence. Use a tool first, then remember the lesson.' };
  const slug = _memSlug(name);
  const t = ['user', 'feedback', 'project', 'reference'].includes(type) ? type : 'reference';
  const today = new Date().toISOString().slice(0, 10);
  const path = 'sandpie/memory/' + slug + '.md';
  let created = today, verb = 'Remembered';
  try { const ex = await opfsReadText(path); const m = /^created:[ \t]*(.+)$/m.exec(ex); if (m) { created = m[1].trim(); verb = 'Updated memory'; } } catch (_) {}
  const desc = String(description || '').replace(/\s*\n\s*/g, ' ').trim();
  const convId = ctx && ctx._conversation_file_name ? ctx._conversation_file_name : 'unknown';
  // project = the model's explicit hint if given, else derived from the top path.
  // First-class grouping key for tiered injection + the graph (memory.js).
  const projLabel = (project && String(project).trim()) || _projFromPaths(toolPaths, name + ' ' + (description || '') + ' ' + body);
  let out = '---\n' + `name: ${slug}\n` + `description: ${desc}\n` + `type: ${t}\n` + `created: ${created}\n` + `last_verified: ${today}\n` + `conversation: ${convId}\n` + `tool_calls: ${toolCallIds.slice(0, 8).join(', ')}\n`;
  if (toolPaths.length) out += `paths: ${toolPaths.join(', ')}\n`;
  if (projLabel) out += `project: ${projLabel}\n`;
  // Explicit supersession: name the memory(ies) this replaces. The page-side
  // consolidation pass archives them to .pruned/ (recoverable) with correct sync.
  if (supersedes) { const sup = (Array.isArray(supersedes) ? supersedes : [supersedes]).map(_memSlug).filter(s => s && s !== slug); if (sup.length) out += `supersedes: ${[...new Set(sup)].join(', ')}\n`; }
  out += '---\n' + String(body).trim() + '\n';
  if (Array.isArray(links) && links.length) out += '\n' + links.map(l => '[[' + _memSlug(l) + ']]').join(' ') + '\n';
  try { await opfsWriteText(path, out); } catch (e) { return { result: 'Error saving memory: ' + ((e && e.message) || e) }; }
  // Notify the page so sync-state marks this file dirty — otherwise the next
  // Dropbox reconciliation deletes it as an orphan (not in cloud, not dirty)
  // BEFORE it's ever pushed. Same mechanism tool_write_file uses.
  self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [path], owner: ctx && ctx.agentId } });
  return { result: verb + ' "' + slug + '" (' + t + ').' };
}

// recall — pull memory facts NOT currently shown in full. Tiered injection shows
// only the active project's memories in full + a 1-line index of the rest; this
// loads any indexed fact by keyword. Deterministic term-overlap scan over the store.
async function tool_recall({ query, limit }, ctx) {
  const terms = [...new Set(String(query || '').toLowerCase().match(/[a-z0-9][a-z0-9_-]{2,}/g) || [])];
  if (!terms.length) return { result: 'recall: provide a query (keywords or a memory name).' };
  let dir; try { dir = await opfsResolveDir(['sandpie', 'memory'], false); } catch (_) { return { result: 'recall: no memory store found.' }; }
  const scored = [];
  try {
    for await (const [nm, h] of dir.entries()) {
      if (h.kind !== 'file' || !nm.endsWith('.md') || nm === 'MEMORY.md' || nm.endsWith('.lessons.md')) continue;
      let text = ''; try { text = await opfsReadText('sandpie/memory/' + nm); } catch (_) { continue; }
      const hay = text.toLowerCase();
      let score = 0; for (const t of terms) if (hay.includes(t)) score++;
      if (nm.toLowerCase().includes(terms[0])) score += 2;   // name match is a strong signal
      if (score) scored.push({ nm, score, text });
    }
  } catch (_) { return { result: 'recall: could not read the memory store.' }; }
  if (!scored.length) return { result: 'recall: no memory matched "' + query + '".' };
  scored.sort((a, b) => b.score - a.score);
  const top = scored.slice(0, Math.max(1, Math.min(limit || 3, 6)));
  const out = top.map(m => '### ' + m.nm.replace(/\.md$/, '') + '\n' + m.text.replace(/^﻿?---[\s\S]*?\r?\n---[ \t]*\r?\n/, '').trim());
  return { result: out.join('\n\n') };
}

// Build the OpenRouter-native `reasoning` parameter from the provider config.
// We always speak OpenRouter's `reasoning` shape ({ effort, max_tokens, exclude })
// instead of the OpenAI-only `reasoning_effort`, so the thinking level is honored
// for every reasoning model OpenRouter fronts (Claude, DeepSeek, Qwen, GLM, …),
// not just OpenAI o-series. `config.reasoning` is the raw OpenRouter value the UI
// captured; `config.reasoningEffort` is the OpenAI-style effort string we map in.
function _openRouterReasoning(config) {
  const r = config && config.reasoning;
  if (r !== undefined && r !== null && r !== '' && r !== 'auto') {
    if (typeof r === 'string' || typeof r === 'number') return { effort: String(r).toLowerCase() };
    return r; // already an object: { effort, max_tokens?, exclude? }
  }
  const eff = config && config.reasoningEffort;
  if (!eff) return null;
  const e = String(eff).toLowerCase();
  const effort = e === 'minimal' ? 'low' : e; // OpenRouter effort vocab is low|medium|high
  return { effort };
}

async function runAgent(config, ctx) {
  const convFileName = config.conversation_file_name || 'unknown';
  ctx._conversation_file_name = convFileName;
  const messages = config.messages.slice();
  // Tools reach the provider endpoint and live transcript through ctx._agentConfig
  // (e.g. spawn_subagent builds the child's config from it).
  ctx._agentConfig = config;
  ctx._messages = messages;
  // BETA projects fork: the conversation's project folder (absolute Dropbox path
  // + namespace). Relative tool paths resolve against it; all writes/deletes are
  // guarded to stay inside it. null on /app and for legacy/Unsorted conversations.
  ctx._projectRoot = config.projectRoot || null;
  ctx._projectNs = config.projectNs || 'home';
  // ---- Worker-side JSONL persistence -------------------------------------
  // The page passes where to append (config.jsonl_path) and how many messages
  // are already on disk (config.persisted_count). Every committed message is
  // appended here at EOF (O(1) SyncAccessHandle) as it is emitted, so the
  // transcript on disk tracks the stream live: no throttled 1.2s page timer to
  // starve while hidden, no giant backlog to serialize when the user stops.
  // Subagents (config.maxRounds set) never persist — their messages aren't part
  // of the parent transcript.
  ctx._persistPath = (!config.maxRounds && config.jsonl_path) ? config.jsonl_path : '';
  ctx._persistCount = Number(config.persisted_count) || 0;
  const persistMessage = async (m) => {
    if (!ctx._persistPath || (ctx.signal && ctx.signal.aborted)) return false;
    try {
      await enqueueAppend(ctx._persistPath, JSON.stringify(m) + '\n');
      ctx._persistCount++;
      // Mark the file dirty for the Dropbox cursor-delta sync (same relay the
      // write_file tool uses) so the turn-end sync pushes the new lines.
      try { self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [ctx._persistPath], owner: ctx && ctx.agentId } }); } catch (_) {}
      return true;
    } catch (e) {
      // Append failed (e.g. exclusive lock) — do NOT advance the counter, and do
      // NOT report a count: the page then falls back to its own incremental save
      // for this message, so nothing is silently lost.
      try { console.warn('[sandpie] worker JSONL append failed:', e && e.message); } catch (_) {}
      return false;
    }
  };
  // message_added carries the running JSONL line count ONLY when the worker
  // actually wrote the line (persist succeeded). Absent count → page fallback.
  const emitAdded = async (m) => {
    const ok = await persistMessage(m);
    ctx.emit({ type: 'message_added', message: m, ...(ok ? { persistedCount: ctx._persistCount } : {}) });
  };
  // Stable per-conversation cache key, generated ONCE and persisted in the
  // conversation meta (see ensureSessionId in conversations.js). Reuse it so
  // OpenRouter prompt-cache grouping survives across turns, refreshes, and
  // devices. The page always supplies config.session_id; the fallback (file
  // name) only protects non-conversation callers and stays unique per file.
  ctx._sessionId = config.session_id || (config.conversation_file_name || 'unknown');
  ctx._conversationTitle = String(config.conversation_title || '').slice(0, 300);
  // Managed provider only: URL to silently re-mint an expired session token on a
  // 401 (see streamOneRoundWithRetry). null/absent for personal providers.
  ctx._authRefreshUrl = config.authRefreshUrl || null;
  // Relay base URL for the `shell` tool (worker has no localStorage).
  ctx._shellRelayUrl = config.shellRelayUrl || 'http://localhost:8765';
  // Localization target ({code,name}) for this turn, or null. When set, a
  // deliverable shown via show_artifact is localized (its text translated) so the
  // user's file is in their language, while the model authored it in English.
  ctx._localize = config.localize || null;
  ctx._replyLang = config.replyLanguage || null;   // session reply language (even when localize is null)
  ctx._fluent = Array.isArray(config.fluent) ? config.fluent.map(c => String(c).split(/[-_]/)[0].toLowerCase()) : null;
  // Seed the task list from the persisted checklist (page passes config.todos).
  // Migrate legacy items: flat items (no id) → sequential ids; the retired
  // 'withdrawn' status → 'deleted'; drop dead tree/evidence/audit fields.
  ctx._todoTree = (Array.isArray(config.todos) ? config.todos : []).map((t, i) => ({
    id: t.id || String(i + 1),
    content: t.content || '',
    status: t.status === 'withdrawn' ? 'deleted' : (_TODO_ALL.includes(t.status) ? t.status : 'pending'),
    created: t.created, completed: t.completed,
    blockedBy: Array.isArray(t.blockedBy) ? t.blockedBy.map(String) : undefined,
    activeForm: t.activeForm,
    reason: t.reason,
  }));
  // Drain any user messages steered in since the last round and splice them into
  // the loop as user turns. Called at the round boundary — after the previous
  // round's tool results are already appended — so a steer can never land between
  // an assistant tool_calls message and its tool results. Each is echoed back as
  // message_added (flagged _steer) so the page renders + persists it in order.
  const drainSteers = async () => {
    const arr = _agentSteers.get(ctx.agentId);
    if (!arr || !arr.length) return false;
    _agentSteers.set(ctx.agentId, []);
    for (const content of arr) {
      const m = { role: 'user', content };
      messages.push(m);
      const steerMsg = { ...m, _steer: true };
      await emitAdded(steerMsg);
    }
    return true;
  };

  // ---- Drift guard + "don't stop with open todos" state ---------------------
  // A model-managed checklist (write_todos) is the loop's clearest signal of
  // whether the task is actually finished. Two mechanisms use it:
  //   • Drift reminder: after too many tool rounds without touching the list,
  //     inject an EPHEMERAL system-reminder (request-only, never persisted) that
  //     re-shows the todos and nudges an update.
  //   • Stop guard: when the model tries to end the turn with items still open,
  //     don't let it — re-prompt and continue. Only a real user stop (abort) or
  //     genuine progress stalling out (MAX_STOP_BLOCKS) ends the turn.
  ctx._todos = _todoFlat(ctx._todoTree);   // flat view of the seeded tree
  ctx._scratchpad = config.scratchpad || '';   // hidden working memory (persisted, re-injected each round)
  // Files this turn touched (path → last-touch ts). Filled by the postMessage
  // interceptor while a tool call is in flight; announced PROGRESSIVELY after
  // each tool call (partial events — the user sees deliverables appear and
  // build live via artifact auto-reload) and consolidated at turn end (full
  // list → authoritative order + deliverable localization).
  ctx._filesTouched = new Map();
  ctx._ftAnnounced = new Map();   // path → last ts already announced mid-turn
  // Register this run's sink under its agentId so owner-stamped writes (direct
  // tools + pool-relayed python writes) route here and NOWHERE else. Unregistered
  // in the agent-message finally (top-level) and tool_spawn_subagent (subruns).
  if (ctx.agentId != null) _touchSinks.set(ctx.agentId, ctx._filesTouched);
  // Citable result ids (F1): every tool result is prefixed "[rN]" so the model
  // can cite it as evidence when closing a claim-todo. Recover the counter and
  // the set of already-issued ids from the persisted transcript, so claims can
  // cite evidence produced in earlier turns of this conversation.
  ctx._resultIds = new Set(); ctx._resultSeq = 0;
  for (const m of messages) {
    if (!m || m.role !== 'tool' || typeof m.content !== 'string') continue;
    const rm = /^\[r(\d+)\]/.exec(m.content);
    if (rm) { ctx._resultIds.add('r' + rm[1]); const n = +rm[1]; if (n > ctx._resultSeq) ctx._resultSeq = n; }
  }
  ctx._roundsSinceTodo = 0;   // CUMULATIVE rounds since the last real write_todos; only reset by touchedTodo
  ctx._lastNagAt = 0;         // value of _roundsSinceTodo at the last nag (cadence gate, does NOT reset the count)
  ctx._stopBlocks = 0;
  ctx._respondRetries = 0;    // bare-prose attempts rejected this turn while forcing respond()
  ctx._responded = false;      // at least one respond() delivered this turn (multi-respond support)
  ctx._langRejectCount = 0;    // respond() calls rejected for missing language this turn
  ctx._respondLangs = new Set(); // language codes already delivered this turn (dedup)
  ctx._respondCount = 0;        // successful respond() deliveries this turn (hard cap)
  ctx._forceRespondNext = false; // one-shot: the NEXT request must compel respond() BY NAME (armed after a bare-prose round)
  ctx._respondIsLatest = false;  // was the MOST RECENT tool action a respond()? true on deliver/synth, false on any other tool → the turn may only end when true (final action is always respond)
  ctx._finalRespondForces = 0;   // times we've forced a closing respond() because the model tried to end on a non-respond action
  ctx._lastTodoDone = ctx._todos.filter(t => t.status === 'completed').length;
  const MAX_STOP_BLOCKS = 3;       // consecutive stop attempts w/o new progress
  // Bare-prose attempts to reject before falling back to DELIVERING the prose.
  // Each retry escalates tool_choice to respond() BY NAME (see _forceRespondNext) —
  // not plain 'required', which the model satisfies with write_todos/scratch/remember
  // and so never actually answers. Two forced attempts: providers vary in how
  // eagerly they honor a named tool_choice. If both are ignored, the exhausted
  // bare-prose round's own content is delivered as the reply (localized to the
  // session Reply language) — never a blank turn.
  const MAX_RESPOND_RETRIES = 2;
  const MAX_RESPOND_DELIVERIES = 5;   // hard cap on respond() deliveries per turn
  const MAX_FINAL_RESPOND_FORCES = 3; // times we re-prompt for a closing respond() before giving up and ending anyway
  // This turn forces respond() when the tool is present: the visible reply comes
  // ONLY from respond(), plain content is hidden, and respond() is the only clean
  // way to end. Subagents (no respond in their toolset) are unaffected.
  const _respondForced = Array.isArray(config.tools) && config.tools.some(t => t && t.function && t.function.name === 'respond');
  // Plan-first gate: when write_todos is in the toolset, no tool may run until a
  // plan exists AND a task is active (in_progress). write_todos (planning) and
  // respond (delivering the reply / ending) are exempt. A completed plan leaves no
  // in_progress task, so the next tool is blocked until a fresh plan starts one.
  // Subagents whose toolset lacks write_todos are unaffected. Surfaces the active
  // item to the user before any work happens.
  // TODO-LAB: 'claude' mode = trust-based TodoWrite clone — no plan-first gate,
  // no open-todos stop guard (see tool_write_todos_claude).
  ctx._todoMode = config.todoMode || '';
  const _planForced = ctx._todoMode !== 'claude' && Array.isArray(config.tools) && config.tools.some(t => t && t.function && t.function.name === 'write_todos');
  const _hasActiveTask = () => Array.isArray(ctx._todos) && ctx._todos.some(t => t && t.status === 'in_progress');
  // "Open" = pending or in_progress. completed AND deleted are both closed.
  const openTodos = () => ctx._todos.filter(t => _TODO_OPEN.has(t.status));
  const hasOpenTodos = () => ctx._todos.length > 0 && openTodos().length > 0;
  const renderTodos = () => ctx._todos.filter(t => t.status !== 'deleted').map(t =>
    (t.status === 'completed' ? '[x]' : t.status === 'in_progress' ? '[~]' : t.status === 'blocked' ? '[!]' : '[ ]') + ' ' + t.content
      + (t.status === 'blocked' && t.reason ? ' — ' + t.reason : '')
  ).join('\n');
  // Ephemeral, request-only reminder for the NEXT round. Never pushed into
  // `messages`, so it is neither persisted nor resent on later rounds; it is
  // echoed to the page as a `reminder` event purely so the user can watch the
  // guard fire while debugging.
  let pendingReminder = null;
  const setReminder = (kind, text, meta) => { pendingReminder = { kind, text, meta: meta || null }; };

  // Round budget: subagents pass config.maxRounds so a delegated loop can't run
  // away in an isolated context; the main loop leaves it unset (unbounded).
  const maxRounds = config.maxRounds || 0;
  let _roundNo = 0;

  // ---- Per-turn profiling ----------------------------------------------------
  // Splits the turn's wall time into: completion (waiting on the model stream),
  // tool compute (each tool timed individually — run_python IS the pyodide cost),
  // and mid-turn compaction (summarizer model calls). Emitted once as a `timing`
  // event just before agent_done; the page forwards it to /api/usage/timing for
  // the admin profiling panel. Subagents (maxRounds set) never emit — their whole
  // runtime is already counted under the PARENT's spawn_subagent tool time, so a
  // separate report would double-count.
  const _profNow = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
  const _prof = {
    completionMs: 0, completionCalls: 0, compactionMs: 0,
    // decodeMs = time from the first generated token to end-of-stream, summed over
    // every attempt that reached a first token (see streamOneRound). prefill is
    // derived at emit as completionMs - decodeMs (the wait before the 1st token:
    // queue + connect + prompt prefill, plus any pre-token retry/backoff wait).
    decodeMs: 0, completionTokens: 0,
    toolMs: 0, toolCalls: 0, tools: Object.create(null),
    wallStart: _profNow(),
    // Suspension accounting (see heartbeat below). suspendMs = total wall time the
    // turn was frozen; suspendHiddenMs = the slice of that while the tab was hidden.
    suspendMs: 0, suspendHiddenMs: 0, suspendEvents: 0, suspendMaxMs: 0,
    _hbTimer: 0,
  };
  ctx._prof = _prof;
  // ---- Suspension heartbeat --------------------------------------------------
  // performance.now()-based timers can't reliably see a suspended tab (the clock
  // may pause or the whole context freezes), so suspension hides inside wall_ms.
  // A plain wall-clock (Date.now) tick measures it directly: when the tab is
  // throttled or frozen the interval can't fire on schedule, so the next callback
  // observes a gap far larger than HB_MS — that overshoot IS the suspended time.
  // Main loop only (subagents fold into the parent's tool time). Cleared before
  // the timing emit below.
  const HB_MS = 2000, HB_FLOOR = 1000;   // ignore <1s of ordinary timer jitter
  if (!maxRounds) {
    let _hbLast = Date.now();
    _prof._hbTimer = setInterval(() => {
      const now = Date.now();
      const drift = now - _hbLast - HB_MS;
      _hbLast = now;
      if (drift > HB_FLOOR) {
        _prof.suspendMs += drift;
        _prof.suspendEvents++;
        if (drift > _prof.suspendMaxMs) _prof.suspendMaxMs = drift;
        if (_pageHidden) _prof.suspendHiddenMs += drift;
      }
    }, HB_MS);
  }
  const _profTool = (name, ms, isErr) => {
    const t = _prof.tools[name] || (_prof.tools[name] = { ms: 0, calls: 0, errors: 0 });
    t.ms += ms; t.calls++; if (isErr) t.errors++;
    _prof.toolMs += ms; _prof.toolCalls++;
  };
  // Emit the per-turn profiling report exactly once, on ANY terminal path. The
  // message handler's finally calls this too, so a turn that THROWS (e.g. a
  // suspended tab whose model stream died and exhausted retries) still reports
  // its suspend_ms — otherwise the very suspensions we care about are discarded
  // with the failed turn and never reach the panel. Idempotent + subagent-safe.
  let _timingEmitted = false;
  const _emitTiming = () => {
    if (_timingEmitted) return;
    _timingEmitted = true;
    if (_prof._hbTimer) { try { clearInterval(_prof._hbTimer); } catch (_) {} _prof._hbTimer = 0; }
    if (maxRounds) return;   // subagents fold into the parent's spawn_subagent time
    ctx.emit({ type: 'timing', timing: {
      session_id: ctx._sessionId || null,
      completion_ms: Math.round(_prof.completionMs),
      completion_calls: _prof.completionCalls,
      // Split of completion_ms: decode = streaming tokens; prefill = the wait
      // before the first token (queue/connect/prompt-prefill). prefill+decode
      // ~= completion_ms (clamped ≥0; old clients report 0/0 → panel falls back).
      decode_ms: Math.round(_prof.decodeMs),
      completion_tokens: Math.round(_prof.completionTokens),
      prefill_ms: Math.max(0, Math.round(_prof.completionMs - _prof.decodeMs)),
      compaction_ms: Math.round(_prof.compactionMs),
      tool_ms: Math.round(_prof.toolMs),
      tool_calls: _prof.toolCalls,
      wall_ms: Math.round(_profNow() - _prof.wallStart),
      // Suspension: total frozen ms, the hidden-tab slice, event count, worst gap.
      suspend_ms: Math.round(_prof.suspendMs),
      suspend_hidden_ms: Math.round(_prof.suspendHiddenMs),
      suspend_events: _prof.suspendEvents,
      suspend_max_ms: Math.round(_prof.suspendMaxMs),
      rounds: _roundNo,
      tools: Object.fromEntries(Object.entries(_prof.tools).map(
        ([k, v]) => [k, { ms: Math.round(v.ms), calls: v.calls, errors: v.errors }])),
    } });
  };
  ctx._reportTiming = _emitTiming;

  while (true) {
    if (ctx.signal && ctx.signal.aborted) break;
    if (maxRounds && _roundNo >= maxRounds) {
      ctx.emit({ type: 'reminder', kind: 'round-cap', text: 'Reached the ' + maxRounds + '-round budget; stopping and returning what is done.' });
      break;
    }
    _roundNo++;
    if (await drainSteers()) ctx._stopBlocks = 0;   // fresh user input → reset the stop guard
    // Reminder assembly (only if nothing more urgent is already queued this round).
    // Two variants keyed off whether a plan exists yet:
    //   • open todos  → drift nudge (re-read/update the list).
    //   • no todos at all → "no-plan" nudge (consider laying out a plan first).
    // Reset the counter whenever the threshold is reached so we re-nag on the same
    // cadence rather than every round (roundsSinceTodo never resets on its own when
    // the model simply never calls write_todos).
    // Fire when the plan has been stale for REMIND_AFTER_ROUNDS since the LAST
    // nag — cadence gate only. We do NOT reset _roundsSinceTodo here (that is the
    // cumulative staleness, reset solely by a real write_todos), so the count
    // shown keeps climbing and the tone escalates until the model actually acts.
    // Drift guard removed — plan + scratchpad are injected every round (volatileMsg),
    // so the model always sees its working state. No nagging needed.
    // METACOG (c'): newest-artifact console note — the page queued it after the
    // newest artifact rendered and logged console output. Higher priority than the
    // grind/reuse nudges below; one-shot (consumed here).
    if (!maxRounds && !pendingReminder) {
      const cn = _consoleNotes.get(convFileName);
      if (cn) {
        _consoleNotes.delete(convFileName);
        const n = cn.entries.length;
        const errs = cn.entries.filter(e => /^ERROR|^UNHANDLED/.test(e)).length;
        setReminder('artifact-console',
          '<system-reminder>The newest artifact in this conversation — ' + (cn.path || '?') + ' — emitted ' + n
          + ' console message' + (n === 1 ? '' : 's') + (errs ? (', ' + errs + ' error/unhandled-rejection line' + (errs === 1 ? '' : 's')) : '') + ' after rendering.'
          + ' If the user\'s task involves this artifact, consider using html_console to read its console output — it may reveal a layout/JS defect worth fixing before you declare the task done.'
          + '</system-reminder>', cn);
      }
    }
    // METACOG (c): grind / reuse-a-tool / remember nudges, if nothing more urgent queued.
    if (!maxRounds && !pendingReminder) {
      try { const mc = _metacogReminder(_statsFor(convFileName), config.metacog); if (mc) setReminder(mc.kind, mc.text, mc.meta); }
      catch (_) {}
    }
    if (ctx.signal && ctx.signal.aborted) break;
    ctx.emit({ type: 'round_start' });
    ctx._attemptStreamed = false;   // fresh round: no partial text to reset on retry
    // Consume the ephemeral reminder for exactly this round: append it to the
    // request body only (never to `messages`), and echo it to the page so the
    // guard is observable without polluting the stored conversation.
    let reminderMsg = null;
    if (pendingReminder) {
      reminderMsg = { role: 'user', content: pendingReminder.text };
      ctx.emit({ type: 'reminder', kind: pendingReminder.kind, text: pendingReminder.text, meta: pendingReminder.meta });
      pendingReminder = null;
    }
    // Ephemeral volatile-context tail: the minute-level clock + whatever the page
    // passed in config.volatileContext (Recent paths). Lives at the END of the
    // request — the system prompt stays byte-stable so the provider's prompt
    // cache holds across turns; this tail only ever invalidates itself. Rebuilt
    // fresh each round, never persisted to the conversation.
    let volatileMsg = null;
    try {
      const _now = new Date();
      const _tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      let _vt = 'Current local date and time: ' + _now.toLocaleString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) + (_tz ? ' (' + _tz + ')' : '') + '. Treat this as "now".';
      if (config.volatileContext) _vt += '\n\n' + config.volatileContext;
      // Per-round ephemeral injection of the plan + scratchpad (replaces drift guard).
      // Both are rebuilt from ctx state each round — survive compaction, never in messages.
      // v2 mode shows ids so the model can flip a status with the cheap delta
      // form ({"todos":[{"id":"N","status":"completed"}]}); claude mode (the
      // default TodoWrite clone) has no id concept, so the list stays id-less.
      const _planTree = Array.isArray(ctx._todoTree) ? ctx._todoTree : [];
      const _planLines = _planTree.filter(t => t.status !== 'deleted').map(t =>
        (t.status === 'completed' ? '[x]' : t.status === 'in_progress' ? '[~]' : t.status === 'blocked' ? '[!]' : '[ ]')
          + (ctx._todoMode === 'claude' ? '' : ' ' + t.id) + ' ' + t.content
      ).join('\n');
      if (_planLines) _vt += '\n\n[plan]\n' + _planLines;
      if (ctx._scratchpad) _vt += '\n\n[scratch]\n' + ctx._scratchpad;
      volatileMsg = { role: 'user', content: '<system-reminder>' + _vt + '</system-reminder>' };
    } catch (_) {}
    // Hard plan-first gate: until a task is in_progress, OFFER only write_todos and
    // respond. Work tools aren't on the menu, so the model literally cannot call one
    // before planning (greetings can still respond). Once a task is active, the full
    // toolset returns. The server-side block below is a fallback for a provider that
    // ignores the restricted list.
    // While gated, the surviving write_todos def carries the names of the hidden
    // tools — without this the model looks at a two-tool list and truthfully
    // reports "I can't run python" instead of planning to unlock it.
    const _availTools = (_planForced && !_hasActiveTask())
      ? (config.tools || []).filter(t => t && t.function && (t.function.name === 'write_todos' || t.function.name === 'scratch' || t.function.name === 'respond' || t.function.name === 'remember'))
          .map(t => {
            if (t.function.name !== 'write_todos') return t;
            const hidden = (config.tools || [])
              .map(x => x && x.function && x.function.name)
              .filter(n => n && n !== 'write_todos' && n !== 'scratch' && n !== 'respond' && n !== 'remember');
            if (!hidden.length) return t;
            return { ...t, function: { ...t.function, description: (t.function.description || '') +
              '\nCURRENTLY HIDDEN by the plan-first gate (they exist and unlock the moment a task is in_progress): ' + hidden.join(', ') + '.' } };
          })
      : config.tools;
    // the model reads it immediately before generating (recency beats a rule
    // Force-respond escalation: a bare-prose round (the model tried to answer
    // WITHOUT respond()) armed _forceRespondNext, so THIS request compels respond()
    // BY NAME. Plain 'required' is too weak — it's satisfiable by write_todos /
    // scratch / remember, so the model dodges the one visible channel and the user
    // never sees a reply. One-shot: consumed for this round's request(s).
    // Applies both BEFORE the first respond (bare-prose dodge) and AFTER it (a
    // closing respond forced because the model tried to end on a non-respond action).
    const _forceRespondNow = _respondForced && ctx._forceRespondNext;
    ctx._forceRespondNext = false;
    const _respondToolChoice = _forceRespondNow
      ? { type: 'function', function: { name: 'respond' } }
      : (_respondForced && !ctx._responded ? 'required' : undefined);
    const reqBody = {
      model: config.model,
      messages: fixToolPairing([config.systemPrompt, ...messages, volatileMsg, reminderMsg].filter(Boolean)),
      stream: true,
      stream_options: { include_usage: true },
      tools: _availTools,
    };
    // Force a tool call every round when respond() is in play (until the first
    // respond): the visible chat is exactly the tool actions + the respond() reply.
    // Working tools satisfy 'required' mid-task. _respondToolChoice escalates to
    // respond()-by-name when a respond is being forced (bare-prose dodge, or the
    // closing respond). After the first respond it is undefined (model may keep
    // working) unless a closing respond is being forced.
    if (_respondToolChoice) reqBody.tool_choice = _respondToolChoice;
    const reasoning = _openRouterReasoning(config);
    if (config.maxTokens != null) reqBody[reasoning ? 'max_completion_tokens' : 'max_tokens'] = config.maxTokens;
    if (config.temperature != null) reqBody.temperature = config.temperature;
    if (config.topP != null) reqBody.top_p = config.topP;
    if (reasoning) reqBody.reasoning = reasoning;
    // OpenRouter upstream routing ({ order: [...], allow_fallbacks }): prefer these
    // providers in order, e.g. ['deepseek'] to hit DeepSeek's own endpoint first.
    if (config.providerRouting) reqBody.provider = config.providerRouting;
    let round;
    const _cWaitStart = _profNow();
    try {
      round = await streamOneRoundWithRetry(config.url, config.headers, reqBody, ctx);
      _prof.completionMs += _profNow() - _cWaitStart; _prof.completionCalls++;
    } catch (e) {
      _prof.completionMs += _profNow() - _cWaitStart;   // the failed wait still cost wall time
      if (isContextOverflowError(e)) {
        // Request exceeded the model's context window (HTTP 413, or a 400/422
        // "maximum context length…" the provider streamed back). Same cure:
        // compact the aged span and retry once. This is the safety net for a
        // turn that ballooned past the window between the last measured size
        // and this send — the pre-send/mid-turn gates read a LAGGING reported
        // token count and can miss it, so this is the backstop that must catch it.
        ctx.emit({ type: 'info', message: 'Context window exceeded — compacting and retrying…' });
        try {
          const _cmpStart = _profNow();
          await maybeCompactMidTurn(config, messages, ctx, null); // null promptTokens forces compaction
          _prof.compactionMs += _profNow() - _cmpStart;
          // Rebuild reqBody with compacted messages and retry
          const compactedReqBody = {
            model: config.model,
            messages: fixToolPairing([config.systemPrompt, ...messages, volatileMsg, reminderMsg].filter(Boolean)),
            stream: true,
            stream_options: { include_usage: true },
            tools: _availTools,
          };
          if (_respondToolChoice) compactedReqBody.tool_choice = _respondToolChoice;
          if (config.maxTokens != null) compactedReqBody[config.reasoningEffort ? 'max_completion_tokens' : 'max_tokens'] = config.maxTokens;
          if (config.temperature != null) compactedReqBody.temperature = config.temperature;
          if (config.topP != null) compactedReqBody.top_p = config.topP;
          if (config.reasoningEffort) compactedReqBody.reasoning_effort = config.reasoningEffort;
          if (config.providerRouting) compactedReqBody.provider = config.providerRouting;
          const _cWaitStart2 = _profNow();
          round = await streamOneRoundWithRetry(config.url, config.headers, compactedReqBody, ctx);
          _prof.completionMs += _profNow() - _cWaitStart2; _prof.completionCalls++;
        } catch (compactErr) {
          if (compactErr && compactErr.compactionFailed) {
            ctx.emit({ type: 'error', message: compactErr.message || 'Compaction failed.' });
            break;
          }
          throw e; // re-throw the original overflow error if compaction didn't help
        }
      } else {
        throw e;
      }
    }
    // respond() is the user-facing-reply whitelist: whatever it carries in "text"
    // IS the visible reply, and it ends the turn. Pre-scan the round so the reply
    // bubble shows ONLY that text — any prose the model leaked into round.content
    // (scratch narration, other-language reasoning) is dropped from what the user
    // sees and from persisted history. Actual delivery + terminal break happen in
    // the tool loop / after it, below.
    const respondCall = round.tool_calls.find(tc => tc && tc.function && tc.function.name === 'respond');
    let respondText = null;
    let _forceRespondRetry = false;
    // Content the model writes outside respond() is never the visible reply — but
    // it is NOT nuked: fold it into the reasoning channel so it shows in the
    // collapsed thinking box and persists there (asstMsg.reasoning), like CoT.
    // (A model that duplicates its answer into content will echo it there too;
    // harmless — the box is collapsed.)
    const _stashAside = (t) => {
      if (t && t.trim()) round.reasoning_content = (round.reasoning_content ? round.reasoning_content + '\n\n' : '') + t;
    };
    let respondLocaleOverride = null;
    let _rejectRespondLang = false;
    let _rejectReason = '';
    if (respondCall) {
      try { const _a = JSON.parse(respondCall.function.arguments || '{}'); respondText = String(_a.text ?? ''); respondLocaleOverride = _locFromOverride(_a.language); if (!respondLocaleOverride) { _rejectRespondLang = true; _rejectReason = 'missing'; } }
      catch (_) { respondText = ''; _rejectRespondLang = true; _rejectReason = 'missing'; }
      _stashAside(round.content);                        // keep any non-respond prose as thinking
      if (_rejectRespondLang) {
        round.content = '';                              // rejected — don't deliver
      } else if (ctx._respondCount >= MAX_RESPOND_DELIVERIES) {
        _rejectRespondLang = true; _rejectReason = 'cap';
        round.content = '';
      } else if (ctx._respondLangs && ctx._respondLangs.has(respondLocaleOverride.code)) {
        _rejectRespondLang = true; _rejectReason = 'duplicate';
        round.content = '';
      } else {
        round.content = respondText;                     // the visible reply IS respond's text
        ctx._responded = true;                           // at least one respond delivered this turn
        ctx._respondIsLatest = true;                     // most recent action is a respond → turn may end here
        ctx._respondCount++;
        ctx._respondLangs.add(respondLocaleOverride.code);
      }
    } else if (_respondForced && round.tool_calls.length) {
      _stashAside(round.content);                        // working-tool round: keep leaked prose as thinking
      round.content = '';
    } else if (_respondForced && !round.tool_calls.length && !ctx.signal?.aborted
               && !ctx._responded && ctx._respondRetries < MAX_RESPOND_RETRIES) {
      round.content = '';                                // bare prose attempt — hide it; we'll force respond() below
      _forceRespondRetry = true;
      ctx._forceRespondNext = true;                      // next request compels respond() BY NAME (not plain 'required')
    } else if (_respondForced && !round.tool_calls.length && !ctx.signal?.aborted
               && !ctx._responded && (round.content || '').trim()) {
      // Retries exhausted and the model STILL answered as bare prose (never called
      // respond()). Never end the turn blank: deliver that prose AS the reply,
      // localized to the session Reply language via the SAME path respond() uses —
      // round_end below carries round.content + this locale, and the page localizes
      // it (endRound CASE A → _currentLocale). Mark the turn answered so tool_choice
      // frees up and the reply isn't re-forced. round.content is left intact.
      respondLocaleOverride = ctx._localize || null;     // session Reply-language authority (null = English)
      ctx._responded = true;
      ctx._respondIsLatest = true;                        // synth reply counts as the closing respond
      ctx._respondCount++;
      if (respondLocaleOverride && respondLocaleOverride.code) ctx._respondLangs.add(respondLocaleOverride.code);
    } else if (_respondForced && !round.tool_calls.length && ctx._responded) {
      _stashAside(round.content);                        // already responded — bare prose after respond is not shown
      round.content = '';
    }
    ctx.emit({ type: 'round_end', content: round.content, tool_calls: round.tool_calls, locale: respondLocaleOverride || undefined });
    if (round.content) ctx._finalText = round.content;   // last non-empty assistant text = the subagent's returned result
    if (round.usage) ctx.emit({ type: 'usage', usage: round.usage });
    // Per-round live rate: exact completion_tokens over this round's decode span
    // (first token -> stream end). The page paints it into the live msg-timer so
    // tok/s updates at every ROUND boundary, not only when the whole turn ends.
    if (round.usage && (round.usage.completion_tokens | 0) > 0 && round.decode_ms > 0) {
      ctx.emit({ type: 'rate', completion_tokens: round.usage.completion_tokens, decode_ms: Math.round(round.decode_ms) });
    }
    if (!round.tool_calls.length) {
      // The model tried to answer in plain text without respond(). It was hidden
      // (round.content blanked above); reject it and force a respond() call so the
      // reply reaches the user through the one visible channel. Capped — on the cap
      // we fall through and show the plain content so the turn can never hang blank.
      if (_forceRespondRetry) {
        ctx._respondRetries++;
        setReminder('force-respond',
          '<system-reminder>Your last message was plain text with no respond() call, so it was NOT shown to the user. '
          + 'The ONLY thing the user sees is the "text" you pass to the respond() tool. '
          + ((ctx._localize && ctx._localize.code)
             ? 'Call respond() now with your complete answer authored in ENGLISH (set the "language" argument to the user\'s reply language; the system translates it for the user). Do not answer any other way. '
             : 'Call respond() now with your complete answer, following the system language directive (set the "language" argument to the user\'s reply language). Do not answer any other way. ')
          + '(attempt ' + ctx._respondRetries + '/' + MAX_RESPOND_RETRIES + ')</system-reminder>',
          { attempt: ctx._respondRetries });
        continue;
      }
      if (round.content) {
        const m = { role: 'assistant', content: round.content, finish_reason: round.finish_reason };
        messages.push(m);
        await emitAdded(m);
      }
      // The model is done, but if the user steered a message in during this round
      // (or while it was finishing) keep the loop alive so that message gets
      // answered instead of stranded until a fresh turn. Otherwise the turn ends.
      if (!ctx.signal?.aborted && ((_agentSteers.get(ctx.agentId) || []).length)) { await drainSteers(); continue; }
      // A reply was delivered AND it was the model's MOST RECENT action → the turn
      // ends here, on the answer. This is the only clean way a respond()-forced turn
      // ends, so the last thing the user sees is ALWAYS a respond(). (If the model
      // responded earlier but then did more work, _respondIsLatest is false and we
      // fall through to force a closing respond below.)
      if (ctx._respondIsLatest) break;
      // Don't let the model end the turn with todos still open — a finished task
      // is often just left unmarked, or the provider dropped the closing round.
      // Re-prompt and continue, unless the user stopped it (abort) or we've hit
      // MAX_STOP_BLOCKS re-prompts with no new item completed (a genuine stall).
      // Exception: once a reply was delivered (respond() or the synth fallback) the
      // turn is answered — never re-prompt for open todos, that would resume work
      // AFTER the user already got their conclusion (exactly the churn we prevent).
      if (!ctx.signal?.aborted && !ctx._responded && hasOpenTodos() && ctx._todoMode !== 'claude') {
        if (ctx._stopBlocks < MAX_STOP_BLOCKS) {
          ctx._stopBlocks++;
          setReminder('stop-block',
            '<system-reminder>You tried to end the turn, but these todo items are still open:\n'
            + renderTodos() + '\n\nUnless the user stopped you, keep going and finish the remaining work. '
            + 'When an item is genuinely done, mark it completed with write_todos. Only stop once every item '
            + 'is completed. If an item is genuinely blocked — it needs user input, an external credential or '
            + 'file, or something you cannot obtain this turn — mark it blocked with write_todos '
            + 'a full {"todos":[…]} list with the task status set to "blocked" and a "reason" field. '
            + 'And if the work is genuinely complete, deliver your answer with respond() — that is the ONLY '
            + 'thing the user sees. Do not keep churning write_todos/scratch in place of answering. '
            + '(auto-continue ' + ctx._stopBlocks + '/' + MAX_STOP_BLOCKS + ')</system-reminder>',
            { open: openTodos().length, attempt: ctx._stopBlocks });
          continue;
        }
        // Stalled: hit the cap with no new completions. Stop anyway, but surface
        // why so it's clear the turn ended with work still open.
        ctx.emit({ type: 'reminder', kind: 'stop-anyway',
          text: 'Ended with ' + openTodos().length + ' open todo(s) after ' + MAX_STOP_BLOCKS
            + ' auto-continues without progress.' });
      }
      // INVARIANT: a turn must CONTAIN a delivered respond() — not necessarily as its
      // literal last action. If the model already delivered a reply this turn
      // (ctx._responded), the user has their answer, so a plain-prose stop ends the
      // turn cleanly here — we do NOT force another respond(). Forcing one in that
      // state is unsatisfiable: the only reply left to give is the same language it
      // already delivered, which the duplicate guard rejects → livelock. We only
      // force a closing respond() when NO reply has been delivered at all (the model
      // tried to end without ever answering). Capped so a refusing model can't loop.
      if (_respondForced && !ctx.signal?.aborted && !ctx._responded && ctx._finalRespondForces < MAX_FINAL_RESPOND_FORCES) {
        ctx._finalRespondForces++;
        ctx._forceRespondNext = true;   // next request compels respond() BY NAME
        setReminder('final-respond',
          '<system-reminder>You are ending the turn but have not delivered a reply at all. '
          + 'Every turn must end with a respond(): call respond() NOW with your final conclusion, reflecting everything you just did '
          + '(authored in ENGLISH; set the "language" argument). It must be the LAST thing you do this turn — do not run any other tool after it. '
          + '(final-respond ' + ctx._finalRespondForces + '/' + MAX_FINAL_RESPOND_FORCES + ')</system-reminder>',
          { attempt: ctx._finalRespondForces });
        continue;
      }
      break;
    }
    const asstMsg = { role: 'assistant', content: round.content, tool_calls: round.tool_calls, finish_reason: round.finish_reason };
    // Preserve the model's reasoning on the tool-call turn and resend it. Across
    // multi-step tool calls the next round re-sends this assistant message, and the
    // provider needs its prior reasoning in context — dropping it makes the provider
    // error. We use OpenRouter's unified `reasoning` field (not OpenAI's
    // `reasoning_content`) so thinking survives for every reasoning model OpenRouter
    // fronts, not just OpenAI o-series. Attached only when non-empty, so models
    // that don't emit reasoning never see the field.
    if (round.reasoning_content) asstMsg.reasoning = round.reasoning_content;
    messages.push(asstMsg);
    await emitAdded(asstMsg);
    const loadedImages = [];
    let touchedTodo = false;
    // Same-round grace, PRESENTATION TOOLS ONLY: if a task was active when this
    // round's calls were emitted and an earlier write_todos in the batch
    // completed the final task, the batch's remaining show_artifact/remember
    // calls still run — the natural "mark done + show the result" pair.
    // Work tools (python, shell, files, …) get NO grace: completing the plan
    // still blocks them instantly, so a model can't smuggle plan-less work
    // into the tail of a round.
    const _roundGrace = _hasActiveTask();
    const _GRACE_TOOLS = new Set(['show_artifact', 'remember', 'scratch']);
    let _endTurnAfterRound = false;   // set when a duplicate-language respond() signals the turn is done
    for (const tc of round.tool_calls) {
      if (ctx.signal && ctx.signal.aborted) break;
      if (!tc.function?.name) continue;
      // Truncated-at-cap calls: the arguments never fully arrived — the provider cut
      // the response at its output-token cap mid-JSON. Running the tool would produce
      // a misleading "missing parameter" error the model blames on itself and retries
      // verbatim, looping until interrupted. Name the real cause and demand a smaller
      // output instead.
      if (round.truncated_tool_ids && round.truncated_tool_ids.includes(tc.id)) {
        const _capTok = round.usage && round.usage.completion_tokens ? round.usage.completion_tokens : null;
        const trunc = 'CALL TRUNCATED: the arguments of this ' + tc.function.name + ' call were CUT OFF mid-stream — '
          + 'the response hit the provider\'s output-token cap (finish_reason=length'
          + (_capTok ? ', ' + _capTok + ' completion tokens' : '') + ') before the JSON finished. '
          + 'What you wrote never arrived; the arguments shown in history ("{}" or partial) are a salvage artifact, not your mistake. '
          + 'Do NOT retry the same call — it will be truncated at the same point again. '
          + 'Produce LESS output per call: write a much shorter first version of the file, then grow it with follow-up edit_file calls '
          + '(e.g. leave a <!-- MORE --> marker and replace it with the next chunk), or simplify the content itself.';
        ctx.emit({ type: 'tool_started', tc });
        ctx.emit({ type: 'tool_result', id: tc.id, result: trunc });
        const tmsg = { role: 'tool', tool_call_id: tc.id, content: trunc };
        messages.push(tmsg);
        await emitAdded(tmsg);
        continue;
      }
      let parsedArgs = {}; try { parsedArgs = JSON.parse(tc.function.arguments || '{}'); } catch (_) {}
      // Plan-first gate fallback: normally the restricted tool list above means a
      // work tool can't even be called before planning, but a provider that ignores
      // that list could still emit one. Reject it here. Emit tool_started+tool_result
      // so the box RESOLVES to the blocked message — never leave it spinning (the box
      // may already exist from streamed arg deltas).
      if (_planForced && tc.function.name !== 'write_todos' && tc.function.name !== 'scratch' && tc.function.name !== 'respond' && tc.function.name !== 'remember' && !_hasActiveTask()
          && !(_roundGrace && _GRACE_TOOLS.has(tc.function.name))) {
        const blk = 'Blocked: no active task. You must plan before acting. Call write_todos to create the checklist and mark the task you are about to work on as in_progress (status:"in_progress" in the initial list, or set status:"in_progress" in the list). If your previous plan is fully complete, make a NEW plan for the current request. Only write_todos, scratch, respond, and remember may be used without an active task. Then retry this call.';
        ctx.emit({ type: 'tool_started', tc });
        ctx.emit({ type: 'tool_result', id: tc.id, result: blk });
        const bmsg = { role: 'tool', tool_call_id: tc.id, content: blk };
        messages.push(bmsg);
        await emitAdded(bmsg);
        continue;
      }
      ctx.emit({ type: 'tool_started', tc });
      if (tc.function.name === 'respond') {
        // Per-call validation: the first respond in the round was validated by
        // the pre-scan; subsequent ones (rare: multiple respond() in one round)
        // are validated here individually.
        let _tcText, _tcLocale, _tcReject = false, _tcReason = '';
        if (tc === respondCall) {
          _tcText = respondText; _tcLocale = respondLocaleOverride;
          _tcReject = _rejectRespondLang; _tcReason = _rejectReason;
        } else {
          try {
            const _a2 = JSON.parse(tc.function.arguments || '{}');
            _tcText = String(_a2.text ?? '');
            _tcLocale = _locFromOverride(_a2.language);
            if (!_tcLocale) { _tcReject = true; _tcReason = 'missing'; }
            else if (ctx._respondCount >= MAX_RESPOND_DELIVERIES) { _tcReject = true; _tcReason = 'cap'; }
            else if (ctx._respondLangs.has(_tcLocale.code)) { _tcReject = true; _tcReason = 'duplicate'; }
          } catch (_) { _tcText = ''; _tcReject = true; _tcReason = 'missing'; }
        }
        if (_tcReject) {
          let _rejMsg;
          if (_tcReason === 'cap') {
            _rejMsg = 'TURN ENDED: You have delivered the maximum number of replies ('
              + MAX_RESPOND_DELIVERIES + ') this turn. Do not call respond() again.';
          } else if (_tcReason === 'duplicate') {
            // A reply was already delivered in this language this turn. Re-delivering
            // the same language means the model is failing to end the turn — so END it
            // now (the reply is already on screen) instead of rejecting and looping.
            // Together with the _responded guard on the closing-respond force above,
            // this closes the respond()/duplicate-guard livelock.
            _endTurnAfterRound = true;
            _rejMsg = 'TURN ENDED: a reply was already delivered in this language ('
              + (_tcLocale ? _tcLocale.code : '?') + '). The turn is now complete — no further action needed.';
          } else {
            ctx._langRejectCount = (ctx._langRejectCount || 0) + 1;
            if (ctx._langRejectCount > 3) {
              ctx._responded = true; ctx._respondIsLatest = true;
              ctx.emit({ type: 'tool_result', id: tc.id, result: 'respond:' + _tcText });
              const rmsg = { role: 'tool', tool_call_id: tc.id, content: '[respond delivered]' };
              messages.push(rmsg); await emitAdded(rmsg); continue;
            }
            _rejMsg = 'REJECTED: The "language" parameter is REQUIRED on respond(). '
              + 'Call respond() again with the SAME text but include the "language" field '
              + 'set to the language code the user asked for (e.g. "ca", "es", "en").';
          }
          ctx.emit({ type: 'tool_result', id: tc.id, result: _rejMsg });
          const rmsg = { role: 'tool', tool_call_id: tc.id, content: _rejMsg };
          messages.push(rmsg); await emitAdded(rmsg); continue;
        }
        // Accepted — deliver. Track for subsequent calls if not the pre-scanned one.
        if (tc !== respondCall) {
          ctx._responded = true;
          ctx._respondCount++;
          ctx._respondLangs.add(_tcLocale.code);
        }
        ctx._respondIsLatest = true;   // a respond just executed → it is the latest action (order matters within a batch)
        ctx.emit({ type: 'tool_result', id: tc.id, result: 'respond:' + _tcText });
        const rmsg = { role: 'tool', tool_call_id: tc.id, content: '[respond delivered]' };
        messages.push(rmsg);
        await emitAdded(rmsg);
        continue;
      }
      ctx._currentToolCallId = tc.id;   // so spawn_subagent can tag its nested events to this box
      ctx._respondIsLatest = false;      // a non-respond tool is executing → respond is no longer the latest action; the turn can't end until a fresh respond
      let toolOut;
      const _toolStart = _profNow();
      let _toolErr = false;
      // Touched-file attribution is by OWNER STAMP (ctx.agentId on each write's
      // forward-to-page payload), routed by the postMessage interceptor to this
      // run's registered sink — not a shared armed pointer. So a python write
      // relayed after this call returns still lands in the RIGHT conversation
      // even while another chat's tool is mid-flight.
      try { toolOut = await runToolGuarded(tc.function.name, parsedArgs, ctx); }
      catch (e) { toolOut = { result: 'Error: ' + (e && e.message || e) }; _toolErr = true; }
      // Profiling: per-tool wall time (run_python == pyodide). Count as an error
      // when the call threw or the tool returned an "Error:" result.
      _profTool(tc.function.name, _profNow() - _toolStart,
        _toolErr || /^(\[r\d+\] )?Error:/.test((toolOut && toolOut.result) || ''));
      if (tc.function.name === 'write_todos' || tc.function.name === 'scratch') touchedTodo = true;
      // Progressive file surfacing: announce files this call just touched so the
      // user sees the deliverable appear NOW (its card auto-reloads on later
      // writes); the turn-end emit re-sends the full list for final ordering.
      if (!maxRounds && ctx._filesTouched && ctx._filesTouched.size) {
        try {
          const fresh = [];
          for (const [p, ts] of ctx._filesTouched) {
            if (!p || _ftExcluded(p)) continue;
            if ((ctx._ftAnnounced.get(p) || 0) >= ts) continue;
            ctx._ftAnnounced.set(p, ts); fresh.push({ path: p, ts });
          }
          if (fresh.length) ctx.emit({ type: 'files_touched', files: fresh, partial: true });
        } catch (_) {}
      }
      try { _metacogObserve(_statsFor(convFileName), tc.function.name, parsedArgs); } catch (_) {}   // METACOG (a)
      // write_todos results must round-trip intact: the page renders + persists
      // the checklist from the 'todos:' JSON line, and history rendering parses
      // it back on reload — a 30kB cut mid-JSON made the persisted result
      // unparseable, so the checklist rendered EMPTY from history. Like the
      // citable-id tag below, checklist bookkeeping is exempt from truncation.
      let safeResult = (tc.function.name === 'write_todos' || tc.function.name === 'scratch')
        ? toolOut.result
        : truncateToolResult(toolOut.result);
      // Citable result id (F1): tag the result so the model can cite it as
      // evidence ("r7") when closing a claim-todo. write_todos output is
      // checklist bookkeeping, not observations of the world — never tagged,
      // so a claim can't cite the checklist as proof of itself.
      if (tc.function.name !== 'write_todos' && tc.function.name !== 'scratch') {
        const rid = 'r' + (++ctx._resultSeq);
        (ctx._resultIds || (ctx._resultIds = new Set())).add(rid);
        safeResult = '[' + rid + '] ' + safeResult;
      }
      ctx.emit({ type: 'tool_result', id: tc.id, result: safeResult });
      const toolMsg = { role: 'tool', tool_call_id: tc.id, content: safeResult };
      messages.push(toolMsg);
      await emitAdded(toolMsg);
      if (toolOut && toolOut.image && toolOut.image.dataUrl) loadedImages.push(toolOut.image);
    }
    // A duplicate-language respond() this round signalled the turn is done (reply
    // already delivered) — end here rather than loop on the rejection.
    if (_endTurnAfterRound) break;
    // respond() is NOT terminal: the model MAY respond and then keep working. The
    // turn-end invariant (the turn must contain a delivered respond) is enforced in
    // the no-tool block above via _respondIsLatest + the closing-respond force. Here
    // we only cap total deliveries so a runaway respond loop can't spin forever.
    if (ctx._respondCount >= MAX_RESPOND_DELIVERIES) break;
    // Drift counter: reset when the plan was touched, else advance. Only a NEW
    // completion clears the stop guard, so a model that keeps finishing items is
    // helped indefinitely while one that merely rewrites the list without progress
    // still hits MAX_STOP_BLOCKS.
    ctx._roundsSinceTodo = touchedTodo ? 0 : ctx._roundsSinceTodo + 1;
    if (touchedTodo) ctx._lastNagAt = 0;   // real plan update clears the escalation baseline
    if (touchedTodo) {
      const done = ctx._todos.filter(t => t.status === 'completed').length;
      if (done > ctx._lastTodoDone) ctx._stopBlocks = 0;
      ctx._lastTodoDone = done;
      // METACOG (b): a completion resets the grind gap; record the span it took.
      try { const s = _statsFor(convFileName); if (done > s.done) { s.gaps.push(s.since); s.since = 0; s.done = done; } } catch (_) {}
    }
    if (loadedImages.length) {
      messages.push({ role: 'user', content: loadedImages.map(im => ({ type: 'image_url', image_url: { url: im.dataUrl } })) });
      const imgMsg = { role: 'user', _loadedImage: true, content: loadedImages.map(im => ({ type: 'image_url', image_url: { url: 'opfs://' + im.path } })) };
      await emitAdded(imgMsg);
    }
    // End of round, and another round WILL follow (this round called tools). If the
    // request we just sent was already over the threshold, pause and compact before
    // issuing the next one. Gated on the round's REAL reported prompt_tokens — the
    // one and only mid-turn condition. Never skipped: a required compaction that
    // fails halts the turn loudly rather than shipping an over-limit request. We
    // don't do this on the turn's final (no-tool) round — worker compaction is
    // ephemeral (not persisted), so it would be a wasted summarizer call.
    try {
      const _cmpStart = _profNow();
      await maybeCompactMidTurn(config, messages, ctx, round.usage && round.usage.prompt_tokens);
      _prof.compactionMs += _profNow() - _cmpStart;
    } catch (e) {
      if (e && e.compactionFailed) { ctx.emit({ type: 'error', message: (e && e.message) || 'Compaction failed.' }); break; }
      console.warn('[sandpie] mid-turn compaction error:', e);
    }
  }
  // Touched-file surfacing (main loop only): the deduped, oldest-first list of
  // files this turn touched — the page renders one card per file (newest at the
  // bottom; .html/images auto-expand, the rest collapse to a clickable card).
  // This REPLACES show_artifact: surfacing is harness-owned, the model cannot
  // forget it. Deliverable localization (the old show_artifact side effect)
  // triggers here too, off-turn, for translatable deliverable formats.
  if (!maxRounds && ctx._filesTouched && ctx._filesTouched.size) {
    try {
      const files = [...ctx._filesTouched.entries()]
        .filter(([p]) => p && !_ftExcluded(p))
        .sort((a, b) => a[1] - b[1])
        .map(([path, ts]) => ({ path, ts }));
      if (files.length) {
        ctx.emit({ type: 'files_touched', files, partial: false });
        const lx = ctx._localize;
        if (lx && lx.code) for (const f of files) if (/\.(html?|docx|md)$/i.test(f.path)) _localizeArtifactOffTurn(f.path, ctx, lx);
      }
    } catch (_) {}
  }
  // Per-turn profiling report (main loop only — see _emitTiming above). Also
  // called from the message handler's finally so a thrown turn still reports.
  _emitTiming();
  ctx.emit({ type: 'agent_done', persistedCount: ctx._persistCount });
}

// ============================================================
// write_file / edit_file
// ============================================================
async function tool_write_file({ path, content, overwrite, _conv }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  if (_betaOn()) {
    const r = _betaResolve(path, ctx);
    if (r.kind === 'dbx') {
      const err = _betaWriteGuard(r.path, ctx);
      if (err) return { result: err };
      const bytes = new TextEncoder().encode(content || '');
      // overwrite:false conflict check via Dropbox metadata (no OPFS to probe).
      if (!overwrite) {
        let meta = null; try { meta = await _dbxMeta(r.path, r.team); } catch (_) {}
        if (meta && meta['.tag'] === 'file') {
          let existing = ''; try { existing = new TextDecoder().decode(await _dbxDownloadBytes(r.path, r.team)); } catch (_) {}
          if ((content || '') === existing) return { result: `${r.path} already contains exactly this content (${existing.length} bytes) — no write needed.` };
          const nm = r.path.split('/').pop();
          const hint = `Pick ONE: (a) small change → edit_file it in place; (b) full replacement intended → call write_file again with overwrite:true. NEVER save a renamed copy like ${nm.replace(/(\.[^.]*)?$/, '_v2$1')}.`;
          const CAP = 2000;
          const shown = existing.length > CAP ? existing.slice(0, CAP) + `\n…(truncated; ${existing.length} bytes total — read_file to see the rest)` : existing;
          return { result: `${r.path} already exists (${existing.length} bytes) — NOT overwritten. ${hint} Current content (head):\n\n${shown}` };
        }
      }
      let existed = false;
      try { const m = await _dbxMeta(r.path, r.team); existed = !!(m && m['.tag'] === 'file'); } catch (_) {}
      try {
        await _dbxUpload(r.path, bytes, r.team);
        _betaTouch(ctx, r.path);
        return { result: `${existed ? 'Overwrote' : 'Created'}: ${r.path} (${bytes.byteLength} bytes)` };
      } catch (e) { return { result: `Write failed: ${(e && e.message) || e}` }; }
    }
    if (r.kind === 'noproject') return { result: 'Error: "' + path + '" is a project-relative path but this conversation has no project folder to write into.' };
    // r.kind === 'opfs' → sandpie/ metadata: fall through to the OPFS path below.
  }
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  let existed = false;
  if (!overwrite) try {
    const root = await opfsRoot();
    const parts = norm.split('/').filter(Boolean); const name = parts.pop();
    let dir = root;
    for (const p of parts) { dir = await dir.getDirectoryHandle(p, { create: false }); }
    try {
      await dir.getFileHandle(name);
      let existing = ''; try { existing = new TextDecoder().decode(await opfsReadBytes(norm)); } catch (_) {}
      // Writing byte-identical content over itself is a no-op, not a conflict.
      if ((content || '') === existing) return { result: `${norm} already contains exactly this content (${existing.length} bytes) — no write needed.` };
      // Refusal echo dedupe: if this exact content was already emitted into the
      // conversation (a prior read or refusal), don't re-echo it.
      const echoKey = (_conv || '') + '|' + norm + '|refusal';
      const hint = `Pick ONE: (a) small change → edit_file it in place; (b) full replacement intended → call write_file again with overwrite:true. NEVER save a renamed copy like ${name.replace(/(\.[^.]*)?$/, '_v2$1')}.`;
      const h = _fnv1a(existing);
      if (_emittedFileHashes.get(echoKey) === h) {
        return { result: `${norm} already exists (${existing.length} bytes, unchanged since it last appeared in your context) — NOT overwritten. ${hint}` };
      }
      _emittedFileHashes.set(echoKey, h);
      const CAP = 2000;
      const shown = existing.length > CAP ? existing.slice(0, CAP) + `\n…(truncated; ${existing.length} bytes total — read_file to see the rest)` : existing;
      return { result: `${norm} already exists (${existing.length} bytes) — NOT overwritten. ${hint} Current content (head):\n\n${shown}` };
    } catch (e) { if (e.name !== 'NotFoundError') throw e; }
  } catch (_) {}
  else try {
    // Overwrite path: only note whether the file existed, for an honest verb.
    const root = await opfsRoot();
    const parts = norm.split('/').filter(Boolean); const name = parts.pop();
    let dir = root;
    for (const p of parts) { dir = await dir.getDirectoryHandle(p, { create: false }); }
    await dir.getFileHandle(name); existed = true;
  } catch (_) {}
  try {
    await opfsWriteBytes(norm, new TextEncoder().encode(content || ''));
    _invalidateFileCache(norm);   // content changed → a re-read must re-emit, not stub
    // Notify the page so sync state marks this file dirty (prevents sync deletion).
    self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [norm], owner: ctx && ctx.agentId } });
    // Keep the Pyodide pool's MEMFS coherent with this OPFS write so a following
    // run_python sees it (per-worker FIFO ⇒ this lands before any later run).
    _pyBroadcast({ type: 'fs-changed', rel: norm });
    return { result: `${existed ? 'Overwrote' : 'Created'}: ${norm} (${new Blob([content]).size} bytes)` };
  } catch (e) { return { result: `Write failed: ${e.message}` }; }
}

// ============================================================
// delete_file
// ============================================================
// Removes a file (or directory) from OPFS and propagates the deletion the same
// way a python-side os.remove does: the page relays `opfs-deleted-by-python`
// (name is historical — it is the generic deletion channel) to dropbox.js,
// which deletes the cloud copy through the confirm-before-trim handshake and
// fans `opfs-removed` out to the Pyodide pool so sibling interpreters drop
// their MEMFS copies. sandpie/ is refused: it holds system state (memories,
// skills, conversation JSONL) that has its own flows.
async function tool_delete_file({ path, recursive }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  if (_betaOn()) {
    const r = _betaResolve(path, ctx);
    if (r.kind === 'opfs') return { result: `Refused: ${r.rel} is under sandpie/ — system data (memories, skills, conversations). Not deletable with this tool.` };
    if (r.kind === 'noproject') return { result: 'Error: "' + path + '" is a project-relative path but this conversation has no project folder.' };
    const err = _betaWriteGuard(r.path, ctx);   // delete is a write — must stay in-project
    if (err) return { result: err };
    try {
      const res = await _dbxDelete(r.path, r.team);
      if (res && res['.tag'] === 'not_found') return { result: `Nothing to delete: ${r.path} does not exist.` };
      _betaUntouch(ctx, r.path);   // a delete is not a create/edit — never surface it as a touched file
      return { result: `Deleted: ${r.path}` };
    } catch (e) { return { result: `Delete failed: ${(e && e.message) || e}` }; }
  }
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  if (!norm) return { result: 'Refused: cannot delete the /files/ root.' };
  if (norm === 'sandpie' || norm.startsWith('sandpie/')) {
    return { result: `Refused: ${norm} is under sandpie/ — system data (memories, skills, conversations, scripts). Not deletable with this tool.` };
  }
  try {
    const root = await opfsRoot();
    const parts = norm.split('/').filter(Boolean); const name = parts.pop();
    let dir = root;
    for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: false });
    await dir.removeEntry(name, { recursive: !!recursive });
    _invalidateFileCache(norm);   // gone → a re-read must NOT claim "unchanged, in your context"
    self.postMessage({ type: 'forward-to-page', payload: { type: 'opfs-deleted-by-python', paths: [norm], owner: ctx && ctx.agentId } });
    return { result: `Deleted: ${norm}` };
  } catch (e) {
    if (e && e.name === 'NotFoundError') return { result: `Not found: ${norm} — nothing to delete.` };
    if (e && (e.name === 'InvalidModificationError' || /not empty/i.test((e && e.message) || ''))) {
      return { result: `Refused: ${norm} is a non-empty directory — pass recursive:true to delete it and everything inside.` };
    }
    return { result: `Delete failed: ${(e && e.message) || e}` };
  }
}

function _matchEol(orig, lf) { return /\r\n/.test(orig) ? lf.replace(/\n/g, '\r\n') : lf; }
function _lineNosOf(text, str) {
  const out = []; let i = -1;
  while (str && (i = text.indexOf(str, i + 1)) !== -1) out.push(text.slice(0, i).split('\n').length);
  return out;
}
function _closestLines(fileLines, oldLines) {
  const target = (oldLines.find(l => l.trim()) || '').trim(); if (!target) return [];
  const pre = (a, b) => { let n = 0; while (n < a.length && n < b.length && a[n] === b[n]) n++; return n; };
  const scored = [];
  fileLines.forEach((l, i) => { const t = l.trim(); if (!t) return; const score = t === target ? 1e9 : (t.includes(target) || target.includes(t)) ? 1e6 : pre(t, target); if (score >= 6) scored.push({ i, t, score }); });
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, 5).map(s => `  line ${s.i + 1}: ${s.t.slice(0, 120)}`);
}
function applyEdit(current, oldStr, newStr) {
  let nos = _lineNosOf(current, oldStr);
  if (nos.length === 1) return { updated: current.replace(oldStr, () => newStr) };
  if (nos.length > 1) return { error: `old_str matches ${nos.length} times (lines ${nos.join(', ')}) — add surrounding context so it matches exactly one place.` };
  const curLF = current.replace(/\r\n?/g, '\n'), oldLF = oldStr.replace(/\r\n?/g, '\n'), newLF = newStr.replace(/\r\n?/g, '\n');
  nos = _lineNosOf(curLF, oldLF);
  if (nos.length === 1) return { updated: _matchEol(current, curLF.replace(oldLF, () => newLF)), note: 'matched ignoring line endings' };
  if (nos.length > 1) return { error: `old_str matches ${nos.length} times (lines ${nos.join(', ')}) — add surrounding context so it matches exactly one place.` };
  const fileLines = curLF.split('\n'), oldLines = oldLF.split('\n');
  const rstrip = s => s.replace(/[ \t]+$/, '');
  const fN = fileLines.map(rstrip), oN = oldLines.map(rstrip);
  const hits = [];
  for (let i = 0; i + oN.length <= fN.length; i++) { let ok = true; for (let j = 0; j < oN.length; j++) if (fN[i + j] !== oN[j]) { ok = false; break; } if (ok) hits.push(i); }
  if (hits.length === 1) { const i = hits[0]; const merged = fileLines.slice(0, i).concat(newLF.split('\n'), fileLines.slice(i + oldLines.length)).join('\n'); return { updated: _matchEol(current, merged), note: 'matched ignoring trailing whitespace' }; }
  if (hits.length > 1) return { error: `old_str matches ${hits.length} places (ignoring trailing whitespace), at lines ${hits.map(i => i + 1).join(', ')} — add surrounding context to disambiguate.` };
  const near = _closestLines(fileLines, oldLines);
  return { error: 'old_str not found (tried exact, line-ending, and trailing-whitespace-tolerant matching). Read the file and copy the exact text into old_str.' + (near.length ? '\nClosest lines in the file:\n' + near.join('\n') : '') };
}

// Longest-common-subsequence line diff (classic DP + backtrack). Returns an
// ordered op list: {t:' '|'-'|'+', s}. Only ever run on the differing CORE of an
// edit (common prefix/suffix already trimmed), so the table stays small.
function _lcsDiff(o, n) {
  const m = o.length, k = n.length;
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(k + 1));
  for (let i = m - 1; i >= 0; i--)
    for (let j = k - 1; j >= 0; j--)
      dp[i][j] = o[i] === n[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops = [];
  let i = 0, j = 0;
  while (i < m && j < k) {
    if (o[i] === n[j]) { ops.push({ t: ' ', s: o[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ t: '-', s: o[i] }); i++; }
    else { ops.push({ t: '+', s: n[j] }); j++; }
  }
  while (i < m) { ops.push({ t: '-', s: o[i++] }); }
  while (j < k) { ops.push({ t: '+', s: n[j++] }); }
  return ops;
}

// Line-level report for a single edit_file change, for the tool result — so the
// model (and the user, in the tool box) sees exactly what changed and where.
// Trims the common prefix/suffix (cheap, O(n)) then LCS-diffs only the differing
// core, so interior unchanged lines render as CONTEXT rather than bogus -/+ churn
// and `added`/`removed` are the true minimal line counts. Returns
// { added, removed, diff } where `diff` is a unified-style, line-numbered hunk
// (counts in the @@ header include context, per convention), or '' when there's
// nothing to show (identical) or the change is too large to diff/print inline —
// in which case `added`/`removed` still carry accurate (or, for a very large
// core, upper-bound) counts for the caller's summary.
function _editReport(oldText, newText, ctx = 3) {
  const o = oldText.split('\n'), n = newText.split('\n');
  let p = 0;
  while (p < o.length && p < n.length && o[p] === n[p]) p++;
  let s = 0;
  while (s < o.length - p && s < n.length - p && o[o.length - 1 - s] === n[n.length - 1 - s]) s++;
  const oEnd = o.length - s, nEnd = n.length - s;
  const oCore = o.slice(p, oEnd), nCore = n.slice(p, nEnd);
  if (!oCore.length && !nCore.length) return { added: 0, removed: 0, diff: '' };
  // Guard the O(m·k) LCS table: on a huge differing core, skip the diff and
  // return the coarse prefix/suffix span (an upper bound) as the counts.
  if (oCore.length * nCore.length > 250000) return { added: nCore.length, removed: oCore.length, diff: '' };

  const ops = _lcsDiff(oCore, nCore);
  let added = 0, removed = 0;
  for (const op of ops) { if (op.t === '+') added++; else if (op.t === '-') removed++; }
  if (added + removed === 0) return { added: 0, removed: 0, diff: '' };
  if (added + removed > 200) return { added, removed, diff: '' };   // too big — caller summarizes

  const lead = Math.min(ctx, p), trail = Math.min(ctx, o.length - oEnd);
  const body = [];
  let oi = p - lead, ni = p - lead;
  for (let i = 0; i < lead; i++) { body.push({ t: ' ', s: o[oi], oi, ni }); oi++; ni++; }
  for (const op of ops) {
    if (op.t === ' ') { body.push({ t: ' ', s: op.s, oi, ni }); oi++; ni++; }
    else if (op.t === '-') { body.push({ t: '-', s: op.s, oi }); oi++; }
    else { body.push({ t: '+', s: op.s, ni }); ni++; }
  }
  for (let i = 0; i < trail; i++) { body.push({ t: ' ', s: o[oEnd + i], oi: oEnd + i, ni: nEnd + i }); }

  const oldLen = body.reduce((a, b) => a + (b.t !== '+' ? 1 : 0), 0);
  const newLen = body.reduce((a, b) => a + (b.t !== '-' ? 1 : 0), 0);
  const start = (p - lead) + 1;
  const pad = String(Math.max(oEnd, nEnd, 1) + trail).length;
  const num = k => String(k).padStart(pad, ' ');
  const out = [`@@ -${start},${oldLen} +${start},${newLen} @@`];
  for (const b of body) {
    if (b.t === ' ') out.push(`  ${num(b.ni + 1)}  ${b.s}`);
    else if (b.t === '-') out.push(`- ${num(b.oi + 1)}  ${b.s}`);
    else out.push(`+ ${num(b.ni + 1)}  ${b.s}`);
  }
  return { added, removed, diff: out.join('\n') };
}

async function tool_edit_file({ path, old_str, new_str = '' }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  if (!old_str) return { result: 'Error: old_str is required.' };
  if (_betaOn()) {
    const r = _betaResolve(path, ctx);
    if (r.kind === 'noproject') return { result: 'Error: "' + path + '" is a project-relative path but this conversation has no project folder.' };
    if (r.kind === 'dbx') {
      const err = _betaWriteGuard(r.path, ctx);   // editing writes back — must stay in-project
      if (err) return { result: err };
      let current;
      try { current = new TextDecoder().decode(await _dbxDownloadBytes(r.path, r.team)); }
      catch { return { result: `File not found: ${r.path}. Use write_file to create it.` }; }
      const res = applyEdit(current, old_str, new_str);
      if (res.error) return { result: res.error };
      try {
        await _dbxUpload(r.path, new TextEncoder().encode(res.updated), r.team);
        _betaTouch(ctx, r.path);
        const head = `Edited ${r.path}${res.note ? ' (' + res.note + ')' : ''}`;
        const rep = _editReport(current, res.updated);
        if (rep.added === 0 && rep.removed === 0) return { result: `${head} — no line changes (content is identical).` };
        if (rep.diff) return { result: `${head} (+${rep.added} -${rep.removed})\n${rep.diff}` };
        return { result: `${head} — +${rep.added} -${rep.removed} line(s); diff too large to show inline.` };
      } catch (e) { return { result: `Edit failed: ${(e && e.message) || e}` }; }
    }
    // r.kind === 'opfs' → sandpie/ metadata: fall through to OPFS below.
  }
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  let current;
  try { current = new TextDecoder().decode(await opfsReadBytes(norm)); }
  catch {
    // Dehydrated: edit a not-yet-downloaded cloud file by hydrating it first.
    if (_indexEntry(norm)) {
      try { await hydrateAsync(norm); current = new TextDecoder().decode(await opfsReadBytes(norm)); }
      catch { return { result: `File not found: ${norm}. Use write_file to create it.` }; }
    } else { return { result: `File not found: ${norm}. Use write_file to create it.` }; }
  }
  const res = applyEdit(current, old_str, new_str);
  if (res.error) return { result: res.error };
  try {
    await opfsWriteBytes(norm, new TextEncoder().encode(res.updated));
    _invalidateFileCache(norm);   // content changed → a re-read must re-emit, not stub
    // Notify the page so sync state marks this file dirty (prevents sync deletion).
    self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [norm], owner: ctx && ctx.agentId } });
    _pyBroadcast({ type: 'fs-changed', rel: norm });
    const head = `Edited ${norm}${res.note ? ' (' + res.note + ')' : ''}`;
    const rep = _editReport(current, res.updated);
    let result;
    if (rep.added === 0 && rep.removed === 0) result = `${head} — no line changes (content is identical).`;
    else if (rep.diff) result = `${head} (+${rep.added} -${rep.removed})\n${rep.diff}`;
    else result = `${head} — +${rep.added} -${rep.removed} line(s); diff too large to show inline.`;
    return { result };
  } catch (e) { return { result: `Edit failed: ${e.message}` }; }
}
