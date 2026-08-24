// sharing.js — team artifact sync.
//
//   THE LISTING IS THE TRUTH. One recursive listing of the team root (e.g. IA/):
//   first path level = DEPARTMENT, second = ARTIFACT, rest = the artifact's files.
//   Mirror it into sandpie/shared-installed/<id>/:
//     • file missing locally, or its rev differs  → download it
//     • local file the listing doesn't have       → delete it
//     • local artifact the listing doesn't have   → delete the folder
//   Deletion is ABSENCE from the live listing. Nothing else.
//
//   THE CURSOR IS ONLY A DOORBELL. list_folder/continue is used for exactly one
//   thing: "did anything change since last poll — yes or no?" Its entries are
//   counted, never interpreted. So a quiet hub costs one tiny call and no
//   listing, while any change (including a delete, which arrives as a tombstone)
//   just sends us to the real listing.
//
// That split matters, because interpreting delta CONTENT is what broke this
// module repeatedly. list_folder is called with include_deleted:true, so even a
// FULL listing carries tombstones for paths that used to exist — an artifact
// MOVED between departments leaves a folder of pure tombstones behind, and code
// that reads meaning into them sees a live artifact in the old department and
// fights the new one. Counting entries can't make that mistake.
//
// Department sharing is the ONLY mode. A 1:1 variant (a per-recipient folder
// restricted with sharing/share_folder + access_inheritance no_inherit) was built
// and removed: Dropbox answered 409 no_permission because this team does not let
// members create shared folders inside a team folder, so the folder could never be
// restricted to one person. Reviving it needs that team policy changed first —
// otherwise the delivery is readable by everyone with access to the team root,
// which is not what "send to one person" should mean.
//
// Per-device state (localStorage, never a file): for each installed artifact the
// department it came from, the rev of each file we hold, and any local edit still
// waiting to be pushed. `.sandpie.json` on the hub carries {pin,title} — which
// file is the MAIN one — and is parsed into that state, never written to disk.
(function () {
  'use strict';
  const INSTALL_ROOT = 'sandpie/shared-installed';
  const PKG_STATE_KEY = 'sandpie-pkg-state';     // localStorage: { [id]: {team,title,pin,kind,revs,dirty} }
  const HUB_CURSOR_KEY = 'sandpie-share-cursor'; // localStorage: { [teamRoot]: cursor } — per device, like dbxfull-cursor
  const ID_OVERRIDE_KEY = 'sandpie-share-identity';
  const META = '.sandpie.json';                  // hub metadata: {pin,title}
  // Files that live on the hub but are never installed: leftovers from older
  // builds, and dotfiles generally. Excluded from install, from publish uploads
  // and from the "delete local strays" pass.
  //
  // META is deliberately NOT skipped: it installs like any other file, so a wrong
  // pin or title is fixed by editing that one file and the existing write-back
  // path publishes it (wbPush refuses to push it unless it still parses as JSON).
  // Republishing the whole artifact to correct one field would mint a new rev for
  // every file, which every other member then re-downloads for nothing.
  const SKIP = (rel) => rel === 'package.json' || rel === 'manifest.json' || (rel !== META && /(^|\/)\./.test(rel));
  const parseMeta = (bytes) => {
    const out = { pin: null, title: null };
    if (!bytes) return out;
    try {
      const j = JSON.parse(new TextDecoder().decode(bytes));
      if (j && typeof j.pin === 'string') out.pin = j.pin;
      if (j && typeof j.title === 'string') out.title = j.title;
    } catch (_) {}
    return out;
  };

  const O = () => window.opfs;
  const prov = () => { try { return window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider(); } catch (_) { return null; } };
  const cloudOn = () => { const p = prov(); return !!(p && p.cloudConnected && p.cloudConnected()); };
  const slug = (s) => String(s || '').toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'pkg';
  const norm = (p) => String(p == null ? '' : p).replace(/^\/+/, '').replace(/\/+$/, '');

  // A SKILL.md is never shared as a bare file called "SKILL.md": the shareable
  // unit is the SKILL — its folder. Retarget the share to the parent folder so
  // the artifact is named after the skill, and the installed copy keeps the
  // skills/<name>/SKILL.md shape that context.js discovery expects.
  const isSkillFile = (p) => /(^|\/)SKILL\.md$/i.test(p);
  function skillTarget(src) {
    if (!isSkillFile(src)) return src;
    const cut = src.lastIndexOf('/');
    return cut > 0 ? src.slice(0, cut) : src;   // SKILL.md at the root: nothing to retarget to
  }
  // The skill's name: frontmatter `name:` when it parses, else null. The caller
  // falls back to the folder name, so the shared id matches the frontmatter when
  // the two agree (context.js flags them when they don't).
  async function skillFmName(dirPath) {
    try {
      const bytes = await O().readBytes(dirPath + '/SKILL.md');
      if (!bytes) return null;
      const fm = window.SandpieContext && SandpieContext.parseFrontmatter && SandpieContext.parseFrontmatter(new TextDecoder().decode(bytes));
      const n = fm && fm.name && String(fm.name).trim();
      return n || null;
    } catch (_) { return null; }
  }

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

  /* ── per-device state ─────────────────────────────────────────────────── */
  function pkgState() { try { return JSON.parse(localStorage.getItem(PKG_STATE_KEY) || '{}'); } catch (_) { return {}; } }
  function setPkgState(s) { try { localStorage.setItem(PKG_STATE_KEY, JSON.stringify(s)); } catch (_) {} }
  function stateOf(id) { const st = pkgState(); return st[id] || null; }
  function saveState(id, mk) { const st = pkgState(); st[id] = mk; setPkgState(st); }

  /* ── hub paths ────────────────────────────────────────────────────────── */
  function teamRoot() { const p = prov(); return (cloudOn() && p.cloudParent && p.cloudParent()) || ''; }
  function deptRoot(dept) { const r = teamRoot(); return r ? r + '/' + norm(dept) : ''; }
  const hubPath = (dept, id, rel) => deptRoot(dept) + '/' + id + (rel ? '/' + rel : '');
  async function teams() {
    const p = prov();
    if (!(cloudOn() && p && p.listTeamFolders)) return [];
    try { return (await p.listTeamFolders()) || []; } catch (_) { return []; }
  }
  const hubDownload = (abs) => prov().cloudDownload(abs, { team: true });
  const hubUpload = (abs, bytes) => prov().cloudUpload(abs, bytes, { team: true });

  /* ── the doorbell: has anything changed since the last listing? ────────── */
  function cursor(root) { try { return JSON.parse(localStorage.getItem(HUB_CURSOR_KEY) || '{}')[root] || ''; } catch (_) { return ''; } }
  function setCursor(root, c) { try { const m = JSON.parse(localStorage.getItem(HUB_CURSOR_KEY) || '{}'); if (c) m[root] = c; else delete m[root]; localStorage.setItem(HUB_CURSOR_KEY, JSON.stringify(m)); } catch (_) {} }
  // Counts the delta and throws the result away. A tombstone, a new file and a
  // rename all mean the same thing here: "go read the real listing". Never returns
  // false unless the hub genuinely reported nothing, so a broken or expired cursor
  // costs one wasted listing, never a missed change.
  async function hubQuiet() {
    const p = prov(), root = teamRoot();
    const cur = cursor(root);
    if (!cur || !p.cloudListContinue) return false;
    try {
      const r = await p.cloudListContinue(cur, { team: true });
      setCursor(root, (r && r.cursor) || '');
      return !(r && r.entries && r.entries.length);
    } catch (e) { setCursor(root, ''); return false; }   // expired/409 → fall through to a full listing
  }

  /* ── the one listing: what the hub holds right now ─────────────────────── */
  // → { ok, arts: { [id]: { id, dept, files: {rel: rev} } } }
  // ok=false means the listing failed or came back empty; callers must NOT delete
  // anything on that basis (an unreachable/misconfigured root must never wipe
  // installed artifacts — a stale copy is recoverable, a deleted one isn't).
  async function hubScan() {
    const p = prov(), root = teamRoot();
    if (!cloudOn() || !root) return { ok: false, arts: {} };
    let entries;
    try {
      // Take the fresh cursor that comes with the listing: from here on, the
      // doorbell reports changes made AFTER this exact snapshot.
      if (p.cloudListWithCursor) { const r = await p.cloudListWithCursor(root, { team: true }); entries = r.entries; setCursor(root, (r && r.cursor) || ''); }
      else if (p.cloudList) entries = await p.cloudList(root, true, { team: true });
      else return { ok: false, arts: {} };
    }
    catch (e) { console.warn('[sharing] hub listing failed:', (e && e.message) || e); setCursor(root, ''); return { ok: false, arts: {} }; }
    if (!entries || !entries.length) return { ok: false, arts: {} };
    // Entries carry ABSOLUTE paths (/IA/IT/<id>/<file>); strip the team-root prefix.
    const prefix = root.replace(/^\/+/, '').toLowerCase() + '/';
    const byKey = {};        // 'dept/id' → { dept, id, files }
    for (const e of entries) {
      if (e.kind !== 'file') continue;
      let rel = String(e.path || '').replace(/^\/+/, '');
      if (rel.toLowerCase().startsWith(prefix)) rel = rel.slice(prefix.length);
      const m = /^([^/]+)\/([^/]+)\/(.+)$/.exec(rel);      // dept / artifact / file…
      if (!m) continue;                                     // loose file under the root or a dept — not an artifact
      const dept = m[1], id = m[2], file = m[3];
      if (id === 'shared-hub' || id === 'shared-incoming') continue;   // legacy containers
      const k = dept + '/' + id;
      (byKey[k] || (byKey[k] = { dept, id, files: {} })).files[file] = e.rev || '';
    }
    // One local folder per artifact id, so the same name in two departments has to
    // be resolved: alphabetically-first department wins, deterministically on every
    // device. (Previously the two copies took turns overwriting each other.)
    const arts = {};
    for (const k of Object.keys(byKey).sort()) {
      const a = byKey[k];
      if (!Object.keys(a.files).some(f => !SKIP(f))) continue;   // nothing installable in there
      if (arts[a.id]) { console.warn('[sharing] "' + a.id + '" exists in both "' + arts[a.id].dept + '" and "' + a.dept + '" — using "' + arts[a.id].dept + '". Delete one hub folder to resolve.'); continue; }
      arts[a.id] = a;
    }
    return { ok: true, arts };
  }

  /* ── mirror one artifact into the workspace ───────────────────────────── */
  const dbxContentHash = async (bytes) => {          // sha256 over each 4 MiB block's sha256
    const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const B = 4 * 1024 * 1024, parts = [];
    for (let o = 0; o < u8.byteLength; o += B) parts.push(new Uint8Array(await crypto.subtle.digest('SHA-256', u8.subarray(o, Math.min(o + B, u8.byteLength)))));
    const cat = new Uint8Array(parts.length * 32);
    for (let i = 0; i < parts.length; i++) cat.set(parts[i], i * 32);
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256', cat))].map(b => b.toString(16).padStart(2, '0')).join('');
  };
  async function mirror(a) {
    const dst = INSTALL_ROOT + '/' + a.id;
    const prev = stateOf(a.id);
    const fresh = !prev || prev.team !== a.dept;      // never seen, or it moved department
    const prevRevs = fresh ? {} : (prev.revs || {});
    const dirty = (prev && prev.dirty) || {};
    const local = new Set(await listOpfs(dst, '', []));
    const revs = {};
    let changed = 0, pin = null, title = null;

    for (const rel of Object.keys(a.files)) {
      if (SKIP(rel)) continue;
      if (dirty[rel]) {                                                           // local edit pending push — don't clobber it
        revs[rel] = prevRevs[rel] || '';
        // A pending edit to META is the user's new pin/title: read it from the
        // local copy so the home row follows the edit now, not one poll after the
        // hub echoes it back.
        if (rel === META) { const m = parseMeta(await readLocal(dst + '/' + rel)); if (m.pin) pin = m.pin; if (m.title) title = m.title; }
        continue;
      }
      if (local.has(rel) && prevRevs[rel] === a.files[rel]) { revs[rel] = a.files[rel]; continue; }   // already current (state already holds META's pin/title)
      const bytes = await hubRead(a, rel);
      if (!bytes) { _forceNext = true; if (local.has(rel)) revs[rel] = prevRevs[rel] || ''; continue; }   // transient failure — keep what we have; _forceNext forces a retry pass
      await write(dst + '/' + rel, bytes);
      revs[rel] = a.files[rel];
      if (rel === META) { const m = parseMeta(bytes); pin = m.pin; title = m.title; }
      changed++;
    }
    // the hub is the authority on what belongs here
    for (const rel of local) {
      if (rel in revs || dirty[rel] || SKIP(rel)) continue;
      await remove(dst + '/' + rel);
      changed++;
    }
    const kind = ('SKILL.md' in a.files) ? 'skill' : 'folder';
    const mk = {
      id: a.id, team: a.dept, from: 'team', kind, revs, dirty,
      title: title || (prev && prev.title) || a.id,
      pin: pin || (!fresh && prev && prev.pin) || null,
    };
    saveState(a.id, mk);
    // Pin the main file on first install; afterwards follow the publisher only if
    // the user still has the old main file pinned (a deliberate unpin stays).
    // Skills are the exception: they never appear on the home screen — they show
    // in Settings → Sharing as installed skills — so never pin one, and clear any
    // pin a previous build left behind.
    if (window.SandpiePins) try {
      if (kind === 'skill') {
        for (const p of SandpiePins.list()) if (p === dst || p.startsWith(dst + '/')) SandpiePins.remove(p);
      } else {
        const main = mainFile(mk, Object.keys(revs));
        if (fresh) { if (main) SandpiePins.add(dst + '/' + main); }
        else if (pin && prev && prev.pin && pin !== prev.pin && SandpiePins.isPinned(dst + '/' + prev.pin)) { SandpiePins.remove(dst + '/' + prev.pin); SandpiePins.add(dst + '/' + pin); }
      }
    } catch (_) {}
    if (changed) {
      console.info('[sharing] ' + a.id + ' ← ' + a.dept + ': ' + changed + ' file(s) updated');
      try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id: a.id } })); } catch (_) {}
    }
    return changed;
  }
  const hubRead = async (a, rel) => { try { return await hubDownload(hubPath(a.dept, a.id, rel)); } catch (e) { console.warn('[sharing] download failed', a.id + '/' + rel, (e && e.message) || e); return null; } };
  // Which file the home row opens: the publisher's pick, else conventions.
  // META is installed like any other file, so it has to be excluded here or the
  // last resort ("first alphabetically") would pick the dotfile every time.
  function mainFile(mk, files) {
    const cand = files.filter(f => f !== META);
    if (mk && mk.pin && cand.includes(mk.pin)) return mk.pin;
    if (cand.includes('SKILL.md')) return 'SKILL.md';
    if (cand.includes('index.html')) return 'index.html';
    return cand.slice().sort()[0] || null;
  }

  /* ── the poll: push pending edits, mirror the hub, drop what's gone ───── */
  let syncing = false, _pollN = 0, _forceNext = false;
  const FULL_EVERY = 10;                       // safety net: ignore the doorbell every Nth poll
  async function autoSync(opts) {
    if (syncing || !O() || !cloudOn()) return; syncing = true;
    try {
      await pushDirty();                       // local edits first, so the mirror sees their revs
      // The doorbell can only skip work, never cause it. Overridden by an explicit
      // full request, by a periodic safety net, and by an unfinished previous pass
      // (a failed download must be retried even though the hub didn't change).
      const force = !!(opts && opts.full) || _forceNext || (++_pollN % FULL_EVERY === 0);
      if (!force && await hubQuiet()) return;
      _forceNext = false;
      const scan = await hubScan();
      if (!scan.ok) return;                    // couldn't see the hub — change nothing
      let touched = 0;
      for (const id of Object.keys(scan.arts)) { try { touched += await mirror(scan.arts[id]); } catch (e) { console.warn('[sharing] mirror failed', id, e); } }
      // Anything under the install root the hub doesn't have: an artifact that was
      // deleted or renamed on the hub, a leftover from an older build, or a copy
      // some other device's sync dropped here. The hub is the authority — remove it.
      let top = []; try { top = await O().listDir(INSTALL_ROOT); } catch (_) {}
      for (const e of top) {
        if (scan.arts[e.name]) continue;
        console.info('[sharing] removing "' + e.name + '" — not on the hub');
        await uninstall(e.name);
        touched++;
      }
      if (touched) fire();
    } catch (e) { console.warn('[sharing] autoSync failed:', e); } finally { syncing = false; }
  }
  // Remove the local copy. Not user-facing: the hub decides what exists, so this
  // only runs when an artifact is gone from the hub (or a publish replaced it).
  async function uninstall(id) {
    const dst = INSTALL_ROOT + '/' + id;
    const st = pkgState(); delete st[id]; setPkgState(st);
    if (window.SandpiePins) { for (const p of SandpiePins.list()) if (p === dst || p.startsWith(dst + '/')) SandpiePins.remove(p); }
    for (const rel of await listOpfs(dst, '', [])) await remove(dst + '/' + rel);
    try { await O().remove(dst); } catch (_) {}
  }

  /* ── write-back: your edits to an installed file go to the hub ────────── */
  const WB_DEBOUNCE = 1500;
  let _wbTimers = {}, _wbDenied = {}, _mine = new Set(), _metaWarned = {};
  const wbNotify = (kind, msg) => { try { if (window.Sandpie && Sandpie.addMsg) Sandpie.addMsg(kind, msg); } catch (_) {} };
  // Our own mirror writes emit file:changed too; ignore exactly those, or every
  // download would be pushed straight back and re-downloaded on the next poll.
  async function write(path, bytes) { _mine.add(path); try { await O().write(path, new Blob([bytes])); } finally { setTimeout(() => _mine.delete(path), 0); } markDirtyForWorkspace(path); }
  async function remove(path) { _mine.add(path); try { await O().remove(path); } catch (_) {} finally { setTimeout(() => _mine.delete(path), 0); } }
  const markDirtyForWorkspace = (p) => { try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', p); } catch (_) {} };
  function wbOnChanged(p) {
    if (typeof p !== 'string' || _mine.has(p)) return;
    const pre = INSTALL_ROOT + '/';
    if (!p.startsWith(pre)) return;
    const rest = p.slice(pre.length), slash = rest.indexOf('/');
    if (slash < 0) return;
    const id = rest.slice(0, slash), rel = rest.slice(slash + 1);
    if (SKIP(rel) || _wbDenied[id]) return;
    const mk = stateOf(id);
    if (!mk || !mk.team) return;
    mk.dirty = mk.dirty || {}; mk.dirty[rel] = true; saveState(id, mk);
    const key = id + '/' + rel;
    clearTimeout(_wbTimers[key]);
    _wbTimers[key] = setTimeout(() => { delete _wbTimers[key]; wbPush(id, rel); }, WB_DEBOUNCE);
  }
  async function wbPush(id, rel) {
    const mk = stateOf(id);
    if (!cloudOn() || !mk || !mk.team) return;
    const abs = hubPath(mk.team, id, rel);
    try {
      const bytes = await O().readBytes(INSTALL_ROOT + '/' + id + '/' + rel);
      if (!bytes) return;
      // META is hand-editable, so a typo here would break the pin for everyone on
      // the team. Refuse to publish anything that isn't a JSON object; it stays
      // dirty and is retried on each poll, so fixing the file publishes it. Warn
      // once per file, or every poll would repeat the message.
      if (rel === META) {
        const wk = id + '/' + rel;
        let ok = false;
        try { const j = JSON.parse(new TextDecoder().decode(bytes)); ok = !!j && typeof j === 'object' && !Array.isArray(j); } catch (_) {}
        if (!ok) {
          if (!_metaWarned[wk]) { _metaWarned[wk] = true; wbNotify('err', '⚠ ' + rel + ' de ' + id + ' no és JSON vàlid — no s\'ha publicat. Corregeix-lo i es tornarà a provar.'); }
          return;
        }
        delete _metaWarned[wk];
      }
      // What's on the hub right now (one listing of this artifact's folder).
      let hub = null;
      try {
        const base = hubPath(mk.team, id, '');
        for (const e of await prov().cloudList(base, true, { team: true })) {
          if (e.kind !== 'file') continue;
          const p = String(e.path || '');
          if (p.toLowerCase().endsWith(('/' + id + '/' + rel).toLowerCase())) { hub = e; break; }
        }
      } catch (_) {}
      // Byte-identical already → just mark clean. Uploading would mint a new rev
      // that every other member then downloads for nothing.
      if (hub && hub.hash) { try { if (await dbxContentHash(bytes) === hub.hash) { clean(id, rel, hub.rev || ''); return; } } catch (_) {} }
      // The hub moved since we last synced this file → someone else's change is
      // there. Keep a copy of the local edit and let the hub win the mirror.
      const known = (mk.revs || {})[rel] || '';
      if (hub && hub.rev && known && hub.rev !== known) { await keepCopy(id, rel, hub.rev); return; }
      const resp = await hubUpload(abs, bytes);
      clean(id, rel, (resp && resp.rev) || '');
    } catch (err) {
      const msg = String((err && err.message) || err);
      if (/403|no_permission|insufficient_permissions|path_root|access_denied/i.test(msg)) { _wbDenied[id] = true; wbNotify('err', '⚠ Sense permís d\'escriptura a l\'hub — el canvi a ' + rel + ' no s\'ha publicat.'); }
      else console.warn('[sharing] write-back failed', id, rel, msg);   // stays dirty → retried next poll
    }
  }
  function clean(id, rel, rev) {
    const mk = stateOf(id); if (!mk) return;
    mk.revs = mk.revs || {}; mk.revs[rel] = rev;
    mk.dirty = mk.dirty || {}; delete mk.dirty[rel];
    saveState(id, mk);
  }
  async function keepCopy(id, rel, hubRev) {
    try {
      const bytes = await O().readBytes(INSTALL_ROOT + '/' + id + '/' + rel);
      if (!bytes) return;
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      const dst = 'artifacts/' + id + '.conflicts/' + rel + '.' + ts;   // visible area — sandbox artifacts migrated out
      await O().write(dst, new Blob([bytes]));
      markDirtyForWorkspace(dst);
      const mk = stateOf(id);
      if (mk) { mk.dirty = mk.dirty || {}; delete mk.dirty[rel]; mk.revs = mk.revs || {}; mk.revs[rel] = ''; saveState(id, mk); }   // rev '' → next mirror re-downloads the hub copy
      wbNotify('err', '⚠ ' + rel + ' ha canviat a l\'hub — la teva edició s\'ha desat a ' + dst + ' i NO s\'ha publicat.');
    } catch (e) { console.warn('[sharing] conflict copy failed', e); }
  }
  async function pushDirty() {
    const st = pkgState();
    for (const id of Object.keys(st)) {
      const mk = st[id];
      if (!mk || !mk.team || _wbDenied[id]) continue;
      for (const rel of Object.keys(mk.dirty || {})) { if (!SKIP(rel)) await wbPush(id, rel); }
    }
  }

  /* ── publish: copy your files into a department's artifact folder ─────── */
  // Dehydrated (cloud-only) files aren't in OPFS — merge the cloud index in so
  // publish doesn't silently drop them.
  async function srcFileList(src, dir) {
    let files = dir ? await listOpfs(src, '', []) : [src.split('/').pop()];
    const p = prov();
    const idx = (p && p.cloudIndex) ? p.cloudIndex() : null;
    if (dir && idx) {
      const pre = norm(src) + '/', set = new Set(files);
      for (const rel of Object.keys(idx)) if (rel.startsWith(pre)) set.add(rel.slice(pre.length));
      files = [...set];
    }
    return files;
  }
  async function publish(srcPath, dept, opts) {
    opts = opts || {};
    const src = skillTarget(norm(srcPath || ''));   // a SKILL.md shares its whole skill folder
    if (!src) throw new Error('publish: srcPath required');
    if (!dept) throw new Error('publish: a department is required');
    const dir = await isDir(src), base = src.split('/').pop();
    // META is excluded from the upload loop even though SKIP now allows it: it is
    // written once, explicitly, after the content lands (see below).
    const files = (await srcFileList(src, dir)).filter(rel => !SKIP(rel) && rel !== META);
    // A skill is named after the skill itself, never "SKILL.md": frontmatter
    // `name:` first, folder name second.
    const name = (dir && files.includes('SKILL.md') && await skillFmName(src)) || base;
    const id = opts.id || slug(name);
    const readSrc = async (rel) => {
      const path = dir ? src + '/' + rel : src;
      try { const b = await O().readBytes(path); if (b) return b; } catch (_) {}
      const p = prov();
      if (p && p.hydrate) { try { if (await p.hydrate(path)) return await O().readBytes(path); } catch (e) { console.warn('[sharing] hydrate failed', rel, (e && e.message) || e); } }
      return null;
    };
    let missed = 0; const sent = [];
    for (const rel of files) { const bytes = await readSrc(rel); if (bytes) { await hubUpload(hubPath(dept, id, rel), bytes); sent.push(rel); } else missed++; }
    if (!sent.length) throw new Error('None of the files in "' + base + '" could be read — nothing was shared.');
    if (missed) console.warn('[sharing] published without ' + missed + ' unreadable file(s)');
    // Which file everyone opens. Written LAST so it never points at content that
    // hasn't landed yet.
    const pin = (opts.pinFile && sent.includes(opts.pinFile)) ? opts.pinFile
              : sent.includes('SKILL.md') ? 'SKILL.md'
              : sent.includes('index.html') ? 'index.html' : sent.slice().sort()[0];
    try { await hubUpload(hubPath(dept, id, META), new TextEncoder().encode(JSON.stringify({ pin, title: name }))); }
    catch (e) { console.warn('[sharing] main-file marker failed:', (e && e.message) || e); }
    _forceNext = true;      // we just changed the hub — next pass reads the listing, doorbell or not
    fire();
    return { id, dests: [dept], pin };
  }

  /* ── home rendering ──────────────────────────────────────────────────── */
  let homeBusy = false, homePending = false;
  // Settings → Sharing tab element refs (created lazily by registerSharingTab).
  // renderHome() paints into the modal panel now — the home screen no longer
  // hosts the shared/team lists.
  let _shareListEl = null, _shareTotalEl = null, _shareEmptyEl = null;
  function fire() { try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {} renderHome(); }
  function subscribe(cb) { const h = () => cb(); window.addEventListener('sandpie-shares-changed', h); return () => window.removeEventListener('sandpie-shares-changed', h); }
  // One row per installed artifact: its main file. Only artifacts this device
  // installed from the hub (state record) appear.
  async function acceptedList() {
    let top = [];
    try { top = await O().listDir(INSTALL_ROOT); } catch (_) { return []; }
    const out = [];
    for (const t of top) {
      const mk = stateOf(t.name);
      if (!mk || !mk.team) continue;
      const files = t.kind === 'directory' ? await listOpfs(INSTALL_ROOT + '/' + t.name, '', []) : [];
      const entry = mainFile(mk, files);
      if (!entry) continue;
      out.push({ id: t.name, title: mk.title || t.name, team: mk.team, kind: mk.kind || 'folder', entry });
    }
    return out.sort((a, b) => a.title.localeCompare(b.title));
  }
  async function renderHome() {
    if (!_shareListEl || !O()) return;
    if (homeBusy) { homePending = true; return; } homeBusy = true;
    try {
      const box = _shareListEl;
      const list = await acceptedList();
      if (_shareTotalEl) _shareTotalEl.textContent = list.length + ' app' + (list.length === 1 ? '' : 's') + ' from the team hub';
      if (_shareEmptyEl) _shareEmptyEl.style.display = list.length ? 'none' : '';
      if (!list.length) { box.innerHTML = ''; return; }
      // No remove button: an artifact leaves this list by leaving the hub.
      // Skills carry an "installed skill" badge instead of a pin button — they
      // live in the model's skill index, not on the home screen.
      box.innerHTML = list.map((g, i) =>
        '<div class="shared-file" data-i="' + i + '">' +
          '<button class="shared-file-open">' + (g.kind === 'skill' ? '🧩' : '📁') + ' ' + esc(g.title) + '</button>' +
          '<span class="shared-by">from ' + esc(g.team) + '</span>' +
          (g.kind === 'skill' ? '<span class="shared-skill-badge">installed skill</span>' : '<button class="shared-pin"></button>') +
        '</div>').join('');
      for (const row of box.querySelectorAll('.shared-file')) {
        const g = list[+row.getAttribute('data-i')];
        const full = INSTALL_ROOT + '/' + g.id + '/' + g.entry;
        row.querySelector('.shared-file-open').onclick = () => { try { opfs.openFile(full, g.entry.split('/').pop()); } catch (_) {} };
        const pb = row.querySelector('.shared-pin');
        if (pb) { if (window.SandpiePins) { try { SandpiePins.bindButton(pb, full); } catch (_) { pb.remove(); } } else pb.remove(); }
      }
    } catch (e) { console.warn('[sharing] renderHome failed', e); } finally { homeBusy = false; if (homePending) { homePending = false; renderHome(); } }
  }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  /* ── share dialog ────────────────────────────────────────────────────── */
  async function shareDialog(srcPath) {
    const src = skillTarget(norm(srcPath || ''));   // a SKILL.md shares its whole skill folder
    const dir = await isDir(src);
    const folderFiles = (await srcFileList(src, dir)).filter(f => !SKIP(f)).sort();
    const skill = dir && folderFiles.includes('SKILL.md');
    // Skills are titled by the skill name (frontmatter, else folder), never "SKILL.md".
    const dlgName = (skill && await skillFmName(src)) || src.split('/').pop();
    const defPin = skill ? 'SKILL.md' : folderFiles.includes('index.html') ? 'index.html' : folderFiles[0];
    const back = document.createElement('div'); back.className = 'share-modal-back';
    back.innerHTML =
      '<div class="share-modal" data-chrome>' +
        '<div class="share-modal-h">Share “' + esc(dlgName) + '”' + (skill ? ' <span class="shared-skill-badge">skill</span>' : '') + '</div>' +
        '<label class="share-opt">Department: <select class="share-in" data-k="team"><option value="">loading…</option></select></label>' +
        // A skill's main file is SKILL.md by definition — no selector to show.
        (dir && !skill ? '<div class="share-pin-file"><label class="share-opt">Main file: <select class="share-in" data-k="pinfile">' + folderFiles.map(f => '<option value="' + esc(f) + '"' + (f === defPin ? ' selected' : '') + '>' + esc(f) + '</option>').join('') + '</select></label></div>' : '') +
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
        const pinFile = skill ? 'SKILL.md' : dir ? (back.querySelector('[data-k="pinfile"]').value || '') : src.split('/').pop();
        const out = await publish(src, dept, { pinFile });
        msg.textContent = '✓ Shared to ' + dept + (out.id ? ' (' + out.id + ')' : '') + '.';
        await autoSync({ full: true });
        setTimeout(close, 900);
      } catch (e) { msg.textContent = 'Error: ' + ((e && e.message) || e); }
    };
  }

  /* ── opfs helpers ────────────────────────────────────────────────────── */
  async function isDir(p) { try { await O().listDir(p); return true; } catch (_) { return false; } }
  async function readLocal(p) { try { return await O().readBytes(p); } catch (_) { return null; } }
  async function listOpfs(base, rel, out) {
    let entries; try { entries = await O().listDir(base + (rel ? '/' + rel : '')); } catch (_) { return out; }
    for (const e of entries) { const r = rel ? rel + '/' + e.name : e.name; if (e.kind === 'directory') await listOpfs(base, r, out); else out.push(r); }
    return out;
  }

  /* ── Settings → Sharing tab ──────────────────────────────────────────── */
  // The shared/team lists moved off the home screen into this modal tab. The
  // tab renders once (lazy); renderHome() paints into it on every refresh.
  function registerSharingTab() {
    if (typeof SandpieSettings === 'undefined' || !SandpieSettings.register) return;
    SandpieSettings.register({
      id: 'sharing', title: 'Sharing', order: 42,
      render(panel) {
        panel.innerHTML = '';
        const head = document.createElement('div');
        head.className = 'share-head';
        const h = document.createElement('h3'); h.textContent = 'Sharing';
        _shareTotalEl = document.createElement('span');
        _shareTotalEl.className = 'share-total';
        head.append(h, _shareTotalEl);
        const sec = document.createElement('div');
        sec.className = 'share-sec-title'; sec.textContent = 'From the team hub (auto-synced)';
        _shareListEl = document.createElement('ul'); _shareListEl.className = 'share-list';
        _shareEmptyEl = document.createElement('div');
        _shareEmptyEl.className = 'share-empty-hint';
        _shareEmptyEl.textContent = 'Nothing shared with you yet — apps appear here automatically when a teammate publishes to the hub.';
        panel.append(head, sec, _shareListEl, _shareEmptyEl);
      },
      onShow() { renderHome(); },   // refresh on every activation, not just first render
    });
  }

  /* ── boot ────────────────────────────────────────────────────────────── */
  function boot() {
    registerSharingTab();
    renderHome(); autoSync({ full: true });
    // First paint of the home-screen +Add badge: pins.js loads BEFORE this
    // module, so it can't read the count at its own init — push it a change.
    try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {}
  }   // first pass always reads the real listing
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  const SHARE_POLL_MS = 60000;
  const pollShares = () => { autoSync(); renderHome(); };
  setInterval(() => { if (!document.hidden) pollShares(); }, SHARE_POLL_MS);
  window.addEventListener('focus', pollShares);
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('sync:done', () => renderHome()); } catch (_) {}
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('file:changed', wbOnChanged); } catch (_) {}
  try {
    if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('message', (ev) => {
      const d = ev.data; if (!d) return;
      const paths = (d.type === 'sw-opfs-changed' && Array.isArray(d.paths)) ? d.paths
                  : (d.type === 'forward-to-page' && d.payload && d.payload.type === 'sw-opfs-changed' && Array.isArray(d.payload.paths)) ? d.payload.paths : null;
      if (paths) for (const p of paths) wbOnChanged(p);
    });
  } catch (_) {}

  window.SandpieSharing = { me, setIdentity, publish, autoSync, uninstall, subscribe, shareDialog, teams, teamRoot, acceptedList, fire, INSTALL_ROOT };
})();
