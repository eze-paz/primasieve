// sandpie.js — Service Worker that runs the LLM agent loop end-to-end.
//
// Why: when the page tab is frozen by Chrome's energy-saver freezing, all
// page-side work stops — including the loop in sendSingle that decides
// "round done, run the tool, kick off the next round". Moving that loop
// into the SW (which is exempt from freezing while it's handling a fetch
// event) lets autonomous LLM ↔ tool ↔ LLM workflows progress while the
// page is minimized.
//
// Pyodide lives inside this SW directly so run_python doesn't have to
// round-trip back to the page. This means a SINGLE shared interpreter
// per origin (the per-conv isolation that the page-side pyWorker
// architecture had is gone here — explicit trade-off).
//
// Wire:
//   page POST /sandpie-agent { messages, model, endpoint, auth, ... }
//     → SW returns NDJSON stream of events:
//        { type:"delta", content?, tool_calls? }
//        { type:"round_end", content, tool_calls }
//        { type:"tool_started", tc }
//        { type:"tool_result", id, result }
//        { type:"message_added", message }  (the assistant or tool message just appended)
//        { type:"agent_done" }
//        { type:"error", message }
//
// Other endpoints kept for compat / discoverability:
//   POST /sandpie-stream { url, headers, body } → raw SSE pass-through
//                                                 (used when caller wants
//                                                 only one round, no agent
//                                                 loop)
//   POST /sandpie-py { code, argv } → run python once
//
// =============================================================================
// SW-side flow (mirrors the page-side flow chart in sandpie.html)
// =============================================================================
//
//   W1  install  → skipWaiting()                                  [line ~33]
//   W2  activate → clients.claim()                                [line ~34]
//   W3  fetch event router — four intercepted paths:             [line ~36]
//         /sandpie-agent  → handleAgent
//         /sandpie-stream → handleStream  (legacy single-round SSE proxy)
//         /sandpie-py     → handlePy      (one-shot run_python)
//         /opfs/<path>    → handleOpfs    (serve OPFS file; injects resize script for HTML)
//
//   S1  handleAgent(req): parse config, open ReadableStream.      [line ~491]
//   S2  ReadableStream.start → runAgent(config, ctx) with         [line ~446]
//       ctx.emit(ev) pushing NDJSON lines back to the page.
//   S3  runAgent loop (one iteration = one LLM round):
//         emit round_start
//         streamOneRound:                                         [line ~392]
//           fetch upstream LLM with stream=true
//           for each SSE delta:
//             accumulate content + toolCalls[i] from delta
//             emit { type:'delta', delta } VERBATIM (raw upstream
//             shape — the page reconstructs its own view)
//           return { content, tool_calls }
//         emit round_end
//         if no tool_calls: emit message_added (asst), break
//         emit message_added (asst with tool_calls)
//         for each tc in tool_calls:
//           sanitize tc.function.arguments via JSON.parse fallback
//           emit tool_started
//           toolOut = await runTool(name, args, ctx)              [line ~377]
//           emit tool_result (with optional artifacts)
//           emit message_added (tool)
//         next iteration
//       emit agent_done
//
//   T1  tool_run_python: lazy initPyodide (single shared interp),
//       exec user code, return stdout + artifacts.
//   T3  tool_show_artifact / tool_load_image: OPFS file validation + result tagging
//
// Adding a new tool: register it in runTool's switch AND export its
// schema to the page via tools[] in sandpie.html (the SW receives
// the schema array verbatim and forwards it to upstream).
// =============================================================================

