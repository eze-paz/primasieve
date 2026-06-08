// sandpie OPFS core — filesystem primitives and path utilities
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
opfs.openFile = async function(fullKey, name) {

  let file;
  try {
    const { parts, name: fname } = splitPath(fullKey);
    const dir = await opfs.resolveDir(parts);
    const handle = await dir.getFileHandle(fname);
    file = await handle.getFile();
  } catch (e) {
    Sandpie.Sandpie.addMsg('err', `Could not open ${fullKey}: ${e.message}`);
    return;
  }
  window._openFilePath = fullKey;
  const ext = (name.split('.').pop() || '').toLowerCase();
  const overlay = document.createElement('div');
  overlay.className = 'file-viewer';
  overlay.setAttribute('data-chrome', '');
  const panel = document.createElement('div');
  panel.className = 'panel';
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

  const finalize = (closeFn) => {
    closeBtn.onclick = closeFn;
    overlay._close = closeFn;
    overlay.addEventListener('click', e => { if (e.target === overlay) closeFn(); });
    document.body.appendChild(overlay);
  };
  if (IMAGE_EXTS.has(ext)) {
    const url = URL.createObjectURL(file); overlay.dataset.blobUrl = url;
    const img = document.createElement('img'); img.src = url; body.appendChild(img);
    finalize(opfs.closeFile); return;
  }
  if (VIDEO_EXTS.has(ext)) {
    const url = URL.createObjectURL(file); overlay.dataset.blobUrl = url;
    const v = document.createElement('video'); v.src = url; v.controls = true; body.appendChild(v);
    finalize(opfs.closeFile); return;
  }
  if (AUDIO_EXTS.has(ext)) {
    const url = URL.createObjectURL(file); overlay.dataset.blobUrl = url;
    const a = document.createElement('audio'); a.src = url; a.controls = true; body.appendChild(a);
    finalize(opfs.closeFile); return;
  }
  if (ext === 'pdf') {
    const url = URL.createObjectURL(file); overlay.dataset.blobUrl = url;
    const f = document.createElement('iframe');
    f.setAttribute('data-chrome', '');
    f.src = url;
    f.style.cssText = 'width:100%;height:70vh;border:0;background:#fff';
    body.appendChild(f);
    finalize(opfs.closeFile); return;
  }

  const text = await file.text();
  const sample = text.slice(0, 4000);
  const repl = (sample.match(/�/g) || []).length;
  const looksBinary = repl > 50 && repl / Math.max(sample.length, 1) > 0.01;
  if (looksBinary) {
    const pre = document.createElement('pre');
    pre.textContent = '(binary file — preview unavailable)';
    body.appendChild(pre);
    finalize(opfs.closeFile); return;
  }
  const isMd = ext === 'md' || ext === 'markdown';
  const editable = text.length <= TEXT_PREVIEW_CAP;

  let mode = isMd ? 'rendered' : 'raw';
  let current = text;
  let textareaEl = null;
  const isDirty = () => mode === 'edit' && textareaEl && textareaEl.value !== current;
  const refreshTitle = () => { title.textContent = (isDirty() ? '• ' : '') + '/' + fullKey; };
  function refreshButtons() {
    mdBtn.style.display = (isMd && mode !== 'edit') ? '' : 'none';
    mdBtn.textContent = mode === 'rendered' ? 'Raw' : 'MD';
    mdBtn.title = mode === 'rendered' ? 'Show raw markdown' : 'Render markdown';
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
    } else if (mode === 'rendered') {
      const div = document.createElement('div');
      div.className = 'md-preview';
      div.textContent = 'Loading preview…';
      body.appendChild(div);
      try {
        const marked = await opfs.opfs.getMarked();
        div.innerHTML = window.marked.parse(current);
      } catch (e) {
        div.textContent = '(failed to load markdown renderer — showing raw)\n\n' + current;
      }
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
  mdBtn.onclick = () => { mode = (mode === 'rendered') ? 'raw' : 'rendered'; render(); };
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
      Sandpie.Sandpie.addMsg('err', `Could not save ${fullKey}: ${e.message}`);
    }
  }
  saveBtn.onclick = doSave;
  function attemptClose() {
    if (isDirty() && !confirm('Unsaved changes will be lost. Close anyway?')) return;
    opfs.closeFile();
  }
  closeBtn.onclick = attemptClose;
  overlay._close = attemptClose;
  overlay.addEventListener('click', e => { if (e.target === overlay) attemptClose(); });
  document.body.appendChild(overlay);
  await render();
}
opfs.closeFile = function() {
  window._openFilePath = null;
  document.querySelectorAll('.file-viewer').forEach(el => {
    const url = el.dataset.blobUrl;
    if (url) URL.revokeObjectURL(url);
    el.remove();
  });
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

opfs.uploadEntry = async function(entry, dirPath) {
  if (entry.isFile) {
    const file = await new Promise(r => entry.file(r));
    const destPath = window.opfsJoin(dirPath, entry.name);
    await opfs.write(destPath, file);
    if (typeof Sandpie !== 'undefined') Sandpie.events.emit('file:changed', destPath);
    const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
    if (sw) sw.postMessage({ type: 'opfs-changed', paths: [destPath] });
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


/* shared files index (used by file browser for shared-folder badges) */
opfs.getSharedSet = async function() {
  try {
    const data = JSON.parse(await opfs.read('shared_index.json'));
    return new Set(Object.keys(data).map(k => k.toLowerCase()));
  } catch { return new Set(); }
};

/* --- backward compat shims for browser/viewer/editor --- */
window.getSharedSet = function() { return opfs.getSharedSet(); };
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


window.opfs = opfs;
window.splitPath = splitPath;
window.joinPath = joinPath;
