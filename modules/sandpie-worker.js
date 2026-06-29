// sandpie-worker.js — Dedicated Web Worker for Pyodide + tools + agent loop.
// Replaces the service worker for all compute: Python, file tools, and the
// cloud LLM agent loop. Communicate via postMessage:
//   IN  {type:'agent', id, config}          → agent run; sends {type:'event', id, event} back
//   IN  {type:'tool', id, name, args, ...}  → single tool; sends {type:'tool_result', id, ...}
//   IN  {type:'abort', id}                  → abort a running agent
//   IN  {type:'dbx-token', ...}             → update Dropbox context
//   IN  {type:'opfs-changed', paths}        → sync new OPFS files into Pyodide MEMFS
//   IN  {type:'opfs-removed', paths}        → drop paths from Pyodide MEMFS
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
const _origConsole = { log: console.log, warn: console.warn, error: console.error, info: console.info };
console.log   = (...args) => { try { _relayLog('log',   args); } catch (_) {} _origConsole.log.apply(console, args); };
console.warn  = (...args) => { try { _relayLog('warn',  args); } catch (_) {} _origConsole.warn.apply(console, args); };
console.error = (...args) => { try { _relayLog('error', args); } catch (_) {} _origConsole.error.apply(console, args); };
console.info  = (...args) => { try { _relayLog('info',  args); } catch (_) {} _origConsole.info.apply(console, args); };

self.addEventListener('error', (ev) => {
  console.error('uncaught error:', ev.message, 'at', (ev.filename || '?') + ':' + (ev.lineno || '?'), ev.error && ev.error.stack ? '\n' + ev.error.stack : '');
});
self.addEventListener('unhandledrejection', (ev) => {
  const r = ev.reason;
  console.error('unhandled rejection:', r && (r.stack || r.message) || String(r));
});

// Dropbox context pushed from the page so search (cloud leg) + hydration can call the API.
let _dbxCtx = null;

// Dehydrated-Dropbox state (opt-in JIT hydration). When on, the page stops
// bulk-downloading and pushes the cloud INDEX here; files are fetched lazily on
// first touch. See the hydration helpers further down. Default off ⇒ no change.
let _dehydrated = false;
let _dbxIndex = null;                 // { [rel]: {name,kind,path,size,rev,cloudMtime} } or null
let _dbxExempt = ['sandpie/conversations', 'sandpie/agents', 'sandpie/skills'];   // app metadata, always eager; sandpie/scripts|artifacts|memory stay dehydratable

// Track active agent AbortControllers so abort messages can cancel them.
const _agentAborts = new Map();

const WORKER_VERSION = '2.17.0-web-search';
console.log('[sandpie-worker] boot — version=' + WORKER_VERSION);

// ---- message protocol entry point ------------------------------------------
self.addEventListener('message', async (event) => {
  const data = event.data;
  if (!data) return;

  if (data.type === 'flush-logs') {
    for (const msg of _logBuffer) { try { self.postMessage(msg); } catch (_) {} }
    return;
  }

  if (data.type === 'dbx-token') {
    _dbxCtx = { token: data.token, pathRoot: data.pathRoot || null, workingRoot: data.workingRoot || '' };
    _dehydrated = !!data.dehydrated;
    return;
  }

  if (data.type === 'dbx-index') {
    _dbxIndex = data.index || null;
    if (Array.isArray(data.exempt) && data.exempt.length) _dbxExempt = data.exempt;
    return;
  }

  if (data.type === 'opfs-removed' && Array.isArray(data.paths)) {
    if (!py) return;
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
    if (!py || !_nativefs) return;
    await withPy(async () => {
      for (const rel of data.paths) {
        const full = '/files/' + String(rel).replace(/^\/+/, '');
        try {
          const bytes = await opfsReadBytes(rel);
          const dir = full.substring(0, full.lastIndexOf('/'));
          if (dir && dir !== '/files') { try { py.FS.mkdirTree(dir); } catch (_) {} }
          py.FS.writeFile(full, bytes);
        } catch (e) {
          console.warn('[sandpie-worker] opfs-changed sync failed for', rel, e);
        }
      }
    });
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
      localterm: config.localterm || null,
    };
    try {
      await runAgent(config, ctx);
    } catch (e) {
      ctx.emit({ type: 'error', message: (e && e.message) || String(e), status: e && e.status });
    } finally {
      _agentAborts.delete(id);
    }
    return;
  }

  if (data.type === 'tool') {
    const { id, name, args, conversation_file_name, localterm } = data;
    const ctx = { _conversation_file_name: conversation_file_name || 'unknown', emit: () => {}, localterm: localterm || null };
    let out;
    try { out = await runTool(name, args || {}, ctx); }
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
    return;
  }
});

// ============================================================
// Pyodide — lazy-loaded. Web Workers can call importScripts()
// from inside async functions (unlike Service Workers where it
// must be at top-level synchronous evaluation time).
// ============================================================
const PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v0.29.4/full/';
let _pyodideJsLoaded = false;
let py = null;
let pyInitPromise = null;
let _nativefs = null;