// =============================================================================
// Console relay — every console.log/warn/error in the SW is also posted
// to all clients so it shows up in the PAGE'S regular DevTools console
// with a `[sw]` prefix. Without this the most actionable signals
// (Pyodide aborts, init failures, fatal resets) get buried in a separate
// DevTools window that you'd have to dig into Application → Service
// Workers → click the SW link to find.
// =============================================================================
// Buffer logs emitted during install/activate when there are no clients
// yet. First time a client connects (via the page-side message handler
// pinging us with `sandpie-sw-flush-logs`), we drain the buffer.
const _swLogBuffer = [];
const _MAX_BUFFER = 200;
function _relayLog(level, args) {
  // Best-effort stringification — most log args are strings or simple objects.
  const text = args.map(a => {
    if (a == null) return String(a);
    if (typeof a === 'string') return a;
    if (a instanceof Error) return (a.stack || a.message || String(a));
    try { return JSON.stringify(a); } catch (_) { return String(a); }
  }).join(' ');
  const msg = { type: 'sandpie-sw-log', level, text, ts: Date.now() };
  // Buffer ALL logs so the page-side relay can fetch the recent history
  // when it connects (e.g. SW boot logs that fired before the page was
  // listening). Cap so a noisy SW doesn't grow unbounded.
  _swLogBuffer.push(msg);
  if (_swLogBuffer.length > _MAX_BUFFER) _swLogBuffer.shift();
  // Fan out to current clients. includeUncontrolled:true so we still
  // reach a page that's mid-boot and not yet under SW control.
  self.clients.matchAll({ includeUncontrolled: true, type: 'window' })
    .then(clients => { for (const c of clients) c.postMessage(msg); })
    .catch(() => {});
}
const _origConsole = { log: console.log, warn: console.warn, error: console.error, info: console.info };
console.log   = (...args) => { try { _relayLog('log',   args); } catch (_) {} _origConsole.log.apply(console, args); };
console.warn  = (...args) => { try { _relayLog('warn',  args); } catch (_) {} _origConsole.warn.apply(console, args); };
console.error = (...args) => { try { _relayLog('error', args); } catch (_) {} _origConsole.error.apply(console, args); };
console.info  = (...args) => { try { _relayLog('info',  args); } catch (_) {} _origConsole.info.apply(console, args); };

// Catch silent SW failures: uncaught errors + unhandled promise rejections.
// Pyodide WASM aborts that terminate the SW thread won't reach this (the
// event loop is gone by then), but any JS-level error will, and seeing it
// in the page console is the first time we'll actually know it happened.
self.addEventListener('error', (ev) => {
  console.error('uncaught error:', ev.message, 'at', (ev.filename || '?') + ':' + (ev.lineno || '?'), ev.error && ev.error.stack ? '\n' + ev.error.stack : '');
});
self.addEventListener('unhandledrejection', (ev) => {
  const r = ev.reason;
  console.error('unhandled rejection:', r && (r.stack || r.message) || String(r));
});

// Drain the boot buffer when a client connects + asks for it. The page
// pings us with `sandpie-sw-flush-logs` on its message-handler init.
self.addEventListener('message', async (event) => {
  const data = event.data;
  if (!data) return;
  if (data.type === 'sandpie-sw-flush-logs') {
    for (const msg of _swLogBuffer) {
      try { event.source.postMessage(msg); } catch (_) {}
    }
    return;
  }
  if (data.type === 'opfs-removed' && Array.isArray(data.paths)) {
    // Page deleted these paths from OPFS. Drop them from Pyodide's MEMFS
    // view too, otherwise the next post-run syncfs() would push the stale
    // in-memory copy back to OPFS and resurrect the file (which then gets
    // re-uploaded to Dropbox on the next sync tick).
    if (!py) return;  // Pyodide not booted yet — nothing to clean up.
    for (const rel of data.paths) {
      const full = '/files/' + String(rel).replace(/^\/+/, '');
      try {
        const st = py.FS.stat(full);
        if (py.FS.isDir(st.mode)) _swRmTree(full);
        else py.FS.unlink(full);
      } catch (_) { /* already gone in MEMFS — fine */ }
    }
    return;
  }
  if (data.type === 'opfs-changed' && Array.isArray(data.paths)) {
    // Page wrote new files to OPFS. Sync them into Pyodide's MEMFS view
    // so the next run_python can see them without a full syncfs() walk.
    if (!py || !_nativefs) return;
    for (const rel of data.paths) {
      const full = '/files/' + String(rel).replace(/^\/+/, '');
      try {
        // Read from OPFS and write into MEMFS
        const bytes = await opfsReadBytes(rel);
        // Ensure parent dirs exist
        const dir = full.substring(0, full.lastIndexOf('/'));
        if (dir && dir !== '/files') {
          try { py.FS.mkdirTree(dir); } catch (_) {}
        }
        py.FS.writeFile(full, bytes);
      } catch (e) {
        console.warn('[sandpie-sw] opfs-changed sync failed for', rel, e);
      }
    }
    return;
  }
});

