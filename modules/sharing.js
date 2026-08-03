// sharing.js — team artifact sync. The whole system:
//   1) look at the team root (e.g. IA/)
//   2) list it (list_folder): first level = DEPARTMENT, second = ARTIFACT name
//   3) every artifact folder you can see → copy its contents into
//      sandpie/shared-installed/<artifact>/ (same name)
//   4) keep the list_folder CURSOR in localStorage (per device, like dbxfull-cursor)
//   5) next poll: list_folder/continue(cursor) → sync only what changed
// That is all. No 1:1 deliveries, no accept/dismiss, and ONE metadata file per
// artifact: .sandpie.json ({pin,title} — which file is the MAIN one). It rides
// the same cursor (rev-tracked in `seen`) but never lands on disk — it becomes
// pin/title in the per-device installed state.
// Per-device installed state (from/team/seen/dirty,pin,title) also lives in localStorage.
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
  // second = artifact. Returns { full, removed:[{dept,id}], depts: { [dept]: {
  // [id]: {changed, kind, revs:{rel:rev}, gone:[rel]} } } }. `revs` carries the
  // hub rev of every file the listing covered, so the caller can tell a REAL
  // change from the echo of an upload it made itself; on a delta scan it only
  // covers the files that changed. `removed` = artifact folders tombstoned in a
  // delta. Every Nth poll forces a full listing (like dropbox.js FULL_SCAN_EVERY)
  // to catch deletions whose tombstones we can't attribute (e.g. a whole dept).
  let _scanN = 0;
  const FULL_SCAN_EVERY = 10;
  async function scanTeamRoot() {
    const p = prov(), root = teamRoot();
    if (!cloudOn() || !root || !p.cloudListWithCursor) return { full: false, removed: [], depts: {} };
    const cur = (++_scanN % FULL_SCAN_EVERY === 0) ? null : hubCursor(root);
    let result = null;
    if (cur && p.cloudListContinue) { try { result = await p.cloudListContinue(cur, { team: true }); } catch (_) { result = null; } }
    const isFull = !result;
    if (!result) { try { result = await p.cloudListWithCursor(root, { team: true }); } catch (e) { if (String((e && e.message) || e).includes('not_found')) return { full: false, removed: [], depts: {} }; throw e; } }
    setHubCursor(root, result.cursor || '');
    const out = {}, removed = [];
    // cloud entries carry ABSOLUTE paths (/IA/IT/<id>/<file>) with no rel field:
    // strip the team-root prefix (lowercase, like pullOldWorkspace) to get dept/id.
    const prefix = root.replace(/^\/+/, '').toLowerCase() + '/';
    for (const e of result.entries) {
      let rel = (e.rel != null) ? e.rel : String(e.path || '').replace(/^\/+/, '');
      if (rel.toLowerCase().startsWith(prefix)) rel = rel.slice(prefix.length);
      const m = /^([^/]+)\/([^/]+)(?:\/(.*))?$/.exec(rel);
      if (!m) continue;
      const dept = m[1], id = m[2], hasFile = !!m[3];
      if (id === 'shared-hub' || id === 'shared-incoming') continue;   // legacy containers, not artifacts
      const rec4 = () => { const d = out[dept] || (out[dept] = {}); return d[id] || (d[id] = { changed: false, kind: 'folder', revs: {}, gone: [] }); };
      if (e.kind === 'deleted') {                         // tombstone from include_deleted
        if (!hasFile) { removed.push({ dept, id }); continue; }   // the artifact folder itself vanished
        const r0 = rec4();
        r0.changed = true;
        delete r0.revs[m[3]];                             // entries are chronological: a later delete wins…
        if (!r0.gone.includes(m[3])) r0.gone.push(m[3]);
        continue;
      }
      if (e.kind === 'file' && !hasFile) continue;        // loose file directly under a dept — not an artifact
      const rec = rec4();
      if (hasFile) {
        rec.changed = true;                               // content present / moved
        if (e.kind === 'file') {
          rec.revs[m[3]] = e.rev || '';
          const gi = rec.gone.indexOf(m[3]); if (gi >= 0) rec.gone.splice(gi, 1);   // …and a later re-add undoes a delete
        }
      }
      if (m[3] === 'SKILL.md') rec.kind = 'skill';
    }
    if (isFull) for (const dept in out) for (const id in out[dept]) out[dept][id].changed = true;
    return { full: isFull, removed, depts: out };
  }

  /* ── install/reconcile: mirror the scanned hub state into the workspace ── */
  // The one hub metadata file, written by publish(): {pin: <main file>, title}.
  // Rev-tracked in `seen` like any content file (so pin changes propagate), but
  // parsed into installed state instead of being written to disk.
  const META = '.sandpie.json';
  // Marker files some hub folders still carry from older builds — never
  // installed, never counted as a change. Must match what the rev comparison
  // in autoSync skips, or every scan looks like a change forever.
  const HUB_IGNORE = (rel) => rel !== META && (rel === 'package.json' || rel === 'manifest.json' || /(^|\/)\./.test(rel));
  // Everything comes from the ONE recursive cursor listing of the team root:
  // file revs (r.revs) + tombstones (r.gone). No per-artifact re-listing —
  // files are downloaded directly by path. On a delta r.revs only covers what
  // changed, so the carried-over `seen` map stands in for the rest; a full
  // listing is the authority on what exists and also prunes local strays.
  async function install(dept, id, kind, r, full) {
    const store = cloudStore(deptRoot(dept)), dst = INSTALL_ROOT + '/' + id;
    let prev = null;
    try { prev = await readInstalledState(id); } catch (_) {}
    const prevDirty = (prev && prev.dirty) || {}, prevSeen = (prev && prev.seen) || {}, prevPin = (prev && prev.pin) || null;
    const sameTeam = !!(prev && prev.team === dept);   // a dept move must not trust revs recorded for another dept's copy
    const local = new Set(await listOpfs(dst, '', []));
    const seen = {};
    if (!full && sameTeam) for (const k in prevSeen) seen[k] = prevSeen[k];
    let changed = 0, metaPin = null, metaTitle = null;
    for (const rel in r.revs) {
      if (rel === META) {   // metadata: parse into state, never onto disk
        if (sameTeam && prevSeen[rel] && prevSeen[rel] === r.revs[rel]) { seen[rel] = prevSeen[rel]; continue; }
        const bytes = await store.readBytes(id + '/' + rel);
        if (!bytes) { if (sameTeam && prevSeen[rel]) seen[rel] = prevSeen[rel]; continue; }
        seen[rel] = r.revs[rel];
        try { const j = JSON.parse(new TextDecoder().decode(bytes)); if (j && typeof j.pin === 'string' && j.pin) metaPin = j.pin; if (j && typeof j.title === 'string' && j.title) metaTitle = j.title; changed++; } catch (_) {}
        continue;
      }
      if (HUB_IGNORE(rel)) continue;
      const p = dst + '/' + rel;
      if (prevDirty[rel]) { if (sameTeam && prevSeen[rel] != null) seen[rel] = prevSeen[rel]; continue; }   // local edit > hub
      if (sameTeam && prevSeen[rel] && prevSeen[rel] === r.revs[rel] && local.has(rel)) { seen[rel] = prevSeen[rel]; continue; }   // rev already held + copy present
      const bytes = await store.readBytes(id + '/' + rel);
      if (!bytes) { seen[rel] = (sameTeam && prevSeen[rel]) || ''; continue; }   // download failed — keep what we have; the rev mismatch retries on the next full scan
      await O().write(p, new Blob([bytes]));
      seen[rel] = r.revs[rel];
      changed++;
      // Notify the workspace sync so it mirrors the file — but NOT the write-back
      // listener: this write came FROM the hub, and pushing it back would mint a
      // new hub rev whose cursor echo re-installs it next poll, forever. emit()
      // is synchronous, so the flag exactly covers our own event.
      _installing = true; try { markDirty(p); } finally { _installing = false; }
    }
    for (const rel of r.gone) {                          // tombstoned on the hub
      if (prevDirty[rel]) continue;                      // …but edited here — keep the edit
      delete seen[rel];
      if (!local.has(rel)) continue;
      try { await O().remove(dst + '/' + rel); } catch (_) {}
      try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', dst + '/' + rel); } catch (_) {}
      changed++;
    }
    if (full) for (const rel of local) {                 // full listing = authority on what exists
      if ((rel in seen) || prevDirty[rel]) continue;
      try { await O().remove(dst + '/' + rel); } catch (_) {}
      try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', dst + '/' + rel); } catch (_) {}
      changed++;
    }
    if (r.revs['SKILL.md'] != null) kind = 'skill';
    else if (prev && prev.kind === 'skill' && !r.gone.includes('SKILL.md')) kind = 'skill';   // a delta that missed SKILL.md must not demote a skill
    const pin = metaPin != null ? metaPin : prevPin;
    await writeInstalledState(id, { id, title: metaTitle || (prev && prev.title) || id, kind: kind || 'folder', pin, rev: 0, from: 'team', team: dept, seen, dirty: prevDirty });
    if (window.SandpiePins) { try {
      // First install: pin the publisher's main file (fallbacks for pre-meta artifacts).
      if (!prev) { const p = pin || (kind === 'skill' ? 'SKILL.md' : Object.keys(seen).filter(k => k !== META)[0]); if (p) SandpiePins.add(dst + '/' + p); }
      // Publisher moved the main file: follow it — but only if the user still has
      // the old one pinned; a deliberate unpin stays unpinned.
      else if (metaPin != null && prevPin && metaPin !== prevPin && SandpiePins.isPinned(dst + '/' + prevPin)) { SandpiePins.remove(dst + '/' + prevPin); SandpiePins.add(dst + '/' + metaPin); }
    } catch (_) {} }
    if (changed) {
      console.info('[sharing] ' + id + ' ← ' + dept + ': ' + changed + ' file(s) updated');
      try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id } })); } catch (_) {}
    }
  }

  /* ── autoSync: scan + install what changed ───────────────────────────── */
  let syncing = false;
  async function autoSync() {
    if (syncing || !O()) return; syncing = true;
    try {
      if (!cloudOn()) return;
      const scan = await scanTeamRoot();
      for (const dept in scan.depts) for (const id in scan.depts[dept]) {
        const r = scan.depts[dept][id];
        if (!r.changed) continue;
        const mk = await readInstalledState(id);
        // Only reconcile when the hub really moved past what we hold. The delta
        // also echoes OUR OWN write-back uploads (wbPush stores the new rev in
        // seen) — those must NOT re-install, or every push loops back as a
        // download+re-upload forever.
        let need = !mk || mk.team !== dept;
        if (!need) {
          const seenRevs = mk.seen || {}, dirty = mk.dirty || {};
          if (r.gone.some(rel => !HUB_IGNORE(rel) && ((rel in seenRevs) || dirty[rel]))) need = true;   // a file we track was deleted on the hub
          if (!need) for (const rel in r.revs) { if (!HUB_IGNORE(rel) && !dirty[rel] && seenRevs[rel] !== r.revs[rel]) { need = true; break; } }   // a rev we don't hold yet
          if (!need && scan.full) for (const rel in seenRevs) { if (!(rel in r.revs)) { need = true; break; } }               // full scan: a file we hold is gone from the hub
        }
        if (!need) continue;
        await install(dept, id, r.kind, r, scan.full);
      }
      // prune installed team packages whose hub folder is gone. A cursor delta
      // only lists what CHANGED — absence there means "quiet", not "deleted" —
      // so absence-pruning is only valid on a FULL scan; deltas prune via the
      // artifact-folder tombstones Dropbox sends.
      const st = pkgState();
      if (scan.full) {
        const present = new Set(); for (const dept in scan.depts) for (const id in scan.depts[dept]) present.add(id);
        for (const id of Object.keys(st)) { if (st[id] && st[id].from === 'team' && !present.has(id)) { await removeInstalledLocal(id); } }
      } else {
        for (const t of scan.removed) {
          if (scan.depts[t.dept] && scan.depts[t.dept][t.id]) continue;   // deleted then re-created within the same delta — the re-create wins
          const mk = st[t.id]; if (mk && mk.from === 'team' && mk.team === t.dept) { await removeInstalledLocal(t.id); }
        }
      }
      // No-provenance sweep: anything physically under INSTALL_ROOT without an
      // installed-state record wasn't put there by this device's hub sync (old
      // builds; the personal-sync mirror used to write here before it was
      // blacked out in dropbox.js). Remove it — with the mirror gone it stays gone.
      let stray = []; try { stray = await O().listDir(INSTALL_ROOT); } catch (_) {}
      for (const e of stray) {
        let mk2 = null; try { mk2 = await readInstalledState(e.name); } catch (_) {}
        if (mk2 && mk2.from === 'team' && mk2.team) continue;
        console.info('[sharing] removing unprovenanced', e.name);
        await removeInstalledLocal(e.name);
      }
      await wbRetryDirty();
    } catch (e) { console.warn('[sharing] autoSync failed:', e); } finally { syncing = false; }
  }
  async function removeInstalledLocal(id) {
    const dst = INSTALL_ROOT + '/' + id;
    try { const st = pkgState(); delete st[id]; setPkgState(st); } catch (_) {}
    if (window.SandpiePins) { for (const p of SandpiePins.list()) if (p === dst || p.startsWith(dst + '/')) SandpiePins.remove(p); }
    for (const rel of await listOpfs(dst, '', [])) { try { await O().remove(dst + '/' + rel); } catch (_) {} }
    try { await O().remove(dst); } catch (_) {}
    fire();
  }

  // Dehydrated (cloud-only) files don't exist in OPFS — merge them into a source
  // listing from the cloud index so publish/dialogs don't silently drop them.
  async function srcFileList(src, dir) {
    let files = dir ? await listOpfs(src, '', []) : [src.split('/').pop()];
    const p = prov();
    const idx = (p && p.cloudIndex) ? p.cloudIndex() : null;
    if (dir && idx) {
      const pre = norm(src) + '/';
      const set = new Set(files);
      for (const rel of Object.keys(idx)) if (rel.startsWith(pre)) set.add(rel.slice(pre.length));
      files = [...set];
    }
    return files;
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
    // Markers/dotfiles never install on the recipient side (HUB_IGNORE) — don't upload them.
    const files = (await srcFileList(src, dir)).filter(rel => rel !== META && !HUB_IGNORE(rel));
    const readSrc = async (rel) => { try { const b = await O().readBytes(dir ? src + '/' + rel : src); if (b) return b; } catch (_) {} const p = prov(); if (p && p.hydrate) { try { if (await p.hydrate(dir ? src + '/' + rel : src)) return await O().readBytes(dir ? src + '/' + rel : src); } catch (e) { console.warn('[sharing] hydrate failed', rel, (e && e.message) || e); } } return null; };
    let missed = 0; const sent = [];
    for (const rel of files) { const bytes = await readSrc(rel); if (bytes) { await store.writeBytes(id + '/' + rel, bytes); sent.push(rel); } else missed++; }
    if (!sent.length) throw new Error('None of the files in "' + base + '" could be read — nothing was shared.');
    if (missed) console.warn('[sharing] published without ' + missed + ' unreadable file(s)');
    // The artifact's metadata: which file is the MAIN one — what every member's
    // home tile pins/opens. Written LAST so it never points at content that
    // hasn't landed yet.
    const pin = (opts.pinFile && sent.includes(opts.pinFile)) ? opts.pinFile
              : sent.includes('SKILL.md') ? 'SKILL.md'
              : sent.includes('index.html') ? 'index.html' : sent[0];
    try { await store.writeBytes(id + '/' + META, new TextEncoder().encode(JSON.stringify({ pin, title: base }))); }
    catch (e) { console.warn('[sharing] main-file marker failed:', (e && e.message) || e); }
    fire();
    return { id, dests: [dept], pin };
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
  // Dropbox content_hash: sha256 of the concatenation of each 4 MiB block's sha256.
  async function dbxContentHash(bytes) {
    const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const B = 4 * 1024 * 1024, parts = [];
    for (let o = 0; o < u8.byteLength; o += B) parts.push(new Uint8Array(await crypto.subtle.digest('SHA-256', u8.subarray(o, Math.min(o + B, u8.byteLength)))));
    const cat = new Uint8Array(parts.length * 32);
    for (let i = 0; i < parts.length; i++) cat.set(parts[i], i * 32);
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256', cat))].map(b => b.toString(16).padStart(2, '0')).join('');
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
      const bytes = await O().readBytes(INSTALL_ROOT + '/' + id + '/' + rel);
      if (!bytes) return;
      // Identical content already on the hub → just mark clean. Uploading would
      // mint a new rev that echoes back through every member's cursor delta as a
      // phantom change (and can ping-pong between devices indefinitely).
      if (e && e.hash) { try { if (await dbxContentHash(bytes) === e.hash) { mk.seen = mk.seen || {}; mk.seen[rel] = hubRev; mk.dirty = mk.dirty || {}; delete mk.dirty[rel]; await writeInstalledState(id, mk); return; } } catch (_) {} }
      if (hubRev && !knownRev) { await wbPreserve(id, rel, mk, hubRev); return; }
      if (knownRev && hubRev && knownRev !== hubRev) { await wbPreserve(id, rel, mk, hubRev); return; }
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
  async function wbPreserve(id, rel, mk, hubRev) {
    try {
      const bytes = await O().readBytes(INSTALL_ROOT + '/' + id + '/' + rel);
      if (!bytes) return;
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      const dst = 'sandpie/artifacts/' + id + '.conflicts/' + rel + '.' + ts;
      await O().write(dst, new Blob([bytes]));
      if (mk) { mk.dirty = mk.dirty || {}; delete mk.dirty[rel];
        if (hubRev) { mk.seen = mk.seen || {}; mk.seen[rel] = hubRev; }   // one-shot conflict: next save of an unchanged hub publishes
        await writeInstalledState(id, mk); }
      wbNotify('err', '⚠ ' + rel + ' ha canviat a l\'hub — la teva edició s\'ha desat a ' + dst + ' i NO s\'ha publicat. Torna a guardar per publicar-la.');
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
  // Home list = ONE row per installed artifact: its main file (publisher's pick,
  // sensible fallbacks for pre-meta artifacts). Only artifacts with provenance
  // (an installed-state record from this device's hub sync) show — anything
  // else under INSTALL_ROOT is debris that autoSync sweeps away.
  async function acceptedList() {
    let top = [];
    try { top = await O().listDir(INSTALL_ROOT); } catch (_) { return []; }
    const out = [];
    for (const t of top) {
      let mk = null; try { mk = await readInstalledState(t.name); } catch (_) {}
      if (!mk || mk.from !== 'team' || !mk.team) continue;
      const files = t.kind === 'directory' ? await listOpfs(INSTALL_ROOT + '/' + t.name, '', []) : [];
      const entry = (mk.pin && files.includes(mk.pin)) ? mk.pin
                  : (mk.kind === 'skill' && files.includes('SKILL.md')) ? 'SKILL.md'
                  : files.includes('index.html') ? 'index.html' : files[0];
      if (!entry) continue;                        // nothing to open (mid-install / empty)
      out.push({ id: t.name, title: mk.title || t.name, team: mk.team, kind: mk.kind || 'folder', entry });
    }
    return out;
  }
  async function renderHome() {
    if (!document.getElementById('sharedHome') || !O()) return;
    if (homeBusy) { homePending = true; return; } homeBusy = true;
    try {
      const box = document.getElementById('sharedHome');
      const list = await acceptedList();
      if (!list.length) { box.innerHTML = ''; return; }
      box.innerHTML = list.map((g, i) =>
        '<div class="shared-file" data-i="' + i + '">' +
          '<button class="shared-file-open">' + (g.kind === 'skill' ? '🧩' : '📁') + ' ' + esc(g.title) + '</button>' +
          '<span class="shared-by">from ' + esc(g.team) + '</span>' +
          '<button class="shared-pin"></button>' +
          '<button class="shared-dismiss" title="Remove">✕</button>' +
        '</div>').join('');
      for (const row of box.querySelectorAll('.shared-file')) {
        const g = list[+row.getAttribute('data-i')];
        const full = INSTALL_ROOT + '/' + g.id + '/' + g.entry;
        row.querySelector('.shared-file-open').onclick = () => { try { opfs.openFile(full, g.entry.split('/').pop()); } catch (_) {} };
        row.querySelector('.shared-dismiss').onclick = () => removeInstalledLocal(g.id);
        const pb = row.querySelector('.shared-pin');
        if (window.SandpiePins) { try { SandpiePins.bindButton(pb, full); } catch (_) { pb.remove(); } } else pb.remove();
      }
    } catch (e) { console.warn('[sharing] renderHome failed', e); } finally { homeBusy = false; if (homePending) { homePending = false; renderHome(); } }
  }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  /* ── share dialog (team only) ────────────────────────────────────────── */
  async function shareDialog(srcPath, presetKind) {
    const src = norm(srcPath || '');
    const dir = await isDir(src);
    const folderFiles = (await srcFileList(src, dir)).filter(f => f !== META && !HUB_IGNORE(f));
    const defPin = folderFiles.includes('SKILL.md') ? 'SKILL.md' : folderFiles.includes('index.html') ? 'index.html' : folderFiles[0];
    const back = document.createElement('div'); back.className = 'share-modal-back';
    back.innerHTML =
      '<div class="share-modal" data-chrome>' +
        '<div class="share-modal-h">Share “' + esc(src.split('/').pop()) + '”</div>' +
        '<label class="share-opt">Department: <select class="share-in" data-k="team"><option value="">loading…</option></select></label>' +
        (dir ? '<div class="share-pin-file"><label class="share-opt">Main file (what everyone opens): <select class="share-in" data-k="pinfile">' + folderFiles.map(f => '<option value="' + esc(f) + '"' + (f === defPin ? ' selected' : '') + '>' + esc(f) + '</option>').join('') + '</select></label></div>' : '') +
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
        const pinFile = dir ? (back.querySelector('[data-k="pinfile"]').value || '') : src.split('/').pop();
        const out = await publish(src, dept, { pinFile });
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
      async listEntries(sub) { const base = root + (sub ? '/' + sub : ''); return (await P().cloudList(base, true, { team: true })).filter(e => e.kind === 'file').map(e => ({ rel: this._rel(e.path, base), rev: e.rev || '', hash: e.hash || '', size: e.size || 0 })); },
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
