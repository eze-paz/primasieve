// sandpie-sw.js — Service Worker that runs the LLM agent loop end-to-end.
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
//   POST /sandpie-py { code, argv, placeholdersList } → run python once

// Version stamp so you can tell at a glance whether a fresh SW build
// is actually running. Logged on every SW boot (install, activate, and
// any cold-start after idle termination). If you don't see this in the
// console after a hard refresh, the browser is still serving a stale
// SW — Application → Service Workers → Update will force a refresh.
const SW_VERSION = '1.2.4';
console.log('[sandpie-sw] boot — version=' + SW_VERSION);

// Silence one specific Pyodide-emitted warning that spams the console
// on every SW boot. Pyodide calls self.addEventListener('message', ...)
// from inside loadPyodide(), which is past the SW's initial-evaluation
// window — Chrome warns "Event handler of 'message' event must be added
// on the initial evaluation of worker script." once per addEventListener
// call. The handler still works while the SW is alive (the only thing
// Chrome's note actually disables is "wake the terminated SW via a
// 'message' postMessage", which we don't use — the page wakes us via
// fetch to /sandpie-agent). So the warning is informational noise.
// Filter ONLY this exact string so unrelated warnings still surface.
const _origWarn = console.warn;
console.warn = function (...args) {
  if (typeof args[0] === 'string' && args[0].indexOf("Event handler of 'message' event must be added on the initial evaluation") !== -1) {
    return;
  }
  _origWarn.apply(console, args);
};
// Pyodide's package-loading logger sometimes uses console.log directly
// (in addition to the messageCallback option). Filter those exact patterns
// so the SW console isn't flooded with "Loading micropip…" / "Loaded X" /
// "already loaded" / "No new packages to load" / "Attempted install" lines
// on every run_python call. Other console.log usage passes through.
const _origLog = console.log;
const _PYO_NOISE = [
  /^Loading [\w\-., ]+$/,
  /^Loaded [\w\-., ]+$/,
  /already loaded from default channel$/,
  /^No new packages to load$/,
  /^Attempted install$/,
];
console.log = function (...args) {
  const s = args[0];
  if (typeof s === 'string') {
    for (const re of _PYO_NOISE) if (re.test(s)) return;
  }
  _origLog.apply(console, args);
};

