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
