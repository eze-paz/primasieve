// sandpie/modules/pyodide-worker.js — Pyodide inside a PAGE-OWNED dedicated Web
// Worker. EXPERIMENTAL, currently wired ONLY for the LiteRT backend (see
// litertlm.js) as an A/B test against running Python in the service worker.
//
// WHY THIS EXISTS: run_python in the service worker hard-crashes — a Pyodide
// WASM abort terminates the SW thread and is UNcatchable (sandpie.js:37), and
// OPFS sync access handles (which mountNativeFS uses) are fragile/disallowed in
// service workers. When the SW thread dies mid-request, the page's awaited
// fetch('./sandpie-tool') never resolves → the UI freezes. A dedicated worker
// has its own memory context, reliable OPFS sync access handles, and is immune
// to the SW's idle termination. This file ports tool_run_python + its OPFS
// helpers from sandpie.js verbatim (minus SW-only bits).
//
// Protocol —
//   page → worker:  { type:'run', id, path, args }
//   worker → page:  { type:'result', id, result, written:[], removed:[] }
//                   { type:'error',  id, message }     // worker-level failure

const PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v0.29.4/full/';
try { importScripts(PYODIDE_INDEX + 'pyodide.js'); }
catch (e) { /* loadPyodide stays undefined → reported on first run() */ }

let py = null, pyInitPromise = null, _nativefs = null;

// ---- OPFS helpers (dedicated-worker context; same async API as sandpie.js) ----
async function opfsRoot() { return navigator.storage.getDirectory(); }
function splitPath(p) { const parts = String(p).split('/').filter(Boolean); const name = parts.pop(); return { parts, name }; }
async function opfsResolveDir(parts, create) { let dir = await opfsRoot(); for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: !!create }); return dir; }
async function opfsReadBytes(path) { const { parts, name } = splitPath(path); const dir = await opfsResolveDir(parts); const h = await dir.getFileHandle(name); return new Uint8Array(await (await h.getFile()).arrayBuffer()); }
async function opfsWriteBytes(path, bytes) { const { parts, name } = splitPath(path); const dir = await opfsResolveDir(parts, true); const h = await dir.getFileHandle(name, { create: true }); const w = await h.createWritable(); await w.write(bytes); await w.close(); }
async function swOpfsDelete(relPath, isDir) {
  const parts = String(relPath).split('/').filter(Boolean);
  const name = parts.pop();
  if (!name) return false;
  try { const dir = await opfsResolveDir(parts); await dir.removeEntry(name, { recursive: !!isDir }); return true; }
  catch (_) { return false; }
}

// ---- Event-driven OPFS write-back (FS.trackingDelegate; armed only during a run) ----
let _capActive = false; const _capTouched = new Set(); const _capDeleted = new Set();
function _capReset() { _capActive = false; _capTouched.clear(); _capDeleted.clear(); }
function _opfsRelFromFs(fsPath) { const p = String(fsPath); if (p === '/files' || p === '/files/') return null; if (p.startsWith('/files/')) return p.slice('/files/'.length); return null; }
function _fsTrackingDelegate() {
  const touch = (fsPath) => { if (!_capActive) return; const rel = _opfsRelFromFs(fsPath); if (rel == null) return; _capTouched.add(rel); _capDeleted.delete(rel); };
  const drop = (fsPath) => { if (!_capActive) return; const rel = _opfsRelFromFs(fsPath); if (rel == null) return; _capDeleted.add(rel); _capTouched.delete(rel); };
  return {
    onWriteToFile: (path) => touch(path),
    onMakeDirectory: (path) => touch(path),
    onDeletePath: (path) => drop(path),
    onMovePath: (oldPath, newPath) => { drop(oldPath); touch(newPath); },
  };
}
async function flushCaptureToOpfs() {
  const removed = [], written = [];
  for (const rel of _capDeleted) { if (await swOpfsDelete(rel, true)) removed.push(rel); }
  for (const rel of _capTouched) {
    const full = '/files/' + rel;
    let st;
    try { st = py.FS.stat(full); } catch (_) { continue; }
    try {
      if (py.FS.isDir(st.mode)) await opfsResolveDir(rel.split('/').filter(Boolean), true);
      else { await opfsWriteBytes(rel, py.FS.readFile(full)); written.push(rel); }
    } catch (_) { /* best effort */ }
  }
  return { removed, written };
}

