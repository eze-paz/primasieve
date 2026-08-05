// pyodide-worker.js — one Pyodide interpreter per instance, run as a nested
// dedicated Worker owned by sandpie-worker.js (the "pool manager"). Moving Python
// off the agent-loop thread means a long/blocking run_python (incl. the sync-XHR
// dehydration fault-in) no longer freezes token streaming in other conversations,
// and a pool of these gives real parallel Python execution.
//
// Protocol (manager → this worker):
//   IN  {type:'dbx-token', ...}          → update Dropbox context (for sync hydrate)
//   IN  {type:'dbx-index', index,exempt} → update dehydrated cloud index
//   IN  {type:'fs-changed', rel}         → targeted OPFS→MEMFS refresh of one path
//   IN  {type:'fs-removed', paths}       → drop paths from MEMFS
//   IN  {type:'run-python', id, path, args} → run a script; replies python-result
// Protocol (this worker → manager):
//   OUT {type:'python-result', id, result}      → run finished (result is raw/untruncated)
//   OUT {type:'forward-to-page', payload}        → relayed to page (opfs-deleted-by-python / sw-opfs-changed / worker-hydrated)
//   OUT {type:'sandpie-worker-log', ...}         → console relay (manager re-forwards to page)

// ---- console relay (Worker → manager → page) ------------------------------
const _WID = (self.name || 'py');
function _relayLog(level, args) {
  let text = args.map(a => {
    if (a == null) return String(a);
    if (typeof a === 'string') return a;
    if (a instanceof Error) return (a.stack || a.message || String(a));
    try { return JSON.stringify(a); } catch (_) { return String(a); }
  }).join(' ');
  const MAX_LOG_LEN = 5000;
  if (text.length > MAX_LOG_LEN) text = text.slice(0, MAX_LOG_LEN) + '…';
  try { self.postMessage({ type: 'sandpie-worker-log', level, text, ts: Date.now() }); } catch (_) {}
}
const _origConsole = { log: console.log, warn: console.warn, error: console.error, info: console.info };
console.log   = (...args) => { try { _relayLog('log',   args); } catch (_) {} _origConsole.log.apply(console, args); };
console.warn  = (...args) => { try { _relayLog('warn',  args); } catch (_) {} _origConsole.warn.apply(console, args); };
console.error = (...args) => { try { _relayLog('error', args); } catch (_) {} _origConsole.error.apply(console, args); };
console.info  = (...args) => { try { _relayLog('info',  args); } catch (_) {} _origConsole.info.apply(console, args); };

self.addEventListener('error', (ev) => {
  console.error('[' + _WID + '] uncaught error:', ev.message, 'at', (ev.filename || '?') + ':' + (ev.lineno || '?'), ev.error && ev.error.stack ? '\n' + ev.error.stack : '');
});
self.addEventListener('unhandledrejection', (ev) => {
  const r = ev.reason;
  console.error('[' + _WID + '] unhandled rejection:', r && (r.stack || r.message) || String(r));
});

console.log('[pyodide-worker] boot — id=' + _WID);

// Dropbox / dehydration context (pushed by the manager, mirrored from the page).
let _dbxCtx = null;
let _dehydrated = false;
let _dbxIndex = null;
let _dbxExempt = ['sandpie/conversations', 'sandpie/skills', 'sandpie/shared-installed', 'sandpie/shared-incoming'];

