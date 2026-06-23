/* =============================================================================
   modules/dropbox-full.js — Full-Dropbox sync provider (subscription model).

   The app's sole cloud-sync provider (the former App-folder modules/dropbox.js
   was removed 2026-06-18). Registers a Sandpie sync provider + its cloud-sync
   settings panel. Self-contained: its own dbx* transport + a `dbxfull-*`
   localStorage namespace.

   Requires the user's Dropbox app to be **Full Dropbox** access type with scopes:
     account_info.read, files.metadata.read, files.content.read, files.content.write

   Model
   -----
   - The user's OWN working files (the OPFS root: conversations, scripts, …) sync
     TWO-WAY into a per-user working folder: <parent>/<email-local-part>/, where
     <parent> is set in the Cloud sync section (default /sandpie). That folder is
     the ONLY place this module ever writes.
   - On a Dropbox **team space**, the API is pointed at the team-space ROOT
     namespace (via the Dropbox-API-Path-Root header) so team/department folders
     are reachable — e.g. set the parent to /R+D+I/sandpie to sync into a shared
     department folder, with each user landing in their own /<email> subfolder.
   - NOTHING else syncs by default (full Dropbox can be 100s of GB). Subscribing
     to other Dropbox folders — read-only, pulled into OPFS /_shared/ — is a
     follow-up slice; the data model (dbxfull-subscriptions) is stubbed here.

   FOUNDATION slice: connect + working-dir two-way sync. The browse/subscribe UI,
   size/quota gating, /_shared/ read-only pull, and the Personal/Shared Files
   split are not wired yet.
   ============================================================================= */
