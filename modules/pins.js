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
  const NS = 'pinnedFiles';
  const LS_KEY = 'sandpie-pinned-files';   // fallback when SandpieConfig isn't loaded

  // Canonical path form: strip leading slashes only. We deliberately do NOT strip a
  // 'files/' prefix — front-end paths (it.fullKey / artifact clean / _openFilePath)
  // are already OPFS-root-relative without it, and stripping it could corrupt a real
  // top-level 'files' folder path.
  function norm(p) { return String(p == null ? '' : p).replace(/^\/+/, '').trim(); }

  function read() {
    const c = window.SandpieConfig;
    if (c) { const v = c.get(NS, null); if (Array.isArray(v)) return v.map(norm).filter(Boolean); }
    try { const raw = localStorage.getItem(LS_KEY); if (raw) { const a = JSON.parse(raw); if (Array.isArray(a)) return a.map(norm).filter(Boolean); } } catch (_) {}
    return [];
  }

  function write(list) {
    const seen = new Set(), uniq = [];
    for (const p of list) { const n = norm(p); if (n && !seen.has(n)) { seen.add(n); uniq.push(n); } }
    const c = window.SandpieConfig;
    if (c) c.set(NS, uniq);
    else { try { localStorage.setItem(LS_KEY, JSON.stringify(uniq)); } catch (_) {} }
    try { window.dispatchEvent(new CustomEvent('sandpie-pins-changed', { detail: uniq })); } catch (_) {}
    return uniq;
  }

  const Pins = {
    list() { return read(); },
    isPinned(p) { const n = norm(p); return n ? read().indexOf(n) !== -1 : false; },
    add(p) { const n = norm(p); if (!n) return false; const l = read(); if (l.indexOf(n) === -1) { l.push(n); write(l); } return true; },
    remove(p) { const n = norm(p); write(read().filter(x => x !== n)); return false; },
    toggle(p) { return this.isPinned(p) ? this.remove(p) : this.add(p); },
    subscribe(cb) {
      const h = (e) => cb((e && e.detail) || read());
      window.addEventListener('sandpie-pins-changed', h);
      return () => window.removeEventListener('sandpie-pins-changed', h);
    },
    // Wire an already-styled button (any class) as a self-updating pin toggle for `path`.
    // Reflects current state (📌 + .pinned class + title), toggles on click, and stays in
    // sync with other surfaces via a self-cleaning subscription (drops itself once the
    // button leaves the DOM).
    bindButton(btn, path) {
      if (!btn) return btn;
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

    const title = document.createElement('div');
    title.className = 'pinned-home-title';
    title.textContent = '📌 Pinned';
    box.appendChild(title);

    const rows = document.createElement('div');
    rows.className = 'pinned-list';
    for (const path of list) {
      const name = path.split('/').pop();
      const row = document.createElement('div');
      row.className = 'pinned-file';
      row.title = path;

      const open = document.createElement('button');
      open.className = 'pinned-file-open';
      open.textContent = name;
      open.onclick = () => { try { if (window.opfs && opfs.openFile) opfs.openFile(path, name); } catch (_) {} };

      const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
      if (dir) { const d = document.createElement('span'); d.className = 'pinned-file-dir'; d.textContent = dir + '/'; open.prepend(d); }

      const unpin = document.createElement('button');
      unpin.className = 'pinned-file-unpin';
      unpin.title = 'Unpin';
      unpin.textContent = '✕';
      unpin.onclick = (e) => { e.stopPropagation(); Pins.remove(path); };

      row.appendChild(open);
      row.appendChild(unpin);
      rows.appendChild(row);
    }
    box.appendChild(rows);
  }

  function init() { renderHome(); Pins.subscribe(renderHome); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