// Recursive rmdir within Pyodide's Emscripten FS. Used by the opfs-removed
// handler when the deleted path is a directory.
function _swRmTree(full) {
  let entries = [];
  try { entries = py.FS.readdir(full); } catch (_) { return; }
  for (const name of entries) {
    if (name === '.' || name === '..') continue;
    const child = full + '/' + name;
    try {
      const st = py.FS.stat(child);
      if (py.FS.isDir(st.mode)) _swRmTree(child);
      else py.FS.unlink(child);
    } catch (_) {}
  }
  try { py.FS.rmdir(full); } catch (_) {}
}

// Version stamp logged on every SW boot — confirms a fresh build is running.
const SW_VERSION = '1.6.0';
console.log('[sandpie-sw] boot — version=' + SW_VERSION);

// --- Pyodide bootstrap ------------------------------------------------------
// importScripts() in a service worker is only legal during the INITIAL
// SYNCHRONOUS evaluation of the SW script (i.e. right here, before any
// addEventListener runs) or synchronously inside an install handler.
// Pyodide's old call site — `importScripts(...)` from inside an async
// initPyodide() — fails with "failed to load" regardless of network state,
// which is why run_python never worked.
//
// Pre-import BOTH pyodide.js (the loader, ~500KB) and pyodide.asm.js (the
// emscripten glue, ~1MB) at top-level so they're in scope before loadPyodide
// runs. loadPyodide() internally calls importScripts(asm.js) again — when
// asm.js is already loaded, Pyodide detects that and skips the redundant
// call. Without the asm.js pre-import, loadPyodide tries the lazy
// importScripts (illegal past top-level) and throws.
//
// Both wrapped in try so a CDN outage at SW-install time can't break message
// sending — non-python tools and completions keep working; run_python
// returns a clear error if Pyodide didn't load. console.log lines confirm
// which step reached us (visible in DevTools → Application → Service workers
// → click the SW link to open its console).
const PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
let _pyodideJsLoaded = false;
try {
  console.log('[sandpie-sw] importing pyodide.js…');
  importScripts(PYODIDE_INDEX + 'pyodide.js');
  console.log('[sandpie-sw] importing pyodide.asm.js…');
  importScripts(PYODIDE_INDEX + 'pyodide.asm.js');
  _pyodideJsLoaded = true;
  console.log('[sandpie-sw] pyodide bootstrap scripts loaded');
} catch (e) {
  console.warn('[sandpie-sw] pyodide bootstrap failed:', e);
}

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// Completion notifications are shown via SW.registration.showNotification()
// because new Notification() from a page is a no-op on Android Chrome and
// not supported at all on iOS Safari tabs (iOS PWAs added to the home
// screen need SW-based notifications too). When the user taps one, we
// focus an existing sandpie window if there is one, otherwise open a new
// one — same UX as the prior page-side notif.onclick.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of wins) {
      if (c.url.includes('sandpie') && 'focus' in c) return c.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow('./sandpie.html');
  })());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  const path = url.pathname;
  if (path.endsWith('/sandpie-agent'))  return event.respondWith(handleAgent(event.request));
  if (path.endsWith('/sandpie-stream')) return event.respondWith(handleStream(event.request));
  if (path.endsWith('/sandpie-py'))     return event.respondWith(handlePy(event.request));
  if (path.includes('/opfs/'))          return event.respondWith(handleOpfs(path));
  // Anything else falls through to the network.
});

// ============================================================
// Pyodide — single shared instance in the SW. Loaded on first
// run_python; survives across requests as long as the SW is alive.
// SW idle termination (~30s) will lose this; next call re-bootstraps.
// ============================================================

