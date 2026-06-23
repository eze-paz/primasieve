const _swLogBuffer = [];
const _MAX_BUFFER = 200;
function _relayLog(level, args) {
  // Best-effort stringification — most log args are strings or simple objects.
  let text = args.map(a => {
    if (a == null) return String(a);
    if (typeof a === 'string') return a;
    if (a instanceof Error) return (a.stack || a.message || String(a));
    try { return JSON.stringify(a); } catch (_) { return String(a); }
  }).join(' ');

  const MAX_LOG_LEN = 5000;

  if (text.length > MAX_LOG_LEN) {
    text = text.slice(0, MAX_LOG_LEN) + '…';
  }
  
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

// Dropbox context pushed from the page so tool_search_dropbox can call the API.
let _dbxCtx = null;

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

    await withPy(async () => {
      for (const rel of data.paths) {
        const full = '/files/' + String(rel).replace(/^\/+/, '');
    
        try {
          const st = py.FS.stat(full);
    
          if (py.FS.isDir(st.mode)) _swRmTree(full);
          else py.FS.unlink(full);
        } catch (_) {}
      }
    });
    
    return;
  }
  if (data.type === 'opfs-changed' && Array.isArray(data.paths)) {
    // Page wrote new files to OPFS. Sync them into Pyodide's MEMFS view
    // so the next run_python can see them without a full syncfs() walk.
    if (!py || !_nativefs) return;
    
    await withPy(async () => {
      for (const rel of data.paths) {
        const full = '/files/' + String(rel).replace(/^\/+/, '');
        try {
          const bytes = await opfsReadBytes(rel);
    
          const dir = full.substring(0, full.lastIndexOf('/'));
          if (dir && dir !== '/files') {
            try { py.FS.mkdirTree(dir); } catch (_) {}
          }
    
          py.FS.writeFile(full, bytes);
        } catch (e) {
          console.warn('[sandpie-sw] opfs-changed sync failed for', rel, e);
        }
      }
    });
    
    return;
  }
  if (data.type === 'dbx-token') {
    _dbxCtx = { token: data.token, pathRoot: data.pathRoot || null, workingRoot: data.workingRoot || '' };
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

async function swOpfsDelete(relPath, isDir) {
  const parts = String(relPath).split('/').filter(Boolean);
  const name = parts.pop();
  if (!name) return false;
  try {
    const dir = await opfsResolveDir(parts);
    await dir.removeEntry(name, { recursive: !!isDir });
    console.log('[sandpie-sw] deleted from OPFS:', relPath);
    return true;
  } catch (e) {
    if (e.name !== 'NotFoundError') {
      console.warn('[sandpie-sw] failed to delete from OPFS:', relPath, e);
    }
    return false;
  }
}


// Version stamp logged on every SW boot — confirms a fresh build is running.
const SW_VERSION = '1.6.5-event-driven';
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
const PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v0.29.4/full/';
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
  if (path.endsWith('/sandpie-tool'))   return event.respondWith(handleTool(event.request));
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
      // OPFS mount at /files. mountNativeFS populates MEMFS from OPFS at mount
      // time, then Python reads/writes against that in-memory view. We do NOT
      // use syncfs() to flush (its reconcile stat()s every OPFS file and drops
      // deletes — pyodide#3881/#3456). Instead FS.trackingDelegate records what
      // Python changes under /files and flushCaptureToOpfs() applies it with
      // targeted writes/removeEntry after each run. If OPFS is unreachable
      // (privacy mode, permissions) we log and continue — Python runs without
      // /files; touching it raises FileNotFoundError.
      try {
        const opfsRoot = await navigator.storage.getDirectory();
        _nativefs = await p.mountNativeFS('/files', opfsRoot);
        p.runPython('import os; os.chdir("/files")');
        // Hook FS mutations so run_python writes just the changed paths back to
        // OPFS (armed only during a run via _capActive).
        p.FS.trackingDelegate = Object.assign(p.FS.trackingDelegate || {}, _fsTrackingDelegate());
        console.log('[sandpie-sw] OPFS mounted at /files (cwd); FS tracking installed');
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

// ---- Event-driven OPFS write-back (FS.trackingDelegate) --------------------
// Replaces both the syncfs() flush (which stat()s every OPFS file and silently
// drops deletes) and the before/after MEMFS snapshot diff (two full-tree walks
// per run). Emscripten's FS.trackingDelegate reports exactly which paths Python
// creates/writes/deletes under /files during a run; we then apply just those to
// OPFS via opfsWriteBytes / swOpfsDelete. O(changed files), and deletions are
// deterministic. Capture is armed only around runPythonAsync (_capActive) so
// page-side py.FS edits aren't echoed back.
let _capActive = false;
const _capTouched = new Set();   // OPFS-relative paths written, or dirs created
const _capDeleted = new Set();   // OPFS-relative paths unlinked / rmdir'd
function _capReset() { _capActive = false; _capTouched.clear(); _capDeleted.clear(); }

// Absolute Emscripten FS path -> OPFS-relative path, or null when outside the
// /files mount (/tmp, site-packages, …) and therefore not persisted.
function _opfsRelFromFs(fsPath) {
  const p = String(fsPath);
  if (p === '/files' || p === '/files/') return null;
  if (p.startsWith('/files/')) return p.slice('/files/'.length);
  return null;
}

// FS.trackingDelegate handlers (installed once after mount). No-ops unless
// _capActive. Names/args match Emscripten 4.0.9 (Pyodide 0.29.x).
function _fsTrackingDelegate() {
  const touch = (fsPath) => {
    if (!_capActive) return;
    const rel = _opfsRelFromFs(fsPath);
    if (rel == null) return;
    _capTouched.add(rel); _capDeleted.delete(rel);
  };
  const drop = (fsPath) => {
    if (!_capActive) return;
    const rel = _opfsRelFromFs(fsPath);
    if (rel == null) return;
    _capDeleted.add(rel); _capTouched.delete(rel);
  };
  return {
    onWriteToFile:   (path) => touch(path),
    onMakeDirectory: (path) => touch(path),
    onDeletePath:    (path) => drop(path),
    onMovePath:      (oldPath, newPath) => { drop(oldPath); touch(newPath); },
  };
}

// Apply the run's captured mutations to OPFS. Returns the OPFS-relative paths
// that actually existed and were deleted, so the page only fires cloud deletes
// for real files — not temp files a script created and removed in the same run.
async function flushCaptureToOpfs() {
  const removed = [];
  const written = [];   // OPFS-relative files actually written back (for cloud-sync)
  // Deletes first. rmtree records children before parents (insertion order),
  // and swOpfsDelete is recursive, so any stragglers go too.
  for (const rel of _capDeleted) {
    if (await swOpfsDelete(rel, true)) removed.push(rel);
  }
  // Writes / new dirs. stat() picks file vs dir and skips paths gone by end of
  // the run (created then deleted within the same run).
  for (const rel of _capTouched) {
    const full = '/files/' + rel;
    let st;
    try { st = py.FS.stat(full); } catch (_) { continue; }
    try {
      if (py.FS.isDir(st.mode)) await opfsResolveDir(rel.split('/').filter(Boolean), true);
      else { await opfsWriteBytes(rel, py.FS.readFile(full)); written.push(rel); }
    } catch (e) { console.warn('[sandpie-sw] OPFS write-back failed:', rel, e); }
  }
  return { removed, written };
}

// ============================================================
// Tool implementations (run inside the SW).
// ============================================================

const MAX_TOOL_RESULT_BYTES = 30 * 1024; // 30kB

function truncateToolResult(result) {
  if (typeof result !== 'string') {
    try {
      result = JSON.stringify(result);
    } catch {
      result = String(result);
    }
  }

  const bytes = new TextEncoder().encode(result);

  if (bytes.length <= MAX_TOOL_RESULT_BYTES) return result;

  // trim safely at byte level
  const sliced = bytes.slice(0, MAX_TOOL_RESULT_BYTES);
  const text = new TextDecoder().decode(sliced);

  return text + "\n\n[truncated: tool result exceeded 30kB]";
}

// ── script-usage tracker ─────────────────────────────────────────
// Accumulates {path: {count, firstUsed, lastUsed}} in OPFS root.
async function trackScriptRun(scriptPath, success, stderr) {
  try {
    const key = 'script_usage_index.json';
    const root = await navigator.storage.getDirectory();
    let data = {};
    try {
      const fh = await root.getFileHandle(key);
      const file = await fh.getFile();
      data = JSON.parse(await file.text());
    } catch (_) {}
    if (!data[scriptPath]) {
      data[scriptPath] = { count: 0, errors: 0, firstUsed: Date.now() };
    }
    data[scriptPath].count += 1;
    data[scriptPath].lastUsed = Date.now();
    if (!success) {
      data[scriptPath].errors += 1;
      data[scriptPath].lastError = (stderr || '').trim().slice(0, 500);
    }
    const fh = await root.getFileHandle(key, { create: true });
    const w = await fh.createWritable();
    await w.write(JSON.stringify(data, null, 2));
    await w.close();
  } catch (e) {
    console.warn('[sandpie-sw] usage tracking failed:', e);
  }
}

// Pull the failing source lines out of a Pyodide traceback so the model can make
// a targeted edit instead of rewriting. runPythonAsync compiles the script as
// File "<exec>", so its line numbers map 1:1 to the script source. Returns ''
// (traceback still shown) if no script frame is found.
function sourceFromTraceback(tb, code) {
  if (!tb || !code) return '';
  const lines = code.split('\n');
  const re = /File "(?:<exec>|<string>|<unknown>)", line (\d+)/g;
  const nums = [];
  let m;
  while ((m = re.exec(tb))) { const n = +m[1]; if (n >= 1 && n <= lines.length) nums.push(n); }
  if (!nums.length) return '';
  const focus = nums[nums.length - 1];               // deepest script frame = where it failed
  const a = Math.max(1, focus - 3), b = Math.min(lines.length, focus + 3);
  const out = [];
  for (let i = a; i <= b; i++) out.push(`${i === focus ? '>' : ' '} ${String(i).padStart(4)} | ${lines[i - 1]}`);
  return out.join('\n');
}

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
      // /files is the OPFS mount (MEMFS populated from OPFS at mount); Python
      // uses plain open()/os.listdir/glob against it.
      if (normPath) {
        self._sandpie_argv = [normPath, ...scriptArgs];
        try { p.runPython('import sys\nfrom js import _sandpie_argv\nsys.argv = list(_sandpie_argv.to_py())'); } catch (_) {}
      }

      try { await p.loadPackagesFromImports(code); } catch (_) {}
      // Arm FS-mutation capture for the user's code, then write the changes back
      // to OPFS with targeted ops — replaces the syncfs() flush and the
      // before/after snapshot diff. flushCaptureToOpfs returns the paths that
      // were really deleted (existed in OPFS) so we only fire cloud deletes for those.
      _capReset();
      _capActive = true;
      await p.runPythonAsync(code);
      _capActive = false;

      let removedPaths = [], writtenPaths = [];
      if (_nativefs) {
        try { ({ removed: removedPaths, written: writtenPaths } = await flushCaptureToOpfs()); }
        catch (e) { console.warn('[sandpie-sw] OPFS write-back after run_python failed:', e); }
      }

      // Notify the page so cloud-sync can act immediately instead of waiting for the
      // next periodic full scan: delete the cloud copies of removed files (batched),
      // and mark written files dirty (sw-opfs-changed → fast-path upload next sync).
      if (removedPaths.length || writtenPaths.length) {
        self.clients.matchAll({ includeUncontrolled: true, type: 'window' })
          .then(clients => {
            for (const c of clients) {
              try {
                if (removedPaths.length) c.postMessage({ type: 'opfs-deleted-by-python', paths: removedPaths });
                if (writtenPaths.length) c.postMessage({ type: 'sw-opfs-changed', paths: writtenPaths });
              } catch (_) {}
            }
          }).catch(() => {});
      }
      let out = stdout.trimEnd();
      if (stderr.trim()) out += (out ? '\n' : '') + '--- stderr ---\n' + stderr.trimEnd();
      trackScriptRun(normPath, true, stderr);
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
        trackScriptRun(normPath, false, stderr);
        return {
          result: 'FATAL: Pyodide runtime crashed and has been reset. All in-memory state (globals, imports, function defs) is gone — the next run_python call will start a clean interpreter. DO NOT retry the failing code as-is; re-do any imports/setup first.'
            + (msg ? '\n--- crash signal ---\n' + msg : '')
            + tail,
        };
      }
      trackScriptRun(normPath, false, stderr);
      const src = sourceFromTraceback(msg, code);
      return { result: 'Error: ' + (msg || 'unknown (no message)')
        + (src ? '\n\n--- ' + normPath + ' (around the error) ---\n' + src : '')
        + tail };
    } finally {
      _capActive = false;
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
    const bytes = await opfsReadBytes(clean);
    // Raw base64 data URL — no decode/recompress (the SW has no DOM canvas). The
    // agent loop turns this into a user-role image_url so the cloud model can see
    // the pixels in the same round; `image:<path>` drives the inline UI thumbnail.
    const ext = (clean.split('.').pop() || '').toLowerCase();
    const mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
                   gif: 'image/gif', webp: 'image/webp' }[ext] || 'application/octet-stream';
    let bin = '';
    const CHUNK = 0x8000;   // chunk the encode — fromCharCode on the whole array overflows the stack
    for (let i = 0; i < bytes.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    const dataUrl = 'data:' + mime + ';base64,' + btoa(bin);
    return { result: 'image:' + clean, image: { path: clean, dataUrl } };
  } catch (e) {
    return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' };
  }
}

