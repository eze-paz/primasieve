/* --------------------------------------------------------------------------
   modules/dropbox.js — Dropbox HTTP API client (Phase 0)
   Extracted: low-level Dropbox API functions
   -------------------------------------------------------------------------- */

function dbxRoute(url) {
  const stripped = url.replace(/^https?:\/\//, '');
  const remote = (document.getElementById('proxyUrl').value || '').trim().replace(/\/$/, '');
  return (remote || '') + '/proxy/' + stripped;
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

function dbxTokens() {
  return JSON.parse(localStorage.getItem('dbx-tokens') || 'null');
}

async function dbxAccessToken() {
  const stored = dbxTokens();
  if (!stored) throw new Error('Dropbox not connected');
  if (Date.now() < stored.expires_at - 60000) return stored.access_token;


  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: stored.refresh_token,
    client_id: stored.app_key,
  });
  const res = await fetch(dbxRoute('https://api.dropboxapi.com/oauth2/token'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!res.ok) throw new Error('Token refresh failed: ' + await res.text());
  const data = await res.json();
  stored.access_token = data.access_token;
  stored.expires_at = Date.now() + data.expires_in * 1000;
  localStorage.setItem('dbx-tokens', JSON.stringify(stored));
  return data.access_token;
}

async function dbxApi(path, body) {
  const token = await dbxAccessToken();
  const res = await fetch(dbxRoute('https://api.dropboxapi.com' + path), {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Dropbox ${path}: ${res.status} ${await res.text()}`);
  return await res.json();
}

async function dbxListFull(folderPath, { recursive = false } = {}) {
  let data = await dbxApi('/2/files/list_folder', {
    path: folderPath === '/' ? '' : folderPath,
    recursive,
    include_deleted: true,
  });
  let entries = data.entries.slice();
  let pageCount = 1;
  while (data.has_more) {

    data = await dbxApi('/2/files/list_folder/continue', { cursor: data.cursor });
    entries = entries.concat(data.entries);
    pageCount++;
  }
  return {
    entries: entries.map(e => ({
      name: e.name,
      kind: e['.tag'],
      path: e.path_display,
      size: e.size,
      rev: e.rev,
      hash: e.content_hash,
      cloudMtime: e.server_modified,
    })),
    cursor: data.cursor,
  };
}

async function dbxListContinue(cursor) {
  let data = await dbxApi('/2/files/list_folder/continue', { cursor });
  let entries = data.entries.slice();
  let pageCount = 1;
  while (data.has_more) {

    data = await dbxApi('/2/files/list_folder/continue', { cursor: data.cursor });
    entries = entries.concat(data.entries);
    pageCount++;
  }
  return {
    entries: entries.map(e => ({
      name: e.name,
      kind: e['.tag'],
      path: e.path_display,
      size: e.size,
      rev: e.rev,
      hash: e.content_hash,
      cloudMtime: e.server_modified,
    })),
    cursor: data.cursor,
  };
}

async function dbxDownload(path, signal) {
  const token = await dbxAccessToken();
  const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/download'), {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      'Dropbox-API-Arg': JSON.stringify({ path }),
      'Content-Type': 'text/plain',
    },
    signal,
  });
  if (!res.ok) throw new Error(`Download ${path}: ${res.status} ${await res.text()}`);




  return new Uint8Array(await res.arrayBuffer());
}

async function dbxUpload(path, content) {
  const token = await dbxAccessToken();
  const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/upload'), {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      'Content-Type': 'application/octet-stream',
      'Dropbox-API-Arg': JSON.stringify({ path, mode: 'overwrite', mute: true, autorename: false }),
    },
    body: content,
  });
  if (!res.ok) throw new Error(`Upload ${path}: ${res.status} ${await res.text()}`);


  return await res.json();
}

async function dbxUploadSessionStart(content, close = true) {
  const token = await dbxAccessToken();
  const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/upload_session/start'), {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      'Content-Type': 'application/octet-stream',
      'Dropbox-API-Arg': JSON.stringify({ close }),
    },
    body: content,
  });
  if (!res.ok) throw new Error(`Upload session start: ${res.status} ${await res.text()}`);
  return await res.json();
}

async function dbxUploadSessionFinishBatch(entries) {
  const token = await dbxAccessToken();
  const res = await fetch(dbxRoute('https://api.dropboxapi.com/2/files/upload_session/finish_batch_v2'), {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ entries }),
  });
  if (!res.ok) throw new Error(`Finish batch: ${res.status} ${await res.text()}`);
  return await res.json();
}

async function dbxUploadBatch(files) {


  const CONCURRENCY = 5;
  const sessions = [];
  for (let i = 0; i < files.length; i += CONCURRENCY) {
    const chunk = files.slice(i, i + CONCURRENCY);
    const results = await Promise.all(chunk.map(async ({ rel, content, s, lm }) => {
      try {
        const session = await dbxUploadSessionStart(content, true);
        return {
          cursor: { session_id: session.session_id, offset: content.byteLength },
          commit: { path: '/' + rel, mode: 'overwrite', mute: true, autorename: false },
          rel, s, lm, content
        };
      } catch (err) {
        console.warn('session start failed:', rel, err);
        return null;
      }
    }));
    sessions.push(...results.filter(Boolean));
  }
  if (sessions.length === 0) return [];
  const entries = sessions.map(s => ({ cursor: s.cursor, commit: s.commit }));
  const result = await dbxUploadSessionFinishBatch(entries);


  if (result['.tag'] === 'async_job_id') {
    console.warn('Unexpected async_job_id from finish_batch_v2:', result.async_job_id);
    return [];
  }
  if (!result.entries) {
    console.warn('Unexpected finish_batch response:', result);
    return [];
  }
  return sessions.map((s, i) => ({ ...s, meta: result.entries[i] }));
}

async function dbxDelete(path, rev = null) {
  const body = { path };
  if (rev) body.parent_rev = rev;
  try {
    return await dbxApi('/2/files/delete_v2', body);
  } catch (e) {
    const msg = String(e.message);
    if (msg.includes('not_found')) return null;
    if (msg.includes('parent_rev') || msg.includes('conflict')) {
      console.warn(`[sync] dbxDelete ${path} skipped — file modified remotely since last sync`);
      return { _skip: true };
    }
    throw e;
  }
}

// Batch delete via Dropbox /2/files/delete_batch — one request for many paths
// instead of N delete_v2 calls. Tolerant of not_found per entry. delete_batch
// may return a result synchronously or hand back an async job we must poll.
async function dbxDeleteBatch(paths) {
  const entries = paths
    .map(p => (String(p).startsWith('/') ? String(p) : '/' + p))
    .map(path => ({ path }));
  if (!entries.length) return;
  let res;
  try { res = await dbxApi('/2/files/delete_batch', { entries }); }
  catch (e) { console.warn('[sync] dbxDeleteBatch failed:', e.message); return; }
  if (res && res['.tag'] === 'async_job_id') {
    const async_job_id = res.async_job_id;
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 600));
      let chk;
      try { chk = await dbxApi('/2/files/delete_batch/check', { async_job_id }); }
      catch (e) { console.warn('[sync] delete_batch/check failed:', e.message); return; }
      if (chk['.tag'] === 'complete') return;
      if (chk['.tag'] === 'failed') { console.warn('[sync] delete_batch failed:', chk.failed); return; }
      // '.tag' === 'in_progress' → keep polling
    }
    console.warn('[sync] delete_batch still in progress after polling window');
  }
}

/* expose to global scope for inline callers during migration */
window.dbxRoute = dbxRoute;
window.b64url = b64url;
window.pkceChallenge = pkceChallenge;
window.dbxTokens = dbxTokens;
window.dbxAccessToken = dbxAccessToken;
window.dbxApi = dbxApi;
window.dbxListFull = dbxListFull;
window.dbxListContinue = dbxListContinue;
window.dbxDownload = dbxDownload;
window.dbxUpload = dbxUpload;
window.dbxUploadSessionStart = dbxUploadSessionStart;
window.dbxUploadSessionFinishBatch = dbxUploadSessionFinishBatch;
window.dbxUploadBatch = dbxUploadBatch;
window.dbxDelete = dbxDelete;
window.dbxDeleteBatch = dbxDeleteBatch;

/* ------------------------------------------------------------------
   Cloud section registration via SandpieMenu
   Runs after DOMContentLoaded so SandpieMenu (inline) is defined.
   ------------------------------------------------------------------ */
document.addEventListener('DOMContentLoaded', function() {
  // If the host page ships the Sandpie sync architecture (modules/cloud-sync.js
  // registers a SyncProvider and owns the cloud section), defer entirely to it.
  // This legacy glue only runs on pages that still drive sync via inline globals
  // (e.g. sandpie.html). dropbox.js itself remains a pure transport library.
  if (window.Sandpie) return;
  if (typeof SandpieMenu === 'undefined') return;
  SandpieMenu.add('cloudSection', {
    title: 'Cloud sync',
    dot: 'dbxDot',
    html: `
      <input id="dbxAppKey" autocomplete="off" placeholder="Dropbox app key" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
      <div class="row">
        <button id="dbxToggleBtn" onclick="dbxToggleConnection()">Connect</button>
        <button class="ghost" id="dbxResyncBtn" onclick="manualResync()" title="Re-pull from Dropbox and reconcile cross-device deletes now">Resync</button>
      </div>
    `,
    onRender(body) {
      const input = body.querySelector('#dbxAppKey');
      if (input) input.addEventListener('input', saveConfig);
      const saved = JSON.parse(localStorage.getItem('dbx-tokens') || 'null');
      if (saved?.app_key && input) input.value = saved.app_key;
    }
  });

  // Boot: set cloud sync dot/button state based on stored tokens
  const tokens = (function() {
    try { return JSON.parse(localStorage.getItem('dbx-tokens') || 'null'); } catch(e) { return null; }
  })();

  const urlParams = new URLSearchParams(location.search);
  const code = urlParams.get('code');
  if (code && typeof dbxExchangeCode === 'function') {
    dbxExchangeCode(code).then(function() {
      history.replaceState({}, '', location.pathname);
      dbxStatus('', 'connected');
      if (typeof sync === 'function') sync();
    }).catch(function(e) {
      dbxStatus('Auth failed: ' + e.message, 'error');
    });
  } else if (tokens) {
    dbxStatus('', 'connected');
    if (typeof sync === 'function') sync();
  }
});


/* ==========================================================================
   Cloud sync engine (merged from modules/cloud-sync.js).
   Self-contained IIFE; consumes the dbx* transport defined above + window.Sandpie.
   No-ops if either is missing, so this file stays usable as a pure transport lib.
   ========================================================================== */
(function () {
  'use strict';

  // ---- persistent state (localStorage) -------------------------------------
  const SYNC_STATE_KEY = 'sandpie-sync-state';
  const CLOUD_INDEX_KEY = 'sandpie-cloud-index';
  const DBX_CURSOR_KEY = 'sandpie-dbx-cursor';
  const DBX_REDIRECT = location.origin + location.pathname;

  let _syncing = false;
  let initialSyncDone = !localStorage.getItem('dbx-tokens');
  let dbxBusyCount = 0;
  let _syncCount = 0;             // periodic full-scan cadence counter (see sync())
  const FULL_SCAN_EVERY = 10;     // safety-net: full local opfs.list() reconcile every Nth sync

  function syncState() { return JSON.parse(localStorage.getItem(SYNC_STATE_KEY) || '{}'); }
  function setSyncState(s) { localStorage.setItem(SYNC_STATE_KEY, JSON.stringify(s)); }
  function cloudIndex() { return JSON.parse(localStorage.getItem(CLOUD_INDEX_KEY) || '{}'); }
  function setCloudIndex(idx) { localStorage.setItem(CLOUD_INDEX_KEY, JSON.stringify(idx)); }
  function dbxCursor() { return localStorage.getItem(DBX_CURSOR_KEY) || null; }
  function setDbxCursor(cursor) {
    if (cursor) localStorage.setItem(DBX_CURSOR_KEY, cursor);
    else localStorage.removeItem(DBX_CURSOR_KEY);
  }

  function saveConfig() {
    const el = document.getElementById('dbxAppKey');
    localStorage.setItem('opencode-config', JSON.stringify({ dbxAppKey: el ? el.value : '' }));
  }

  // One-time migrations from older state layouts. Idempotent, no host needed.
  (function migrateLegacyState() {
    if (localStorage.getItem(SYNC_STATE_KEY)) return;
    const oldManifest = JSON.parse(localStorage.getItem('opfs-sync-manifest') || '{}');
    const oldIndex = JSON.parse(localStorage.getItem('dbx-index') || '{}');
    const s = {};
    for (const [path, info] of Object.entries(oldIndex)) {
      if (info.kind !== 'file') continue;
      s[path] = {
        rev: info.rev,
        size: info.size,
        syncedMtime: oldManifest[path] || 0,
      };
    }
    setSyncState(s);
  })();
  (function validateCloudState() {
    const idx = cloudIndex();
    const cursor = dbxCursor();
    if (Object.keys(idx).length > 0 && !cursor) {
      setCloudIndex({});
    }
  })();

  // ---- status dot / busy indicator ------------------------------------------
  function dbxStatus(text, kind) {
    Sandpie.setDot('dbxDot', kind === 'connected' ? 'ok' : kind === 'error' ? 'err' : null);
    const sec = Sandpie.menu.get('cloudSection');
    const btn = sec?.querySelector('#dbxToggleBtn');
    if (btn) btn.textContent = kind === 'connected' ? 'Disconnect' : 'Connect';
  }

  function setDbxBusy(busy) {
    dbxBusyCount = Math.max(0, dbxBusyCount + (busy ? 1 : -1));
    const sec = Sandpie.menu.get('cloudSection');
    const dot = sec?.querySelector('#dbxDot');
    if (!dot) return;
    if (dbxBusyCount > 0) dot.classList.add('busy');
    else dot.classList.remove('busy');
  }

  // ---- connect / disconnect / OAuth -----------------------------------------
  function dbxToggleConnection() {
    if (dbxTokens()) dbxDisconnect();
    else dbxConnect();
  }

  async function dbxConnect() {
    const appKey = (document.getElementById('dbxAppKey').value || '').trim();
    if (!appKey) { dbxStatus('Enter your app key first', 'error'); return; }
    saveConfig();
    const { verifier, challenge } = await pkceChallenge();
    localStorage.setItem('dbx-pkce', JSON.stringify({
      verifier,
      app_key: appKey,
      ts: Date.now(),
    }));
    const params = new URLSearchParams({
      client_id: appKey,
      response_type: 'code',
      redirect_uri: DBX_REDIRECT,
      code_challenge: challenge,
      code_challenge_method: 'S256',
      token_access_type: 'offline',
    });
    location.href = 'https://www.dropbox.com/oauth2/authorize?' + params.toString();
  }

  function dbxDisconnect() {
    localStorage.removeItem('dbx-tokens');
    localStorage.removeItem(SYNC_STATE_KEY);
    localStorage.removeItem('dbx-index');
    localStorage.removeItem('opfs-sync-manifest');
    localStorage.removeItem(CLOUD_INDEX_KEY);
    localStorage.removeItem(DBX_CURSOR_KEY);
    dbxStatus('Not connected', 'disconnected');
    Sandpie.refreshFiles();
  }

  async function dbxExchangeCode(code) {
    const stashed = JSON.parse(localStorage.getItem('dbx-pkce') || 'null');
    if (!stashed) throw new Error('Missing PKCE state');
    if (Date.now() - stashed.ts > 10 * 60 * 1000) {
      localStorage.removeItem('dbx-pkce');
      throw new Error('PKCE state expired — please reconnect');
    }
    const { verifier, app_key: appKey } = stashed;
    const body = new URLSearchParams({
      code,
      grant_type: 'authorization_code',
      client_id: appKey,
      code_verifier: verifier,
      redirect_uri: DBX_REDIRECT,
    });
    const res = await fetch(dbxRoute('https://api.dropboxapi.com/oauth2/token'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!res.ok) throw new Error('Code exchange failed: ' + await res.text());
    const data = await res.json();
    localStorage.setItem('dbx-tokens', JSON.stringify({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at: Date.now() + data.expires_in * 1000,
      app_key: appKey,
    }));
    localStorage.removeItem('dbx-pkce');
  }

  // ---- cloud listing (rolling cursor index) ---------------------------------
  async function cloudListAll() {
    const storedCursor = dbxCursor();
    const existingIndex = cloudIndex();
    if (storedCursor && Object.keys(existingIndex).length > 0) {
      try {
        const result = await dbxListContinue(storedCursor);
        const delta = [];   // [rel, entry] for entries that changed this cycle
        for (const e of result.entries) {
          let rel = e.path.replace(/^\/+/, '');
          if (!rel) continue;
          const prefixes = ['files/', 'Apps/sandpie/', 'App/'];
          for (const p of prefixes) {
            if (rel.toLowerCase().startsWith(p.toLowerCase())) {
              rel = rel.slice(p.length);
              break;
            }
          }
          if (rel.toLowerCase().startsWith(BULK_TMP_NAME)) continue;  // ignore staging folder
          if (e.kind === 'deleted') {
            delete existingIndex[rel];
          } else {
            existingIndex[rel] = e;
            delta.push([rel, e]);
          }
        }
        setDbxCursor(result.cursor);
        setCloudIndex(existingIndex);
        return { index: existingIndex, delta };
      } catch (err) {
        console.warn('Cursor sync failed, falling back to full sync:', err.message);
        setDbxCursor(null);
      }
    }
    const result = await dbxListFull('/', { recursive: true });
    const out = {};
    for (const e of result.entries) {
      let rel = e.path.replace(/^\/+/, '');
      if (!rel) continue;
      const prefixes = ['files/', 'Apps/sandpie/', 'App/'];
      for (const p of prefixes) {
        if (rel.toLowerCase().startsWith(p.toLowerCase())) {
          rel = rel.slice(p.length);
          break;
        }
      }
      if (rel.toLowerCase().startsWith(BULK_TMP_NAME)) continue;  // ignore staging folder
      if (e.kind !== 'deleted') {
        out[rel] = e;
      }
    }
    setDbxCursor(result.cursor);
    setCloudIndex(out);
    return { index: out, delta: null };   // delta === null => full listing, treat all entries as changed
  }

  async function pruneOrphanDirs(cloud) {
    const opfs = Sandpie.opfs;
    const source = cloud ? Object.keys(cloud) : Object.keys(syncState());
    const cloudPaths = new Set();
    for (const k of source) {
      const lower = k.toLowerCase();
      cloudPaths.add(lower);
      const segs = lower.split('/');
      for (let i = 1; i < segs.length; i++) cloudPaths.add(segs.slice(0, i).join('/'));
    }
    let pruned = 0;
    let changed = true;
    while (changed) {
      changed = false;
      let all;
      try { all = await opfs.listAll(''); } catch { return pruned; }

      all.sort((a, b) => b.path.split('/').length - a.path.split('/').length);
      for (const e of all) {
        if (e.kind !== 'directory') continue;
        if (cloudPaths.has(e.path.toLowerCase())) continue;
        let children;
        try { children = await opfs.listDir(e.path); } catch { continue; }
        if (children.length) continue;
        try { await opfs.remove(e.path); pruned++; changed = true; } catch {}
      }
    }
    return pruned;
  }

  // ---- bulk download (bounded-parallel per-file) ----------------------------
  // Pulling changed files one /files/download at a time, serially, is O(N)
  // blocking round-trips — a 1000-file first sync can take ~an hour. We instead
  // fetch them through a bounded worker pool: still O(N) requests, but the wall
  // clock is ~N/CONCURRENCY. This path is strictly READ-ONLY — we never copy or
  // stage files inside the user's Dropbox to perform a download. (An earlier
  // copy_batch→download_zip "staging" approach was removed: it duplicated the
  // user's data into their own synced tree, which propagated to every device and
  // could leave a full duplicate behind on any interruption.)
  const BULK_DL_CONCURRENCY = 32;  // parallel per-file download workers
  // Legacy staging-folder name from that removed approach. Kept ONLY so any folder
  // still left behind in a user's Dropbox is ignored by cloudListAll (see the
  // filters there) instead of being synced down as if it were real content.
  const BULK_TMP_NAME = 'sandpie-sync-tmp';

  // Bounded-parallel per-file download. Failures are logged and omitted (left for
  // the next sync), matching the resilience of the old serial loop.
  async function bulkParallelDownload(items) {
    const out = new Map();
    let idx = 0;
    async function worker() {
      while (idx < items.length) {
        const it = items[idx++];
        try { out.set(it.rel, await dbxDownload(it.cloudPath)); }
        catch (err) { console.warn('[sync] download failed:', it.rel, err); }
      }
    }
    const n = Math.min(BULK_DL_CONCURRENCY, items.length);
    await Promise.all(Array.from({ length: n }, worker));
    return out;
  }

  // Fetch every file in `items` through the parallel pool, then write to OPFS and
  // advance sync state. Files that fail this round are simply retried next sync.
  //   item = { rel, cloudPath, e, mode: 'full' | 'mtimeOnly' }
  async function bulkDownload(items, state, opfs) {
    if (!items.length) return;
    const contents = await bulkParallelDownload(items);
    for (const it of items) {
      const content = contents.get(it.rel);
      if (!content) continue;                          // failed this round; retried next sync
      await opfs.write(it.rel, content);
      const mtime = await Sandpie.opfsMtime(it.rel);
      if (it.mode === 'full' || !state[it.rel]) {
        state[it.rel] = { rev: it.e.rev, size: it.e.size, syncedMtime: mtime };
      } else {
        state[it.rel].syncedMtime = mtime;
        state[it.rel].size = it.e.size;
      }
      contents.delete(it.rel);                         // release memory as we go
    }
  }

  // ---- the sync engine ------------------------------------------------------
  //   opts.full — force a full local reconcile (used by manualResync / initial sync).
  async function sync(opts = {}) {
    if (!dbxTokens()) return;
    if (_syncing) return;
    if (Sandpie.isGenerating()) return;
    _syncing = true;
    setDbxBusy(true);
    _syncCount++;
    const opfs = Sandpie.opfs;
    const openFilePath = Sandpie.openFilePath();
    try {
      dbxStatus('', 'connected');
      const { index: cloud, delta } = await cloudListAll();
      const state = syncState();

      // A "full" pass walks every local file to catch writes that never emitted a
      // dirty signal. Otherwise the push side is event-driven (files marked dirty
      // via file:changed / sw-opfs-changed → syncedMtime === 0). We force it on the
      // first sync, on manual resync, every Nth cycle, and whenever the remote was
      // re-listed in full (delta === null).
      const fullScan = !!opts.full || !initialSyncDone || delta === null
        || (_syncCount % FULL_SCAN_EVERY === 0);

      // Reconcile remote deletions: anything tracked but no longer in the cloud
      // index was deleted remotely (the cursor reported it). Drop the clean local
      // copy; keep it if it was modified locally since the last sync.
      let removedAny = false;
      for (const path of Object.keys(state)) {
        if (cloud[path]) continue;
        const s = state[path];
        const lm = await Sandpie.opfsMtime(path);
        if (lm > 0 && lm > s.syncedMtime) continue;
        try { await opfs.remove(path); } catch {}
        delete state[path];
        removedAny = true;
      }

      // Pull: only evaluate cloud entries that changed this cycle (the cursor
      // delta), or every entry on a full listing. Downloads are deferred into
      // `toDownload` and fetched by the bounded-parallel pool. See bulkDownload().
      const toConsider = delta === null ? Object.entries(cloud) : delta;
      const toDownload = [];
      for (const [path, e] of toConsider) {
        if (e.kind !== 'file') continue;
        const s = state[path];
        const localExists = await opfs.exists(path);
        if (!s) {
          if (localExists) {
            state[path] = {
              rev: e.rev, size: e.size,
              syncedMtime: await Sandpie.opfsMtime(path),
            };
          } else {
            toDownload.push({ rel: path, cloudPath: e.path, e, mode: 'full' });
          }
          continue;
        }
        const cloudChanged = s.rev !== e.rev;
        const localDirty = localExists && (await Sandpie.opfsMtime(path)) > s.syncedMtime;
        if (path === openFilePath) continue;
        if (cloudChanged && localDirty) continue;
        if (cloudChanged) {
          toDownload.push({ rel: path, cloudPath: e.path, e, mode: 'full' });
          continue;
        }
        if (!localExists) {
          toDownload.push({ rel: path, cloudPath: e.path, e, mode: 'mtimeOnly' });
          continue;
        }
        state[path].size = e.size;
      }
      await bulkDownload(toDownload, state, opfs);

      // Push: collect dirty files. Fast path = files an event marked dirty
      // (syncedMtime === 0) — no per-file OPFS walk. Safety-net full scan walks
      // every local file and compares mtime, catching any write that slipped
      // through without an event.
      const dirty = [];
      if (fullScan) {
        let opfsRels = [];
        try { opfsRels = await opfs.list(); } catch {}
        for (const rel of opfsRels) {
          if (rel === openFilePath) continue;
          const lm = await Sandpie.opfsMtime(rel);
          const s = state[rel];
          if (s && lm <= s.syncedMtime) continue;
          dirty.push({ rel, lm, s });
        }
      } else {
        for (const rel of Object.keys(state)) {
          if (rel === openFilePath) continue;
          if (state[rel].syncedMtime !== 0) continue;       // not event-marked dirty
          if (!(await opfs.exists(rel))) continue;          // marked dirty, then deleted
          dirty.push({ rel, lm: await Sandpie.opfsMtime(rel), s: state[rel] });
        }
      }
      if (dirty.length) console.log('[sandpie] sync: uploading', dirty.length, 'changed file(s)');

      const BATCH_SIZE = 50;
      for (let i = 0; i < dirty.length; i += BATCH_SIZE) {
        const chunk = dirty.slice(i, i + BATCH_SIZE);

        const files = await Promise.all(chunk.map(async ({ rel, s, lm }) => {
          const content = await opfs.readBytes(rel);
          return { rel, content, s, lm };
        }));
        try {
          const results = await dbxUploadBatch(files);
          for (const r of results) {
            if (r.meta && r.meta['.tag'] === 'success') {
              state[r.rel] = {
                rev: r.meta.rev || (r.s && r.s.rev) || '',
                size: r.meta.size != null ? r.meta.size : (r.s && r.s.size != null ? r.s.size : r.content.byteLength),
                syncedMtime: r.lm,
              };
            } else {
              console.warn('batch item failed:', r.rel, r.meta);
            }
          }
        } catch (err) {
          console.warn('batch upload failed:', err);
        }
      }
      setSyncState(state);

      // Only prune empty dirs after a deletion or full reconcile, and only rebuild
      // the file/conversation lists when something actually changed — idle cycles
      // do neither.
      if (removedAny || fullScan) await pruneOrphanDirs(cloud);
      if (toDownload.length || dirty.length || removedAny) {
        await Sandpie.refreshFiles();
        await Sandpie.refreshConversations();
      }
    } catch (e) {
      dbxStatus('Sync failed: ' + e.message, 'error');
      console.warn('sync:', e);
    } finally {
      initialSyncDone = true;
      setDbxBusy(false);
      _syncing = false;
    }
  }

  async function manualResync() {
    if (!dbxTokens()) {
      dbxStatus('Not connected', 'disconnected');
      return;
    }
    const btn = document.getElementById('dbxResyncBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Resyncing…'; }
    try {
      await sync({ full: true });   // manual resync always does a full local reconcile
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Resync'; }
    }
  }

  // ---- file browser integration ---------------------------------------------
  // Per-file status the page's file list renders. null => "not tracked" so the
  // file browser falls back to a plain local view.
  function fileStatus(path, opfsMtime) {
    const s = syncState()[path];
    if (!s) return null;
    return opfsMtime <= s.syncedMtime ? 'synced' : 'modified';
  }

  // React to a file the page wrote (saveConv, file edits, imports): mark it dirty
  // so the next sync uploads it via the fast path — no full opfs.list() scan
  // needed. Mirrors the sw-opfs-changed handler used for Python writes.
  function onFileChanged(path) {
    const rel = String(path).replace(/^\/+/, '');
    if (!rel) return;
    const state = syncState();
    if (state[rel]) state[rel].syncedMtime = 0;
    else state[rel] = { rev: '', size: 0, syncedMtime: 0 };
    setSyncState(state);
  }

  // React to a file the page deleted: drop it (and any children) from sync state
  // synchronously, then best-effort delete the cloud copy.
  function onFileDeleted(path) {
    const rel = String(path).replace(/^\/+/, '');
    const st = syncState();
    const lk = rel.toLowerCase();
    let changed = false;
    for (const k of Object.keys(st)) {
      const kk = k.toLowerCase();
      if (kk === lk || kk.startsWith(lk + '/')) { delete st[k]; changed = true; }
    }
    if (changed) setSyncState(st);
    if (dbxTokens()) dbxDelete('/' + rel).catch(() => {});
  }

  // OPFS changes reported by the service worker (e.g. files written by Python).
  function wireServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.addEventListener('message', (ev) => {
      const d = ev.data;
      if (!d) return;
      if (d.type === 'opfs-deleted-by-python' && Array.isArray(d.paths)) {
        (async () => {
          if (!dbxTokens()) return;
          // Delete the cloud copies: one batched delete_batch for many paths,
          // a single delete_v2 for one.
          if (d.paths.length > 1) {
            try { await dbxDeleteBatch(d.paths.map(p => '/' + p)); } catch {}
          } else if (d.paths.length === 1) {
            try { await dbxDelete('/' + d.paths[0]); } catch {}
          }
          // Drop the deleted paths (and any children) from sync state.
          const state = syncState();
          let changed = false;
          for (const path of d.paths) {
            const lk = path.toLowerCase();
            for (const k of Object.keys(state)) {
              if (k.toLowerCase() === lk || k.toLowerCase().startsWith(lk + '/')) {
                delete state[k];
                changed = true;
              }
            }
          }
          if (changed) setSyncState(state);
          try { await Sandpie.refreshFiles(); } catch {}
        })();
        return;
      }
      if (d.type === 'sw-opfs-changed' && Array.isArray(d.paths)) {
        console.log('[sandpie] ← SW notified:', d.paths);
        const state = syncState();
        let changed = false;
        for (const path of d.paths) {
          if (!state[path]) {
            state[path] = { rev: '', size: 0, syncedMtime: 0 };
            changed = true;
          } else {
            state[path].syncedMtime = 0;
            changed = true;
          }
        }
        if (changed) setSyncState(state);
        return;
      }
    });
  }

  // ---- sidebar "Cloud sync" section -----------------------------------------
  function addSection() {
    Sandpie.menu.add('cloudSection', {
      title: 'Cloud sync',
      dot: 'dbxDot',
      html: `
        <input id="dbxAppKey" autocomplete="off" placeholder="Dropbox app key" style="width:100%; padding:0.4rem; margin-bottom:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.85rem;">
        <div class="row">
          <button id="dbxToggleBtn">Connect</button>
          <button class="ghost" id="dbxResyncBtn" title="Re-pull from Dropbox and reconcile cross-device deletes now">Resync</button>
        </div>
      `,
      onRender(body) {
        const input = body.querySelector('#dbxAppKey');
        if (input) {
          input.addEventListener('input', saveConfig);
          const saved = (function () {
            try { return JSON.parse(localStorage.getItem('dbx-tokens') || 'null'); } catch (e) { return null; }
          })();
          if (saved?.app_key) input.value = saved.app_key;
        }
        body.querySelector('#dbxToggleBtn')?.addEventListener('click', dbxToggleConnection);
        body.querySelector('#dbxResyncBtn')?.addEventListener('click', manualResync);
      },
    });
  }

  // ---- boot -----------------------------------------------------------------
  function boot() {
    // Require both the host contract and the Dropbox transport. If either is
    // absent, register nothing — the page runs local-only with no errors.
    if (!window.Sandpie || typeof dbxTokens !== 'function') {
      console.warn('[cloud-sync] host (Sandpie) or transport (dropbox.js) missing — cloud sync disabled');
      return;
    }

    addSection();

    Sandpie.registerSyncProvider({
      sync,
      fileStatus,
      getState: syncState,
      isConnected: () => !!dbxTokens(),
      get initialSyncDone() { return initialSyncDone; },
    });

    Sandpie.events.on('file:deleted', onFileDeleted);
    Sandpie.events.on('file:changed', onFileChanged);
    wireServiceWorker();
    setInterval(() => { if (!document.hidden) sync(); }, 60000);

    // OAuth return, or initial sync if already connected.
    const code = new URLSearchParams(location.search).get('code');
    if (code) {
      dbxExchangeCode(code).then(function () {
        history.replaceState({}, '', location.pathname);
        dbxStatus('', 'connected');
        sync();
      }).catch(function (e) {
        dbxStatus('Auth failed: ' + e.message, 'error');
      });
    } else if (dbxTokens()) {
      dbxStatus('', 'connected');
      sync();
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
