/* --------------------------------------------------------------------------
   modules/cloud-sync.js — Cloud sync engine (Dropbox-backed)

   Owns the sync *policy*: reconciliation, the rolling cloud index, OAuth, the
   "Cloud sync" sidebar section, and periodic/manual sync. It depends only on:
     • window.Sandpie  — the host contract (opfs, events, registerSyncProvider…)
     • window.dbx*     — the Dropbox *transport* from modules/dropbox.js
   If either is missing (e.g. dropbox.js not included) it registers nothing and
   the page runs local-only — no ReferenceErrors. Remove this <script> and cloud
   sync simply disappears; the page and core chat are unaffected.
   -------------------------------------------------------------------------- */

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
            const content = await dbxDownload(e.path);
            await opfs.write(path, content);
            state[path] = {
              rev: e.rev, size: e.size,
              syncedMtime: await Sandpie.opfsMtime(path),
            };
          }
          continue;
        }
        const cloudChanged = s.rev !== e.rev;
        const localDirty = localExists && (await Sandpie.opfsMtime(path)) > s.syncedMtime;
        if (path === openFilePath) continue;
        if (cloudChanged && localDirty) continue;
        if (cloudChanged) {
          const content = await dbxDownload(e.path);
          await opfs.write(path, content);
          state[path] = {
            rev: e.rev, size: e.size,
            syncedMtime: await Sandpie.opfsMtime(path),
          };
          continue;
        }

        if (!localExists) {
          const content = await dbxDownload(e.path);
          await opfs.write(path, content);
          state[path].syncedMtime = await Sandpie.opfsMtime(path);
        }
        state[path].size = e.size;
      }

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
          const state = syncState();
          let changed = false;
          for (const path of d.paths) {
            try { await dbxDelete('/' + path); } catch {}
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