let py = null;
let pyInitPromise = null;
// Pyodide's NativeFS mount handle for /files. Held at module scope so
// tool_run_python can call nativefs.syncfs() after each user run to push
// Python-side writes back into OPFS. Null if the mount failed at init
// (browser without OPFS, permission error, etc.) — Python still runs in
// MEMFS, just without /files.
let _nativefs = null;
async function initPyodide() {
  if (py) return py;
  if (pyInitPromise) return pyInitPromise;
  if (!_pyodideJsLoaded) {
    // pyodide.js wasn't loaded at SW init (CDN unreachable or blocked).
    // Surface a usable error instead of hanging the agent loop forever.
    throw new Error('Pyodide unavailable: pyodide.js failed to load when the service worker installed. Reload the page after going online to retry.');
  }
  // Wrap loadPyodide so a failure CLEARS pyInitPromise. Without this clear,
  // a rejected pyInitPromise sticks around forever and every subsequent call
  // resolves to the same failure — the next user retry returns the identical
  // error with no way to recover short of a page reload. The typical cause
  // is a CDN flake during the asm.js/wasm fetch; the second attempt usually
  // succeeds.
  pyInitPromise = (async () => {
    try {
      const p = await loadPyodide({ indexURL: PYODIDE_INDEX });
      // Lazy OPFS mount at /files. mountNativeFS gives Python a view onto
      // the user's OPFS via Pyodide's NATIVEFS — reads and writes translate
      // through to OPFS on demand. No upfront walk, no rmTree, no per-call
      // sync. tool_run_python calls nativefs.syncfs() after each run to
      // push pending writes back. If OPFS is unreachable (privacy mode,
      // permissions, older browser) we log and continue — Python runs
      // without /files; user code that touches it gets a normal Python
      // FileNotFoundError.
      try {
        const opfsRoot = await navigator.storage.getDirectory();
        _nativefs = await p.mountNativeFS('/files', opfsRoot);
        p.runPython('import os; os.chdir("/files")');
        console.log('[sandpie-sw] OPFS mounted at /files (cwd)');
      } catch (e) {
        _nativefs = null;
        console.warn('[sandpie-sw] OPFS mount failed (Python /files unavailable):', e);
      }
      py = p;
      return p;
    } catch (e) {
      pyInitPromise = null;  // allow retry on next initPyodide() call
      throw e;
    }
  })();
  return pyInitPromise;
}

// Hard reset Pyodide state. Call when the interpreter is wedged (Emscripten
// abort, WASM runtime error, memory corruption) so the next run_python call
// re-bootstraps from scratch instead of repeatedly hitting the corrupted
// instance. NOT to be called on Python-side exceptions (PythonError) —
// those are user-code errors and Pyodide is still healthy.
function resetPyodide(reason) {
  console.warn('[sandpie-sw] resetting Pyodide:', reason);
  py = null;
  pyInitPromise = null;
  _nativefs = null;  // dies with the interpreter; new init re-mounts
}

// Heuristic: should we treat this catch as Pyodide being dead?
// Conservative — false-positive resets only waste a reinit, false-negative
// resets leave the user stuck. So we require strong signals.
function isPyodideFatal(e, msg, stderr) {
  // Completely empty exception (no message, no stderr) — classic Emscripten
  // Abort signature.
  if (!msg && !stderr.trim()) return true;
  // WebAssembly runtime panics — instance is unrecoverable.
  if (typeof WebAssembly !== 'undefined' && e instanceof WebAssembly.RuntimeError) return true;
  const sig = ((msg || '') + ' ' + (stderr || '')).toLowerCase();
  // Emscripten / wasm death signatures.
  if (sig.includes('aborted(')) return true;
  if (sig.includes('runtimeerror: abort(')) return true;
  if (sig.includes('memory access out of bounds')) return true;
  if (sig.includes('out of memory') && sig.includes('wasm')) return true;
  return false;
}


// =============================================================================
// withPy — single-flight serializer for tool_run_python calls.
// =============================================================================
// The SW holds ONE Pyodide interpreter shared across all convs. tool_run_python
// mutates interpreter-global state (setStdout/setStderr batched callbacks
// closed over caller-local accumulators, self._sandpie_argv for script-mode
// sys.argv). Two concurrent callers would trample these and one would return
// garbage — withPy serializes the critical section.
//
// Trade-off: no parallelism across convs for Python. Acceptable; the only way
// to get true parallelism would be per-conv interpreters (workers), which
// were explicitly reverted.
//
// Implementation note: chain via .then(fn, fn) so a rejection from the
// previous call doesn't skip subsequent waiters — every queued fn runs in
// turn regardless of how the previous one settled. _pyMutex is then reset
// to a resolved promise (`.catch(() => {})`) so the chain length stays O(1)
// in the rejection case (no infinite chain of rejected promises).
let _pyMutex = Promise.resolve();
function withPy(fn) {
  const next = _pyMutex.then(fn, fn);
  _pyMutex = next.catch(() => {});
  return next;
}

