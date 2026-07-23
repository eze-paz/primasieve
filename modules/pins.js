// pins.js — "pin any file" feature.
//
// A pinned file is a user-chosen shortcut, surfaced on the home screen (the
// #welcome empty state the user sees on "+ New chat"). Pin state is small,
// per-device UI state → stored in SandpieConfig (localStorage) under the
// 'pinnedFiles' namespace, with a raw-localStorage fallback (same convention as
// notifications.js). Paths are OPFS-root-relative with leading slashes stripped —
// the exact form opfs.openFile / the file-viewer / show_artifact already use.
//
// Public API (window.SandpiePins):
//   list()            -> string[]        pinned paths, in pin order
//   isPinned(path)    -> boolean
//   add(path) / remove(path) / toggle(path)
//   subscribe(cb)     -> unsubscribe fn  (cb receives the new list)
//   bindButton(btn, path)                wire an existing button as a pin toggle
//
// Any surface that pins a file only needs window.SandpiePins.bindButton(btn, path)
// (buttons) or .toggle(path) (menu items). The home-screen list re-renders itself
// on every change via the 'sandpie-pins-changed' event.
(function () {
  'use strict';
  const LS_KEY = 'sandpie-pinned-files';           // instant-boot mirror + offline fallback
  const LEGACY_NS = 'pinnedFiles';                  // pre-sync SandpieConfig namespace (migrated once)
  const OPFS_PATH = 'sandpie/config/pins.json';     // synced source of truth (eager: dropbox EXEMPT_PREFIXES)

  // Canonical path form: strip leading slashes only. We deliberately do NOT strip a
  // 'files/' prefix — front-end paths (it.fullKey / artifact clean / _openFilePath)
  // are already OPFS-root-relative without it, and stripping it could corrupt a real
  // top-level 'files' folder path.
  function norm(p) { return String(p == null ? '' : p).replace(/^\/+/, '').trim(); }
  function uniqNorm(list) {
    const seen = new Set(), out = [];
    for (const p of (list || [])) { const n = norm(p); if (n && !seen.has(n)) { seen.add(n); out.push(n); } }
    return out;
  }
  const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

  // The in-memory cache is the SYNCHRONOUS source for list()/isPinned() (those can't await).
  // Seeded from the localStorage mirror at boot for instant paint, then reconciled with the
  // synced OPFS file (sandpie/config/pins.json) which is authoritative across devices.
  let cache = (() => {
    try { const raw = localStorage.getItem(LS_KEY); if (raw) { const a = JSON.parse(raw); if (Array.isArray(a)) return uniqNorm(a); } } catch (_) {}
    const c = window.SandpieConfig; if (c) { const v = c.get(LEGACY_NS, null); if (Array.isArray(v)) return uniqNorm(v); }  // migrate old local-only pins
    return [];
  })();

  function mirrorLocal(list) { try { localStorage.setItem(LS_KEY, JSON.stringify(list)); } catch (_) {} }
  function fire(list) { try { window.dispatchEvent(new CustomEvent('sandpie-pins-changed', { detail: list })); } catch (_) {} }

  // Write the synced OPFS file and flag it dirty so Dropbox uploads it (file:changed is the
  // same signal createFile/renameEntry use). Fire-and-forget; UI already updated from cache.
  async function writeDisk(list) {
    if (!(window.opfs && opfs.write)) return;
    try {
      await opfs.write(OPFS_PATH, new Blob([JSON.stringify(list)], { type: 'application/json' }));
      if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', OPFS_PATH);
    } catch (e) { console.warn('[pins] OPFS write failed:', e); }
  }

  // Read the synced OPFS file. null = absent/unreadable → keep the current cache.
  async function readDisk() {
    if (!(window.opfs && opfs.readBytes)) return null;
    try {
      const arr = JSON.parse(new TextDecoder().decode(await opfs.readBytes(OPFS_PATH)));
      return Array.isArray(arr) ? uniqNorm(arr) : null;
    } catch (_) { return null; }   // NotFound / parse error
  }

  // Persist a new list: cache + local mirror + change event synchronously, then the OPFS file.
  function persist(list) {
    cache = uniqNorm(list);
    mirrorLocal(cache);
    fire(cache);
    writeDisk(cache);
    return cache;
  }

  // Reconcile the cache with the synced OPFS file — at boot and on window focus (Dropbox may
  // have pulled a newer pins.json from another device). OPFS is authoritative; last-write-wins.
  let seeded = false;
  async function refreshFromDisk() {
    const disk = await readDisk();
    if (disk === null) {
      // No synced file yet: one-time seed from the pins we booted with, so existing
      // localStorage-only pins start syncing across devices.
      if (!seeded) { seeded = true; if (cache.length) await writeDisk(cache); }
      return;
    }
    seeded = true;
    if (!same(disk, cache)) { cache = disk; mirrorLocal(cache); fire(cache); }
  }

  const Pins = {
    list() { return cache.slice(); },
    isPinned(p) { const n = norm(p); return n ? cache.indexOf(n) !== -1 : false; },
    add(p) { const n = norm(p); if (n && cache.indexOf(n) === -1) persist(cache.concat(n)); return true; },
    remove(p) { const n = norm(p); persist(cache.filter(x => x !== n)); return false; },
    toggle(p) { return this.isPinned(p) ? this.remove(p) : this.add(p); },
    refresh() { return refreshFromDisk(); },
    subscribe(cb) {
      const h = (e) => cb((e && e.detail) || cache.slice());
      window.addEventListener('sandpie-pins-changed', h);
      return () => window.removeEventListener('sandpie-pins-changed', h);
    },
    // Wire an already-styled button (any class) as a self-updating pin toggle for `path`.
    // Reflects current state (📌 + .pinned class + title), toggles on click, and stays in
    // sync with other surfaces via a self-cleaning subscription (drops itself once the
    // button leaves the DOM).
    bindButton(btn, path) {
      if (!btn) return btn;
      btn.classList.add('pin-toggle');   // drives the grayscale→accent icon-state CSS
      const refresh = () => {
        const on = Pins.isPinned(path);
        btn.textContent = '📌';
        btn.title = on ? 'Unpin file' : 'Pin file';
        btn.classList.toggle('pinned', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      };
      btn.onclick = (e) => { if (e) { e.preventDefault(); e.stopPropagation(); } Pins.toggle(path); refresh(); };
      refresh();
      const unsub = Pins.subscribe(() => { if (!btn.isConnected) { unsub(); return; } refresh(); });
      return btn;
    },
  };
  window.SandpiePins = Pins;

  /* ─────────────── home-screen "Pinned" list (rendered into #welcome) ─────────────── */
  function renderHome() {
    const welcome = document.getElementById('welcome');
    if (!welcome) return;
    let box = document.getElementById('pinnedHome');
    if (!box) {
      box = document.createElement('div');
      box.id = 'pinnedHome';
      box.className = 'pinned-home';
      welcome.appendChild(box);   // after the title / taglines
    }
    const list = Pins.list();
    box.textContent = '';
    if (!list.length) { box.style.display = 'none'; return; }
    box.style.display = '';

    // App-style grid of tiles (phone home-screen feel): thumbnail placeholder +
    // short label (filename, no path, no extension). Click a tile → open in viewer.
    const grid = document.createElement('div');
    grid.className = 'pin-grid';
    for (const path of list) {
      const fname = path.split('/').pop();
      const dot = fname.lastIndexOf('.');
      const shortName = dot > 0 ? fname.slice(0, dot) : fname;      // drop the extension
      const ext = dot > 0 ? fname.slice(dot + 1).toLowerCase() : '';

      const tile = document.createElement('div');
      tile.className = 'pin-tile';
      tile.title = path;

      const open = document.createElement('button');
      open.className = 'pin-tile-btn';
      open.onclick = () => { try { if (window.opfs && opfs.openFile) opfs.openFile(path, fname); } catch (_) {} };

      // Thumbnail PLACEHOLDER — real per-file thumbnails are TODO. For now a rounded
      // "app icon" tile showing the file's extension; data-ext lets a future
      // thumbnailer target it, and .has-thumb (unused yet) will swap in an <img>.
      const thumb = document.createElement('div');
      thumb.className = 'pin-thumb';
      thumb.dataset.ext = ext;
      thumb.textContent = ext ? ext.toUpperCase() : '📄';
      open.appendChild(thumb);

      const label = document.createElement('div');
      label.className = 'pin-tile-label';
      label.textContent = shortName;

      const unpin = document.createElement('button');
      unpin.className = 'pin-tile-unpin';
      unpin.title = 'Unpin';
      unpin.textContent = '✕';
      unpin.onclick = (e) => { e.stopPropagation(); Pins.remove(path); };

      tile.append(open, label, unpin);
      grid.appendChild(tile);
    }
    box.appendChild(grid);
  }

  function init() {
    renderHome();
    Pins.subscribe(renderHome);
    refreshFromDisk();                                  // reconcile with the synced OPFS file at boot
    window.addEventListener('focus', refreshFromDisk);  // pick up pins.json pulled from another device
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