async function initPyodide() {
  if (py) return py;
  if (pyInitPromise) return pyInitPromise;
  if (!_pyodideJsLoaded) {
    try {
      console.log('[sandpie-worker] importing pyodide.js…');
      importScripts(PYODIDE_INDEX + 'pyodide.js');
      console.log('[sandpie-worker] importing pyodide.asm.js…');
      importScripts(PYODIDE_INDEX + 'pyodide.asm.js');
      _pyodideJsLoaded = true;
      console.log('[sandpie-worker] pyodide bootstrap scripts loaded');
    } catch (e) {
      console.warn('[sandpie-worker] pyodide bootstrap failed:', e);
      throw new Error('Pyodide unavailable: failed to load pyodide.js — check network. ' + (e && e.message || e));
    }
  }
  pyInitPromise = (async () => {
    try {
      const p = await loadPyodide({ indexURL: PYODIDE_INDEX });
      try {
        const opfsRootDir = await navigator.storage.getDirectory();
        _nativefs = await p.mountNativeFS('/files', opfsRootDir);
        p.runPython('import os; os.chdir("/files")');
        p.FS.trackingDelegate = Object.assign(p.FS.trackingDelegate || {}, _fsTrackingDelegate());
        try { p.runPython(_HYDRATE_AUDIT_PY); } catch (e) { console.warn('[sandpie-worker] hydrate audit hook install failed:', e); }
        console.log('[sandpie-worker] OPFS mounted at /files (cwd); FS tracking installed');
      } catch (e) {
        _nativefs = null;
        console.warn('[sandpie-worker] OPFS mount failed (Python /files unavailable):', e);
      }
      py = p;
      return p;
    } catch (e) {
      pyInitPromise = null;
      throw e;
    }
  })();
  return pyInitPromise;
}

function resetPyodide(reason) {
  console.warn('[sandpie-worker] resetting Pyodide:', reason);
  py = null;
  pyInitPromise = null;
  _nativefs = null;
}

function isPyodideFatal(e, msg, stderr) {
  if (!msg && !stderr.trim()) return true;
  if (typeof WebAssembly !== 'undefined' && e instanceof WebAssembly.RuntimeError) return true;
  const sig = ((msg || '') + ' ' + (stderr || '')).toLowerCase();
  if (sig.includes('aborted(')) return true;
  if (sig.includes('runtimeerror: abort(')) return true;
  if (sig.includes('memory access out of bounds')) return true;
  if (sig.includes('out of memory') && sig.includes('wasm')) return true;
  return false;
}

