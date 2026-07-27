// sharing.js — share skills / artifacts / folders across the org, scoped, with
// silent auto-update. Browser-only; rides the existing Dropbox team folder.
//
// PATHS (named for clarity):
//   • TEAM hub (shared by all)    <teamParent>/shared-hub/              (Dropbox API;
//     outside every workspace, so recipients POLL it). <teamParent> =
//     provider.cloudParent(), default /R+D+I/sandpie; '' on a non-team account.
//   • 1:1 delivery                 addressed by EMAIL, no shared folder required.
//     ONE Dropbox shared folder per package, every recipient added as a member.
//     A FOLDER is shared LIVE where it sits (sandpie/skills/thing) — the sender's
//     later edits reach recipients through Dropbox with no re-publish, and
//     autoSync() re-installs them silently. A SINGLE FILE cannot be shared by
//     Dropbox (SharePathError.is_file), so it is wrapped in /Sandpie Outbox/<id>/
//     as a copy and is NOT live.
//     Recipients read the folder by namespace and never mount it, so nothing
//     appears in their Dropbox. See dropbox.js "Dropbox sharing API".
//   • per-user INSTALLED          sandpie/shared-installed/  (in the recipient's own
//     workspace; read-only accepted packages, the worker's guard keys on this prefix)
//
// Because the shared folder is the sender's own workspace folder, its NAME carries
// no signal — a recipient identifies Sandpie packages by probing each shared folder
// for the .sandpie-share.json marker at its root (verdict cached per folder id).
//
// 1:1 recipients are VIEWERS, so they cannot delete a package they've consumed.
// Accept/dismiss is recorded in the recipient's own shares.json, keyed "<id>@<rev>".
// An explicit re-share bumps rev and re-notifies; plain content edits do not bump
// rev and instead flow through as a silent auto-update. (Team packages are
// unchanged: auto-install, tracked by the installed marker's rev.)
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
  const SUBS_PATH = 'sandpie/config/shares.json';   // accept/dismiss state (1:1) + team subscriptions
  const PKG_MARKER = '.sandpie-pkg.json';           // per-installed-package marker: {id,title,kind,publisher,pin,rev,revs}
  const SHARE_MARKER = '.sandpie-share.json';       // manifest at the root of a 1:1 shared folder
  const LEGACY_PROBE_KEY = 'sandpie-share-probe';   // removed: a persisted "is this ours" index that went stale and hid deliveries
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
      async listEntries(sub) { return (await listOpfs(root + (sub ? '/' + sub : ''), '', [])).map(rel => ({ rel, rev: '', size: 0 })); },
      async probeText(rel) { try { const t = await O().read(root + '/' + rel); return t == null ? { missing: true } : { text: t }; } catch (_) { return { missing: true }; } },
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
      // Paths RELATIVE TO `base` (the sub dir), like localStore — install() does
      // readBytes(sub + '/' + rel), so rel must NOT re-include that prefix. When
      // absRoot is '' the store is namespace-rooted and Dropbox already returns
      // namespace-relative paths, so there is nothing to strip but the slash.
      _rel(path, base) {
        const s = String(path);
        if (!base) return s.replace(/^\/+/, '');
        const i = s.toLowerCase().indexOf(base.toLowerCase() + '/');
        return i >= 0 ? s.slice(i + base.length + 1) : s.split('/').pop();
      },
      async listFiles(sub) {
        const base = absRoot + (sub ? '/' + sub : '');
        return (await P().cloudList(base, true, opt)).filter(e => e.kind === 'file').map(e => this._rel(e.path, base));
      },
      async listDirs(sub) { const base = absRoot + (sub ? '/' + sub : ''); return (await P().cloudList(base, false, opt)).filter(e => e.kind === 'folder' || e.kind === 'directory').map(e => e.path.split('/').pop()); },   // Dropbox tags folders 'folder', not 'directory'
      // Same as listFiles but keeps each file's Dropbox rev. That rev is what tells
      // a recipient a LIVE shared folder changed under them — the manifest rev only
      // moves on an explicit re-share.
      async listEntries(sub) {
        const base = absRoot + (sub ? '/' + sub : '');
        return (await P().cloudList(base, true, opt)).filter(e => e.kind === 'file')
          .map(e => ({ rel: this._rel(e.path, base), rev: e.rev || '', size: e.size || 0 }));
      },
      async readText(rel) { try { return new TextDecoder().decode(await P().cloudDownload(absRoot + '/' + rel, opt)); } catch (_) { return null; } },
      async readBytes(rel) { try { return await P().cloudDownload(absRoot + '/' + rel, opt); } catch (_) { return null; } },
      // readText() cannot tell "the file isn't there" from "I wasn't allowed to
      // look", and treating those the same is what made unreadable shares get
      // cached as "not a Sandpie package". This keeps them apart.
      //   {missing:true}          → definitively absent; safe to remember
      //   {error:'...'}           → could not tell; must NOT be remembered
      async probeText(rel) {
        try { return { text: new TextDecoder().decode(await P().cloudDownload(absRoot + '/' + rel, opt)) }; }
        catch (e) {
          const msg = (e && e.message) || String(e);
          if (/not_found|path\/not_found/i.test(msg)) return { missing: true };
          return { error: msg };
        }
      },
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
  const canShare1to1 = () => { const p = prov(); return !!(cloudOn() && p && p.shareFolderWith); };
  // SENDER side. A folder is shared LIVE where it already sits; a single file has
  // to be wrapped, because Dropbox will not share a file. Returns the store to
  // write the manifest (and, for a file, the copy) into.
  // Shares the folder but does NOT invite anyone yet — publish() writes the marker
  // first and calls store.invite() afterwards. Inviting first opens a window where
  // the recipient sees a markerless share and concludes it isn't a package.
  async function outboundStore(srcRel, isFolder, pkgId, level) {
    const p = prov();
    if (!canShare1to1()) { const st = localStore(LOCAL_HUB + '/_outbox/' + pkgId); st.invite = async () => {}; return st; }
    const abs = isFolder ? p.shareWorkspacePath(srcRel) : await p.shareOutboxFolder(pkgId);
    let id;
    try { id = await p.shareEnsureFolder(abs); }
    catch (e) {
      // A folder created moments ago may not have reached Dropbox yet — the sync
      // cycle is up to a minute. share_folder then fails with a bare not_found,
      // which reads as a bug rather than "wait a moment".
      if (isFolder && /not_found/i.test(String((e && e.message) || e))) {
        throw new Error('"' + srcRel.split('/').pop() + '" has not finished syncing to Dropbox yet — wait for the sync to settle and share again.');
      }
      throw e;
    }
    const st = cloudStore(abs, { team: false });   // the sender's own Dropbox = home namespace
    st.shareId = id; st.live = isFolder; st.level = level;
    st.invite = async (emails) => {
      // ORDER MATTERS. Share the marker FILE first, then the folder.
      // add_file_member on a file the recipient can already reach through the
      // parent folder may be treated as a no-op — no explicit file membership, so
      // nothing for list_received_files to return, so the delivery is invisible.
      // Granting file access while they are still a stranger to the folder avoids
      // depending on that behaviour.
      // Not swallowed: without the notification the package is undiscoverable, so
      // a failure here has to reach the sender rather than look like a success.
      if (p.shareNotify) await p.shareNotify(abs + '/' + SHARE_MARKER, emails, level);
      const r = await p.shareInvite(id, emails, level);          // folder membership → they can READ the package
      st.level = r.level;
      return r;
    };
    return st;
  }

  // RECIPIENT side. list_folders returns EVERY shared folder the user is in, not
  // just ours, and the folder name is the sender's own so it proves nothing. Probe
  // each one for the marker and remember the verdict per folder id — otherwise a
  // user in twenty corporate shared folders pays twenty downloads every poll.
  // Discovery is ONE request. The sender shares the marker file itself with each
  // recipient (add_file_member) on top of the folder share, so the recipient can
  // ask Dropbox directly for the deliveries addressed to them —
  // list_received_files — and every result carries parent_shared_folder_id, which
  // is the namespace the package lives in. Nothing is scanned and nothing is
  // written down, so the cost does not grow with how many shared folders the
  // account belongs to. (It used to: opening all 88 of them looking for a marker,
  // three times per tick, was ~264 requests.)
  //
  // _incomingCache / _catalogCache are per-pass request coalescing, NOT an index:
  // in memory only, never persisted, and dropped by invalidateIncoming() on every
  // poll tick.
  let _incomingCache = null, _lastProbe = [], _catalogCache = null, _lastShareId = '';
  // SELF-TEST MODE. Dropbox will not list a file to that file's owner, so a package
  // shared with your own address can never come back through list_received_files.
  // This pretends ONE specific folder — the one selfTest() just published — is an
  // incoming delivery, which is enough to walk invite → accept → live-update on a
  // single account. It does NOT exercise real cross-account discovery.
  //
  // Deliberately scoped to a single {pkg, folder} rather than "every folder I own":
  // a global switch turned every package the user had ever shared into an invite
  // from themselves, and probed every markerless owned folder on each tick.
  const SELF_KEY = 'sandpie-share-allow-self';
  function allowSelf() {
    try {
      const raw = localStorage.getItem(SELF_KEY);
      if (!raw) return null;
      const v = JSON.parse(raw);
      return (v && v.folderId) ? v : null;
    } catch (_) { return null; }
  }
  function setAllowSelf(v) {
    try { if (v && v.folderId) localStorage.setItem(SELF_KEY, JSON.stringify(v)); else localStorage.removeItem(SELF_KEY); } catch (_) {}
    invalidateIncoming(); fire();
    return allowSelf();
  }
  async function incomingShares(force) {
    if (!canShare1to1()) return [];
    if (_incomingCache && !force) return _incomingCache;
    try {
      const self = allowSelf();
      // Own shares are not deliveries to me — except the one self-test folder.
      const list = (await prov().shareListDeliveries(SHARE_MARKER)).filter(s => !s.isOwner || (self && s.id === self.folderId));
      if (self && !list.some(s => s.id === self.folderId)) {
        list.push({ id: self.folderId, name: self.pkgId || 'self test', owner: 'you', from: 'you (self test)', isOwner: true, invitedAt: 0, path: '', self: true });
      }
      _incomingCache = list;
    }
    catch (e) { console.warn('[sharing] could not list deliveries:', (e && e.message) || e); _incomingCache = _incomingCache || []; }
    return _incomingCache;
  }
  function invalidateIncoming() { _incomingCache = null; _catalogCache = null; _needsMount.clear(); }
  // One store per delivery, read BY NAMESPACE — nothing is mounted, so nothing
  // appears in the recipient's Dropbox. Paths are relative to the shared folder
  // itself, hence root ''. Every entry here is already known to be a package
  // (Dropbox told us), so there is nothing to probe or classify.
  async function incomingStores(force) {
    if (!canShare1to1()) return [localStore(LOCAL_HUB + '/_inbox/' + localPart(me().user))];
    return (await incomingShares(force)).filter(s => !_needsMount.has(s.id)).map(s => {
      const st = cloudStore('', { ns: s.id });
      st.from = s.from; st.shareId = s.id; st.shareName = s.name; st.invitedAt = s.invitedAt || 0;
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
    await catalog(force);   // catalog() is what discovers refusals; memoised, so this is free after the first call
    return (await incomingShares()).filter(s => _needsMount.has(s.id));
  }
  // Back-compat shim: recipientHub(email) used to be the outbound store.
  async function recipientHub(email) { return localStore(LOCAL_HUB + '/_inbox/' + localPart(email)); }

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
  // TEAM hub layout: packages/<id>/manifest.json + files (many packages per store).
  async function readManifest(store, id) { const t = await store.readText('packages/' + id + '/manifest.json'); if (!t) return null; try { return JSON.parse(t); } catch (_) { return null; } }
  async function listManifests(store) {
    const ids = await store.listDirs('packages'); const out = [];
    for (const id of ids) { const m = await readManifest(store, id); if (m) out.push({ ...m, _store: store }); }
    return out;
  }
  // 1:1 layout: the shared folder IS the package — marker at its root, files
  // alongside. Returns {manifest} | {missing:true} | {error}. The caller MUST only
  // remember a verdict for the first two: an `error` means we could not tell, and
  // recording that as "not a package" is what hides a real delivery.
  async function readShareManifest(store) {
    const r = await store.probeText(SHARE_MARKER);
    if (r.error) return { error: r.error };
    if (r.missing || !r.text) return { missing: true };
    try { const m = JSON.parse(r.text); return (m && m.id) ? { manifest: m } : { missing: true }; }
    catch (_) { return { missing: true }; }   // present but unparseable → not one of ours
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

    const acl = { org: !!audience.org, users: (audience.users || []).map(String), teams: (audience.teams || []).map(String) };
    // pin target: explicit opts.pinFile (a rel path within the folder) wins; else the
    // artifact itself, else the folder's first file as a fallback.
    const pinFile = opts.pin ? (opts.pinFile && files.includes(opts.pinFile) ? opts.pinFile : (kind === 'artifact' ? base : (files[0] || ''))) : null;
    // 'viewer' (default) or 'editor'. Recorded in the manifest so the recipient can
    // tell whether they are looking at something they may write back to.
    const level = opts.access === 'editor' ? 'editor' : 'viewer';
    const mk = (rev) => ({ id, kind, title: opts.title || base, publisher: me().user, rev, acl, pin: pinFile, skill: kind === 'skill', access: level, ts: 0 });
    const dests = [], users = (audience.users || []).map(String);
    let rev = 1;

    // ── TEAM: copy into the hub under packages/<id>/ (unchanged) ──
    if (audience.org || (audience.teams && audience.teams.length)) {
      const store = teamHub();
      const prev = await readManifest(store, id);
      rev = (prev ? parseInt(prev.rev, 10) || 0 : 0) + 1;
      for (const rel of files) { const bytes = await readSrc(rel); if (bytes) await store.writeBytes('packages/' + id + '/' + rel, bytes); }
      await store.writeText('packages/' + id + '/manifest.json', JSON.stringify(mk(rev), null, 2));
      dests.push(store.kind + ':' + store.root);
    }

    // ── 1:1: ONE shared folder, every recipient added as a member ──
    // A folder is shared LIVE in place, so there is nothing to copy — the sender's
    // later edits are the update. A single file is copied into an outbox wrapper
    // because Dropbox refuses to share a file.
    if (users.length) {
      let store;
      try { store = await outboundStore(src, dir, id, level); }
      catch (e) { throw new Error('Could not set up delivery to ' + users.join(', ') + ': ' + ((e && e.message) || e)); }
      const prev = (await readShareManifest(store)).manifest;
      rev = (prev ? parseInt(prev.rev, 10) || 0 : 0) + 1;
      if (!dir) { const bytes = await readSrc(base); if (bytes) await store.writeBytes(base, bytes); }
      // Marker BEFORE members: the first thing a recipient does with a new share is
      // look for it, and a miss is remembered.
      await store.writeText(SHARE_MARKER, JSON.stringify(mk(rev), null, 2));
      try { await store.invite(users); }
      catch (e) { throw new Error('Could not invite ' + users.join(', ') + ': ' + ((e && e.message) || e)); }
      _lastShareId = store.shareId || '';   // selfTest needs it to point self-mode at this one folder
      dests.push((store.live ? 'live:' : 'copy:') + store.root);
    }

    if (!dests.length) throw new Error('publish: no audience');
    fire();
    return { id, rev, kind, live: dir && users.length > 0, access: level, shareId: _lastShareId, dests };
  }

  /* ── catalog (what's available TO ME) ─────────────────────────────────── */
  // Merge every mounted 1:1 outbox (one per sender) + the team hub (polled). Team
  // manifests are ACL-filtered; 1:1 manifests are addressed to me by construction —
  // Dropbox itself enforced that when the sender invited my email.
  // MEMOISED for the current poll pass. Every caller here (autoSync, pendingInvites,
  // pendingMounts, each renderHome) used to re-run it, and each run downloads
  // .sandpie-share.json once per shared folder — so a single tick fired several
  // probes per share, and fire()→renderHome() multiplied that again. The listing
  // and the probes are refreshed together by invalidateIncoming(), which the poll
  // ticks already call, so the cache never goes stale for longer than one tick.
  async function catalog(force) {
    if (_catalogCache && !force) return _catalogCache;
    const who = me(), byId = {};
    _lastProbe = [];
    for (const store of await incomingStores()) {
      const r = await readShareManifest(store);
      _lastProbe.push({ id: store.shareId, name: store.shareName, from: store.from, result: r.manifest ? 'package' : (r.missing ? 'not-a-package' : 'ERROR'), error: r.error || '' });
      if (r.error) {
        // Could not read it. A path-root refusal means the namespace read is not
        // allowed here and the folder has to be mounted the old way; anything else
        // is logged and retried next poll. Either way, DO NOT cache a verdict.
        if (isPathRootRefusal(r.error)) { _needsMount.add(store.shareId); console.info('[sharing] namespace read refused for', store.shareName, '— offering a mount instead'); }
        else console.warn('[sharing] could not read shared folder', store.shareName, '—', r.error);
        continue;
      }
      // Dropbox told us this folder holds a delivery, so a missing marker normally
      // means the sender withdrew it. Not worth a console line every poll tick.
      if (!r.manifest) { console.debug('[sharing] no', SHARE_MARKER, 'in', store.shareName); continue; }
      const m = r.manifest;
      m._from = 'incoming'; m._sender = m.publisher || store.from; m._store = store; m._shareId = store.shareId;
      byId[m.id] = m;
    }
    for (const m of await listManifests(teamHub())) if (!byId[m.id] && entitled(m, who)) { m._from = 'team'; byId[m.id] = m; }
    _catalogCache = byId;
    return byId;
  }
  // A 1:1 delivery is consumed by RECORDING it, not by deleting it: the recipient
  // is a viewer on the sender's folder and has no write access there. Keyed by
  // id@rev so a re-share (rev+1) produces a fresh key and notifies again.
  const consumeKey = (m) => m.id + '@' + (m.rev == null ? '?' : m.rev);
  // An earlier build keyed these by bare id (accepted[id] = rev). Honour those so a
  // package someone already accepted doesn't reappear as a fresh invite after the
  // key format changed. Read-only compatibility — nothing is rewritten.
  function consumed(s, m) {
    const k = consumeKey(m), d = s.dismissed || [];
    return !!s.accepted[k] || !!s.accepted[m.id] || d.includes(k) || d.includes(m.id);
  }
  async function isConsumed(m) { return consumed(await subs(), m); }
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
      const self = allowSelf();
      if (m.publisher === who.user && !(self && m.id === self.pkgId)) continue;   // my own delivery bouncing back
      if (consumed(s, m)) continue;
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
  // Where a package's files live within its store: team packages sit under
  // packages/<id>/ in the shared hub; a 1:1 shared folder IS the package, so its
  // files are at the root (minus the marker).
  const pkgSub = (m) => (m._from === 'team' ? 'packages/' + m.id : '');
  const isPkgMeta = (rel) => rel === 'manifest.json' || rel === SHARE_MARKER;
  async function install(m) {
    const store = m._store, dst = INSTALL_ROOT + '/' + m.id, sub = pkgSub(m);
    const entries = (await store.listEntries(sub)).filter(e => !isPkgMeta(e.rel));
    const revs = {};
    for (const e of entries) {
      const bytes = await store.readBytes(sub ? sub + '/' + e.rel : e.rel);
      if (!bytes) continue;
      const p = dst + '/' + e.rel;
      await O().write(p, new Blob([bytes]));
      revs[e.rel] = e.rev || '';
      markDirty(p);   // emit file:changed so Dropbox marks it dirty + uploads it — without this the
                      // reconciliation pass deletes it as a local-only orphan under the eager prefix
    }
    // Files the sender has since DELETED from a live shared folder must go too,
    // otherwise an update leaves orphans behind in the installed copy.
    const keep = new Set(Object.keys(revs));
    for (const rel of await listOpfs(dst, '', [])) {
      if (rel === PKG_MARKER || keep.has(rel)) continue;
      const p = dst + '/' + rel;
      try { await O().remove(p); } catch (_) {}
      try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', p); } catch (_) {}
    }
    // marker so "Shared with me" + rollback-free identification work without shares.json.
    // `revs` is the per-file Dropbox rev map — how autoSync notices that a LIVE
    // shared folder changed without the manifest rev moving.
    const mp = dst + '/' + PKG_MARKER;
    await O().write(mp, new Blob([JSON.stringify({ id: m.id, title: m.title, kind: m.kind, publisher: m.publisher, pin: m.pin || null, rev: m.rev, from: m._from || 'incoming', revs })], { type: 'application/json' }));
    markDirty(mp);
    // apply directives
    if (m.pin && window.SandpiePins) { try { SandpiePins.add(dst + '/' + m.pin); } catch (_) {} }
    // skill:true → nothing to move; context.js discovers sandpie/shared-installed/<id>/SKILL.md and load_skill resolves it
    try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id: m.id, rev: m.rev } })); } catch (_) {}
  }
  // Has a LIVE shared folder changed since we installed it? Compares the per-file
  // Dropbox revs, because the sender editing files in place never touches the
  // manifest rev. Cheap: one list_folder, no downloads.
  async function liveChanged(m, marker) {
    if (!m._store || m._store.kind !== 'cloud') return false;
    const was = (marker && marker.revs) || null;
    if (!was) return false;   // installed before rev tracking → leave it alone
    let entries; try { entries = (await m._store.listEntries(pkgSub(m))).filter(e => !isPkgMeta(e.rel)); } catch (_) { return false; }
    if (entries.length !== Object.keys(was).length) return true;
    return entries.some(e => was[e.rel] !== (e.rev || ''));
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
  // These THROW on real failure so the caller (busyClick) can restore the row and
  // show why, instead of an alert() that leaves the row looking like it worked.
  async function acceptMount(shareId) {
    const p = prov();
    if (!(p && p.shareMount)) return;
    try { await p.shareMount(shareId); }
    catch (e) {
      const msg = (e && e.message) || String(e);
      if (!MOUNT_OK_ANYWAY.test(msg)) throw new Error(mountErrorText(msg));
      console.info('[sharing] mount handled by Dropbox itself:', msg);
    }
    invalidateIncoming();
    await autoSync();
    fire();
  }
  async function declineMount(shareId) {
    const p = prov();
    if (!(p && p.shareDecline)) return;
    await p.shareDecline(shareId);
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

  /* ── auto-install / auto-update / prune ─────────────────────────────────── */
  // TEAM packages: every entitled hub package is silently installed and kept at the
  //   latest manifest rev; ones removed from the hub are dropped locally.
  // 1:1 packages: only ones the user has ALREADY accepted are refreshed — an
  //   un-accepted delivery stays an invite. A live shared folder changes without the
  //   manifest rev moving, so the trigger is the per-file rev map (liveChanged).
  //   This is what makes "I edit the folder, they get it" true end to end.
  // Checking a LIVE folder for changes costs one list_folder per accepted package.
  // That does not need to happen on every render — only on a slow tick — or a busy
  // home screen turns into a steady stream of Dropbox calls.
  let _liveCheckAt = 0;
  const LIVE_CHECK_EVERY = 120000;
  let syncing = false;
  async function autoSync() {
    if (syncing || !O()) return; syncing = true;
    const checkLive = (Date.now() - _liveCheckAt) > LIVE_CHECK_EVERY;
    if (checkLive) _liveCheckAt = Date.now();
    try {
      const cat = await catalog(); const teamIds = new Set(); let changed = false;
      const accepted = (await subs()).accepted || {};
      for (const id in cat) {
        const m = cat[id];
        let mk = null; try { mk = JSON.parse(await O().read(INSTALL_ROOT + '/' + id + '/' + PKG_MARKER)); } catch (_) {}
        if (m._from === 'team') {
          teamIds.add(id);
          if (!mk || String(mk.rev) !== String(m.rev)) { await install(m); changed = true; }   // install() marks from='team'
          continue;
        }
        // 1:1 — refresh only what's installed AND accepted at this rev.
        if (!mk || mk.from === 'team') continue;
        if (!accepted[consumeKey(m)] && !accepted[m.id]) continue;   // bare id = legacy accept key
        if (String(mk.rev) !== String(m.rev) || await liveChanged(m, mk)) {
          await install(m);
          console.info('[sharing] refreshed', id, 'from', m._sender);
          changed = true;
        }
      }
      let dirs = []; try { dirs = (await O().listDir(INSTALL_ROOT)).filter(e => e.kind === 'directory').map(e => e.name); } catch (_) {}
      for (const id of dirs) {
        if (teamIds.has(id)) continue;
        let mk = null; try { mk = JSON.parse(await O().read(INSTALL_ROOT + '/' + id + '/' + PKG_MARKER)); } catch (_) {}
        if (mk && mk.from === 'team') { await removeInstalledLocal(id); changed = true; }   // unshared from the hub → drop local
      }
      if (changed) fire();
    } catch (e) { console.warn('[sharing] autoSync failed:', e); } finally { syncing = false; }
  }

  /* ── diagnose ─────────────────────────────────────────────────────────── */
  // Run SandpieSharing.diagnose() in the console on the RECIPIENT's machine when a
  // delivery doesn't show up. It re-runs the real discovery call and reports what
  // each step returned — enough to separate a scope problem, a permission refusal,
  // a delivery that was never announced, and one already accepted.
  async function diagnose() {
    const p = prov();
    const out = { identity: me().user, cloudConnected: !!(p && p.cloudConnected && p.cloudConnected()), canShare1to1: canShare1to1() };
    if (!out.cloudConnected) { out.verdict = 'Dropbox is not connected.'; return out; }
    if (!out.canShare1to1) { out.verdict = 'This build has no 1:1 sharing transport (provider.shareFolderWith missing).'; return out; }
    try { localStorage.removeItem(LEGACY_PROBE_KEY); } catch (_) {}   // clear the removed index if an old build left one
    invalidateIncoming();
    // THE discovery call — one request, regardless of how many shared folders exist.
    try { out.deliveries = (await p.shareListDeliveries(SHARE_MARKER)).map(s => ({ folderId: s.id, from: s.owner, isOwner: s.isOwner, invitedAt: s.invitedAt ? new Date(s.invitedAt).toISOString() : '' })); }
    catch (e) {
      out.listError = (e && e.message) || String(e);
      out.verdict = /sharing permission/i.test(out.listError)
        ? 'The Dropbox app is missing the sharing scopes for THIS login — disconnect and reconnect Dropbox.'
        : 'list_received_files failed: ' + out.listError;
      return out;
    }
    out.incomingCount = (await incomingShares(true)).length;
    const cat = await catalog(true);
    out.reads = _lastProbe;                 // one entry per delivery actually read
    out.packagesFound = Object.keys(cat).filter(k => cat[k]._from === 'incoming');
    out.needsMount = [..._needsMount];
    out.subs = await subs();
    out.pendingInvites = (await pendingInvites()).map(m => m.id + '@' + m.rev);
    // Only for context when something is wrong — discovery no longer walks this.
    if (!out.pendingInvites.length) {
      try { out.sharedFolderCount = (await p.shareListIncoming()).length; } catch (_) {}
    }
    const errs = out.reads.filter(x => x.result === 'ERROR');
    if (out.pendingInvites.length) out.verdict = 'OK: ' + out.pendingInvites.join(', ') + ' should be showing on the home screen.';
    else if (!out.deliveries.length) out.verdict = 'Dropbox reports no ' + SHARE_MARKER + ' shared with this account. Either the sender never sent one, used a different email, or sent it from a build that predates delivery notifications — ask them to share it again.';
    else if (!out.incomingCount) out.verdict = 'The only deliveries listed are ones you sent yourself.';
    else if (errs.length && !out.packagesFound.length) out.verdict = 'A delivery is addressed to you but its folder could not be read — see reads[].error. ' + (isPathRootRefusal(errs[0].error) ? 'That is a permission refusal, so it is offered as an "Add to Dropbox" row instead.' : 'The sender may have shared the marker without sharing the folder.');
    else if (!out.packagesFound.length) out.verdict = 'Delivery listed but its marker no longer parses — the sender may have withdrawn it.';
    else out.verdict = 'Package(s) found but already accepted/dismissed — see subs.';
    if (errs.length && out.pendingInvites.length) out.verdict += ' (Note: ' + errs.length + ' other delivery/deliveries could not be read — see reads[].)';
    return out;
  }

  /* ── self test ────────────────────────────────────────────────────────── */
  // SandpieSharing.selfTest() — publish a throwaway package to your own address and
  // walk the whole flow on one account. Turns self-mode on, creates a scratch skill
  // folder, shares it, and reports what each Dropbox step actually returned. The
  // one thing it CANNOT prove is cross-account discovery: Dropbox does not list a
  // file to its owner, so whether list_received_files really carries the delivery
  // to someone else still needs a second account. It reports that honestly rather
  // than passing.
  async function selfTest() {
    const p = prov(), out = { steps: [] };
    const say = (s, v) => { out.steps.push(s + ': ' + v); };
    if (!canShare1to1()) { out.verdict = 'Dropbox not connected, or this build has no sharing transport.'; return out; }
    const email = (p.accountEmail && p.accountEmail()) || me().user;
    out.email = email;
    setAllowSelf(null); say('self-mode', 'reset (armed after publish, scoped to the test package only)');

    const dir = 'sandpie/skills/sandpie-selftest';
    const stamp = new Date().toISOString();
    await O().write(dir + '/SKILL.md', new Blob(['# Sandpie self test\nCreated ' + stamp + '\n'], { type: 'text/markdown' }));
    markDirty(dir + '/SKILL.md');
    say('scratch folder', dir + ' (delete it when you are done)');

    // It has to reach Dropbox before it can be shared.
    say('waiting for sync', 'up to ~60s');
    let synced = false;
    for (let i = 0; i < 30 && !synced; i++) {
      try { await Sandpie.syncProvider().sync(); } catch (_) {}
      try { synced = !!(await p.cloudList(p.shareWorkspacePath(dir), false, { team: false })).length; } catch (_) {}
      if (!synced) await new Promise(r => setTimeout(r, 2000));
    }
    if (!synced) { out.verdict = 'The scratch folder never reached Dropbox — sync may be stalled. Check the Cloud sync panel.'; return out; }
    say('synced', 'yes');

    try { out.publish = await publish(dir, { users: [email] }, { title: 'Sandpie self test' }); say('publish', JSON.stringify(out.publish.dests)); }
    catch (e) { out.verdict = 'publish() failed: ' + ((e && e.message) || e); return out; }
    // Arm self-mode for THIS folder only — not "every folder I own".
    if (!out.publish.shareId) { out.verdict = 'Published, but no shared_folder_id came back, so self-mode cannot be scoped. Check the console for a share_folder error.'; return out; }
    setAllowSelf({ pkgId: out.publish.id, folderId: out.publish.shareId });
    say('self-mode', 'armed for ' + out.publish.id + ' only (folder ' + out.publish.shareId + ')');

    // Did Dropbox accept a self-addressed file share, and does it come back?
    try {
      const got = await p.shareListDeliveries(SHARE_MARKER);
      out.listReceivedFiles = got.map(g => ({ folderId: g.id, isOwner: g.isOwner }));
      say('list_received_files', got.length ? got.length + ' delivery/deliveries (self-addressed shares DO come back)'
                                            : '0 — expected for a self-share; Dropbox does not list a file to its owner');
    } catch (e) { say('list_received_files', 'FAILED ' + ((e && e.message) || e)); }

    invalidateIncoming();
    out.pendingInvites = (await pendingInvites()).map(m => m.id + '@' + m.rev);
    say('invite visible', out.pendingInvites.length ? out.pendingInvites.join(', ') : 'NO');
    out.verdict = out.pendingInvites.length
      ? 'Working. Accept it on the home screen, then edit ' + dir + '/SKILL.md and wait ~2 min — sandpie/shared-installed/ should follow. Cross-account discovery is still unproven; that needs a second account.'
      : 'The package was published but no invite appeared. Run SandpieSharing.diagnose() for the per-step detail.';
    return out;
  }
  async function selfTestCleanup() {
    const p = prov(), dir = 'sandpie/skills/sandpie-selftest';
    try { const id = await p.shareEnsureFolder(p.shareWorkspacePath(dir)); if (p.shareUnshare) await p.shareUnshare(id); } catch (_) {}
    for (const rel of await listOpfs(dir, '', [])) { try { await O().remove(dir + '/' + rel); } catch (_) {} try { Sandpie.events.emit('file:deleted', dir + '/' + rel); } catch (_) {} }
    try { await O().remove(dir); } catch (_) {}
    await removeInstalledLocal('sandpie-selftest');
    setAllowSelf(null);
    // Its accept/dismiss record would otherwise linger and suppress a later re-run.
    try { const s = await subs(); let n = 0;
      for (const k of Object.keys(s.accepted)) if (k === 'sandpie-selftest' || k.startsWith('sandpie-selftest@')) { delete s.accepted[k]; n++; }
      s.dismissed = (s.dismissed || []).filter(k => k !== 'sandpie-selftest' && !k.startsWith('sandpie-selftest@'));
      if (n || s.dismissed) await saveSubs(s);
    } catch (_) {}
    return 'Removed ' + dir + ', its installed copy and accept record, and turned self-mode off.';
  }

  /* ── events ───────────────────────────────────────────────────────────── */
  function fire() { try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {} renderHome(); }
  function subscribe(cb) { const h = () => cb(); window.addEventListener('sandpie-shares-changed', h); return () => window.removeEventListener('sandpie-shares-changed', h); }

  const Sharing = { me, setIdentity, catalog, subs, entitled, publish, pendingInvites, pendingMounts, acceptedList, accept, dismiss, acceptMount, declineMount, uninstall, unshareTeam, autoSync, subscribe, shareDialog, teamHub, recipientHub, outboundStore, incomingShares, incomingStores, invalidateIncoming, liveChanged, diagnose, selfTest, selfTestCleanup, setAllowSelf, allowSelf, INSTALL_ROOT, LOCAL_HUB, SHARE_MARKER };
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
        // Dropbox access level for the 1:1 share. Team-hub shares are copies into a
        // folder whose permissions the team already owns, so it does not apply there.
        '<div class="share-access"><label class="share-opt">They can: <select class="share-in" data-k="access">' +
          '<option value="viewer" selected>View only</option>' +
          '<option value="editor">View and edit</option>' +
        '</select></label><div class="share-warn" style="display:none; font-size:0.75rem; color:var(--sp-warn, #c93); margin:0.15rem 0 0 1.1rem;"></div></div>' +
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
    // Access level applies to 1:1 only, and "edit" on a LIVE folder share is real
    // write access to the sender's own workspace folder — say so plainly, because
    // it is not recoverable by unsharing after the fact.
    const accessRow = back.querySelector('.share-access');
    const accessSel = back.querySelector('.share-in[data-k="access"]');
    const warnBox = back.querySelector('.share-warn');
    const syncAccessUi = () => {
      const to1to1 = back.querySelector('input[name="aud"]:checked').value === 'users';
      accessRow.style.display = to1to1 ? '' : 'none';
      const editor = accessSel.value === 'editor';
      warnBox.style.display = (to1to1 && editor) ? '' : 'none';
      warnBox.textContent = folder
        ? '⚠ They can change and delete files in your own "' + src.split('/').pop() + '" folder.'
        : '⚠ They can change and delete this shared copy.';
    };
    back.querySelectorAll('input[name="aud"]').forEach(r => r.addEventListener('change', syncAccessUi));
    accessSel.addEventListener('change', syncAccessUi);
    syncAccessUi();
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
        const r = await publish(srcPath, audience, { kind: presetKind, pin, pinFile, access: accessSel.value });
        // A live folder share keeps updating on its own, which the sender should
        // know — their later edits (and deletes) reach these people automatically.
        const tail = !cloudOn() ? ' [local test — Dropbox not connected]'
          : sel !== 'users' ? ''
          : (r.access === 'editor' ? ' with edit access' : ' (view only)')
            + (r.live ? '. This folder now stays in sync with them — your later edits and deletes reach them automatically.'
                      : '. They see it next time Sandpie is open.');
        msg.textContent = 'Shared (v' + r.rev + ') → ' + (sel === 'org' ? 'the team' : audience.users.join(', '))
          + (pin ? ', pinned ' + (pinFile || 'file') : '') + tail;
        setTimeout(close, sel === 'users' ? 3600 : 1400);
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
  // Every row action here is async and can take seconds (accept downloads the
  // package; mount/decline are Dropbox round-trips). Without feedback the button
  // just sits there looking untouched, so people click it again and conclude it's
  // broken. This makes the click land immediately: the row goes inert, the button
  // says what it's doing, and re-entry is impossible even before the first await.
  // On success the row is normally replaced by renderHome(); on failure the row
  // comes back so the action can be retried, with the reason attached.
  function busyClick(btn, busyLabel, fn) {
    btn.onclick = async (e) => {
      if (e) e.stopPropagation();
      const row = btn.closest('.shared-file') || btn.parentNode;
      if (row.dataset.busy === '1') return;      // set synchronously — a double-click cannot slip past
      row.dataset.busy = '1';
      const btns = [...row.querySelectorAll('button')];
      const prev = btns.map(b => ({ b, html: b.innerHTML, dis: b.disabled }));
      btns.forEach(b => { b.disabled = true; });
      btn.textContent = busyLabel;
      row.style.opacity = '0.6';
      row.title = busyLabel;
      try { await fn(); }
      catch (err) {
        console.warn('[sharing] action failed:', err);
        // Restore only if this row still exists — a successful action re-renders it away.
        if (row.isConnected) {
          prev.forEach(({ b, html, dis }) => { b.innerHTML = html; b.disabled = dis; });
          row.style.opacity = ''; row.dataset.busy = ''; row.title = '';
          let note = row.querySelector('.share-row-err');
          if (!note) { note = document.createElement('div'); note.className = 'share-row-err'; note.style.cssText = 'flex:1 0 100%; font-size:0.72rem; color:var(--sp-danger, #c33); margin-top:0.2rem;'; row.append(note); }
          note.textContent = (err && err.message) || String(err);
        }
      }
    };
    return btn;
  }
  const kindIcon = (k) => k === 'skill' ? '🧩' : k === 'folder' ? '📁' : '📄';
  const entryOf = (m) => m.pin || (m.kind === 'artifact' ? m.title : (m.kind === 'skill' ? 'SKILL.md' : ''));   // the file to open/pin
  function inviteRow(m) {
    const row = document.createElement('div'); row.className = 'shared-file invite';
    const accNote = m.access === 'editor' ? ' · can edit' : '';
    row.innerHTML = '<span class="shared-file-name">' + kindIcon(m.kind) + ' ' + esc(m.title) + '</span><span class="shared-by">from ' + esc(m._sender || m.publisher) + esc(accNote) + '</span>';
    const acc = document.createElement('button'); acc.className = 'ghost shared-accept'; acc.textContent = 'Accept';
    const dis = document.createElement('button'); dis.className = 'shared-dismiss'; dis.title = 'Dismiss'; dis.textContent = '✕';
    busyClick(acc, 'Accepting…', () => accept(m.id));
    busyClick(dis, '…', () => dismiss(m.id));
    row.append(acc, dis); return row;
  }
  // FALLBACK row, normally never shown: this account wouldn't let us read the
  // sender's shared folder by namespace, so the only way in is to actually add it
  // to the user's Dropbox. Everyone else's shares are read in place and go straight
  // to the invite rows above.
  function mountRow(s) {
    const row = document.createElement('div'); row.className = 'shared-file invite';
    row.innerHTML = '<span class="shared-file-name">🤝 ' + esc(s.from || s.name) + ' shared files with you</span><span class="shared-by">' + esc(s.owner || '') + ' · needs adding to your Dropbox</span>';
    const acc = document.createElement('button'); acc.className = 'ghost shared-accept'; acc.textContent = 'Add';
    const dis = document.createElement('button'); dis.className = 'shared-dismiss'; dis.title = 'Decline and stop receiving from this person'; dis.textContent = '✕';
    busyClick(acc, 'Adding…', () => acceptMount(s.id));
    busyClick(dis, '…', () => declineMount(s.id));
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
    if (onDelete) { const del = document.createElement('button'); del.className = 'shared-dismiss'; del.title = 'Remove'; del.textContent = '✕'; busyClick(del, '…', () => onDelete()); row.append(del); }
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
  // An earlier build persisted an "is this shared folder ours" index; a stale entry
  // in it hides real deliveries, so drop any leftover once on load.
  try { localStorage.removeItem(LEGACY_PROBE_KEY); } catch (_) {}
  function boot() { renderHome(); autoSync(); observeInbox(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  // Deliveries live OUTSIDE the workspace now, so workspace sync activity says
  // nothing about them — and 'sync:done' only fires when the workspace actually
  // changed, so an idle recipient would never re-check. Poll on our own clock.
  // One round is 1 list_folders plus one cheap probe per shared folder (a folder
  // that isn't ours costs a single not_found and no download), and the per-pass
  // memo in catalog() keeps any burst of re-renders free.
  const SHARE_POLL_MS = 60000;
  const pollShares = () => { invalidateIncoming(); autoSync(); renderHome(); };
  setInterval(() => { if (!document.hidden) pollShares(); }, SHARE_POLL_MS);
  window.addEventListener('focus', pollShares);
  // A sync that pulled files still warrants a re-render, but NOT a fresh probe
  // round — invalidating here would double the request rate for no new information.
  try { if (window.Sandpie && Sandpie.events && Sandpie.events.on) Sandpie.events.on('sync:done', () => { renderHome(); }); } catch (_) {}
})();
