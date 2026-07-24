// sharing.js — share skills / artifacts / folders across the org, scoped, with
// silent auto-update. Browser-only; rides the existing Dropbox team folder.
//
// PATHS (named for clarity):
//   • TEAM hub (shared by all)    <parent>/shared-hub/                  (Dropbox API;
//     outside every workspace, so recipients POLL it)
//   • per-user INCOMING (1:1)     <parent>/<recipient>/sandpie/shared-incoming/
//     (a 1:1 delivery is written straight here; the recipient's own sync pulls it —
//      no polling — and it's physically private to them)
//   • per-user INSTALLED          <recipient>/sandpie/shared-installed/  (read-only,
//     accepted packages; the worker's read-only guard keys on this prefix)
//   where <parent> = the folder every user's workspace sits under (workspace root's
//   parent), e.g. /R+D+I/sandpie ; workspace = <parent>/<email-local-part>.
//
// A published package is a folder:  packages/<id>/manifest.json + <files…> (FLAT —
//   overwritten each publish; Dropbox keeps prior revisions for rollback).
//   manifest = { id, kind:'skill'|'artifact'|'folder', title, publisher, rev,
//                acl:{org,users[],teams[]}, pin:<relFile>|null, skill:bool, ts }
//   Per-package manifests (not one shared index) → no multi-writer clobber.
//
// ACCEPT (keep the accept step): install the package into the read-only
//   sandpie/shared-installed/<id>/, THEN apply manifest directives:
//     • skill:true  → already discovered + loadable there (context.js/load_skill)
//     • pin:<file>  → SandpiePins.add(sandpie/shared-installed/<id>/<file>) → home grid
//   Plain files just sit in sandpie/shared-installed/ and show in "Shared with me".
//   Silent auto-update advances accepted subs to the latest rev on boot/focus.
//
// SEAM (needs 2 real team accounts to verify): the cloud transport
//   (cloudUpload/Download/List via dropbox.js). Falls back to a LOCAL sim hub
//   (under sandpie/shared-incoming) when Dropbox isn't connected, so the full
//   lifecycle is testable offline via SandpieSharing.setIdentity({user,teams}).
(function () {
  'use strict';
  const INSTALL_ROOT = 'sandpie/shared-installed';   // read-only accepted packages (worker guard keys on this)
  const LOCAL_HUB = 'sandpie/shared-incoming';       // per-user 1:1 inbox (1:1 deliveries sync in here) + offline sim hub
  const SUBS_PATH = 'sandpie/config/shares.json';   // team-share subscription state only (1:1 uses the filesystem)
  const PKG_MARKER = '.sandpie-pkg.json';           // per-installed-package marker: {id,title,kind,publisher,pin,rev}
  const ID_OVERRIDE_KEY = 'sandpie-share-identity';
  const slug = (s) => String(s || '').toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'pkg';
  const localPart = (email) => String(email || '').split('@')[0].toLowerCase();
  const O = () => window.opfs;
  const prov = () => { try { return window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider(); } catch (_) { return null; } };
  const cloudOn = () => { const p = prov(); return !!(p && p.cloudConnected && p.cloudConnected()); };

  /* ── identity ─────────────────────────────────────────────────────────── */
  function me() {
    try { const o = JSON.parse(localStorage.getItem(ID_OVERRIDE_KEY) || 'null'); if (o && o.user) return { user: String(o.user), teams: Array.isArray(o.teams) ? o.teams : [] }; } catch (_) {}
    try { const u = window.SandpieAccount && SandpieAccount.current && SandpieAccount.current(); if (u && (u.email || u.name)) return { user: String(u.email || u.name), teams: Array.isArray(u.teams) ? u.teams : [] }; } catch (_) {}
    return { user: 'me@local', teams: [] };
  }
  function setIdentity(id) { if (id) localStorage.setItem(ID_OVERRIDE_KEY, JSON.stringify(id)); else localStorage.removeItem(ID_OVERRIDE_KEY); fire(); }

  /* ── stores (uniform read/write over a hub root) ──────────────────────── */
  function markDirty(p) { try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', p); } catch (_) {} }
  async function listOpfs(base, rel, out) {
    let entries; try { entries = await O().listDir(base + (rel ? '/' + rel : '')); } catch (_) { return out; }
    for (const e of entries) {
      const r = rel ? rel + '/' + e.name : e.name;
      if (e.kind === 'directory') await listOpfs(base, r, out); else out.push(r);
    }
    return out;
  }
  function localStore(root) {
    return {
      kind: 'local', root,
      async listFiles(sub) { return await listOpfs(root + (sub ? '/' + sub : ''), '', []); },
      async listDirs(sub) { try { return (await O().listDir(root + (sub ? '/' + sub : ''))).filter(e => e.kind === 'directory').map(e => e.name); } catch (_) { return []; } },
      async readText(rel) { try { return await O().read(root + '/' + rel); } catch (_) { return null; } },
      async readBytes(rel) { try { return await O().readBytes(root + '/' + rel); } catch (_) { return null; } },
      async writeBytes(rel, bytes) { await O().write(root + '/' + rel, new Blob([bytes])); markDirty(root + '/' + rel); },
      async writeText(rel, txt) { await O().write(root + '/' + rel, new Blob([txt], { type: 'application/json' })); markDirty(root + '/' + rel); },
    };
  }
  function cloudStore(absRoot) {
    const P = () => prov();
    const strip = (p) => { const i = p.toLowerCase().indexOf(absRoot.toLowerCase() + '/'); return i >= 0 ? p.slice(i + absRoot.length + 1) : p.replace(/^\/+/, ''); };
    return {
      kind: 'cloud', root: absRoot,
      async listFiles(sub) { const base = absRoot + (sub ? '/' + sub : ''); return (await P().cloudList(base, true)).filter(e => e.kind === 'file').map(e => strip(e.path)); },
      async listDirs(sub) { const base = absRoot + (sub ? '/' + sub : ''); return (await P().cloudList(base, false)).filter(e => e.kind === 'directory').map(e => e.path.split('/').pop()); },
      async readText(rel) { try { return new TextDecoder().decode(await P().cloudDownload(absRoot + '/' + rel)); } catch (_) { return null; } },
      async readBytes(rel) { try { return await P().cloudDownload(absRoot + '/' + rel); } catch (_) { return null; } },
      async writeBytes(rel, bytes) { await P().cloudUpload(absRoot + '/' + rel, bytes); },
      async writeText(rel, txt) { await P().cloudUpload(absRoot + '/' + rel, new TextEncoder().encode(txt)); },
    };
  }
  // The hubs this identity can reach. Cloud mode uses real Dropbox paths; offline
  // mode simulates the per-user folders under one local hub, partitioned by identity
  // (_team = shared hub, _inbox/<user> = each person's private 1:1 inbox) so tests
  // faithfully model who-can-see-what.
  function teamHub() { const p = prov(); return (cloudOn() && p.cloudParent && p.cloudParent()) ? cloudStore(p.cloudParent() + '/shared-hub') : localStore(LOCAL_HUB + '/_team'); }
  function recipientHub(email) { const p = prov(); return (cloudOn() && p.cloudParent && p.cloudParent()) ? cloudStore(p.cloudParent() + '/' + localPart(email) + '/sandpie/shared-incoming') : localStore(LOCAL_HUB + '/_inbox/' + localPart(email)); }
  function myInbox() { return cloudOn() ? localStore(LOCAL_HUB) : localStore(LOCAL_HUB + '/_inbox/' + localPart(me().user)); }   // real: 1:1 deliveries sync into my own hub

  /* ── subscriptions ────────────────────────────────────────────────────── */
  // Real mode: one shares.json in the user's own (per-user) workspace. Offline sim:
  // partition by identity so simulated users don't share each other's accept state.
  function subsPath() { return cloudOn() ? SUBS_PATH : 'sandpie/config/shares.' + localPart(me().user) + '.json'; }
  async function subs() { let s = null; try { s = JSON.parse(await O().read(subsPath())); } catch (_) {} return (s && typeof s === 'object') ? { accepted: s.accepted || {}, dismissed: s.dismissed || [] } : { accepted: {}, dismissed: [] }; }
  async function saveSubs(s) { const p = subsPath(); await O().write(p, new Blob([JSON.stringify(s, null, 2)], { type: 'application/json' })); markDirty(p); }

  function entitled(m, who) {
    const a = m.acl || {};
    if (a.org) return true;
    if (Array.isArray(a.users) && a.users.map(String).includes(who.user)) return true;
    if (Array.isArray(a.teams) && a.teams.some(t => who.teams.includes(t))) return true;
    return false;
  }

  /* ── package IO over a store ──────────────────────────────────────────── */
  async function readManifest(store, id) { const t = await store.readText('packages/' + id + '/manifest.json'); if (!t) return null; try { return JSON.parse(t); } catch (_) { return null; } }
  async function listManifests(store) {
    const ids = await store.listDirs('packages'); const out = [];
    for (const id of ids) { const m = await readManifest(store, id); if (m) out.push({ ...m, _store: store }); }
    return out;
  }

  /* ── publish ──────────────────────────────────────────────────────────── */
  async function isDir(p) { try { await O().listDir(p); return true; } catch (_) { return false; } }
  async function fileExists(p) { try { await O().readBytes(p); return true; } catch (_) { return false; } }
  // audience { org?, users?:[email], teams?:[id] }; opts { kind?, title?, id?, pin?:bool }
  async function publish(srcPath, audience, opts) {
    opts = opts || {};
    const src = String(srcPath || '').replace(/^\/+/, '').replace(/\/+$/, '');
    if (!src) throw new Error('publish: srcPath required');
    if (src.startsWith(INSTALL_ROOT + '/') || src.startsWith(LOCAL_HUB + '/')) throw new Error('publish: share your own file, not a managed/hub path');
    const dir = await isDir(src), base = src.split('/').pop();
    const kind = opts.kind || (dir ? (await fileExists(src + '/SKILL.md') ? 'skill' : 'folder') : 'artifact');
    const id = opts.id || slug(base);

    // collect the source file list (rel paths under the version dir)
    const files = dir ? await listOpfs(src, '', []) : [base];
    const readSrc = (rel) => dir ? O().readBytes(src + '/' + rel) : O().readBytes(src);

    // destinations: team → one team hub; 1:1 → each recipient's inbox hub.
    const dests = [];
    if (audience.org || (audience.teams && audience.teams.length)) dests.push(teamHub());
    for (const u of (audience.users || [])) dests.push(recipientHub(u));
    if (!dests.length) throw new Error('publish: no audience');

    const acl = { org: !!audience.org, users: (audience.users || []).map(String), teams: (audience.teams || []).map(String) };
    // pin target: explicit opts.pinFile (a rel path within the folder) wins; else the
    // artifact itself, else the folder's first file as a fallback.
    const pinFile = opts.pin ? (opts.pinFile && files.includes(opts.pinFile) ? opts.pinFile : (kind === 'artifact' ? base : (files[0] || ''))) : null;
    let rev = 1;
    for (const store of dests) {
      const prev = await readManifest(store, id);
      rev = (prev ? parseInt(prev.rev, 10) || 0 : 0) + 1;
      // Files live FLAT under packages/<id>/ (no v/<n>/ dirs) — overwritten each
      // publish. Dropbox keeps prior revisions for rollback; `rev` just bumps so
      // subscribers notice an update.
      for (const rel of files) { const bytes = await readSrc(rel); if (bytes) await store.writeBytes('packages/' + id + '/' + rel, bytes); }
      const manifest = { id, kind, title: opts.title || base, publisher: me().user, rev, acl, pin: pinFile, skill: kind === 'skill', ts: 0 };
      await store.writeText('packages/' + id + '/manifest.json', JSON.stringify(manifest, null, 2));
    }
    fire();
    return { id, rev, kind, dests: dests.map(d => d.kind + ':' + d.root) };
  }

  /* ── catalog (what's available TO ME) ─────────────────────────────────── */
  // Merge my 1:1 inbox (local, synced in) + the team hub (polled). Team manifests
  // are ACL-filtered; inbox manifests are addressed to me by construction.
  async function catalog() {
    const who = me(), byId = {};
    for (const m of await listManifests(myInbox())) { m._from = 'incoming'; byId[m.id] = m; }   // 1:1: a file in shared-incoming IS the pending notification
    for (const m of await listManifests(teamHub())) if (!byId[m.id] && entitled(m, who)) { m._from = 'team'; byId[m.id] = m; }
    return byId;
  }

  // Pending invites (the notification list):
  //   • incoming (1:1)  → its mere PRESENCE in shared-incoming = pending. Accept MOVES
  //     it out (→ shared-installed) which clears the notification; a re-share re-delivers
  //     a fresh file and re-notifies. No accepted-state cache, so nothing goes stale.
  //   • team            → tracked in shares.json (accepted/dismissed) for silent auto-update.
  async function pendingInvites() {
    const who = me(), cat = await catalog(), s = await subs(), out = [];
    for (const id in cat) {
      const m = cat[id];
      if (m.publisher === who.user) continue;
      if (m._from === 'incoming') { out.push(m); continue; }   // present ⇒ pending (accept consumes it)
      if (s.accepted[id] != null || s.dismissed.includes(id)) continue;
      out.push(m);
    }
    return out;
  }
  // "Shared with me" = whatever is physically installed (each package carries a small
  // .sandpie-pkg.json marker written at install), independent of shares.json.
  async function acceptedList() {
    const out = [];
    let dirs = []; try { dirs = (await O().listDir(INSTALL_ROOT)).filter(e => e.kind === 'directory').map(e => e.name); } catch (_) {}
    for (const id of dirs) {
      let mk = null; try { mk = JSON.parse(await O().read(INSTALL_ROOT + '/' + id + '/' + PKG_MARKER)); } catch (_) {}
      out.push(mk || { id, title: id, kind: 'folder' });
    }
    return out;
  }

  /* ── accept / install / activate ──────────────────────────────────────── */
  async function install(m) {
    const store = m._store, dst = INSTALL_ROOT + '/' + m.id;
    const files = (await store.listFiles('packages/' + m.id)).filter(rel => rel !== 'manifest.json');
    for (const rel of files) {
      const bytes = await store.readBytes('packages/' + m.id + '/' + rel);
      if (!bytes) continue;
      const p = dst + '/' + rel;
      await O().write(p, new Blob([bytes]));
      markDirty(p);   // emit file:changed so Dropbox marks it dirty + uploads it — without this the
                      // reconciliation pass deletes it as a local-only orphan under the eager prefix
    }
    // marker so "Shared with me" + rollback-free identification work without shares.json
    const mp = dst + '/' + PKG_MARKER;
    await O().write(mp, new Blob([JSON.stringify({ id: m.id, title: m.title, kind: m.kind, publisher: m.publisher, pin: m.pin || null, rev: m.rev })], { type: 'application/json' }));
    markDirty(mp);
    // apply directives
    if (m.pin && window.SandpiePins) { try { SandpiePins.add(dst + '/' + m.pin); } catch (_) {} }
    // skill:true → nothing to move; context.js discovers sandpie/shared-installed/<id>/SKILL.md and load_skill resolves it
    try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id: m.id, rev: m.rev } })); } catch (_) {}
  }
  // Delete a 1:1 package from shared-incoming (local + Dropbox) — used by accept (move)
  // and dismiss. file:deleted propagates the removal to the recipient's Dropbox folder.
  async function consumeIncoming(m) {
    const base = m._store.root + '/packages/' + m.id;
    for (const rel of await listOpfs(base, '', [])) {
      const p = base + '/' + rel;
      try { await O().remove(p); } catch (_) {}
      try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', p); } catch (_) {}
    }
    try { await O().remove(base); } catch (_) {}   // drop the now-empty package dir (local)
  }
  async function accept(id) {
    const cat = await catalog(); const m = cat[id]; if (!m) return;
    await install(m);
    if (m._from === 'incoming') { await consumeIncoming(m); }                 // MOVE: clears the notification
    else { const s = await subs(); s.accepted[id] = m.rev; s.dismissed = s.dismissed.filter(x => x !== id); await saveSubs(s); }
    fire();
  }
  async function dismiss(id) {
    const cat = await catalog(); const m = cat[id];
    if (m && m._from === 'incoming') { await consumeIncoming(m); fire(); return; }   // delete without installing
    const s = await subs(); if (!s.dismissed.includes(id)) s.dismissed.push(id); await saveSubs(s); fire();
  }

  /* ── silent auto-update ───────────────────────────────────────────────── */
  let syncing = false;
  async function autoSync() {
    if (syncing || !O()) return; syncing = true;
    try {
      const cat = await catalog(), s = await subs(); let changed = false;
      // Team subscriptions only. 1:1 shares are never in shares.json (they're accepted
      // by moving the file), so a re-delivered 1:1 shows as a fresh invite instead of
      // silently re-installing — the bug this guard prevents.
      for (const id in s.accepted) { const m = cat[id]; if (!m || m._from !== 'team') continue; if (String(m.rev) !== String(s.accepted[id])) { await install(m); s.accepted[id] = m.rev; changed = true; } }
      if (changed) { await saveSubs(s); fire(); }
    } catch (e) { console.warn('[sharing] autoSync failed:', e); } finally { syncing = false; }
  }

  /* ── events ───────────────────────────────────────────────────────────── */
  function fire() { try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {} renderHome(); }
  function subscribe(cb) { const h = () => cb(); window.addEventListener('sandpie-shares-changed', h); return () => window.removeEventListener('sandpie-shares-changed', h); }

  const Sharing = { me, setIdentity, catalog, subs, entitled, publish, pendingInvites, acceptedList, accept, dismiss, autoSync, subscribe, shareDialog, teamHub, recipientHub, INSTALL_ROOT, LOCAL_HUB };
  window.SandpieSharing = Sharing;

  /* ── share dialog ─────────────────────────────────────────────────────── */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function splitList(s) { return String(s || '').split(/[,\s]+/).map(x => x.trim()).filter(Boolean); }
  async function shareDialog(srcPath, presetKind) {
    const who = me();
    const src = String(srcPath || '').replace(/^\/+/, '').replace(/\/+$/, '');
    // For a folder share, list its files so the publisher can choose WHICH one to pin.
    const folder = await isDir(src);
    const folderFiles = folder ? await listOpfs(src, '', []) : [];
    const back = document.createElement('div'); back.className = 'share-modal-back';
    back.innerHTML =
      '<div class="share-modal" data-chrome>' +
        '<div class="share-modal-h">Share “' + esc(src.split('/').pop()) + '”</div>' +
        '<label class="share-opt"><input type="radio" name="aud" value="org" checked> Everyone in the org</label>' +
        (who.teams.length ? '<label class="share-opt"><input type="radio" name="aud" value="teams"> Team(s): <input class="share-in" data-k="teams" placeholder="' + esc(who.teams.join(', ')) + '"></label>'
                          : '<label class="share-opt share-dim"><input type="radio" name="aud" value="teams" disabled> Teams (no team directory yet)</label>') +
        '<label class="share-opt"><input type="radio" name="aud" value="users"> Specific people: <input class="share-in" data-k="users" placeholder="email, email…"></label>' +
        '<label class="share-opt share-pin"><input type="checkbox" data-k="pin"> Pin to their home screen</label>' +
        (folder ? '<div class="share-pin-file" style="display:none;"><label class="share-opt">Pin which file: <select class="share-in" data-k="pinfile">' +
                    folderFiles.map(f => '<option value="' + esc(f) + '">' + esc(f) + '</option>').join('') +
                  '</select></label></div>' : '') +
        '<div class="share-modal-btns"><button class="ghost" data-act="cancel">Cancel</button><button class="ghost share-primary" data-act="share">Share</button></div>' +
        '<div class="share-modal-msg"></div>' +
      '</div>';
    document.body.appendChild(back);
    const close = () => back.remove();
    back.addEventListener('click', (e) => { if (e.target === back) close(); });
    back.querySelector('[data-act="cancel"]').onclick = close;
    // Reveal the "which file" picker only when pinning a folder.
    const pinBox = back.querySelector('[data-k="pin"]');
    const pinFileRow = back.querySelector('.share-pin-file');
    if (pinFileRow) pinBox.addEventListener('change', () => { pinFileRow.style.display = pinBox.checked ? '' : 'none'; });
    back.querySelector('[data-act="share"]').onclick = async () => {
      const sel = back.querySelector('input[name="aud"]:checked').value, audience = {};
      if (sel === 'org') audience.org = true;
      else if (sel === 'teams') audience.teams = splitList(back.querySelector('.share-in[data-k="teams"]').value) || who.teams;
      else audience.users = splitList(back.querySelector('.share-in[data-k="users"]').value);
      if ((sel === 'users' && !(audience.users || []).length) || (sel === 'teams' && !(audience.teams || []).length)) { back.querySelector('.share-modal-msg').textContent = 'Enter at least one ' + (sel === 'users' ? 'email' : 'team') + '.'; return; }
      const pin = !!pinBox.checked;
      const pinSel = back.querySelector('.share-in[data-k="pinfile"]');
      const pinFile = pin && folder && pinSel ? pinSel.value : undefined;
      const msg = back.querySelector('.share-modal-msg'); msg.textContent = 'Sharing…';
      try { const r = await publish(srcPath, audience, { kind: presetKind, pin, pinFile }); msg.textContent = 'Shared (v' + r.rev + ') → ' + (sel === 'org' ? 'everyone' : sel === 'teams' ? audience.teams.join(', ') : audience.users.join(', ')) + (pin ? ', pinned ' + (pinFile || 'file') : '') + (cloudOn() ? '' : ' [local test — Dropbox not connected]'); setTimeout(close, 1400); }
      catch (e) { msg.textContent = 'Share failed: ' + ((e && e.message) || e); }
    };
  }

  /* ── home inbox + installed list ──────────────────────────────────────── */
  let homeBusy = false, homePending = false;
  async function renderHome() {
    const welcome = document.getElementById('welcome'); if (!welcome || !O()) return;
    if (homeBusy) { homePending = true; return; } homeBusy = true;
    try {
      let box = document.getElementById('sharedHome');
      if (!box) { box = document.createElement('div'); box.id = 'sharedHome'; box.className = 'shared-home'; welcome.appendChild(box); }
      let invites = [], installed = [];
      try { invites = await pendingInvites(); installed = await acceptedList(); } catch (_) {}
      box.textContent = '';
      if (!invites.length && !installed.length) { box.style.display = 'none'; return; }
      box.style.display = '';
      if (invites.length) { const h = document.createElement('div'); h.className = 'shared-home-title'; h.textContent = '📥 Shared with you'; box.appendChild(h); for (const m of invites) box.appendChild(inviteRow(m)); }
      if (installed.length) { const h = document.createElement('div'); h.className = 'shared-home-title'; h.textContent = '🔗 Shared with me'; box.appendChild(h); for (const m of installed) box.appendChild(installedRow(m)); }
    } finally { homeBusy = false; if (homePending) { homePending = false; renderHome(); } }
  }
  const kindIcon = (k) => k === 'skill' ? '🧩' : k === 'folder' ? '📁' : '📄';
  function inviteRow(m) {
    const row = document.createElement('div'); row.className = 'shared-file invite';
    row.innerHTML = '<span class="shared-file-name">' + kindIcon(m.kind) + ' ' + esc(m.title) + '</span><span class="shared-by">from ' + esc(m.publisher) + '</span>';
    const acc = document.createElement('button'); acc.className = 'ghost shared-accept'; acc.textContent = 'Accept'; acc.onclick = () => accept(m.id);
    const dis = document.createElement('button'); dis.className = 'shared-dismiss'; dis.title = 'Dismiss'; dis.textContent = '✕'; dis.onclick = () => dismiss(m.id);
    row.append(acc, dis); return row;
  }
  function installedRow(m) {
    const row = document.createElement('div'); row.className = 'shared-file';
    const open = document.createElement('button'); open.className = 'shared-file-open'; open.innerHTML = kindIcon(m.kind) + ' ' + esc(m.title);
    open.title = m.kind === 'skill' ? 'Shared skill — the model can load it by name' : INSTALL_ROOT + '/' + m.id;
    open.onclick = () => { const entry = m.pin || (m.kind === 'artifact' ? m.title : ''); if (entry) { try { opfs.openFile(INSTALL_ROOT + '/' + m.id + '/' + entry, entry.split('/').pop()); } catch (_) {} } };
    row.append(open); return row;
  }

  /* ── boot ─────────────────────────────────────────────────────────────── */
  function boot() { renderHome(); autoSync(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  window.addEventListener('focus', () => autoSync());
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('sync:done', () => autoSync()); } catch (_) {}
})();