// Load a skill's instructions on the model's request. Skills are folders under
// skills/, so the name maps straight to skills/<name>/SKILL.md — no index to
// consult. The name is validated (also blocks path traversal). We strip the
// leading frontmatter (the model already has name/description from the Skills
// section of the prompt) and return the body; the agent loop caps it
// (truncateToolResult).
async function tool_load_skill({ name }, ctx) {
  const n = String(name || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(n)) {
    return { result: 'Error: invalid skill name "' + name + '". Use the exact name from the Skills section.' };
  }
  const file = 'skills/' + n + '/SKILL.md';
  let text;
  try { text = new TextDecoder().decode(await opfsReadBytes(file)); }
  catch (e) { return { result: 'Error: could not read ' + file + ' — no such skill, or its ' + file + ' is missing.' }; }
  const body = text.replace(/^﻿?---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/, '').trim();
  return { result: body || text };
}

// ============================================================
// read_file / list_files / search — plain-JS file tools over OPFS.
// These run without Pyodide, so they're instant and can't crash the interpreter
// the way run_python can. Reading / browsing / grepping should go through these;
// run_python is for actual computation, data libraries and HTTP.
// ============================================================
const FILE_TOOL_CAP = 28 * 1024;        // chars of tool output before we truncate + tell the model to page
const FILE_TEXT_MAX = 2 * 1024 * 1024;  // skip files larger than this for text read/search
const SEARCH_SKIP_TOP = '_conversations'; // app-internal chat logs; only searched if explicitly targeted