// ---- Pyodide lifecycle ----
async function initPyodide() {
  if (py) return py;
  if (pyInitPromise) return pyInitPromise;
  if (typeof loadPyodide !== 'function') throw new Error('Pyodide unavailable: pyodide.js failed to load in the worker (CDN blocked?).');
  pyInitPromise = (async () => {
    try {
      const p = await loadPyodide({ indexURL: PYODIDE_INDEX });
      // OPFS mount at /files (sync access handles are reliable in a dedicated
      // worker — the whole reason for this file). Falls back to MEMFS-only if OPFS
      // is unreachable.
      try {
        const opfs = await navigator.storage.getDirectory();
        _nativefs = await p.mountNativeFS('/files', opfs);
        p.runPython('import os; os.chdir("/files")');
        p.FS.trackingDelegate = Object.assign(p.FS.trackingDelegate || {}, _fsTrackingDelegate());
      } catch (e) { _nativefs = null; }
      py = p;
      return p;
    } catch (e) { pyInitPromise = null; throw e; }
  })();
  return pyInitPromise;
}
function resetPyodide() { py = null; pyInitPromise = null; _nativefs = null; }
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
  for (let i = a; i <= b; i++) out.push((i === focus ? '>' : ' ') + ' ' + String(i).padStart(4) + ' | ' + lines[i - 1]);
  return out.join('\n');
}

// ---- run one script (mirrors sandpie.js tool_run_python) ----
async function runScript(path, args) {
  if (!path) return { result: 'Error: "path" is required. Save a script with write_file first, then call run_python with its path.' };
  const scriptArgs = Array.isArray(args) ? args.map(String) : [];
  const normPath = String(path).replace(/^\/+/, '').replace(/^files\//, '');

  let code;
  try { code = new TextDecoder().decode(await opfsReadBytes(normPath)); }
  catch (e) { return { result: `Error: could not read /files/${normPath}: ${e.message}.` }; }

  let p;
  try { p = await initPyodide(); }
  catch (e) { return { result: 'Error loading Pyodide: ' + ((e && e.message) || e) }; }

  let stdout = '', stderr = '', removedPaths = [], writtenPaths = [];
  try {
    p.setStdout({ batched: s => { stdout += s + '\n'; } });
    p.setStderr({ batched: s => { stderr += s + '\n'; } });
    if (normPath) {
      self._sandpie_argv = [normPath, ...scriptArgs];
      try { p.runPython('import sys\nfrom js import _sandpie_argv\nsys.argv = list(_sandpie_argv.to_py())'); } catch (_) {}
    }
    try { await p.loadPackagesFromImports(code); } catch (_) {}
    _capReset();
    _capActive = true;
    await p.runPythonAsync(code);
    _capActive = false;

    if (_nativefs) {
      try { ({ removed: removedPaths, written: writtenPaths } = await flushCaptureToOpfs()); } catch (_) {}
    }
    let out = stdout.trimEnd();
    if (stderr.trim()) out += (out ? '\n' : '') + '--- stderr ---\n' + stderr.trimEnd();
    return { result: out || '(no output)', written: writtenPaths, removed: removedPaths };
  } catch (e) {
    let msg = '';
    if (e != null) {
      if (typeof e === 'string') msg = e;
      else if (e.message) msg = e.message;
      else { try { const s = e.toString(); if (s && s !== '[object Object]') msg = s; } catch (_) {} }
    }
    const tail = stderr.trim() ? '\n--- stderr ---\n' + stderr.trimEnd() : '';
    if (isPyodideFatal(e, msg, stderr)) {
      resetPyodide();
      return { result: 'FATAL: Pyodide runtime crashed and has been reset. All in-memory state (globals, imports, function defs) is gone — the next run_python starts a clean interpreter. DO NOT retry the failing code as-is; re-do any imports/setup first.' + (msg ? '\n--- crash signal ---\n' + msg : '') + tail };
    }
    const src = sourceFromTraceback(msg, code);
    return { result: 'Error: ' + (msg || 'unknown (no message)') + (src ? '\n\n--- ' + normPath + ' (around the error) ---\n' + src : '') + tail };
  } finally {
    _capActive = false;
    try { p && p.setStdout({}); } catch (_) {}
    try { p && p.setStderr({}); } catch (_) {}
  }
}

// Single-flight: serialize runs (shared interpreter globals — setStdout closures,
// sys.argv) so two concurrent calls can't trample each other.
let _mutex = Promise.resolve();
self.onmessage = async (e) => {
  const m = e.data || {};
  if (m.type !== 'run') return;
  const job = _mutex.then(() => runScript(m.path, m.args));
  _mutex = job.catch(() => {});
  try {
    const r = await job;
    self.postMessage({ type: 'result', id: m.id, result: r.result, written: r.written || [], removed: r.removed || [] });
  } catch (err) {
    self.postMessage({ type: 'error', id: m.id, message: String((err && err.message) || err) });
  }
};