(function () {
  'use strict';
  if (!window.Sandpie) { console.warn('[dropbox-full] no Sandpie host — disabled'); return; }

  // ---- persistent state (dbxfull-* namespace) -------------------------------
  const TOKENS_KEY = 'dbxfull-tokens';
  const PKCE_KEY   = 'dbxfull-pkce';
  const ROOT_KEY   = 'dbxfull-working-root';
  const STATE_KEY  = 'dbxfull-sync-state';
  const INDEX_KEY  = 'dbxfull-cloud-index';
  const CURSOR_KEY = 'dbxfull-cursor';
  const SUBS_KEY   = 'dbxfull-subscriptions';   // [{path,label,addedAt,bytes}] — read-only team/shared folder mirrors
  const APPKEY_CFG = 'dbxfull-appkey';
  const PARENT_KEY = 'dbxfull-parent';          // parent folder; <email-local> is appended
  const DEFAULT_PARENT = '/R+D+I/sandpie';      // default sync parent (deployment default)
  const AUTOCONN_OPTOUT = 'dbxfull-no-autoconnect';   // localStorage: set on explicit Disconnect
  const AUTOCONN_TRIED  = 'dbxfull-autoconn-tried';   // sessionStorage: per-session auto-connect loop guard
  const NS_KEY     = 'dbxfull-pathroot';        // team-space root namespace id ('' when root === home)
  const NS_VER_KEY = 'dbxfull-ns-ver';          // detection-logic version; bump ⇒ force a one-time re-fetch
  const EMAIL_KEY  = 'dbxfull-email';           // cached account email for the per-user subfolder
  const SIG_KEY    = 'dbxfull-target-sig';      // namespace|path signature; change ⇒ reset sync state
  const NS_DETECT_VER = '2';                    // bumped: detect via root !== home (was tag==='team', which missed team spaces reported as 'user')
  const SUBSTATE_KEY  = 'dbxfull-subs-state';   // { localRel: {rev,size} } for subscription mirrors — rev-based pull, no mtime/dirty tracking (read-only)
  const SUBS_PREFIX   = '_subs';                // reserved OPFS top-level dir holding read-only subscription mirrors; fenced out of push
  const DEHYDRATED_KEY = 'dbxfull-dehydrated';  // opt-in: don't bulk-download; the AI hydrates files on demand (worker)
  const EXEMPT_PREFIXES = ['_conversations', 'skills', 'agents'];   // always eagerly synced — the app reads these directly
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
  // On a team space we operate relative to the team-space ROOT namespace so team
  // folders (e.g. /R+D+I) are reachable; default API behavior is the member's home
  // namespace. The namespace id comes from get_current_account (team accounts only).
  function pathRootHeaderObj() {
    const ns = localStorage.getItem(NS_KEY);
    return ns ? { 'Dropbox-API-Path-Root': JSON.stringify({ '.tag': 'root', root: ns }) } : {};
  }
  // Dropbox-API-Arg travels in an HTTP header, which must be ASCII. Escape every
  // non-ASCII char as \uXXXX (Dropbox un-escapes server-side) — otherwise a path
  // with accents (e.g. "DOCUMENTACIÓ", "Pràctiques") is sent as raw Latin-1 and
  // the request is rejected (empty 401 at the proxy). Paths in JSON *bodies* are
  // unaffected, which is why upload/list worked and only download broke.
  function apiArg(obj) {
    return JSON.stringify(obj).replace(/[^\x00-\x7F]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  }
  async function api(path, body, { pathRoot = true } = {}) {
    const token = await accessToken();
    const headers = { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' };
    if (pathRoot) Object.assign(headers, pathRootHeaderObj());
    const res = await fetch(dbxRoute('https://api.dropboxapi.com' + path), {
      method: 'POST', headers, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Dropbox ${path}: ${res.status} ${await res.text()}`);
    return await res.json();
  }
  const mapEntry = e => ({ name: e.name, kind: e['.tag'], path: e.path_display, size: e.size, rev: e.rev, hash: e.content_hash, cloudMtime: e.server_modified });
  async function listFolder(folderPath, { recursive = false } = {}) {
    let data = await api('/2/files/list_folder', { path: folderPath === '/' ? '' : folderPath, recursive, include_deleted: true });
    let entries = data.entries.slice();
    while (data.has_more) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }); entries = entries.concat(data.entries); }
    return { entries: entries.map(mapEntry), cursor: data.cursor };
  }
  async function listContinue(cursor) {
    let data = await api('/2/files/list_folder/continue', { cursor });
    let entries = data.entries.slice();
    while (data.has_more) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }); entries = entries.concat(data.entries); }
    return { entries: entries.map(mapEntry), cursor: data.cursor };
  }
  async function download(path, signal) {
    // /2/files/download's SUCCESS (200) response does NOT carry CORS headers — only
    // its preflight and ERROR responses do. So a direct browser fetch can read an
    // error but not the file: a 200 fails the browser CORS check ("No
    // Access-Control-Allow-Origin"), which is exactly what breaks sync. The old
    // build hid this by routing through a same-origin /proxy/; this server has none
    // (see dbxRoute). Dropbox's documented browser-download path is
    // get_temporary_link (a normal RPC — fully CORS-enabled) → GET the returned URL
    // (a plain GET = no custom headers = NO preflight, and the temp-link host returns
    // ACAO), which works cross-origin even under the prod COOP/COEP isolation.
    const tl = await api('/2/files/get_temporary_link', { path });
    const res = await fetch(dbxRoute(tl.link), { method: 'GET', signal });
    if (!res.ok) throw new Error(`Download ${path}: ${res.status}`);
    return new Uint8Array(await res.arrayBuffer());
  }
  async function uploadSessionStart(content, close = true) {
    const token = await accessToken();
    const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/upload_session/start'), {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream', 'Dropbox-API-Arg': apiArg({ close }), ...pathRootHeaderObj() },
      body: content,
    });
    if (!res.ok) throw new Error(`Upload session start: ${res.status} ${await res.text()}`);
    return await res.json();
  }
  async function uploadSessionFinishBatch(entries) {
    const token = await accessToken();
    const res = await fetch(dbxRoute('https://api.dropboxapi.com/2/files/upload_session/finish_batch_v2'), {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...pathRootHeaderObj() },
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
        } catch (err) { console.warn('[dropbox-full] session start failed:', rel, err); return null; }
      }));
      sessions.push(...results.filter(Boolean));
    }
    if (!sessions.length) return [];
    const entries = sessions.map(x => ({ cursor: x.cursor, commit: x.commit }));
    const result = await uploadSessionFinishBatch(entries);
    if (result['.tag'] === 'async_job_id') { console.warn('[dropbox-full] finish_batch returned async_job_id — skipped, will retry next sync'); return []; }
    if (!result.entries) { console.warn('[dropbox-full] unexpected finish_batch response:', result); return []; }
    return sessions.map((x, i) => ({ ...x, meta: result.entries[i] }));
  }
  async function del(path) {
    try { return await api('/2/files/delete_v2', { path }); }
    catch (e) { if (String(e.message).includes('not_found')) return null; throw e; }
  }
  async function getCurrentAccount() { return await api('/2/users/get_current_account', null, { pathRoot: false }); }

  // ===========================================================================
  //  Working root  (<parent>/<email-local-part>/)
  // ===========================================================================
  function workingRoot() { return localStorage.getItem(ROOT_KEY) || ''; }
  function sanitizeSeg(s) { return String(s).replace(/[^a-zA-Z0-9._-]/g, '_').replace(/^_+|_+$/g, '') || 'user'; }
  async function ensureWorkingRoot() {
    // Account fetched once (cached): the team-space root namespace (team accounts
    // only) + the email used for the per-user subfolder.
    let ns = localStorage.getItem(NS_KEY);
    let email = localStorage.getItem(EMAIL_KEY);
    if (ns === null || !email || localStorage.getItem(NS_VER_KEY) !== NS_DETECT_VER) {
      const acct = await getCurrentAccount();
      const ri = acct.root_info || {};
      // Team space ⇔ the root namespace differs from the home namespace. Do NOT gate on
      // root_info['.tag']: an account sitting in a team space can still report '.tag' ===
      // 'user' while having a distinct root_namespace_id (confirmed in the field). Gating on
      // the tag left the path-root header off, so team paths like /R+D+I resolved against the
      // personal home folder instead of the team space. '' ⇒ no header ⇒ home namespace.
      ns = (ri.root_namespace_id && ri.root_namespace_id !== ri.home_namespace_id) ? ri.root_namespace_id : '';
      email = acct.email || acct.account_id || 'user';
      localStorage.setItem(NS_KEY, ns);
      localStorage.setItem(EMAIL_KEY, email);
      localStorage.setItem(NS_VER_KEY, NS_DETECT_VER);
      console.info('[dropbox-full] path-root', ns ? ('→ team root ' + ns) : '→ home', '(root=' + ri.root_namespace_id + ', home=' + ri.home_namespace_id + ')');
    }
    // Working dir = <parent>/<email-local>. Parent is set in the Cloud sync
    // section (default DEFAULT_PARENT = /R+D+I/sandpie, the department folder).
    const local = sanitizeSeg(String(email).split('@')[0]);
    let parent = (localStorage.getItem(PARENT_KEY) || DEFAULT_PARENT).trim() || DEFAULT_PARENT;
    if (!parent.startsWith('/')) parent = '/' + parent;
    parent = parent.replace(/\/+$/, '');
    const root = parent + '/' + local;
    // Relocate guard. The sync target is (namespace + path): the SAME path string
    // resolves to DIFFERENT folders under different path-roots (home namespace vs
    // team space), so the namespace MUST be part of the signature — otherwise
    // switching roots reuses stale state and wrongly deletes local files as
    // "removed remotely". When the signature changes (parent edit, or first run
    // under a new namespace) drop the old sync state so the new location starts
    // fresh: re-pull there + re-push the local working dir, deleting nothing.
    const sig = (ns || 'home') + '|' + root;
    if (localStorage.getItem(SIG_KEY) !== sig) {
      localStorage.setItem(SIG_KEY, sig);
      localStorage.removeItem(STATE_KEY);
      localStorage.removeItem(INDEX_KEY);
      localStorage.removeItem(CURSOR_KEY);
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
  // ----- subscription mirrors (read-only) ------------------------------------
  // A subscribed cloud folder is mirrored into OPFS under "_subs/<label>/…". This
  // prefix is fenced out of the push (see sync()) so mirrored files are NEVER
  // uploaded — that fence is what makes "read-only" actually true.
  function isUnderSubs(rel) {
    const r = String(rel).replace(/^\/+/, '').toLowerCase();
    return r === SUBS_PREFIX || r.startsWith(SUBS_PREFIX + '/');
  }
  function subLocalRoot(sub) { return SUBS_PREFIX + '/' + sanitizeSeg(sub.label); }
  // Path of `p` relative to `basePath` (case-insensitive), or null if outside it.
  function relUnder(basePath, p) {
    const bp = String(basePath).replace(/^\/+/, '').toLowerCase();
    let s = String(p).replace(/^\/+/, '');
    if (!bp) return s;                                     // base is the namespace root
    if (s.toLowerCase().startsWith(bp + '/')) return s.slice(bp.length + 1);
    if (s.toLowerCase() === bp) return '';
    return null;
  }

  // ===========================================================================
  //  Sync state
  // ===========================================================================
  function syncState() { try { return JSON.parse(localStorage.getItem(STATE_KEY) || '{}'); } catch { return {}; } }
  function setSyncState(s) { localStorage.setItem(STATE_KEY, JSON.stringify(s)); }
  function cloudIndex() { try { return JSON.parse(localStorage.getItem(INDEX_KEY) || '{}'); } catch { return {}; } }
  function setCloudIndex(i) { localStorage.setItem(INDEX_KEY, JSON.stringify(i)); }
  function dehydrated() { return localStorage.getItem(DEHYDRATED_KEY) === '1'; }
  function isExemptRel(rel) {
    const r = String(rel).replace(/^\/+/, '').toLowerCase();
    return EXEMPT_PREFIXES.some(p => { const pl = p.toLowerCase(); return r === pl || r.startsWith(pl + '/'); });
  }
  function cursor() { return localStorage.getItem(CURSOR_KEY) || null; }
  function setCursor(c) { if (c) localStorage.setItem(CURSOR_KEY, c); else localStorage.removeItem(CURSOR_KEY); }
  function subscriptions() { try { return JSON.parse(localStorage.getItem(SUBS_KEY) || '[]'); } catch { return []; } }
  function setSubscriptions(s) { localStorage.setItem(SUBS_KEY, JSON.stringify(s)); }
  function subsState() { try { return JSON.parse(localStorage.getItem(SUBSTATE_KEY) || '{}'); } catch { return {}; } }
  function setSubsState(s) { localStorage.setItem(SUBSTATE_KEY, JSON.stringify(s)); }

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
        for (const e of result.entries) {
          const rel = cloudToRel(e.path);
          if (rel == null || rel === '') continue;
          if (e.kind === 'deleted') delete idx[rel];
          else { idx[rel] = e; delta.push([rel, e]); }
        }
        setCursor(result.cursor); setCloudIndex(idx);
        return { index: idx, delta };
      } catch (err) {
        console.warn('[dropbox-full] cursor sync failed, full re-list:', err.message);
        setCursor(null);
      }
    }
    let result;
    try {
      result = await listFolder(workingRoot(), { recursive: true });
    } catch (e) {
      if (String(e.message).includes('not_found')) {   // working folder doesn't exist yet
        setCursor(null); setCloudIndex({});
        return { index: {}, delta: null };
      }
      throw e;
    }
    const out = {};
    for (const e of result.entries) {
      const rel = cloudToRel(e.path);
      if (rel == null || rel === '') continue;
      if (e.kind !== 'deleted') out[rel] = e;
    }
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
        } catch (err) { console.warn('[dropbox-full] download failed:', it.rel, err); }
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
      const { index: cloud, delta } = await cloudListWorking();
      if (dehydrated()) pushDbxIndexToSW();   // keep the worker's lazy index fresh
      const state = syncState();
      const fullScan = !!opts.full || !initialSyncDone || delta === null || (_syncCount % FULL_SCAN_EVERY === 0);

      // remote deletions: tracked locally but gone from cloud
      let removedAny = false;
      for (const path of Object.keys(state)) {
        if (cloud[path]) continue;
        const lm = await Sandpie.opfsMtime(path);
        if (lm > 0 && lm > state[path].syncedMtime) continue;   // locally modified — keep
        try { await opfs.remove(path); } catch {}
        delete state[path]; removedAny = true;
      }

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
        const localDirty = localExists && (await Sandpie.opfsMtime(path)) > s.syncedMtime;
        if (path === openFilePath) continue;
        if (cloudChanged && localDirty) continue;          // conflict — leave for the user
        if (cloudChanged || !localExists) { toDownload.push({ rel: path, cloudPath: e.path, e }); continue; }
        state[path].size = e.size;
      }
      if (toDownload.length) _setSyncProgress(0, toDownload.length, 'Downloading');
      await bulkDownload(toDownload, state, opfs, toDownload.length ? (d, t) => _setSyncProgress(d, t, 'Downloading') : null);

      // push: dirty = event-marked (syncedMtime===0); full scan walks all local
      // files. Uploaded via upload_session + finish_batch_v2 (one commit call per
      // batch) — minimizes round-trips and avoids too_many_write_operations
      // throttling on a large first sync. syncedMtime is the mtime captured at
      // collection time, so a write that lands mid-upload re-uploads next cycle.
      const deh = dehydrated();
      const cidx = deh ? cloudIndex() : null;   // dehydrated: don't push lazily-hydrated cloud files back (stage 1)
      const dirty = [];
      if (fullScan) {
        let rels = []; try { rels = await opfs.list(); } catch {}
        for (const rel of rels) {
          if (rel === openFilePath) continue;
          if (isUnderSubs(rel)) continue;            // read-only subscription mirror — never push
          if (deh && !isExemptRel(rel) && cidx[rel]) continue;   // lazy cloud file — not a local creation
          const s = state[rel];
          const lm = await Sandpie.opfsMtime(rel);
          if (s && lm <= s.syncedMtime) continue;
          dirty.push({ rel, lm, s });
        }
      } else {
        for (const rel of Object.keys(state)) {
          if (rel === openFilePath) continue;
          if (isUnderSubs(rel)) continue;            // read-only subscription mirror — never push
          if (deh && !isExemptRel(rel) && cidx[rel]) continue;   // lazy cloud file — not a local creation
          if (state[rel].syncedMtime !== 0) continue;
          if (!(await opfs.exists(rel))) continue;
          dirty.push({ rel, lm: await Sandpie.opfsMtime(rel), s: state[rel] });
        }
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
            } else {
              console.warn('[dropbox-full] batch item failed:', r.rel, r.meta);
            }
          }
        } catch (err) { console.warn('[dropbox-full] batch upload failed:', err); }
        upDone += chunk.length;
        _setSyncProgress(upDone, dirty.length, 'Uploading');
      }
      setSyncState(state);

      if (firstSync || toDownload.length || dirty.length || removedAny) {
        await Sandpie.refreshFiles();
        await Sandpie.refreshConversations();
      }
    } catch (e) {
      dbxStatus('Sync failed: ' + e.message, 'error');
      console.warn('[dropbox-full] sync:', e);
    } finally {
      initialSyncDone = true; setBusy(false); _syncing = false;
      try { _setSyncProgress(0, 0); } catch (_) {}   // clear the bar when the cycle ends
    }
  }


  // ===========================================================================
  //  Subscriptions  (read-only mirrors of other Dropbox folders)
  // ===========================================================================
  function fmtBytes(b) {
    if (!b || b < 0) return '0 B';
    const u = ['B', 'kB', 'MB', 'GB', 'TB']; let i = 0;
    while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
    return (i ? b.toFixed(1).replace(/\.0$/, '') : b) + ' ' + u[i];
  }
  async function storageHeadroom() {
    try { const { quota = 0, usage = 0 } = await navigator.storage.estimate(); return Math.max(0, quota - usage); }
    catch { return Infinity; }
  }
  // Dropbox has no folder-size call, so estimate by summing file sizes from a
  // bounded recursive listing — enough to warn before mirroring a giant folder.
  async function estimateFolderSize(folderPath, { maxFiles = 8000 } = {}) {
    let bytes = 0, files = 0, capped = false;
    const consume = (entries) => {
      for (const e of entries) {
        if (e['.tag'] === 'file') { bytes += e.size || 0; files++; }
        if (files >= maxFiles) { capped = true; break; }
      }
    };
    let data = await api('/2/files/list_folder', { path: folderPath === '/' ? '' : folderPath, recursive: true });
    consume(data.entries);
    while (data.has_more && !capped) { data = await api('/2/files/list_folder/continue', { cursor: data.cursor }); consume(data.entries); }
    return { bytes, files, capped };
  }

  function isSubscribed(cloudPath) {
    const p = String(cloudPath).toLowerCase();
    return subscriptions().some(s => s.path.toLowerCase() === p);
  }
  function subscribe(cloudPath, label) {
    if (isSubscribed(cloudPath)) return;
    const subs = subscriptions();
    const base = sanitizeSeg(label || cloudPath.split('/').filter(Boolean).pop() || 'folder');
    let lab = base, n = 2;
    while (subs.some(s => sanitizeSeg(s.label) === lab)) lab = base + '_' + (n++);   // keep _subs/<label> unique
    subs.push({ path: cloudPath, label: lab, addedAt: Date.now(), bytes: 0 });
    setSubscriptions(subs);
  }
  async function unsubscribe(cloudPath) {
    const p = String(cloudPath).toLowerCase();
    const subs = subscriptions();
    const sub = subs.find(s => s.path.toLowerCase() === p);
    if (!sub) return;
    setSubscriptions(subs.filter(s => s !== sub));
    const root = subLocalRoot(sub);
    try { await Sandpie.opfs.remove(root); } catch {}
    const st = subsState();
    for (const k of Object.keys(st)) { if (k === root || k.startsWith(root + '/')) delete st[k]; }
    setSubsState(st);
    await Sandpie.refreshFiles();
  }

  // Pull every subscribed folder into its OPFS mirror. rev-based: skip unchanged
  // files, download new/changed, drop local files that vanished from the cloud.
  // Never uploads — _subs/ is fenced out of push().
  let _subsSyncing = false;
  async function refreshSubscriptions() {
    if (!tokens() || _subsSyncing) return;
    _subsSyncing = true;
    const opfs = Sandpie.opfs;
    const st = subsState();
    const subs = subscriptions();
    let touched = false;
    try {
      for (const sub of subs) {
        const localRoot = subLocalRoot(sub);
        let entries;
        try { ({ entries } = await listFolder(sub.path, { recursive: true })); }
        catch (err) { console.warn('[dropbox-full] subscription list failed:', sub.path, err.message); continue; }

        const want = new Map();    // localRel -> cloud entry
        let subBytes = 0;
        for (const e of entries) {
          if (e.kind !== 'file') continue;
          const r = relUnder(sub.path, e.path);
          if (r == null || r === '') continue;
          want.set(localRoot + '/' + r, e);
          subBytes += e.size || 0;
        }
        sub.bytes = subBytes;

        // drop local files that no longer exist remotely
        let existing = []; try { existing = await opfs.list(localRoot); } catch {}
        for (const rel of existing) {
          if (!want.has(rel)) { try { await opfs.remove(rel); } catch {} delete st[rel]; touched = true; }
        }
        // download new / changed (by rev)
        const toDl = [];
        for (const [rel, e] of want) {
          if (st[rel] && st[rel].rev === e.rev && await opfs.exists(rel)) continue;
          toDl.push({ rel, cloudPath: e.path, e });
        }
        let i = 0, stop = false;
        const worker = async () => {
          while (i < toDl.length && !stop) {
            const it = toDl[i++];
            try {
              const bytes = await download(it.cloudPath);
              await opfs.write(it.rel, bytes);
              st[it.rel] = { rev: it.e.rev, size: it.e.size };
              touched = true;
            } catch (err) {
              console.warn('[dropbox-full] subscription download failed:', it.rel, err && err.message);
              if (/quota/i.test(String(err && err.message))) { stop = true; dbxStatus('Out of local storage — subscription only partly mirrored', 'error'); }
            }
          }
        };
        await Promise.all(Array.from({ length: Math.min(8, toDl.length) }, worker));
      }
      setSubsState(st);
      setSubscriptions(subs);    // persist measured byte counts
    } finally { _subsSyncing = false; }
    if (touched) await Sandpie.refreshFiles();
  }

  // Folder browser + subscribe/unsubscribe modal (launched from Cloud sync).
  function openSubscriptionManager() {
    if (!tokens()) { alert('Connect to Dropbox first.'); return; }
    const overlay = document.createElement('div');
    overlay.className = 'modal';
    overlay.style.display = 'flex';
    overlay.setAttribute('data-chrome', '');
    overlay.innerHTML = `
      <div class="modal-backdrop"></div>
      <div class="modal-content subs-modal" style="max-width:560px; width:92%;">
        <h3>Subscriptions <span style="font-weight:400; font-size:0.78rem; color:var(--sp-text-dim);">· read-only</span></h3>
        <div style="display:flex; gap:6px; align-items:center; margin-bottom:0.4rem;">
          <button class="ghost" id="subsUp" title="Up">←</button>
          <input id="subsPath" readonly style="flex:1; padding:0.35rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.8rem;">
        </div>
        <button class="subs-pick" id="subsPick" disabled>Open a folder to subscribe to it</button>
        <div style="font-size:0.72rem; color:var(--sp-text-dim); margin-bottom:0.25rem;">Folders here — click a name to open, or use a row's Subscribe</div>
        <ul class="subs-list" id="subsBrowse" style="max-height:30vh; overflow:auto; margin:0 0 0.6rem;"></ul>
        <div style="font-size:0.72rem; color:var(--sp-text-dim); margin-bottom:0.25rem; display:flex; justify-content:space-between; align-items:center;">
          <span>Subscribed folders</span>
          <button class="ghost" id="subsRefresh" title="Re-pull all subscriptions now" style="font-size:0.7rem; padding:0.2rem 0.5rem;">Refresh all</button>
        </div>
        <ul class="subs-list" id="subsCurrent" style="max-height:22vh; overflow:auto; margin:0;"></ul>
        <div class="modal-actions"><button class="ghost" id="subsClose">Close</button></div>
      </div>`;
    document.body.appendChild(overlay);
    const $ = s => overlay.querySelector(s);
    let browsePath = '';
    const close = () => overlay.remove();
    $('.modal-backdrop').onclick = close;
    $('#subsClose').onclick = close;

    async function renderBrowse() {
      $('#subsPath').value = browsePath || '/';
      // Primary action: subscribe to the folder you're currently inside.
      const pick = $('#subsPick');
      const here = browsePath.split('/').filter(Boolean).pop();
      if (!browsePath) { pick.disabled = true; pick.textContent = 'Open a folder to subscribe to it'; pick.onclick = null; }
      else if (isSubscribed(browsePath)) { pick.disabled = true; pick.textContent = `Subscribed ✓  ·  ${here}`; pick.onclick = null; }
      else { pick.disabled = false; pick.textContent = `＋ Subscribe to “${here}”`; pick.onclick = () => doSubscribe(browsePath, here, pick); }

      const ul = $('#subsBrowse');
      ul.innerHTML = '<li class="empty">Loading…</li>';
      let entries;
      try { ({ entries } = await listFolder(browsePath || '', { recursive: false })); }
      catch (err) { ul.innerHTML = ''; const li = document.createElement('li'); li.className = 'empty'; li.textContent = 'Failed: ' + err.message; ul.appendChild(li); return; }
      const folders = entries.filter(e => e.kind === 'folder').sort((a, b) => a.name.localeCompare(b.name));
      ul.innerHTML = '';
      if (!folders.length) { const li = document.createElement('li'); li.className = 'empty'; li.textContent = '(no subfolders — use the button above to subscribe here)'; ul.appendChild(li); }
      for (const f of folders) {
        const li = document.createElement('li');
        const name = document.createElement('span');
        name.className = 'name folder';
        name.textContent = '📁 ' + f.name;
        name.title = 'Open';
        name.onclick = () => { browsePath = f.path; renderBrowse(); };
        li.appendChild(name);
        const btn = document.createElement('button');
        if (isSubscribed(f.path)) { btn.textContent = 'Subscribed ✓'; btn.disabled = true; }
        else { btn.textContent = 'Subscribe'; btn.onclick = () => doSubscribe(f.path, f.name, btn); }
        li.appendChild(btn);
        ul.appendChild(li);
      }
    }
    async function doSubscribe(cloudPath, name, btn) {
      btn.disabled = true; btn.textContent = 'Checking…';
      let est;
      try { est = await estimateFolderSize(cloudPath); }
      catch (err) { dbxStatus('Size check failed: ' + err.message, 'error'); renderBrowse(); return; }
      const headroom = await storageHeadroom();
      const sizeStr = (est.capped ? '>' : '≈') + fmtBytes(est.bytes) + ' across ' + (est.capped ? '>' : '') + est.files + ' files';
      if (est.bytes > headroom) {
        alert(`"${name}" is ${sizeStr}, but only ${fmtBytes(headroom)} of browser storage is free.\nFree up space or pick a smaller folder.`);
        renderBrowse(); return;
      }
      if ((est.bytes > 200 * 1024 * 1024 || est.capped) && !confirm(`Mirror "${name}" (${sizeStr}) into local storage, read-only?`)) {
        renderBrowse(); return;
      }
      subscribe(cloudPath, name);
      renderBrowse(); renderCurrent();
      dbxStatus('Mirroring ' + name + '…', 'connected');
      await refreshSubscriptions();
      dbxStatus('', 'connected');
      renderCurrent();
    }
    function renderCurrent() {
      const ul = $('#subsCurrent');
      ul.innerHTML = '';
      const subs = subscriptions();
      if (!subs.length) { const li = document.createElement('li'); li.className = 'empty'; li.textContent = '(none yet — browse above to subscribe)'; ul.appendChild(li); return; }
      for (const sub of subs) {
        const li = document.createElement('li');
        const name = document.createElement('span');
        name.className = 'name';
        name.textContent = '📡 ' + sub.label;
        name.title = sub.path;
        li.appendChild(name);
        const size = document.createElement('span');
        size.className = 'file-size';
        size.textContent = sub.bytes ? fmtBytes(sub.bytes) : '';
        li.appendChild(size);
        const btn = document.createElement('button');
        btn.className = 'ghost';
        btn.style.cssText = 'margin-left:6px; font-size:0.7rem; padding:0.2rem 0.5rem;';
        btn.textContent = 'Unsubscribe';
        btn.onclick = async () => { if (!confirm('Remove "' + sub.label + '" and delete its local copy?')) return; await unsubscribe(sub.path); renderCurrent(); renderBrowse(); };
        li.appendChild(btn);
        ul.appendChild(li);
      }
    }
    $('#subsUp').onclick = () => { if (!browsePath) return; const parts = browsePath.split('/').filter(Boolean); parts.pop(); browsePath = parts.length ? '/' + parts.join('/') : ''; renderBrowse(); };
    $('#subsRefresh').onclick = async () => { const b = $('#subsRefresh'); b.disabled = true; b.textContent = 'Refreshing…'; try { await refreshSubscriptions(); } finally { b.disabled = false; b.textContent = 'Refresh all'; renderCurrent(); } };

    renderBrowse();
    renderCurrent();
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
  function onFileDeleted(path) {
    const rel = String(path).replace(/^\/+/, '');
    const st = syncState(); const lk = rel.toLowerCase(); let changed = false;
    for (const k of Object.keys(st)) { const kk = k.toLowerCase(); if (kk === lk || kk.startsWith(lk + '/')) { delete st[k]; changed = true; } }
    if (changed) setSyncState(st);
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
    worker.postMessage({
      type: 'dbx-token',
      token: t.access_token,
      pathRoot: localStorage.getItem(NS_KEY) || null,
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
        const st = syncState(); let changed = false;
        for (const p of d.paths) { const lk = p.toLowerCase(); for (const k of Object.keys(st)) { if (k.toLowerCase() === lk || k.toLowerCase().startsWith(lk + '/')) { delete st[k]; changed = true; } } }
        if (changed) setSyncState(st);
        return;
      }
      if (d.type === 'sw-opfs-changed' && Array.isArray(d.paths)) {
        const st = syncState(); let changed = false;
        for (const p of d.paths) { if (!st[p]) st[p] = { rev: '', size: 0, syncedMtime: 0 }; else st[p].syncedMtime = 0; changed = true; }
        if (changed) setSyncState(st);
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
  async function serverAppKey() {
    if (_serverAppKey !== null) return _serverAppKey;
    try {
      const res = await fetch('/config', { headers: { Accept: 'application/json' } });
      _serverAppKey = res.ok ? (((await res.json()) || {}).dropboxAppKey || '') : '';
    } catch { _serverAppKey = ''; }
    return _serverAppKey;
  }
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
    // Keep PARENT_KEY + APPKEY_CFG + SUBS_KEY so a reconnect reuses the configured
    // folder/key and re-mirrors the same subscriptions. Drop the local mirror +
    // its pull-state (stale once disconnected; re-pulled on reconnect).
    [TOKENS_KEY, STATE_KEY, INDEX_KEY, CURSOR_KEY, ROOT_KEY, NS_KEY, NS_VER_KEY, EMAIL_KEY, SIG_KEY, SUBSTATE_KEY].forEach(k => localStorage.removeItem(k));
    try { Sandpie.opfs.remove(SUBS_PREFIX).catch(() => {}); } catch {}
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
      root.textContent = connected
        ? (workingRoot() ? ('Syncing to ' + workingRoot()) : 'Resolving folder…')
        : 'Your username is appended to the sync folder automatically.';
    }
  }
  const CLOUD_HTML = `
        <div style="display:flex; align-items:center; gap:0.45rem; padding:0.4rem 0.55rem; margin-bottom:0.6rem; border:1px solid var(--sp-border); border-radius:6px; background:var(--sp-panel);">
          <span id="dbxfullDot" style="width:9px; height:9px; border-radius:50%; flex:none; background:var(--sp-text-dim);"></span>
          <span id="dbxfullStatusText" style="font-size:0.8rem; font-weight:500; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">Not connected</span>
          <span id="dbxfullAccount" style="font-size:0.7rem; color:var(--sp-text-dim); margin-left:auto; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:55%;"></span>
        </div>
        <input id="dbxfullAppKey" autocomplete="off" placeholder="Dropbox app key (Full Dropbox access)" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
        <label style="display:block; font-size:0.7rem; color:var(--sp-text-dim); margin:0 0 0.25rem 0.1rem;">Sync folder</label>
        <input id="dbxfullParent" autocomplete="off" placeholder="${DEFAULT_PARENT}" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
        <button class="ghost" id="dbxfullToggleBtn" style="width:100%;">Connect</button>
        <div id="dbxfullRoot" style="font-size:0.65rem; color:var(--sp-text-dim); margin-top:0.4rem;"></div>
        <button class="ghost" id="dbxfullSubsBtn" title="Browse Dropbox and mirror folders read-only" style="margin-top:0.5rem; width:100%;">📡 Subscriptions…</button>
        <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.78rem; margin-top:0.7rem; cursor:pointer;">
          <input type="checkbox" id="dbxfullDehydrated" style="flex:none; width:16px; height:16px; margin:0; padding:0;">
          <span>On-demand file access</span>
        </label>
        <div style="font-size:0.63rem; color:var(--sp-text-dim); margin:0.2rem 0 0 1.5rem; line-height:1.35;">The AI sees your whole Dropbox tree and fetches a file only when it reads or runs it — no bulk download. <code>_conversations</code>, <code>skills</code>, <code>agents</code> stay fully synced. Fetched files are cleared on reload.</div>
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
    const parent = body.querySelector('#dbxfullParent');
    if (parent) {
      parent.value = localStorage.getItem(PARENT_KEY) || DEFAULT_PARENT;
      // Commit on blur/Enter (not each keystroke) so a half-typed path never syncs.
      parent.addEventListener('change', () => {
        localStorage.setItem(PARENT_KEY, parent.value.trim() || DEFAULT_PARENT);
        renderCloudState();
      });
    }
    body.querySelector('#dbxfullToggleBtn')?.addEventListener('click', toggleConnection);
    body.querySelector('#dbxfullSubsBtn')?.addEventListener('click', openSubscriptionManager);
    const dehyd = body.querySelector('#dbxfullDehydrated');
    if (dehyd) {
      dehyd.checked = dehydrated();
      dehyd.addEventListener('change', () => {
        localStorage.setItem(DEHYDRATED_KEY, dehyd.checked ? '1' : '0');
        pushDbxTokenToSW();
        pushDbxIndexToSW();
        sync({ full: true }).catch(() => {});
      });
    }
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
  //  ⚠️  TEMPORARY ONE-TIME MIGRATION — REMOVE AFTER ALL USERS HAVE MIGRATED.
  //  The old site (gasn2cloud.com/sandpie) synced each user's files to their
  //  Dropbox App folder /Apps/AI_Sandbox. The new site syncs to the team folder
  //  /R+D+I/sandpie/<user>. On a user's first connect, if their new root doesn't
  //  exist yet, locate the old AI_Sandbox folder (the one holding _conversations)
  //  and COPY it to the new root. Non-destructive (copy), guarded (only when the
  //  new root is absent → runs once), best-effort (never blocks sync).
  //  PILOT SAFELY: MIGRATION_DRY_RUN=true LOCATES + logs only (no copy). Once the
  //  console shows the correct source folder, set it to false to copy for real.
  //  TO REMOVE LATER: delete this whole block + the two maybeMigrateAiSandbox()
  //  calls in boot(). Grep token: MIGRATE_AI_SANDBOX
  // ===========================================================================
  const MIGRATE_AI_SANDBOX = true;        // master switch — set false / delete to disable
  const MIGRATION_DRY_RUN  = true;        // true = locate + log only; false = actually copy
  const OLD_APP_FOLDER     = 'AI_Sandbox';
  const OLD_CONV_DIR       = '_conversations';
  let _migrationChecked = false;
  async function dbxMeta(path, pathRoot) {
    // Metadata, or null if absent. Rethrows other errors so the caller can abort.
    // not_found ⇒ absent here. malformed_path ⇒ this path is invalid in THIS
    // namespace (e.g. an /Apps/ virtual path probed under the team path-root) —
    // treat as absent so the caller can fall through to the home namespace.
    try { return await api('/2/files/get_metadata', { path }, { pathRoot }); }
    catch (e) { if (/not_found|malformed_path/.test(String(e && e.message))) return null; throw e; }
  }
  async function findOldRoot() {
    // /Apps/AI_Sandbox, but under a team space it sits beneath the member's folder
    // (e.g. /Ezequiel De Paz/Apps/AI_Sandbox) whose name we can't predict — so try
    // the canonical path in both namespaces, then scan for the _conversations dir.
    for (const pr of [true, false]) {
      if (await dbxMeta('/Apps/' + OLD_APP_FOLDER + '/' + OLD_CONV_DIR, pr)) return { path: '/Apps/' + OLD_APP_FOLDER, pathRoot: pr };
    }
    const tail = new RegExp('/' + OLD_APP_FOLDER + '/' + OLD_CONV_DIR + '$', 'i');
    for (const pr of [true, false]) {
      let data;
      try { data = await api('/2/files/search_v2', { query: OLD_CONV_DIR, options: { file_status: 'active', filename_only: true, max_results: 100 } }, { pathRoot: pr }); }
      catch { continue; }
      for (const m of (data && data.matches) || []) {
        const p = m.metadata && m.metadata.metadata && m.metadata.metadata.path_display;
        if (p && tail.test(p)) return { path: p.slice(0, -(OLD_CONV_DIR.length + 1)), pathRoot: pr };
      }
    }
    return null;
  }
  async function dbxCopyFolder(from, to, pathRoot) {
    const parent = to.slice(0, to.lastIndexOf('/'));
    if (parent) { try { await api('/2/files/create_folder_v2', { path: parent, autorename: false }, { pathRoot }); } catch (_) {} }
    await api('/2/files/copy_v2', { from_path: from, to_path: to, autorename: false }, { pathRoot });
  }
  async function maybeMigrateAiSandbox() {
    if (!MIGRATE_AI_SANDBOX || _migrationChecked) return;
    _migrationChecked = true;
    try {
      const newRoot = workingRoot();
      if (!newRoot) return;
      if (await dbxMeta(newRoot, true)) return;     // new root already set up → skip (one-time guard)
      const old = await findOldRoot();
      if (!old) { console.info('[migrate] AI_Sandbox: nothing to migrate (no old ' + OLD_CONV_DIR + ')'); return; }
      console.info('[migrate] AI_Sandbox: found', JSON.stringify(old), '→', newRoot, MIGRATION_DRY_RUN ? '(DRY RUN — not copying)' : '(copying…)');
      if (MIGRATION_DRY_RUN) return;
      if (old.pathRoot !== true) { console.warn('[migrate] AI_Sandbox: old folder is in the home namespace, not the team root — cross-namespace copy not handled; skipping. Tell the dev.'); return; }
      await dbxCopyFolder(old.path, newRoot, true);
      console.info('[migrate] AI_Sandbox: copied', old.path, '→', newRoot);
    } catch (e) {
      console.warn('[migrate] AI_Sandbox failed (non-fatal):', e && e.message);
    }
  }

  // ===========================================================================
  //  Boot
  // ===========================================================================
  function boot() {
    addSection();
    Sandpie.registerSyncProvider({
      sync, fileStatus, getState: syncState,
      isConnected: () => !!tokens(),
      isReadOnlyPath: (rel) => isUnderSubs(rel),   // subscription mirrors are read-only
      subscriptionsDir: () => SUBS_PREFIX,
      get initialSyncDone() { return initialSyncDone; },
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
        await maybeMigrateAiSandbox();   // MIGRATE_AI_SANDBOX (temporary)
        dbxStatus('', 'connected');
        sync().then(refreshSubscriptions);
      }).catch(e => dbxStatus('Auth failed: ' + e.message, 'error'));
    } else if (tokens()) {
      (async () => {
        try { await ensureWorkingRoot(); await maybeMigrateAiSandbox(); }   // MIGRATE_AI_SANDBOX (temporary)
        catch (e) { console.warn('[dropbox-full] pre-sync:', e && e.message); }
        dbxStatus('', 'connected');
        sync().then(refreshSubscriptions);
      })();
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
