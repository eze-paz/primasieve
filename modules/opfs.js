// sandpie OPFS core — filesystem primitives and path utilities

// File-viewer preview type sets + text-preview size cap (used by openFile below).
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif']);
const VIDEO_EXTS = new Set(['mp4', 'webm', 'mov', 'm4v']);
const AUDIO_EXTS = new Set(['mp3', 'wav', 'ogg', 'oga', 'flac', 'm4a', 'aac']);
const TEXT_PREVIEW_CAP = 200_000;

function splitPath(path) {
  const parts = String(path).split('/').filter(Boolean);
  const name = parts.pop();
  return { parts, name };
}
const opfs = {
  async root() { return await navigator.storage.getDirectory(); },

  async resolveDir(parts, { create = false } = {}) {
    let dir = await this.root();
    for (const p of parts) dir = await dir.getDirectoryHandle(p, { create });
    return dir;
  },
  async read(path) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts);
    const handle = await dir.getFileHandle(name);
    return await (await handle.getFile()).text();
  },

  async readBytes(path) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts);
    const handle = await dir.getFileHandle(name);
    const file = await handle.getFile();
    return new Uint8Array(await file.arrayBuffer());
  },
  async write(path, content) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts, { create: true });
    const handle = await dir.getFileHandle(name, { create: true });
    const w = await handle.createWritable();
    await w.write(content);
    await w.close();
  },
  async remove(path) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts);
    await dir.removeEntry(name, { recursive: true });

    try {
      const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (sw) sw.postMessage({ type: 'opfs-removed', paths: [path] });
    } catch (_) {}
  },

  async exists(path) {
    try {
      const { parts, name } = splitPath(path);
      const dir = await this.resolveDir(parts);
      await dir.getFileHandle(name);
      return true;
    } catch { return false; }
  },
  async mkdir(path) {
    const parts = String(path).split('/').filter(Boolean);
    await this.resolveDir(parts, { create: true });
  },

  async listDir(path = '') {
    const parts = String(path).split('/').filter(Boolean);
    const dir = await this.resolveDir(parts);
    const out = [];
    for await (const [n, h] of dir.entries()) out.push({ name: n, kind: h.kind });
    return out.sort((a, b) => a.kind !== b.kind ? (a.kind === 'directory' ? -1 : 1) : a.name.localeCompare(b.name));
  },

  async list(prefix = '') {
    const out = [];
    const walk = async (dir, p) => {
      for await (const [n, h] of dir.entries()) {
        const full = p ? `${p}/${n}` : n;
        if (h.kind === 'file') out.push(full);
        else await walk(h, full);
      }
    };
    const startParts = String(prefix).split('/').filter(Boolean);
    const start = await this.resolveDir(startParts);
    await walk(start, prefix.replace(/^\/+|\/+$/g, ''));
    return out.sort();
  },

  async listAll(prefix = '') {
    const out = [];
    const walk = async (dir, p) => {
      for await (const [n, h] of dir.entries()) {
        const full = p ? `${p}/${n}` : n;
        out.push({ path: full, kind: h.kind });
        if (h.kind === 'directory') await walk(h, full);
      }
    };
    const startParts = String(prefix).split('/').filter(Boolean);
    const start = await this.resolveDir(startParts);
    await walk(start, prefix.replace(/^\/+|\/+$/g, ''));
    return out;
  },
};
function joinPath(folder, name) {
  if (folder === '/' || folder === '') return '/' + name;
  return folder.replace(/\/$/, '') + '/' + name;
}



/* ---------------------------------------------------------------------------
   File primitives extracted from sandpie-test.html
   --------------------------------------------------------------------------- */

/* metadata helpers */
opfs.lastModified = async function(path) {
  try {
    const { parts, name } = splitPath(path);
    let dir = await navigator.storage.getDirectory();
    for (const p of parts) {
      dir = await dir.getDirectoryHandle(p);
    }
    const handle = await dir.getFileHandle(name);
    const file = await handle.getFile();
    return file.lastModified;
  } catch (e) {
    return 0;
  }
};

