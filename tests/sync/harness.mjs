// Test world for the Dropbox sync pipeline.
//
// Boots the REAL modules — modules/dbx-token.js, modules/dbx-syncstate.js,
// modules/dropbox.js — plus the REAL file tools extracted from
// modules/sandpie-worker.js, against an in-memory OPFS and an in-memory fake of
// the Dropbox API. Nothing here reimplements sync logic: the point is that these
// tests fail when the shipped code changes behaviour.
//
// Production wiring, reproduced exactly:
//   tool_write_file -> self.postMessage({forward-to-page, sw-opfs-changed})
//                   -> conversations.js relay (relayToPage)
//                   -> navigator.serviceWorker 'message' listener in dropbox.js
//                   -> ledger marks the path dirty
//                   -> sync() -> pushDirty() -> upload -> cloud
//
// world.reload() models a page refresh: OPFS, localStorage and the cloud
// persist; all module state is rebuilt from scratch.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const R = (p) => readFileSync(join(here, '..', '..', p), 'utf8');

const srcToken = R('modules/dbx-token.js');
const srcLedger = R('modules/dbx-syncstate.js');
const srcDropbox = R('modules/dropbox.js');
const workerSrc = R('modules/sandpie-worker.js');

// ── extract real tool sources from the worker (same trick as tests/tools) ──
function extractFrom(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) throw new Error('extract: not found: ' + marker);
  const end = src.indexOf('\n}\n', i);
  if (end < 0) throw new Error('extract: no terminator for ' + marker);
  return src.slice(i, end + 3);
}
// The edit helpers are a contiguous block in the worker (_matchEol .. _editReport);
// take it whole rather than chasing each transitive dependency.
function sliceBetween(src, startMarker, endMarker) {
  const i = src.indexOf(startMarker);
  if (i < 0) throw new Error('slice: start not found: ' + startMarker);
  const j = src.indexOf(endMarker, i);
  if (j < 0) throw new Error('slice: end not found: ' + endMarker);
  const end = src.indexOf('\n}\n', j);
  return src.slice(i, end + 3);
}
const srcFnv = extractFrom(workerSrc, 'function _fnv1a(');
const srcEditHelpers = sliceBetween(workerSrc, 'function _matchEol(', 'function _editReport(');
const srcWrite = extractFrom(workerSrc, 'async function tool_write_file(');
const srcEdit = extractFrom(workerSrc, 'async function tool_edit_file(');
const srcDelete = extractFrom(workerSrc, 'async function tool_delete_file(');
const TOOL_SRC = srcFnv + srcEditHelpers + srcWrite + srcEdit + srcDelete;

export const WSROOT = '/sandpie';
const enc = (s) => new TextEncoder().encode(s);
const dec = (b) => new TextDecoder().decode(b);
const T0 = 1700000000000;

