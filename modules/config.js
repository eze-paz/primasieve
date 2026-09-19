// sandpie /modules/config.js — SandpieConfig: one coherent config store (localStorage).
//
// Joins every module's settings into a single namespaced JSON object:
//   { __version: 1, appearance: {...}, providers: [...], cloud: {...}, ... }
// Each module owns its namespace; SandpieConfig never interprets the value
// (array, object, scalar — opaque). Dependencies flow ONE way: modules depend
// on SandpieConfig; SandpieConfig names no specific module.
//
// Storage: localStorage ('sandpie-config') ONLY. It is per-device and is NOT a
// visible/synced OPFS file. The old durable copy 'sandpie_config.json' was
// removed — it lived in the synced OPFS root, so it showed in the file browser
// and synced to Dropbox, which we don't want. Consequence: config no longer
// syncs across devices. NO secrets belong here anyway (API keys/tokens stay in
// their own per-device localStorage).
//
// On first load after this change, any config that lived ONLY in the old OPFS
// file (e.g. carried from another device by Dropbox) is adopted into the mirror,
// then the file is removed locally and from Dropbox.
//
// Optional, like every sandpie module: if config.js isn't loaded, callers fall
// back to their own localStorage and nothing breaks.
//
// CLASSIC script (global window.SandpieConfig). Load after core.js, before the
// modules that read config.

const SandpieConfig = (() => {
  const LS_KEY    = 'sandpie-config';
  const OPFS_PATH = 'sandpie_config.json';   // legacy — migrated off + deleted on boot
  const VERSION   = 1;

  const listeners = new Map();   // ns -> Set<cb>;  '*' -> Set<cb> (any change)
  let _cache = loadMirror();
  if (typeof _cache.__version !== 'number') _cache.__version = VERSION;

  let _readyResolve;
  const _ready = new Promise((r) => { _readyResolve = r; });

  // ── localStorage store (synchronous) ──
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

  // ── public API ──
  // get(ns, default?) — returns the live stored value (treat as read-only; use
  //                     set/update to change). Missing → default.
  function get(ns, dflt) {
    return (ns in _cache && _cache[ns] !== undefined) ? _cache[ns] : dflt;
  }
  // set(ns, value) — replace a namespace wholesale. No-op (no notify/persist)
  // when the value is unchanged: avoids spurious notifications and the feedback
  // loops they cause when a subscriber re-sets its own namespace.
  function set(ns, value) {
    if ((ns in _cache) && JSON.stringify(_cache[ns]) === JSON.stringify(value)) return value;
    _cache[ns] = value;
    persistMirror();
    notify(ns);
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
  // ready() — resolves (with a snapshot) after the one-time migration, so callers
  // can safely run their own one-time migrations against the loaded config.
  function ready() { return _ready; }

  // ── legacy OPFS-file adoption (idempotent; flag 'sandpie-config-migrated' retired 2026-09-18) ──
  // Adopt any namespaces the local mirror is missing (so another device's
  // settings carried in the old synced file aren't lost), then remove the file
  // locally and from Dropbox (via the standard file:deleted event — its listener
  // is registered by dropbox's boot, which runs before this async resumes).
  async function migrateOffOpfs() {
    if (window.opfs) {
      try {
        let text = null;
        try { text = await opfs.read(OPFS_PATH); } catch (_) {}
        if (text == null) {   // maybe a dehydrated placeholder — hydrate then read
          try {
            const sp = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
            if (sp && sp.hydrate) { await sp.hydrate(OPFS_PATH); text = await opfs.read(OPFS_PATH); }
          } catch (_) {}
        }
        if (text != null) {
          let incoming = null; try { incoming = JSON.parse(text); } catch (_) {}
          if (incoming && typeof incoming === 'object') {
            let changed = false;
            for (const ns of Object.keys(incoming)) {
              if (ns === '__version') continue;
              if (!(ns in _cache)) { _cache[ns] = incoming[ns]; changed = true; }   // mirror wins; fill gaps only
            }
            if (changed) { persistMirror(); for (const ns of Object.keys(_cache)) if (ns !== '__version') notify(ns); }
          }
        }
        let existed = false; try { existed = await opfs.exists(OPFS_PATH); } catch (_) {}
        try { await opfs.remove(OPFS_PATH); } catch (_) {}
        if (existed && window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', OPFS_PATH);
      } catch (_) {}
    }
  }

  function boot() {
    migrateOffOpfs().finally(() => { try { _readyResolve(getAll()); } catch (_) {} });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  return { get, set, update, getAll, subscribe, ready, OPFS_PATH };
})();
window.SandpieConfig = SandpieConfig;