let _pyMutex = Promise.resolve();
function withPy(fn) {
  const next = _pyMutex.then(fn, fn);
  _pyMutex = next.catch(() => {});
  return next;
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
async function opfsWriteBytes(path, bytes) {
  const { parts, name } = splitPath(path);
  const dir = await opfsResolveDir(parts, true);
  const handle = await dir.getFileHandle(name, { create: true });
  const w = await handle.createWritable();
  await w.write(bytes);
  await w.close();
}

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
  return _dbxExempt.some(p => { const pl = String(p).toLowerCase(); return r === pl || r.startsWith(pl + '/'); });
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
function _dbxHeaders(json) {
  const h = { Authorization: 'Bearer ' + (_dbxCtx && _dbxCtx.token) };
  if (json) h['Content-Type'] = 'application/json';
  if (_dbxCtx && _dbxCtx.pathRoot) h['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: _dbxCtx.pathRoot });
  return h;
}
// Async hydration (file tools): get_temporary_link RPC → GET the link → OPFS.
// Mirrors dropbox-full.js download() — the documented CORS-enabled browser path.
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
// Synchronous hydration for Pyodide: two blocking XHRs (get_temporary_link, then
// GET), writing THROUGH Pyodide's FS so the just-opened file is visible inline
// without a syncfs round-trip. Exposed to Python via the run_python audit hook.
function _syncDownloadBytes(cloudPath) {
  const x1 = new XMLHttpRequest();
  x1.open('POST', 'https://api.dropboxapi.com/2/files/get_temporary_link', false);
  const h = _dbxHeaders(true);
  for (const k in h) x1.setRequestHeader(k, h[k]);
  x1.send(JSON.stringify({ path: cloudPath }));
  if (x1.status !== 200) throw new Error('get_temporary_link ' + x1.status);
  const link = JSON.parse(x1.responseText).link;
  const x2 = new XMLHttpRequest();
  x2.open('GET', link, false);
  let ab = true;
  try { x2.responseType = 'arraybuffer'; } catch (_) { ab = false; }   // workers allow this on sync XHR; main thread does not
  if (!ab) { try { x2.overrideMimeType('text/plain; charset=x-user-defined'); } catch (_) {} }
  x2.send();
  if (x2.status !== 200) throw new Error('download ' + x2.status);
  if (ab && x2.response) return new Uint8Array(x2.response);
  const s = x2.responseText, b = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i) & 0xff;
  return b;
}
self._sandpie_hydrate_sync = function (pathStr) {
  try {
    if (!_dehydrated || !_dbxIndex || !_dbxCtx || !py) return;
    let full = String(pathStr || '');
    if (!full) return;
    if (!full.startsWith('/')) full = '/files/' + full.replace(/^files\//, '');
    if (!full.startsWith('/files/')) return;
    const rel = full.slice('/files/'.length).replace(/^\/+/, '');
    if (!rel || _relExempt(rel)) return;
    try { if (py.FS.analyzePath(full).exists) return; } catch (_) {}
    const entry = _dbxIndex[rel];
    if (!entry || entry.kind !== 'file') return;
    const bytes = _syncDownloadBytes(_cloudPathFor(rel, entry));
    const dir = full.slice(0, full.lastIndexOf('/'));
    if (dir && dir !== '/files') { try { py.FS.mkdirTree(dir); } catch (_) {} }
    py.FS.writeFile(full, bytes);
    _hydratedSet.add(rel);
  } catch (e) { console.warn('[sandpie-worker] sync hydrate failed:', pathStr, (e && e.message) || e); }
};
// Python preamble: an audit hook that faults in /files paths on open(). Bound
// once after Pyodide init. Skips stdlib (absolute non-/files) and pseudo-paths.
const _HYDRATE_AUDIT_PY = `
import sys
from js import _sandpie_hydrate_sync as __sp_hydrate
def __sp_audit(event, args):
    if event == 'open' and args:
        p = args[0]
        if isinstance(p, str) and (p.startswith('/files') or (p[:1] not in ('/', '<'))):
            try: __sp_hydrate(p)
            except Exception: pass
sys.addaudithook(__sp_audit)
`;
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
// Flushing last session's hydrated copies is now PAGE-side (dropbox-full
// dehydratePurge() on boot) — it knows sync state, so it can skip files with
// unsynced edits. The worker no longer persists a manifest or wipes on boot.

// ---- Event-driven OPFS write-back (FS.trackingDelegate) --------------------
let _capActive = false;
const _capTouched = new Set();
const _capDeleted = new Set();
function _capReset() { _capActive = false; _capTouched.clear(); _capDeleted.clear(); }

function _opfsRelFromFs(fsPath) {
  const p = String(fsPath);
  if (p === '/files' || p === '/files/') return null;
  if (p.startsWith('/files/')) return p.slice('/files/'.length);
  return null;
}

function _fsTrackingDelegate() {
  const touch = (fsPath) => {
    if (!_capActive) return;
    const rel = _opfsRelFromFs(fsPath); if (rel == null) return;
    _capTouched.add(rel); _capDeleted.delete(rel);
  };
  const drop = (fsPath) => {
    if (!_capActive) return;
    const rel = _opfsRelFromFs(fsPath); if (rel == null) return;
    _capDeleted.add(rel); _capTouched.delete(rel);
  };
  return {
    onWriteToFile:   (path) => touch(path),
    onMakeDirectory: (path) => touch(path),
    onDeletePath:    (path) => drop(path),
    onMovePath:      (oldPath, newPath) => { drop(oldPath); touch(newPath); },
  };
}

async function flushCaptureToOpfs() {
  const removed = [], written = [];
  for (const rel of _capDeleted) { if (await swOpfsDelete(rel, true)) removed.push(rel); }
  for (const rel of _capTouched) {
    const full = '/files/' + rel;
    let st; try { st = py.FS.stat(full); } catch (_) { continue; }
    try {
      if (py.FS.isDir(st.mode)) await opfsResolveDir(rel.split('/').filter(Boolean), true);
      else { await opfsWriteBytes(rel, py.FS.readFile(full)); written.push(rel); }
    } catch (e) { console.warn('[sandpie-worker] OPFS write-back failed:', rel, e); }
  }
  return { removed, written };
}

function _swRmTree(full) {
  let entries = []; try { entries = py.FS.readdir(full); } catch (_) { return; }
  for (const name of entries) {
    if (name === '.' || name === '..') continue;
    const child = full + '/' + name;
    try { const st = py.FS.stat(child); if (py.FS.isDir(st.mode)) _swRmTree(child); else py.FS.unlink(child); } catch (_) {}
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
    console.log('[sandpie-worker] deleted from OPFS:', relPath);
    return true;
  } catch (e) {
    if (e.name !== 'NotFoundError') console.warn('[sandpie-worker] failed to delete from OPFS:', relPath, e);
    return false;
  }
}

// ============================================================
// Tool implementations
// ============================================================
const MAX_TOOL_RESULT_BYTES = 30 * 1024;
function truncateToolResult(result) {
  if (typeof result !== 'string') { try { result = JSON.stringify(result); } catch { result = String(result); } }
  const bytes = new TextEncoder().encode(result);
  if (bytes.length <= MAX_TOOL_RESULT_BYTES) return result;
  return new TextDecoder().decode(bytes.slice(0, MAX_TOOL_RESULT_BYTES)) + "\n\n[truncated: tool result exceeded 30kB]";
}

function sourceFromTraceback(tb, code) {
  if (!tb || !code) return '';
  const lines = code.split('\n');
  const re = /File "(?:<exec>|<string>|<unknown>)", line (\d+)/g;
  const nums = []; let m;
  while ((m = re.exec(tb))) { const n = +m[1]; if (n >= 1 && n <= lines.length) nums.push(n); }
  if (!nums.length) return '';
  const focus = nums[nums.length - 1];
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
  // The audit hook only hydrates files the script open()s at RUNTIME; the entry
  // script itself is read here before Python starts, so it needs the same
  // try-OPFS-then-hydrate-on-miss dance as read_file/load_image. Otherwise a
  // dehydrated (cloud-only) script reports "could not read".
  try {
    let bytes;
    try { bytes = await opfsReadBytes(normPath); }
    catch (miss) {
      if (_indexEntry(normPath)) { await hydrateAsync(normPath); bytes = await opfsReadBytes(normPath); }
      else throw miss;
    }
    code = new TextDecoder().decode(bytes);
  }
  catch (e) { return { result: `Error: could not read /files/${normPath}: ${e.message}.` }; }
  return withPy(async () => {
    let p;
    try { p = await initPyodide(); }
    catch (e) { return { result: 'Error loading Pyodide: ' + (e && e.message || e) }; }
    let stdout = '', stderr = '';
    try {
      p.setStdout({ batched: s => { stdout += s + '\n'; } });
      p.setStderr({ batched: s => { stderr += s + '\n'; } });
      if (normPath) {
        self._sandpie_argv = [normPath, ...scriptArgs];
        try { p.runPython('import sys\nfrom js import _sandpie_argv\nsys.argv = list(_sandpie_argv.to_py())'); } catch (_) {}
      }
      try { await p.loadPackagesFromImports(code); } catch (_) {}
      _capReset(); _capActive = true;
      await p.runPythonAsync(code);
      _capActive = false;
      let removedPaths = [], writtenPaths = [];
      if (_nativefs) {
        try { ({ removed: removedPaths, written: writtenPaths } = await flushCaptureToOpfs()); }
        catch (e) { console.warn('[sandpie-worker] OPFS write-back after run_python failed:', e); }
      }
      if (removedPaths.length || writtenPaths.length) {
        try {
          if (removedPaths.length) self.postMessage({ type: 'forward-to-page', payload: { type: 'opfs-deleted-by-python', paths: removedPaths } });
          if (writtenPaths.length) self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: writtenPaths } });
        } catch (_) {}
      }
      let out = stdout.trimEnd();
      if (stderr.trim()) out += (out ? '\n' : '') + '--- stderr ---\n' + stderr.trimEnd();
      return { result: out || '(no output)' };
    } catch (e) {
      let msg = '';
      if (e != null) {
        if (typeof e === 'string') msg = e;
        else if (e.message) msg = e.message;
        else { try { const s = e.toString(); if (s && s !== '[object Object]') msg = s; } catch (_) {} }
      }
      const tail = stderr.trim() ? '\n--- stderr ---\n' + stderr.trimEnd() : '';
      if (isPyodideFatal(e, msg, stderr)) {
        resetPyodide(msg || stderr.trim() || 'empty exception');
        return { result: 'FATAL: Pyodide runtime crashed and has been reset. All in-memory state (globals, imports, function defs) is gone — the next run_python call will start a clean interpreter. DO NOT retry the failing code as-is; re-do any imports/setup first.' + (msg ? '\n--- crash signal ---\n' + msg : '') + tail };
      }
      const src = sourceFromTraceback(msg, code);
      return { result: 'Error: ' + (msg || 'unknown (no message)') + (src ? '\n\n--- ' + normPath + ' (around the error) ---\n' + src : '') + tail };
    } finally {
      _capActive = false;
      try { p && p.setStdout({}); } catch (_) {}
      try { p && p.setStderr({}); } catch (_) {}
    }
  });
}

