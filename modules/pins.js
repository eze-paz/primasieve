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
    // Reorder to exactly `order`. Only a PERMUTATION of what is already pinned is
    // accepted — a drag that raced an unpin (or a stale DOM read) must not be able
    // to drop or resurrect pins. Anything the caller missed keeps its place at the
    // end rather than vanishing.
    reorder(order) {
      const want = uniqNorm(order).filter(p => cache.indexOf(p) !== -1);
      const rest = cache.filter(p => want.indexOf(p) === -1);
      const next = want.concat(rest);
      if (same(next, cache)) return cache.slice();
      return persist(next).slice();
    },
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

  /* ─────────────── thumbnails ─────────────── */
  // Best-effort, offline, per-file thumbnails for the home grid:
  //   • image files  → the image itself
  //   • HTML         → og:image / apple-touch-icon / favicon declared in <head>, whether
  //                    embedded (data:) or a sibling OPFS file; else the theme-color tint
  //   • everything else → the typed extension badge (handled inline in renderHome)
  // Nothing is fetched from the network and no page is executed/rendered — we only read OPFS
  // bytes and parse declared metadata with a DETACHED DOMParser (runs no scripts, loads nothing).
  const THUMB_IMG_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'svg', 'ico']);
  const THUMB_MAX_BYTES = 8 * 1024 * 1024;     // don't inline a huge image for a 60px tile
  const HTML_HEAD_BYTES = 1 * 1024 * 1024;     // only <head> is needed; cap the read
  let liveThumbUrls = [];                        // object URLs from the current render, revoked on the next

  function mimeForExt(ext) {
    return ({ png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp',
      bmp: 'image/bmp', avif: 'image/avif', svg: 'image/svg+xml', ico: 'image/x-icon' })[ext] || 'application/octet-stream';
  }
  async function getFile(path) {
    const parts = path.split('/').filter(Boolean); const name = parts.pop();
    const dir = await opfs.resolveDir(parts);
    return (await dir.getFileHandle(name)).getFile();
  }
  // Object URL for an image File. OPFS Files often have an empty type, which breaks SVG (and
  // strict image decoders), so re-wrap in a Blob with the extension's MIME when type is missing.
  async function urlForImageFile(f, ext) {
    if (f.type) return URL.createObjectURL(f);
    return URL.createObjectURL(new Blob([await f.arrayBuffer()], { type: mimeForExt(ext) }));
  }
  // Best thumbnail source declared in an HTML <head>: og/twitter image, then apple-touch-icon,
  // then the largest favicon.
  function pickHtmlThumbHref(doc) {
    const meta = doc.querySelector('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"], meta[property="twitter:image"]');
    const mc = meta && meta.getAttribute('content');
    if (mc && mc.trim()) return mc.trim();
    const apple = doc.querySelector('link[rel~="apple-touch-icon"]');
    const ah = apple && apple.getAttribute('href');
    if (ah && ah.trim()) return ah.trim();
    const icons = Array.prototype.filter.call(doc.querySelectorAll('link[rel]'),
      l => /(^|\s)(shortcut\s+)?icon(\s|$)/i.test(l.getAttribute('rel') || ''));
    icons.sort((a, b) => (parseInt(b.getAttribute('sizes')) || 0) - (parseInt(a.getAttribute('sizes')) || 0));
    const ih = icons[0] && icons[0].getAttribute('href');
    return (ih && ih.trim()) || null;
  }
  // Resolve an href from an HTML file → { data } (inline), { path } (sibling OPFS file), or
  // null (external URL, skipped to stay offline). Relative paths resolve against the file's dir.
  function resolveHref(basePath, href) {
    if (/^data:/i.test(href)) return { data: href };
    if (/^[a-z][a-z0-9+.\-]*:/i.test(href) || href.startsWith('//')) return null;   // http(s):/mailto:/protocol-relative → external
    let rel;
    if (href[0] === '/') rel = href.replace(/^\/+/, '');
    else {
      const segs = basePath.includes('/') ? basePath.slice(0, basePath.lastIndexOf('/')).split('/').filter(Boolean) : [];
      for (const s of href.split('/')) { if (s === '' || s === '.') continue; if (s === '..') segs.pop(); else segs.push(s); }
      rel = segs.join('/');
    }
    return { path: rel.replace(/[?#].*$/, '') };
  }
  // Resolve a thumbnail for `path`. Returns { url?, src?, tint? } or null (→ keep the badge).
  async function loadThumb(path, ext) {
    if (!(window.opfs && opfs.resolveDir)) return null;
    try {
      if (THUMB_IMG_EXTS.has(ext)) {
        const f = await getFile(path);
        if (f.size > THUMB_MAX_BYTES) return null;
        return { url: await urlForImageFile(f, ext) };
      }
      if (ext === 'html' || ext === 'htm') {
        const f = await getFile(path);
        const head = await f.slice(0, Math.min(f.size, HTML_HEAD_BYTES)).text();
        const doc = new DOMParser().parseFromString(head, 'text/html');
        const tint = (doc.querySelector('meta[name="theme-color"]') || {}).content || null;
        const href = pickHtmlThumbHref(doc);
        if (!href) return { tint };
        const r = resolveHref(path, href);
        if (!r) return { tint };                                  // external → badge (+tint), no image
        if (r.data) return { src: r.data, tint };
        const f2 = await getFile(r.path);
        if (f2.size > THUMB_MAX_BYTES) return { tint };
        return { url: await urlForImageFile(f2, (r.path.split('.').pop() || '').toLowerCase()), tint };
      }
    } catch (_) {}
    return null;
  }
  // Apply a resolved thumbnail to a tile's .pin-thumb — swaps the badge for an <img> once it
  // decodes. Safe against stale re-renders (checks isConnected; revokes orphaned object URLs).
  async function applyThumb(thumbEl, path, ext) {
    const res = await loadThumb(path, ext);
    if (!res || !thumbEl.isConnected) { if (res && res.url) URL.revokeObjectURL(res.url); return; }
    if (res.tint) thumbEl.style.background = res.tint;
    const src = res.url || res.src;
    if (!src) return;
    if (res.url) liveThumbUrls.push(res.url);
    const img = document.createElement('img');
    img.className = 'pin-thumb-img'; img.alt = '';
    // An <img> is natively draggable, and Chromium puts 'Files' in the dataTransfer
    // for one it can materialise — so pressing a thumbnail to reorder started a
    // real file drag and raised the "Drop files to attach" overlay instead.
    img.draggable = false;
    img.onload = () => { if (thumbEl.isConnected) { thumbEl.textContent = ''; thumbEl.appendChild(img); thumbEl.classList.add('has-thumb'); } };
    img.onerror = () => { if (res.url) { URL.revokeObjectURL(res.url); const i = liveThumbUrls.indexOf(res.url); if (i >= 0) liveThumbUrls.splice(i, 1); } };
    img.src = src;
  }

  /* ── always-present "+Add" tile (opens Settings → Sharing) ───────────── */
  function buildAddTile() {
    const tile = document.createElement('div');
    tile.className = 'pin-tile add-tile';
    tile.title = 'Apps from the team hub';
    const icon = document.createElement('div');
    icon.className = 'add-icon';
    icon.innerHTML = '+<span class="add-count" id="addCount">0</span>';
    const label = document.createElement('div');
    label.className = 'add-label'; label.textContent = 'Add';
    tile.append(icon, label);
    tile.onclick = () => { try { if (window.SandpieSettings) SandpieSettings.open('sharing'); } catch (_) {} };
    return tile;
  }
  async function refreshAddCount() {
    const el = document.getElementById('addCount');
    if (!el) return;
    try {
      if (window.SandpieSharing && SandpieSharing.acceptedList) {
        const n = (await SandpieSharing.acceptedList()).length;
        el.textContent = n;
      }
    } catch (_) {}
  }

  /* ─────────────── home-screen "Pinned" list (rendered into #welcome) ─────────────── */
  function renderHome() {
    for (const u of liveThumbUrls) { try { URL.revokeObjectURL(u); } catch (_) {} }
    liveThumbUrls = [];
    // Home lists share one centered parent (#homeCenter holds pinnedHome; the shared/team list now lives in Settings → Sharing).
    const host = document.getElementById('homeCenter') || document.getElementById('messages');
    if (!host) return;
    let box = document.getElementById('pinnedHome');
    if (!box) {
      box = document.createElement('div');
      box.id = 'pinnedHome';
      box.className = 'pinned-home';
      // #messages fallback: its last children are the command panel + sticky
      // composer, so a bare appendChild would put the grid BELOW them.
      if (typeof window.appendContent === 'function') window.appendContent(host, box);
      else host.appendChild(box);
    }
    const list = Pins.list();
    box.textContent = '';
    box.style.display = '';
    const addTile = buildAddTile();
    if (!list.length) {   // the always-present +Add tile IS the empty state now
      box.appendChild(addTile);
      refreshAddCount();
      return;
    }

    // App-style grid of tiles (phone home-screen feel): thumbnail placeholder +
    // short label (filename, no path, no extension). Click a tile → open in viewer.
    // Shared/team pins point at a file inside the package
    // (sandpie/shared-installed/<id>/<file>). Show the FOLDER name instead of the
    // file basename — consistent with the Shared with me / Team artifacts lists.
    // The installed mirror (written by sharing.js renderHome) maps id → title.
    let installedTitles = null;
    try { installedTitles = JSON.parse(localStorage.getItem('sharing-installed-cache') || 'null'); } catch (_) {}
    const titleFor = (path) => {
      const m = /^sandpie\/shared-installed\/([^\/]+)\//.exec(path);
      if (m && Array.isArray(installedTitles)) {
        const hit = installedTitles.find(x => x && x.id === m[1]);
        if (hit && hit.title) return hit.title;
      }
      return null;
    };
    const grid = document.createElement('div');
    grid.className = 'pin-grid';
    for (const path of list) {
      const fname = path.split('/').pop();
      const dot = fname.lastIndexOf('.');
      const folderTitle = titleFor(path);
      const shortName = folderTitle || (dot > 0 ? fname.slice(0, dot) : fname);   // folder name, else basename minus ext
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
      applyThumb(thumb, path, ext);   // async: swaps in a real thumbnail if one can be resolved

      const label = document.createElement('div');
      label.className = 'pin-tile-label';
      label.textContent = shortName;

      const unpin = document.createElement('button');
      unpin.className = 'pin-tile-unpin';
      unpin.title = 'Unpin';
      unpin.textContent = '✕';
      unpin.onclick = (e) => { e.stopPropagation(); Pins.remove(path); };

      tile.append(open, label, unpin);
      tile.dataset.path = path;
      grid.appendChild(tile);
    }
    grid.appendChild(buildAddTile());
    box.appendChild(grid);
    wireReorder(grid);
    refreshAddCount();
  }

  /* ─────────────── drag to reorder ───────────────
     Pointer Events rather than HTML5 drag-and-drop, because DnD does not fire on
     touch and the grid is used on phones. Mouse starts dragging after a few pixels
     of movement; touch requires a short hold first, so an ordinary swipe still
     scrolls the page. While dragging we preventDefault on touchmove (needs a
     non-passive listener) — that is what actually stops the scroll, since changing
     touch-action mid-gesture has no effect. */
  const DRAG_SLOP = 6;        // px before a mouse press counts as a drag
  const TOUCH_HOLD = 220;     // ms to hold before a touch starts dragging
  function wireReorder(grid) {
    let tile = null, dragging = false, holdTimer = null, startX = 0, startY = 0, moved = false;

    const cleanup = () => {
      clearTimeout(holdTimer); holdTimer = null;
      if (tile) tile.classList.remove('pin-dragging');
      grid.classList.remove('pin-reordering');
      tile = null; dragging = false; moved = false;
    };
    const begin = (pointerId) => {
      if (!tile || dragging) return;
      dragging = true;
      // Capture only NOW, never on pointerdown. While the grid holds the capture,
      // pointerdown and pointerup both target the grid, so the browser fires click
      // on the grid instead of the tile's button — which silently killed opening a
      // pinned file by clicking it.
      if (pointerId != null) { try { grid.setPointerCapture(pointerId); } catch (_) {} }
      tile.classList.add('pin-dragging');
      grid.classList.add('pin-reordering');
    };
    // Insert the dragged tile before or after whichever tile the pointer is over,
    // picking the side by the midpoint so the swap feels like it follows the cursor.
    const moveOver = (x, y) => {
      const el = document.elementFromPoint(x, y);
      const over = el && el.closest ? el.closest('.pin-tile') : null;
      if (!over || over === tile || over.parentNode !== grid) return;
      const r = over.getBoundingClientRect();
      const after = (x - r.left) > r.width / 2;
      grid.insertBefore(tile, after ? over.nextSibling : over);
    };
    // `click` fires AFTER pointerup, by which point cleanup() has reset state — so
    // the suppression flag has to outlive it. Cleared on the next task.
    let suppressClick = false;
    const commit = () => {
      if (dragging) {
        const order = [...grid.querySelectorAll('.pin-tile')].map(t => t.dataset.path).filter(Boolean);
        Pins.reorder(order);   // fires sandpie-pins-changed → renderHome repaints from the new order
      }
      if (moved) { suppressClick = true; setTimeout(() => { suppressClick = false; }, 0); }
      cleanup();
    };
    grid.addEventListener('click', (e) => { if (suppressClick) { e.preventDefault(); e.stopPropagation(); } }, true);

    // Belt and braces for the same problem: anything inside the grid that the
    // browser considers draggable (a thumbnail, a selected label) must never start
    // a native HTML5 drag. One suppressed dragstart covers every such element,
    // including ones added later by the async thumbnailer.
    grid.addEventListener('dragstart', (e) => { e.preventDefault(); e.stopPropagation(); });
    grid.addEventListener('pointerdown', (e) => {
      if (e.button != null && e.button !== 0) return;
      const t = e.target.closest ? e.target.closest('.pin-tile') : null;
      if (!t || (e.target.closest && e.target.closest('.pin-tile-unpin'))) return;
      tile = t; startX = e.clientX; startY = e.clientY; moved = false;
      // No pointer capture here — see begin(). A plain click must reach the tile.
      if (e.pointerType === 'touch') { const id = e.pointerId; holdTimer = setTimeout(() => begin(id), TOUCH_HOLD); }
    });
    grid.addEventListener('pointermove', (e) => {
      if (!tile) return;
      if (Math.abs(e.clientX - startX) > DRAG_SLOP || Math.abs(e.clientY - startY) > DRAG_SLOP) {
        moved = true;
        if (!dragging && e.pointerType !== 'touch') begin(e.pointerId);
        // A touch that moves before the hold elapses is a scroll, not a drag.
        if (!dragging && e.pointerType === 'touch') { clearTimeout(holdTimer); cleanup(); return; }
      }
      if (dragging) moveOver(e.clientX, e.clientY);
    });
    // Non-passive: preventDefault here is what keeps the page still mid-drag.
    grid.addEventListener('touchmove', (e) => { if (dragging) e.preventDefault(); }, { passive: false });
    grid.addEventListener('pointerup', commit);
    grid.addEventListener('pointercancel', cleanup);
  }

  function init() {
    renderHome();
    Pins.subscribe(renderHome);
    refreshFromDisk();                                  // reconcile with the synced OPFS file at boot
    window.addEventListener('focus', refreshFromDisk);  // pick up pins.json pulled from another device
    // The +Add badge follows the team hub (sharing.js dispatches on change).
    window.addEventListener('sandpie-shares-changed', refreshAddCount);
    try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('sync:done', refreshAddCount); } catch (_) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