// importScripts() in a Service Worker is only legal during the initial
// synchronous evaluation of the SW script (i.e. right here at the top),
// or synchronously inside the install event handler. Calling it lazily
// from inside a fetch handler / async function throws "failed to load"
// regardless of network state.
//
// Pyodide's loadPyodide() internally calls importScripts() a SECOND time
// to fetch pyodide.asm.js. That second call is past the legal window and
// fails with the same "failed to load" error. So we pre-load BOTH scripts
// here at the top — Pyodide detects pyodide.asm.js is already in scope
// and skips its own importScripts call.
//
// Cost: ~500KB pyodide.js + ~1MB pyodide.asm.js on SW boot (HTTP-cached
// after first time, so usually instant). The heavy ~10MB WASM payload
// is still loaded lazily by loadPyodide() via fetch (not importScripts),
// so we don't pay that until run_python is actually called.
//
// Wrapped in try so the SW still installs successfully on offline /
// blocked-CDN networks — non-python tools keep working; run_python
// then reports Pyodide unavailable.
const PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
let _pyodideJsLoaded = false;
try {
  importScripts(PYODIDE_INDEX + 'pyodide.js');
  importScripts(PYODIDE_INDEX + 'pyodide.asm.js');
  _pyodideJsLoaded = true;
} catch (e) {
  console.warn('[sandpie-sw] Pyodide bootstrap scripts failed to load:', e);
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
async function initPyodide() {
  if (py) return py;
  if (pyInitPromise) return pyInitPromise;
  if (!_pyodideJsLoaded) {
    throw new Error('Pyodide bootstrap script unavailable (CDN unreachable when SW installed). Reload the page after going online to retry.');
  }
  pyInitPromise = (async () => {
    // pyodide.js was imported at the top of this file (must happen at SW
    // script parse time — SWs forbid importScripts past that point). Now
    // just instantiate the runtime; loadPyodide is in the global scope.
    // Do NOT pass stdout/stderr to loadPyodide here. Earlier we did, to
    // silence the loader chatter, but that no-op stuck around even after
    // per-call setStdout() and made print() output silently disappear
    // ("(no output)" returned even when the script had clearly printed).
    // Loader noise is handled at the right layer instead:
    //   * `messageCallback: () => {}` on loadPackagesFromImports (below)
    //   * console.log filter at SW top-level (catches anything that leaks
    //     through to console.log directly).
    py = await loadPyodide({ indexURL: PYODIDE_INDEX });
    try { py.FS.mkdir('/files'); } catch (_) {}
    return py;
  })();
  return pyInitPromise;
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
async function opfsList(prefix) {
  prefix = prefix || '';
  const out = [];
  const walk = async (dir, p) => {
    for await (const [n, h] of dir.entries()) {
      const full = p ? p + '/' + n : n;
      if (full === '_conversations' || full.startsWith('_conversations/')) continue;
      if (h.kind === 'file') out.push(full);
      else await walk(h, full);
    }
  };
  const start = prefix ? await opfsResolveDir(prefix.split('/').filter(Boolean)) : await opfsRoot();
  await walk(start, prefix.replace(/^\/+|\/+$/g, ''));
  return out.sort();
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

// ---- Pyodide /files ↔ OPFS sync ----
async function syncOpfsToPy(p, placeholdersList) {
  const rmTree = (full) => {
    let stat;
    try { stat = p.FS.stat(full); } catch (_) { return; }
    if (p.FS.isDir(stat.mode)) {
      for (const name of p.FS.readdir(full)) {
        if (name === '.' || name === '..') continue;
        rmTree(full + '/' + name);
      }
      if (full !== '/files') p.FS.rmdir(full);
    } else {
      p.FS.unlink(full);
    }
  };
  rmTree('/files');
  try { p.FS.mkdir('/files'); } catch (_) {}
  const files = await opfsList();
  const hydrated = new Set(files);
  const ensureDirs = (segs) => {
    let cur = '/files';
    for (const s of segs) {
      cur += '/' + s;
      try { p.FS.mkdir(cur); } catch (_) {}
    }
    return cur;
  };
  for (const rel of files) {
    const segs = rel.split('/');
    const fn = segs.pop();
    const dir = ensureDirs(segs);
    p.FS.writeFile(dir + '/' + fn, await opfsReadBytes(rel));
  }
  const placeholders = new Set();
  for (const rel of (placeholdersList || [])) {
    if (hydrated.has(rel)) continue;
    const segs = rel.split('/');
    const fn = segs.pop();
    const dir = ensureDirs(segs);
    try {
      p.FS.writeFile(dir + '/' + fn, new Uint8Array(0));
      placeholders.add(rel);
    } catch (_) {}
  }
  return placeholders;
}

function bytesEqual(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

async function syncPyToOpfs(p, placeholders) {
  const pyFiles = new Set();
  const walk = (full, rel) => {
    for (const name of p.FS.readdir(full)) {
      if (name === '.' || name === '..') continue;
      const childFull = full + '/' + name;
      const childRel = rel ? rel + '/' + name : name;
      const stat = p.FS.stat(childFull);
      if (p.FS.isFile(stat.mode)) pyFiles.add(childRel);
      else walk(childFull, childRel);
    }
  };
  walk('/files', '');
  const filled = [];
  const written = [];
  for (const rel of pyFiles) {
    const newBytes = p.FS.readFile('/files/' + rel);
    if (placeholders.has(rel) && newBytes.length === 0) continue;
    let oldBytes = null;
    try { oldBytes = await opfsReadBytes(rel); } catch (_) {}
    if (oldBytes && bytesEqual(oldBytes, newBytes)) continue;
    await opfsWriteBytes(rel, newBytes);
    written.push(rel);
    if (placeholders.has(rel)) filled.push(rel);
  }
  return { filled, written };
}

const OPEN_PATCH = `
import builtins, os
if getattr(builtins.open, '__name__', None) == '_sandpie_open':
    if hasattr(builtins, '_original_open'):
        builtins.open = builtins._original_open
if hasattr(builtins, '_original_open'):
    _real_open = builtins._original_open
else:
    _real_open = builtins.open
    builtins._original_open = _real_open
try:
    from js import _sandpie_cloud_paths
    _sandpie_cloud_set = set(_sandpie_cloud_paths.to_py())
except Exception:
    _sandpie_cloud_set = set()
def _sandpie_normalize(path):
    s = str(path)
    if s.startswith('/files/'): s = s[len('/files/'):]
    while s.startswith('./'): s = s[2:]
    return s.lstrip('/')
def _sandpie_open(path, *args, **kwargs):
    n = _sandpie_normalize(path)
    if n in _sandpie_cloud_set:
        raise FileNotFoundError(
            f"[Errno 2] {path!s} is a sandpie cloud placeholder. "
            f"Call fetch_file({{'path': '{n}'}}) to download it first, then re-run. "
            f"If you meant a host path (outside /files/), use the read_file tool instead."
        )
    return _real_open(path, *args, **kwargs)
builtins.open = _sandpie_open
`;

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

// Append corrective guidance for common Pyodide foot-guns so the model's next
// retry has actionable info instead of just a raw traceback. Small models
// (Gemma e2b etc.) re-emit the same broken pattern when given only Python's
// error text — a HINT block with a worked example breaks the loop.
function pythonErrorHint(errText) {
  const hints = [];
  // asyncio.run() inside an already-running loop — common because models default
  // to wrapping coroutines in asyncio.run() instead of using top-level await.
  if (/asyncio\.run\(\) cannot be called from a running event loop/i.test(errText)
      || /coroutine .* was never awaited/i.test(errText)) {
    hints.push(
      'HINT: Pyodide already runs inside an event loop, so asyncio.run() is forbidden here. ' +
      'Use top-level await directly. Also note pyfetch() returns a FetchResponse object, not the body — you must call .string() or .bytes() on it. ' +
      'Correct pattern for fetching a URL and saving to OPFS:\n' +
      '    from pyodide.http import pyfetch\n' +
      '    r = await pyfetch("https://example.com")\n' +
      '    body = await r.string()           # or: await r.bytes() for binary\n' +
      '    open("example.html", "w").write(body)\n' +
      '    print("saved", len(body), "bytes")\n' +
      'No asyncio.run, no async def wrapper needed — just await at the top of the snippet.'
    );
  }
  // open() on something that isn't a path (e.g. open(FetchResponse, "w")).
  if (/expected str, bytes or os\.PathLike/i.test(errText)) {
    hints.push(
      'HINT: open() needs a filename string. You probably passed a FetchResponse or other object. ' +
      'For URLs use: r = await pyfetch(url); body = await r.string(); open("file","w").write(body).'
    );
  }
  return hints.length ? '\n--- hint ---\n' + hints.join('\n') : '';
}

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
  let p;
  try { p = await initPyodide(); }
  catch (e) { return { result: 'Error loading Pyodide: ' + (e && e.message || e) }; }
  let stdout = '', stderr = '';
  const artifacts = [];
  try {
    p.setStdout({ batched: s => { stdout += s + '\n'; } });
    p.setStderr({ batched: s => { stderr += s + '\n'; } });
    const placeholders = await syncOpfsToPy(p, ctx.placeholdersList || []);
    p.runPython('import os; os.chdir("/files")');
    self._sandpie_cloud_paths = [...placeholders];
    try { p.runPython(OPEN_PATCH); } catch (_) {}
    if (normPath) {
      self._sandpie_argv = [normPath, ...scriptArgs];
      try { p.runPython('import sys\nfrom js import _sandpie_argv\nsys.argv = list(_sandpie_argv.to_py())'); } catch (_) {}
    }
    self._sandpieDisplay = (html) => artifacts.push(html);
    try { p.runPython(DISPLAY_PATCH); } catch (_) {}
    // messageCallback: () => {} silences the per-call "Loading X…" /
    // "Loaded X" logger spam that pyodide emits on every package-check.
    try { await p.loadPackagesFromImports(code, { messageCallback: () => {}, errorCallback: () => {} }); } catch (_) {}
    await p.runPythonAsync(code);
    const sync = await syncPyToOpfs(p, placeholders);
    let out = stdout.trimEnd();
    if (stderr.trim()) {
      out += (out ? '\n' : '') + '--- stderr ---\n' + stderr.trimEnd();
      out += pythonErrorHint(stderr + ' ' + stdout);
    }
    if (artifacts.length) {
      const note = '(rendered ' + artifacts.length + ' artifact' + (artifacts.length === 1 ? '' : 's') + ' via IPython.display — visible to the user)';
      out = out ? out + '\n' + note : note;
    }
    return { result: out || '(no output)', artifacts, filled: sync.filled, written: sync.written };
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
    if (!msg && !stderr.trim()) {
      // Fatal interpreter death — reset for next call.
      py = null; pyInitPromise = null;
      return { result: 'FATAL: Pyodide runtime crashed and has been reset. All in-memory state (globals, imports, function defs) is gone — the next run_python call will start a clean interpreter. DO NOT retry the failing code as-is; re-do any imports/setup first.', artifacts };
    }
    const hint = pythonErrorHint((msg || '') + ' ' + stderr);
    return { result: 'Error: ' + (msg || 'unknown (no message)') + tail + hint, artifacts };
  } finally {
    try { p && p.setStdout({}); } catch (_) {}
    try { p && p.setStderr({}); } catch (_) {}
  }
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

// Extract the first balanced JSON object from a string, ignoring any
// trailing garbage. Some models emit non-JSON control tokens after the
// closing brace of tool_call arguments (e.g. `<|tool_calls_section_end|>`,
// partial reasoning text, raw `<think>` blocks). The leak corrupts BOTH
// our local JSON.parse AND the next round's request body — the upstream
// LLM API re-parses arguments internally and rejects the whole request
// with a 400 if it's malformed. So we sanitize here at the source.
function extractFirstJsonObject(s) {
  s = String(s == null ? '' : s);
  let depth = 0, start = -1, inStr = false, esc = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (start === -1) {
      if (c === '{') { start = i; depth = 1; }
      continue;
    }
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === '"') { inStr = false; }
    } else {
      if (c === '"') { inStr = true; }
      else if (c === '{') depth++;
      else if (c === '}') {
        depth--;
        if (depth === 0) {
          try { return JSON.parse(s.slice(start, i + 1)); } catch (_) { return {}; }
        }
      }
    }
  }
  return {};
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
    if (config.think) reqBody.think = true;
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
      // Sanitize args: strip trailing control tokens / reasoning leaks so
      // both this local execution AND the next round's request body have
      // a valid JSON `arguments` field. We OVERWRITE tc.function.arguments
      // (which already went into messages[] via push) so the message
      // record stays consistent with what we executed.
      const parsedArgs = extractFirstJsonObject(tc.function.arguments);
      tc.function.arguments = JSON.stringify(parsedArgs);
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
        placeholdersList: config.placeholdersList || [],
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
// Same shape as the prior sandpie-sw.js implementation.
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
  const ctx = { placeholdersList: args.placeholdersList || [] };
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