// ============================================================




async function tool_show_artifact({ path }, ctx) {
  if (!path) return { result: 'Error: path is required.' };
  const clean = String(path).replace(/^\/+/, '');
  try { await opfsReadBytes(clean); return { result: 'artifact:' + clean }; }
  catch (e) {
    if (_indexEntry(clean)) { try { await hydrateAsync(clean); return { result: 'artifact:' + clean }; } catch (_) {} }
    return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' };
  }
}

// Images are embedded as base64 in the NEXT model request. The upstream gateway
// (NPAW ai-balancer.npaw.com) caps the WHOLE request body at ~1 MB and that limit
// is NOT raisable, so instead of rejecting a large image we downscale + re-encode
// it to fit (see _compressImageToFit / tool_load_image). All three limits sit
// UNDER ~1 MB, leaving headroom for the system prompt + tools + history that share
// the body with the image(s):
//   • IMAGE_MAX_B64_BYTES    — per image: the compress-to-fit target (base64).
//   • IMAGE_CONVO_B64_BUDGET — cumulative images across the conversation (≈ 1 image).
//   • MAX_REQUEST_BYTES      — hard ceiling on the WHOLE serialized body, just under
//                              the gateway's cap; an over-size request then fails
//                              fast client-side with a clear message, not a 413.
const IMAGE_MAX_B64_BYTES    = 700 * 1024;   // per image: compress-to-fit target
const IMAGE_CONVO_B64_BUDGET = 900 * 1024;   // cumulative images across the conversation
const MAX_REQUEST_BYTES      = 950 * 1024;   // whole serialized body (just under NPAW's ~1 MB cap)
const _fmtBytes = n => n >= 1024 * 1024 ? (n / (1024 * 1024)).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB';
// Base64 bytes of images already present in the request messages (real data: URLs
// only; opfs:// placeholders cost nothing).
function _imageB64InMessages(msgs) {
  let n = 0;
  for (const m of (msgs || [])) {
    const c = m && m.content;
    if (!Array.isArray(c)) continue;
    for (const p of c) {
      if (p && p.type === 'image_url' && p.image_url && typeof p.image_url.url === 'string' && p.image_url.url.startsWith('data:')) n += p.image_url.url.length;
    }
  }
  return n;
}

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
  const clean = String(path).replace(/^\/+/, '');
  try {
    let bytes;
    try { bytes = await opfsReadBytes(clean); }
    catch (miss) {
      if (_indexEntry(clean)) { await hydrateAsync(clean); bytes = await opfsReadBytes(clean); }
      else throw miss;
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
    // Cumulative conversation budget (on the FINAL, possibly-compressed size).
    const budget = ctx && ctx._imageBudget;
    if (budget && budget.used + estB64 > budget.total) {
      return { result: `Error: "${clean}" was NOT loaded — even compressed, the conversation's images would total ${_fmtBytes(budget.used + estB64)}, over the ${_fmtBytes(budget.total)} image budget (the upstream gateway caps the whole request near 1 MB). Load only the one image you need, reuse an image already shown above, or continue in a fresh conversation.` };
    }
    if (budget) budget.used += estB64;   // reserve before encoding so the next call in the batch sees it
    let bin = ''; const CHUNK = 0x8000;
    for (let i = 0; i < bytes.length; i += CHUNK) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    const dataUrl = 'data:' + mime + ';base64,' + btoa(bin);
    return { result: 'image:' + clean, image: { path: clean, dataUrl } };
  } catch (e) { return { result: 'Error: file not found: ' + clean + '. Write it with run_python first.' }; }
}