// ---- message protocol ------------------------------------------------------
self.addEventListener('message', async (event) => {
  const data = event.data;
  if (!data) return;

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

  if (data.type === 'fs-removed' && Array.isArray(data.paths)) {
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

  if (data.type === 'fs-changed' && data.rel) {
    if (!py || !_nativefs) return;
    await withPy(async () => {
      const rel = String(data.rel).replace(/^\/+/, '');
      const full = '/files/' + rel;
      try {
        const bytes = await opfsReadBytes(rel);
        const dir = full.substring(0, full.lastIndexOf('/'));
        if (dir && dir !== '/files') { try { py.FS.mkdirTree(dir); } catch (_) {} }
        py.FS.writeFile(full, bytes);
      } catch (e) {
        console.warn('[pyodide-worker] fs-changed sync failed for', rel, e);
      }
    });
    return;
  }

  if (data.type === 'run-python') {
    const { id, path, args } = data;
    let out;
    try { out = await tool_run_python({ path, args }); }
    catch (e) { out = { result: 'Error: ' + (e && e.message || e) }; }
    try { self.postMessage({ type: 'python-result', id, result: (out && out.result) || '' }); } catch (_) {}
    return;
  }
});

// ============================================================
// Pyodide — lazy-loaded. Web Workers can call importScripts()
// from inside async functions.
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
      console.log('[pyodide-worker] importing pyodide.js…');
      importScripts(PYODIDE_INDEX + 'pyodide.js');
      console.log('[pyodide-worker] importing pyodide.asm.js…');
      importScripts(PYODIDE_INDEX + 'pyodide.asm.js');
      _pyodideJsLoaded = true;
      console.log('[pyodide-worker] pyodide bootstrap scripts loaded');
    } catch (e) {
      console.warn('[pyodide-worker] pyodide bootstrap failed:', e);
      throw new Error('Pyodide unavailable: failed to load pyodide.js — check network. ' + (e && e.message || e));
    }
  }
  pyInitPromise = (async () => {
    try {
      const p = await loadPyodide({ indexURL: PYODIDE_INDEX });
      try {
        const opfsRootDir = await navigator.storage.getDirectory();
        _nativefs = await p.mountNativeFS('/files', opfsRootDir);
        // A freshly-spawned pool worker must be born coherent with whatever the
        // other workers / write_file have already put in OPFS. syncfs(true)
        // populates MEMFS from the backing OPFS once at mount time. (Ongoing
        // changes arrive as targeted fs-changed/fs-removed messages, which avoid
        // syncfs's known delete-fragility.)
        await new Promise((resolve) => {
          try { p.FS.syncfs(true, () => resolve()); } catch (_) { resolve(); }
        });
        p.runPython('import os; os.chdir("/files")');
        p.FS.trackingDelegate = Object.assign(p.FS.trackingDelegate || {}, _fsTrackingDelegate());
        try { p.runPython(_HYDRATE_AUDIT_PY); } catch (e) { console.warn('[pyodide-worker] hydrate audit hook install failed:', e); }
        try { p.runPython(_CLOUD_FS_PY); } catch (e) { console.warn('[pyodide-worker] cloud fs view patch install failed:', e); }
        console.log('[pyodide-worker] OPFS mounted at /files (cwd); FS tracking installed');
      } catch (e) {
        _nativefs = null;
        console.warn('[pyodide-worker] OPFS mount failed (Python /files unavailable):', e);
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
  console.warn('[pyodide-worker] resetting Pyodide:', reason);
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

// Per-worker serial lock: one execution at a time within THIS interpreter, so
// the capture/stdout globals below stay consistent. Parallelism comes from the
// manager running several of these workers, not from concurrency inside one.
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
async function _opfsGetFile(rel) {
  const { parts, name } = splitPath(rel);
  const dir = await opfsResolveDir(parts);
  return (await dir.getFileHandle(name)).getFile();
}

// ============================================================
// Dehydrated Dropbox — opt-in JIT hydration (sync leg for Pyodide open())
// ============================================================
const _hydratedSet = new Set();
const _hydrating = new Map();
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
// Async hydration (used to fault in the entry script itself before Python starts).
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
// Synchronous hydration for Pyodide open(): two blocking XHRs, writing THROUGH
// Pyodide's FS so the just-opened file is visible inline. Only possible in a
// Worker (sync XHR + responseType forbidden on the main thread).
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
  try { x2.responseType = 'arraybuffer'; } catch (_) { ab = false; }
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
  } catch (e) { console.warn('[pyodide-worker] sync hydrate failed:', pathStr, (e && e.message) || e); }
};
// ---- Cloud-index view for Python (stat / listdir / scandir) ------------------
// Expose the dehydrated cloud index to Python so its view of /files matches the
// file viewer: os.path.exists/getsize, os.listdir, glob, pathlib all see cloud
// entries that have no local bytes yet. Pure metadata (no network, no bytes);
// byte hydration stays in _sandpie_hydrate_sync (open() audit hook). Returns
// null when dehydrated mode is off / index absent -> Python falls back to the
// plain OPFS behaviour. The pool manager keeps _dbxIndex live via dbx-index
// messages, so these read the freshest snapshot on every call.
self._sandpie_cloud_stat = function (rel) {
  try {
    if (!_dehydrated || !_dbxIndex) return null;
    const r = String(rel || '').replace(/^\/+/, '').replace(/\/+$/, '');
    if (!r || _relExempt(r)) return null;
    const e = _dbxIndex[r];
    if (!e) return null;
    return { kind: e.kind === 'file' ? 'file' : 'folder', size: e.kind === 'file' ? (e.size || 0) : 0, mtime: e.cloudMtime ? Math.max(0, Math.floor(new Date(e.cloudMtime).getTime() / 1000)) : 0 };
  } catch (_) { return null; }
};
self._sandpie_cloud_children = function (rel) {
  try {
    if (!_dehydrated || !_dbxIndex) return null;
    const base = String(rel || '').replace(/^\/+/, '').replace(/\/+$/, '');
    const prefix = base ? base + '/' : '';
    const out = [], dirs = new Set(), seen = new Set();
    for (const k0 of Object.keys(_dbxIndex)) {
      const k = k0.replace(/^\/+/, '');
      if (!k || _relExempt(k)) continue;
      if (prefix && !k.startsWith(prefix)) continue;
      const rest = k.slice(prefix.length);
      if (!rest) continue;
      const slash = rest.indexOf('/');
      if (slash >= 0) { dirs.add(rest.slice(0, slash)); continue; }
      if (seen.has(rest)) continue;               // folder already aggregated via its children
      seen.add(rest);
      const e = _dbxIndex[k0];
      out.push({ name: rest, kind: (e && e.kind === 'folder') ? 'folder' : 'file' });
    }
    for (const d of dirs) if (!seen.has(d)) out.push({ name: d, kind: 'folder' });
    return out;
  } catch (_) { return null; }
};
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

// ---- Cloud-index view for Python: wrap the three introspection choke points ----
// os.stat / os.listdir / os.scandir (plus lstat/access) consult the cloud index
// when the local FS reports ENOENT/ENOTDIR, so os.path.*, pathlib, glob, shutil
// and os.walk all see dehydrated entries with truthful metadata and ZERO
// downloads. Bytes still come exclusively from open() -> _sandpie_hydrate_sync.
// Important: listings are VIRTUAL — no placeholder files are ever created, so
// the open() hydrate guard (analyzePath().exists) can never short-circuit on a
// hollow file.
const _CLOUD_FS_PY = `
import os
from js import _sandpie_cloud_stat, _sandpie_cloud_children

_orig_stat = os.stat
_orig_lstat = os.lstat
_orig_access = os.access
_orig_listdir = os.listdir
_orig_scandir = os.scandir

def _cloud_rel(path):
    try:
        p = os.fspath(path)
    except Exception:
        return None
    if isinstance(p, bytes):
        try:
            p = p.decode('utf-8')
        except Exception:
            return None
    if not isinstance(p, str):
        return None
    if p.startswith('/files/'):
        rel = p[len('/files/'):]
    elif p == '/files' or p == '/files/':
        rel = ''
    elif p.startswith('files/'):
        rel = p[len('files/'):]
    elif p.startswith('/'):
        return None
    else:
        rel = p
    rel = rel.strip('/')
    if rel == '.' or rel == '..':
        rel = ''
    return rel

def _cloud_meta(rel):
    if rel is None:
        return None
    try:
        m = _sandpie_cloud_stat(rel)
        if m is None:
            return None
        if hasattr(m, 'to_py'):
            m = m.to_py()
        if not isinstance(m, dict):
            return None
        return m
    except Exception:
        return None

def _cloud_result(m):
    try:
        mode = 0o100644 if m.get('kind') == 'file' else 0o040755
        size = int(m.get('size') or 0)
        mt = int(m.get('mtime') or 0)
        return os.stat_result((mode, 0, 0, 1, 0, 0, size, mt, mt, mt))
    except Exception:
        return None

def _patched_stat(path, *args, **kwargs):
    try:
        return _orig_stat(path, *args, **kwargs)
    except (FileNotFoundError, NotADirectoryError):
        if kwargs.get('dir_fd') is not None:
            raise
        m = _cloud_meta(_cloud_rel(path))
        r = _cloud_result(m) if m is not None else None
        if r is None:
            raise
        return r

def _patched_lstat(path, *args, **kwargs):
    try:
        return _orig_lstat(path, *args, **kwargs)
    except (FileNotFoundError, NotADirectoryError):
        if kwargs.get('dir_fd') is not None:
            raise
        m = _cloud_meta(_cloud_rel(path))
        r = _cloud_result(m) if m is not None else None
        if r is None:
            raise
        return r

def _patched_access(path, mode, *args, **kwargs):
    # os.access returns False on ENOENT (it does not raise), so a False result
    # must also fall back to the cloud index.
    try:
        r = _orig_access(path, mode, *args, **kwargs)
    except (FileNotFoundError, NotADirectoryError):
        r = False
    if r:
        return r
    if kwargs.get('dir_fd') is not None:
        return r
    m = _cloud_meta(_cloud_rel(path))
    if m is None:
        return r
    if mode == 0:
        return True
    if m.get('kind') == 'folder':
        return bool(mode & (os.R_OK | os.W_OK | os.X_OK))
    return bool(mode & (os.R_OK | os.W_OK))

def _cloud_children(rel):
    if rel is None:
        return None
    try:
        kids = _sandpie_cloud_children(rel)
        if kids is None:
            return None
        if hasattr(kids, 'to_py'):
            kids = kids.to_py()
        out = []
        for k in kids:
            out.append(dict(k))
        return out
    except Exception:
        return None

def _patched_listdir(path='.'):
    err = None
    names = None
    try:
        names = _orig_listdir(path)
    except (FileNotFoundError, NotADirectoryError) as e:
        err = e
    rel = _cloud_rel(path)
    kids = _cloud_children(rel)
    if kids is None:
        if err is not None:
            raise err
        return names
    extra = [k['name'] for k in kids if k.get('name')]
    if isinstance(path, bytes):
        extra = [n.encode('utf-8') for n in extra]
    if err is not None and not extra:
        m = _cloud_meta(rel)
        if m is None or m.get('kind') != 'folder':
            raise err
    merged = set(names or []) | set(extra)
    return sorted(merged)

class _CloudDirEntry:
    __slots__ = ('name', 'path', '_kind')
    def __init__(self, name, base, kind):
        if isinstance(base, bytes):
            name = name.encode('utf-8')
        self.name = name
        self.path = os.path.join(base, name)
        self._kind = kind
    def is_dir(self, follow_symlinks=True):
        return self._kind == 'folder'
    def is_file(self, follow_symlinks=True):
        return self._kind == 'file'
    def is_symlink(self):
        return False
    def inode(self):
        return 0
    def stat(self, follow_symlinks=True):
        m = _cloud_meta(_cloud_rel(self.path))
        r = _cloud_result(m) if m is not None else None
        if r is None:
            raise FileNotFoundError('No such file or directory: ' + str(self.path))
        return r
    def __repr__(self):
        return '<_CloudDirEntry %r>' % (self.name,)

class _ScandirResult:
    def __init__(self, entries):
        self._entries = list(entries)
        self._i = 0
    def __iter__(self):
        return self
    def __next__(self):
        if self._i >= len(self._entries):
            raise StopIteration
        e = self._entries[self._i]
        self._i += 1
        return e
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()
        return False
    def close(self):
        self._i = len(self._entries)

def _patched_scandir(path='.', *, dir_fd=None):
    if dir_fd is not None:
        return _orig_scandir(path, dir_fd=dir_fd)
    err = None
    local = None
    try:
        local = _orig_scandir(path)
    except (FileNotFoundError, NotADirectoryError) as e:
        err = e
    rel = _cloud_rel(path)
    kids = _cloud_children(rel)
    if kids is None:
        if local is not None:
            return local
        raise err
    local_entries = []
    names_local = set()
    if local is not None:
        try:
            local_entries = list(local)
            names_local = {e.name for e in local_entries}
        except OSError:
            local_entries = []
            names_local = set()
    if err is not None and not kids:
        m = _cloud_meta(rel)
        if m is None or m.get('kind') != 'folder':
            raise err
    base = os.fspath(path)
    merged = list(local_entries)
    for k in kids:
        name = k.get('name')
        if not name or name in names_local:
            continue
        merged.append(_CloudDirEntry(name, base, k.get('kind') or 'file'))
    return _ScandirResult(merged)

os.stat = _patched_stat
os.lstat = _patched_lstat
os.access = _patched_access
os.listdir = _patched_listdir
os.scandir = _patched_scandir
`;

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
    } catch (e) { console.warn('[pyodide-worker] OPFS write-back failed:', rel, e); }
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
    console.log('[pyodide-worker] deleted from OPFS:', relPath);
    return true;
  } catch (e) {
    if (e.name !== 'NotFoundError') console.warn('[pyodide-worker] failed to delete from OPFS:', relPath, e);
    return false;
  }
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

async function tool_run_python({ path, args }) {
  if (!path) return { result: 'Error: "path" is required. Save a script with write_file first, then call run_python with its path.' };
  const scriptArgs = Array.isArray(args) ? args.map(String) : [];
  const normPath = String(path).replace(/^\/+/, '').replace(/^files\//, '');
  let code;
  // The audit hook only hydrates files the script open()s at RUNTIME; the entry
  // script itself is read here before Python starts, so it needs the same
  // try-OPFS-then-hydrate-on-miss dance as read_file/load_image.
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
        catch (e) { console.warn('[pyodide-worker] OPFS write-back after run_python failed:', e); }
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
