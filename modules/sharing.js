// sharing.js — team artifact sync. The whole system:
//   1) look at the team root (e.g. IA/)
//   2) list it (list_folder): first level = DEPARTMENT, second = ARTIFACT name
//   3) every artifact folder you can see → copy its contents into
//      sandpie/shared-installed/<artifact>/ (same name)
//   4) keep the list_folder CURSOR in localStorage (per device, like dbxfull-cursor)
//   5) next poll: list_folder/continue(cursor) → sync only what changed
// That is all. No manifests, no marker files, no 1:1 deliveries, no accept/dismiss.
// Per-device installed state (from/team/seen/dirty) also lives in localStorage.
(function () {
  'use strict';
  const INSTALL_ROOT = 'sandpie/shared-installed';
  const PKG_STATE_KEY = 'sandpie-pkg-state';     // localStorage: { [id]: {from,team,seen,dirty,pin} }
  const HUB_CURSOR_KEY = 'sandpie-share-cursor'; // localStorage: { [teamRoot]: cursor }
  const ID_OVERRIDE_KEY = 'sandpie-share-identity';

  const O = () => window.opfs;
  const prov = () => { try { return window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider(); } catch (_) { return null; } };
  const cloudOn = () => { const p = prov(); return !!(p && p.cloudConnected && p.cloudConnected()); };
  const slug = (s) => String(s || '').toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'pkg';
  const norm = (p) => String(p == null ? '' : p).replace(/^\/+/, '').replace(/\/+$/, '');
  const markDirty = (p) => { try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', p); } catch (_) {} };

  /* ── identity ─────────────────────────────────────────────────────────── */
  function me() {
    try { const o = JSON.parse(localStorage.getItem(ID_OVERRIDE_KEY) || 'null'); if (o && o.user) return { user: String(o.user), teams: Array.isArray(o.teams) ? o.teams : [] }; } catch (_) {}
    let teams = [];
    try { const u = window.SandpieAccount && SandpieAccount.current && SandpieAccount.current(); if (u && Array.isArray(u.teams)) teams = u.teams; } catch (_) {}
    try { const p = prov(); const e = p && p.accountEmail && p.accountEmail(); if (e) return { user: String(e), teams }; } catch (_) {}
    try { const u = window.SandpieAccount && SandpieAccount.current && SandpieAccount.current(); if (u && (u.email || u.name)) return { user: String(u.email || u.name), teams }; } catch (_) {}
    return { user: 'me@local', teams };
  }
  function setIdentity(id) { if (id) localStorage.setItem(ID_OVERRIDE_KEY, JSON.stringify(id)); else localStorage.removeItem(ID_OVERRIDE_KEY); fire(); }

  /* ── per-device installed state (localStorage, like dropbox.js syncState) ── */
  function pkgState() { try { return JSON.parse(localStorage.getItem(PKG_STATE_KEY) || '{}'); } catch (_) { return {}; } }
  function setPkgState(s) { try { localStorage.setItem(PKG_STATE_KEY, JSON.stringify(s)); } catch (_) {} }
  async function readInstalledState(id) {
    const st = pkgState();
    if (st[id]) return st[id];
    // one-time migration from the legacy .sandpie-pkg.json marker (pre-cursor builds)
    try {
      const old = JSON.parse(await O().read(INSTALL_ROOT + '/' + id + '/.sandpie-pkg.json'));
      if (old) {
        const seen = old.revs || {};
        st[id] = { id, title: old.title || id, kind: old.kind || 'folder', pin: old.pin || null, rev: old.rev || 0, from: old.from || 'team', team: old.team || '', seen, dirty: old.dirty || {} };
        setPkgState(st);
        try { await O().remove(INSTALL_ROOT + '/' + id + '/.sandpie-pkg.json'); } catch (_) {}
        return st[id];
      }
    } catch (_) {}
    return null;
  }
  async function writeInstalledState(id, mk) { const st = pkgState(); st[id] = mk; setPkgState(st); }

  /* ── team root + departments ──────────────────────────────────────────── */
  function teamRoot() { const p = prov(); return (cloudOn() && p.cloudParent && p.cloudParent()) || ''; }
  function deptRoot(dept) { const r = teamRoot(); return r ? r + '/' + norm(dept) : ''; }
  // Departments this identity can see (first level under the team root).
  async function teams() {
    const p = prov();
    if (!(cloudOn() && p && p.listTeamFolders)) return [];
    try { return (await p.listTeamFolders()) || []; } catch (_) { return []; }
  }

  /* ── cursor-delta scan of the team root ───────────────────────────────── */
  function hubCursor(root) { try { return JSON.parse(localStorage.getItem(HUB_CURSOR_KEY) || '{}')[root] || null; } catch (_) { return null; } }
  function setHubCursor(root, c) { try { const m = JSON.parse(localStorage.getItem(HUB_CURSOR_KEY) || '{}'); if (!c) delete m[root]; else m[root] = c; localStorage.setItem(HUB_CURSOR_KEY, JSON.stringify(m)); } catch (_) {} }
  // One recursive listing of the team root (IA/): first path segment = department,
  // second = artifact. Returns { [dept]: { [id]: {changed:bool} } }.
  async function scanTeamRoot() {
    const p = prov(), root = teamRoot();
    if (!cloudOn() || !root || !p.cloudListWithCursor) return {};
    const cur = hubCursor(root);
    let result = null;
    if (cur && p.cloudListContinue) { try { result = await p.cloudListContinue(cur, { team: true }); } catch (_) { result = null; } }
    const isFull = !result;
    if (!result) { try { result = await p.cloudListWithCursor(root, { team: true }); } catch (e) { if (String((e && e.message) || e).includes('not_found')) return {}; throw e; } }
    setHubCursor(root, result.cursor || '');
    const out = {};
    for (const e of result.entries) {
      const m = /^([^/]+)\/([^/]+)(?:\/(.*))?$/.exec(e.rel || '');
      if (!m) continue;
      const dept = m[1], id = m[2], hasFile = !!m[3];
      if (id === 'shared-hub' || id === 'shared-incoming') continue;   // legacy containers, not artifacts
      const d = out[dept] || (out[dept] = {});
      const rec = d[id] || (d[id] = { changed: false, kind: 'folder' });
      if (hasFile) rec.changed = true;                       // content present / moved
      if (m[3] === 'SKILL.md') rec.kind = 'skill';
    }
    if (isFull) for (const dept in out) for (const id in out[dept]) out[dept][id].changed = true;
    return out;
  }

  /* ── install: copy an artifact folder into the workspace ─────────────── */
  async function install(dept, id, kind) {
    const store = cloudStore(deptRoot(dept)), dst = INSTALL_ROOT + '/' + id;
    let prevDirty = {}, prevSeen = {}, prevPin = null;
    try { const pm = await readInstalledState(id); prevDirty = (pm && pm.dirty) || {}; prevSeen = (pm && pm.seen) || {}; prevPin = (pm && pm.pin) || null; } catch (_) {}
    const entries = (await store.listEntries(id)).filter(e => e.rel !== 'package.json' && e.rel !== 'manifest.json' && !e.rel.startsWith('.'));
    const seen = {};
    for (const e of entries) {
      const p = dst + '/' + e.rel;
      if (prevDirty[e.rel]) { seen[e.rel] = prevSeen[e.rel] || ''; continue; }   // local > dropbox
      const bytes = await store.readBytes(id + '/' + e.rel);
      if (!bytes) continue;
      await O().write(p, new Blob([bytes]));
      seen[e.rel] = e.rev || '';
      markDirty(p);
    }
    const keep = new Set(Object.keys(seen));
    for (const rel of await listOpfs(dst, '', [])) {
      if (keep.has(rel) || prevDirty[rel]) continue;
      try { await O().remove(dst + '/' + rel); } catch (_) {}
      try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', dst + '/' + rel); } catch (_) {}
    }
    await writeInstalledState(id, { id, title: id, kind: kind || 'folder', pin: prevPin, rev: 0, from: 'team', team: dept, seen, dirty: prevDirty });
    if (window.SandpiePins) { try { if (prevPin) SandpiePins.remove(dst + '/' + prevPin); const p = kind === 'skill' ? 'SKILL.md' : (entries[0] && entries[0].rel); if (p) { SandpiePins.add(dst + '/' + p); } } catch (_) {} }
    try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id } })); } catch (_) {}
  }

  /* ── autoSync: scan + install what changed ───────────────────────────── */
  let syncing = false;
  async function autoSync() {
    if (syncing || !O()) return; syncing = true;
    try {
      if (!cloudOn()) return;
      const scan = await scanTeamRoot();
      for (const dept in scan) for (const id in scan[dept]) {
        const r = scan[dept][id];
        if (!r.changed) continue;
        const mk = await readInstalledState(id);
        if (!mk || mk.team !== dept) await install(dept, id, r.kind);
        else if (r.changed) { await install(dept, id, r.kind); console.info('[sharing] refreshed', id, 'from', dept); }
      }
      // prune: installed team packages whose folder vanished from the scan
      const seen = new Set(); for (const dept in scan) for (const id in scan[dept]) seen.add(id);
      const st = pkgState();
      for (const id of Object.keys(st)) { if (st[id] && st[id].from === 'team' && !seen.has(id)) { await removeInstalledLocal(id); } }
      await wbRetryDirty();
    } catch (e) { console.warn('[sharing] autoSync failed:', e); } finally { syncing = false; }
  }
  async function removeInstalledLocal(id) {
    const dst = INSTALL_ROOT + '/' + id;
    try { const st = pkgState(); delete st[id]; setPkgState(st); } catch (_) {}
    if (window.SandpiePins) { for (const p of SandpiePins.list()) if (p === dst || p.startsWith(dst + '/')) SandpiePins.remove(p); }
    for (const rel of await listOpfs(dst, '', [])) { try { await O().remove(dst + '/' + rel); } catch (_) {} }
    try { await O().remove(dst); } catch (_) {}
  }

  /* ── publish: copy your files into a department's artifact folder ────── */
  async function publish(srcPath, dept, opts) {
    opts = opts || {};
    const src = norm(srcPath || '');
    if (!src) throw new Error('publish: srcPath required');
    if (src.startsWith('sandpie/shared-incoming')) throw new Error('publish: share your own file, not a delivery/inbox path');
    const dir = await isDir(src), base = src.split('/').pop();
    const id = opts.id || slug(base);
    const store = cloudStore(deptRoot(dept));
    const files = dir ? await listOpfs(src, '', []) : [base];
    const readSrc = async (rel) => { try { const b = await O().readBytes(dir ? src + '/' + rel : src); if (b) return b; } catch (_) {} const p = prov(); if (p && p.hydrate) { try { if (await p.hydrate(dir ? src + '/' + rel : src)) return await O().readBytes(dir ? src + '/' + rel : src); } catch (e) { console.warn('[sharing] hydrate failed', rel, (e && e.message) || e); } } return null; };
    let missed = 0;
    for (const rel of files) { const bytes = await readSrc(rel); if (bytes) await store.writeBytes(id + '/' + rel, bytes); else missed++; }
    if (missed === files.length) throw new Error('None of the files in "' + base + '" could be read — nothing was shared.');
    if (missed) console.warn('[sharing] published without ' + missed + ' unreadable file(s)');
    fire();
    return { id, dests: [dept] };
  }

  /* ── write-back: local edits in the installed copy → the hub ─────────── */
  const WB_DEBOUNCE = 1500;
  const WB_SKIP = /(^|\/)\.[^/]+$|\.bak(?:-|$)|(^|\/)(package|cache|items_cache|extraction_log)\.json$/;
  let _installing = false, _wbTimers = {}, _wbDenied = {};
  const wbNotify = (kind, msg) => { try { if (window.Sandpie && Sandpie.addMsg) Sandpie.addMsg(kind, msg); } catch (_) {} };
  const wbMatch = (p) => {
    const pre = INSTALL_ROOT + '/';
    if (typeof p !== 'string' || !p.startsWith(pre)) return null;
    const rest = p.slice(pre.length), slash = rest.indexOf('/');
    if (slash < 0) return null;
    return { id: rest.slice(0, slash), rel: rest.slice(slash + 1) };
  };
  function wbOnChanged(p) {
    const m = wbMatch(p);
    if (!m) return;
    if (m.rel === 'package.json' || WB_SKIP.test(m.rel)) return;
    if (_installing || _wbDenied[m.id]) return;
    wbMarkDirty(m.id, m.rel);
    const key = m.id + '/' + m.rel;
    clearTimeout(_wbTimers[key]);
    _wbTimers[key] = setTimeout(() => { delete _wbTimers[key]; wbPush(m.id, m.rel); }, WB_DEBOUNCE);
  }
  async function wbMarkDirty(id, rel) {
    try { const mk = await readInstalledState(id); if (!mk || mk.from !== 'team' || !mk.team) return; mk.dirty = mk.dirty || {}; mk.dirty[rel] = true; await writeInstalledState(id, mk); } catch (_) {}
  }
  async function wbPush(id, rel) {
    try {
      if (!cloudOn()) return;
      const mk = await readInstalledState(id);
      if (!mk || mk.from !== 'team' || !mk.team) return;
      const store = cloudStore(deptRoot(mk.team));
      const entries = await store.listEntries(id);
      const e = entries.find(x => x.rel === rel);
      const hubRev = (e && e.rev) || '', knownRev = (mk.seen || {})[rel] || '';
      if (hubRev && !knownRev) { await wbPreserve(id, rel, mk); return; }
      if (knownRev && hubRev && knownRev !== hubRev) { await wbPreserve(id, rel, mk); return; }
      const bytes = await O().readBytes(INSTALL_ROOT + '/' + id + '/' + rel);
      if (!bytes) return;
      const p = prov();
      const resp = await p.cloudUpload(deptRoot(mk.team) + '/' + id + '/' + rel, bytes, { team: true });
      const newRev = (resp && resp.rev) || hubRev;
      mk.seen = mk.seen || {}; mk.seen[rel] = newRev;
      mk.dirty = mk.dirty || {}; delete mk.dirty[rel];
      await writeInstalledState(id, mk);
    } catch (err) {
      const msg = String((err && err.message) || err);
      if (/403|no_permission|insufficient_permissions|path_root|access_denied/i.test(msg)) { _wbDenied[id] = true; wbNotify('err', '⚠ Sense permís d\'escriptura a l\'hub — el canvi a ' + rel + ' no s\'ha publicat (queda pendent).'); }
      else console.warn('[sharing] write-back failed', id, rel, msg);
    }
  }
  async function wbPreserve(id, rel, mk) {
    try {
      const bytes = await O().readBytes(INSTALL_ROOT + '/' + id + '/' + rel);
      if (!bytes) return;
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      const dst = 'sandpie/artifacts/' + id + '.conflicts/' + rel + '.' + ts;
      await O().write(dst, new Blob([bytes]));
      if (mk) { mk.dirty = mk.dirty || {}; delete mk.dirty[rel]; await writeInstalledState(id, mk); }
      wbNotify('err', '⚠ ' + rel + ' ha canviat a l\'hub — la teva edició s\'ha desat a ' + dst + ' i NO s\'ha publicat.');
    } catch (e) { console.warn('[sharing] conflict preserve failed', e); }
  }
  async function wbRetryDirty() {
    const st = pkgState();
    for (const id of Object.keys(st)) {
      const mk = st[id];
      if (!mk || mk.from !== 'team' || !mk.team) continue;
      for (const rel of Object.keys((mk.dirty) || {})) {
        if (_wbDenied[id]) break;
        if (WB_SKIP.test(rel) || rel === 'package.json') continue;
        try { await wbPush(id, rel); } catch (e) { console.warn('[sharing] wbRetryDirty', id, rel, e); }
      }
    }
  }

  /* ── home rendering (team artifacts + installed) ─────────────────────── */
  let homeBusy = false, homePending = false;
  function fire() { try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {} renderHome(); }
  function subscribe(cb) { const h = () => cb(); window.addEventListener('sandpie-shares-changed', h); return () => window.removeEventListener('sandpie-shares-changed', h); }
  async function acceptedList() {
    const out = [];
    let dirs = []; try { dirs = (await O().listDir(INSTALL_ROOT)).filter(e => e.kind === 'directory').map(e => e.name); } catch (_) {}
    for (const id of dirs) { let mk = null; try { mk = await readInstalledState(id); } catch (_) {} out.push(mk || { id, title: id, kind: 'folder' }); }
    return out;
  }
  async function renderHome() {
    if (!document.getElementById('sharedHome') || !O()) return;
    if (homeBusy) { homePending = true; return; } homeBusy = true;
    try {
      const box = document.getElementById('sharedHome');
      const list = await acceptedList();
      if (!list.length) { box.innerHTML = ''; return; }
      box.innerHTML = list.map(m => {
        const entry = m.pin || (m.kind === 'skill' ? 'SKILL.md' : '');
        const full = entry ? INSTALL_ROOT + '/' + m.id + '/' + entry : null;
        return '<div class="shared-file">' +
          '<button class="shared-file-open" ' + (full ? 'onclick="opfs.openFile(\'' + full + '\',\'' + entry + '\')"' : '') + '>' + (m.kind === 'skill' ? '🧩' : '📁') + ' ' + esc(m.title || m.id) + '</button>' +
          '<span class="shared-by">from ' + esc(m.team || 'team') + '</span>' +
          '<button class="shared-dismiss" title="Remove" onclick="SandpieSharing.uninstall(\'' + m.id + '\')">✕</button>' +
          '</div>';
      }).join('');
    } catch (e) { console.warn('[sharing] renderHome failed', e); } finally { homeBusy = false; if (homePending) { homePending = false; renderHome(); } }
  }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  /* ── share dialog (team only) ────────────────────────────────────────── */
  async function shareDialog(srcPath, presetKind) {
    const src = norm(srcPath || '');
    const dir = await isDir(src);
    const folderFiles = dir ? await listOpfs(src, '', []) : [];
    const back = document.createElement('div'); back.className = 'share-modal-back';
    back.innerHTML =
      '<div class="share-modal" data-chrome>' +
        '<div class="share-modal-h">Share “' + esc(src.split('/').pop()) + '”</div>' +
        '<label class="share-opt">Department: <select class="share-in" data-k="team"><option value="">loading…</option></select></label>' +
        '<label class="share-opt share-pin"><input type="checkbox" data-k="pin" checked> Pin to my home screen</label>' +
        (dir ? '<div class="share-pin-file"><label class="share-opt">Pin which file: <select class="share-in" data-k="pinfile">' + folderFiles.map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('') + '</select></label></div>' : '') +
        '<div class="share-modal-btns"><button class="ghost" data-act="cancel">Cancel</button><button class="ghost share-primary" data-act="share">Share</button></div>' +
        '<div class="share-modal-msg"></div>' +
      '</div>';
    document.body.appendChild(back);
    const close = () => back.remove();
    back.addEventListener('click', (e) => { if (e.target === back) close(); });
    back.querySelector('[data-act="cancel"]').onclick = close;
    const sel = back.querySelector('[data-k="team"]');
    const msg = back.querySelector('.share-modal-msg');
    const depts = await teams();
    sel.innerHTML = depts.length ? depts.map(t => '<option value="' + esc(t.name) + '">' + esc(t.name) + '</option>').join('') : '<option value="">no team folders available</option>';
    back.querySelector('[data-act="share"]').onclick = async () => {
      const dept = sel.value; if (!dept) { msg.textContent = 'Pick a department first.'; return; }
      msg.textContent = 'Sharing…';
      try {
        const pin = back.querySelector('[data-k="pin"]').checked;
        const pinFile = dir ? (back.querySelector('[data-k="pinfile"]').value || '') : src.split('/').pop();
        const out = await publish(src, dept, { pin, pinFile });
        msg.textContent = '✓ Shared to ' + dept + (out.id ? ' (' + out.id + ')' : '') + '.';
        await autoSync();
        setTimeout(close, 900);
      } catch (e) { msg.textContent = 'Error: ' + ((e && e.message) || e); }
    };
  }

  /* ── cloud store over the team root (paths relative to a dept root) ──── */
  function cloudStore(root) {
    const P = () => prov();
    return {
      kind: 'cloud', root,
      _rel(path, base) { const s = String(path); if (!base) return s.replace(/^\/+/, ''); const i = s.toLowerCase().indexOf(base.toLowerCase() + '/'); return i >= 0 ? s.slice(i + base.length + 1) : s.split('/').pop(); },
      async listEntries(sub) { const base = root + (sub ? '/' + sub : ''); return (await P().cloudList(base, true, { team: true })).filter(e => e.kind === 'file').map(e => ({ rel: this._rel(e.path, base), rev: e.rev || '', size: e.size || 0 })); },
      async readBytes(rel) { try { return await P().cloudDownload(root + '/' + rel, { team: true }); } catch (_) { return null; } },
      async writeBytes(rel, bytes) { await P().cloudUpload(root + '/' + rel, bytes, { team: true }); },
    };
  }
  async function isDir(p) { try { await O().listDir(p); return true; } catch (_) { return false; } }
  async function listOpfs(base, rel, out) {
    let entries; try { entries = await O().listDir(base + (rel ? '/' + rel : '')); } catch (_) { return out; }
    for (const e of entries) { const r = rel ? rel + '/' + e.name : e.name; if (e.kind === 'directory') await listOpfs(base, r, out); else out.push(r); }
    return out;
  }

  /* ── boot ────────────────────────────────────────────────────────────── */
  function boot() { renderHome(); autoSync(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  const SHARE_POLL_MS = 60000;
  const pollShares = () => { autoSync(); renderHome(); };
  setInterval(() => { if (!document.hidden) pollShares(); }, SHARE_POLL_MS);
  window.addEventListener('focus', pollShares);
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('sync:done', () => renderHome()); } catch (_) {}
  // write-back wiring: page-side file:changed + the worker's sw-opfs-changed relay
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('file:changed', wbOnChanged); } catch (_) {}
  try {
    if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('message', (ev) => {
      const d = ev.data; if (!d) return;
      const paths = (d.type === 'sw-opfs-changed' && Array.isArray(d.paths)) ? d.paths
                  : (d.type === 'forward-to-page' && d.payload && d.payload.type === 'sw-opfs-changed' && Array.isArray(d.payload.paths)) ? d.payload.paths : null;
      if (paths) for (const p of paths) wbOnChanged(p);
    });
  } catch (_) {}

  const Sharing = { me, setIdentity, publish, autoSync, uninstall: removeInstalledLocal, subscribe, shareDialog, teams, teamRoot, acceptedList, fire, INSTALL_ROOT };
  window.SandpieSharing = Sharing;
})();
