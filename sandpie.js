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
//        { type:"tool_result", id, result, artifacts? }
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
//   W3  fetch event router — three intercepted paths:             [line ~36]
//         /sandpie-agent  → handleAgent
//         /sandpie-stream → handleStream  (legacy single-round SSE proxy)
//         /sandpie-py     → handlePy      (one-shot run_python)
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
//             → dispatches to tool_run_python / tool_shell /
//               tool_read_file / tool_write_file / tool_fetch_file
//           emit tool_result (with optional artifacts)
//           emit message_added (tool)
//         next iteration
//       emit agent_done
//
//   T1  tool_run_python: lazy initPyodide (single shared interp),
//       exec user code, return stdout + artifacts. NO automatic
//       OPFS sync — Python operates in plain Pyodide MEMFS. The LLM
//       uses read_file / write_file / fetch_file for actual file I/O.
//   T2  tool_shell:      POST proxyBase/shell                     [line ~330]
//   T3  tool_read_file:  GET  proxyBase/file?path=                [line ~344]
//   T4  tool_write_file: POST proxyBase/file?path=                [line ~347]
//   T5  tool_fetch_file: Dropbox download via SW dbx helper       [line ~355]
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
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'sandpie-sw-flush-logs') {
    for (const msg of _swLogBuffer) {
      try { event.source.postMessage(msg); } catch (_) {}
    }
  }
});

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

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  const path = url.pathname;
  if (path.endsWith('/sandpie-agent'))  return event.respondWith(handleAgent(event.request));
  if (path.endsWith('/sandpie-stream')) return event.respondWith(handleStream(event.request));
  if (path.endsWith('/sandpie-py'))     return event.respondWith(handlePy(event.request));
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
        console.log('[sandpie-sw] OPFS mounted at /files');
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

