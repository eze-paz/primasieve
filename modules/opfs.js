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

/* --- backward compat shims for browser/viewer/editor --- */
window.closeCtxMenu = function() { return opfs.closeCtxMenu(); };
window.showContextMenu = function(x, y, items) { return opfs.showContextMenu(x, y, items); };
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
