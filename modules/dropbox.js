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

/* --------------------------------------------------------------------------
   Bulk download primitives (copy_batch_v2 → download_zip → delete_v2)
   Used by modules/cloud-sync.js to pull many changed files in ~O(1) round-trips
   instead of one /files/download per file. See bulkDownload() in the sync engine below.
   -------------------------------------------------------------------------- */

async function dbxCopyBatch(entries) {
  // entries: [{ from_path, to_path }, ...]  — keep each call ≤ 1000 entries.
  // Returns a launch result: { '.tag': 'complete', entries } or
  // { '.tag': 'async_job_id', async_job_id }.
  return await dbxApi('/2/files/copy_batch_v2', { entries, autorename: false });
}

async function dbxCopyBatchCheck(asyncJobId) {
  // Returns { '.tag': 'in_progress' } or { '.tag': 'complete', entries }.
  return await dbxApi('/2/files/copy_batch/check_v2', { async_job_id: asyncJobId });
}

async function dbxDownloadZip(path, signal) {
  // Downloads a whole folder as one zip. Dropbox caps this at 20 GB / 10,000 files.
  const token = await dbxAccessToken();
  const res = await fetch(dbxRoute('https://content.dropboxapi.com/2/files/download_zip'), {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      'Dropbox-API-Arg': JSON.stringify({ path }),
      'Content-Type': 'text/plain',
    },
    signal,
  });
  if (!res.ok) throw new Error(`Download zip ${path}: ${res.status} ${await res.text()}`);
  return new Uint8Array(await res.arrayBuffer());
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
window.dbxCopyBatch = dbxCopyBatch;
window.dbxCopyBatchCheck = dbxCopyBatchCheck;
window.dbxDownloadZip = dbxDownloadZip;

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
          }
        }
        setDbxCursor(result.cursor);
        setCloudIndex(existingIndex);
        return existingIndex;
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
    return out;
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

  // ---- bulk download (staged-zip + parallel fallback) -----------------------
  // Pulling changed files one /files/download at a time is O(N) network round-
  // trips — a 1000-file first sync on a new device can take ~an hour. Instead we
  // copy the exact changed files into a temp Dropbox folder (server-side, metadata
  // only), download that whole folder as ONE zip, unzip locally, then delete the
  // temp folder: ~O(1) round-trips for any N up to the zip cap. Small batches and
  // any failure fall back to bounded-parallel per-file downloads.
  const BULK_TMP_NAME = 'sandpie-sync-tmp';
  const BULK_ZIP_THRESHOLD = 20;   // files; below this, parallel per-file is simpler
  const BULK_COPY_MAX = 1000;      // max entries per copy_batch_v2 call
  const BULK_ZIP_FILE_MAX = 9000;  // max files per download_zip (Dropbox caps at 10k / 20GB)
  const BULK_DL_CONCURRENCY = 12;  // parallel per-file workers

  function bulkSleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  // Only attempt the staged-zip path if every primitive it needs is present
  // (transport helpers + the fflate unzip lib loaded by the host page).
  function zipBulkAvailable() {
    return typeof dbxCopyBatch === 'function'
        && typeof dbxCopyBatchCheck === 'function'
        && typeof dbxDownloadZip === 'function'
        && typeof dbxDelete === 'function'
        && !!(window.fflate && window.fflate.unzip);
  }

  // Resolve a copy_batch_v2 launch result, polling check_v2 until the async job
  // completes. Per-entry failures are tolerated by the caller (missing files just
  // fall through to the per-file path), so we only wait for overall completion.
  async function waitForCopyBatch(res) {
    if (res && res['.tag'] === 'complete') return;
    if (!res || res['.tag'] !== 'async_job_id') {
      throw new Error('copy_batch: unexpected response ' + JSON.stringify(res));
    }
    const jobId = res.async_job_id;
    for (let i = 0; i < 120; i++) {
      await bulkSleep(Math.min(750 + i * 250, 3000));
      const chk = await dbxCopyBatchCheck(jobId);
      if (chk['.tag'] === 'complete') return;
      // '.tag' === 'in_progress' → keep polling
    }
    throw new Error('copy_batch: timed out waiting for async job');
  }

  function unzipBulk(u8) {
    return new Promise((resolve, reject) => {
      window.fflate.unzip(u8, (err, files) => (err ? reject(err) : resolve(files)));
    });
  }

  // Copy one chunk of files into the temp folder, download it as a zip, unzip, and
  // map each entry back to its relative path. Adds rel -> Uint8Array to `out`.
  async function bulkZipChunk(chunk, out) {
    // Derive temp folder within the app's actual Dropbox scope (e.g. /Apps/sandpie/sandpie-sync-tmp)
    // rather than using a hardcoded root path that may be outside the app's permission scope.
    const firstItem = chunk[0];
    const base = firstItem.cloudPath.slice(0, firstItem.cloudPath.length - firstItem.rel.length);
    const tmpPath = base.replace(/\/+$/, '') + '/' + BULK_TMP_NAME;
    try { await dbxDelete(tmpPath); } catch (e) {}   // clear any crashed-run leftover
    try {
      for (let i = 0; i < chunk.length; i += BULK_COPY_MAX) {
        const entries = chunk.slice(i, i + BULK_COPY_MAX).map((it) => ({
          from_path: it.cloudPath,
          to_path: tmpPath + '/' + it.rel,
        }));
        await waitForCopyBatch(await dbxCopyBatch(entries));
      }
      const files = await unzipBulk(await dbxDownloadZip(tmpPath));
      const byRel = new Map(chunk.map((it) => [it.rel.toLowerCase(), it]));
      for (const [name, bytes] of Object.entries(files)) {
        if (name.endsWith('/')) continue;                              // directory entry
        let rel = name;
        if (rel.startsWith(BULK_TMP_NAME + '/')) rel = rel.slice(BULK_TMP_NAME.length + 1);
        const it = byRel.get(rel.toLowerCase());
        if (it) out.set(it.rel, bytes);
      }
    } finally {
      try { await dbxDelete(tmpPath); } catch (e) {}
    }
  }

  async function bulkDownloadViaZip(items) {
    const out = new Map();
    for (let i = 0; i < items.length; i += BULK_ZIP_FILE_MAX) {
      await bulkZipChunk(items.slice(i, i + BULK_ZIP_FILE_MAX), out);
    }
    return out;
  }

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

  // Fetch every file in `items`, then write to OPFS and advance sync state. Uses
  // the staged-zip path for large batches (falling back to per-file on any error)
  // and bounded-parallel per-file for the remainder.
  //   item = { rel, cloudPath, e, mode: 'full' | 'mtimeOnly' }
  async function bulkDownload(items, state, opfs) {
    if (!items.length) return;
    let contents = new Map();
    if (items.length >= BULK_ZIP_THRESHOLD && zipBulkAvailable()) {
      try {
        contents = await bulkDownloadViaZip(items);
      } catch (err) {
        console.warn('[sync] staged-zip bulk download failed — falling back to per-file:', err);
        contents = new Map();
      }
    }
    const remaining = items.filter((it) => !contents.has(it.rel));
    if (remaining.length) {
      const perFile = await bulkParallelDownload(remaining);
      for (const [rel, bytes] of perFile) contents.set(rel, bytes);
    }
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
  async function sync() {
    if (!dbxTokens()) return;
    if (_syncing) return;
    if (Sandpie.isGenerating()) return;
    _syncing = true;
    setDbxBusy(true);
    const opfs = Sandpie.opfs;
    const openFilePath = Sandpie.openFilePath();
    try {
      dbxStatus('', 'connected');
      const cloud = await cloudListAll();
      const state = syncState();

      for (const path of Object.keys(state)) {
        if (cloud[path]) continue;
        const s = state[path];
        const lm = await Sandpie.opfsMtime(path);
        if (lm > 0 && lm > s.syncedMtime) continue;
        try { await opfs.remove(path); } catch {}
        delete state[path];
      }

      // Decide per file what to pull (unchanged policy), but defer the actual
      // downloads into `toDownload` so they can be fetched in bulk rather than
      // one blocking round-trip at a time. See bulkDownload() above.
      const toDownload = [];
      for (const [path, e] of Object.entries(cloud)) {
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

      let opfsRels = [];
      try { opfsRels = await opfs.list(); } catch {}
      const dirty = [];
      for (const rel of opfsRels) {
        if (rel === openFilePath) continue;
        const lm = await Sandpie.opfsMtime(rel);
        const s = state[rel];
        if (s && lm <= s.syncedMtime) {
          console.log('[sandpie] sync skip (clean):', rel);
          continue;
        }
        console.log('[sandpie] sync dirty:', rel, 'lm=', lm, 'synced=', s?.syncedMtime);
        dirty.push({ rel, lm, s });
      }
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
      await pruneOrphanDirs(cloud);

      await Sandpie.refreshFiles();
      await Sandpie.refreshConversations();
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
      await sync();
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