// Extract the missing file path from a Pyodide PythonError whose underlying
// Python exception is FileNotFoundError. Standard repr in the JS-side error
// message is:
//   FileNotFoundError: [Errno 2] No such file or directory: 'path'
// Returns the OPFS-relative path (no leading '/', no '/files/' prefix) so
// it can be passed straight to tool_fetch_file. Returns null if the error
// is anything other than that shape — caller treats null as "don't retry".
function _extractMissingPath(e) {
  const msg = (e && (e.message || String(e))) || '';
  if (!/FileNotFoundError/.test(msg)) return null;
  const m = msg.match(/No such file or directory:\s*['"]([^'"]+)['"]/);
  if (!m) return null;
  let p = m[1];
  p = p.replace(/^\/+/, '').replace(/^files\//, '');
  return p || null;
}

// =============================================================================
// withPy — single-flight serializer for tool_run_python calls.
// =============================================================================
// The SW holds ONE Pyodide interpreter shared across all convs. tool_run_python
// mutates interpreter-global state (setStdout/setStderr batched callbacks
// closed over caller-local accumulators, self._sandpieDisplay, self._sandpie_argv,
// the DISPLAY_PATCH IPython redirect). Two concurrent callers would trample
// these and one would return garbage — withPy serializes the critical section.
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

const DISPLAY_PATCH = `
def _sandpie_display(*objs, **kwargs):
    import base64
    try:
        import js
    except Exception:
        return
    for obj in objs:
        html = None
        try:
            if hasattr(obj, '_repr_html_'):
                html = obj._repr_html_()
            if html is None and hasattr(obj, '_repr_svg_'):
                html = obj._repr_svg_()
            if html is None and hasattr(obj, '_repr_png_'):
                d = obj._repr_png_()
                if isinstance(d, (bytes, bytearray)):
                    d = base64.b64encode(d).decode()
                html = '<img src="data:image/png;base64,' + d + '">'
            if html is None and hasattr(obj, '_repr_jpeg_'):
                d = obj._repr_jpeg_()
                if isinstance(d, (bytes, bytearray)):
                    d = base64.b64encode(d).decode()
                html = '<img src="data:image/jpeg;base64,' + d + '">'
        except Exception as e:
            html = '<pre>display error: ' + str(e) + '</pre>'
        if html is None:
            s = str(obj).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html = '<pre>' + s + '</pre>'
        try:
            js._sandpieDisplay(html)
        except Exception:
            pass
try:
    import IPython.display as _ipd
    _ipd.display = _sandpie_display
except Exception:
    pass
`;

// ============================================================
// Tool implementations (run inside the SW).
// ============================================================

async function tool_run_python({ code, path, args }, ctx) {
  if (!code && !path) return { result: 'Error: provide either "code" or "path".' };
  if (code && path) return { result: 'Error: provide either "code" or "path", not both.' };
  const scriptArgs = Array.isArray(args) ? args.map(String) : [];
  let normPath = '';
  if (path) {
    normPath = String(path).replace(/^\/+/, '').replace(/^files\//, '');
    try {
      code = new TextDecoder().decode(await opfsReadBytes(normPath));
    } catch (e) {
      return { result: `Error: could not read /files/${normPath}: ${e.message}.` };
    }
  }
  // Serialize the interpreter-touching critical section so concurrent
  // run_python calls don't race on the shared interpreter's globals
  // (setStdout closures, IPython.display redirect, etc).
  return withPy(async () => {
    let p;
    try { p = await initPyodide(); }
    catch (e) { return { result: 'Error loading Pyodide: ' + (e && e.message || e) }; }
    let stdout = '', stderr = '';
    const artifacts = [];
    try {
      p.setStdout({ batched: s => { stdout += s + '\n'; } });
      p.setStderr({ batched: s => { stderr += s + '\n'; } });
      // Python environment: stdout/stderr capture + IPython.display →
      // artifacts redirect + optional argv for `path:` mode. /files is
      // mounted lazily via mountNativeFS at init — Python can use plain
      // open()/os.listdir/glob and it reads OPFS on demand. Files not
      // hydrated from Dropbox simply aren't present in /files (no
      // placeholder shim needed); LLM uses fetch_file to bring them in.
      if (normPath) {
        self._sandpie_argv = [normPath, ...scriptArgs];
        try { p.runPython('import sys\nfrom js import _sandpie_argv\nsys.argv = list(_sandpie_argv.to_py())'); } catch (_) {}
      }
      self._sandpieDisplay = (html) => artifacts.push(html);
      try { p.runPython(DISPLAY_PATCH); } catch (_) {}
      try { await p.loadPackagesFromImports(code); } catch (_) {}
      // Single-retry: if user code dies with FileNotFoundError on a path
      // that turns out to live in Dropbox, fetch_file it and re-run the
      // whole snippet once. The LLM never sees the failure-then-retry —
      // it just gets the successful result. Budget is 1 to avoid fetch
      // storms inside one call; subsequent missing files in the same
      // snippet surface to the LLM (it can run again, where they'd
      // already be local or trigger another single retry).
      let _retried = false;
      while (true) {
        try {
          await p.runPythonAsync(code);
          break;
        } catch (runErr) {
          if (_retried) throw runErr;
          const missing = _extractMissingPath(runErr);
          if (!missing || !ctx.dbxTokens) throw runErr;
          const fr = await tool_fetch_file({ path: missing }, ctx);
          if (typeof fr.result !== 'string' || fr.result.startsWith('Error')) throw runErr;
          // Re-sync OPFS into Pyodide's /files view so the just-fetched
          // file is now visible to open() / os.listdir on the retry.
          if (_nativefs) { try { await _nativefs.syncfs(); } catch (_) {} }
          // Discard partial output captured before the failing line so
          // the user sees a clean run, not an interleaving of attempts.
          stdout = '';
          stderr = '';
          _retried = true;
        }
      }
      // Flush any writes Python made into /files back to OPFS. No-op when
      // Python didn't touch the FS. Skipped (with a warning) if the mount
      // failed at init — Python had no /files to write to, nothing to flush.
      if (_nativefs) {
        try { await _nativefs.syncfs(); }
        catch (e) { console.warn('[sandpie-sw] syncfs after run_python failed:', e); }
      }
      let out = stdout.trimEnd();
      if (stderr.trim()) out += (out ? '\n' : '') + '--- stderr ---\n' + stderr.trimEnd();
      if (artifacts.length) {
        const note = '(rendered ' + artifacts.length + ' artifact' + (artifacts.length === 1 ? '' : 's') + ' via IPython.display — visible to the user)';
        out = out ? out + '\n' + note : note;
      }
      return { result: out || '(no output)', artifacts };
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
          artifacts,
        };
      }
      return { result: 'Error: ' + (msg || 'unknown (no message)') + tail, artifacts };
    } finally {
      try { p && p.setStdout({}); } catch (_) {}
      try { p && p.setStderr({}); } catch (_) {}
    }
  });
}