function normFilesPath(p) {
  // strip a leading slash and an optional /files/ prefix and any trailing slash
  return String(p == null ? '' : p).replace(/^\/+/, '').replace(/^files\//, '').replace(/\/+$/, '');
}

// Anchored glob -> RegExp over a relative path: '*' = run within one segment,
// '**' = run across segments, '?' = one non-slash char; everything else literal.
function globToRegExp(glob) {
  const g = String(glob);
  let re = '';
  for (let i = 0; i < g.length; i++) {
    const c = g[i];
    if (c === '*') {
      if (g[i + 1] === '*') { re += '.*'; i++; if (g[i + 1] === '/') i++; }
      else re += '[^/]*';
    } else if (c === '?') {
      re += '[^/]';
    } else {
      re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    }
  }
  return new RegExp('^' + re + '$', 'i');
}

// Collect entries under a relative dir. Files carry their handle; dirs are
// included only when includeDirs. Caps how many entries we walk. Returns null
// when startRel isn't a directory.
async function opfsCollect(startRel, { recursive = false, includeDirs = false, max = 5000, skipTop = null } = {}) {
  const startParts = startRel ? startRel.split('/').filter(Boolean) : [];
  let startDir;
  try { startDir = await opfsResolveDir(startParts); }
  catch { return null; }
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
      } else {
        out.push({ path: full, kind: 'file', handle: h });
      }
    }
  }
  await walk(startDir, startRel);
  return out;
}

async function tool_read_file({ path, offset, limit }) {
  const norm = normFilesPath(path);
  if (!norm) return { result: 'Error: path is required.' };
  let file;
  try {
    const { parts, name } = splitPath(norm);
    const dir = await opfsResolveDir(parts);
    file = await (await dir.getFileHandle(name)).getFile();
  } catch { return { result: 'Error: file not found: ' + norm }; }
  if (file.size > FILE_TEXT_MAX) {
    return { result: `Error: ${norm} is ${file.size} bytes — too large to read as text. Process it with run_python instead.` };
  }
  const text = await file.text();
  if (/\x00/.test(text.slice(0, 4096))) {
    return { result: `Error: ${norm} looks binary. Use load_image (images) or run_python.` };
  }
  const lines = text.split('\n');
  const total = lines.length;
  let start = Number.isInteger(offset) && offset > 0 ? offset : 1;
  if (start > total) start = total;
  const lim = Number.isInteger(limit) && limit > 0 ? limit : 2000;
  const end = Math.min(total, start - 1 + lim);
  const header = `${norm} — ${total} line${total === 1 ? '' : 's'}, ${file.size} bytes`
    + (start > 1 || end < total ? ` (showing ${start}-${end})` : '');
  let buf = header + '\n';
  let lastShown = start - 1, truncated = false;
  for (let i = start; i <= end; i++) {
    const row = i + '\t' + lines[i - 1] + '\n';
    if (buf.length + row.length > FILE_TOOL_CAP) { truncated = true; break; }
    buf += row; lastShown = i;
  }
  if (truncated) buf += `…[truncated at line ${lastShown}; call again with offset=${lastShown + 1} for more]`;
  return { result: buf.replace(/\n$/, '') };
}