// ---- OPFS helpers (same async API as the page, works in SW too) ----
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
async function opfsWriteBytes(path, bytes) {
  const { parts, name } = splitPath(path);
  const dir = await opfsResolveDir(parts, true);
  const handle = await dir.getFileHandle(name, { create: true });
  const w = await handle.createWritable();
  await w.write(bytes);
  await w.close();
}

// ============================================================
// Tool implementations (run inside the SW).
// ============================================================

async function tool_run_python({ path, args }, ctx) {
  if (!path) return { result: 'Error: "path" is required. Save a script with write_file first, then call run_python with its path.' };
  const scriptArgs = Array.isArray(args) ? args.map(String) : [];
  const normPath = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  let code;
  try {
    code = new TextDecoder().decode(await opfsReadBytes(normPath));
  } catch (e) {
    return { result: `Error: could not read /files/${normPath}: ${e.message}.` };
  }
  // Serialize the interpreter-touching critical section so concurrent
  // run_python calls don't race on the shared interpreter's globals
  // (setStdout closures, sys.argv, etc).
  return withPy(async () => {
    let p;
    try { p = await initPyodide(); }
    catch (e) { return { result: 'Error loading Pyodide: ' + (e && e.message || e) }; }
    let stdout = '', stderr = '';
    try {
      p.setStdout({ batched: s => { stdout += s + '\n'; } });
      p.setStderr({ batched: s => { stderr += s + '\n'; } });
      // Python environment: stdout/stderr capture + optional argv for `path:` mode.
      // /files is mounted lazily via mountNativeFS at init — Python can use plain
      // open()/os.listdir/glob and it reads OPFS on demand. Files not hydrated
      // Files not in OPFS must be created with run_python first.
      if (normPath) {
        self._sandpie_argv = [normPath, ...scriptArgs];
        try { p.runPython('import sys\nfrom js import _sandpie_argv\nsys.argv = list(_sandpie_argv.to_py())'); } catch (_) {}
      }
      try { await p.loadPackagesFromImports(code); } catch (_) {}
      // Single-retry: if user code dies with FileNotFoundError on a path
      // that references a missing file — the user must create it first.
      // whole snippet once. The LLM never sees the failure-then-retry —
      // it just gets the successful result. Budget is 1 to avoid fetch
      // storms inside one call; subsequent missing files in the same
      // snippet surface to the LLM (it can run again, where they'd
      // already be local or trigger another single retry).
      let _retried = false;
      // Flush any writes Python made into /files back to OPFS. No-op when
      // Python didn't touch the FS. Skipped (with a warning) if the mount
      // failed at init — Python had no /files to write to, nothing to flush.
      if (_nativefs) {
        try { await _nativefs.syncfs(); }
        catch (e) { console.warn('[sandpie-sw] syncfs after run_python failed:', e); }
      }
      let out = stdout.trimEnd();
      if (stderr.trim()) out += (out ? '\n' : '') + '--- stderr ---\n' + stderr.trimEnd();
      return { result: out || '(no output)' };
    } catch (e) {
      let msg = '';
      if (e != null) {
        if (typeof e === 'string') msg = e;
        else if (e.message) msg = e.message;
        else {
          try { const s = e.toString(); if (s && s !== '[object Object]') msg = s; } catch (_) {}
        }
      }
      const tail = stderr.trim() ? '\n--- stderr ---\n' + stderr.trimEnd() : '';
      // Fatal interpreter death: empty exception, WASM runtime error, or
      // Emscripten abort. Reset so the next call rebootstraps a fresh
      // interpreter instead of repeatedly failing in the wedged one.
      if (isPyodideFatal(e, msg, stderr)) {
        resetPyodide(msg || stderr.trim() || 'empty exception');
        return {
          result: 'FATAL: Pyodide runtime crashed and has been reset. All in-memory state (globals, imports, function defs) is gone — the next run_python call will start a clean interpreter. DO NOT retry the failing code as-is; re-do any imports/setup first.'
            + (msg ? '\n--- crash signal ---\n' + msg : '')
            + tail,
        };
      }
      return { result: 'Error: ' + (msg || 'unknown (no message)') + tail };
    } finally {
      try { p && p.setStdout({}); } catch (_) {}
      try { p && p.setStderr({}); } catch (_) {}
    }
  });
}