async function tool_load_skill({ name }, ctx) {
  const n = String(name || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(n)) return { result: 'Error: invalid skill name "' + name + '". Use the exact name from the Skills section.' };
  const file = 'sandpie/skills/' + n + '/SKILL.md';
  let text;
  try { text = new TextDecoder().decode(await opfsReadBytes(file)); }
  catch (e) { return { result: 'Error: could not read ' + file + ' — no such skill, or its ' + file + ' is missing.' }; }
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

async function tool_read_file({ path, offset, limit }) {
  const norm = normFilesPath(path);
  if (!norm) return { result: 'Error: path is required.' };
  let file;
  try { file = await _opfsGetFile(norm); }
  catch {
    if (_indexEntry(norm)) {
      try { await hydrateAsync(norm); file = await _opfsGetFile(norm); }
      catch (e) { return { result: `Error: ${norm} is in Dropbox but could not be fetched: ${(e && e.message) || e}` }; }
    } else { return { result: 'Error: file not found: ' + norm }; }
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
  return { result: buf.replace(/\n$/, '') };
}

async function tool_list_files({ path, pattern, recursive, scope }) {
  const rx = pattern ? globToRegExp(pattern) : null;
  const raw = (path == null) ? '' : String(path).trim();
  const connected = !!(_dbxCtx && _dbxCtx.token);

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
async function _dropboxSearchPaths(query, searchPath, filenameOnly, fileExtensions) {
  const { token, pathRoot } = _dbxCtx;
  const headers = { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' };
  if (pathRoot) headers['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: pathRoot });
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
  if (!page.length) return `No more cloud matches for "${query}" in ${scope} — ${totalStr} total; offset ${off} is past the end.`;
  if (total <= PAGE && off === 0) return `${total} cloud file(s) matching "${query}" in ${scope} (outside your workspace — copy one in with copy_to_workspace("<path>"), then read_file/load_image it):\n` + page.join('\n');
  const end = off + page.length;
  const hints = [];
  if (end < total) hints.push(`call search again with offset:${end} for the next ${Math.min(PAGE, total - end)}`);
  if (r.hasMore && end >= total) hints.push(`>${total} matches total — narrow the path/term to reach the rest`);
  hints.push('or narrow the path/term for fewer, more relevant matches');
  return `${totalStr} cloud files match "${query}" in ${scope} — showing ${off + 1}-${end} (outside your workspace — copy one in with copy_to_workspace("<path>"), then read_file/load_image it):\n` + page.join('\n') + `\n(${hints.join('; ')}.)`;
}
async function _dropboxListFolder(folderPath, recursive) {
  const { token, pathRoot } = _dbxCtx;
  const headers = { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' };
  if (pathRoot) headers['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: pathRoot });
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

// Unified search. Path-aware: inside the working root it greps local files and
// (when dehydrated) merges Dropbox content-search hits for un-downloaded files;
// an absolute Dropbox path OUTSIDE the working root does a pure cloud search.
async function tool_search({ pattern, path, include, files_only, ignore_case, offset, scope }) {
  if (!pattern) return { result: 'Error: pattern (a regular expression) is required.' };
  let rx; try { rx = new RegExp(pattern, ignore_case === false ? '' : 'i'); }
  catch (e) { return { result: 'Error: invalid regex: ' + (e && e.message || e) }; }

  const connected = !!(_dbxCtx && _dbxCtx.token);
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
        const r = await _dropboxSearchPaths(lits.join(' '), cloudScope, false, _globExtensions(include));
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

// ---- copy_to_workspace — server-side copy a file from elsewhere in the user's
// Dropbox INTO the working root so the LLM can use it. READ-ONLY on the source.
// Only offered when Dropbox is connected (gated in tools.js toolDefs).
async function tool_copy_to_workspace({ src, dest }) {
  if (!_dbxCtx || !_dbxCtx.token) return { result: 'Error: Dropbox is not connected.' };
  const from = (src == null ? '' : String(src)).trim();
  if (!from) return { result: 'Error: "src" (an absolute Dropbox path, e.g. from search) is required.' };
  if (!from.startsWith('/')) return { result: 'Error: "src" must be an absolute Dropbox path like "/R+D+I/reports/q1.pdf" (use the path search returned).' };
  const wr = (_dbxCtx.workingRoot || '').replace(/\/+$/, '');
  if (!wr) return { result: 'Error: your workspace folder is not resolved yet — try again in a moment.' };
  let rel = (dest != null && String(dest).trim())
    ? String(dest).trim().replace(/^\/+/, '').replace(/^files\//, '').replace(/\/+$/, '')
    : from.split('/').filter(Boolean).pop();
  if (!rel || rel.split('/').some(s => s === '..')) return { result: 'Error: invalid "dest".' };
  const headers = { Authorization: 'Bearer ' + _dbxCtx.token, 'Content-Type': 'application/json' };
  if (_dbxCtx.pathRoot) headers['Dropbox-API-Path-Root'] = JSON.stringify({ '.tag': 'root', root: _dbxCtx.pathRoot });
  let res;
  try { res = await fetch('https://api.dropboxapi.com/2/files/copy_v2', { method: 'POST', headers, body: JSON.stringify({ from_path: from, to_path: wr + '/' + rel, autorename: true }) }); }
  catch (e) { return { result: 'Error reaching Dropbox: ' + (e && e.message || e) }; }
  if (!res.ok) { const txt = await res.text().catch(() => ''); return { result: 'Copy failed (' + res.status + '): ' + txt.slice(0, 400) }; }
  const meta = ((await res.json().catch(() => ({}))) || {}).metadata || {};
  const finalPath = meta.path_display || (wr + '/' + rel);
  const finalRel = _relUnderRoot(finalPath) || rel;
  if (meta['.tag'] === 'folder') {
    if (_dehydrated) {
      if (!_dbxIndex) _dbxIndex = {};
      _dbxIndex[finalRel] = { name: meta.name || finalRel.split('/').pop(), kind: 'folder', path: finalPath, cloudMtime: meta.server_modified };
    }
    return { result: `Copied folder into your workspace as ${finalRel}/. Its files appear after the next sync; then use list_files / read_file on them.` };
  }

  // Download the copied file into OPFS immediately so the LLM can work on it.
  let dlOk = false;
  try {
    const tlRes = await fetch('https://api.dropboxapi.com/2/files/get_temporary_link', { method: 'POST', headers, body: JSON.stringify({ path: finalPath }) });
    if (tlRes.ok) {
      const { link } = await tlRes.json();
      const dl = await fetch(link, { method: 'GET' });
      if (dl.ok) {
        const bytes = new Uint8Array(await dl.arrayBuffer());
        await opfsWriteBytes(finalRel, bytes);
        dlOk = true;

        // 1. Record in cloud index so it's known as synced
        if (_dehydrated) {
          if (!_dbxIndex) _dbxIndex = {};
          _dbxIndex[finalRel] = { name: meta.name || finalRel.split('/').pop(), kind: 'file', path: finalPath, size: meta.size, rev: meta.rev, cloudMtime: meta.server_modified };
        }

        // 2. Notify the page (dropbox-full.js) so file viewer renders it
        _reportHydrated(finalRel);

        // 3. If Pyodide is running, sync the new file into MEMFS so run_python sees it
        if (py && _nativefs) {
          await withPy(async () => {
            const full = '/files/' + finalRel;
            const dir = full.substring(0, full.lastIndexOf('/'));
            if (dir && dir !== '/files') { try { py.FS.mkdirTree(dir); } catch (_) {} }
            py.FS.writeFile(full, bytes);
          });
        }
      }
    }
  } catch (e) {
    console.warn('[sandpie-worker] copy_to_workspace download failed:', e);
  }

  let extra = dlOk
    ? ' — downloaded and ready to use'
    : ' (Dropbox copy succeeded, but download to workspace failed — will appear after next sync)';
  return { result: `Copied into your workspace as ${finalRel}${meta.size != null ? ' (' + meta.size + ' bytes)' : ''}${extra}. Use read_file or run_python on "${finalRel}".` };
}

const KNOWN_TOOLS = ['run_python','write_file','edit_file','read_file','list_files','search','copy_to_workspace','show_artifact','load_skill','load_image','local_shell'];

async function unknownTool(name) {
  const n = String(name || '').trim().toLowerCase();
  if (/^[a-z0-9][a-z0-9_-]*$/.test(n)) {
    try { await opfsReadBytes('sandpie/skills/' + n + '/SKILL.md'); return { result: 'Error: "' + name + '" is a skill, not a tool. Call load_skill({"name":"' + n + '"}) to use it.' }; } catch {}
  }
  return { result: 'Error: unknown tool "' + name + '". Available tools: ' + KNOWN_TOOLS.join(', ') + '.' };
}

// local_shell — run a command on the user's OWN machine via the localterm helper
// (loopback /exec). Token comes from ctx.localterm (passed in the run config; the
// worker has no localStorage). Graceful, non-looping errors when the helper is down.
async function tool_local_shell({ command, timeout }, ctx) {
  const cmd = (command == null) ? '' : String(command);
  if (!cmd.trim()) return { result: 'Error: "command" is required.' };
  const lt = ctx && ctx.localterm;
  if (!lt || !lt.token) return { result: 'Error: the local terminal is not available — the localterm helper is not running or not paired. Tell the user to start it (sandpie Terminal panel → Download), then retry ONCE. Do not retry repeatedly.' };
  const port = lt.port || 8771;
  let to = parseInt(timeout, 10); if (!(to > 0)) to = 60; if (to > 300) to = 300;
  let r;
  try {
    r = await fetch(`http://127.0.0.1:${port}/exec?token=${encodeURIComponent(lt.token)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cmd, timeout: to }),
      signal: ctx && ctx.signal,
    });
  } catch (e) {
    return { result: `Error: could not reach the localterm helper on 127.0.0.1:${port} (${(e && e.message) || e}). It is likely not running — tell the user to start it (Terminal panel) and STOP, do not retry in a loop.` };
  }
  if (!r.ok) {
    const hint = r.status === 403 ? ' Token rejected (helper may have restarted) — ask the user to reopen sandpie from the helper to re-pair.' : '';
    return { result: `Error: localterm helper returned HTTP ${r.status}.${hint}` };
  }
  let d; try { d = await r.json(); } catch { return { result: 'Error: bad response from the localterm helper.' }; }
  let out = d.stdout || '';
  if (d.stderr) out += (out ? '\n' : '') + '[stderr]\n' + d.stderr;
  if (d.timedOut) out += `\n[timed out after ${to}s — command killed]`;
  out += `\n[exit code ${d.code != null ? d.code : '?'}]`;
  const CAP = 20000;
  if (out.length > CAP) out = out.slice(0, CAP) + `\n…(output truncated; ${out.length} bytes total)`;
  return { result: out.trim() };
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
    case 'search':        return tool_search(args, ctx);
    case 'search_dropbox':return tool_search(args, ctx);   // legacy alias → unified search
    case 'copy_to_workspace': return tool_copy_to_workspace(args, ctx);
    case 'write_file':    return tool_write_file({...args, _conv: convFileName}, ctx);
    case 'edit_file':     return tool_edit_file(args, ctx);
    case 'local_shell':   return tool_local_shell(args, ctx);
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
  if (e instanceof TypeError) return true;
  return false;
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

async function streamOneRoundWithRetry(reqUrl, headers, body, ctx) {
  const BACKOFF_MS = [1000, 2000, 5000, 10000];
  let authRefreshed = false;   // at most one transparent token re-mint per round
  for (let attempt = 0; ; attempt++) {
    try {
      if (attempt > 0) ctx.emit({ type: 'info', message: null });
      ctx._hermesMode = body && body._hermesMode;
      return await streamOneRound(reqUrl, headers, body, ctx);
    } catch (e) {
      if (ctx.signal?.aborted) throw e;
      // Managed session token expired → re-mint from the still-valid SSO cookie
      // and retry once, transparently (no user-facing message). Gated to the
      // managed provider (ctx._authRefreshUrl set) and to one attempt: a fresh
      // token that still 401s means the SSO session itself is gone — let it surface.
      if (e && e.status === 401 && ctx._authRefreshUrl && !authRefreshed) {
        authRefreshed = true;
        const tok = await _refreshAuthToken(ctx._authRefreshUrl);
        if (tok) {
          headers['Authorization'] = 'Bearer ' + tok;   // mutate in place → later rounds reuse it
          self.postMessage({ type: 'managed-token-refreshed', token: tok });
          continue;                                      // immediate retry with the fresh token
        }
      }
      if (!isRetryableError(e)) throw e;
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
      ctx.emit({ type: 'info', message: `Provider error (${e.status || 'network'}) — retrying in ${delay / 1000}s… (attempt ${attempt + 1})` });
      await swSleep(delay, ctx.signal);
    }
  }
}

function parseLeakedToolCalls(text) {
  const toolCalls = [];
  if (typeof text !== 'string' || text.indexOf('<|tool_call') === -1) return { toolCalls, stripped: text };
  const callRe = /<\|tool_call_begin\|>\s*functions\.([A-Za-z0-9_.\-]+):(\d+)\s*<\|tool_call_argument_begin\|>([\s\S]*?)<\|tool_call_end\|>/g;
  let m;
  while ((m = callRe.exec(text)) !== null) {
    const [, name, idx, rawArgs] = m;
    toolCalls.push({ id: 'call_' + idx, type: 'function', function: { name, arguments: (rawArgs || '').trim() } });
  }
  const stripped = text.replace(/<\|tool_calls_section_begin\|>[\s\S]*?<\|tool_calls_section_end\|>/g, '').replace(/<\|tool_calls_section_begin\|>[\s\S]*$/g, '').trim();
  return { toolCalls, stripped };
}

function scrubFramingTokens(s) { return typeof s === 'string' ? s.replace(/<\|[\s\S]*?\|>/g, '') : s; }

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
  let idx = 0;
  while ((m = callRe.exec(text)) !== null) {
    try {
      const parsed = JSON.parse(m[1]);
      if (parsed && parsed.name) {
        toolCalls.push({
          id: 'call_hermes_' + (idx++),
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
            id: 'call_hermes_' + (idx++),
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

function normalizeToolArgs(raw) {
  const s0 = raw == null ? '' : String(raw);
  if (s0.indexOf('<|') === -1) { try { JSON.parse(s0); return s0; } catch (_) {} }
  const s = scrubFramingTokens(s0).trim(); if (!s) return '{}';
  const tryParse = (t) => { try { return JSON.stringify(JSON.parse(t)); } catch (_) { return null; } };
  const escStray = (t) => t.replace(/\\(?!["\\/bfnrtu])/g, '\\\\');
  let out = tryParse(s) || tryParse(escStray(s));
  if (out) return out;
  const obj = firstBalancedObject(s);
  if (obj) { out = tryParse(obj) || tryParse(escStray(obj)); if (out) return out; }
  return '{}';
}

async function streamOneRound(reqUrl, headers, body, ctx) {
  const payload = JSON.stringify(body);
  // Total-body guard: fail fast (and clearly) BEFORE the server returns a cryptic
  // 413. Measures real UTF-8 bytes. Not retryable (size won't change on retry).
  let bytes; try { bytes = new Blob([payload]).size; } catch (_) { bytes = payload.length; }
  if (bytes > MAX_REQUEST_BYTES) {
    throw new Error(`Request too large: ${_fmtBytes(bytes)} exceeds the ~${_fmtBytes(MAX_REQUEST_BYTES)} limit (the upstream gateway caps the request body near 1 MB and that can't be raised). The conversation is holding too much to send (usually images) — remove some, load only the one(s) you need, or start a fresh conversation.`);
  }
  const res = await fetch(reqUrl, { method: 'POST', headers, body: payload, signal: ctx.signal });
  if (!res.ok) {
    const text = (await res.text()).slice(0, 300);
    const hint = res.status === 413 ? ` (request body was ${_fmtBytes(bytes)}; the upstream gateway rejected it as too large — its ~1 MB cap can't be raised, so send fewer/smaller images or trim the conversation)` : '';
    throw Object.assign(new Error(res.status + ': ' + text + hint), { status: res.status });
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', content = '', reasoningText = '';
  const toolCalls = []; let usage = null, sawDone = false;
  while (!sawDone) {
    const { done, value } = await reader.read(); if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n'); buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6); if (data === '[DONE]') { sawDone = true; break; }
      try {
        const parsed = JSON.parse(data);
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
  let keptToolCalls = toolCalls.filter(tc => tc && tc.id && tc.function && tc.function.name);
  if (!keptToolCalls.length) {
    let parsed = parseLeakedToolCalls(content);
    if (parsed.toolCalls.length) { keptToolCalls = parsed.toolCalls; content = parsed.stripped; }
    else if (!content.trim()) { parsed = parseLeakedToolCalls(reasoningText); if (parsed.toolCalls.length) keptToolCalls = parsed.toolCalls; }
  }
  if (!keptToolCalls.length && ctx._hermesMode) {
    const hermesParsed = parseHermesToolCalls(content);
    if (hermesParsed.toolCalls.length) { keptToolCalls = hermesParsed.toolCalls; content = hermesParsed.stripped; }
  }
  for (const tc of keptToolCalls) {
    if (!tc || !tc.function) continue;
    if (typeof tc.function.name === 'string') tc.function.name = scrubFramingTokens(tc.function.name).trim().replace(/^functions\./, '');
    tc.function.arguments = normalizeToolArgs(tc.function.arguments);
  }
  return { content, tool_calls: keptToolCalls, usage };
}

async function runAgent(config, ctx) {
  const convFileName = config.conversation_file_name || 'unknown';
  ctx._conversation_file_name = convFileName;
  const messages = config.messages.slice();
  // Cumulative image budget for load_image — seeded from images already in the
  // conversation, then incremented per load so a batch of parallel load_image
  // calls in one turn can't pile up and blow the context / request body.
  ctx._imageBudget = { total: IMAGE_CONVO_B64_BUDGET, used: _imageB64InMessages(messages) };
  // Managed provider only: URL to silently re-mint an expired session token on a
  // 401 (see streamOneRoundWithRetry). null/absent for personal providers.
  ctx._authRefreshUrl = config.authRefreshUrl || null;
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
    if (config.maxTokens != null) reqBody[config.reasoningEffort ? 'max_completion_tokens' : 'max_tokens'] = config.maxTokens;
    if (config.temperature != null) reqBody.temperature = config.temperature;
    if (config.reasoningEffort) reqBody.reasoning_effort = config.reasoningEffort;
    const round = await streamOneRoundWithRetry(config.url, config.headers, reqBody, ctx);
    ctx.emit({ type: 'round_end', content: round.content, tool_calls: round.tool_calls });
    if (round.usage) ctx.emit({ type: 'usage', usage: round.usage });
    if (!round.tool_calls.length) {
      if (round.content) {
        const m = { role: 'assistant', content: round.content };
        messages.push(m); ctx.emit({ type: 'message_added', message: m });
      }
      break;
    }
    const asstMsg = { role: 'assistant', content: round.content, tool_calls: round.tool_calls };
    messages.push(asstMsg); ctx.emit({ type: 'message_added', message: asstMsg });
    const loadedImages = [];
    for (const tc of round.tool_calls) {
      if (ctx.signal && ctx.signal.aborted) break;
      if (!tc.function?.name) continue;
      let parsedArgs = {}; try { parsedArgs = JSON.parse(tc.function.arguments || '{}'); } catch (_) {}
      ctx.emit({ type: 'tool_started', tc });
      let toolOut;
      try { toolOut = await runTool(tc.function.name, parsedArgs, ctx); }
      catch (e) { toolOut = { result: 'Error: ' + (e && e.message || e) }; }
      const safeResult = truncateToolResult(toolOut.result);
      ctx.emit({ type: 'tool_result', id: tc.id, result: safeResult });
      const toolMsg = { role: 'tool', tool_call_id: tc.id, content: safeResult };
      messages.push(toolMsg); ctx.emit({ type: 'message_added', message: toolMsg });
      if (toolOut && toolOut.image && toolOut.image.dataUrl) loadedImages.push(toolOut.image);
    }
    if (loadedImages.length) {
      messages.push({ role: 'user', content: loadedImages.map(im => ({ type: 'image_url', image_url: { url: im.dataUrl } })) });
      ctx.emit({ type: 'message_added', message: { role: 'user', _loadedImage: true, content: loadedImages.map(im => ({ type: 'image_url', image_url: { url: 'opfs://' + im.path } })) } });
    }
  }
  ctx.emit({ type: 'agent_done' });
}

// ============================================================
// write_file / edit_file
// ============================================================
async function tool_write_file({ path, content, _conv }) {
  if (!path) return { result: 'Error: path is required.' };
  const norm = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  try {
    const root = await opfsRoot();
    const parts = norm.split('/').filter(Boolean); const name = parts.pop();
    let dir = root;
    for (const p of parts) { dir = await dir.getDirectoryHandle(p, { create: false }); }
    try {
      await dir.getFileHandle(name);
      let existing = ''; try { existing = new TextDecoder().decode(await opfsReadBytes(norm)); } catch (_) {}
      const CAP = 12000;
      const shown = existing.length > CAP ? existing.slice(0, CAP) + `\n…(truncated; ${existing.length} bytes total — use read_file to page the rest)` : existing;
      return { result: `${norm} already exists — NOT overwritten. To change it, use edit_file (do NOT rewrite the whole file or save a renamed copy like ${name.replace(/(\.[^.]*)?$/, '_v2$1')}). Its current content:\n\n${shown}` };
    } catch (e) { if (e.name !== 'NotFoundError') throw e; }
  } catch (_) {}
  try {
    await opfsWriteBytes(norm, new TextEncoder().encode(content || ''));
    // Notify the page so sync state marks this file dirty (prevents sync deletion).
    self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [norm] } });
    if (py && _nativefs) {
      await withPy(() => new Promise((resolve) => {
        try { py.FS.syncfs(true, (err) => { if (err) console.warn('[sandpie-worker] syncfs after write_file failed:', err); resolve(); }); }
        catch (e) { console.warn('[sandpie-worker] syncfs after write_file failed:', e); resolve(); }
      }));
    }
    return { result: `Created: ${norm} (${new Blob([content]).size} bytes)` };
  } catch (e) { return { result: `Write failed: ${e.message}` }; }
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

async function tool_edit_file({ path, old_str, new_str = '' }) {
  if (!path) return { result: 'Error: path is required.' };
  if (!old_str) return { result: 'Error: old_str is required.' };
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
    // Notify the page so sync state marks this file dirty (prevents sync deletion).
    self.postMessage({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [norm] } });
    if (py && _nativefs) {
      await withPy(() => new Promise((resolve) => {
        try { py.FS.syncfs(true, (err) => { if (err) console.warn('[sandpie-worker] syncfs after edit_file failed:', err); resolve(); }); }
        catch (e) { console.warn('[sandpie-worker] syncfs after edit_file failed:', e); resolve(); }
      }));
    }
    return { result: `Edited: ${norm}${res.note ? ' (' + res.note + ')' : ''}` };
  } catch (e) { return { result: `Edit failed: ${e.message}` }; }
}