opfs.getFileSize = async function(path) {
  try {
    const parts = path.split('/').filter(Boolean);
    const name = parts.pop();
    const dir = await opfs.resolveDir(parts);
    const handle = await dir.getFileHandle(name);
    return (await handle.getFile()).size;
  } catch {}
  const s = (Sandpie.syncProvider()?.getState?.() || {})[path];
  return s && s.size || 0;
};

opfs.getFolderSize = async function(path) {
  const prefix = path ? path.toLowerCase() + '/' : '';
  let total = 0;
  const state = Sandpie.syncProvider()?.getState?.() || {};
  for (const k of Object.keys(state)) {
    const kl = k.toLowerCase();
    if (prefix && !kl.startsWith(prefix)) continue;
    if (prefix && kl.length <= prefix.length) continue;
    total += state[k].size || 0;
  }
  try {
    for (const f of await opfs.list(path)) {
      const full = (path ? path + '/' : '') + f;
      if (!state[full]) {
        try {
          const parts = full.split('/').filter(Boolean);
          const name = parts.pop();
          const dir = await opfs.resolveDir(parts);
          const handle = await dir.getFileHandle(name);
          total += (await handle.getFile()).size;
        } catch {}
      }
    }
  } catch {}
  return total;
};

opfs.formatSize = function(bytes) {
  if (!bytes || bytes < 0) return '';
  const units = ['B', 'kB', 'MB', 'GB', 'TB'];
  let u = 0;
  while (bytes >= 1024 && u < units.length - 1) { bytes /= 1024; u++; }
  return (u === 0 ? bytes : bytes.toFixed(1).replace(/\.0$/, '')) + units[u];
};

opfs.currentPath = function() {
  return (document.getElementById('opfsPath').value || '').trim().replace(/^\/+|\/+$/g, '');
};

/* Read-only fence. Subscription mirrors are owned by the sync provider, which
   declares which paths are read-only and the reserved dir name. Falls back to
   "everything writable" when the provider doesn't implement it (e.g. the
   app-folder dropbox.js used by sandpie.html). */
opfs._roProvider = function() { try { return window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider(); } catch { return null; } };
opfs.isReadOnly = function(path) { const p = opfs._roProvider(); try { return !!(p && p.isReadOnlyPath && p.isReadOnlyPath(path)); } catch { return false; } };
opfs.subsDirName = function() { const p = opfs._roProvider(); try { return (p && p.subscriptionsDir && p.subscriptionsDir()) || null; } catch { return null; } };



/* ---------------------------------------------------------------------------
   File browser, viewer, and editor — extracted from sandpie-test.html
   --------------------------------------------------------------------------- */

let _activeCtxMenu = null;

opfs.closeCtxMenu = function() {
  _activeCtxMenu?.remove();
  _activeCtxMenu = null;
};

opfs.showContextMenu = function(x, y, items) {
  opfs.closeCtxMenu();
  const menu = document.createElement('div');
  menu.className = 'ctx-menu';
  menu.setAttribute('data-chrome', '');
  for (const item of items) {
    const btn = document.createElement('button');
    btn.textContent = item.label;
    if (item.danger) btn.className = 'danger';
    btn.onclick = (e) => { e.stopPropagation(); opfs.closeCtxMenu(); item.action(); };
    menu.appendChild(btn);
  }
  document.body.appendChild(menu);
  const r = menu.getBoundingClientRect();
  let left = x, top = y;
  if (left + r.width > window.innerWidth) left = window.innerWidth - r.width - 8;
  if (top + r.height > window.innerHeight) top = window.innerHeight - r.height - 8;
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
  _activeCtxMenu = menu;
};



