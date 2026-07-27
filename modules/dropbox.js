/* =============================================================================
   modules/dropbox.js — Full-Dropbox sync provider.

   The app's sole cloud-sync provider (the former App-folder modules/dropbox.js
   was removed 2026-06-18). Registers a Sandpie sync provider + its cloud-sync
   settings panel. Self-contained: its own dbx* transport + a `dbxfull-*`
   localStorage namespace.

   Requires the user's Dropbox app to be **Full Dropbox** access type with scopes:
     account_info.read, files.metadata.read, files.content.read, files.content.write

   Model
   -----
   - The user's OWN working files (the OPFS root: conversations, scripts, …) sync
     TWO-WAY into /sandpie in the user's OWN Dropbox — i.e. their HOME namespace,
     with NO Dropbox-API-Path-Root header. On a team space that home namespace is
     the member's personal folder (what shows as /<Member Name>/sandpie from the
     team root), so each user's workspace is physically private to them. That
     folder is the ONLY place the sync engine ever writes.
     (Was: <teamParent>/<email-local-part>/ under the team-space root namespace.
      See maybeMigrateToHome() — one-time import of the old team workspace.)
   - The TEAM path-root is still used, but ONLY for the sharing hub and for
     cloud browse/search (`team: true` on the transport helpers). Sync never
     touches it. Everything team-scoped hangs off teamParent(), default
     /R+D+I/sandpie (overridable; the deployment's GET /config dropboxParent
     supplies the org default).
   - NOTHING else syncs by default (full Dropbox can be 100s of GB). In on-demand
     ("dehydrated") mode the working folder is browsed/hydrated lazily instead of
     bulk-downloaded.
   ============================================================================= */