async function tool_list_files({ path, pattern, recursive }) {
  const norm = normFilesPath(path);
  const rx = pattern ? globToRegExp(pattern) : null;
  const entries = await opfsCollect(norm, { recursive: !!recursive, includeDirs: !recursive, max: 4000 });
  if (entries === null) return { result: 'Error: not a directory: ' + (norm || '/files/') };
  const rows = rx ? entries.filter(e => rx.test(e.path) || rx.test(e.path.split('/').pop())) : entries;
  if (!rows.length) {
    return { result: `No ${pattern ? 'files matching "' + pattern + '"' : 'entries'} under /${norm || ''}.` };
  }
  let buf = `${rows.length} entr${rows.length === 1 ? 'y' : 'ies'} under /${norm || ''}${pattern ? ' matching "' + pattern + '"' : ''}:\n`;
  let shown = 0, truncated = false;
  for (const e of rows) {
    let line;
    if (e.kind === 'directory') {
      line = e.path + '/\n';
    } else {
      let size = '?', mtime = '';
      try { const f = await e.handle.getFile(); size = f.size + 'b'; mtime = '  ' + new Date(f.lastModified).toISOString().slice(0, 16).replace('T', ' '); }
      catch {}
      line = `${e.path}\t${size}${mtime}\n`;
    }
    if (buf.length + line.length > FILE_TOOL_CAP) { truncated = true; break; }
    buf += line; shown++;
  }
  if (truncated) buf += `…[${rows.length - shown} more not shown; narrow with path/pattern]`;
  return { result: buf.replace(/\n$/, '') };
}