/* Open file viewer/editor */
opfs.openFile = async function(fullKey, name, opts = {}) {

  let file;
  try {
    const { parts, name: fname } = splitPath(fullKey);
    const dir = await opfs.resolveDir(parts);
    const handle = await dir.getFileHandle(fname);
    file = await handle.getFile();
  } catch (e) {
    Sandpie.addMsg('err', `Could not open ${fullKey}: ${e.message}`);
    return;
  }
  opfs.closeFile();                 // single viewer instance — close any open one first
  window._openFilePath = fullKey;
  const ext = (name.split('.').pop() || '').toLowerCase();
  // Render beside the chat (desktop) when asked. The side panel is mobile-blocked,
  // so on mobile we always fall back to the modal overlay (mount() handles this).
  const side = opts.prefer === 'side' && !opfs._isMobile();
  const overlay = document.createElement('div');
  overlay.className = 'file-viewer';
  overlay.setAttribute('data-chrome', '');
  const panel = document.createElement('div');
  panel.className = 'panel fv-panel';
  const header = document.createElement('header');
  const title = document.createElement('span');
  title.className = 'title';
  title.textContent = '/' + fullKey;
  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent = `${file.size.toLocaleString()} bytes`;

  const mdBtn = document.createElement('button');
  mdBtn.className = 'mode';
  mdBtn.style.display = 'none';
  const pencilBtn = document.createElement('button');
  pencilBtn.className = 'mode';
  pencilBtn.textContent = '✎';
  pencilBtn.title = 'Edit';
  pencilBtn.style.display = 'none';
  const saveBtn = document.createElement('button');
  saveBtn.className = 'mode';
  saveBtn.textContent = '💾';
  saveBtn.title = 'Save (Ctrl+S)';
  saveBtn.style.display = 'none';
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '✕';
  closeBtn.title = 'Close (Esc)';
  header.append(title, meta, mdBtn, pencilBtn, saveBtn, closeBtn);
  const body = document.createElement('div');
  body.className = 'body';
  panel.append(header, body);
  overlay.appendChild(panel);

  // Mount the panel: into the side panel (desktop, prefer:'side') or the modal
  // overlay (default, and the mobile fallback since the side panel is hidden there).
  const mount = (closeFn) => {
    closeBtn.onclick = closeFn;
    if (side) {
      const host = document.getElementById('messagesSide');
      if (host) {
        overlay.classList.add('side');   // restyle the .file-viewer to fill the column (not a modal)
        host.appendChild(overlay);
        host.classList.add('viewer-mode');
        document.body.classList.add('viewer-side-open');
        return;
      }
    }
    overlay._close = closeFn;
    overlay.addEventListener('click', e => { if (e.target === overlay) closeFn(); });
    document.body.appendChild(overlay);
  };
  if (IMAGE_EXTS.has(ext)) {
    const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;
    const img = document.createElement('img'); img.src = url; body.appendChild(img);
    mount(opfs.closeFile); return;
  }
  if (VIDEO_EXTS.has(ext)) {
    const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;
    const v = document.createElement('video'); v.src = url; v.controls = true; body.appendChild(v);
    mount(opfs.closeFile); return;
  }
  if (AUDIO_EXTS.has(ext)) {
    const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;
    const a = document.createElement('audio'); a.src = url; a.controls = true; body.appendChild(a);
    mount(opfs.closeFile); return;
  }
  if (ext === 'pdf') {
    const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;
    const f = document.createElement('iframe');
    f.setAttribute('data-chrome', '');
    f.src = url;
    f.style.cssText = 'width:100%;height:70vh;border:0;background:#fff';
    body.appendChild(f);
    mount(opfs.closeFile); return;
  }

  const text = await file.text();
  const sample = text.slice(0, 4000);
  const repl = (sample.match(/�/g) || []).length;
  const looksBinary = repl > 50 && repl / Math.max(sample.length, 1) > 0.01;
  if (looksBinary) {
    const pre = document.createElement('pre');
    pre.textContent = '(binary file — preview unavailable)';
    body.appendChild(pre);
    mount(opfs.closeFile); return;
  }
  const isMd = ext === 'md' || ext === 'markdown';
  const isHtml = ext === 'html' || ext === 'htm' || ext === 'svg';
  const previewable = isMd || isHtml;   // can show a rendered preview + a source toggle
  const editable = text.length <= TEXT_PREVIEW_CAP && !opfs.isReadOnly(fullKey);   // subscription mirrors are view-only

  let mode = previewable ? 'preview' : 'raw';
  let current = text;
  let textareaEl = null;
  const isDirty = () => mode === 'edit' && textareaEl && textareaEl.value !== current;
  const refreshTitle = () => { title.textContent = (isDirty() ? '• ' : '') + '/' + fullKey; };
  function refreshButtons() {
    mdBtn.style.display = (previewable && mode !== 'edit') ? '' : 'none';
    mdBtn.textContent = mode === 'preview' ? 'Source' : 'Preview';
    mdBtn.title = mode === 'preview' ? 'Show raw source' : 'Show rendered preview';
    pencilBtn.style.display = (editable && mode !== 'edit') ? '' : 'none';
    saveBtn.style.display = mode === 'edit' ? '' : 'none';
  }
  async function render() {
    body.innerHTML = '';
    textareaEl = null;
    if (mode === 'edit') {
      const ta = document.createElement('textarea');
      ta.className = 'editor';
      ta.spellcheck = false;
      ta.value = current;
      ta.addEventListener('input', refreshTitle);
      ta.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault(); doSave();
        }
      });
      body.appendChild(ta);
      textareaEl = ta;
      ta.focus();
    } else if (mode === 'preview' && isMd) {
      const div = document.createElement('div');
      div.className = 'md-preview';
      div.textContent = 'Loading preview…';
      body.appendChild(div);
      try {
        await opfs.getMarked();
        div.innerHTML = window.marked.parse(current);
      } catch (e) {
        div.textContent = '(failed to load markdown renderer — showing raw)\n\n' + current;
      }
    } else if (mode === 'preview' && isHtml) {
      const f = document.createElement('iframe');
      f.className = 'fv-frame';
      f.setAttribute('data-chrome', '');
      f.src = 'opfs/' + fullKey;   // served live by the SW (scripts run)
      f.style.cssText = 'width:100%;height:70vh;border:0;background:#fff;';
      body.appendChild(f);
    } else {
      const pre = document.createElement('pre');
      pre.textContent = current.length > TEXT_PREVIEW_CAP
        ? current.slice(0, TEXT_PREVIEW_CAP) + `\n…[truncated, full size ${current.length.toLocaleString()} chars]`
        : current;
      body.appendChild(pre);
    }
    refreshButtons();
    refreshTitle();
  }
  mdBtn.onclick = () => { mode = (mode === 'preview') ? 'raw' : 'preview'; render(); };
  pencilBtn.onclick = () => { mode = 'edit'; render(); };
  async function doSave() {
    if (!textareaEl) return;
    const newContent = textareaEl.value;
    try {
      await opfs.write(fullKey, newContent);
      Sandpie.events.emit('file:changed', fullKey);
      current = newContent;
      meta.textContent = `${new Blob([newContent]).size.toLocaleString()} bytes`;
      refreshTitle();
      await window.refreshFileList();
    } catch (e) {
      Sandpie.addMsg('err', `Could not save ${fullKey}: ${e.message}`);
    }
  }
  saveBtn.onclick = doSave;
  function attemptClose() {
    if (isDirty() && !confirm('Unsaved changes will be lost. Close anyway?')) return;
    opfs.closeFile();
  }
  mount(attemptClose);
  await render();
}
opfs._isMobile = function() {
  try { return window.matchMedia('(max-width: 768px), (hover: none) and (pointer: coarse)').matches; }
  catch (_) { return false; }
};
opfs.closeFile = function() {
  window._openFilePath = null;
  // revoke any blob URLs (image/video/audio/pdf), modal or side
  document.querySelectorAll('.fv-panel[data-blob-url]').forEach(p => {
    try { URL.revokeObjectURL(p.dataset.blobUrl); } catch (_) {}
  });
  document.querySelectorAll('.file-viewer').forEach(el => el.remove());   // modal + side overlays
  const host = document.getElementById('messagesSide');
  if (host) host.classList.remove('viewer-mode');
  document.body.classList.remove('viewer-side-open');
};