// Validate a file exists in OPFS and mark it for artifact rendering on the page.
// The page recognises 'artifact:<path>' in the result and renders an iframe via /opfs/<path>.
async function tool_show_artifact({ path }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  const clean = String(path).replace(/^\/+/, '');
  try {
    await opfsReadBytes(clean);
    return { result: 'artifact:' + clean };
  } catch (e) {
    return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' };
  }
}

async function tool_load_image({ path }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  const clean = String(path).replace(/^\/+/, '');
  try {
    await opfsReadBytes(clean);
    return { result: 'image:' + clean };
  } catch (e) {
    return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' };
  }
}

async function runTool(name, args, ctx) {
  switch (name) {
    case 'run_python':    return tool_run_python(args, ctx);
    case 'show_artifact': return tool_show_artifact(args, ctx);
    case 'load_image':    return tool_load_image(args, ctx);
    case 'write_file':    return tool_write_file(args, ctx);   // ← add
    case 'edit_file':     return tool_edit_file(args, ctx);    // ← add
    default:              return { result: 'Error: unknown tool ' + name };
  }
}

// ============================================================
// Auto-retry for transient upstream errors.
// ============================================================
const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504, 520, 522, 524]);
function isRetryableError(e) {
  if (!e || e.name === 'AbortError') return false;
  if (typeof e.status === 'number' && RETRYABLE_STATUS.has(e.status)) return true;
  if (e instanceof TypeError) return true; // bare network failure (DNS, dropped)
  return false;
}
function swSleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    if (signal) signal.addEventListener('abort', () => { clearTimeout(id); reject(new DOMException('aborted', 'AbortError')); }, { once: true });
  });
}
async function streamOneRoundWithRetry(reqUrl, headers, body, ctx) {
  const BACKOFF_MS = [1000, 2000, 5000, 10000]; // caps at 10s after 4th attempt
  for (let attempt = 0; ; attempt++) {
    try {
      if (attempt > 0) ctx.emit({ type: 'info', message: null });
      return await streamOneRound(reqUrl, headers, body, ctx);
    } catch (e) {
      if (ctx.signal?.aborted) throw e;
      if (!isRetryableError(e)) throw e;
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
      ctx.emit({ type: 'info', message: `Provider error (${e.status || 'network'}) — retrying in ${delay / 1000}s… (attempt ${attempt + 1})` });
      await swSleep(delay, ctx.signal);
    }
  }
}

// ============================================================
// LLM round: stream once, return assembled content + tool_calls.
// Emits delta events to ctx for live rendering on the page.
// ============================================================
async function streamOneRound(reqUrl, headers, body, ctx) {
  const res = await fetch(reqUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: ctx.signal,
  });
  if (!res.ok) {
    const text = (await res.text()).slice(0, 300);
    throw Object.assign(new Error(res.status + ': ' + text), { status: res.status });
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let content = '';
  const toolCalls = [];
  let sawDone = false;
  while (!sawDone) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6);
      if (data === '[DONE]') { sawDone = true; break; }
      try {
        const parsed = JSON.parse(data);
        const delta = parsed && parsed.choices && parsed.choices[0] && parsed.choices[0].delta;
        if (!delta) continue;
        if (delta.content) content += delta.content;
        if (delta.tool_calls) {
          for (const tc of delta.tool_calls) {
            const i = tc.index || 0;
            if (!toolCalls[i]) toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
            if (tc.id) toolCalls[i].id = tc.id;
            if (tc.function?.name) toolCalls[i].function.name += tc.function.name;
            if (tc.function?.arguments) toolCalls[i].function.arguments += tc.function.arguments;
          }
        }
        ctx.emit({ type: 'delta', delta });
      } catch (_) {}
    }
  }
  try { reader.cancel(); } catch (_) {}
  // Filter out tool calls without an id (incomplete deltas) — same logic as page.
  const keptToolCalls = toolCalls.filter(tc => tc && tc.id);
  return { content, tool_calls: keptToolCalls };
}