export function makeWorld(opts = {}) {
  // Shared, reload-surviving state: OPFS, localStorage, the cloud.
  const S = opts._shared || {
    FS: new Map(Object.entries(opts.files || {})),
    MT: new Map(),
    CLOUD: new Map(),
    LOG: [],
    LSMAP: new Map(Object.entries(opts.localStorage || {})),
    offset: 0,
    revSeq: 0,
    seeded: false,
  };
  const { FS, MT, CLOUD, LOG, LSMAP } = S;
  // The clock must track the real Date.now(): dropbox.js compares file mtimes
  // against Date.now() (the 24h dehydration window), so a fixed fake epoch would
  // make every file look years stale. advance() moves the whole world forward.
  const nowMs = () => Date.now() + S.offset;
  if (!S.seeded) {
    for (const k of FS.keys()) MT.set(k, nowMs());
    S.seeded = true;
  }

  function cloudPut(path, content) {
    const e = { content, rev: "rev" + (++S.revSeq), size: enc(content).length, server_modified: new Date(nowMs()).toISOString() };
    CLOUD.set(path, e);
    LOG.push({ kind: 'file', path, ...e });
    return e;
  }
  function cloudDel(path) {
    const had = CLOUD.delete(path);
    for (const k of [...CLOUD.keys()]) if (k.startsWith(path + '/')) CLOUD.delete(k);
    LOG.push({ kind: 'deleted', path });
    return had;
  }
  if (!opts._shared) for (const [rel, content] of Object.entries(opts.cloud || {})) cloudPut(WSROOT + '/' + rel, content);

  const CALLS = [];
  let failNext = null;

  const localStorage = {
    getItem: (k) => (LSMAP.has(k) ? LSMAP.get(k) : null),
    setItem: (k, v) => { LSMAP.set(k, String(v)); },
    removeItem: (k) => { LSMAP.delete(k); },
    clear: () => LSMAP.clear(),
  };

  // ── fake Dropbox transport ──
  const SESS = new Map();
  let sessSeq = 0;
  function toEntry(x) {
    if (x.kind === 'deleted') return { '.tag': 'deleted', name: x.path.split('/').pop(), path_display: x.path, path_lower: x.path.toLowerCase() };
    return { '.tag': 'file', name: x.path.split('/').pop(), path_display: x.path, path_lower: x.path.toLowerCase(), rev: x.rev, size: x.size, server_modified: x.server_modified };
  }
  async function fakeFetch(url, init = {}) {
    const u = String(url);
    const is = (p) => u.includes(p);
    let body = null;
    if (init.body && typeof init.body === 'string') { try { body = JSON.parse(init.body); } catch (_) { body = null; } }
    const h = init.headers || {};
    const rawArg = h['Dropbox-API-Arg'] || h['dropbox-api-arg'] || null;
    const arg = rawArg ? JSON.parse(rawArg) : null;
    CALLS.push({ url: u, body, arg });
    const json = (o, status = 200) => ({ ok: status < 400, status, json: async () => o, text: async () => JSON.stringify(o) });

    if (failNext && u.includes(failNext.match)) {
      const f = failNext; failNext = null;
      return json({ error_summary: f.summary || 'internal_error/' }, f.status || 500);
    }
    if (is('/2/users/get_current_account')) {
      return json({ email: 'test@example.com', account_id: 'acct1', root_info: { '.tag': 'user', root_namespace_id: '1', home_namespace_id: '1' } });
    }
    if (is('/2/files/list_folder/get_latest_cursor')) return json({ cursor: 'c' + LOG.length });
    if (is('/2/files/list_folder/continue')) {
      const n = parseInt(String(body.cursor).slice(1), 10) || 0;
      return json({ entries: LOG.slice(n).map(toEntry), cursor: 'c' + LOG.length, has_more: false });
    }
    if (is('/2/files/list_folder')) {
      const base = body && body.path ? body.path : '';
      const entries = [...CLOUD.entries()]
        .filter(([p]) => !base || p === base || p.startsWith(base + '/'))
        .map(([p, e]) => toEntry({ kind: 'file', path: p, ...e }));
      return json({ entries, cursor: 'c' + LOG.length, has_more: false });
    }
    if (is('/2/files/upload_session/start')) {
      const id = 's' + (++sessSeq);
      SESS.set(id, init.body instanceof Uint8Array ? dec(init.body) : String(init.body || ''));
      return json({ session_id: id });
    }
    if (is('/2/files/upload_session/finish_batch')) {
      const entries = ((body && body.entries) || []).map((x) => {
        const content = SESS.get(x.cursor.session_id) ?? '';
        const e = cloudPut(x.commit.path, content);
        return { '.tag': 'success', name: x.commit.path.split('/').pop(), path_display: x.commit.path, rev: e.rev, size: e.size, server_modified: e.server_modified };
      });
      return json({ '.tag': 'complete', entries });
    }
    if (is('/2/files/upload')) {
      const content = init.body instanceof Uint8Array ? dec(init.body) : String(init.body || '');
      const p = arg ? arg.path : (body && body.path);
      const e = cloudPut(p, content);
      return json({ path_display: p, rev: e.rev, size: e.size });
    }
    if (is('/2/files/delete_v2')) {
      if (!cloudDel(body.path)) return json({ error_summary: 'path_lookup/not_found/' }, 409);
      return json({ metadata: { path_display: body.path } });
    }
    if (is('/2/files/create_folder_v2')) return json({ metadata: { path_display: body.path } });
    if (is('/2/files/get_metadata')) {
      const e = CLOUD.get(body.path);
      if (!e) return json({ error_summary: 'path/not_found/' }, 409);
      return json({ '.tag': 'file', path_display: body.path, rev: e.rev, size: e.size, server_modified: e.server_modified });
    }
    if (is('/2/files/get_temporary_link')) {
      if (!CLOUD.has(body.path)) return json({ error_summary: 'path/not_found/' }, 409);
      return json({ link: 'https://dl.fake' + body.path });
    }
    if (u.startsWith('https://dl.fake')) {
      const e = CLOUD.get(u.slice('https://dl.fake'.length));
      if (!e) return { ok: false, status: 404, text: async () => 'nf' };
      return { ok: true, status: 200, arrayBuffer: async () => enc(e.content).buffer, text: async () => e.content };
    }
    return json({ error_summary: 'UNMOCKED/' + u }, 400);
  }

  // ── Sandpie host ──
  const listeners = new Map();
  const events = {
    on: (k, fn) => { if (!listeners.has(k)) listeners.set(k, []); listeners.get(k).push(fn); },
    emit: (k, v) => { for (const fn of listeners.get(k) || []) fn(v); },
  };
  const opfs = {
    exists: async (rel) => FS.has(rel),
    list: async () => [...FS.keys()],
    read: async (rel) => { if (!FS.has(rel)) throw new Error('ENOENT ' + rel); return FS.get(rel); },
    readBytes: async (rel) => enc(FS.get(rel) ?? ''),
    // bulkDownload writes the downloaded bytes straight through, so accept both
    // a string and a Uint8Array/ArrayBuffer (String(bytes) would store "111,114,…").
    write: async (rel, data) => {
      const text = (data instanceof Uint8Array) ? dec(data)
        : (data instanceof ArrayBuffer) ? dec(new Uint8Array(data))
        : String(data);
      FS.set(rel, text); MT.set(rel, nowMs());
    },
    remove: async (rel) => {
      FS.delete(rel); MT.delete(rel);
      for (const k of [...FS.keys()]) if (k.startsWith(rel + '/')) { FS.delete(k); MT.delete(k); }
    },
  };

  const world = {
    FS, MT, CLOUD, LOG, CALLS, LSMAP, localStorage, opfs, events,
    generating: false,
    relayBroken: false,
    get now() { return nowMs(); },
    advance(ms) { S.offset += ms; },
    failOnce(match, status, summary) { failNext = { match, status, summary }; },
    cloudPut, cloudDel,
    cloudText: (rel) => (CLOUD.get(WSROOT + '/' + rel) || {}).content,
    cloudHas: (rel) => CLOUD.has(WSROOT + '/' + rel),
    localText: (rel) => FS.get(rel),
    localHas: (rel) => FS.has(rel),

    // STORAGE-NEUTRAL READ. What the model or the file viewer can actually get
    // back for a path, wherever it currently lives. Today a project file is
    // usually in both OPFS and Dropbox; after the full-Dropbox refactor it will
    // exist ONLY in Dropbox, so an assertion written against localHas()/localText()
    // would fail for a file that is perfectly fine.
    //
    // Rule for these suites: assert on readBack()/readable() unless the test is
    // specifically ABOUT where the bytes live. The two deliberate exceptions are
    // sandpie/* (memory.js and pins.js read OPFS synchronously while building a
    // prompt, so a local copy IS the contract) and suite-engine.mjs (which tests
    // the current engine's internals and dies with it).
    readBack: (rel) => (FS.has(rel) ? FS.get(rel) : (CLOUD.get(WSROOT + '/' + rel) || {}).content),
    readable: (rel) => (FS.has(rel) ? true : CLOUD.has(WSROOT + '/' + rel)),
    where: (rel) => ({ local: FS.has(rel), cloud: CLOUD.has(WSROOT + '/' + rel) }),
    ledger: () => { try { return JSON.parse(LSMAP.get('dbxfull-sync-state') || '{}'); } catch (_) { return {}; } },
    reload: () => makeWorld({ ...opts, _shared: S }),
  };

  const Sandpie = {
    opfs,
    events,
    opfsMtime: async (rel) => MT.get(rel) || 0,
    openFilePath: () => world.openFile || null,
    refreshFiles: async () => {},
    refreshConversations: async () => {},
    reload: () => {},
    isGenerating: () => world.generating,
    registerSyncProvider: (p) => { world.provider = p; },
  };

  // ── browser globals ──
  const swListeners = [];
  const navigator = {
    serviceWorker: {
      addEventListener: (t, fn) => { if (t === 'message') swListeners.push(fn); },
      dispatchEvent: (ev) => { for (const fn of swListeners) fn(ev); return true; },
      controller: null,
    },
    locks: null,
  };
  const elStub = () => ({
    style: {}, dataset: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    appendChild() {}, removeChild() {}, addEventListener() {}, removeEventListener() {}, remove() {},
    setAttribute() {}, getAttribute: () => null, insertAdjacentHTML() {},
    querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    innerHTML: '', textContent: '',
  });
  const document = {
    readyState: 'complete',
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: elStub,
    addEventListener: () => {},
    body: elStub(),
    head: elStub(),
  };
  // Minimal in-memory IndexedDB. Not optional: since commit 3c12314 the cloud
  // cursor is only advanced once the index has been COMMITTED to IDB, so a stub
  // that always errors silently degrades every sync to a full re-list and
  // changes what the cleanup passes see. Backed by shared state so the store
  // survives world.reload(), like the real thing.
  if (!S.idb) S.idb = new Map();
  const fire = (obj, name, arg) => setTimeout(() => { const fn = obj[name]; if (fn) fn(arg || {}); }, 0);
  const indexedDB = {
    open(name) {
      const req = { result: null, error: null };
      const db = {
        _stores: S.idb,
        createObjectStore(store) { if (!S.idb.has(store)) S.idb.set(store, new Map()); return {}; },
        close() {},
        transaction(store) {
          const map = S.idb.get(store) || (S.idb.set(store, new Map()), S.idb.get(store));
          const tx = { error: null };
          let pending = 0;
          const settle = () => { if (--pending === 0) fire(tx, 'oncomplete'); };
          tx.objectStore = () => ({
            put(value, key) { pending++; setTimeout(() => { map.set(key, value); settle(); }, 0); return {}; },
            clear() { pending++; setTimeout(() => { map.clear(); settle(); }, 0); return {}; },
            get(key) {
              const r = { result: undefined };
              pending++;
              setTimeout(() => { r.result = map.get(key); fire(r, 'onsuccess'); settle(); }, 0);
              return r;
            },
          });
          // A transaction with no requests still completes.
          setTimeout(() => { if (pending === 0) fire(tx, 'oncomplete'); }, 0);
          return tx;
        },
      };
      req.result = db;
      const fresh = S.idb.size === 0;
      setTimeout(() => {
        if (fresh && req.onupgradeneeded) req.onupgradeneeded({});
        fire(req, 'onsuccess');
      }, 0);
      return req;
    },
  };
  const crypto = {
    getRandomValues: (a) => { for (let i = 0; i < a.length; i++) a[i] = i & 255; return a; },
    subtle: { digest: async () => new ArrayBuffer(32) },
  };

  // The page's worker handle. dropbox.js polls for it on a 1s timer
  // (pushDbxTokenToSW / pushDbxIndexToSW / wireTokenRequestListener), so without
  // a stub those retries never terminate.
  const WORKER_MSGS = [];
  const workerStub = {
    postMessage: (m) => { WORKER_MSGS.push(m); },
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  const sandbox = {
    localStorage, navigator, document, indexedDB, crypto,
    fetch: fakeFetch,
    console: opts.verbose ? console : { log() {}, info() {}, warn() {}, error() {}, debug() {} },
    // Timers fire on the macrotask queue but never re-arm a long poll: any delay
    // over a second is dropped, which keeps retry loops from spinning forever.
    // Real timers: flushBeforeReload races a 2500ms timeout against the upload,
    // so squashing every delay inverts that race. Only absurdly long timers are
    // capped, to keep a stray poll from holding the process open.
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 3000)),
    clearTimeout,
    setInterval: () => 0,
    clearInterval: () => {},
    _sandpieWorker: workerStub,
    Sandpie,
    location: { search: '', pathname: '/app', href: 'https://x/app', origin: 'https://x' },
    history: { replaceState() {} },
    alert: () => {},
    confirm: () => true,
    prompt: () => null,
  };
  sandbox.self = sandbox;
  sandbox.window = sandbox;

  const keys = Object.keys(sandbox);
  const load = (src, label) => {
    try { new Function(...keys, src)(...keys.map((k) => sandbox[k])); }
    catch (e) { throw new Error('loading ' + label + ': ' + (e && e.message)); }
  };
  load(srcToken, 'dbx-token.js');
  load(srcLedger, 'dbx-syncstate.js');
  load(srcDropbox, 'dropbox.js');
  world.ledgerApi = sandbox.SandpieDbxSyncState;
  world.workerMsgs = WORKER_MSGS;

  // conversations.js relay: worker forward-to-page -> serviceWorker 'message'
  function relayDispatch(msg) {
    if (world.relayBroken) return;
    if (!msg || msg.type !== 'forward-to-page') return;
    navigator.serviceWorker.dispatchEvent({ data: msg.payload });
  }
  world.relay = relayDispatch;

  // ── worker side: the real file tools over the same OPFS ──
  const POSTED = [];
  const toolGlobals = `
    const FILE_TEXT_MAX = 2 * 1024 * 1024;
    const FILE_TOOL_CAP = 30000;
    const _emittedFileHashes = new Map();
    const _pyBroadcast = () => {};
    const _invalidateFileCache = () => {};
    const _betaOn = () => false;
    const _ensureDbxCtx = async () => {};
    const _indexEntry = () => null;
    const hydrateAsync = async () => false;
    const _nf = () => { const e = new Error('not found'); e.name = 'NotFoundError'; return e; };
    const opfsRoot = async () => {
      const dirHandle = (prefix) => ({
        async getDirectoryHandle(name) { return dirHandle(prefix + name + '/'); },
        async getFileHandle(name) { if (!FS.has(prefix + name)) throw _nf(); return {}; },
        async removeEntry(name, o) {
          const p = prefix + name;
          if (FS.has(p)) { FS.delete(p); return; }
          const kids = [...FS.keys()].filter((k) => k.startsWith(p + '/'));
          if (!kids.length) throw _nf();
          if (!(o && o.recursive)) { const e = new Error('not empty'); e.name = 'InvalidModificationError'; throw e; }
          for (const k of kids) FS.delete(k);
        },
      });
      return dirHandle('');
    };
    const opfsReadBytes = async (rel) => new TextEncoder().encode(FS.get(rel) ?? '');
    const opfsWriteBytes = async (rel, bytes) => { FS.set(rel, new TextDecoder().decode(bytes)); MT.set(rel, NOW()); };
    const _opfsGetFile = async (rel) => {
      if (!FS.has(rel)) throw _nf();
      const s = FS.get(rel);
      return { size: new TextEncoder().encode(s).length, text: async () => s };
    };
    const self = { postMessage: (m) => { POSTED.push(m); relay(m); } };
  `;
  world.POSTED = POSTED;
  world.tools = new Function('FS', 'MT', 'POSTED', 'relay', 'NOW',
    toolGlobals + TOOL_SRC +
    '\nreturn { tool_write_file, tool_edit_file, tool_delete_file };')(
    FS, MT, POSTED, relayDispatch, nowMs);

  // A non-tool OPFS writer (pyodide / walios bridge) that marks via the shared
  // ledger module instead of the sw-opfs-changed relay.
  world.writeViaLedgerApi = (rel, text) => {
    FS.set(rel, text); MT.set(rel, nowMs());
    sandbox.SandpieDbxSyncState.markDirty(rel);
  };
  // A raw OPFS writer that marks nothing at all (the walios pre-fix behaviour).
  world.writeUnmarked = (rel, text) => { FS.set(rel, text); MT.set(rel, nowMs()); };
  // A worker-style writer that posts sw-opfs-changed directly (pyodide relay).
  world.writeViaPost = (rel, text) => {
    FS.set(rel, text); MT.set(rel, nowMs());
    relayDispatch({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: [rel] } });
  };

  world.seedTokens = () => {
    LSMAP.set('dbxfull-tokens', JSON.stringify({
      access_token: 'tok', refresh_token: 'refresh', expires_at: Date.now() + 3600e3,
    }));
  };
  world.sync = async (o) => {
    if (!world.provider) throw new Error('no sync provider registered — dropbox.js did not boot');
    return world.provider.sync(o);
  };
  world.flushBeforeReload = async (o) => world.provider.flushBeforeReload(o);
  return world;
}