async function tool_search({ pattern, path, include, files_only, ignore_case }) {
  if (!pattern) return { result: 'Error: pattern (a regular expression) is required.' };
  let rx;
  try { rx = new RegExp(pattern, ignore_case === false ? '' : 'i'); }
  catch (e) { return { result: 'Error: invalid regex: ' + (e && e.message || e) }; }
  const norm = normFilesPath(path);
  const inc = include ? globToRegExp(include) : null;
  const skipTop = norm.startsWith(SEARCH_SKIP_TOP) ? null : SEARCH_SKIP_TOP;
  const files = await opfsCollect(norm, { recursive: true, includeDirs: false, max: 6000, skipTop });
  if (files === null) return { result: 'Error: not a directory: ' + (norm || '/files/') };

  let buf = '', matches = 0, scanned = 0, truncated = false;
  const hitFiles = new Set();
  for (const f of files) {
    if (inc && !(inc.test(f.path) || inc.test(f.path.split('/').pop()))) continue;
    let text;
    try {
      const file = await f.handle.getFile();
      if (file.size > FILE_TEXT_MAX) continue;
      text = await file.text();
    } catch { continue; }
    if (/\x00/.test(text.slice(0, 4096))) continue; // binary
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
  const where = norm ? '/' + norm : '/files/';
  if (files_only) {
    if (!hitFiles.size) return { result: `No files contain /${pattern}/ in ${where}. Scanned ${scanned}.` };
    return { result: `${hitFiles.size} file(s) match (scanned ${scanned}):\n` + [...hitFiles].sort().join('\n') };
  }
  if (!matches) return { result: `No matches for /${pattern}/ in ${where}${inc ? ' (include ' + include + ')' : ''}. Scanned ${scanned} files.` };
  const head = `${matches} match${matches === 1 ? '' : 'es'} in ${hitFiles.size} file${hitFiles.size === 1 ? '' : 's'} (scanned ${scanned})${truncated ? ' — truncated; narrow the pattern or path' : ''}:\n`;
  return { result: head + buf.replace(/\n$/, '') };
}

async function tool_search_dropbox({ query, path, filename_only }) {
  if (!_dbxCtx) return { result: 'Error: Dropbox token not available in service worker. Connect Dropbox in Settings and reload the page.' };
  if (!query || typeof query !== 'string' || !query.trim()) return { result: 'Error: query is required.' };

  const { token, pathRoot, workingRoot } = _dbxCtx;
  const searchPath = (typeof path === 'string' && path.trim()) ? path.trim() : (workingRoot || '');

  const reqBody = {
    query: query.trim(),
    options: { path: searchPath, max_results: 101, file_status: 'active', filename_only: !!filename_only },
  };
  const headers = { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' };
  if (pathRoot) headers['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: pathRoot });

  let res;
  try {
    res = await fetch('https://api.dropboxapi.com/2/files/search_v2', { method: 'POST', headers, body: JSON.stringify(reqBody) });
  } catch (e) {
    return { result: 'Error reaching Dropbox: ' + e.message };
  }
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    return { result: 'Dropbox search failed (' + res.status + '): ' + txt.slice(0, 400) };
  }

  const data = await res.json();
  const matches = Array.isArray(data.matches) ? data.matches : [];

  if (matches.length === 0) return { result: 'No files found for "' + query + '".' };
  if (matches.length > 100) return { result: 'Too many results (>100) for "' + query + '". Use more specific terms or restrict to a subfolder with the path parameter.' };

  const paths = matches.map(m => {
    const meta = m.metadata?.metadata || m.metadata || {};
    return meta.path_display || meta.path_lower || '(unknown)';
  }).sort();

  return { result: matches.length + ' file(s) found for "' + query + '":\n' + paths.join('\n') };
}

// Names runTool actually dispatches. Keep in sync with the switch below.
const KNOWN_TOOLS = ['run_python','write_file','edit_file','read_file',
                     'list_files','search','search_dropbox','show_artifact','load_skill','load_image'];

// A call to a tool that doesn't exist. Return a factual, generic correction so
// the model can self-correct next round: if the name is actually a skill, point
// it at load_skill; otherwise just list the real tools. No domain-specific advice.
async function unknownTool(name) {
  const n = String(name || '').trim().toLowerCase();
  if (/^[a-z0-9][a-z0-9_-]*$/.test(n)) {
    try {
      await opfsReadBytes('skills/' + n + '/SKILL.md');   // throws if it isn't a skill
      return { result: 'Error: "' + name + '" is a skill, not a tool. Call load_skill({"name":"' + n + '"}) to use it.' };
    } catch {}
  }
  return { result: 'Error: unknown tool "' + name + '". Available tools: ' + KNOWN_TOOLS.join(', ') + '.' };
}

async function runTool(name, args, ctx) {
  const convFileName = ctx._conversation_file_name || 'unknown';
  switch (name) {
    case 'run_python':    return tool_run_python({...args, _conv: convFileName}, ctx);
    case 'show_artifact': return tool_show_artifact(args, ctx);
    case 'load_image':    return tool_load_image(args, ctx);
    case 'load_skill':    return tool_load_skill(args, ctx);
    case 'read_file':     return tool_read_file(args, ctx);
    case 'list_files':    return tool_list_files(args, ctx);
    case 'search':          return tool_search(args, ctx);
    case 'search_dropbox':  return tool_search_dropbox(args, ctx);
    case 'write_file':    return tool_write_file({...args, _conv: convFileName}, ctx);   // ← add
    case 'edit_file':     return tool_edit_file(args, ctx);    // ← add
    default:              return unknownTool(name);
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

// Parse a model's NATIVE (non-OpenAI) tool-call special tokens out of raw text.
// Handles the Kimi K2 / Moonshot syntax that some routes fail to translate into
// structured `delta.tool_calls`, leaking it through as plain text instead:
//   <|tool_calls_section_begin|>
//     <|tool_call_begin|>functions.NAME:IDX<|tool_call_argument_begin|>{json}<|tool_call_end|>
//   <|tool_calls_section_end|>
// Returns { toolCalls, stripped } where `stripped` is the text with the whole
// section removed. Safe no-op (empty toolCalls, text unchanged) when absent.
function parseLeakedToolCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string' || text.indexOf('<|tool_call') === -1) {
    return { toolCalls, stripped: text };
  }
  const callRe = /<\|tool_call_begin\|>\s*functions\.([A-Za-z0-9_.\-]+):(\d+)\s*<\|tool_call_argument_begin\|>([\s\S]*?)<\|tool_call_end\|>/g;
  let m;
  while ((m = callRe.exec(text)) !== null) {
    const [, name, idx, rawArgs] = m;
    toolCalls.push({
      id: 'call_' + idx,
      type: 'function',
      function: { name, arguments: (rawArgs || '').trim() },
    });
  }
  // Strip the well-formed section, then any dangling begin marker left by a
  // truncated stream, so the raw tokens never reach history or the screen.
  const stripped = text
    .replace(/<\|tool_calls_section_begin\|>[\s\S]*?<\|tool_calls_section_end\|>/g, '')
    .replace(/<\|tool_calls_section_begin\|>[\s\S]*$/g, '')
    .trim();
  return { toolCalls, stripped };
}

// Scrub a model's leaked NATIVE framing tokens (e.g. Kimi's <|tool_call_end|>,
// <|tool_calls_section_end|>) out of a string. These must NEVER appear inside a
// structured tool call; when a buggy route leaks them into the name/arguments
// they corrupt the JSON, and once stored in history and sent back they make the
// provider 400 on the malformed `arguments` — ending the round with no
// agent_done, which the page then misreports as a service-worker crash.
function scrubFramingTokens(s) {
  return typeof s === 'string' ? s.replace(/<\|[\s\S]*?\|>/g, '') : s;
}

// First balanced {...} object in a string (brace-aware and string-aware), used
// to drop trailing junk left after a tool call's JSON arguments.
function firstBalancedObject(s) {
  const start = s.indexOf('{');
  if (start < 0) return null;
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
    } else if (c === '"') inStr = true;
    else if (c === '{') depth++;
    else if (c === '}' && --depth === 0) return s.slice(start, i + 1);
  }
  return null;
}