// ============================================================
// Agent loop: stream → check for tool_calls → run them → repeat.
// ============================================================
async function runAgent(config, ctx) {
  const messages = config.messages.slice();
  while (true) {
    if (ctx.signal && ctx.signal.aborted) break;
    ctx.emit({ type: 'round_start' });
    const reqBody = {
      model: config.model,
      messages: [config.systemPrompt, ...messages].filter(Boolean),
      stream: true,
      tools: config.tools,
    };
    const round = await streamOneRoundWithRetry(config.url, config.headers, reqBody, ctx);
    ctx.emit({ type: 'round_end', content: round.content, tool_calls: round.tool_calls });
    if (!round.tool_calls.length) {
      if (round.content) {
        const m = { role: 'assistant', content: round.content };
        messages.push(m);
        ctx.emit({ type: 'message_added', message: m });
      }
      break;
    }
    const asstMsg = { role: 'assistant', content: round.content, tool_calls: round.tool_calls };
    messages.push(asstMsg);
    ctx.emit({ type: 'message_added', message: asstMsg });
    for (const tc of round.tool_calls) {
      if (ctx.signal && ctx.signal.aborted) break;
      let parsedArgs = {};
      try { parsedArgs = JSON.parse(tc.function.arguments || '{}'); } catch (_) {}
      ctx.emit({ type: 'tool_started', tc });
      let toolOut;
      try { toolOut = await runTool(tc.function.name, parsedArgs, ctx); }
      catch (e) { toolOut = { result: 'Error: ' + (e && e.message || e) }; }
      ctx.emit({ type: 'tool_result', id: tc.id, result: toolOut.result });
      const toolMsg = { role: 'tool', tool_call_id: tc.id, content: toolOut.result };
      messages.push(toolMsg);
      ctx.emit({ type: 'message_added', message: toolMsg });
    }
  }
  ctx.emit({ type: 'agent_done' });
}

// ============================================================
// Handler wiring.
// ============================================================

async function handleAgent(req) {
  let config;
  try { config = await req.json(); }
  catch (e) { return jsonErr(400, 'bad request body: ' + e.message); }
  const abortCtl = new AbortController();
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const ctx = {
        emit(ev) { try { controller.enqueue(enc.encode(JSON.stringify(ev) + '\n')); } catch (_) {} },
        signal: abortCtl.signal,
        origin: config.origin || '',
      };
      try {
        await runAgent(config, ctx);
      } catch (e) {
        ctx.emit({ type: 'error', message: (e && e.message) || String(e), status: e && e.status });
      } finally {
        try { controller.close(); } catch (_) {}
      }
    },
    async cancel() {
      try { abortCtl.abort(); } catch (_) {}
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store' },
  });
}

// Backward-compat: a one-shot SSE proxy (just opens upstream, pipes back).
// Same shape as the prior implementation.
async function handleStream(req) {
  let payload;
  try { payload = await req.json(); }
  catch (e) { return jsonErr(400, 'bad request body: ' + e.message); }
  const { url, headers, body } = payload || {};
  if (!url) return jsonErr(400, 'missing "url"');
  const ctl = new AbortController();
  let upstream;
  try {
    upstream = await fetch(url, {
      method: 'POST',
      headers: headers || { 'Content-Type': 'application/json' },
      body: typeof body === 'string' ? body : JSON.stringify(body || {}),
      signal: ctl.signal,
    });
  } catch (e) { return jsonErr(502, 'upstream fetch failed: ' + (e && e.message || e)); }
  if (!upstream.ok) {
    const text = await upstream.text().catch(() => '');
    return new Response(text, { status: upstream.status });
  }
  const reader = upstream.body.getReader();
  const stream = new ReadableStream({
    start(controller) {
      (async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) { controller.close(); break; }
            controller.enqueue(value);
          }
        } catch (e) { try { controller.error(e); } catch (_) {} }
      })();
    },
    async cancel() {
      try { ctl.abort(); } catch (_) {}
      try { await reader.cancel(); } catch (_) {}
    },
  });
  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') || 'text/event-stream',
      'Cache-Control': 'no-store',
    },
  });
}

