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
  // ---- FIXED LAYOUT. Deliberately not configurable ------------------------
  // Both roots are part of the org's agreed structure, not a per-user preference:
  // a workspace somewhere unexpected is invisible to nobody but its owner, and a
  // mistyped team root silently detaches someone from every department hub. Change
  // them here, not in the UI.
  const DEFAULT_WSROOT = '/sandpie';            // personal workspace, in the user's own Dropbox
  const DEFAULT_TEAM_PARENT = '/IA';            // team-folders root; one folder per department (IA/R+D+I, …)
  const LEGACY_TEAM_PARENT = '/R+D+I/sandpie';  // where workspaces lived before the move to personal folders
  const HUB_DIR = 'shared-hub';                 // per-department hub dir name (lowercase; must match sharing.js)
  const MAX_TEAM_FOLDERS = 50;                  // sanity bound on a misconfigured team root
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
  const LAST_SYNC_KEY = 'dbxfull-last-sync-ts';   // Date.now() after each successful sync (device-switch detection)
  const EXEMPT_PREFIXES = ['sandpie/conversations', 'sandpie/skills', 'sandpie/memory', 'sandpie/config', 'sandpie/shared-installed', 'sandpie/shared-incoming'];   // app metadata: always eagerly synced + never dehydrate-purged. memory MUST be exempt: it's injected into every system prompt page-side (memory.js list()/systemBlock read local OPFS directly, NOT via the worker's lazy hydration), so purging it locally silently breaks recall. sandpie/config holds pins.json (read page-side at boot by pins.js — same reason). (sandpie/scripts, sandpie/artifacts stay dehydratable.)
  // The personal workspace sync must NOT mirror the hub-managed subtree: every
  // device installs it from the TEAM hub (sharing.js), and a second authority
  // here — pushing/pulling the user's own mirror of it — resurrected
  // uninstalled artifacts and ping-ponged copies between devices. Still listed
  // in EXEMPT_PREFIXES (never dehydrate-purged); just invisible to push, pull,
  // cleanup passes and the file:changed/file:deleted reactions.
  const NOSYNC_PREFIX = 'sandpie/shared-installed';
  const isNoSyncRel = (p) => { const r = String(p).replace(/^\/+/, ''); return r === NOSYNC_PREFIX || r.startsWith(NOSYNC_PREFIX + '/'); };
  // Paths this module is writing right now (downloads/hydration). opfs.write emits
  // file:changed for EVERY write, which is what finally makes user edits upload —
  // but our own downloads must not be mistaken for edits and pushed straight back.
  const _pulling = new Set();
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
  // sharingInfo carries no_access / traverse_only, which is how Dropbox tells us the
  // user can see a folder exists but isn't a member — the basis of the team picker.
  const mapEntry = e => ({ name: e.name, kind: e['.tag'], path: e.path_display || e.path_lower, size: e.size, rev: e.rev, hash: e.content_hash, cloudMtime: e.server_modified, sharingInfo: e.sharing_info || null });
  async function listFolder(folderPath, { recursive = false, team = false, ns = '' } = {}) {
    let data = await api('/2/files/list_folder', { path: folderPath === '/' ? '' : folderPath, recursive, include_deleted: true }, { team, ns });
    let entries = data.entries.slice();
    while (data.has_more) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }, { team, ns }); entries = entries.concat(data.entries); }
    return { entries: entries.map(mapEntry), cursor: data.cursor };
  }
  // Dropbox requires list_folder/continue to run under the SAME path-root as the
  // list_folder that minted the cursor — a team-hub cursor continued without the
  // header 409s (PathRootError) every time, silently degrading the hub sync to a
  // full listing on every poll. Default team:false = the home-namespace workspace
  // cursor, which is correct header-less.
  async function listContinue(cursor, { team = false, ns = '' } = {}) {
    let data = await api('/2/files/list_folder/continue', { cursor }, { team, ns });
    let entries = data.entries.slice();
    while (data.has_more) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }, { team, ns }); entries = entries.concat(data.entries); }
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
  // Creating a folder that already exists answers 409, which the browser logs as a
  // failed request even though we handle it — and on a re-share EVERY folder
  // already exists, so the console fills with alarming noise on a working path.
  // Ask first; only create when it is genuinely absent. Returns true if created.
  async function mkdirp(path) {
    if (await dbxMeta(path, false)) return false;
    try { await api('/2/files/create_folder_v2', { path, autorename: false }); return true; }
    catch (e) { if (/conflict/.test(String(e && e.message))) return false; throw e; }   // lost a race; fine
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
  function teamParent() { return DEFAULT_TEAM_PARENT; }
  // The department folders under the team root that THIS user can actually reach.
  // Dropbox already enforces cross-visibility: a department folder the user is not
  // a member of either doesn't come back at all, or comes back flagged no_access /
  // traverse_only. Filtering on those flags is what makes the share picker show
  // only the teams they're allowed to see, without us maintaining any list.
  //
  // The root may live in the team space (a team folder) or be a plain shared folder
  // mounted in the user's own Dropbox, so try the team path-root first and fall
  // back to the home namespace.
  async function listTeamFolders() {
    const root = teamParent();
    if (!root) return [];
    const read = async (team) => {
      try { return (await listFolder(root, { recursive: false, team })).entries; }
      catch (e) { if (/not_found|malformed_path|no_permission|path_root/i.test(String((e && e.message) || e))) return null; throw e; }
    };
    let entries = await read(true), team = true;
    if (entries === null) { entries = await read(false); team = false; }
    if (entries === null) return [];
    const out = entries
      .filter(e => e.kind === 'folder')
      // Never treat our own hub as a department. A root that already contains a
      // shared-hub (an older layout, or a root pointed one level too deep) would
      // otherwise yield <root>/shared-hub/shared-hub and a listing per pass for a
      // path that cannot exist.
      .filter(e => String(e.name || '').toLowerCase() !== HUB_DIR)
      .filter(e => { const si = e.sharingInfo || {}; return !si.no_access && !si.traverse_only; })
      .map(e => ({ name: e.name, path: e.path, team }))
      .sort((a, b) => a.name.localeCompare(b.name));
    // A correctly pointed root holds a handful of departments. Many more means it
    // is aimed at something else — every extra entry costs a listing per poll tick,
    // which is how the sharing calls get rate-limited out.
    if (out.length > MAX_TEAM_FOLDERS) {
      console.warn('[dropbox] team root ' + root + ' has ' + out.length + ' subfolders — is it pointing at the department root? Using the first ' + MAX_TEAM_FOLDERS + '.');
      return out.slice(0, MAX_TEAM_FOLDERS);
    }
    return out;
  }
  // Where this user's workspace USED to live: <old team parent>/<email-local>, under
  // the team path-root. Only used to locate data for the one-time import; '' if we
  // never knew the email (nothing to import from).
  function legacyTeamRoot() {
    const email = localStorage.getItem(EMAIL_KEY);
    if (!email) return '';
    const parent = normPath(localStorage.getItem(PARENT_KEY) || LEGACY_TEAM_PARENT, LEGACY_TEAM_PARENT);
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
    // Workspace = /sandpie in the user's own Dropbox. No <email> subfolder: the home
    // namespace is already per-user, and the path is fixed (see DEFAULT_WSROOT).
    const root = DEFAULT_WSROOT;
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
          _pulling.add(it.rel);                    // our own write — not a user edit
          try { await opfs.write(it.rel, bytes); } finally { _pulling.delete(it.rel); }
          const mtime = await Sandpie.opfsMtime(it.rel);
          state[it.rel] = { rev: it.e.rev, size: it.e.size, syncedMtime: mtime };
        } catch (err) { console.warn('[dropbox] download failed:', it.rel, err); }
        if (onProgress) { try { onProgress(++done, total); } catch (_) {} }
      }
    }
    await Promise.all(Array.from({ length: Math.min(DL_CONCURRENCY, items.length) }, worker));
  }

  // ---- device-switch splash screen (full-screen Globe) -----------------------
  // Shows a branded overlay when sync detects files changed on another device.
  // Hidden as soon as sync completes. Uses sandpie CSS vars for dark/light mode.
  let _splashActive = false;
  let _splashTotal = 0;

  function _showSyncSplash(totalFiles) {
    _splashActive = true;
    let splash = document.getElementById('deviceSyncSplash');
    if (!splash) {
      // Fallback only — normally the element is static in sandpie.html (first paint).
      splash = document.createElement('div');
      splash.id = 'deviceSyncSplash';
      splash.innerHTML =
        '<div class="splash-grid"></div>' +
        '<div class="splash-glow"></div>' +
        '<div class="splash-content">' +
          '<div class="splash-icon-ring">' +
            '<div class="ring-outer"></div>' +
            '<div class="ring-inner"></div>' +
            '<span class="ring-emoji"><svg class="ring-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" shape-rendering="geometricPrecision" text-rendering="geometricPrecision" fill="currentColor" stroke="currentColor"><g transform="translate(-44.341361-141.326128)"><ellipse rx="50" ry="50" transform="matrix(.112215 0 0 0.112215 66.181612 150.285667)" fill="currentColor" stroke="currentColor" stroke-width="0"></ellipse><ellipse rx="50" ry="50" transform="matrix(.112215 0 0 0.112215 51.960112 172.258787)" fill="currentColor" stroke="currentColor" stroke-width="0"></ellipse><line x1="-25" y1="0" x2="25" y2="0" transform="matrix(-.261472 0.406229 0.840873 0.541233 58.552318 162.138739)" fill="currentColor" stroke="currentColor"></line><line x1="-25" y1="0" x2="25" y2="0" transform="matrix(-.261472 0.406229 0.840873 0.541233 61.570862 162.138739)" fill="currentColor" stroke="currentColor"></line><line x1="-25" y1="0" x2="25" y2="0" transform="matrix(-.261472 0.406229 0.840873 0.541233 55.552318 162.138739)" fill="currentColor" stroke="currentColor"></line></g></svg></span>' +
          '</div>' +
          '<div class="splash-brand"><span class="bracket">[</span>sandpie<span class="bracket">]</span></div>' +
          '<div class="splash-tagline">Synchronizing</div>' +
          '<div class="splash-progress">' +
            '<div class="splash-progress-track"><div id="spProgFill" class="splash-progress-fill"></div></div>' +
            '<div id="spProgLabel" class="splash-progress-label"><span></span><span></span></div>' +
          '</div>' +
        '</div>';
      document.body.appendChild(splash);
    } else {
      // Static element already visible from first paint — reset any fade state.
      splash.style.opacity = '1';
      splash.style.transition = '';
    }
    _splashTotal = totalFiles;
    const fill = document.getElementById('spProgFill');
    const label = document.getElementById('spProgLabel');
    if (totalFiles > 0) {
      // Determinate: stop the pulse, width is driven by _updateSyncSplash.
      if (fill) { fill.classList.add('determinate'); fill.style.marginLeft = '0'; }
      _updateSyncSplash(0, totalFiles);
    } else {
      // Base state is the indeterminate pulse — just drop determinate.
      // Keep the label BLANK (the static markup's two empty spans) — no
      // "Syncing…" filler when there's nothing to download.
      if (fill) fill.classList.remove('determinate');
    }
  }

  function _updateSyncSplash(done, total) {
    const fill = document.getElementById('spProgFill');
    const label = document.getElementById('spProgLabel');
    if (!fill || !label || !total) return;
    fill.classList.add('determinate');
    fill.style.marginLeft = '0';
    const pct = Math.min(100, Math.round((done / total) * 100));
    fill.style.width = pct + '%';
    label.innerHTML = '<span>' + done + ' downloaded</span><span>' + (total - done) + ' remaining</span>';
  }

  // Lifting the splash right after the cursor check reveals the welcome with an
  // EMPTY sharedHome — sharing.js fills it asynchronously after Dropbox API calls.
  // Wait for sharing's first render so the home appears fully assembled. Timeout
  // guards against sharing.js being absent/erroring (never hang the splash).
  function _hideSyncSplashAfterHome(instant) {
    let hidden = false;
    const doHide = () => { if (hidden) return; hidden = true; _hideSyncSplash(instant); };
    if (!window.Sandpie || !Sandpie.events || !Sandpie.events.on) { doHide(); return; }
    let off = null;
    off = Sandpie.events.on('sharing:home-rendered', () => { try { if (off) off(); } catch (_) {} doHide(); });
    setTimeout(function() { try { if (off) off(); } catch (_) {} doHide(); }, 3000);
  }

  function _hideSyncSplash(instant) {
    _splashActive = false;
    const el = document.getElementById('deviceSyncSplash');
    if (!el) return;
    // Unconditional: the bar ALWAYS lands at 100% before any close (determinate
    // run, indeterminate dehydrated-only sync, no-delta flash, or error path).
    const fill = document.getElementById('spProgFill');
    const label = document.getElementById('spProgLabel');
    if (fill) {
      fill.classList.add('determinate');   // stop the pulse
      fill.style.marginLeft = '0';
      fill.style.width = '100%';
    }
    if (label) {
      label.innerHTML = _splashTotal > 0
        ? '<span>' + _splashTotal + ' downloaded</span><span>0 remaining</span>'
        : '<span>Synchronized</span><span></span>';
    }
    if (instant) { el.remove(); return; }
    el.style.opacity = '0'; el.style.transition = 'opacity .3s ease';
    setTimeout(function() { el.remove(); }, 350);
  }

  // ---- the sync engine (working dir only) ------------------------------------
  async function sync(opts = {}) {
    if (!tokens()) return;
    if (_syncing) return;
    if (Sandpie.isGenerating()) return;
    // Device-switch detection: if last sync was < 5 min ago, skip the splash
    // DISABLED after testing — splash now fires on any cursor delta.
    // const _lastSync = parseInt(localStorage.getItem(LAST_SYNC_KEY) || '0', 10);
    // const _isRecent = (Date.now() - _lastSync) < 300000;
    _syncing = true; setBusy(true); _syncCount++;
    const firstSync = !initialSyncDone;
    const opfs = Sandpie.opfs;
    const openFilePath = Sandpie.openFilePath();
    try {
      await ensureWorkingRoot();
      dbxStatus('', 'connected');
      const { index: cloud, delta, deletions } = await cloudListWorking();
      // Device-switch signal: the cursor reported changes (adds/changes OR
      // deletions). No stale-time gate — splash fires on ANY delta now.
      // (delta covers dehydrated files too — they still changed on another device.)
      const _deviceSwitch = !!((delta && delta.length > 0) || (deletions && deletions.length > 0));
      if (dehydrated()) pushDbxIndexToSW();   // keep the worker's lazy index fresh
      const state = syncState();
      // hub-managed subtree: drop legacy state entries so neither Pass 1 nor the
      // dirty-push loop ever touches it (see NOSYNC_PREFIX)
      for (const k of Object.keys(state)) if (isNoSyncRel(k)) delete state[k];
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
        if (isNoSyncRel(path)) { keptCount++; continue; }   // hub-managed — never delete locally
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
        if (isNoSyncRel(path)) continue;                    // hub-managed — never pull the stale mirror
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
      // Splash is static in sandpie.html (first paint). First boot sync decides:
      // device switch → keep it + wire progress; no delta → fade it out fast.
      if (_splashActive) {
        if (_deviceSwitch) {
          _showSyncSplash(toDownload.length);
        } else {
          _hideSyncSplashAfterHome(true);   // no delta — lift once the home has rendered
        }
      }
      await bulkDownload(toDownload, state, opfs, _splashActive ? function(d, t) { _updateSyncSplash(d, t); } : null);

      // push: only files explicitly marked dirty (syncedMtime===0) by edit events.
      // A full-scan upload that treated "no state entry" as dirty has been removed
      // because it causes mega-uploads when localStorage state is lost or reset and
      // Dropbox already holds the correct copies. Dropbox is the authority; we only
      // upload files the conversation itself created or edited.
      // NOTE: the open file is skipped when PULLING (never clobber what someone is
      // editing) but must NOT be skipped here — a Save in the viewer marks the open
      // file dirty, and skipping it meant the user's own edit sat unuploaded until
      // they closed the file.
      const dirty = [];
      for (const rel of Object.keys(state)) {
        if (state[rel].syncedMtime !== 0) continue;
        if (!(await opfs.exists(rel))) continue;
        dirty.push({ rel, lm: await Sandpie.opfsMtime(rel), s: state[rel] });
      }
      const BATCH_SIZE = 50;
      let upDone = 0;
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
      // Remember when sync last completed — used to detect device switches on next load
      localStorage.setItem(LAST_SYNC_KEY, String(Date.now()));
    } catch (e) {
      dbxStatus('Sync failed: ' + e.message, 'error');
      console.warn('[dropbox] sync:', e);
    } finally {
      initialSyncDone = true; setBusy(false); _syncing = false;
      if (_splashActive) _hideSyncSplashAfterHome();
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
    if (isNoSyncRel(rel)) return;   // hub-managed — sharing.js owns its cloud side
    if (_pulling.has(rel)) return;  // a file WE just downloaded, not a user edit
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
    if (isNoSyncRel(rel)) { forgetFromStateAndIndex(rel); return; }   // hub-managed: tidy local bookkeeping, never touch the personal cloud
    forgetFromStateAndIndex(rel);
    if (tokens()) del(relToCloud(rel)).catch(() => {});
  }
  // Fetch one dehydrated file into OPFS. Shared by the provider's hydrate() hook
  // and the service worker's /files/ fault-in — both need exactly this, and a
  // second copy would drift.
  async function hydrateRel(rel) {
    const r = String(rel).replace(/^\/+/, '');
    if (!dehydrated() || isExemptRel(r)) return false;
    const e = cloudIndex()[r];
    if (!e || e.kind !== 'file') return false;      // unknown to the cloud index ⇒ genuinely absent, no request
    if (await Sandpie.opfs.exists(r)) return true;
    const bytes = await download(e.path || relToCloud(r));
    _pulling.add(r);                                // our own write — not a user edit
    try { await Sandpie.opfs.write(r, bytes); } finally { _pulling.delete(r); }
    // Record as a clean synced copy (same as worker-hydrated) so it's flushed
    // on next boot and writes back if edited.
    try { const st = syncState(); st[r] = { rev: e.rev || '', size: e.size || 0, syncedMtime: await Sandpie.opfsMtime(r) }; setSyncState(st); } catch (_) {}
    return true;
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
      // The SW serves /files/ straight out of OPFS, so a dehydrated file 404s and
      // an artifact fetching its own sibling assets breaks. It asks us to fetch the
      // file first; we answer on the port it supplied and it retries the read.
      if (d.type === 'sw-hydrate' && d.rel) {
        const port = ev.ports && ev.ports[0];
        (async () => {
          let ok = false;
          try { ok = await hydrateRel(d.rel); }
          catch (e) { console.warn('[dropbox] sw hydrate failed:', d.rel, (e && e.message) || e); }
          if (port) { try { port.postMessage({ ok }); } catch (_) {} }
        })();
        return;
      }
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

  // Fetch GET /config once for the deployment's Dropbox app key (non-secret) so the
  // panel can one-click connect. The folder layout is NOT taken from here any more:
  // both roots are fixed constants, so a stale server value cannot detach a user
  // from their workspace or from the department hubs.
  async function loadServerConfig() {
    if (_serverAppKey !== null) return;
    try {
      const res = await fetch('/config', { headers: { Accept: 'application/json' } });
      const cfg = res.ok ? ((await res.json()) || {}) : {};
      _serverAppKey = cfg.dropboxAppKey || '';
    } catch { _serverAppKey = ''; }
  }
  async function serverAppKey() { await loadServerConfig(); return _serverAppKey; }
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
    // Keep PARENT_KEY + APPKEY_CFG so a reconnect reuses the key, and so PARENT_KEY
    // can still locate the legacy team workspace if the import hasn't happened yet.
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
      }
    };
    await Promise.all(Array.from({ length: Math.min(DL_CONCURRENCY, files.length) }, worker));
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
  // What gets shared is ONE Dropbox folder per package, with every recipient added
  // as a member of it. Two cases:
  //
  //   FOLDER source (a skill, or any folder) — the LIVE workspace folder itself is
  //     shared, e.g. /sandpie/skills/thing. Edits the sender makes propagate to
  //     every recipient through Dropbox with no re-publish. Consequences the sender
  //     is signing up for: deleting a file in there deletes it for everyone, and
  //     Dropbox will then refuse to share that folder's parent or any folder inside
  //     it (SharePathError contains_shared_folder / inside_shared_folder).
  //
  //   SINGLE FILE source — Dropbox cannot share a file (SharePathError.is_file), so
  //     it is wrapped: /Sandpie Outbox/<id>/ holds a COPY. Not live; re-sharing
  //     republishes it.
  //
  // The package manifest is a .sandpie-share.json at the root of the shared folder.
  // That marker is also how a recipient recognises which of their shared folders
  // are Sandpie packages — the folder name is the sender's own, so it carries no
  // reliable signal.
  //
  // Recipients are invited as VIEWER by default; the share dialog can raise that to
  // EDITOR. On a LIVE folder share, editor is real write access to the sender's own
  // workspace folder, so the dialog says so rather than burying it. Accept/dismiss
  // state lives in the recipient's own shares.json either way (keyed id@rev; an
  // explicit re-share bumps rev and re-notifies, plain content edits update
  // silently), so it does not depend on the recipient being able to delete anything.
  //
  // Requires the sharing.read + sharing.write scopes on the Dropbox app. A token
  // minted before those were granted fails with missing_scope; that's surfaced as
  // a reconnect prompt rather than a raw API error.
  const OUTBOX_PARENT = '/Sandpie Outbox';   // wrappers for single-file shares (sender's Dropbox)
  // opts is passed straight to api(): PATH-based sharing calls against the team
  // space need {team:true} (the path-root header), or the path resolves against the
  // member's home namespace and 404s. ID-based calls (add/remove/update member,
  // unshare, list members) take a shared_folder_id and need no header, which is why
  // the original helpers worked without one.
  async function shareApi(path, body, opts) {
    try { return await api(path, body, opts); }
    catch (e) {
      if (/missing_scope|insufficient_scope/i.test(String((e && e.message) || e))) {
        throw new Error('Dropbox sharing permission is missing for this login — reconnect Dropbox (Settings → Cloud sync → Disconnect, then Connect) to grant it.');
      }
      throw e;
    }
  }
  // create_folder_v2 inside the TEAM space (1:1 mailbox containers live there).
  async function teamMkdir(path) {
    try { await api('/2/files/create_folder_v2', { path, autorename: false }, { team: true }); return true; }
    catch (e) { if (/conflict/.test(String((e && e.message) || e))) return false; throw e; }   // already there / lost a race
  }
  // Share a folder in the team space with SPECIFIC people. access_inheritance
  // 'no_inherit' is the whole point: without it a folder inside a team folder
  // inherits that folder's membership, so every teammate still sees it. Returns the
  // shared_folder_id; idempotent if the folder is already shared.
  async function shareFolderRestricted(path) {
    const T = { team: true };
    let md = null;
    try { md = await api('/2/files/get_metadata', { path }, T); } catch (_) {}
    const existing = md && md.sharing_info && md.sharing_info.shared_folder_id;
    if (existing) return existing;
    const arg = { path, acl_update_policy: 'owner', force_async: false };
    let res;
    try { res = await shareApi('/2/sharing/share_folder', Object.assign({ access_inheritance: { '.tag': 'no_inherit' } }, arg), T); }
    catch (e) { res = await shareApi('/2/sharing/share_folder', arg, T); }   // parameter refused → set it separately below
    if (res['.tag'] === 'async_job_id') {
      const job = res.async_job_id; res = null;
      for (let i = 0; i < 30 && !res; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const st = await shareApi('/2/sharing/check_share_job_status', { async_job_id: job });
        if (st['.tag'] === 'in_progress') continue;
        if (st['.tag'] === 'failed') throw new Error('share_folder failed: ' + JSON.stringify(st).slice(0, 200));
        res = st;
      }
      if (!res) throw new Error('Dropbox is still creating the shared folder — try again in a moment.');
    }
    const id = res.shared_folder_id;
    if (!id) throw new Error('share_folder did not return a shared_folder_id');
    if (((res.access_inheritance || {})['.tag']) !== 'no_inherit') {
      await shareApi('/2/sharing/set_access_inheritance', { shared_folder_id: id, access_inheritance: { '.tag': 'no_inherit' } });
    }
    return id;
  }
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
  // Current membership of a shared folder, as {emailLower: {level, accountId,
  // invitee}}. `users` have joined and carry a dropbox_id; `invitees` were invited
  // by email and have not joined, so they have no id yet — which decides how their
  // access level can be changed (see below).
  async function folderMembers(sharedFolderId) {
    const out = {};
    let data = await shareApi('/2/sharing/list_folder_members', { shared_folder_id: sharedFolderId, limit: 100 });
    for (let guard = 0; guard < 50; guard++) {
      for (const u of (data.users || [])) {
        const em = String((u.user || {}).email || '').toLowerCase();
        if (em) out[em] = { level: (u.access_type || {})['.tag'] || '', accountId: (u.user || {}).account_id || '', invitee: false };
      }
      for (const i of (data.invitees || [])) {
        const em = String((i.invitee || {}).email || '').toLowerCase();
        if (em && !out[em]) out[em] = { level: (i.access_type || {})['.tag'] || '', accountId: ((i.user || {}).account_id) || '', invitee: true };
      }
      if (!data.cursor) break;
      data = await shareApi('/2/sharing/list_folder_members/continue', { cursor: data.cursor });
    }
    return out;
  }
  // Share `path` (a folder in the user's OWN Dropbox — either a live workspace
  // folder or an outbox wrapper) with these emails at `level` ('viewer' | 'editor').
  // Idempotent, and it CONVERGES: re-sharing to someone who already has a different
  // access level moves them to the new one rather than silently keeping the old.
  async function shareFolderWith(path, emails, level) { return inviteToFolder(await shareFolderId(path), emails, level); }
  async function inviteToFolder(id, emails, level) {
    const want = (level === 'editor') ? 'editor' : 'viewer';
    // Read the membership FIRST rather than adding and handling the failure. On a
    // re-share every recipient is already a member, so the add-then-recover shape
    // meant a 409 per recipient every single time — the same call count, but the
    // console read like the share had failed.
    const members = await folderMembers(id);
    for (const email of (emails || [])) {
      const em = String(email);
      const cur = members[em.toLowerCase()];
      if (!cur) {
        await shareApi('/2/sharing/add_folder_member', {
          shared_folder_id: id,
          members: [{ member: { '.tag': 'email', email: em }, access_level: { '.tag': want } }],
          quiet: true,   // no Dropbox notification email — the app is the notification
        });
        continue;
      }
      if (!cur || cur.level === want || cur.level === 'owner') continue;
      if (!cur.invitee && cur.accountId) {
        // Joined members can be updated in place — but ONLY by dropbox_id;
        // UpdateFolderMemberArg.member documents that email is not accepted.
        await shareApi('/2/sharing/update_folder_member', {
          shared_folder_id: id,
          member: { '.tag': 'dropbox_id', dropbox_id: cur.accountId },
          access_level: { '.tag': want },
        });
      } else {
        // A pending invitee has no dropbox_id, so there is nothing to update —
        // withdraw the invitation and re-issue it at the new level.
        await shareApi('/2/sharing/remove_folder_member', {
          shared_folder_id: id, member: { '.tag': 'email', email: em }, leave_a_copy: false,
        });
        await shareApi('/2/sharing/add_folder_member', {
          shared_folder_id: id,
          members: [{ member: { '.tag': 'email', email: em }, access_level: { '.tag': want } }],
          quiet: true,
        });
      }
    }
    return { id, level: want };
  }
  // Outbox wrapper for a SINGLE FILE, which Dropbox refuses to share directly
  // (SharePathError.is_file). Named after the FILE, extension and all, because in
  // the mount fallback this folder is what shows up in the recipient's Dropbox —
  // "report.html" tells them what they got; the slugged package id would not.
  // Keeps spaces and accents — this name is meant to be read. Only strips what
  // Dropbox or a path parser would choke on.
  function sanitizeName(s) {
    return String(s).replace(/[\\/:*?"<>|]/g, '_').replace(/[\x00-\x1f]/g, '').replace(/^[.\s]+|[.\s]+$/g, '').slice(0, 120) || 'shared';
  }
  // `created` lets the caller skip probing a brand-new folder for a manifest that
  // cannot be there yet — one less request that could only ever answer not_found.
  async function ensureOutboxFolder(displayName) {
    const path = OUTBOX_PARENT + '/' + sanitizeName(displayName);
    // create_folder_v2 makes missing parents, so don't probe for the parent as
    // well — that was a second guaranteed 409 on the first ever share.
    let created;
    try { created = await mkdirp(path); }
    catch (e) {
      if (!/not_found|malformed_path/i.test(String((e && e.message) || e))) throw e;
      await mkdirp(OUTBOX_PARENT);
      created = await mkdirp(path);
    }
    return { path, created };
  }
  // Stop sharing entirely — the package disappears for every recipient. Used when
  // the sender un-shares; leaves the sender's own files in place.
  async function unshareFolder(sharedFolderId) {
    await shareApi('/2/sharing/unshare_folder', { shared_folder_id: sharedFolderId, leave_a_copy: true });
  }
  // ---- Delivery notifications -------------------------------------------------
  // The marker file is shared with each recipient INDIVIDUALLY, on top of the folder
  // share. That turns discovery from a scan into a single request: the recipient
  // asks Dropbox for the files shared with them, and every SharedFileMetadata
  // carries parent_shared_folder_id — which IS the package's namespace. One call,
  // whether the account belongs to five shared folders or five hundred.
  async function notifyFileMembers(filePath, emails, level) {
    const want = (level === 'editor') ? 'editor' : 'viewer';
    const res = await shareApi('/2/sharing/add_file_member', {
      file: filePath,
      members: (emails || []).map(e => ({ '.tag': 'email', email: String(e) })),
      access_level: { '.tag': want },
      quiet: true,
    });
    // Per-member outcomes come back in the RESULT array, not as an HTTP error.
    // Already-a-member is the steady state and must not be treated as a failure.
    for (const r of (Array.isArray(res) ? res : [])) {
      const t = JSON.stringify((r && r.result) || r || '');
      if (/error/i.test(t) && !/already|invalid_dropbox_id/i.test(t)) console.warn('[dropbox] add_file_member:', t.slice(0, 200));
    }
    return res;
  }
  // Every delivery addressed to this account, in one request (plus pagination).
  // Filtering by `name` is what makes it ours; parent_shared_folder_id is where the
  // package lives.
  async function listDeliveries(markerName) {
    const want = String(markerName).toLowerCase();
    const out = [];
    let data = await shareApi('/2/sharing/list_received_files', { limit: 300 });
    for (let guard = 0; guard < 50; guard++) {
      for (const e of (data.entries || [])) {
        if (String(e.name || '').toLowerCase() !== want) continue;
        if (!e.parent_shared_folder_id) continue;   // not inside a shared folder ⇒ no namespace to read
        out.push({
          id: e.parent_shared_folder_id,
          fileId: e.id || '',
          name: e.name,
          owner: (e.owner_display_names || [])[0] || '',
          from: (e.owner_display_names || [])[0] || '',
          isOwner: ((e.access_type || {})['.tag'] || '') === 'owner',
          invitedAt: Date.parse(e.time_invited || '') || 0,
          path: e.path_lower || '',
        });
      }
      if (!data.cursor) break;
      data = await shareApi('/2/sharing/list_received_files/continue', { cursor: data.cursor });
    }
    return out;
  }

  // Every shared folder this account is a member of. Kept for diagnose() only —
  // discovery no longer walks this list.
  // `path` is the mount point, '' when unmounted. `isOwner` marks folders WE shared
  // out, so a sender never sees their own package come back as an incoming delivery.
  async function listIncomingShares() {
    const out = [];
    let data = await shareApi('/2/sharing/list_folders', { limit: 100 });
    for (let guard = 0; guard < 50; guard++) {
      for (const e of (data.entries || [])) {
        out.push({
          id: e.shared_folder_id,
          name: e.name,
          owner: (e.owner_display_names || [])[0] || '',
          from: (e.owner_display_names || [])[0] || '',
          isOwner: ((e.access_type || {})['.tag'] || '') === 'owner',
          path: e.path_lower || '',
          // Used to decide what to look at FIRST. A corporate account can be a
          // member of hundreds of shared folders and we must not probe them all
          // every tick: newest invitation wins, and team folders go last because a
          // Sandpie package is always a personal-namespace folder.
          invitedAt: Date.parse(e.time_invited || '') || 0,
          isTeamFolder: !!e.is_team_folder || !!e.is_inside_team_folder,
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
    // Splash markup is static in sandpie.html (first paint, removed inline if
    // no Dropbox). Active only if it survived that — i.e. this user is connected.
    _splashActive = !!document.getElementById('deviceSyncSplash');
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
      hydrate: (rel) => hydrateRel(rel),
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
      cloudParent: () => teamParent(),               // the team-folders ROOT, e.g. /IA
      listTeamFolders: () => listTeamFolders(),      // departments this user may see
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
      // Cursor-based delta listing for the TEAM hub — mirrors the workspace sync's
      // dbxfull-cursor: the cursor is a per-device localStorage variable, never a
      // file. Returns {entries, cursor}; callers store the cursor and pass it to
      // cloudListContinue() on the next poll to get ONLY what changed.
      async cloudListWithCursor(absPath, { team = true, ns = '' } = {}) {
        try { return await listFolder(absPath, { recursive: true, team, ns }); }
        catch (e) { if (String((e && e.message) || e).includes('not_found')) return { entries: [], cursor: '' }; throw e; }
      },
      async cloudListContinue(cursor, { team = true } = {}) {
        try { return await listContinue(cursor, { team }); }
        catch (e) { throw e; }   // stale/expired cursor → caller falls back to a full list
      },
      // Workspace-scoped variants (home namespace) — used by sharing.js to clean up
      // its own copies inside the user's workspace, which is NOT in the team root.
      workspaceDelete: (absPath) => del(absPath, { team: false }),
      // --- 1:1 delivery by email (Dropbox sharing API; no team folder) --------
      // The Dropbox account's own email — the authoritative sender identity for a
      // share, independent of whatever account.js reports.
      accountEmail: () => localStorage.getItem(EMAIL_KEY) || '',
      shareFolderWith: (path, emails, level) => shareFolderWith(path, emails, level),   // level 'viewer'|'editor'; → {id, level}
      // --- 1:1 mailbox inside the TEAM space (sharing.js deliver()) -----------
      // A folder only its members can see, so access control IS the addressing —
      // the recipient finds it in the recursive listing they already do, with no
      // list_shared_folders / list_received_files call anywhere.
      cloudMkdir: (absPath) => teamMkdir(absPath),
      shareRestricted: (absPath) => shareFolderRestricted(absPath),   // → shared_folder_id, no_inherit
      // Split so a caller can write the package marker BEFORE anyone is invited —
      // a recipient who polls between the invite and the marker would otherwise see
      // a share that looks like it isn't ours.
      shareEnsureFolder: (path) => shareFolderId(path),     // → shared_folder_id (shares it if needed)
      shareInvite: (id, emails, level) => inviteToFolder(id, emails, level),
      shareMembers: (id) => folderMembers(id),              // {emailLower: {level, accountId, invitee}}
      shareOutboxFolder: (name) => ensureOutboxFolder(name),   // wrapper for a single-file share, named after the file
      shareWorkspacePath: (rel) => relToCloud(rel),         // OPFS rel → the live Dropbox path
      shareNotify: (filePath, emails, level) => notifyFileMembers(filePath, emails, level),   // share the marker itself → the recipient's O(1) signal
      shareListDeliveries: (markerName) => listDeliveries(markerName),   // ONE call: every delivery addressed to me
      shareListIncoming: () => listIncomingShares(),        // every shared folder — diagnose() only
      shareMount: (id) => mountShare(id),                   // fallback when a namespace read is refused
      shareDecline: (id) => declineShare(id),               // leave a share (stop receiving)
      shareUnshare: (id) => unshareFolder(id),              // sender: revoke for everyone
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
