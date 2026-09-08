// Single source of truth for the Dropbox sync LEDGER (localStorage
// 'dbxfull-sync-state'), shared by modules/dropbox.js and /walios/terminal.html.
//
// Why this exists
// ---------------
// dropbox.js decides what to delete from the entry a file has here:
//
//   syncedMtime === 0   -> dirty, needs upload  -> KEEP (both cleanup passes)
//   a real mtime        -> clean, matches cloud -> KEEP while the cloud has it
//   NO ENTRY AT ALL     -> orphan               -> opfs.remove()   <-- Pass 2
//
// walios writes into the SAME OPFS root the app syncs (its /root mount has no
// subdir sandbox), through its own opfs-worker bridge, and recorded nothing here.
// So every file a shell created -- a whole `git clone` -- was an orphan, and the
// next cleanup deleted it. Only the FILES: opfs.list() returns files and recurses
// through directories without listing them, which is why the directory skeleton
// survived and looked like an empty tree rather than a deletion.
//
// Anything that writes to OPFS outside dropbox.js must therefore mark what it
// wrote, and this is the one implementation of "mark".
//
// Plain classic script on purpose, like modules/walios-backend.js and
// modules/dbx-token.js: the consumers include a <script> tag and a classic
// Worker, neither of which can `import`.

(function (g) {
  'use strict';

  const STATE_KEY = 'dbxfull-sync-state';

  function read() {
    try { return JSON.parse(localStorage.getItem(STATE_KEY) || '{}'); } catch { return {}; }
  }
  // A FAILED write silently recreates the very bug this module exists to stop: the
  // files stay unmarked, so the next cleanup deletes them as orphans. localStorage is
  // ~5MB and the ledger costs ~64 bytes per file, so this only bites on a very large
  // tree -- but it must never fail quietly. Callers can watch for 'dbx:ledger-error'.
  let warned = false;
  function write(s) {
    try { localStorage.setItem(STATE_KEY, JSON.stringify(s)); return true; }
    catch (e) {
      const msg = (e && e.message) || String(e);
      if (!warned) {
        warned = true;
        console.error('[dbx-syncstate] could not write the sync ledger:', msg,
                      '- files written from now on may be treated as orphans and deleted');
      }
      try { g.dispatchEvent(new CustomEvent('dbx:ledger-error', { detail: { error: msg } })); } catch {}
      return false;
    }
  }

  const norm = (p) => String(p).replace(/^\/+/, '');

  // Mark paths as locally modified and awaiting upload. Idempotent; a file that is
  // already dirty stays dirty, and a clean entry is demoted to dirty (its cloud rev
  // is kept so a conditional update can still use it).
  //
  // Re-reads immediately before writing: the app and a walios tab are different
  // documents sharing one localStorage, and a read-modify-write over a stale copy
  // would drop the other's marks.
  function markDirty(paths) {
    const list = (Array.isArray(paths) ? paths : [paths]).map(norm).filter(Boolean);
    if (!list.length) return 0;
    const st = read();
    let changed = 0;
    for (const rel of list) {
      if (st[rel] && st[rel].syncedMtime === 0) continue;      // already pending
      st[rel] = { rev: (st[rel] && st[rel].rev) || '', size: (st[rel] && st[rel].size) || 0, syncedMtime: 0 };
      changed++;
    }
    if (changed) write(st);
    return changed;
  }

  // Record a file that was just brought DOWN from Dropbox, i.e. already identical
  // to the cloud copy. Marking these dirty would upload them straight back.
  function markClean(rel, { rev = '', size = 0, mtime = Date.now() } = {}) {
    const r = norm(rel); if (!r) return;
    const st = read();
    st[r] = { rev, size, syncedMtime: mtime };
    write(st);
  }

  // Drop entries for paths that no longer exist locally.
  function forget(paths) {
    const list = (Array.isArray(paths) ? paths : [paths]).map(norm).filter(Boolean);
    if (!list.length) return;
    const st = read();
    let changed = false;
    for (const rel of list) if (st[rel]) { delete st[rel]; changed = true; }
    if (changed) write(st);
  }

  function dirtyPaths() {
    const st = read();
    return Object.keys(st).filter((k) => st[k] && st[k].syncedMtime === 0);
  }

  g.SandpieDbxSyncState = { STATE_KEY, read, write, markDirty, markClean, forget, dirtyPaths };
})(typeof self !== 'undefined' ? self : globalThis);
