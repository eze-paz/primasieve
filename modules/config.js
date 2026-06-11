// sandpie /modules/config.js — SandpieConfig: one coherent, OPFS-backed config store.
//
// Joins every module's settings into a single namespaced JSON object:
//   { __version: 1, appearance: {...}, providers: [...], cloud: {...}, ... }
// Each module owns its namespace; SandpieConfig never interprets the value
// (array, object, scalar — opaque). Dependencies flow ONE way: modules depend
// on SandpieConfig; SandpieConfig names no specific module.
//
// Two tiers of storage, same idea as the old prefs module:
//   • localStorage mirror ('sandpie-config') — synchronous, so the UI can read
//     config instantly on boot without awaiting OPFS.
//   • OPFS file ('sandpie_config.json') — the durable copy. Because it lives in
//     the synced OPFS root, the EXISTING Dropbox sync engine carries it to a
//     user's other devices for free: a write emits 'file:changed' and the engine
//     pushes it like any other file. No server, no new sync code.
//
// On boot we render from the mirror, then reconcile from OPFS (OPFS wins — it is
// the cross-device truth). NO secrets belong here: API keys and tokens stay in
// their own per-device localStorage, never in this synced blob.
//
// Optional, like every sandpie module: if config.js isn't loaded, callers fall
// back to their own localStorage and nothing breaks. SandpieConfig itself needs
// only window.opfs (degrades to mirror-only without it) and, when present, the
// Sandpie event bus to trigger sync.
//
// CLASSIC script (global window.SandpieConfig). Load after core.js, before the
// modules that read config.

const SandpieConfig = (() => {
  const LS_KEY    = 'sandpie-config';
  const OPFS_PATH = 'sandpie_config.json';
  const VERSION   = 1;
  const WRITE_DEBOUNCE_MS = 250;

  const listeners = new Map();   // ns -> Set<cb>;  '*' -> Set<cb> (any change)
  let _cache = loadMirror();
  if (typeof _cache.__version !== 'number') _cache.__version = VERSION;

  let _readyResolve;
  const _ready = new Promise((r) => { _readyResolve = r; });

  // ── localStorage mirror (synchronous) ──
  function loadMirror() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; }
    catch (_) { return {}; }
  }
  function persistMirror() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(_cache)); } catch (_) {}
  }

  function notify(ns) {
    for (const cb of (listeners.get(ns) || [])) { try { cb(_cache[ns]); } catch (e) { console.warn('[SandpieConfig] listener error:', e); } }
    for (const cb of (listeners.get('*') || [])) { try { cb(_cache); } catch (e) { console.warn('[SandpieConfig] listener error:', e); } }
  }

  // ── OPFS (durable + synced) ──
  let _writeTimer = null;
  let _lastWritten = null;   // last JSON we wrote, so a no-op write stays a no-op
  function scheduleWrite() {
    clearTimeout(_writeTimer);
    _writeTimer = setTimeout(flush, WRITE_DEBOUNCE_MS);
  }
  async function flush() {
    if (!window.opfs) return;
    const json = JSON.stringify(_cache, null, 2);
    if (json === _lastWritten) return;
    try {
      await opfs.write(OPFS_PATH, json);
      _lastWritten = json;
      // Mark dirty for the sync engine — same hook opfs.js's file save uses.
      try { if (window.Sandpie) Sandpie.events.emit('file:changed', OPFS_PATH); } catch (_) {}
    } catch (e) { console.warn('[SandpieConfig] OPFS write failed:', e && e.message); }
  }

  // Read the durable copy and adopt it (OPFS wins — it carries other devices'
  // changes). Diffs against the current cache so it's a no-op (and loop-safe)
  // when nothing changed, e.g. when our own write echoes back as 'file:changed'.
  async function reconcileFromOpfs() {
    if (!window.opfs) return;
    let text;
    try { text = await opfs.read(OPFS_PATH); }
    catch (_) { return; }   // no durable copy yet — mirror/defaults stand
    let incoming;
    try { incoming = JSON.parse(text); } catch (_) { return; }
    if (!incoming || typeof incoming !== 'object') return;
    if (JSON.stringify(incoming) === JSON.stringify(_cache)) { _lastWritten = JSON.stringify(_cache, null, 2); return; }
    const touched = new Set([...Object.keys(_cache), ...Object.keys(incoming)]);
    _cache = incoming;
    if (typeof _cache.__version !== 'number') _cache.__version = VERSION;
    persistMirror();
    _lastWritten = JSON.stringify(_cache, null, 2);
    for (const ns of touched) if (ns !== '__version') notify(ns);
  }

  // ── public API ──
  // get(ns, default?) — returns the live stored value (treat as read-only; use
  //                     set/update to change). Missing → default.
  function get(ns, dflt) {
    return (ns in _cache && _cache[ns] !== undefined) ? _cache[ns] : dflt;
  }
  // set(ns, value) — replace a namespace wholesale. No-op (no notify, no write)
  // when the value is unchanged: avoids spurious notifications — and the
  // feedback loops they cause when a subscriber re-sets its own namespace — plus
  // redundant OPFS writes and syncs.
  function set(ns, value) {
    if ((ns in _cache) && JSON.stringify(_cache[ns]) === JSON.stringify(value)) return value;
    _cache[ns] = value;
    persistMirror();
    notify(ns);
    scheduleWrite();
    return value;
  }
  // update(ns, partial) — shallow-merge into an object namespace.
  function update(ns, partial) {
    const cur = (_cache[ns] && typeof _cache[ns] === 'object' && !Array.isArray(_cache[ns])) ? _cache[ns] : {};
    return set(ns, { ...cur, ...(partial && typeof partial === 'object' ? partial : {}) });
  }
  function getAll() { try { return JSON.parse(JSON.stringify(_cache)); } catch (_) { return {}; } }
  // subscribe(ns, cb) or subscribe(cb) for any change. Returns an unsubscribe fn.
  function subscribe(ns, cb) {
    if (typeof ns === 'function') { cb = ns; ns = '*'; }
    let s = listeners.get(ns); if (!s) listeners.set(ns, s = new Set());
    s.add(cb);
    return () => s.delete(cb);
  }
  // ready() — resolves (with a snapshot) after the first OPFS reconcile, so
  // callers can safely run one-time migrations against the durable copy.
  function ready() { return _ready; }

  // ── boot: reconcile from OPFS once the page (and opfs) are available ──
  function boot() {
    reconcileFromOpfs().finally(() => { try { _readyResolve(getAll()); } catch (_) {} });
    // If anything rewrites our file (e.g. the sync engine pulling a newer copy
    // from another device), re-adopt it. The diff check keeps our own writes
    // from looping.
    try { if (window.Sandpie) Sandpie.events.on('file:changed', (p) => { if (p === OPFS_PATH) reconcileFromOpfs(); }); } catch (_) {}
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', (ev) => {
        const d = ev.data;
        if (d && (d.type === 'sw-opfs-changed' || d.type === 'opfs-changed') && Array.isArray(d.paths) && d.paths.includes(OPFS_PATH)) reconcileFromOpfs();
      });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  return { get, set, update, getAll, subscribe, ready, OPFS_PATH };
})();
window.SandpieConfig = SandpieConfig;