// One-shot run_python endpoint — useful for testing in isolation.
async function handlePy(req) {
  let args;
  try { args = await req.json(); }
  catch (e) { return jsonErr(400, 'bad request body: ' + e.message); }
  const ctx = {};
  const out = await tool_run_python(args, ctx);
  return new Response(JSON.stringify(out), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Serve an OPFS file over HTTP. HTML files get the postMessage resize script
// injected so the page-side resize listener can autosize the artifact iframe.
async function handleOpfs(path) {
  const opfsPath = decodeURIComponent(path.slice(path.indexOf('/opfs/') + '/opfs/'.length));
  try {
    const bytes = await opfsReadBytes(opfsPath);
    const ext = (opfsPath.split('.').pop() || '').toLowerCase();
    const types = { html:'text/html', htm:'text/html', svg:'image/svg+xml',
                    png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg',
                    gif:'image/gif', webp:'image/webp', csv:'text/csv',
                    json:'application/json', txt:'text/plain' };
    const ct = types[ext] || 'application/octet-stream';
    if (ext === 'html' || ext === 'htm') {
      let text = new TextDecoder().decode(bytes);
      const script = `<script>(function(){` +
        `function report(){var h=Math.max(document.body?document.body.scrollHeight:0,` +
        `document.documentElement?document.documentElement.scrollHeight:0,100);` +
        `parent.postMessage({type:'sandpie-artifact-resize',h:h},'*');}` +
        `var ro=new ResizeObserver(function(){requestAnimationFrame(report);});` +
        `if(document.body)ro.observe(document.body);` +
        `if(document.documentElement)ro.observe(document.documentElement);` +
        `window.addEventListener('load',report);` +
        `setTimeout(report,50);setTimeout(report,300);` +
        `})();<\/script>`;
      if (/<\/body>/i.test(text)) text = text.replace(/<\/body>/i, script + '</body>');
      else text += script;
      return new Response(text, { headers: { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' } });
    }
    return new Response(bytes, { headers: { 'Content-Type': ct, 'Content-Disposition': 'attachment', 'Cache-Control': 'no-store' } });
  } catch (e) {
    return new Response('Not found: ' + opfsPath, { status: 404, headers: { 'Content-Type': 'text/plain' } });
  }
}

function jsonErr(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function tool_write_file({ path, content }) {
  if (!path) return { result: 'Error: path is required.' };
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  try {
    const root = await opfsRoot();
    // Check existence
    const parts = norm.split('/').filter(Boolean);
    const name = parts.pop();
    let dir = root;
    for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: false }).catch(() => null) || await (async () => { throw new Error('checking'); })();
    try {
      await dir.getFileHandle(name);
      return { result: `File already exists: ${norm}. Use edit_file to modify it.` };
    } catch (_) { /* doesn't exist — good */ }
  } catch (_) { /* parent dir doesn't exist yet — that's fine, write creates it */ }
  try {
    await opfsWriteBytes(norm, new TextEncoder().encode(content || ''));
    return { result: `Created: ${norm} (${new Blob([content]).size} bytes)` };
  } catch (e) { return { result: `Write failed: ${e.message}` }; }
}

async function tool_edit_file({ path, old_str, new_str = '' }) {
  if (!path)    return { result: 'Error: path is required.' };
  if (!old_str) return { result: 'Error: old_str is required.' };
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  let current;
  try {
    current = new TextDecoder().decode(await opfsReadBytes(norm));
  } catch { return { result: `File not found: ${norm}` }; }
  const count = current.split(old_str).length - 1;
  if (count === 0) return { result: `old_str not found in ${norm}. Read the file first to verify exact content.` };
  if (count > 1)  return { result: `old_str matches ${count} times in ${norm} — make it more specific.` };
  try {
    const updated = current.replace(old_str, new_str);
    await opfsWriteBytes(norm, new TextEncoder().encode(updated));
    return { result: `Edited: ${norm}` };
  } catch (e) { return { result: `Edit failed: ${e.message}` }; }
}