// Force a tool call's `arguments` to a VALID JSON object string. Strips leaked
// framing tokens, then parses; on failure applies minimal repairs (escape stray
// backslashes, then isolate the first balanced {...}); if nothing parses, falls
// back to "{}" so a malformed call degrades to a no-arg call the model can retry
// — never poisoned JSON that 400s every subsequent round and kills the session.
function normalizeToolArgs(raw) {
  const s0 = raw == null ? '' : String(raw);
  // Fast path: already-valid JSON with no leaked framing — leave it untouched.
  if (s0.indexOf('<|') === -1) { try { JSON.parse(s0); return s0; } catch (_) {} }
  const s = scrubFramingTokens(s0).trim();
  if (!s) return '{}';
  const tryParse = (t) => { try { return JSON.stringify(JSON.parse(t)); } catch (_) { return null; } };
  const escStray = (t) => t.replace(/\\(?!["\\/bfnrtu])/g, '\\\\');
  let out = tryParse(s) || tryParse(escStray(s));
  if (out) return out;
  const obj = firstBalancedObject(s);
  if (obj) { out = tryParse(obj) || tryParse(escStray(obj)); if (out) return out; }
  return '{}';
}

// ============================================================
// LLM round: stream once, return assembled content + tool_calls.
// Emits delta events to ctx for live rendering on the page.
// ============================================================
async function streamOneRound(reqUrl, headers, body, ctx) {
  
  const timeoutSignal = AbortSignal.timeout(120000);

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
  let reasoningText = '';
  const toolCalls = [];
  let usage = null;
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
        // Usage arrives via stream_options:{include_usage:true}. It typically
        // rides on a trailing chunk whose `choices` array is empty, so capture
        // it before the `delta` guard below skips the chunk.
        if (parsed && parsed.usage) usage = parsed.usage;
        const delta = parsed && parsed.choices && parsed.choices[0] && parsed.choices[0].delta;
        if (!delta) continue;
        if (delta.content) content += delta.content;
        if (typeof delta.reasoning_content === 'string') reasoningText += delta.reasoning_content;
        else if (typeof delta.reasoning === 'string') reasoningText += delta.reasoning;
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
  
  let keptToolCalls = toolCalls.filter(tc =>
    tc &&
    tc.id &&
    tc.function &&
    tc.function.name
  );
  
  // Recovery: some models (notably Kimi K2) emit their NATIVE tool-call special
  // tokens as plain text when the upstream route fails to parse them into
  // structured `delta.tool_calls`. The tokens leak into `content` (or the
  // reasoning/"thought" stream) and, because `tool_calls` stays empty, the
  // agent loop sees "no tool calls" and stops mid-task. Re-parse them here so
  // the loop can actually run the tool and continue.
  if (!keptToolCalls.length) {
    let parsed = parseLeakedToolCalls(content);
    if (parsed.toolCalls.length) {
      keptToolCalls = parsed.toolCalls;
      content = parsed.stripped;        // don't persist/show the raw tokens
    } else if (!content.trim()) {
      // The call may have been emitted into the reasoning channel, which we
      // don't fold into `content`. Recover it from there as a fallback.
      parsed = parseLeakedToolCalls(reasoningText);
      if (parsed.toolCalls.length) keptToolCalls = parsed.toolCalls;
    }
  }

  // Scrub leaked framing tokens out of every structured tool call and force its
  // arguments to valid JSON. A leaked <|tool_calls_section_end|> (or a bad escape
  // such as \p) inside `arguments` would otherwise be persisted to history and
  // 400 the provider on the next round — killing the session.
  for (const tc of keptToolCalls) {
    if (!tc || !tc.function) continue;
    if (typeof tc.function.name === 'string') {
      tc.function.name = scrubFramingTokens(tc.function.name).trim().replace(/^functions\./, '');
    }
    tc.function.arguments = normalizeToolArgs(tc.function.arguments);
  }

  return { content, tool_calls: keptToolCalls, usage };
}

// ============================================================
// Agent loop: stream → check for tool_calls → run them → repeat.
// ============================================================
async function runAgent(config, ctx) {
  const convFileName = config.conversation_file_name || 'unknown';
  ctx._conversation_file_name = convFileName;
  const messages = config.messages.slice();
  while (true) {
    if (ctx.signal && ctx.signal.aborted) break;
    ctx.emit({ type: 'round_start' });
    const reqBody = {
      model: config.model,
      messages: [config.systemPrompt, ...messages].filter(Boolean),
      stream: true,
      stream_options: { include_usage: true },
      tools: config.tools,
    };
    // Reasoning models require max_completion_tokens (it counts reasoning + answer
    // together) and reject max_tokens — so switch ONLY when a reasoning_effort is
    // configured, leaving plain providers / older OpenAI-compat endpoints on max_tokens.
    if (config.maxTokens != null) reqBody[config.reasoningEffort ? 'max_completion_tokens' : 'max_tokens'] = config.maxTokens;
    if (config.temperature != null) reqBody.temperature = config.temperature;
    if (config.reasoningEffort) reqBody.reasoning_effort = config.reasoningEffort;
    const round = await streamOneRoundWithRetry(config.url, config.headers, reqBody, ctx);
    ctx.emit({ type: 'round_end', content: round.content, tool_calls: round.tool_calls });
    // Real token counts when the provider honors include_usage. The final
    // round's prompt_tokens reflects the full context being carried, so the
    // page treats the last usage seen as the conversation's current size.
    if (round.usage) ctx.emit({ type: 'usage', usage: round.usage });
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
    const loadedImages = [];   // images produced by load_image this turn (injected after all tool results)
    for (const tc of round.tool_calls) {
      if (ctx.signal && ctx.signal.aborted) break;
      
      if (!tc.function?.name) {
        continue;
      }
      
      let parsedArgs = {};
      
      try {
        parsedArgs = JSON.parse(
          tc.function.arguments || '{}'
        );
      } catch (_) {}
      ctx.emit({ type: 'tool_started', tc });
      let toolOut;

      try {
        toolOut = await runTool(tc.function.name, parsedArgs, ctx);
      } catch (e) {
        toolOut = { result: 'Error: ' + (e && e.message || e) };
      }
      
      // 🚨 enforce size cap here
      const safeResult = truncateToolResult(toolOut.result);
      
      ctx.emit({
        type: 'tool_result',
        id: tc.id,
        result: safeResult,
      });
      
      const toolMsg = {
        role: 'tool',
        tool_call_id: tc.id,
        content: safeResult,
      };
      
      messages.push(toolMsg);

      ctx.emit({ type: 'message_added', message: toolMsg });

      if (toolOut && toolOut.image && toolOut.image.dataUrl) loadedImages.push(toolOut.image);
    }

    // Tool-role messages can't carry images on OpenAI-style /chat/completions, so
    // any image loaded this turn is threaded in as a user-role image_url block —
    // injected AFTER all tool results so parallel tool calls stay grouped.
    if (loadedImages.length) {
      // Cloud-visible: real data URLs (the model sees the pixels this round and on).
      messages.push({
        role: 'user',
        content: loadedImages.map(im => ({ type: 'image_url', image_url: { url: im.dataUrl } })),
      });
      // Persisted form: opfs:// refs (small, re-resolved by buildAgentConfig on later
      // turns/reloads) + a flag so the renderer skips it (the tool box shows the image).
      ctx.emit({
        type: 'message_added',
        message: {
          role: 'user',
          _loadedImage: true,
          content: loadedImages.map(im => ({ type: 'image_url', image_url: { url: 'opfs://' + im.path } })),
        },
      });
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

  // Unbounded event queue — agent pushes, stream pulls at its own pace
  const queue = [];
  let done = false;
  let notify = null; // resolves when new items are pushed

  function push(ev) {
    queue.push(enc.encode(JSON.stringify(ev) + '\n'));
    if (notify) { notify(); notify = null; }
  }

  // Run the agent completely independently of the stream
  const agentPromise = (async () => {
    const ctx = {
      emit: push,
      signal: abortCtl.signal,
      origin: config.origin || '',
    };
    try {
      await runAgent(config, ctx);
    } catch (e) {
      push({ type: 'error', message: (e && e.message) || String(e), status: e && e.status });
    } finally {
      done = true;
      if (notify) { notify(); notify = null; }
    }
  })();

  const stream = new ReadableStream({
    async pull(controller) {
      // Drain everything currently in the queue
      while (queue.length > 0) {
        controller.enqueue(queue.shift());
      }
      // If agent is done and queue is empty, close
      if (done && queue.length === 0) {
        controller.close();
        return;
      }
      // Otherwise wait for the next push() before pull() is called again
      await new Promise(r => { notify = r; });
      while (queue.length > 0) {
        controller.enqueue(queue.shift());
      }
      if (done && queue.length === 0) {
        controller.close();
      }
    },
    cancel() {
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

// One-shot tool runner. Lets the page-side wllama agent loop execute ANY tool
// through the SAME runTool() the main agent loop uses (run_python, OPFS file
// tools, artifacts, skills, …) — so there's no second implementation to drift,
// and run_python still gets the shared Pyodide here. Mirrors handlePy.
async function handleTool(req) {
  let payload;
  try { payload = await req.json(); }
  catch (e) { return jsonErr(400, 'bad request body: ' + e.message); }
  const { name, args, conversation_file_name } = payload || {};
  if (!name) return jsonErr(400, 'missing "name"');
  const ctx = { _conversation_file_name: conversation_file_name || 'unknown', emit: () => {} };
  let out;
  try { out = await runTool(name, args || {}, ctx); }
  catch (e) { out = { result: 'Error: ' + (e && e.message || e) }; }
  return new Response(JSON.stringify({
    result: truncateToolResult((out && out.result) || ''),
    artifacts: (out && out.artifacts) || null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

// Serve an OPFS file over HTTP. HTML files get the postMessage resize script
// injected so the page-side resize listener can autosize the artifact iframe.
async function handleOpfs(path) {
  // Strip query string before parsing path, but keep it for checking download flag
  const [pathOnly, query] = path.split('?');
  const opfsPath = decodeURIComponent(pathOnly.slice(pathOnly.indexOf('/opfs/') + '/opfs/'.length));
  const forceDownload = query && new URLSearchParams(query).get('download') === '1';
  // In prod the host page is cross-origin isolated (COOP=same-origin, COEP=credentialless).
  // A nested iframe is *blocked* unless its own response also carries COEP — credentialless
  // gives nested navigables no relaxation — so without this every artifact dies with
  // "NOT-SET cross-origin-embedder-policy". We synthesize these responses, so stamp the
  // policy here. credentialless (matching the host page) lets artifacts still pull no-cors
  // CDN images/fonts; same-origin CORP is the matching resource policy. One stamp covers
  // the artifact iframe, the OPFS file viewer, and the side panel — they all route here.
  const isolation = {
    'Cross-Origin-Embedder-Policy': 'credentialless',
    'Cross-Origin-Resource-Policy': 'same-origin',
  };
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
      return new Response(text, { headers: { 'Content-Type': 'text/html', 'Cache-Control': 'no-store', ...isolation } });
    }
    const headers = { 'Content-Type': ct, 'Cache-Control': 'no-store', ...isolation };
    if (forceDownload) headers['Content-Disposition'] = 'attachment';
    return new Response(bytes, { headers });
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

async function tool_write_file({ path, content, _conv }) {
  if (!path) return { result: 'Error: path is required.' };
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');

  try {
    const root = await opfsRoot();
  
    const parts = norm.split('/').filter(Boolean);
    const name = parts.pop();
  
    let dir = root;
  
    for (const p of parts) {
      dir = await dir.getDirectoryHandle(p, {
        create: false,
      });
    }
  
    try {
      await dir.getFileHandle(name);
      // It already exists — don't overwrite. Hand back the current content (like
      // opening it in an editor) so the model edits in place with edit_file
      // instead of rewriting it or saving a renamed copy.
      let existing = '';
      try { existing = new TextDecoder().decode(await opfsReadBytes(norm)); } catch (_) {}
      const CAP = 12000;
      const shown = existing.length > CAP
        ? existing.slice(0, CAP) + `\n…(truncated; ${existing.length} bytes total — use read_file to page the rest)`
        : existing;
      return {
        result: `${norm} already exists — NOT overwritten. To change it, use edit_file (do NOT rewrite the whole file or save a renamed copy like ${name.replace(/(\.[^.]*)?$/, '_v2$1')}). Its current content:\n\n${shown}`,
      };
    } catch (e) {
      if (e.name !== 'NotFoundError') {
        throw e;
      }
    }
  } catch (_) {
    // parent directory may not exist yet
  }
  
  try {
    await opfsWriteBytes(norm, new TextEncoder().encode(content || ''));
    // Sync the new OPFS file into Pyodide's MEMFS so run_python can see it
    // immediately without needing a separate syncfs pass. Runs inside withPy
    // to avoid racing with a concurrent run_python call on the same interpreter.
    if (py && _nativefs) {
      await withPy(() => new Promise((resolve) => {
        try { py.FS.syncfs(true, (err) => {
          if (err) console.warn('[sandpie-sw] syncfs after write_file failed:', err);
          resolve();
        }); }
        catch (e) { console.warn('[sandpie-sw] syncfs after write_file failed:', e); resolve(); }
      }));
    }
    // Track provenance: which conversation created this file
    try {
      const root = await navigator.storage.getDirectory();
      let fh;
      try { fh = await root.getFileHandle('conv2file_index.json'); }
      catch (_) { fh = await root.getFileHandle('conv2file_index.json', { create: true }); }
      const writable = await fh.createWritable({ keepExistingData: true });
      let map = {};
      try { map = JSON.parse(await (await fh.getFile()).text()); } catch (_) {}
      if (!map[norm]) map[norm] = { conversations: [], count: 0 };
      if (_conv && !map[norm].conversations.includes(_conv)) map[norm].conversations.push(_conv);
      map[norm].count++;
      await writable.write(JSON.stringify(map, null, 2));
      await writable.close();
    } catch (_) {}

    return { result: `Created: ${norm} (${new Blob([content]).size} bytes)` };
  } catch (e) { return { result: `Write failed: ${e.message}` }; }
}

// --- edit_file matching ----------------------------------------------------
// Forgiving substring replacement so a tiny whitespace/line-ending drift in
// old_str doesn't fail the edit (which is what pushes the model to rewrite the
// whole file). Tries, in order: exact → line-ending-normalized (CRLF/CR↔LF) →
// trailing-whitespace-tolerant whole-line match. On failure returns the match
// count + line numbers, or the closest lines, so the model can retry precisely.
// Pure + side-effect-free → unit-testable. Returns {updated} | {error}.
function _matchEol(orig, lf) { return /\r\n/.test(orig) ? lf.replace(/\n/g, '\r\n') : lf; }
function _lineNosOf(text, str) {
  const out = []; let i = -1;
  while (str && (i = text.indexOf(str, i + 1)) !== -1) out.push(text.slice(0, i).split('\n').length);
  return out;
}
function _closestLines(fileLines, oldLines) {
  const target = (oldLines.find(l => l.trim()) || '').trim();
  if (!target) return [];
  const pre = (a, b) => { let n = 0; while (n < a.length && n < b.length && a[n] === b[n]) n++; return n; };
  const scored = [];
  fileLines.forEach((l, i) => {
    const t = l.trim(); if (!t) return;
    const score = t === target ? 1e9 : (t.includes(target) || target.includes(t)) ? 1e6 : pre(t, target);
    if (score >= 6) scored.push({ i, t, score });
  });
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, 5).map(s => `  line ${s.i + 1}: ${s.t.slice(0, 120)}`);
}
function applyEdit(current, oldStr, newStr) {
  // 1) exact (function replacement so $ in newStr stays literal)
  let nos = _lineNosOf(current, oldStr);
  if (nos.length === 1) return { updated: current.replace(oldStr, () => newStr) };
  if (nos.length > 1)   return { error: `old_str matches ${nos.length} times (lines ${nos.join(', ')}) — add surrounding context so it matches exactly one place.` };
  // 2) line-ending-normalized
  const curLF = current.replace(/\r\n?/g, '\n');
  const oldLF = oldStr.replace(/\r\n?/g, '\n');
  const newLF = newStr.replace(/\r\n?/g, '\n');
  nos = _lineNosOf(curLF, oldLF);
  if (nos.length === 1) return { updated: _matchEol(current, curLF.replace(oldLF, () => newLF)), note: 'matched ignoring line endings' };
  if (nos.length > 1)   return { error: `old_str matches ${nos.length} times (lines ${nos.join(', ')}) — add surrounding context so it matches exactly one place.` };
  // 3) trailing-whitespace-tolerant, whole-line anchored
  const fileLines = curLF.split('\n'), oldLines = oldLF.split('\n');
  const rstrip = s => s.replace(/[ \t]+$/, '');
  const fN = fileLines.map(rstrip), oN = oldLines.map(rstrip);
  const hits = [];
  for (let i = 0; i + oN.length <= fN.length; i++) {
    let ok = true;
    for (let j = 0; j < oN.length; j++) if (fN[i + j] !== oN[j]) { ok = false; break; }
    if (ok) hits.push(i);
  }
  if (hits.length === 1) {
    const i = hits[0];
    const merged = fileLines.slice(0, i).concat(newLF.split('\n'), fileLines.slice(i + oldLines.length)).join('\n');
    return { updated: _matchEol(current, merged), note: 'matched ignoring trailing whitespace' };
  }
  if (hits.length > 1) return { error: `old_str matches ${hits.length} places (ignoring trailing whitespace), at lines ${hits.map(i => i + 1).join(', ')} — add surrounding context to disambiguate.` };
  // 4) not found → near-miss help
  const near = _closestLines(fileLines, oldLines);
  return { error: 'old_str not found (tried exact, line-ending, and trailing-whitespace-tolerant matching). Read the file and copy the exact text into old_str.' + (near.length ? '\nClosest lines in the file:\n' + near.join('\n') : '') };
}

async function tool_edit_file({ path, old_str, new_str = '' }) {
  if (!path)    return { result: 'Error: path is required.' };
  if (!old_str) return { result: 'Error: old_str is required.' };
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  let current;
  try {
    current = new TextDecoder().decode(await opfsReadBytes(norm));
  } catch { return { result: `File not found: ${norm}. Use write_file to create it.` }; }
  const res = applyEdit(current, old_str, new_str);
  if (res.error) return { result: res.error };
  try {
    await opfsWriteBytes(norm, new TextEncoder().encode(res.updated));
    if (py && _nativefs) {
      await withPy(() => new Promise((resolve) => {
        try { py.FS.syncfs(true, (err) => {
          if (err) console.warn('[sandpie-sw] syncfs after edit_file failed:', err);
          resolve();
        }); }
        catch (e) { console.warn('[sandpie-sw] syncfs after edit_file failed:', e); resolve(); }
      }));
    }
    return { result: `Edited: ${norm}${res.note ? ' (' + res.note + ')' : ''}` };
  } catch (e) { return { result: `Edit failed: ${e.message}` }; }
}