opfs.getMarked = function() {
  if (!window.markedPromise) {
    window.markedPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/marked@13/marked.min.js';
      s.onload = () => resolve(window.marked);
      s.onerror = () => reject(new Error('failed to load marked'));
      document.head.appendChild(s);
    });
  }
  return window.markedPromise;
};

opfs.up = function() {
  const $ = id => document.getElementById(id);
  const cur = ($('opfsPath').value || '').trim() || '/';
  if (cur === '/' || cur === '') return;
  $('opfsPath').value = cur.replace(/\/[^/]+\/?$/, '') || '/';
  if (typeof refreshFileList === 'function') refreshFileList();
};

opfs.createFolder = async function() {
  const $ = id => document.getElementById(id);
  const name = prompt('Folder name:');
  if (!name || !name.trim()) return;
  const clean = name.trim().replace(/[\\/:*?"<>|]/g, '_');
  if (!clean) return;
  const path = opfs.currentPath();
  if (opfs.isReadOnly(path)) { alert('Read-only subscription folder — cannot create here.'); return; }
  const fullPath = window.opfsJoin(path, clean);
  try {
    await opfs.mkdir(fullPath);
    if (typeof Sandpie !== 'undefined') Sandpie.events.emit('file:changed', fullPath);
    if (typeof refreshFileList === 'function') await refreshFileList();
  } catch (e) {
    console.warn('mkdir failed:', fullPath, e);
    alert('Could not create folder: ' + e.message);
  }
};

opfs.createFile = async function() {
  const $ = id => document.getElementById(id);
  const name = prompt('File name:');
  if (!name || !name.trim()) return;
  const clean = name.trim().replace(/[\\/:*?"<>|]/g, '_');
  if (!clean) return;
  const path = opfs.currentPath();
  if (opfs.isReadOnly(path)) { alert('Read-only subscription folder — cannot create here.'); return; }
  const fullPath = window.opfsJoin(path, clean);
  try {
    await opfs.write(fullPath, '');
    if (typeof Sandpie !== 'undefined') Sandpie.events.emit('file:changed', fullPath);
    if (typeof refreshFileList === 'function') await refreshFileList();
  } catch (e) {
    console.warn('create file failed:', fullPath, e);
    alert('Could not create file: ' + e.message);
  }
};

// Announce a freshly uploaded/written OPFS file so it (a) shows up in the file
// sidebar and (b) is synced into the run_python (Pyodide) MEMFS mount at /files
// — so the model can read it the moment it replies. Every upload entry point
// (attach button, drag-and-drop, programmatic writes) routes through here. The
// SW only live-syncs once Pyodide has booted; before that the file is already in
// OPFS and gets picked up when the /files mount populates. The sidebar refresh
// is debounced so a multi-file drop refreshes the list just once.
let _notifyRefreshT = null;
opfs.notifyUpload = function(path) {
  try { if (typeof Sandpie !== 'undefined') Sandpie.events.emit('file:changed', path); } catch (_) {}
  try {
    const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
    if (sw) sw.postMessage({ type: 'opfs-changed', paths: [path] });
  } catch (_) {}
  clearTimeout(_notifyRefreshT);
  _notifyRefreshT = setTimeout(() => { try { opfs.refreshFileList(); } catch (_) {} }, 60);
};

// Pick a non-colliding path under dir/ so an upload never clobbers an existing
// file of the same name (foo.txt → foo-2.txt → …).
opfs.uniquePath = async function(dir, name) {
  const safe = String(name).replace(/[\\/:*?"<>|]/g, '_') || 'file';
  const first = window.opfsJoin(dir, safe);
  if (!(await opfs.exists(first))) return first;
  const dot = safe.lastIndexOf('.');
  const stem = dot > 0 ? safe.slice(0, dot) : safe;
  const ext = dot > 0 ? safe.slice(dot) : '';
  for (let i = 2; i < 1000; i++) {
    const p = window.opfsJoin(dir, `${stem}-${i}${ext}`);
    if (!(await opfs.exists(p))) return p;
  }
  return window.opfsJoin(dir, `${stem}-${Date.now()}${ext}`);
};

// Open the OS file picker and upload the chosen file(s) straight into an OPFS
// folder (the file browser's "Upload files" action). Unlike the composer attach
// / drag-drop, this is a pure workspace upload — files land in dirPath, show in
// the sidebar, and sync into the run_python /files mount, without touching the
// message composer. A single reused hidden input avoids leaking nodes on cancel.
let _uploadInput = null;
opfs.promptUpload = function(dirPath) {
  if (opfs.isReadOnly(dirPath)) { alert('This is a read-only folder — uploads are disabled here.'); return; }
  if (!_uploadInput) {
    _uploadInput = document.createElement('input');
    _uploadInput.type = 'file';
    _uploadInput.multiple = true;
    _uploadInput.style.display = 'none';
    document.body.appendChild(_uploadInput);
  }
  _uploadInput.onchange = async () => {
    const files = Array.from(_uploadInput.files || []);
    _uploadInput.value = '';
    for (const f of files) {
      try {
        const dest = await opfs.uniquePath(dirPath, f.name);
        await opfs.write(dest, f);
        opfs.notifyUpload(dest);   // sidebar + run_python /files mount
      } catch (e) { console.warn('[sandpie] upload failed:', f.name, e); }
    }
  };
  _uploadInput.click();
};

opfs.uploadEntry = async function(entry, dirPath) {
  if (entry.isFile) {
    const file = await new Promise(r => entry.file(r));
    const destPath = window.opfsJoin(dirPath, entry.name);
    await opfs.write(destPath, file);
    opfs.notifyUpload(destPath);
  } else if (entry.isDirectory) {
    const sub = window.opfsJoin(dirPath, entry.name);
    await opfs.mkdir(sub);
    const batch = [];
    const reader = entry.createReader();
    while (true) {
      const entries = await new Promise(r => reader.readEntries(r));
      if (!entries.length) break;
      batch.push(...entries);
    }
    for (const child of batch) await opfs.uploadEntry(child, sub);
  }
};


let subsExpanded = false;

opfs.refreshFileList = async function() {
  const ul = document.getElementById('fileList');
  const path = opfs.currentPath();

  let opfsList = [];
  try { opfsList = await opfs.listDir(path); } catch {}
  const localMap = new Map();
  for (const e of opfsList) localMap.set(e.name, e.kind === 'directory' ? 'folder' : 'file');

  const state = (window.Sandpie && Sandpie.syncProvider()?.getState?.()) || {};
  const prefix = path ? path + '/' : '';
  const remoteMap = new Map();
  for (const k of Object.keys(state)) {
    const kl = k.toLowerCase();
    if (!kl.startsWith(prefix.toLowerCase())) continue;
    const rest = k.slice(prefix.length);
    if (!rest) continue;
    if (rest.includes('/')) {
      const firstSeg = rest.split('/')[0];
      if (!remoteMap.has(firstSeg)) remoteMap.set(firstSeg, 'folder');
    } else {
      remoteMap.set(rest, 'file');
    }
  }
  const names = new Set([...localMap.keys(), ...remoteMap.keys()]);
  const SUBS = opfs.subsDirName();   // reserved subscription-mirror dir (null if the provider has none)
  // At root the subscription mirror is surfaced as its own "Subscriptions"
  // group (below), not as a regular inline folder.
  if (path === '' && SUBS) names.delete(SUBS);

  const frag = document.createDocumentFragment();

  const renderItem = (it) => {
    const li = document.createElement('li');
    const btn = document.createElement('span');
    btn.className = 'name' + (it.kind === 'folder' ? ' folder' : '');
    const isPlaceholder = it.kind === 'file' && it.status === 'cloud';
    const ro = opfs.isReadOnly(it.fullKey);
    const kindIcon = it.kind === 'folder' ? '📁 ' : (isPlaceholder ? '☁ ' : '📄 ');
    btn.textContent = kindIcon + it.name;
    btn.title = isPlaceholder ? 'cloud placeholder · click to download' : `${it.kind} · ${it.status}${ro ? ' · read-only' : ''}`;
    if (it.kind === 'folder') {
      btn.onclick = () => { document.getElementById('opfsPath').value = '/' + it.fullKey; opfs.refreshFileList(); };
    } else {
      btn.onclick = () => opfs.openFile(it.fullKey, it.name);
    }
    li.append(btn);
    const sizeSpan = document.createElement('span');
    sizeSpan.className = 'file-size';
    sizeSpan.textContent = opfs.formatSize(it.size);
    li.append(sizeSpan);
    li.addEventListener('contextmenu', (ev) => {
      ev.preventDefault();
      const menuItems = [];
      menuItems.push({ label: 'Copy path', action: () => { navigator.clipboard.writeText(it.fullKey).catch(() => {}); } });
      if (!ro) {
        menuItems.push({ label: 'Upload files', action: () => opfs.promptUpload(opfsCurrentPath()) });
        menuItems.push({ label: 'New folder', action: () => opfs.createFolder() });
        menuItems.push({ label: 'New file', action: () => opfs.createFile() });
      }
      if (it.kind === 'file') {
        menuItems.push({ label: 'Open in new tab', action: () => window.open('opfs/' + it.fullKey, '_blank') });
        menuItems.push({ label: 'Download', action: () => window.open('opfs/' + it.fullKey + '?download=1', '_blank') });
      }
      if (!ro) menuItems.push({ label: 'Delete', danger: true, action: async () => {
        try {
          await opfs.remove(it.fullKey);
          if (window.Sandpie) Sandpie.events.emit('file:deleted', it.fullKey);
          await opfs.refreshFileList();
        } catch (e) { console.warn('delete failed:', it.fullKey, e); }
      }});
      opfs.showContextMenu(ev.clientX, ev.clientY, menuItems);
    });
    frag.appendChild(li);
  };

  // Regular entries in the current directory
  const items = [];
  for (const name of names) {
    const local = localMap.get(name);
    const remote = remoteMap.get(name);
    const kind = local === 'folder' || remote === 'folder' ? 'folder' : 'file';
    const fullKey = opfsJoin(path, name);
    let status = 'synced';
    if (kind === 'folder') {
      status = local && remote ? 'synced' : (local ? 'local' : 'cloud');
    } else if (!local) {
      status = 'cloud';
    } else if (!remote) {
      status = 'local';
    } else {
      const s = state[fullKey];
      const lastMod = await opfs.lastModified(fullKey);
      status = lastMod > 0 && s && s.syncedMtime != null && lastMod <= s.syncedMtime ? 'synced' : 'modified';
    }
    items.push({ name, kind, status, fullKey });
  }
  await Promise.all(items.map(async (it) => {
    it.size = it.kind === 'folder' ? await opfs.getFolderSize(it.fullKey) : await opfs.getFileSize(it.fullKey);
  }));
  items.sort((a, b) => a.kind !== b.kind ? (a.kind === 'folder' ? -1 : 1) : a.name.localeCompare(b.name));

  // Subscriptions (read-only Dropbox mirrors) — shown at root only, as a
  // collapsible group instead of an inline folder.
  let subItems = [];
  if (path === '' && SUBS) {
    let subDirs = [];
    try { subDirs = (await opfs.listDir(SUBS)).filter(e => e.kind === 'directory'); } catch {}
    subItems = await Promise.all(subDirs.map(async (e) => {
      const fullKey = SUBS + '/' + e.name;
      return { name: e.name, kind: 'folder', status: 'synced', fullKey, size: await opfs.getFolderSize(fullKey) };
    }));
    subItems.sort((a, b) => a.name.localeCompare(b.name));
  }

  const fcEl = document.getElementById('fileCount');
  if (fcEl) fcEl.textContent = items.length ? `${items.length}` : '';

  if (!items.length && !subItems.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = (window.Sandpie && Sandpie.initialSyncDone()) ? '(empty)' : 'Loading…';
    ul.replaceChildren(li);
    return;
  }

  for (const it of items) renderItem(it);

  if (subItems.length) {
    const header = document.createElement('li');
    header.className = 'shared-toggle';
    header.textContent = `${subsExpanded ? '▾' : '▸'} Subscriptions (${subItems.length})`;
    header.title = 'Read-only Dropbox folder mirrors';
    header.onclick = () => { subsExpanded = !subsExpanded; opfs.refreshFileList(); };
    frag.appendChild(header);
    if (subsExpanded) subItems.forEach(renderItem);
  }

  ul.replaceChildren(frag);
};

/* --- backward compat shims for browser/viewer/editor --- */
window.closeCtxMenu = function() { return opfs.closeCtxMenu(); };
window.showContextMenu = function(x, y, items) { return opfs.showContextMenu(x, y, items); };

window.openFileViewer = function(fullKey, name) { return opfs.openFile(fullKey, name); };
window.closeFileViewer = function() { return opfs.closeFile(); };
window.getMarked = function() { return opfs.getMarked(); };
window.opfsUp = function() { return opfs.up(); };
window.createNewFolder = function() { return opfs.createFolder(); };
window.createNewFile = function() { return opfs.createFile(); };
window.uploadEntry = function(entry, dirPath) { return opfs.uploadEntry(entry, dirPath); };


/* --- backward compatibility shims (so sandpie-test.html call sites still work) --- */

window._openFilePath = null;
window.markedPromise = null;

window.opfsLastModified = function(path) { return opfs.lastModified(path); };
window.getFileSize = function(path) { return opfs.getFileSize(path); };
window.getFolderSize = function(path) { return opfs.getFolderSize(path); };
window.formatSize = function(bytes) { return opfs.formatSize(bytes); };
window.opfsCurrentPath = function() { return opfs.currentPath(); };
window.opfsJoin = function(base, child) { return base ? base + '/' + child : child; };
window.refreshFileList = function() { return opfs.refreshFileList(); };


window.opfs = opfs;
window.splitPath = splitPath;
window.joinPath = joinPath;

/* File-browser UI wiring (moved from sandpie-test.html). Deferred to
   DOMContentLoaded because opfs.js loads in <head>, before #fileList/#opfsPath
   exist in the body. */
function initFileBrowser() {
  document.addEventListener('click', closeCtxMenu);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeCtxMenu(); });
  window.addEventListener('blur', closeCtxMenu);

  // Esc closes an open file viewer
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const v = document.querySelector('.file-viewer');
      if (v) (v._close || closeFileViewer)();
    }
  });

  const opfsPathEl = document.getElementById('opfsPath');
  if (opfsPathEl) {
    opfsPathEl.addEventListener('change', refreshFileList);
    opfsPathEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') refreshFileList(); });
  }

  const list = document.getElementById('fileList');
  if (list) {
    list.addEventListener('contextmenu', (ev) => {
      if (ev.target.closest('li')) return;
      ev.preventDefault();
      if (opfs.isReadOnly(opfsCurrentPath())) return;   // read-only subscription area — no create
      showContextMenu(ev.clientX, ev.clientY, [
        { label: 'Upload files', action: () => opfs.promptUpload(opfsCurrentPath()) },
        { label: 'New folder', action: () => createNewFolder() },
        { label: 'New file', action: () => createNewFile() },
      ]);
    });
    // File drops are handled app-wide by the window-level drop zone
    // (SandpieImages.initWindowDrop), which attaches them to the composer and
    // uploads to OPFS + MEMFS — so the sidebar no longer has its own drop target.
  }

  refreshFileList();
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initFileBrowser);
} else {
  initFileBrowser();
}