// shell / read_file / write_file all go through the cloud proxy at /shell.
// proxyBase is provided by the page (so the SW doesn't have to introspect
// page state) — typically `https://gasn2cloud.com` or empty for same-origin.
async function tool_shell(args, ctx) {
  const r = await fetch((ctx.proxyBase || '') + '/shell', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Origin': ctx.origin || '' },
    body: JSON.stringify(args),
  });
  const j = await r.json().catch(() => ({}));
  if (j.error) return { result: 'Error: ' + j.error };
  let out = (j.stdout || '');
  if (j.stderr) out += (out ? '\n' : '') + '--- stderr ---\n' + j.stderr;
  if (typeof j.code === 'number' && j.code !== 0) out += (out ? '\n' : '') + `[exit ${j.code}]`;
  return { result: out || '(no output)' };
}

async function tool_read_file(args, ctx) {
  return tool_shell({ cmd: `cat "${String(args.path).replace(/"/g, '\\"')}"`, cwd: args.cwd, timeout: args.timeout }, ctx);
}
async function tool_write_file(args, ctx) {
  // Best-effort: shell-escape and use `tee`. Caller can pass content_b64 for binary safety.
  const content = args.content || '';
  const b64 = btoa(unescape(encodeURIComponent(content)));
  const cmd = `printf '%s' "$(echo '${b64}' | base64 -d)" > "${String(args.path).replace(/"/g, '\\"')}"`;
  return tool_shell({ cmd, cwd: args.cwd, timeout: args.timeout }, ctx);
}

async function tool_fetch_file(args, ctx) {
  // Dropbox download. Requires tokens from page (no localStorage in SW).
  if (!ctx.dbxTokens) return { result: 'Error: Dropbox tokens not available in SW context (page did not provide them).' };
  const rel = String(args.path || '').replace(/^\/+/, '');
  if (!rel) return { result: 'Error: missing path' };
  try {
    const r = await fetch('https://content.dropboxapi.com/2/files/download', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + ctx.dbxTokens.access_token,
        'Dropbox-API-Arg': JSON.stringify({ path: '/' + rel }),
      },
    });
    if (!r.ok) return { result: `Error: dropbox returned ${r.status}: ${await r.text().catch(() => '')}` };
    const bytes = new Uint8Array(await r.arrayBuffer());
    await opfsWriteBytes(rel, bytes);
    return { result: `Hydrated ${rel} (${bytes.length} bytes)` };
  } catch (e) {
    return { result: 'Error: ' + (e && e.message || e) };
  }
}

async function runTool(name, args, ctx) {
  switch (name) {
    case 'run_python': return tool_run_python(args, ctx);
    case 'shell':      return tool_shell(args, ctx);
    case 'read_file':  return tool_read_file(args, ctx);
    case 'write_file': return tool_write_file(args, ctx);
    case 'fetch_file': return tool_fetch_file(args, ctx);
    default:           return { result: 'Error: unknown tool ' + name };
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
    const round = await streamOneRound(config.url, config.headers, reqBody, ctx);
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
      ctx.emit({ type: 'tool_result', id: tc.id, result: toolOut.result, artifacts: toolOut.artifacts || [] });
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
        proxyBase: config.proxyBase || '',
        origin: config.origin || '',
        dbxTokens: config.dbxTokens || null,
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

function jsonErr(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