(function () {
  'use strict';
  if (!window.Sandpie) { console.warn('[dropbox] no Sandpie host — disabled'); return; }

  // ---- persistent state (dbxfull-* namespace) -------------------------------
  const TOKENS_KEY = 'dbxfull-tokens';
  const PKCE_KEY   = 'dbxfull-pkce';
  const ROOT_KEY   = 'dbxfull-working-root';
  const STATE_KEY  = 'dbxfull-sync-state';
  const INDEX_KEY  = 'dbxfull-cloud-index';
  const CURSOR_KEY = 'dbxfull-cursor';
  const APPKEY_CFG = 'dbxfull-appkey';
  // LEGACY (pre-home-namespace): the team parent the workspace used to hang off,
  // with <email-local> appended. Still read — by legacyTeamRoot(), to locate the
  // old workspace for the one-time import — but no longer drives the sync target.
  const PARENT_KEY = 'dbxfull-parent';
  const WSROOT_KEY = 'dbxfull-workspace-root';  // personal workspace root, home namespace (user override)
  const DEFAULT_WSROOT = '/sandpie';            // default personal workspace root
  const TEAMPARENT_KEY = 'dbxfull-team-parent';         // team shared area (sharing hub lives here); user override
  const TEAMPARENT_RES = 'dbxfull-team-parent-server';  // cached GET /config dropboxParent (org default)
  const DEFAULT_TEAM_PARENT = '/R+D+I/sandpie'; // fallback team shared area
  const AUTOCONN_OPTOUT = 'dbxfull-no-autoconnect';   // localStorage: set on explicit Disconnect
  const AUTOCONN_TRIED  = 'dbxfull-autoconn-tried';   // sessionStorage: per-session auto-connect loop guard
  const NS_KEY     = 'dbxfull-pathroot';        // team-space root namespace id ('' when root === home)
  const HOMENS_KEY = 'dbxfull-homens';          // home namespace id — needed for cross-namespace `ns:` paths
  const NS_VER_KEY = 'dbxfull-ns-ver';          // detection-logic version; bump ⇒ force a one-time re-fetch
  const EMAIL_KEY  = 'dbxfull-email';           // cached account email (sharing identity + legacy root)
  const SIG_KEY    = 'dbxfull-target-sig';      // namespace|path signature; change ⇒ reset sync state
  const NS_DETECT_VER = '3';                    // 2: detect via root !== home. 3: also capture home_namespace_id.
  const DEHYDRATED_KEY = 'dbxfull-dehydrated';  // DEPRECATED: on-demand is now the default when connected
  const PENDING_KEY    = 'dbxfull-pending';       // uploaded-but-not-yet-cursor-confirmed paths (protect from cleanup)
  const EXEMPT_PREFIXES = ['sandpie/conversations', 'sandpie/skills', 'sandpie/memory', 'sandpie/config', 'sandpie/shared-installed', 'sandpie/shared-incoming'];   // app metadata: always eagerly synced + never dehydrate-purged. memory MUST be exempt: it's injected into every system prompt page-side (memory.js list()/systemBlock read local OPFS directly, NOT via the worker's lazy hydration), so purging it locally silently breaks recall. sandpie/config holds pins.json (read page-side at boot by pins.js — same reason). (sandpie/scripts, sandpie/artifacts stay dehydratable.)
  const DBX_REDIRECT = location.origin + location.pathname;

  // ===========================================================================
  //  Transport  (own copy; full-Dropbox absolute paths)
  // ===========================================================================
  function dbxRoute(url) {
    // Browser → Dropbox directly. Dropbox supports CORS across the API (the PKCE
    // token endpoint, the RPC endpoints, and the content endpoints), so no server
    // hop is needed. The previous build prefixed a server-side /proxy/ (shared
    // with the LLM proxy via the AI provider's #proxyUrl field), but the thin
    // sandpie-server has no /proxy/ route — and proxying would route the user's
    // Dropbox access token through our server. Going direct keeps that token in
    // the browser. If a deployment's egress truly can't reach *.dropboxapi.com,
    // reintroduce a proxy hop here, decoupled from the AI provider's proxyUrl.
    return url;
  }
  function b64url(buf) {
    return btoa(String.fromCharCode(...new Uint8Array(buf)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  }
  async function pkceChallenge() {
    const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    return { verifier, challenge: b64url(hash) };
  }
  function tokens() { try { return JSON.parse(localStorage.getItem(TOKENS_KEY) || 'null'); } catch { return null; } }
  async function accessToken() {
    const stored = tokens();
    if (!stored) throw new Error('Dropbox not connected');
    if (Date.now() < stored.expires_at - 60000) return stored.access_token;
    const body = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: stored.refresh_token, client_id: stored.app_key });
    const res = await fetch(dbxRoute('https://api.dropboxapi.com/oauth2/token'), {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body.toString(),
    });
    if (!res.ok) throw new Error('Token refresh failed: ' + await res.text());
    const data = await res.json();
    stored.access_token = data.access_token;
    stored.expires_at = Date.now() + data.expires_in * 1000;
    localStorage.setItem(TOKENS_KEY, JSON.stringify(stored));
    pushDbxTokenToSW();
    return data.access_token;
  }
  // TEAM-scoped calls only. The default API behavior — no header — resolves paths
  // against the member's HOME namespace, which is where the personal workspace now
  // lives; that is the default for every transport helper below. Pass `team: true`
  // to reach team/department folders (e.g. /R+D+I) instead: the sharing hub and
  // cloud browse/search. No-op on a non-team account (no team root namespace).
  // `ns` roots the call at an arbitrary namespace instead. A shared folder IS a
  // namespace (the spec has `alias SharedFolderId = NamespaceId`), so passing a
  // shared_folder_id here reads that folder IN PLACE — no mounting, nothing added
  // to the user's Dropbox. Membership is the only gate; PathRootError.no_permission
  // is what you get without it.
  function pathRootHeader({ team = false, ns = '' } = {}) {
    if (ns) return { 'Dropbox-API-Path-Root': JSON.stringify({ '.tag': 'namespace_id', namespace_id: String(ns) }) };
    const t = localStorage.getItem(NS_KEY);
    return (team && t) ? { 'Dropbox-API-Path-Root': JSON.stringify({ '.tag': 'root', root: t }) } : {};
  }
  function pathRootHeaderObj() { return pathRootHeader({ team: true }); }
  // Dropbox-API-Arg travels in an HTTP header, which must be ASCII. Escape every
  // non-ASCII char as \uXXXX (Dropbox un-escapes server-side) — otherwise a path
  // with accents (e.g. "DOCUMENTACIÓ", "Pràctiques") is sent as raw Latin-1 and
  // the request is rejected (empty 401 at the proxy). Paths in JSON *bodies* are
  // unaffected, which is why upload/list worked and only download broke.
  function apiArg(obj) {
    return JSON.stringify(obj).replace(/[^\x00-\x7F]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  }
  async function api(path, body, { team = false, ns = '' } = {}) {
    const token = await accessToken();
    const headers = { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' };
    Object.assign(headers, pathRootHeader({ team, ns }));
    const res = await fetch(dbxRoute('https://api.dropboxapi.com' + path), {
      method: 'POST', headers, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Dropbox ${path}: ${res.status} ${await res.text()}`);
    return await res.json();
  }
  // DeletedMetadata sometimes lacks path_display (only path_lower). Fallback so
  // deletion entries survive `cloudToRel` and actually remove items from index.
  const mapEntry = e => ({ name: e.name, kind: e['.tag'], path: e.path_display || e.path_lower, size: e.size, rev: e.rev, hash: e.content_hash, cloudMtime: e.server_modified });
  async function listFolder(folderPath, { recursive = false, team = false, ns = '' } = {}) {
    let data = await api('/2/files/list_folder', { path: folderPath === '/' ? '' : folderPath, recursive, include_deleted: true }, { team, ns });
    let entries = data.entries.slice();
    while (data.has_more) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }, { team, ns }); entries = entries.concat(data.entries); }
    return { entries: entries.map(mapEntry), cursor: data.cursor };
  }
  async function listContinue(cursor) {
    let data = await api('/2/files/list_folder/continue', { cursor });
    let entries = data.entries.slice();
    while (data.has_more) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }); entries = entries.concat(data.entries); }
    return { entries: entries.map(mapEntry), cursor: data.cursor };
  }
  async function download(path, signal, { team = false, ns = '' } = {}) {
    // /2/files/download's SUCCESS (200) response does NOT carry CORS headers — only
    // its preflight and ERROR responses do. So a direct browser fetch can read an
    // error but not the file: a 200 fails the browser CORS check ("No
    // Access-Control-Allow-Origin"), which is exactly what breaks sync. The old
    // build hid this by routing through a same-origin /proxy/; this server has none
    // (see dbxRoute). Dropbox's documented browser-download path is
    // get_temporary_link (a normal RPC — fully CORS-enabled) → GET the returned URL
    // (a plain GET = no custom headers = NO preflight, and the temp-link host returns
    // ACAO), which works cross-origin even under the prod COOP/COEP isolation.
    const tl = await api('/2/files/get_temporary_link', { path }, { team, ns });
    const res = await fetch(dbxRoute(tl.link), { method: 'GET', signal });
    if (!res.ok) throw new Error(`Download ${path}: ${res.status}`);
    return new Uint8Array(await res.arrayBuffer());
  }
  async function uploadSessionStart(content, close = true) {
    const token = await accessToken();
    const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/upload_session/start'), {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream', 'Dropbox-API-Arg': apiArg({ close }) },
      body: content,
    });
    if (!res.ok) throw new Error(`Upload session start: ${res.status} ${await res.text()}`);
    return await res.json();
  }
  async function uploadSessionFinishBatch(entries) {
    const token = await accessToken();
    const res = await fetch(dbxRoute('https://api.dropboxapi.com/2/files/upload_session/finish_batch_v2'), {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries }),
    });
    if (!res.ok) throw new Error(`Finish batch: ${res.status} ${await res.text()}`);
    return await res.json();
  }
  // Bounded-parallel upload_session/start (5 at a time), then ONE finish_batch_v2
  // commit for the whole batch — far fewer commit round-trips than per-file
  // uploads, and avoids too_many_write_operations throttling on a large first
  // sync. Adapted from dropbox.js; commit path is prefixed with the working root.
  async function uploadBatch(files) {
    const CONCURRENCY = 5;
    const sessions = [];
    for (let i = 0; i < files.length; i += CONCURRENCY) {
      const chunk = files.slice(i, i + CONCURRENCY);
      const results = await Promise.all(chunk.map(async ({ rel, content, lm, s }) => {
        try {
          const session = await uploadSessionStart(content, true);
          return {
            cursor: { session_id: session.session_id, offset: content.byteLength },
            commit: { path: relToCloud(rel), mode: 'overwrite', mute: true, autorename: false },
            rel, lm, s, content,
          };
        } catch (err) { console.warn('[dropbox] session start failed:', rel, err); return null; }
      }));
      sessions.push(...results.filter(Boolean));
    }
    if (!sessions.length) return [];
    const entries = sessions.map(x => ({ cursor: x.cursor, commit: x.commit }));
    const result = await uploadSessionFinishBatch(entries);
    if (result['.tag'] === 'async_job_id') { console.warn('[dropbox] finish_batch returned async_job_id — skipped, will retry next sync'); return []; }
    if (!result.entries) { console.warn('[dropbox] unexpected finish_batch response:', result); return []; }
    return sessions.map((x, i) => ({ ...x, meta: result.entries[i] }));
  }
  async function del(path, { team = false, ns = '' } = {}) {
    try { return await api('/2/files/delete_v2', { path }, { team, ns }); }
    catch (e) { if (String(e.message).includes('not_found')) return null; throw e; }
  }
  async function getCurrentAccount() { return await api('/2/users/get_current_account', null); }
  async function dbxMeta(path, team) {
    // Metadata, or null if absent. Rethrows other errors so the caller can abort.
    // not_found ⇒ absent here. malformed_path ⇒ this path is invalid in THIS
    // namespace — treat as absent so the caller can fall through.
    try { return await api('/2/files/get_metadata', { path }, { team }); }
    catch (e) { if (/not_found|malformed_path/.test(String(e && e.message))) return null; throw e; }
  }
  async function mkdirp(path) {
    try { return await api('/2/files/create_folder_v2', { path, autorename: false }); }
    catch (e) { if (/conflict/.test(String(e && e.message))) return null; throw e; }
  }

  // ===========================================================================
  //  Working root  (/sandpie, in the user's own HOME namespace)
  // ===========================================================================
  function workingRoot() { return localStorage.getItem(ROOT_KEY) || ''; }
  function sanitizeSeg(s) { return String(s).replace(/[^a-zA-Z0-9._-]/g, '_').replace(/^_+|_+$/g, '') || 'user'; }
  function normPath(p, fallback) {
    let s = String(p == null ? '' : p).trim() || fallback;
    if (!s.startsWith('/')) s = '/' + s;
    return s.replace(/\/+$/, '') || fallback;
  }
  // The TEAM shared area — where the sharing hub lives. Always resolved against the
  // team-space root namespace (`team: true`), independent of the personal workspace.
  // '' on a non-team account: there is no team space, so sharing falls back to its
  // local simulation (see sharing.js cloudOn()/cloudParent()).
  function teamParent() {
    if (!localStorage.getItem(NS_KEY)) return '';
    const cfg = localStorage.getItem(TEAMPARENT_KEY) || localStorage.getItem(TEAMPARENT_RES) || DEFAULT_TEAM_PARENT;
    return normPath(cfg, DEFAULT_TEAM_PARENT);
  }
  // Where this user's workspace USED to live: <old team parent>/<email-local>, under
  // the team path-root. Only used to locate data for the one-time import; '' if we
  // never knew the email (nothing to import from).
  function legacyTeamRoot() {
    const email = localStorage.getItem(EMAIL_KEY);
    if (!email) return '';
    const parent = normPath(localStorage.getItem(PARENT_KEY) || localStorage.getItem(TEAMPARENT_RES) || DEFAULT_TEAM_PARENT, DEFAULT_TEAM_PARENT);
    return parent + '/' + sanitizeSeg(String(email).split('@')[0]);
  }
  async function ensureWorkingRoot() {
    // Account fetched once (cached): the team-space root namespace (team accounts
    // only) + the home namespace id + the account email (sharing identity).
    let ns = localStorage.getItem(NS_KEY);
    let email = localStorage.getItem(EMAIL_KEY);
    if (ns === null || !email || localStorage.getItem(NS_VER_KEY) !== NS_DETECT_VER) {
      const acct = await getCurrentAccount();
      const ri = acct.root_info || {};
      // Team space ⇔ the root namespace differs from the home namespace. Do NOT gate on
      // root_info['.tag']: an account sitting in a team space can still report '.tag' ===
      // 'user' while having a distinct root_namespace_id (confirmed in the field). Gating on
      // the tag left the path-root header off, so team paths like /R+D+I resolved against the
      // personal home folder instead of the team space. '' ⇒ no team space at all.
      ns = (ri.root_namespace_id && ri.root_namespace_id !== ri.home_namespace_id) ? ri.root_namespace_id : '';
      email = acct.email || acct.account_id || 'user';
      localStorage.setItem(NS_KEY, ns);
      localStorage.setItem(HOMENS_KEY, ri.home_namespace_id || '');
      localStorage.setItem(EMAIL_KEY, email);
      localStorage.setItem(NS_VER_KEY, NS_DETECT_VER);
      console.info('[dropbox] workspace → home namespace ' + (ri.home_namespace_id || '(default)') + '; team root ' + (ns || '(none)'));
    }
    // Cache the deployment's team parent (GET /config dropboxParent) so teamParent()
    // — which is called synchronously all over — can see the org default. It now
    // configures the SHARING hub only; the workspace root is always personal.
    try { const sp = await serverParent(); if (sp) localStorage.setItem(TEAMPARENT_RES, normPath(sp, DEFAULT_TEAM_PARENT)); } catch (_) {}
    // Workspace = /sandpie in the user's own Dropbox. No <email> subfolder: the home
    // namespace is already per-user. Overridable in the Cloud sync section.
    const root = normPath(localStorage.getItem(WSROOT_KEY) || DEFAULT_WSROOT, DEFAULT_WSROOT);
    // Relocate guard. The sync target is (namespace + path): the SAME path string
    // resolves to DIFFERENT folders under different path-roots (home namespace vs
    // team space), so the namespace MUST be part of the signature — otherwise
    // switching roots reuses stale state and wrongly deletes local files as
    // "removed remotely". When the signature changes (root edit, or the one-time
    // move off the team space) drop the old sync state so the new location starts
    // fresh: re-pull there + re-push the local working dir, deleting nothing.
    const sig = 'home|' + root;
    if (localStorage.getItem(SIG_KEY) !== sig) {
      localStorage.setItem(SIG_KEY, sig);
      localStorage.removeItem(STATE_KEY);
      localStorage.removeItem(INDEX_KEY);
      localStorage.removeItem(CURSOR_KEY);
      localStorage.removeItem(PENDING_KEY);
    }
    localStorage.setItem(ROOT_KEY, root);
    return root;
  }
  // OPFS rel "foo/bar.json"  <->  Dropbox "<workingRoot>/foo/bar.json"
  function relToCloud(rel) { return workingRoot() + '/' + String(rel).replace(/^\/+/, ''); }
  function cloudToRel(p) {
    const rp = workingRoot().replace(/^\/+/, '').toLowerCase();
    let s = String(p).replace(/^\/+/, '');
    if (s.toLowerCase().startsWith(rp + '/')) return s.slice(rp.length + 1);
    if (s.toLowerCase() === rp) return '';
    return null;   // outside the working root — ignore
  }

  // ===========================================================================
  //  Sync state
  // ===========================================================================
  function syncState() { try { return JSON.parse(localStorage.getItem(STATE_KEY) || '{}'); } catch { return {}; } }
  function setSyncState(s) { localStorage.setItem(STATE_KEY, JSON.stringify(s)); }
  function cloudIndex() { try { return JSON.parse(localStorage.getItem(INDEX_KEY) || '{}'); } catch { return {}; } }
  function setCloudIndex(i) { localStorage.setItem(INDEX_KEY, JSON.stringify(i)); }
  function dehydrated() { return !!tokens(); }  // always on-demand when Dropbox is connected
  function isExemptRel(rel) {
    const r = String(rel).replace(/^\/+/, '').toLowerCase();
    return EXEMPT_PREFIXES.some(p => {
      const pl = p.toLowerCase();
      if (pl === 'sandpie/skills') {
        // Only SKILL.md files, not scripts/templates/etc under skills folders
        return r.startsWith(pl + '/') && r.split('/').pop() === 'skill.md';
      }
      return r === pl || r.startsWith(pl + '/');
    });
  }
  // Convert an already-synced workspace to on-demand: remove LOCAL copies of clean
  // cloud files so they re-fetch lazily. SAFETY: deletes via opfs.remove() only —
  // it never emits 'file:deleted', so onFileDeleted/del() never runs and NOTHING
  // is deleted from Dropbox. Skips exempt folders, the open file, and any file
  // with unsynced local edits (lm > syncedMtime) so no local change is lost.
  async function dehydratePurge() {
    const opfs = Sandpie.opfs;
    const idx = cloudIndex();
    const st = syncState();
    const openFilePath = Sandpie.openFilePath ? Sandpie.openFilePath() : null;
    let purged = 0, kept = 0;
    for (const rel of Object.keys(idx)) {
      const e = idx[rel];
      if (!e || e.kind !== 'file') continue;
      if (isExemptRel(rel) || rel === openFilePath) { kept++; continue; }
      if (!(await opfs.exists(rel))) continue;                 // already not local
      const s = st[rel];
      const lm = await Sandpie.opfsMtime(rel);
      if (!s || lm > s.syncedMtime) { kept++; continue; }      // untracked or locally modified — keep
      if (Date.now() - lm < 86400000) { kept++; continue; }    // modified in the last 24h — keep
      try { await opfs.remove(rel); delete st[rel]; purged++; } // OPFS-only delete; Dropbox untouched
      catch (_) {}
    }
    setSyncState(st);
    return { purged, kept };
  }
  // One-time: stage 1 wrote a worker manifest (_dehydrated_cache.json) at the OPFS
  // root which the push could leak to Dropbox. We no longer create it — remove any
  // leftover copy locally and remotely (best-effort, guarded once; it's our own
  // internal file, never user data, so del() here is safe).
  async function cleanupStaleArtifacts() {
    if (localStorage.getItem('dbxfull-artifacts-cleaned') !== '1') {
      localStorage.setItem('dbxfull-artifacts-cleaned', '1');
      try { await Sandpie.opfs.remove('_dehydrated_cache.json'); } catch (_) {}
      try { if (tokens()) await del(relToCloud('_dehydrated_cache.json')); } catch (_) {}
    }
    // Subscriptions feature removed — delete any leftover read-only mirror data
    // locally (OPFS only; opfs.remove never emits file:deleted, so the source
    // folders in Dropbox are untouched). One-time.
    if (localStorage.getItem('dbxfull-subs-removed') !== '1') {
      localStorage.setItem('dbxfull-subs-removed', '1');
      try { await Sandpie.opfs.remove('_subs'); } catch (_) {}
      localStorage.removeItem('dbxfull-subscriptions');
      localStorage.removeItem('dbxfull-subs-state');
    }
    // Worker provenance/usage index files are no longer written — remove any
    // leftovers locally + from Dropbox (root-level files that used to sync). Once.
    if (localStorage.getItem('dbxfull-index-files-cleaned') !== '1') {
      localStorage.setItem('dbxfull-index-files-cleaned', '1');
      for (const f of ['conv2file_index.json', 'script_usage_index.json']) {
        try { await Sandpie.opfs.remove(f); } catch (_) {}
        try { if (tokens()) await del(relToCloud(f)); } catch (_) {}
      }
    }
  }

  // One-time move of the app folders under a single sandpie/ folder:
  //   _conversations -> sandpie/conversations,  agents -> sandpie/agents,  skills -> sandpie/skills,
  //   scripts -> sandpie/scripts,  artifacts -> sandpie/artifacts,  memory -> sandpie/memory.
  // (conversations/agents/skills/memory are exempt = eager; scripts/artifacts stay
  // dehydratable — they're just relocated.)
  // Dropbox side uses move_v2 (ATOMIC — the source is preserved if it fails), and
  // if it can't complete we abort WITHOUT touching local, so local and Dropbox
  // never diverge (no data loss, no duplication); we retry next boot. Only after
  // Dropbox reflects the new layout (or we're offline) do we move OPFS + set the
  // guard. Runs before dehydratePurge so the moved files are seen at their new path.
  // Guard bumped to -v2 when scripts/artifacts/memory were added: users who ran the
  // 3-folder v1 re-run once (already-moved folders no-op via not_found/conflict).
  const SANDPIE_MOVES = [['_conversations', 'sandpie/conversations'], ['agents', 'sandpie/agents'], ['skills', 'sandpie/skills'], ['scripts', 'sandpie/scripts'], ['artifacts', 'sandpie/artifacts'], ['memory', 'sandpie/memory']];
  async function opfsMoveDir(oldRel, newRel) {
    const opfs = Sandpie.opfs;
    let files = [];
    try { files = await opfs.list(oldRel); } catch { return; }   // nothing to move
    for (const f of files) {
      const sub = f.slice(oldRel.length).replace(/^\/+/, '');
      try { await opfs.write(newRel + '/' + sub, await opfs.readBytes(f)); }
      catch (e) { console.warn('[dropbox] move file failed:', f, e && e.message); }
    }
    try { await opfs.remove(oldRel); } catch (_) {}
  }
  async function migrateExemptToSandpie() {
    if (localStorage.getItem('dbxfull-sandpie-migrated-v2') === '1') return;
    if (tokens()) {
      let wr = '';
      try { await ensureWorkingRoot(); wr = (localStorage.getItem(ROOT_KEY) || '').replace(/\/+$/, ''); } catch (_) {}
      if (!wr) return;   // root not resolved yet → retry next boot
      for (const [oldName, newRel] of SANDPIE_MOVES) {
        try { await api('/2/files/move_v2', { from_path: wr + '/' + oldName, to_path: wr + '/' + newRel, autorename: false }); }
        catch (e) {
          const m = String((e && e.message) || '').toLowerCase();
          // not_found = source already moved/never existed; conflict/duplicate = dest already there → fine.
          if (!/not_found|malformed_path|conflict|duplicate/.test(m)) { console.warn('[dropbox] sandpie migration deferred:', oldName, m); return; }
        }
      }
      // Dropbox now reflects the new layout — reset sync state so the next sync
      // reconciles it cleanly (the existing target-change reset path).
      localStorage.removeItem(STATE_KEY); localStorage.removeItem(INDEX_KEY); localStorage.removeItem(CURSOR_KEY); localStorage.removeItem(PENDING_KEY);
    }
    for (const [oldName, newRel] of SANDPIE_MOVES) {
      try { await opfsMoveDir(oldName, newRel); } catch (e) { console.warn('[dropbox] local move failed:', oldName, e && e.message); }
    }
    localStorage.setItem('dbxfull-sandpie-migrated-v2', '1');
    try { if (window.refreshFileList) window.refreshFileList(); } catch (_) {}
    try { if (window.refreshConversationList) window.refreshConversationList(); } catch (_) {}
  }
  function cursor() { return localStorage.getItem(CURSOR_KEY) || null; }
  function setCursor(c) { if (c) localStorage.setItem(CURSOR_KEY, c); else localStorage.removeItem(CURSOR_KEY); }

  // ---- pending-upload set (protect freshly-uploaded files from cleanup race) ----
  // `cloudListWorking()` clears entries as soon as Dropbox cursor/index confirms them.
  // This prevents the deletion pass from removing a file whose upload succeeded but
  // whose cursor has not yet moved past it. No timeout needed — deterministic.
  function pending() {
    try { return JSON.parse(localStorage.getItem(PENDING_KEY) || '{}'); }
    catch { return {}; }
  }
  function setPending(obj) { localStorage.setItem(PENDING_KEY, JSON.stringify(obj)); }
  function addPending(rel) {
    const p = pending(); if (!p[rel]) { p[rel] = 1; setPending(p); }
  }
  function removePending(rel) {
    const p = pending(); if (p[rel]) { delete p[rel]; setPending(p); }
  }
  function clearPending(confirmedRels) {
    // Batch-remove a set of relatives from pending.
    const p = pending(); let changed = false;
    for (const r of confirmedRels) { if (p[r]) { delete p[r]; changed = true; } }
    if (changed) setPending(p);
  }

  let _syncing = false;
  let initialSyncDone = !tokens();
  let _syncCount = 0;
  const FULL_SCAN_EVERY = 10;

  // ---- cloud listing of ONLY the working root (cursor delta) -----------------
  async function cloudListWorking() {
    const stored = cursor();
    const idx = cloudIndex();
    if (stored && Object.keys(idx).length > 0) {
      try {
        const result = await listContinue(stored);
        const delta = [];
        const deletions = [];
        const confirmed = [];
        for (const e of result.entries) {
          const rel = cloudToRel(e.path);
          if (rel == null || rel === '') continue;
          if (e.kind === 'deleted') {
            delete idx[rel];
            deletions.push(rel);
            // path_lower may differ in case from the original key — try case-insensitive too
            const rl = rel.toLowerCase();
            for (const k of Object.keys(idx)) { if (k.toLowerCase() === rl) { delete idx[k]; break; } }
            // Dropbox reports only the folder itself as deleted — not its descendants.
            // Remove them from the index or they'd persist in cloudSet and never be
            // deleted locally on incremental (cursor-delta) syncs.
            const prefix = rel + '/';
            const prefixLc = prefix.toLowerCase();
            for (const k of Object.keys(idx)) {
              if (k.toLowerCase().startsWith(prefixLc)) { delete idx[k]; deletions.push(k); }
            }
          } else { idx[rel] = e; delta.push([rel, e]); }
          confirmed.push(rel);   // clear pending for any cursor entry (present or deleted)
        }
        if (confirmed.length) clearPending(confirmed);
        setCursor(result.cursor); setCloudIndex(idx);
        return { index: idx, delta, deletions };
      } catch (err) {
        console.warn('[dropbox] cursor sync failed, full re-list:', err.message);
        setCursor(null);
      }
    }
    let result;
    try {
      result = await listFolder(workingRoot(), { recursive: true });
    } catch (e) {
      if (String(e.message).includes('not_found')) {   // working folder doesn't exist yet (or was deleted)
        setCursor(null); setCloudIndex({}); setPending({});
        return { index: {}, delta: null };
      }
      throw e;
    }
    const out = {};
    const confirmed = [];
    for (const e of result.entries) {
      const rel = cloudToRel(e.path);
      if (rel == null || rel === '') continue;
      if (e.kind !== 'deleted') { out[rel] = e; confirmed.push(rel); }
    }
    if (confirmed.length) clearPending(confirmed);
    setCursor(result.cursor); setCloudIndex(out);
    return { index: out, delta: null };
  }

  // ---- sync progress bar (non-disruptive) -----------------------------------
  // Live transfer progress shown ABOVE the conversation list during ANY sync —
  // downloads (pulling cloud files) AND uploads (pushing local changes) — so it's
  // actually visible in normal use. (The old bar replaced #convList and only ran
  // on the very first sync's downloads, which a returning user whose files are
  // already local never hits — hence "I never see it".) It's a sibling of
  // #convList, so refreshConversationList()'s replaceChildren doesn't touch it;
  // sync()'s finally clears it. Hidden whenever nothing is transferring.
  function _setSyncProgress(done, total, phase) {
    const ul = document.getElementById('convList');
    if (!ul || !ul.parentNode) return;
    let bar = document.getElementById('dbxSyncProgress');
    if (!total) { if (bar) bar.remove(); return; }
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'dbxSyncProgress';
      bar.className = 'sync-progress';
      ul.parentNode.insertBefore(bar, ul);
    }
    const pct = Math.min(100, Math.round((done / total) * 100));
    bar.innerHTML =
      `<div class="sp-row"><span>${phase || 'Syncing'}…</span><span>${done} / ${total}</span></div>` +
      `<div class="sp-track"><div class="sp-fill" style="width:${pct}%"></div></div>`;
  }

  // ---- bounded-parallel per-file download ------------------------------------
  const DL_CONCURRENCY = 16;
  async function bulkDownload(items, state, opfs, onProgress) {
    if (!items.length) return;
    let i = 0, done = 0;
    const total = items.length;
    async function worker() {
      while (i < items.length) {
        const it = items[i++];
        try {
          const bytes = await download(it.cloudPath);
          await opfs.write(it.rel, bytes);
          const mtime = await Sandpie.opfsMtime(it.rel);
          state[it.rel] = { rev: it.e.rev, size: it.e.size, syncedMtime: mtime };
        } catch (err) { console.warn('[dropbox] download failed:', it.rel, err); }
        if (onProgress) { try { onProgress(++done, total); } catch (_) {} }
      }
    }
    await Promise.all(Array.from({ length: Math.min(DL_CONCURRENCY, items.length) }, worker));
  }

  // ---- the sync engine (working dir only) ------------------------------------
  async function sync(opts = {}) {
    if (!tokens()) return;
    if (_syncing) return;
    if (Sandpie.isGenerating()) return;
    _syncing = true; setBusy(true); _syncCount++;
    const firstSync = !initialSyncDone;
    const opfs = Sandpie.opfs;
    const openFilePath = Sandpie.openFilePath();
    try {
      await ensureWorkingRoot();
      dbxStatus('', 'connected');
      const { index: cloud, delta, deletions } = await cloudListWorking();
      if (dehydrated()) pushDbxIndexToSW();   // keep the worker's lazy index fresh
      const state = syncState();
      const fullScan = !!opts.full || !initialSyncDone || delta === null || (_syncCount % FULL_SCAN_EVERY === 0);

      // ── Dropbox is the authority: delete everything that no longer exists in cloud ──
      let removedAny = false;
      const cloudSet = new Set(Object.keys(cloud));
      const p = pending();
      const isConv = p => p.includes('conversations');

      // ── Pass 1: entries still in sync-state ──
      for (const path of Object.keys(state)) {
        if (cloudSet.has(path)) continue;
        if (state[path].syncedMtime === 0) {
          if (isConv(path)) console.log('[dropbox] PASS1 KEEP (dirty):', path, 'syncedMtime=0');
          continue;
        }
        if (p[path]) {
          if (isConv(path)) console.log('[dropbox] PASS1 KEEP (pending):', path);
          continue;
        }
        const exists = await opfs.exists(path);
        if (isConv(path)) console.log('[dropbox] PASS1 DELETE:', path, 'exists=', exists);
        if (!exists) { delete state[path]; continue; }
        try {
          await opfs.remove(path);
          delete state[path]; removedAny = true;
        } catch (e) {
          console.warn('[dropbox] PASS1 remove FAILED:', path, e && e.message);
        }
      }

      // ── Pass 2: local files with no state entry ──
      let allLocal = []; try { allLocal = await opfs.list(); } catch (e) {
        console.warn('[dropbox] opfs.list() FAILED:', e && e.message);
      }
      let removedCount = 0, keptCount = 0;
      for (const path of allLocal) {
        if (cloudSet.has(path)) { keptCount++; continue; }
        if (state[path] && state[path].syncedMtime === 0) {
          if (isConv(path)) console.log('[dropbox] PASS2 KEEP (dirty-state):', path);
          keptCount++; continue;
        }
        if (p[path]) {
          if (isConv(path)) console.log('[dropbox] PASS2 KEEP (pending):', path);
          keptCount++; continue;
        }
        if (isConv(path)) console.log('[dropbox] PASS2 DELETE orphan:', path);
        try {
          await opfs.remove(path);
          if (state[path]) delete state[path];
          removedAny = true; removedCount++;
        } catch (e) {
          console.warn('[dropbox] PASS2 remove FAILED:', path, e && e.message);
        }
      }
      console.log('[dropbox] cleanup done:', allLocal.length, 'local files,', cloudSet.size, 'cloud items,', removedCount, 'deleted,', keptCount, 'kept');

      // pull
      const toConsider = (fullScan || delta === null) ? Object.entries(cloud) : delta;
      const toDownload = [];
      for (const [path, e] of toConsider) {
        if (e.kind !== 'file') continue;
        if (dehydrated() && !isExemptRel(path)) continue;   // on-demand: skip eager download; worker hydrates on touch
        const s = state[path];
        const localExists = await opfs.exists(path);
        if (!s) {
          if (localExists) state[path] = { rev: e.rev, size: e.size, syncedMtime: await Sandpie.opfsMtime(path) };
          else toDownload.push({ rel: path, cloudPath: e.path, e });
          continue;
        }
        const cloudChanged = s.rev !== e.rev;
        if (path === openFilePath) continue;
        if (cloudChanged || !localExists) { toDownload.push({ rel: path, cloudPath: e.path, e }); continue; }
        state[path].size = e.size;
      }
      if (toDownload.length) _setSyncProgress(0, toDownload.length, 'Downloading');
      await bulkDownload(toDownload, state, opfs, toDownload.length ? (d, t) => _setSyncProgress(d, t, 'Downloading') : null);

      // push: only files explicitly marked dirty (syncedMtime===0) by edit events.
      // A full-scan upload that treated "no state entry" as dirty has been removed
      // because it causes mega-uploads when localStorage state is lost or reset and
      // Dropbox already holds the correct copies. Dropbox is the authority; we only
      // upload files the conversation itself created or edited.
      const dirty = [];
      for (const rel of Object.keys(state)) {
        if (rel === openFilePath) continue;
        if (state[rel].syncedMtime !== 0) continue;
        if (!(await opfs.exists(rel))) continue;
        dirty.push({ rel, lm: await Sandpie.opfsMtime(rel), s: state[rel] });
      }
      const BATCH_SIZE = 50;
      let upDone = 0;
      if (dirty.length) _setSyncProgress(0, dirty.length, 'Uploading');
      for (let i = 0; i < dirty.length; i += BATCH_SIZE) {
        const chunk = dirty.slice(i, i + BATCH_SIZE);
        const files = await Promise.all(chunk.map(async ({ rel, lm, s }) => ({ rel, lm, s, content: await opfs.readBytes(rel) })));
        try {
          const results = await uploadBatch(files);
          for (const r of results) {
            if (r.meta && r.meta['.tag'] === 'success') {
              state[r.rel] = {
                rev: r.meta.rev || (r.s && r.s.rev) || '',
                size: r.meta.size != null ? r.meta.size : (r.s && r.s.size != null ? r.s.size : r.content.byteLength),
                syncedMtime: r.lm,
              };
              addPending(r.rel);   // protect from deletion until cursor confirms
            } else {
              console.warn('[dropbox] batch item failed:', r.rel, r.meta);
            }
          }
        } catch (err) { console.warn('[dropbox] batch upload failed:', err); }
        upDone += chunk.length;
        _setSyncProgress(upDone, dirty.length, 'Uploading');
      }
      setSyncState(state);

      // Dehydrate files not modified in the last 24h
      if (dehydrated()) await dehydratePurge();

      // Any cursor-delta activity should refresh the viewer, which renders the
      // cloud index in dehydrated mode. Adds of cloud-only files skip download
      // (toDownload empty) and remote deletes remove nothing from OPFS
      // (removedAny false), so without delta/deletions here the viewer would only
      // update on a manual page refresh.
      const cursorChanged = (delta && delta.length) || (deletions && deletions.length);
      if (firstSync || toDownload.length || dirty.length || removedAny || cursorChanged) {
        await Sandpie.refreshFiles();
        await Sandpie.refreshConversations();
        // Let sharing.js react to pulled changes (e.g. a new file in shared-incoming
        // → refresh the invite notifications + banner without a manual refresh).
        try { Sandpie.events.emit('sync:done', { downloaded: toDownload.map(d => d.rel), deletions: deletions || [] }); } catch (_) {}
      }
    } catch (e) {
      dbxStatus('Sync failed: ' + e.message, 'error');
      console.warn('[dropbox] sync:', e);
    } finally {
      initialSyncDone = true; setBusy(false); _syncing = false;
      try { _setSyncProgress(0, 0); } catch (_) {}   // clear the bar when the cycle ends
    }
  }



  // ---- file-browser status + event reactions --------------------------------
  function fileStatus(path, opfsMtime) {
    const s = syncState()[path];
    if (!s) return null;
    return opfsMtime <= s.syncedMtime ? 'synced' : 'modified';
  }
  function onFileChanged(path) {
    const rel = String(path).replace(/^\/+/, '');
    if (!rel) return;
    const st = syncState();
    if (st[rel]) st[rel].syncedMtime = 0; else st[rel] = { rev: '', size: 0, syncedMtime: 0 };
    setSyncState(st);
  }
  // Remove a path (and its subtree) from BOTH the sync state and the cloud index.
  // The file viewer and the worker read the cloud index in dehydrated mode, so
  // skipping the index left a deleted cloud-only placeholder still showing (and
  // re-listable) after the delete. Re-pushes the trimmed index to the worker.
  function forgetFromStateAndIndex(rel) {
    const lk = String(rel).toLowerCase();
    const st = syncState(); let sChanged = false;
    for (const k of Object.keys(st)) { const kk = k.toLowerCase(); if (kk === lk || kk.startsWith(lk + '/')) { delete st[k]; sChanged = true; } }
    if (sChanged) setSyncState(st);
    const idx = cloudIndex(); let iChanged = false;
    for (const k of Object.keys(idx)) { const kk = k.toLowerCase(); if (kk === lk || kk.startsWith(lk + '/')) { delete idx[k]; iChanged = true; } }
    if (iChanged) { setCloudIndex(idx); pushDbxIndexToSW(); }
  }
  function onFileDeleted(path) {
    const rel = String(path).replace(/^\/+/, '');
    forgetFromStateAndIndex(rel);
    if (tokens()) del(relToCloud(rel)).catch(() => {});
  }
  function pushDbxTokenToSW() {
    const worker = window._sandpieWorker;
    if (!worker) {
      // Worker initialised by conversations.js which loads after this module.
      setTimeout(pushDbxTokenToSW, 1000);
      return;
    }
    const t = tokens();
    if (!t) return;
    // pathRoot is now TEAM-ONLY: the worker uses it for cloud browse/search (so the
    // model can still see /R+D+I), never for workspace paths. The workspace lives in
    // the home namespace, i.e. NO header — see _dbxHeaders() in sandpie-worker.js.
    worker.postMessage({
      type: 'dbx-token',
      token: t.access_token,
      pathRoot: null,                                    // workspace ops: home namespace
      teamRoot: localStorage.getItem(NS_KEY) || null,    // cloud browse/search: team namespace
      homeNs: localStorage.getItem(HOMENS_KEY) || '',    // for cross-namespace copy_to_workspace
      workingRoot: localStorage.getItem(ROOT_KEY) || '',
      dehydrated: dehydrated(),
    });
  }
  // Push the cloud INDEX to the worker so dehydrated mode can list/hydrate from
  // it. index:null clears it (mode off) → worker falls back to OPFS-only.
  function pushDbxIndexToSW() {
    const worker = window._sandpieWorker;
    if (!worker) { setTimeout(pushDbxIndexToSW, 1000); return; }
    worker.postMessage({ type: 'dbx-index', index: dehydrated() ? cloudIndex() : null, exempt: EXEMPT_PREFIXES });
  }
  function wireServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    pushDbxTokenToSW();
    pushDbxIndexToSW();
    navigator.serviceWorker.addEventListener('message', (ev) => {
      const d = ev.data; if (!d) return;
      if (d.type === 'opfs-deleted-by-python' && Array.isArray(d.paths)) {
        (async () => { if (!tokens()) return; for (const p of d.paths) { try { await del(relToCloud(p)); } catch {} } })();
        for (const p of d.paths) forgetFromStateAndIndex(p);
        return;
      }
      if (d.type === 'sw-opfs-changed' && Array.isArray(d.paths)) {
        const st = syncState(); let changed = false;
        for (const p of d.paths) { if (!st[p]) st[p] = { rev: '', size: 0, syncedMtime: 0 }; else st[p].syncedMtime = 0; changed = true; }
        if (changed) setSyncState(st);
        return;
      }
      // The worker fetched (hydrated) cloud files into OPFS. Record them as clean
      // synced copies so they aren't re-uploaded, but ARE flushed on next boot and
      // — if later edited — become dirty and write back. (Read-only hydration for
      // run_python stays in MEMFS and is not reported here.)
      if (d.type === 'worker-hydrated' && Array.isArray(d.paths)) {
        (async () => {
          const st = syncState(); const idx = cloudIndex(); let changed = false;
          for (const p of d.paths) {
            const e = idx[p]; if (!e) continue;
            st[p] = { rev: e.rev || '', size: e.size || 0, syncedMtime: await Sandpie.opfsMtime(p) };
            changed = true;
          }
          if (changed) setSyncState(st);
        })();
        return;
      }
    });
  }

  // ===========================================================================
  //  OAuth
  // ===========================================================================
  // A managed deployment (sandpie-server) can provide the company Dropbox app
  // key via GET /config, so the panel pre-fills it and "Connect" is one click.
  // The key is a PUBLIC PKCE client_id, not a secret. null = not fetched yet;
  // '' = no server / unset → fall back to the user-entered or saved key. Cached.
  let _serverAppKey = null;
  let _serverParent = null;
  // Fetch GET /config once and cache what the deployment provides: the Dropbox
  // app key AND the default sync parent (see app.js). Both non-secret. Lets the
  // panel one-click connect and inherit the org sync root instead of hardcoding it.
  async function loadServerConfig() {
    if (_serverAppKey !== null) return;
    try {
      const res = await fetch('/config', { headers: { Accept: 'application/json' } });
      const cfg = res.ok ? ((await res.json()) || {}) : {};
      _serverAppKey = cfg.dropboxAppKey || '';
      _serverParent = cfg.dropboxParent || '';
    } catch { _serverAppKey = ''; _serverParent = ''; }
  }
  async function serverAppKey() { await loadServerConfig(); return _serverAppKey; }
  async function serverParent() { await loadServerConfig(); return _serverParent; }
  function saveConfig() {
    const el = document.getElementById('dbxfullAppKey');
    if (el) localStorage.setItem(APPKEY_CFG, el.value || '');
  }
  function toggleConnection() { if (tokens()) disconnect(); else connect(); }
  async function connect() {
    localStorage.removeItem(AUTOCONN_OPTOUT);     // a (re)connect cancels any prior opt-out
    let appKey = (document.getElementById('dbxfullAppKey')?.value || '').trim();
    if (!appKey) appKey = await serverAppKey();   // managed deployment provides it
    if (!appKey) { dbxStatus('Enter your full-access Dropbox app key first', 'error'); return; }
    saveConfig();
    const { verifier, challenge } = await pkceChallenge();
    localStorage.setItem(PKCE_KEY, JSON.stringify({ verifier, app_key: appKey, ts: Date.now() }));
    const params = new URLSearchParams({
      client_id: appKey, response_type: 'code', redirect_uri: DBX_REDIRECT,
      code_challenge: challenge, code_challenge_method: 'S256', token_access_type: 'offline',
    });
    location.href = 'https://www.dropbox.com/oauth2/authorize?' + params.toString();
  }
  function disconnect() {
    // Explicit disconnect opts out of auto-connect (see maybeAutoConnect) so a
    // managed-login user who disconnects isn't silently reconnected on reload.
    localStorage.setItem(AUTOCONN_OPTOUT, '1');
    // Keep WSROOT_KEY / TEAMPARENT_KEY / PARENT_KEY + APPKEY_CFG so a reconnect
    // reuses the configured folders and key (PARENT_KEY also still locates the
    // legacy team workspace if the import hasn't happened yet).
    // Drop the local sync state (stale once disconnected; re-pulled on reconnect).
    [TOKENS_KEY, STATE_KEY, INDEX_KEY, CURSOR_KEY, ROOT_KEY, NS_KEY, HOMENS_KEY, NS_VER_KEY, EMAIL_KEY, SIG_KEY, PENDING_KEY].forEach(k => localStorage.removeItem(k));
    dbxStatus('Not connected', 'disconnected');
    Sandpie.refreshFiles();
  }
  // Auto-connect for managed (server-login) deployments. Triggered by the
  // 'account:signedin' bus event (account.js): if the user signed in through the
  // server, isn't already connected, hasn't explicitly disconnected, and the
  // deployment provides a Dropbox app key (GET /config), start the OAuth flow
  // automatically — seamless when Dropbox is federated to the same IdP. The
  // per-session AUTOCONN_TRIED guard stops a cancelled/failed bounce from looping.
  async function maybeAutoConnect() {
    if (tokens()) return;                                 // already connected
    if (localStorage.getItem(AUTOCONN_OPTOUT)) return;    // user opted out via Disconnect
    if (sessionStorage.getItem(AUTOCONN_TRIED)) return;   // already tried this session
    const key = await serverAppKey();
    if (!key) return;                                     // no managed app key → nothing to do
    sessionStorage.setItem(AUTOCONN_TRIED, '1');
    connect();                                            // → Dropbox OAuth
  }
  async function exchangeCode(code) {
    const stashed = JSON.parse(localStorage.getItem(PKCE_KEY) || 'null');
    if (!stashed) throw new Error('Missing PKCE state');
    if (Date.now() - stashed.ts > 10 * 60 * 1000) { localStorage.removeItem(PKCE_KEY); throw new Error('PKCE expired — reconnect'); }
    const body = new URLSearchParams({
      code, grant_type: 'authorization_code', client_id: stashed.app_key,
      code_verifier: stashed.verifier, redirect_uri: DBX_REDIRECT,
    });
    const res = await fetch(dbxRoute('https://api.dropboxapi.com/oauth2/token'), {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body.toString(),
    });
    if (!res.ok) throw new Error('Code exchange failed: ' + await res.text());
    const data = await res.json();
    localStorage.setItem(TOKENS_KEY, JSON.stringify({
      access_token: data.access_token, refresh_token: data.refresh_token,
      expires_at: Date.now() + data.expires_in * 1000, app_key: stashed.app_key,
    }));
    localStorage.removeItem(PKCE_KEY);
  }

  // ===========================================================================
  //  Sidebar "Cloud sync" section + status
  // ===========================================================================
  // Connection-state UI. dbxStatus()/setBusy() just record the latest message +
  // busy count; renderCloudState() paints the panel from the single source of
  // truth — tokens() (connected?), _busy (syncing?), _lastErr — so the panel is
  // correct whenever it (re)renders, not only when an event fires. The previous
  // bug: wireCloudPanel never repainted, so the button was frozen at "Connect".
  // Safe when the panel isn't mounted — every element lookup is guarded.
  let _busy = 0;
  let _lastMsg = '';
  let _lastErr = false;
  function dbxStatus(text, kind) {
    _lastErr = kind === 'error';
    _lastMsg = text || '';   // e.g. "Mirroring …"; '' falls back to "Connected"
    renderCloudState();
  }
  function setBusy(b) {
    _busy = Math.max(0, _busy + (b ? 1 : -1));
    renderCloudState();
  }
  function renderCloudState() {
    const connected = !!tokens();
    const dot  = document.getElementById('dbxfullDot');
    const text = document.getElementById('dbxfullStatusText');
    const acct = document.getElementById('dbxfullAccount');
    const btn  = document.getElementById('dbxfullToggleBtn');
    const root = document.getElementById('dbxfullRoot');
    const key  = document.getElementById('dbxfullAppKey');
    let color, label, pulse = false;
    if (_lastErr)       { color = 'var(--sp-danger)';   label = _lastMsg || 'Error'; }
    else if (_busy)     { color = 'var(--sp-warn)';     label = 'Syncing…'; pulse = true; }
    else if (connected) { color = 'var(--sp-success)';  label = _lastMsg || 'Connected'; }
    else                { color = 'var(--sp-text-dim)'; label = 'Not connected'; }
    if (dot)  { dot.style.background = color; dot.style.animation = pulse ? 'sync-pulse 1s ease-in-out infinite' : 'none'; }
    if (text) { text.textContent = label; text.title = label; text.style.color = _lastErr ? 'var(--sp-danger)' : 'var(--sp-text)'; }
    if (acct) { acct.textContent = connected ? (localStorage.getItem(EMAIL_KEY) || '') : ''; }
    if (btn)  { btn.textContent = connected ? 'Disconnect' : 'Connect'; }
    if (key)  { key.style.display = connected ? 'none' : ''; }   // app key only matters before connecting
    if (root) {
      const tp = teamParent();
      root.textContent = connected
        ? (workingRoot()
            ? ('Syncing to ' + workingRoot() + ' in your own Dropbox' + (tp ? ' · sharing via ' + tp : ''))
            : 'Resolving folder…')
        : 'Syncs to a folder in your own Dropbox — nobody else on the team can see it.';
    }
  }
  const CLOUD_HTML = `
        <div style="display:flex; align-items:center; gap:0.45rem; padding:0.4rem 0.55rem; margin-bottom:0.6rem; border:1px solid var(--sp-border); border-radius:6px; background:var(--sp-panel);">
          <span id="dbxfullDot" style="width:9px; height:9px; border-radius:50%; flex:none; background:var(--sp-text-dim);"></span>
          <span id="dbxfullStatusText" style="font-size:0.8rem; font-weight:500; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">Not connected</span>
          <span id="dbxfullAccount" style="font-size:0.7rem; color:var(--sp-text-dim); margin-left:auto; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:55%;"></span>
        </div>
        <input id="dbxfullAppKey" autocomplete="off" placeholder="Dropbox app key (Full Dropbox access)" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
        <label style="display:block; font-size:0.7rem; color:var(--sp-text-dim); margin:0 0 0.25rem 0.1rem;">Sync folder (in your own Dropbox)</label>
        <input id="dbxfullWsRoot" autocomplete="off" placeholder="${DEFAULT_WSROOT}" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
        <label style="display:block; font-size:0.7rem; color:var(--sp-text-dim); margin:0 0 0.25rem 0.1rem;">Team shared folder (sharing only)</label>
        <input id="dbxfullTeamParent" autocomplete="off" placeholder="${DEFAULT_TEAM_PARENT}" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
        <button class="ghost" id="dbxfullToggleBtn" style="width:100%;">Connect</button>
        <div id="dbxfullRoot" style="font-size:0.65rem; color:var(--sp-text-dim); margin-top:0.4rem;"></div>

      `;
  function wireCloudPanel(body) {
    const input = body.querySelector('#dbxfullAppKey');
    if (input) {
      input.addEventListener('input', saveConfig);
      const existing = tokens()?.app_key || localStorage.getItem(APPKEY_CFG) || '';
      input.value = existing;
      // No key of their own → pre-fill the deployment's company key (if any) so
      // Connect is one click. Async; only fill if the user hasn't typed since.
      if (!existing) serverAppKey().then(k => { if (k && !input.value) input.value = k; });
    }
    const wsRoot = body.querySelector('#dbxfullWsRoot');
    if (wsRoot) {
      wsRoot.value = localStorage.getItem(WSROOT_KEY) || DEFAULT_WSROOT;
      // Commit on blur/Enter (not each keystroke) so a half-typed path never syncs.
      // ensureWorkingRoot() picks the new value up on the next cycle; the changed
      // target signature resets sync state there, so nothing is deleted remotely.
      wsRoot.addEventListener('change', () => {
        localStorage.setItem(WSROOT_KEY, normPath(wsRoot.value, DEFAULT_WSROOT));
        ensureWorkingRoot().catch(() => {}).then(renderCloudState);
      });
    }
    const teamP = body.querySelector('#dbxfullTeamParent');
    if (teamP) {
      teamP.value = localStorage.getItem(TEAMPARENT_KEY) || localStorage.getItem(TEAMPARENT_RES) || DEFAULT_TEAM_PARENT;
      teamP.addEventListener('change', () => {
        localStorage.setItem(TEAMPARENT_KEY, normPath(teamP.value, DEFAULT_TEAM_PARENT));
        renderCloudState();
      });
    }
    body.querySelector('#dbxfullToggleBtn')?.addEventListener('click', toggleConnection);
    renderCloudState();   // paint the live connection state on (re)render — the fix
  }
  // Prefer the gear modal (SandpieSettings); fall back to the sidebar. The
  // Dropbox token + app key stay in localStorage (secrets are never synced).
  function addSection() {
    if (window.SandpieSettings) {
      SandpieSettings.register({ id: 'cloud', title: 'Cloud sync', order: 40, render(panel) { panel.innerHTML = CLOUD_HTML; wireCloudPanel(panel); } });
      return;
    }
    Sandpie.menu.add('cloudSection', { title: 'Cloud sync', html: CLOUD_HTML, onRender: wireCloudPanel });
  }

  // ===========================================================================
  //  ⚠️  ONE-TIME MIGRATION — team workspace → personal (home-namespace) workspace.
  //
  //  Old:  <teamParent>/<email-local>/…   e.g. /R+D+I/sandpie/ezequiel/…  (team path-root)
  //  New:  /sandpie/…                     in the user's own Dropbox      (home namespace)
  //
  //  Guarded (skips once the new root exists / once the guard key is set),
  //  NON-DESTRUCTIVE (copies — the old team folder is left completely untouched,
  //  so a rollback is just flipping the root back), and best-effort: any failure
  //  is logged and retried next boot rather than blocking sync.
  //
  //  Two strategies, in order:
  //    1. Server-side folder copy. The two roots live in DIFFERENT namespaces, so
  //       the destination is written as a namespace-relative path
  //       ("ns:<home_namespace_id>/sandpie") while the request carries the team
  //       path-root. One call, no bytes through the browser.
  //    2. Fallback — pull-then-push. List the old folder, download every file into
  //       OPFS, and let the normal dirty-push upload it to the new root. Slower and
  //       it pulls everything local for one boot (dehydratePurge trims it later),
  //       but it only uses transport paths that are already proven in daily sync.
  //
  //  TO REMOVE LATER (once every user has migrated): delete this block, the
  //  maybeMigrateToHome() calls in boot(), PARENT_KEY, and legacyTeamRoot().
  //  Grep token: MIGRATE_TO_HOME
  // ===========================================================================
  const MIGRATE_TO_HOME  = true;                        // master switch
  const MIGRATED_KEY     = 'dbxfull-home-migrated-v1';  // set once the import is settled
  let _migrationChecked  = false;
  // Strategy 1: one server-side copy_v2. `to` may be an "ns:<id>/…" path so the
  // copy can cross from the team namespace into the user's home namespace.
  async function copyAcrossNamespaces(from, to, team) {
    await api('/2/files/copy_v2', { from_path: from, to_path: to, autorename: false }, { team });
  }
  // Strategy 2: download the old workspace into OPFS. The sync-state reset that
  // ensureWorkingRoot() already performed on the root change means every local
  // file counts as dirty, so the next sync() pushes all of this to the new root.
  // Never overwrites a local file that already exists — local wins, so nothing the
  // user has since edited on this device is clobbered by a stale cloud copy.
  async function pullOldWorkspace(oldRoot, team) {
    const opfs = Sandpie.opfs;
    const { entries } = await listFolder(oldRoot, { recursive: true, team });
    const prefix = oldRoot.replace(/^\/+/, '').toLowerCase() + '/';
    const files = [];
    for (const e of entries) {
      if (e.kind !== 'file' || !e.path) continue;
      const s = String(e.path).replace(/^\/+/, '');
      if (!s.toLowerCase().startsWith(prefix)) continue;
      files.push({ rel: s.slice(prefix.length), path: e.path });
    }
    if (!files.length) return 0;
    let i = 0, done = 0, failed = 0;
    const worker = async () => {
      while (i < files.length) {
        const f = files[i++];
        try {
          if (!(await opfs.exists(f.rel))) {
            await opfs.write(f.rel, await download(f.path, undefined, { team }));
          }
          onFileChanged(f.rel);   // mark dirty ⇒ next sync uploads it to the new root
        } catch (err) { failed++; console.warn('[migrate:home] pull failed:', f.rel, err && err.message); }
        try { _setSyncProgress(++done, files.length, 'Moving your files'); } catch (_) {}
      }
    };
    await Promise.all(Array.from({ length: Math.min(DL_CONCURRENCY, files.length) }, worker));
    try { _setSyncProgress(0, 0); } catch (_) {}
    if (failed) throw new Error(failed + ' of ' + files.length + ' files could not be pulled');
    return files.length;
  }
  async function maybeMigrateToHome() {
    if (!MIGRATE_TO_HOME || _migrationChecked) return;
    if (localStorage.getItem(MIGRATED_KEY) === '1') return;
    if (!tokens()) return;
    _migrationChecked = true;
    const newRoot = workingRoot();
    if (!newRoot) { _migrationChecked = false; return; }   // root unresolved → retry next boot
    try {
      // Already have a personal workspace? Then either we've migrated before or the
      // user started fresh here — either way, importing on top would collide.
      if (await dbxMeta(newRoot, false)) {
        console.info('[migrate:home]', newRoot, 'already exists — nothing to import');
        localStorage.setItem(MIGRATED_KEY, '1');
        return;
      }
      const teamNs = localStorage.getItem(NS_KEY) || '';
      const oldRoot = legacyTeamRoot();
      if (!oldRoot || !(await dbxMeta(oldRoot, !!teamNs))) {
        console.info('[migrate:home] no old workspace at', oldRoot || '(unknown)', '— nothing to import');
        localStorage.setItem(MIGRATED_KEY, '1');
        return;
      }
      // 1) server-side copy (cross-namespace via ns: when there's a team space)
      const homeNs = localStorage.getItem(HOMENS_KEY) || '';
      const dest = (teamNs && homeNs) ? ('ns:' + homeNs + newRoot) : newRoot;
      try {
        await copyAcrossNamespaces(oldRoot, dest, !!teamNs);
        console.info('[migrate:home] server-side copied', oldRoot, '→', dest);
        localStorage.setItem(MIGRATED_KEY, '1');
        // The copy landed outside anything the local sync state knows about; drop
        // it so the next sync does a clean full listing of the new root.
        localStorage.removeItem(STATE_KEY); localStorage.removeItem(INDEX_KEY);
        localStorage.removeItem(CURSOR_KEY); localStorage.removeItem(PENDING_KEY);
        return;
      } catch (e) {
        console.warn('[migrate:home] server-side copy unavailable (' + (e && e.message) + ') — falling back to download+re-upload');
      }
      // 2) pull-then-push
      dbxStatus('Moving your files to your own Dropbox…', '');
      const n = await pullOldWorkspace(oldRoot, !!teamNs);
      console.info('[migrate:home] pulled', n, 'file(s) from', oldRoot, '— sync will push them to', newRoot);
      localStorage.setItem(MIGRATED_KEY, '1');
      dbxStatus('', 'connected');
      try { await Sandpie.refreshFiles(); await Sandpie.refreshConversations(); } catch (_) {}
    } catch (e) {
      // Leave the guard UNSET so the next boot retries. The old folder is untouched.
      _migrationChecked = false;
      console.warn('[migrate:home] failed (non-fatal, will retry):', e && e.message);
    }
  }

  // ===========================================================================
  //  Dropbox sharing API — 1:1 delivery addressed by EMAIL, no team folder
  // ===========================================================================
  // The old 1:1 path needed a folder both people could already reach. This one
  // doesn't: the sender shares a folder out of their OWN Dropbox and invites an
  // email address; the recipient discovers the invite through the API. Nothing is
  // pre-arranged, so it reaches anyone the corp's Dropbox sharing policy allows.
  //
  // The recipient does NOT mount anything. A shared folder is a namespace
  // (`alias SharedFolderId = NamespaceId`), so we read it in place with
  // Dropbox-API-Path-Root {".tag":"namespace_id"} — membership is the only gate.
  // Nothing appears in the recipient's Dropbox: no "Sandpie from bob" folder
  // cluttering their root, nothing to clean up after accept or decline. The
  // accepted package is COPIED into their own workspace (sandpie/shared-installed),
  // which is the only copy they actually use.
  // mount_folder survives only as a fallback for accounts where namespace reads
  // are refused (PathRootError.no_permission) — see sharing.js.
  //
  // Layout, all in the SENDER's home namespace (deliberately outside /sandpie, so
  // the sync engine never sees it):
  //   /Sandpie Shares/<recipient-local>/Sandpie from <sender-local>/   ← the SHARED folder
  //       packages/<id>/manifest.json + files…
  // The recipient segment keeps one outbox per recipient (so two recipients never
  // collide); the leaf carries the SENDER's name because the leaf is what shows up
  // in the recipient's Dropbox once mounted.
  //
  // ONE outbox per (sender, recipient) pair, created once and reused for every
  // later delivery — sharing per-package would mint a fresh Dropbox namespace and
  // a fresh mount on their side for every artifact.
  //
  // Recipients are invited as VIEWER: a delivery must not give someone write
  // access to the sender's Dropbox. That means the recipient cannot delete a
  // consumed package, so accept/dismiss state lives in their own shares.json
  // (keyed id@rev, so a re-share bumps rev and re-notifies) — see sharing.js.
  //
  // Requires the sharing.read + sharing.write scopes on the Dropbox app. A token
  // minted before those were granted fails with missing_scope; that's surfaced as
  // a reconnect prompt rather than a raw API error.
  const OUTBOX_PARENT     = '/Sandpie Shares';
  const SHARE_NAME_PREFIX = 'Sandpie from ';        // recipient-side folder name + the discovery filter
  const OUTBOX_CACHE      = 'dbxfull-share-outbox'; // {recipientLocal: {path, id, email}}
  function isShareFolderName(n) { return String(n || '').toLowerCase().startsWith(SHARE_NAME_PREFIX.toLowerCase()); }
  async function shareApi(path, body) {
    try { return await api(path, body); }
    catch (e) {
      if (/missing_scope|insufficient_scope/i.test(String((e && e.message) || e))) {
        throw new Error('Dropbox sharing permission is missing for this login — reconnect Dropbox (Settings → Cloud sync → Disconnect, then Connect) to grant it.');
      }
      throw e;
    }
  }
  function myLocalPart() { return sanitizeSeg(String(localStorage.getItem(EMAIL_KEY) || 'me').split('@')[0]).toLowerCase(); }
  // Idempotent: the shared_folder_id for `path`, sharing the folder if it isn't
  // already shared. share_folder can go async on a big folder, so poll for it.
  async function shareFolderId(path) {
    const md = await dbxMeta(path, false);
    const existing = md && md.sharing_info && md.sharing_info.shared_folder_id;
    if (existing) return existing;
    let res = await shareApi('/2/sharing/share_folder', { path, acl_update_policy: 'owner', force_async: false });
    if (res['.tag'] === 'async_job_id') {
      const jobId = res.async_job_id;
      res = null;
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const st = await shareApi('/2/sharing/check_share_job_status', { async_job_id: jobId });
        if (st['.tag'] === 'in_progress') continue;
        if (st['.tag'] === 'failed') throw new Error('share_folder failed: ' + JSON.stringify(st).slice(0, 200));
        res = st;   // 'complete' → the ShareFolderMetadata, flattened
        break;
      }
      if (!res) throw new Error('share_folder is still running — try sharing again in a moment.');
    }
    const id = res.shared_folder_id || '';
    if (!id) throw new Error('share_folder did not return a shared_folder_id');
    return id;
  }
  // Ensure (and cache) the outbox shared with `email`. Safe to call on every publish.
  async function ensureOutbox(email) {
    const to = sanitizeSeg(String(email).split('@')[0]).toLowerCase();
    const path = OUTBOX_PARENT + '/' + to + '/' + SHARE_NAME_PREFIX + myLocalPart();
    let cache = {}; try { cache = JSON.parse(localStorage.getItem(OUTBOX_CACHE) || '{}'); } catch (_) {}
    if (cache[to] && cache[to].path === path && cache[to].id) return cache[to];
    await mkdirp(OUTBOX_PARENT);
    await mkdirp(OUTBOX_PARENT + '/' + to);
    await mkdirp(path);
    const id = await shareFolderId(path);
    try {
      await shareApi('/2/sharing/add_folder_member', {
        shared_folder_id: id,
        members: [{ member: { '.tag': 'email', email: String(email) }, access_level: { '.tag': 'viewer' } }],
        quiet: true,   // no Dropbox notification email — the app is the notification
      });
    } catch (e) {
      // Re-inviting someone already on the folder is the normal steady state.
      if (!/already_a_member|already_invited/i.test(String((e && e.message) || e))) throw e;
    }
    cache[to] = { path, id, email: String(email) };
    localStorage.setItem(OUTBOX_CACHE, JSON.stringify(cache));
    return cache[to];
  }
  // Every Sandpie share folder this account is a member of, mounted or not — we
  // read them all by namespace, so `path` (the mount point, '' when unmounted) is
  // informational rather than a gate.
  async function listIncomingShares() {
    const out = [];
    let data = await shareApi('/2/sharing/list_folders', { limit: 100 });
    for (let guard = 0; guard < 50; guard++) {
      for (const e of (data.entries || [])) {
        if (!isShareFolderName(e.name)) continue;
        out.push({
          id: e.shared_folder_id,
          name: e.name,
          from: e.name.slice(SHARE_NAME_PREFIX.length) || ((e.owner_display_names || [])[0] || ''),
          owner: (e.owner_display_names || [])[0] || '',
          path: e.path_lower || '',
        });
      }
      if (!data.cursor) break;
      data = await shareApi('/2/sharing/list_folders/continue', { cursor: data.cursor });
    }
    return out;
  }
  async function mountShare(sharedFolderId) {
    const md = await shareApi('/2/sharing/mount_folder', { shared_folder_id: sharedFolderId });
    return md.path_lower || '';
  }
  async function declineShare(sharedFolderId) {
    await shareApi('/2/sharing/relinquish_folder_membership', { shared_folder_id: sharedFolderId, leave_a_copy: false });
  }

  // ===========================================================================
  //  Boot
  // ===========================================================================
  function boot() {
    addSection();
    Sandpie.registerSyncProvider({
      sync, fileStatus, getState: syncState,
      isConnected: () => !!tokens(),
      // Absolute Dropbox path of the synced workspace (/sandpie, home namespace).
      // Lets the search tool tell the model where it is, so it can scope a cloud
      // search to the team shared folder instead of guessing.
      workingRoot: () => (localStorage.getItem(ROOT_KEY) || '').replace(/\/+$/, ''),
      teamParent: () => teamParent(),
      get initialSyncDone() { return initialSyncDone; },
      // Dehydrated-mode hooks: let the file browser show the full Dropbox tree
      // (what the LLM sees) as cloud placeholders and fetch one on demand when
      // opened. hydrate() uses download() → opfs.write — the same read-only path
      // as bulk sync; it never emits file:deleted, so nothing is deleted remotely.
      isDehydrated: () => dehydrated(),
      cloudIndex: () => (dehydrated() ? cloudIndex() : null),
      isExempt: (rel) => isExemptRel(rel),
      hydrate: async (rel) => {
        const r = String(rel).replace(/^\/+/, '');
        if (!dehydrated() || isExemptRel(r)) return false;
        const e = cloudIndex()[r];
        if (!e || e.kind !== 'file') return false;
        if (await Sandpie.opfs.exists(r)) return true;
        const bytes = await download(e.path || relToCloud(r));
        await Sandpie.opfs.write(r, bytes);
        // Record as a clean synced copy (same as worker-hydrated) so it's flushed
        // on next boot and writes back if edited.
        try { const st = syncState(); st[r] = { rev: e.rev || '', size: e.size || 0, syncedMtime: await Sandpie.opfsMtime(r) }; setSyncState(st); } catch (_) {}
        return true;
      },
      // --- Sharing transport (sharing.js) -----------------------------------
      // Read/write arbitrary paths OUTSIDE the per-user workspace, using the same
      // authed API. `team: true` (the default for these, since sharing is
      // team-scoped) resolves the path against the TEAM root namespace via the
      // path-root header — the personal workspace no longer lives there, so the
      // sharing hub is the only thing that still uses it.
      // cloudParent() = the team shared area (e.g. /R+D+I/sandpie); '' on a
      // non-team account, which makes sharing.js fall back to its local hub.
      // Each takes {team} (team-space root) or {ns} (an arbitrary namespace, e.g. a
      // shared_folder_id — reads someone's shared folder without mounting it).
      cloudConnected: () => !!tokens(),
      cloudParent: () => teamParent(),
      async cloudUpload(absPath, bytes, { team = true, ns = '' } = {}) {
        const token = await accessToken();
        const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/upload'), {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream',
                     'Dropbox-API-Arg': apiArg({ path: absPath, mode: 'overwrite', mute: true, autorename: false }),
                     ...pathRootHeader({ team, ns }) },
          body: bytes,
        });
        if (!res.ok) throw new Error('cloudUpload ' + absPath + ': ' + res.status + ' ' + (await res.text()).slice(0, 200));
        return await res.json();
      },
      cloudDownload: (absPath, { team = true, ns = '' } = {}) => download(absPath, undefined, { team, ns }),
      cloudDelete: (absPath, { team = true, ns = '' } = {}) => del(absPath, { team, ns }),   // delete_v2 (recursive for folders); no-op on not_found
      async cloudList(absPath, recursive = false, { team = true, ns = '' } = {}) {
        try { return (await listFolder(absPath, { recursive, team, ns })).entries; }
        catch (e) { if (String((e && e.message) || e).includes('not_found')) return []; throw e; }
      },
      // Workspace-scoped variants (home namespace) — used by sharing.js to clean up
      // its own copies inside the user's workspace, which is NOT in the team root.
      workspaceDelete: (absPath) => del(absPath, { team: false }),
      // --- 1:1 delivery by email (Dropbox sharing API; no team folder) --------
      // The Dropbox account's own email — the authoritative sender identity for a
      // share, independent of whatever account.js reports.
      accountEmail: () => localStorage.getItem(EMAIL_KEY) || '',
      shareEnsureOutbox: (email) => ensureOutbox(email),   // → {path, id, email}; idempotent
      shareListIncoming: () => listIncomingShares(),        // path:'' ⇒ pending (unmounted)
      shareMount: (id) => mountShare(id),                   // accept → returns the mount path
      shareDecline: (id) => declineShare(id),               // decline / leave
    });
    Sandpie.events.on('file:deleted', onFileDeleted);
    Sandpie.events.on('file:changed', onFileChanged);
    Sandpie.events.on('account:signedin', maybeAutoConnect);   // managed login → auto-connect Dropbox
    wireServiceWorker();
    setInterval(() => { if (!document.hidden) sync(); }, 60000);

    const code = new URLSearchParams(location.search).get('code');
    if (code) {
      exchangeCode(code).then(async () => {
        history.replaceState({}, '', location.pathname);
        await ensureWorkingRoot();
        await maybeMigrateToHome();   // MIGRATE_TO_HOME (temporary) — must precede the first sync
        dbxStatus('', 'connected');
        await cleanupStaleArtifacts();
        await migrateExemptToSandpie();
        sync();
      }).catch(e => dbxStatus('Auth failed: ' + e.message, 'error'));
    } else if (tokens()) {
      (async () => {
        try { await ensureWorkingRoot(); await maybeMigrateToHome(); }   // MIGRATE_TO_HOME (temporary)
        catch (e) { console.warn('[dropbox] pre-sync:', e && e.message); }
        dbxStatus('', 'connected');
        await cleanupStaleArtifacts();
        await migrateExemptToSandpie();
        // On-demand mode is now default; ephemeral purge happens in sync cycle
        sync();
      })();
    } else {
      migrateExemptToSandpie().catch(() => {});   // offline: local-only move under sandpie/
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
