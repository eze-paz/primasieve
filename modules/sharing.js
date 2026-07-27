// sharing.js — share skills / artifacts / folders across the org, scoped, with
// silent auto-update. Browser-only; rides the existing Dropbox team folder.
//
// PATHS (named for clarity):
//   • TEAM hub (shared by all)    <teamParent>/shared-hub/              (Dropbox API;
//     outside every workspace, so recipients POLL it). <teamParent> =
//     provider.cloudParent(), default /R+D+I/sandpie; '' on a non-team account.
//   • 1:1 delivery                 addressed by EMAIL, no shared folder required.
//     The sender's own Dropbox holds an outbox per recipient, shared with them via
//     the Dropbox sharing API (provider.shareEnsureOutbox); the recipient finds the
//     invite with shareListIncoming() and accepts it with shareMount(). See the
//     "Dropbox sharing API" section of dropbox.js for the exact layout.
//     This replaces the old assumption that both people could already reach one
//     team folder — now the only input needed is an email address.
//   • per-user INSTALLED          sandpie/shared-installed/  (in the recipient's own
//     workspace; read-only accepted packages, the worker's guard keys on this prefix)
//
// 1:1 recipients are VIEWERS on the sender's outbox, so they cannot delete a
// package they've consumed. Accept/dismiss is therefore recorded in the
// recipient's own shares.json, keyed "<id>@<rev>" — a re-share bumps rev, which
// produces a new key and re-notifies. (Team packages are unchanged: auto-install,
// tracked by the installed marker's rev.)
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
  const COLLAPSE_KEY = 'sandpie-shared-collapsed';      // "Shared with me" collapsed state (per device)
  const TEAM_COLLAPSE_KEY = 'sandpie-team-collapsed';   // "Team artifacts" collapsed state (per device)
  const ID_OVERRIDE_KEY = 'sandpie-share-identity';
  const slug = (s) => String(s || '').toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'pkg';
  const localPart = (email) => String(email || '').split('@')[0].toLowerCase();
  const O = () => window.opfs;
  const prov = () => { try { return window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider(); } catch (_) { return null; } };
  const cloudOn = () => { const p = prov(); return !!(p && p.cloudConnected && p.cloudConnected()); };

  /* ── identity ─────────────────────────────────────────────────────────── */
  function me() {
    try { const o = JSON.parse(localStorage.getItem(ID_OVERRIDE_KEY) || 'null'); if (o && o.user) return { user: String(o.user), teams: Array.isArray(o.teams) ? o.teams : [] }; } catch (_) {}
    let teams = [];
    try { const u = window.SandpieAccount && SandpieAccount.current && SandpieAccount.current(); if (u && Array.isArray(u.teams)) teams = u.teams; } catch (_) {}
    // Prefer the DROPBOX account email when connected. 1:1 shares are addressed to
    // a Dropbox email and Dropbox decides who receives them, so that address has to
    // be the same identity used for "is this mine?" (publisher gate, skip-my-own)
    // and for team ACL matching — otherwise a user whose SSO email differs from
    // their Dropbox email is two different people to this module.
    try { const p = prov(); const e = p && p.accountEmail && p.accountEmail(); if (e) return { user: String(e), teams }; } catch (_) {}
    try { const u = window.SandpieAccount && SandpieAccount.current && SandpieAccount.current(); if (u && (u.email || u.name)) return { user: String(u.email || u.name), teams }; } catch (_) {}
    return { user: 'me@local', teams };
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
  // `opt` picks the namespace the paths resolve in:
  //   {team:true}  the team space  — the shared hub
  //   {team:false} the home namespace — my own Dropbox
  //   {ns:'<shared_folder_id>'} somebody else's shared folder, read IN PLACE
  //     without mounting it. Paths are then relative to that folder, so absRoot
  //     is '' and rel becomes '/packages/…'.
  function cloudStore(absRoot, opt) {
    const P = () => prov();
    opt = (opt === true || opt === false) ? { team: opt } : (opt || { team: true });
    return {
      kind: 'cloud', root: absRoot, ns: opt.ns || '', team: !!opt.team,
      async listFiles(sub) {
        // Return paths RELATIVE TO `base` (the sub dir), like localStore — install()
        // does readBytes('packages/<id>/' + rel), so rel must NOT re-include that prefix.
        const base = absRoot + (sub ? '/' + sub : ''), bl = base.toLowerCase() + '/';
        return (await P().cloudList(base, true, opt)).filter(e => e.kind === 'file').map(e => {
          const i = e.path.toLowerCase().indexOf(bl);
          return i >= 0 ? e.path.slice(i + base.length + 1) : e.path.split('/').pop();
        });
      },
      async listDirs(sub) { const base = absRoot + (sub ? '/' + sub : ''); return (await P().cloudList(base, false, opt)).filter(e => e.kind === 'folder' || e.kind === 'directory').map(e => e.path.split('/').pop()); },   // Dropbox tags folders 'folder', not 'directory'
      async readText(rel) { try { return new TextDecoder().decode(await P().cloudDownload(absRoot + '/' + rel, opt)); } catch (_) { return null; } },
      async readBytes(rel) { try { return await P().cloudDownload(absRoot + '/' + rel, opt); } catch (_) { return null; } },
      async writeBytes(rel, bytes) { await P().cloudUpload(absRoot + '/' + rel, bytes, opt); },
      async writeText(rel, txt) { await P().cloudUpload(absRoot + '/' + rel, new TextEncoder().encode(txt), opt); },
    };
  }
  // The hubs this identity can reach. Cloud mode uses real Dropbox paths; offline
  // mode simulates the per-user folders under one local hub, partitioned by identity
  // (_team = shared hub, _inbox/<user> = each person's private 1:1 inbox) so tests
  // faithfully model who-can-see-what.
  // TEAM hub needs a team space; without one (cloudParent() === '') it falls back
  // to the local simulation, same as being offline. 1:1 does NOT need a team space
  // — it goes through the Dropbox sharing API instead.
  function hubRoot() { const p = prov(); return (cloudOn() && p.cloudParent && p.cloudParent()) ? (p.cloudParent() + '/shared-hub') : ''; }
  function teamHub() { const h = hubRoot(); return h ? cloudStore(h, { team: true }) : localStore(LOCAL_HUB + '/_team'); }
  const canShare1to1 = () => { const p = prov(); return !!(cloudOn() && p && p.shareEnsureOutbox); };
  // SENDER side: the outbox shared with this email, created + invited on first use.
  // Async because setting up a Dropbox share is a few API calls.
  async function recipientHub(email) {
    if (!canShare1to1()) return localStore(LOCAL_HUB + '/_inbox/' + localPart(email));
    const box = await prov().shareEnsureOutbox(String(email));
    return cloudStore(box.path, { team: false });   // the sender's own Dropbox = home namespace
  }
  // RECIPIENT side. One cached listing per pass serves both the mounted stores and
  // the pending-mount rows — shareListIncoming() is a couple of API calls and both
  // renderHome() and autoSync() want it.
  let _incomingCache = null;
  async function incomingShares(force) {
    if (!canShare1to1()) return [];
    if (_incomingCache && !force) return _incomingCache;
    try { _incomingCache = await prov().shareListIncoming(); }
    catch (e) { console.warn('[sharing] could not list incoming shares:', (e && e.message) || e); _incomingCache = _incomingCache || []; }
    return _incomingCache;
  }
  function invalidateIncoming() { _incomingCache = null; _needsMount.clear(); }
  // One store per sender, read BY NAMESPACE — mounted or not, nothing is added to
  // the recipient's Dropbox. Paths are relative to the shared folder, so root ''.
  async function incomingStores(force) {
    if (!canShare1to1()) return [localStore(LOCAL_HUB + '/_inbox/' + localPart(me().user))];
    return (await incomingShares(force)).filter(s => !_needsMount.has(s.id)).map(s => {
      const st = cloudStore('', { ns: s.id });
      st.from = s.from; st.shareId = s.id;
      return st;
    });
  }
  // Shares whose namespace read was REFUSED (PathRootError.no_permission, or a team
  // configuration that insists on the automounter). Those are the only ones that
  // still need an explicit mount, so they're the only ones that surface a mount row.
  // Populated by catalog(); normally empty.
  const _needsMount = new Set();
  function isPathRootRefusal(msg) { return /no_permission|invalid_root|path_root/i.test(String(msg || '')); }
  async function pendingMounts(force) {
    if (!canShare1to1()) return [];
    if (force || !_incomingCache) await catalog();   // catalog() is what discovers refusals
    return (await incomingShares()).filter(s => _needsMount.has(s.id));
  }

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

    // destinations: team → one team hub; 1:1 → one outbox per recipient email,
    // each set up (created + shared + invited) on demand.
    const dests = [];
    if (audience.org || (audience.teams && audience.teams.length)) dests.push(teamHub());
    for (const u of (audience.users || [])) {
      try { dests.push(await recipientHub(u)); }
      catch (e) { throw new Error('Could not set up delivery to ' + u + ': ' + ((e && e.message) || e)); }
    }
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
  // Merge every mounted 1:1 outbox (one per sender) + the team hub (polled). Team
  // manifests are ACL-filtered; 1:1 manifests are addressed to me by construction —
  // Dropbox itself enforced that when the sender invited my email.
  async function catalog() {
    const who = me(), byId = {};
    for (const store of await incomingStores()) {
      let ms = [];
      try { ms = await listManifests(store); }
      catch (e) {
        const msg = (e && e.message) || String(e);
        // A refused namespace read is the one case that still needs a real mount.
        if (isPathRootRefusal(msg)) { _needsMount.add(store.shareId); console.info('[sharing] namespace read refused for', store.from, '— will offer a mount'); }
        else console.warn('[sharing] unreadable share from', store.from, msg);
      }
      for (const m of ms) { m._from = 'incoming'; m._sender = store.from || m.publisher; byId[m.id] = m; }
    }
    for (const m of await listManifests(teamHub())) if (!byId[m.id] && entitled(m, who)) { m._from = 'team'; byId[m.id] = m; }
    return byId;
  }
  // A 1:1 delivery is consumed by RECORDING it, not by deleting it: the recipient
  // is a viewer on the sender's folder and has no write access there. Keyed by
  // id@rev so a re-share (rev+1) produces a fresh key and notifies again.
  const consumeKey = (m) => m.id + '@' + (m.rev == null ? '?' : m.rev);
  async function isConsumed(m) {
    const s = await subs(), k = consumeKey(m);
    return !!s.accepted[k] || (s.dismissed || []).includes(k);
  }
  async function markConsumed(m, how) {
    const s = await subs(), k = consumeKey(m);
    if (how === 'accept') s.accepted[k] = { id: m.id, rev: m.rev, from: m._sender || m.publisher || '' };
    else { s.dismissed = s.dismissed || []; if (!s.dismissed.includes(k)) s.dismissed.push(k); }
    await saveSubs(s);
  }

  // Pending invites (the notification list). 1:1 only — team artifacts are NOT
  // invited; they auto-install and always list under "Team artifacts" (see
  // autoSync). A 1:1 package is pending until accept/dismiss records it at its
  // current rev; a re-share bumps rev and it becomes pending again.
  async function pendingInvites() {
    const who = me(), cat = await catalog(), s = await subs(), out = [];
    for (const id in cat) {
      const m = cat[id];
      if (m._from !== 'incoming') continue;
      if (m.publisher === who.user) continue;              // my own delivery bouncing back
      const k = consumeKey(m);
      if (s.accepted[k] || (s.dismissed || []).includes(k)) continue;
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
    await O().write(mp, new Blob([JSON.stringify({ id: m.id, title: m.title, kind: m.kind, publisher: m.publisher, pin: m.pin || null, rev: m.rev, from: m._from || 'incoming' })], { type: 'application/json' }));
    markDirty(mp);
    // apply directives
    if (m.pin && window.SandpiePins) { try { SandpiePins.add(dst + '/' + m.pin); } catch (_) {} }
    // skill:true → nothing to move; context.js discovers sandpie/shared-installed/<id>/SKILL.md and load_skill resolves it
    try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id: m.id, rev: m.rev } })); } catch (_) {}
  }
  // Delete a 1:1 package from shared-incoming (local + Dropbox) — used by accept (move)
  // and dismiss. file:deleted propagates the removal to the recipient's Dropbox folder.
  // Consume a 1:1 delivery. The package itself stays in the SENDER's Dropbox (we're
  // a viewer there and must not — cannot — delete it); what clears the notification
  // is the id@rev record. Also sweeps away local leftovers from the two older 1:1
  // designs, which did deliver into folders we own.
  async function consumeIncoming(m, how) {
    await markConsumed(m, how || 'accept');
    const store = m._store;
    const bases = new Set([LOCAL_HUB + '/packages/' + m.id]);   // legacy: workspace-synced delivery
    if (store && store.kind === 'local') bases.add(store.root + '/packages/' + m.id);   // offline sim
    for (const base of bases) {
      for (const rel of await listOpfs(base, '', [])) {
        const p = base + '/' + rel;
        try { await O().remove(p); } catch (_) {}
        try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', p); } catch (_) {}
      }
      try { await O().remove(base); } catch (_) {}   // drop the now-empty package dir (local)
    }
  }
  /* ── mounting: the FALLBACK path ────────────────────────────────────────── */
  // Shares are normally read in place by namespace and never mounted, so nothing
  // lands in the recipient's Dropbox. This runs only when that read is refused.
  // Even then it stays an explicit user action — it adds a folder to their Dropbox.
  // declineMount() is also the "stop receiving from this person" action: it
  // relinquishes membership, which is the ONLY way to sever the channel (a
  // sender's outbox is reused for every later delivery).
  // MountFolderError cases that are NOT failures:
  //   already_mounted — someone/something mounted it between our list and our click.
  //   must_automount  — a team space handles mounting itself; Dropbox's automounter
  //                     will add it shortly. Common on team accounts, where shares
  //                     often arrive already mounted and never show a pending row
  //                     at all. Either way the right move is to refresh, not error.
  const MOUNT_OK_ANYWAY = /already_mounted|must_automount/i;
  function mountErrorText(msg) {
    const m = String(msg || '');
    if (/insufficient_quota/i.test(m))    return 'Not enough space in your Dropbox to add this shared folder.';
    if (/not_mountable/i.test(m))         return 'Dropbox will not let this folder be added directly — it sits inside a team folder.';
    if (/inside_shared_folder/i.test(m))  return 'Cannot add this: it would put a shared folder inside another shared folder.';
    if (/no_permission/i.test(m))         return 'You do not have permission to add this shared folder.';
    return 'Could not accept that share: ' + m;
  }
  async function acceptMount(shareId) {
    const p = prov();
    if (!(p && p.shareMount)) return;
    try { await p.shareMount(shareId); }
    catch (e) {
      const msg = (e && e.message) || String(e);
      if (!MOUNT_OK_ANYWAY.test(msg)) { console.warn('[sharing] mount failed:', msg); alert(mountErrorText(msg)); return; }
      console.info('[sharing] mount handled by Dropbox itself:', msg);
    }
    invalidateIncoming();
    await autoSync();
    fire();
  }
  async function declineMount(shareId) {
    const p = prov();
    if (!(p && p.shareDecline)) return;
    try { await p.shareDecline(shareId); }
    catch (e) { console.warn('[sharing] decline failed:', (e && e.message) || e); }
    invalidateIncoming();
    fire();
  }
  // Delete a locally-installed package: sandpie/shared-installed/<id>/ (local + the
  // user's own Dropbox copy), and unpin anything under it. Used by both the
  // "Shared with me" ✕ (uninstall) and the team ✕ (unshare, after hub delete).
  async function removeInstalledLocal(id) {
    const dst = INSTALL_ROOT + '/' + id;
    if (window.SandpiePins) { for (const p of SandpiePins.list()) if (p === dst || p.startsWith(dst + '/')) SandpiePins.remove(p); }
    try {
      const p = prov();
      // The installed copy lives in MY workspace (home namespace), not the team
      // space — so this delete must NOT carry the team path-root.
      if (cloudOn() && p && p.workingRoot) {
        const abs = String(p.workingRoot() || '').replace(/\/+$/, '') + '/' + dst;
        if (p.workspaceDelete) await p.workspaceDelete(abs);
        else if (p.cloudDelete) await p.cloudDelete(abs, { team: false });
      }
    } catch (e) { console.warn('[sharing] cloud delete of installed failed:', e); }
    for (const rel of await listOpfs(dst, '', [])) {
      const p = dst + '/' + rel;
      try { await O().remove(p); } catch (_) {}
      try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', p); } catch (_) {}
    }
    try { await O().remove(dst); } catch (_) {}
  }
  // "Shared with me" ✕ — remove my accepted 1:1 copy (a re-share re-delivers, so nothing to suppress).
  async function uninstall(id) { await removeInstalledLocal(id); fire(); }
  // Team ✕ (publisher-gated in the UI) — UNSHARE: delete the package from the team hub
  // (gone for everyone), then drop the local auto-installed copy.
  async function unshareTeam(id) {
    try {
      const p = prov();
      if (cloudOn() && p && p.cloudDelete && p.cloudParent && p.cloudParent()) {
        const abs = String(p.cloudParent() || '').replace(/\/+$/, '') + '/shared-hub/packages/' + id;
        await p.cloudDelete(abs);
        console.log('[sharing] unshared team artifact from hub:', abs);
      }
    } catch (e) { console.warn('[sharing] unshare (hub delete) failed:', e); }
    await removeInstalledLocal(id);
    fire();
  }
  async function accept(id) {   // 1:1 only (team never produces invites)
    const cat = await catalog(); const m = cat[id]; if (!m) return;
    await install(m);
    if (m._from === 'incoming') await consumeIncoming(m, 'accept');   // copies into shared-installed; clears the notification
    fire();
  }
  async function dismiss(id) {  // 1:1 only — record the refusal without installing
    const cat = await catalog(); const m = cat[id];
    if (m && m._from === 'incoming') await consumeIncoming(m, 'dismiss');
    fire();
  }

  /* ── team artifacts: auto-install / auto-update / prune (no accept) ─────── */
  // Every entitled team-hub package is silently installed and kept at latest rev, and
  // ones removed from the hub (unshared) are dropped locally. 1:1 installs (from !=
  // 'team') are never touched here.
  let syncing = false;
  async function autoSync() {
    if (syncing || !O()) return; syncing = true;
    try {
      const cat = await catalog(); const teamIds = new Set(); let changed = false;
      for (const id in cat) {
        const m = cat[id]; if (m._from !== 'team') continue; teamIds.add(id);
        let mk = null; try { mk = JSON.parse(await O().read(INSTALL_ROOT + '/' + id + '/' + PKG_MARKER)); } catch (_) {}
        if (!mk || String(mk.rev) !== String(m.rev)) { await install(m); changed = true; }   // install() marks from='team'
      }
      let dirs = []; try { dirs = (await O().listDir(INSTALL_ROOT)).filter(e => e.kind === 'directory').map(e => e.name); } catch (_) {}
      for (const id of dirs) {
        if (teamIds.has(id)) continue;
        let mk = null; try { mk = JSON.parse(await O().read(INSTALL_ROOT + '/' + id + '/' + PKG_MARKER)); } catch (_) {}
        if (mk && mk.from === 'team') { await removeInstalledLocal(id); changed = true; }   // unshared from the hub → drop local
      }
      if (changed) fire();
    } catch (e) { console.warn('[sharing] team autoSync failed:', e); } finally { syncing = false; }
  }

  /* ── events ───────────────────────────────────────────────────────────── */
  function fire() { try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {} renderHome(); }
  function subscribe(cb) { const h = () => cb(); window.addEventListener('sandpie-shares-changed', h); return () => window.removeEventListener('sandpie-shares-changed', h); }

  const Sharing = { me, setIdentity, catalog, subs, entitled, publish, pendingInvites, pendingMounts, acceptedList, accept, dismiss, acceptMount, declineMount, uninstall, unshareTeam, autoSync, subscribe, shareDialog, teamHub, recipientHub, incomingShares, incomingStores, invalidateIncoming, INSTALL_ROOT, LOCAL_HUB };
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
        // "Share with team" needs the team hub; without a team space it would
        // silently fall through to the local simulation, so default to 1:1 instead.
        '<label class="share-opt"' + (hubRoot() ? '' : ' style="opacity:.45"') + '><input type="radio" name="aud" value="org"' + (hubRoot() ? ' checked' : ' disabled') + '> Share with team' + (hubRoot() ? '' : ' <span style="font-size:.75em">(no team folder configured)</span>') + '</label>' +
        '<label class="share-opt"><input type="radio" name="aud" value="users"' + (hubRoot() ? '' : ' checked') + '> Specific people: <input class="share-in" data-k="users" placeholder="email, email…"></label>' +
        '<label class="share-opt share-pin"><input type="checkbox" data-k="pin" checked> Pin to their home screen</label>' +
        (folder ? '<div class="share-pin-file"><label class="share-opt">Pin which file: <select class="share-in" data-k="pinfile">' +
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
      else audience.users = splitList(back.querySelector('.share-in[data-k="users"]').value);
      const msg = back.querySelector('.share-modal-msg');
      if (sel === 'users') {
        // The email IS the address now — a typo means the delivery silently goes
        // to a folder nobody will ever mount, so reject anything unaddressable.
        if (!(audience.users || []).length) { msg.textContent = 'Enter at least one email.'; return; }
        const bad = audience.users.filter(u => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(u));
        if (bad.length) { msg.textContent = 'Not a valid email: ' + bad.join(', '); return; }
      }
      const pin = !!pinBox.checked;
      const pinSel = back.querySelector('.share-in[data-k="pinfile"]');
      const pinFile = pin && folder && pinSel ? pinSel.value : undefined;
      // First delivery to a new person sets up a Dropbox share (a few API calls).
      msg.textContent = sel === 'users' ? 'Setting up delivery…' : 'Sharing…';
      try {
        const r = await publish(srcPath, audience, { kind: presetKind, pin, pinFile });
        msg.textContent = 'Shared (v' + r.rev + ') → ' + (sel === 'org' ? 'the team' : audience.users.join(', '))
          + (pin ? ', pinned ' + (pinFile || 'file') : '')
          + (cloudOn() ? (sel === 'users' ? '. They see it next time Sandpie is open.' : '') : ' [local test — Dropbox not connected]');
        setTimeout(close, sel === 'users' ? 2600 : 1400);
      }
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
      if (!box) { box = document.createElement('div'); box.id = 'sharedHome'; box.className = 'shared-home'; welcome.appendChild(box); observeInbox(); }
      let invites = [], installed = [], mounts = [];
      // invites first: pendingInvites() runs catalog(), which is what discovers any
      // namespace-read refusal, so pendingMounts() is then a cache hit.
      try { invites = await pendingInvites(); mounts = await pendingMounts(); installed = await acceptedList(); } catch (_) {}
      _pendingCount = invites.length + mounts.length;   // banner is updated in finally, once the box is populated/sized
      box.textContent = '';
      const shared = installed.filter(m => m.from !== 'team');   // accepted 1:1
      const team = installed.filter(m => m.from === 'team');     // auto, always shown
      if (!invites.length && !mounts.length && !shared.length && !team.length) { box.style.display = 'none'; return; }
      box.style.display = '';
      if (invites.length || mounts.length) {
        const card = document.createElement('div'); card.className = 'share-invites';
        const h = document.createElement('div'); h.className = 'shared-home-title'; h.textContent = '📥 Shared with you'; card.appendChild(h);
        for (const s of mounts) card.appendChild(mountRow(s));   // first contact from a sender
        for (const m of invites) card.appendChild(inviteRow(m));
        box.appendChild(card);
      }
      if (shared.length) box.appendChild(group('🔗 Shared with me', COLLAPSE_KEY, shared, m => itemRow(m, () => uninstall(m.id))));
      // Team artifacts: ✕ (unshare) only on ones I published; everyone else gets pin only.
      if (team.length) box.appendChild(group('👥 Team artifacts', TEAM_COLLAPSE_KEY, team, m => itemRow(m, m.publisher === me().user ? () => unshareTeam(m.id) : null)));
    } finally { homeBusy = false; updateBanner(); if (homePending) { homePending = false; renderHome(); } }
  }
  const kindIcon = (k) => k === 'skill' ? '🧩' : k === 'folder' ? '📁' : '📄';
  const entryOf = (m) => m.pin || (m.kind === 'artifact' ? m.title : (m.kind === 'skill' ? 'SKILL.md' : ''));   // the file to open/pin
  function inviteRow(m) {
    const row = document.createElement('div'); row.className = 'shared-file invite';
    row.innerHTML = '<span class="shared-file-name">' + kindIcon(m.kind) + ' ' + esc(m.title) + '</span><span class="shared-by">from ' + esc(m._sender || m.publisher) + '</span>';
    const acc = document.createElement('button'); acc.className = 'ghost shared-accept'; acc.textContent = 'Accept'; acc.onclick = () => accept(m.id);
    const dis = document.createElement('button'); dis.className = 'shared-dismiss'; dis.title = 'Dismiss'; dis.textContent = '✕'; dis.onclick = () => dismiss(m.id);
    row.append(acc, dis); return row;
  }
  // FALLBACK row, normally never shown: this account wouldn't let us read the
  // sender's shared folder by namespace, so the only way in is to actually add it
  // to the user's Dropbox. Everyone else's shares are read in place and go straight
  // to the invite rows above.
  function mountRow(s) {
    const row = document.createElement('div'); row.className = 'shared-file invite';
    row.innerHTML = '<span class="shared-file-name">🤝 ' + esc(s.from || s.name) + ' shared files with you</span><span class="shared-by">' + esc(s.owner || '') + ' · needs adding to your Dropbox</span>';
    const acc = document.createElement('button'); acc.className = 'ghost shared-accept'; acc.textContent = 'Add'; acc.onclick = () => acceptMount(s.id);
    const dis = document.createElement('button'); dis.className = 'shared-dismiss'; dis.title = 'Decline and stop receiving from this person'; dis.textContent = '✕'; dis.onclick = () => declineMount(s.id);
    row.append(acc, dis); return row;
  }
  // A collapsible titled group (count in the title), collapsed by default; '0' = user expanded.
  function group(title, key, items, rowFn) {
    const frag = document.createDocumentFragment();
    let collapsed = true; try { if (localStorage.getItem(key) === '0') collapsed = false; } catch (_) {}
    const h = document.createElement('button'); h.className = 'shared-home-title shared-toggle';
    const caret = document.createElement('span'); caret.className = 'shared-caret'; caret.textContent = collapsed ? '▸' : '▾';
    const lbl = document.createElement('span'); lbl.className = 'shared-group-name'; lbl.textContent = title;
    const cnt = document.createElement('span'); cnt.className = 'shared-count'; cnt.textContent = items.length;
    h.append(caret, lbl, cnt);
    const list = document.createElement('div'); list.className = 'shared-list'; list.style.display = collapsed ? 'none' : '';
    for (const m of items) list.appendChild(rowFn(m));
    h.onclick = () => { const open = list.style.display === 'none'; list.style.display = open ? '' : 'none'; caret.textContent = open ? '▾' : '▸'; try { localStorage.setItem(key, open ? '0' : '1'); } catch (_) {} };
    frag.append(h, list); return frag;
  }
  // A row for an installed item: open · pin toggle · (optional ✕). onDelete=null → no ✕.
  function itemRow(m, onDelete) {
    const row = document.createElement('div'); row.className = 'shared-file';
    const entry = entryOf(m), full = entry ? INSTALL_ROOT + '/' + m.id + '/' + entry : null;
    const open = document.createElement('button'); open.className = 'shared-file-open'; open.innerHTML = kindIcon(m.kind) + ' ' + esc(m.title);
    open.title = m.kind === 'skill' ? 'Shared skill — the model can load it by name' : INSTALL_ROOT + '/' + m.id;
    open.onclick = () => { if (entry) { try { opfs.openFile(full, entry.split('/').pop()); } catch (_) {} } };
    row.append(open);
    if (full && window.SandpiePins) { const pin = document.createElement('button'); pin.className = 'shared-pin'; SandpiePins.bindButton(pin, full); row.append(pin); }
    if (onDelete) { const del = document.createElement('button'); del.className = 'shared-dismiss'; del.title = 'Remove'; del.textContent = '✕'; del.onclick = (e) => { e.stopPropagation(); onDelete(); }; row.append(del); }
    return row;
  }

  /* ── off-home banner ──────────────────────────────────────────────────── */
  // A slim top banner shown when there are pending invites AND the home inbox is
  // NOT on screen (i.e. the user is in a conversation, not looking at the invites).
  // Tapping it lands on the home screen. Visibility of the inbox is tracked with an
  // IntersectionObserver (robust to scroll; no rect polling), count comes from renderHome.
  let _pendingCount = 0, _banner = null, _inboxVisible = true, _io = null;
  function observeInbox() {
    const box = document.getElementById('sharedHome');
    if (!box || !window.IntersectionObserver) return;
    if (_io) _io.disconnect();
    _io = new IntersectionObserver((entries) => { _inboxVisible = entries.some(e => e.isIntersecting); updateBanner(); }, { threshold: 0.01 });
    _io.observe(box);
  }
  function updateBanner() {
    const show = _pendingCount > 0 && !_inboxVisible;
    if (!show) { if (_banner) _banner.style.display = 'none'; return; }
    if (!_banner) {
      _banner = document.createElement('div');
      _banner.className = 'share-banner';
      _banner.setAttribute('data-chrome', '');
      _banner.onclick = () => { try { if (window.newConversation) newConversation(); } catch (_) {} };
      (document.querySelector('main') || document.body).appendChild(_banner);   // scoped to the main pane
    }
    _banner.textContent = '📥 ' + _pendingCount + ' item' + (_pendingCount === 1 ? '' : 's') + ' shared with you — tap to view';
    _banner.style.display = '';
  }

  /* ── boot ─────────────────────────────────────────────────────────────── */
  function boot() { renderHome(); autoSync(); observeInbox(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  // Neither 1:1 nor team deliveries sync into the workspace any more — both are
  // polled. These two are the poll ticks: refocusing the tab, and the end of each
  // sync cycle (~60s). invalidateIncoming() forces a fresh list_folders so a share
  // invited while the tab was open still shows up.
  window.addEventListener('focus', () => { invalidateIncoming(); autoSync(); renderHome(); });
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('sync:done', () => { invalidateIncoming(); autoSync(); renderHome(); }); } catch (_) {}
})();