// Boot a connected world and complete the first sync, so tests start from a
// steady state (tokens present, cursor established).
//
// The cloud is ALWAYS seeded with one file. sync() has a guard (C3) that skips
// both destructive cleanup passes when the cloud listing comes back empty, on
// the grounds that an empty listing is probably a transient failure rather than
// "the user deleted everything". An empty fake cloud therefore disables exactly
// the code the orphan-cleanup tests exist to exercise, and they would pass for
// the wrong reason.
export const CLOUD_SEED = 'sandpie/config/.seed.json';

export async function connectedWorld(opts = {}) {
  const w = makeWorld({ ...opts, cloud: { [CLOUD_SEED]: '{}', ...(opts.cloud || {}) } });
  w.seedTokens();
  await w.sync();
  return w;
}

// Deletions run fire-and-forget off the file:deleted event (and retry through
// the pending-delete handshake), so a test has to wait for the ledger to drain
// rather than a fixed tick.
export async function settleDeletes(w, ms = 500) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const pend = JSON.parse(w.LSMAP.get('dbxfull-pending-deletes') || '[]');
    if (!pend.length) return true;
    await new Promise((r) => setTimeout(r, 10));
  }
  return false;
}

export function runner() {
  let passed = 0, failed = 0;
  const fails = [];
  return {
    ok(cond, label, extra) {
      if (cond) { passed++; console.log('  ok    ' + label); }
      else {
        failed++; fails.push(label);
        console.log('  FAIL  ' + label + (extra !== undefined ? '\n          got: ' + JSON.stringify(extra).slice(0, 300) : ''));
      }
    },
    // A behaviour that is currently broken. Reports, never fails the suite.
    known(cond, label, note) {
      if (cond) console.log('  ok    ' + label + '  (known bug now FIXED — promote to ok())');
      else console.log('  KNOWN ' + label + (note ? '\n          ' + note : ''));
    },
    group(name) { console.log('\n' + name); },
    done(title) {
      console.log('\n' + title + ': ' + passed + ' passed, ' + failed + ' failed');
      if (failed) { console.log('failing:\n  - ' + fails.join('\n  - ')); process.exitCode = 1; }
      return failed;
    },
  };
}
