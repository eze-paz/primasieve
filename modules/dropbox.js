// modules/dropbox.js — Dropbox sync module for sandpie
// Extracted from sandpie-test.html monolith
//
// Usage:
//   import { createDropboxSync } from './modules/dropbox.js';
//   const dbx = createDropboxSync({ ...deps });
//   await dbx.init();

const DBX_REDIRECT = location.origin + location.pathname;
const DBX_CURSOR_KEY = 'sandpie-dbx-cursor';

// ---------------------------------------------------------------------------
// PKCE
// ---------------------------------------------------------------------------
function b64url(buf) {
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function pkceChallenge() {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: b64url(hash) };
}

// ---------------------------------------------------------------------------
// Core Dropbox API
// ---------------------------------------------------------------------------
export function createDropboxSync({
  route,
  onStatus,
  onProgress,
  setBusy,
  opfs,
  syncState,
  setSyncState,
  cloudIndex,
  setCloudIndex,
  splitPath,
  refreshFileList,
  refreshConversationList,
  convStreams,
} = {}) {

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
    const res = await fetch(route('https://api.dropboxapi.com/oauth2/token'), {
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

  async function connect(appKey) {
    if (!appKey) { onStatus('Enter your app key first', 'error'); return; }
    const { verifier, challenge } = await pkceChallenge();
    localStorage.setItem('dbx-pkce', JSON.stringify({ verifier, app_key: appKey, ts: Date.now() }));
    const params = new URLSearchParams({
      client_id: appKey, response_type: 'code', redirect_uri: DBX_REDIRECT,
      code_challenge: challenge, code_challenge_method: 'S256', token_access_type: 'offline',
    });
    location.href = 'https://www.dropbox.com/oauth2/authorize?' + params.toString();
  }

  function disconnect() {
    localStorage.removeItem('dbx-tokens');
    localStorage.removeItem('sandpie-sync-state');
    localStorage.removeItem('dbx-index');
    localStorage.removeItem('opfs-sync-manifest');
    localStorage.removeItem('sandpie-cloud-index');
    localStorage.removeItem(DBX_CURSOR_KEY);
    onStatus('Not connected', 'disconnected');
    if (refreshFileList) refreshFileList();
  }

  async function exchangeCode(code) {
    const stashed = JSON.parse(localStorage.getItem('dbx-pkce') || 'null');
    if (!stashed) throw new Error('Missing PKCE state');
    if (Date.now() - stashed.ts > 10 * 60 * 1000) {
      localStorage.removeItem('dbx-pkce');
      throw new Error('PKCE state expired — please reconnect');
    }
    const { verifier, app_key: appKey } = stashed;
    const body = new URLSearchParams({
      code, grant_type: 'authorization_code', client_id: appKey,
      code_verifier: verifier, redirect_uri: DBX_REDIRECT,
    });
    const res = await fetch(route('https://api.dropboxapi.com/oauth2/token'), {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body.toString(),
    });
    if (!res.ok) throw new Error('Code exchange failed: ' + await res.text());
    const data = await res.json();
    localStorage.setItem('dbx-tokens', JSON.stringify({
      access_token: data.access_token, refresh_token: data.refresh_token,
      expires_at: Date.now() + data.expires_in * 1000, app_key: appKey,
    }));
    localStorage.removeItem('dbx-pkce');
  }

  function toggleConnection(appKey) {
    if (dbxTokens()) disconnect(); else connect(appKey);
  }

  async function dbxApi(path, body) {
    const token = await dbxAccessToken();
    const res = await fetch(route('https://api.dropboxapi.com' + path), {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Dropbox ${path}: ${res.status} ${await res.text()}`);
    return await res.json();
  }

  async function dbxListFull(folderPath, { recursive = false } = {}) {
    let data = await dbxApi('/2/files/list_folder', {
      path: folderPath === '/' ? '' : folderPath, recursive, include_deleted: true,
    });
    let entries = data.entries.slice(), pageCount = 1;
    while (data.has_more) {
      onProgress(`listing… page ${pageCount}`);
      data = await dbxApi('/2/files/list_folder/continue', { cursor: data.cursor });
      entries = entries.concat(data.entries); pageCount++;
    }
    return {
      entries: entries.map(e => ({ name: e.name, kind: e['.tag'], path: e.path_display, size: e.size, rev: e.content_hash, cloudMtime: e.server_modified })),
      cursor: data.cursor,
    };
  }

  async function dbxListContinue(cursor) {
    let data = await dbxApi('/2/files/list_folder/continue', { cursor });
    let entries = data.entries.slice(), pageCount = 1;
    while (data.has_more) {
      onProgress(`checking changes… page ${pageCount}`);
      data = await dbxApi('/2/files/list_folder/continue', { cursor: data.cursor });
      entries = entries.concat(data.entries); pageCount++;
    }
    return {
      entries: entries.map(e => ({ name: e.name, kind: e['.tag'], path: e.path_display, size: e.size, rev: e.content_hash, cloudMtime: e.server_modified })),
      cursor: data.cursor,
    };
  }

  async function dbxDownload(path, signal) {
    const token = await dbxAccessToken();
    const res = await fetch(route('https://content.dropboxapi.com/2/files/download'), {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Dropbox-API-Arg': JSON.stringify({ path }), 'Content-Type': 'text/plain' }, signal,
    });
    if (!res.ok) throw new Error(`Download ${path}: ${res.status} ${await res.text()}`);
    return new Uint8Array(await res.arrayBuffer());
  }

  async function dbxDownloadBatch(paths, { concurrency = 5 } = {}) {
    const results = [];
    for (let i = 0; i < paths.length; i += concurrency) {
      const chunk = paths.slice(i, i + concurrency);
      const chunkResults = await Promise.all(chunk.map(async (path) => {
        try { return await dbxDownload(path); } catch (err) { console.warn('download failed:', path, err.message); return null; }
      }));
      results.push(...chunkResults);
    }
    return results;
  }

  async function dbxUpload(path, content) {
    const token = await dbxAccessToken();
    const res = await fetch(route('https://content.dropboxapi.com/2/files/upload'), {
      method: 'POST', headers: {
        Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream',
        'Dropbox-API-Arg': JSON.stringify({ path, mode: 'overwrite', mute: true, autorename: false }),
      }, body: content,
    });
    if (!res.ok) throw new Error(`Upload ${path}: ${res.status} ${await res.text()}`);
    return await res.json();
  }

  async function dbxUploadSessionStart(content, close = true) {
    const token = await dbxAccessToken();
    const res = await fetch(route('https://content.dropboxapi.com/2/files/upload_session/start'), {
      method: 'POST', headers: {
        Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream',
        'Dropbox-API-Arg': JSON.stringify({ close }),
      }, body: content,
    });
    if (!res.ok) throw new Error(`Upload session start: ${res.status} ${await res.text()}`);
    return await res.json();
  }

  async function dbxUploadSessionFinishBatch(entries) {
    const token = await dbxAccessToken();
    const res = await fetch(route('https://api.dropboxapi.com/2/files/upload_session/finish_batch_v2'), {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
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
          return { cursor: { session_id: session.session_id, offset: content.byteLength }, commit: { path: '/' + rel, mode: 'overwrite', mute: true, autorename: false }, rel, s, lm, content };
        } catch (err) { console.warn('session start failed:', rel, err); return null; }
      }));
      sessions.push(...results.filter(Boolean));
    }
    if (sessions.length === 0) return [];
    const entries = sessions.map(s => ({ cursor: s.cursor, commit: s.commit }));
    const result = await dbxUploadSessionFinishBatch(entries);
    if (result['.tag'] === 'async_job_id') { console.warn('Unexpected async_job_id:', result.async_job_id); return []; }
    if (!result.entries) { console.warn('Unexpected finish_batch response:', result); return []; }
    return sessions.map((s, i) => ({ ...s, meta: result.entries[i] }));
  }

  async function dbxDelete(path) {
    try { return await dbxApi('/2/files/delete_v2', { path }); }
    catch (e) { if (String(e.message).includes('not_found')) return null; throw e; }
  }

  function dbxCursor() { return localStorage.getItem(DBX_CURSOR_KEY) || null; }
  function setDbxCursor(cursor) {
    if (cursor) localStorage.setItem(DBX_CURSOR_KEY, cursor);
    else localStorage.removeItem(DBX_CURSOR_KEY);
  }

  const SYNC_STATE_KEY = 'sandpie-sync-state';
  const CLOUD_INDEX_KEY = 'sandpie-cloud-index';

  function _syncState() { return syncState ? syncState() : JSON.parse(localStorage.getItem(SYNC_STATE_KEY) || '{}'); }
  function _setSyncState(s) { setSyncState ? setSyncState(s) : localStorage.setItem(SYNC_STATE_KEY, JSON.stringify(s)); }
  function _cloudIndex() { return cloudIndex ? cloudIndex() : JSON.parse(localStorage.getItem(CLOUD_INDEX_KEY) || '{}'); }
  function _setCloudIndex(idx) { setCloudIndex ? setCloudIndex(idx) : localStorage.setItem(CLOUD_INDEX_KEY, JSON.stringify(idx)); }

  (function migrateLegacyState() {
    if (localStorage.getItem(SYNC_STATE_KEY)) return;
    const oldManifest = JSON.parse(localStorage.getItem('opfs-sync-manifest') || '{}');
    const oldIndex = JSON.parse(localStorage.getItem('dbx-index') || '{}');
    const s = {};
    for (const [path, info] of Object.entries(oldIndex)) {
      if (info.kind !== 'file') continue;
      s[path] = { rev: info.rev, size: info.size, hydrated: oldManifest[path] !== undefined, syncedMtime: oldManifest[path] || 0 };
    }
    _setSyncState(s);
  })();

  (function validateCloudState() {
    const idx = _cloudIndex();
    const cursor = dbxCursor();
    if (Object.keys(idx).length > 0 && !cursor) { _setCloudIndex({}); }
  })();

  async function opfsLastModified(relPath) {
    try {
      const { parts, name } = splitPath(relPath);
      const dir = await opfs.resolveDir(parts);
      const handle = await dir.getFileHandle(name);
      return (await handle.getFile()).lastModified;
    } catch { return 0; }
  }

  function isEagerHydrate(path, size) {
    if (path === '_conversations' || path.startsWith('_conversations/')) return true;
    if (/(?:^|\/)sandpie_[^/]*\.md$/.test(path)) return true;
    if (typeof size === 'number' && size < 64 * 1024) return true;
    return false;
  }

  async function pruneOrphanDirs(cloud) {
    const source = cloud ? Object.keys(cloud) : Object.keys(_syncState());
    const cloudPaths = new Set();
    for (const k of source) {
      const lower = k.toLowerCase();
      cloudPaths.add(lower);
      const segs = lower.split('/');
      for (let i = 1; i < segs.length; i++) cloudPaths.add(segs.slice(0, i).join('/'));
    }
    let pruned = 0, changed = true;
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

  async function cloudListAll() {
    const storedCursor = dbxCursor();
    const existingIndex = _cloudIndex();
    if (storedCursor && Object.keys(existingIndex).length > 0) {
      try {
        const result = await dbxListContinue(storedCursor);
        for (const e of result.entries) {
          let rel = e.path.replace(/^\/+/, '');
          if (!rel) continue;
          const prefixes = ['files/', 'Apps/sandpie/', 'App/'];
          for (const p of prefixes) {
            if (rel.toLowerCase().startsWith(p.toLowerCase())) { rel = rel.slice(p.length); break; }
          }
          if (e.kind === 'deleted') delete existingIndex[rel]; else existingIndex[rel] = e;
        }
        setDbxCursor(result.cursor);
        _setCloudIndex(existingIndex);
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
        if (rel.toLowerCase().startsWith(p.toLowerCase())) { rel = rel.slice(p.length); break; }
      }
      if (e.kind !== 'deleted') out[rel] = e;
    }
    setDbxCursor(result.cursor);
    _setCloudIndex(out);
    return out;
  }

  let _syncing = false;
  let _openFilePath = null;

  function anyStreamGenerating() {
    if (!convStreams) return false;
    for (const s of convStreams.values()) if (s.generating) return true;
    return false;
  }

  async function sync() {
    if (!dbxTokens()) return;
    if (_syncing) return;
    if (anyStreamGenerating()) return;
    _syncing = true;
    setBusy(true);
    try {
      onStatus('', 'connected');
      const cloud = await cloudListAll();
      const state = _syncState();

      for (const path of Object.keys(state)) {
        if (cloud[path]) continue;
        const s = state[path];
        if (s.hydrated) {
          const lm = await opfsLastModified(path);
          if (lm > 0 && lm > s.syncedMtime) continue;
          try { await opfs.remove(path); } catch {}
        }
        delete state[path];
      }

      const downloads = [];
      for (const [path, e] of Object.entries(cloud)) {
        if (e.kind !== 'file') continue;
        const s = state[path];
        const eager = isEagerHydrate(path, e.size);
        const localExists = await opfs.exists(path);

        if (!s) {
          if (localExists) {
            state[path] = { rev: e.rev, size: e.size, hydrated: true, syncedMtime: await opfsLastModified(path) };
          } else if (eager) {
            downloads.push({ path, e, stateKey: path });
          } else {
            state[path] = { rev: e.rev, size: e.size, hydrated: false, syncedMtime: 0 };
          }
          continue;
        }

        const cloudChanged = s.rev !== e.rev;
        const localDirty = localExists && (await opfsLastModified(path)) > s.syncedMtime;
        if (path === _openFilePath) continue;
        if (cloudChanged && localDirty) continue;
        if (cloudChanged) { downloads.push({ path, e, stateKey: path }); continue; }
        if (s.hydrated && !localExists) { state[path].hydrated = false; state[path].syncedMtime = 0; }
        state[path].size = e.size;
      }

      if (downloads.length) {
        onProgress(`downloading ${downloads.length} file(s)…`);
        const results = await dbxDownloadBatch(downloads.map(d => d.e.path));
        for (let i = 0; i < downloads.length; i++) {
          const d = downloads[i], content = results[i];
          if (content) {
            await opfs.write(d.path, content);
            state[d.stateKey] = { rev: d.e.rev, size: d.e.size, hydrated: true, syncedMtime: await opfsLastModified(d.path) };
          }
        }
      }

      let opfsRels = [];
      try { opfsRels = await opfs.list(); } catch {}
      const dirty = [];
      for (const rel of opfsRels) {
        if (rel === _openFilePath) continue;
        const lm = await opfsLastModified(rel);
        const s = state[rel];
        if (s && s.hydrated && lm <= s.syncedMtime) continue;
        dirty.push({ rel, lm, s });
      }
      const BATCH_SIZE = 50;
      for (let i = 0; i < dirty.length; i += BATCH_SIZE) {
        const chunk = dirty.slice(i, i + BATCH_SIZE);
        onProgress(`uploading…(${i + chunk.length}/${dirty.length})`);
        const files = await Promise.all(chunk.map(async ({ rel, s, lm }) => {
          const content = await opfs.readBytes(rel);
          return { rel, content, s, lm };
        }));
        try {
          const results = await dbxUploadBatch(files);
          for (const r of results) {
            if (r.meta && r.meta['.tag'] === 'success') {
              state[r.rel] = {
                rev: (r.meta.content_hash) || (r.s && r.s.rev) || '',
                size: r.meta.size != null ? r.meta.size : (r.s && r.s.size != null ? r.s.size : r.content.byteLength),
                hydrated: true, syncedMtime: r.lm,
              };
            } else { console.warn('batch item failed:', r.rel, r.meta); }
          }
        } catch (err) { console.warn('batch upload failed:', err); }
      }

      _setSyncState(state);
      await pruneOrphanDirs(cloud);
      onProgress('');
      if (refreshFileList) await refreshFileList();
      if (refreshConversationList) await refreshConversationList();
    } catch (e) {
      onProgress(''); onStatus('Sync failed: ' + e.message, 'error'); console.warn('sync:', e);
    } finally {
      onProgress(''); setBusy(false); _syncing = false;
    }
  }

  async function manualResync() {
    if (!dbxTokens()) { onStatus('Not connected', 'disconnected'); return; }
    await sync();
  }

  async function init() {
    const params = new URLSearchParams(location.search);
    const code = params.get('code');
    if (code) {
      try {
        await exchangeCode(code);
        history.replaceState({}, '', location.pathname);
        onStatus('', 'connected');
        await sync();
      } catch (e) { onStatus('Auth failed: ' + e.message, 'error'); }
    } else if (dbxTokens()) {
      onStatus('', 'connected');
      await sync();
    }
  }

  return {
    tokens: dbxTokens, connect, disconnect, toggleConnection, exchangeCode,
    api: dbxApi, listFull: dbxListFull, listContinue: dbxListContinue,
    download: dbxDownload, downloadBatch: dbxDownloadBatch,
    upload: dbxUpload, uploadBatch: dbxUploadBatch, delete: dbxDelete,
    sync, manualResync, cloudListAll,
    setOpenFilePath: (p) => { _openFilePath = p; },
    init,
  };
}
