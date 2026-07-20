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


  // Append to the end of a file (creating it if absent) WITHOUT rewriting existing
  // bytes: open keeping existing data and do one positioned write at the current
  // size. The append-only conversation JSONL uses this so persisting a new message
  // costs O(new bytes), not O(whole conversation). NOTE: some Chromium versions may
  // copy-on-write a temp file in createWritable; if this profiles as O(N), move the
  // append into a worker using a FileSystemSyncAccessHandle (true O(1) append).
  async append(path, content) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts, { create: true });
    const handle = await dir.getFileHandle(name, { create: true });
    const size = (await handle.getFile()).size;
    const w = await handle.createWritable({ keepExistingData: true });
    await w.write({ type: 'write', position: size, data: content });
    await w.close();
  },

  async remove(path) {


    const { parts, name } = splitPath(path);


    const dir = await this.resolveDir(parts);


    await dir.removeEntry(name, { recursive: true });





    try {


      if (window._sandpieWorker) window._sandpieWorker.postMessage({ type: 'opfs-removed', paths: [path] });


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





/* ---- storage persistence indicator -------------------------------------- */


const sandpiePersistence = {


  async check() {


    const banner = document.getElementById('persistBanner');


    const icon   = document.getElementById('persistIcon');


    const msg    = document.getElementById('persistMsg');


    const btn    = document.getElementById('persistBtn');


    if (!banner || !msg) return;





    let granted = false;


    try {


      if (navigator.storage && navigator.storage.persisted) {


        granted = await navigator.storage.persisted();


      }


    } catch (e) { console.error('persisted() error:', e); }





    if (granted) {


      banner.style.display = 'none';


      return;


    }





    icon.textContent = '\u26a0';


    msg.textContent = 'Files may be deleted by the browser';


    banner.className = 'persist-banner persist-denied';


    btn.style.display = '';


    btn.onclick = () => this.request();


    banner.style.display = '';


  },





  async request() {


    const btn = document.getElementById('persistBtn');


    if (btn) { btn.disabled = true; btn.textContent = 'Requesting\u2026'; }


    let granted = false;


    try {


      if (navigator.storage && navigator.storage.persist) {


        granted = await navigator.storage.persist();


      }


    } catch (e) {


      console.error('persist() error:', e);


      alert('Permission request failed: ' + e.message);


    }


    if (btn) {


      btn.disabled = false;


      btn.textContent = granted ? 'Granted!' : 'Protect files';


    }


    await this.check();


    if (!granted) {


      alert('Persistence not granted. Browser may evict data under pressure.');


    }


  }


};





sandpiePersistence.check();











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


  // Report the EXPECTED (hydrated) size. In on-demand mode most files are cloud


  // placeholders with no local bytes, so summing OPFS + sync-state alone misses


  // them (they live only in the cloud index) and undercounts. Build a best-known


  // size per file from, in priority: local OPFS (real size of hydrated/local-only


  // files) → cloud index (expected size of un-hydrated placeholders) → sync state


  // (tracked files not in the index, e.g. exempt folders / non-dehydrated mode).


  const prefix = path ? path.toLowerCase() + '/' : '';


  const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


  const sizes = new Map();   // lowercased path -> size





  // 1) Local files — their on-disk size IS the hydrated size.


  try {


    for (const full of await opfs.list(path)) {   // opfs.list returns full paths under `path`


      try {


        const { parts, name } = splitPath(full);


        const dir = await opfs.resolveDir(parts);


        sizes.set(full.toLowerCase(), (await (await dir.getFileHandle(name)).getFile()).size);


      } catch {}


    }


  } catch {}





  // 2) Cloud index (on-demand mode) — expected size for files not present locally.


  const cidx = (sp && sp.cloudIndex) ? sp.cloudIndex() : null;


  if (cidx) {


    for (const k of Object.keys(cidx)) {


      const e = cidx[k];


      if (!e || e.kind !== 'file') continue;


      const kl = k.toLowerCase();


      if (prefix && !kl.startsWith(prefix)) continue;


      if (!sizes.has(kl)) sizes.set(kl, e.size || 0);


    }


  }





  // 3) Sync state — tracked files that are neither local nor in the index.


  const state = (sp && sp.getState) ? (sp.getState() || {}) : {};


  for (const k of Object.keys(state)) {


    const kl = k.toLowerCase();


    if (prefix && !kl.startsWith(prefix)) continue;


    if (!sizes.has(kl)) sizes.set(kl, state[k].size || 0);


  }





  let total = 0;


  for (const v of sizes.values()) total += v || 0;


  return total;


};





opfs.formatSize = function(bytes) {


  if (!bytes || bytes < 0) return '';


  const units = ['B', 'kB', 'MB', 'GB', 'TB'];


  let u = 0;


  while (bytes >= 1024 && u < units.length - 1) { bytes /= 1024; u++; }


  return (u === 0 ? bytes : bytes.toFixed(1).replace(/\.0$/, '')) + units[u];


};





// Lightweight transient toast (no CSS dependency) — reused for folder-zip progress.


opfs._toast = function(msg, ms) {


  let el = document.getElementById('opfsToast');


  if (!el) {


    el = document.createElement('div');


    el.id = 'opfsToast';


    el.style.cssText = 'position:fixed;left:50%;bottom:1.3rem;transform:translateX(-50%);' +


      'background:var(--sp-surface,#1c2128);color:var(--sp-text,#e6edf3);' +


      'border:1px solid var(--sp-border,#30363d);border-radius:8px;padding:0.5rem 0.9rem;' +


      'font:0.82rem system-ui,sans-serif;z-index:4000;box-shadow:0 4px 16px rgba(0,0,0,0.45);' +


      'max-width:80vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;pointer-events:none;';


    document.body.appendChild(el);


  }


  el.textContent = msg;


  el.style.display = 'block';


  clearTimeout(el._t);


  if (ms) el._t = setTimeout(() => { el.style.display = 'none'; }, ms);


  return el;


};





// Download an entire OPFS folder as a .zip. Collects every file under the folder


// (local OPFS + any cloud-only files from the dehydrated index, hydrating those on


// demand), builds a DEFLATE zip with JSZip (lazy-loaded), and triggers a browser


// download. Read-only safe; works on dehydrated folders too.


opfs.downloadFolderZip = async function(folderKey) {


  const folderName = (folderKey.split('/').filter(Boolean).pop()) || 'folder';


  try {


    const fileSet = new Set();


    try { for (const f of await opfs.list(folderKey)) fileSet.add(f); } catch (_) {}


    const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


    const cidx = (sp && sp.cloudIndex) ? sp.cloudIndex() : null;   // dehydrated: cloud-only files live here


    if (cidx) {


      const pfx = folderKey + '/';


      for (const rel of Object.keys(cidx)) {


        const e = cidx[rel];


        if (e && e.kind === 'file' && rel.startsWith(pfx)) fileSet.add(rel);


      }


    }


    const files = [...fileSet].sort();


    if (!files.length) { opfs._toast(folderName + ' is empty — nothing to download', 3500); return; }





    if (!window.JSZip) {


      opfs._toast('Preparing…');


      await opfs._loadScript('https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js');


    }


    if (!window.JSZip) throw new Error('zip library unavailable');


    const zip = new JSZip();





    let added = 0, skipped = 0;


    for (let i = 0; i < files.length; i++) {


      const rel = files[i];


      if (files.length > 3 && i % 4 === 0) opfs._toast('Zipping ' + folderName + ' — ' + (i + 1) + '/' + files.length + '…');


      let bytes = null;


      try { bytes = await opfs.readBytes(rel); } catch (_) {}


      if (bytes == null && sp && sp.hydrate) {   // cloud-only placeholder → fetch then read


        try { await sp.hydrate(rel); bytes = await opfs.readBytes(rel); } catch (_) {}


      }


      if (bytes == null) { skipped++; continue; }


      zip.file(folderName + '/' + rel.slice(folderKey.length + 1), bytes);


      added++;


    }


    if (!added) { opfs._toast('Could not read any files in ' + folderName, 4000); return; }





    opfs._toast('Compressing ' + folderName + '…');


    const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } });


    const url = URL.createObjectURL(blob);


    const a = document.createElement('a');


    a.href = url; a.download = folderName + '.zip';


    document.body.appendChild(a); a.click(); a.remove();


    setTimeout(() => URL.revokeObjectURL(url), 10000);


    opfs._toast('Downloaded ' + folderName + '.zip' + (skipped ? ' (' + skipped + ' file' + (skipped > 1 ? 's' : '') + ' skipped)' : ''), 4000);


  } catch (e) {


    console.warn('[opfs] folder zip failed:', folderKey, e);


    opfs._toast('Download failed: ' + (e && e.message ? e.message : 'error'), 4500);


  }


};





opfs.currentPath = function() {


  return (document.getElementById('opfsPath').value || '').trim().replace(/^\/+|\/+$/g, '');


};





/* Read-only fence. The sync provider MAY declare which paths are read-only; this


/* subscriptions removed - all paths are writeable */


opfs.isReadOnly = function() { return false; };











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


    if (item.info) {                 // non-clickable display row (e.g. folder size)


      const info = document.createElement('div');


      info.className = 'ctx-info';


      info.textContent = item.label;


      menu.appendChild(info);


      continue;


    }


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


  return menu;


};











/* Open file viewer/editor */


opfs.openFile = async function(fullKey, name, opts = {}) {





  let file;


  const _readLocal = async () => {


    const { parts, name: fname } = splitPath(fullKey);


    const dir = await opfs.resolveDir(parts);


    return (await dir.getFileHandle(fname)).getFile();


  };


  try {


    file = await _readLocal();


  } catch (e) {


    // Dehydrated mode: a not-yet-downloaded cloud file (bytes not local). Fetch on


    // demand via the sync provider, then open + refresh (rows look identical


    // whether local or not, so nothing visibly changes).


    const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


    let hydrated = false;


    if (sp && sp.hydrate) { try { hydrated = await sp.hydrate(fullKey); } catch (_) {} }


    if (hydrated) { try { file = await _readLocal(); } catch (_) {} opfs.refreshFileList().catch(() => {}); }


    if (!file) { Sandpie.addMsg('err', `Could not open ${fullKey}: ${e.message}`); return; }


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
    body.innerHTML = '';
    mount(opfs.closeFile);
    try {
      await opfs._renderPdfInto(new Uint8Array(await file.arrayBuffer()), body);
    } catch (_e) {
      const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;
      const f = document.createElement('iframe');
      f.setAttribute('data-chrome', '');
      f.src = url;
      f.style.cssText = 'width:100%;height:70vh;border:0;background:#fff';
      body.innerHTML = ''; body.appendChild(f);
    }
    return;
  }


  if (ext === 'pptx' || ext === 'ppt') {


    // PPTX rendering via pptx-viewer (MIT, lightweight, client-side — no server).


    // Lazy-loaded from CDN on first use (same pattern as getMarked). The library


    // parses the OOXML zip and renders slides as SVG in a container with nav


    // controls. Falls back to a "download to view" message if the CDN is blocked.


    body.innerHTML = '<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">Loading presentation viewer…</div>';


    mount(opfs.closeFile);


    // Faithful path (COI): LibreOffice → PDF, shown inline. Falls back to the


    // lightweight pptx-viewer when isolation is unavailable or the engine fails.


    if (await opfs._renderOfficePdf(file, ext, name, body, panel)) return;


    try {


      await opfs.getPptxViewer();


      const container = document.createElement('div');


      // Force a light-theme context: pptx-viewer renders slides as SVG, and SVG


      // text without an explicit fill inherits currentColor. Sandpie's dark theme


      // sets color:white → invisible text on white slide backgrounds. Pinning


      // color:#333 + background:#fff ensures inherited text is always visible.


      // Also reset font-family so the viewer's own styles apply cleanly.


      container.style.cssText = 'width:100%;min-height:60vh;color:#333;background:#fff;font-family:sans-serif;';


      container.className = 'pptx-viewer-container';


      body.innerHTML = '';


      body.appendChild(container);


      const viewer = new window.PPTXViewer.PPTXViewer(container, {


        showControls: true,


        keyboardNavigation: true,


      });


      await viewer.load(file);


    } catch (e) {


      body.innerHTML = '';


      const div = document.createElement('div');


      div.style.cssText = 'padding:1.5rem;color:var(--sp-text-dim);text-align:center;';


      const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;


      div.innerHTML = `Could not load presentation viewer (${(e && e.message) || e}).<br><a href="${url}" download="${name}" style="color:var(--sp-accent);">Download ${name}</a> to view locally.`;


      body.appendChild(div);


    }


    return;


  }


  if (ext === 'docx' || ext === 'doc') {


    // docx-preview renders OOXML client-side into styled HTML (light theme,


    // like Word). Lazy-loaded from CDN on first use. .doc (legacy binary) isn't


    // OOXML → renderAsync throws → the catch shows a download link.


    body.innerHTML = '<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">Loading document viewer…</div>';


    mount(opfs.closeFile);


    // Faithful path (COI): LibreOffice → PDF, shown inline. Falls back to


    // docx-preview (approximate HTML) when isolation is unavailable or the engine


    // fails (e.g. .doc legacy binary that ZetaOffice can still often open).


    if (await opfs._renderOfficePdf(file, ext, name, body, panel)) return;


    try {


      const docx = await opfs.getDocxPreview();


      const container = document.createElement('div');


      // docx-preview emits page-styled HTML; pin a light context so its text and


      // page chrome stay readable under Sandpie's dark theme.


      container.className = 'docx-viewer-container';


      container.style.cssText = 'width:100%;min-height:60vh;color:#222;background:#f3f3f3;font-family:sans-serif;overflow:auto;';


      body.innerHTML = '';


      body.appendChild(container);


      await docx.renderAsync(file, container, null, { className: 'docx', inWrapper: true });


    } catch (e) {


      body.innerHTML = '';


      const div = document.createElement('div');


      div.style.cssText = 'padding:1.5rem;color:var(--sp-text-dim);text-align:center;';


      const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;


      div.innerHTML = `Could not render document (${(e && e.message) || e}).<br><a href="${url}" download="${name}" style="color:var(--sp-accent);">Download ${name}</a> to view locally.`;


      body.appendChild(div);


    }


    return;


  }


  if (ext === 'tex') {


    const dirPath = fullKey.replace(/\/[^\/]+$/, '');


    body.innerHTML = '<iframe src="/convert_latex/index.html?v=4#project=' + encodeURIComponent(dirPath) + '" style="width:100%;height:calc(100vh - 60px);border:0;border-radius:6px;"></iframe>';


    mount(opfs.closeFile);


    return;


  }


  if (ext === 'xlsx' || ext === 'xls' || ext === 'ods') {


    // SheetJS reads the workbook client-side; each sheet renders to an HTML table


    // with a tab bar to switch between sheets. Lazy-loaded from CDN on first use.


    body.innerHTML = '<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">Loading spreadsheet viewer…</div>';


    mount(opfs.closeFile);


    // Faithful path (COI): LibreOffice → PDF, shown inline. Falls back to the


    // SheetJS HTML-table viewer when isolation is unavailable or the engine fails.


    if (await opfs._renderOfficePdf(file, ext, name, body, panel)) return;


    try {


      const XLSX = await opfs.getSheetJS();


      const wb = XLSX.read(new Uint8Array(await file.arrayBuffer()), { type: 'array' });


      body.innerHTML = '';


      const container = document.createElement('div');


      container.className = 'xlsx-viewer-container';


      container.style.cssText = 'width:100%;color:#222;background:#fff;font-family:sans-serif;';


      const tabs = document.createElement('div');


      tabs.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;padding:6px;border-bottom:1px solid #ddd;position:sticky;top:0;background:#f5f5f5;z-index:1;';


      const sheetHost = document.createElement('div');


      sheetHost.style.cssText = 'overflow:auto;max-height:65vh;padding:4px;';


      const showSheet = (nm) => {


        sheetHost.innerHTML = XLSX.utils.sheet_to_html(wb.Sheets[nm], { editable: false });


        Array.from(tabs.children).forEach(b => { b.style.fontWeight = (b.textContent === nm) ? '700' : '400'; });


      };


      wb.SheetNames.forEach(nm => {


        const b = document.createElement('button');


        b.textContent = nm;


        b.style.cssText = 'padding:3px 10px;font:12px sans-serif;border:1px solid #ccc;border-radius:3px;background:#fff;color:#222;cursor:pointer;';


        b.onclick = () => showSheet(nm);


        tabs.appendChild(b);


      });


      if (wb.SheetNames.length > 1) container.appendChild(tabs);


      container.appendChild(sheetHost);


      body.appendChild(container);


      showSheet(wb.SheetNames[0]);


    } catch (e) {


      body.innerHTML = '';


      const div = document.createElement('div');


      div.style.cssText = 'padding:1.5rem;color:var(--sp-text-dim);text-align:center;';


      const url = URL.createObjectURL(file); panel.dataset.blobUrl = url;


      div.innerHTML = `Could not render spreadsheet (${(e && e.message) || e}).<br><a href="${url}" download="${name}" style="color:var(--sp-accent);">Download ${name}</a> to view locally.`;


      body.appendChild(div);


    }


    return;


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


  const editable = text.length <= TEXT_PREVIEW_CAP;





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


      opfs.toUrl(fullKey).then(url => { f.src = url; }).catch(() => {});


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





// Lazy-load pptx-viewer (MIT, ~110KB UMD, only dep is fflate for zip — bundled).


// Renders .pptx slides client-side as SVG with navigation controls. No server.


opfs.getPptxViewer = function() {


  if (!window._pptxViewerPromise) {


    window._pptxViewerPromise = new Promise((resolve, reject) => {


      const s = document.createElement('script');


      s.src = 'https://cdn.jsdelivr.net/npm/pptx-viewer@0.2.2/dist/pptx-viewer.umd.js';


      s.onload = () => resolve(window.PPTXViewer);


      s.onerror = () => reject(new Error('failed to load pptx-viewer from CDN'));


      document.head.appendChild(s);


    });


  }


  return window._pptxViewerPromise;


};





// Append a <script src> and resolve once it loads (shared by the docx/xlsx


// lazy-loaders below). Rejects on a network/CDN failure so callers can fall back.


opfs._loadScript = function(src) {


  return new Promise((resolve, reject) => {


    const s = document.createElement('script');


    s.src = src;


    s.onload = () => resolve();


    s.onerror = () => reject(new Error('failed to load ' + src));


    document.head.appendChild(s);


  });


};





// Lazy-load docx-preview (Apache-2.0). Parses the OOXML zip and renders a .docx


// into styled HTML, client-side. Needs JSZip present as a global, so load that


// first. Exposes window.docx.renderAsync. No server. (.doc legacy binary isn't


// OOXML and won't render — the openFile branch falls back to a download link.)


opfs.getDocxPreview = function() {


  if (!window._docxPreviewPromise) {


    window._docxPreviewPromise = (async () => {


      if (!window.JSZip) {


        await opfs._loadScript('https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js');


      }


      await opfs._loadScript('https://cdn.jsdelivr.net/npm/docx-preview@0.3.5/dist/docx-preview.min.js');


      if (!window.docx || !window.docx.renderAsync) throw new Error('docx-preview failed to initialize');


      return window.docx;


    })();


  }


  return window._docxPreviewPromise;


};





// Hand a document off to the /convert/ popup through IndexedDB. The popup (which


// IS crossOriginIsolated, unlike this page) picks the job up by id from the URL


// hash, deletes it, and runs the LibreOffice WASM conversion there.


opfs._putConvertJob = function(job) {


  return new Promise((resolve, reject) => {


    const open = indexedDB.open('sandpie-convert', 1);


    open.onupgradeneeded = () => open.result.createObjectStore('jobs', { keyPath: 'id' });


    open.onerror = () => reject(open.error);


    open.onsuccess = () => {


      const db = open.result;


      const tx = db.transaction('jobs', 'readwrite');


      tx.objectStore('jobs').put(job);


      tx.oncomplete = () => { db.close(); resolve(); };


      tx.onerror = () => { db.close(); reject(tx.error); };


    };


  });


};


// In-page office→PDF engine. When the app page is crossOriginIsolated (prod


// sends COOP/COEP; locally via coiserver.py), we can run ZetaOffice (LibreOffice


// WASM) directly — no popup. It lives in a hidden same-origin iframe


// (convert/office-engine.html) which, being a child of a COI top-level, is itself


// COI. Booted once on first use and kept warm for the session; each conversion is


// a postMessage round-trip. Returns a promise for { convert(bytes, ext) → PDF


// ArrayBuffer }, or null when isolation is unavailable (caller falls back to the


// lightweight docx-preview/SheetJS/pptx-viewer path, or the popup).


opfs._pdfjsReady = null;
opfs._ensurePdfjs = function () {
  if (!opfs._pdfjsReady) {
    opfs._pdfjsReady = opfs._loadScript('/modules/pdf.min.js').then(function () {
      if (!window.pdfjsLib) throw new Error('pdf.js failed to load');
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/modules/pdf.worker.min.js';
    });
  }
  return opfs._pdfjsReady;
};
// Render PDF bytes into `container` as stacked <canvas> pages via pdf.js. Native
// <iframe src="blob:...pdf"> works on desktop Chrome (PDFium) but Android Chrome
// has no inline PDF viewer and shows "refused to connect", so we rasterize here.
opfs._renderPdfInto = async function (bytes, container) {
  await opfs._ensurePdfjs();
  const data = (bytes instanceof Uint8Array) ? bytes : new Uint8Array(bytes);
  // disableFontFace: render glyphs as canvas vector paths via pdf.js's own font
  // parser instead of the browser @font-face engine. A PDF with a broken embedded
  // font (e.g. missing "glyf" table) gets "recovered" by pdf.js, but desktop
  // Chrome's OTS sanitizer rejects the recovered font -> blank text; mobile is
  // lenient. Path rendering sidesteps the browser font engine entirely, so text
  // renders identically on every device. Safe here: we only rasterize to canvas.
  const doc = await window.pdfjsLib.getDocument({ data: data.slice(0), disableFontFace: true }).promise;
  container.innerHTML = '';
  container.style.cssText = 'width:100%;height:70vh;overflow:auto;background:#525659;padding:8px 0;';
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cw = (container.clientWidth || container.offsetWidth || 800) - 16;
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const base = page.getViewport({ scale: 1 });
    const scale = Math.max(0.2, cw / base.width);
    const vp = page.getViewport({ scale: scale * dpr });
    const canvas = document.createElement('canvas');
    canvas.width = vp.width; canvas.height = vp.height;
    canvas.style.cssText = 'display:block;margin:0 auto 8px;width:' + Math.round(vp.width / dpr) + 'px;max-width:100%;box-shadow:0 1px 4px rgba(0,0,0,.4);background:#fff';
    container.appendChild(canvas);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
  }
};

opfs.OFFICE_ENGINE_EXTS = new Set(['docx','doc','odt','rtf','xlsx','xls','ods','csv','pptx','ppt','odp','odg']);





// Filenames of every font in sandpie/fonts/ — from BOTH the local OPFS listing


// AND the Dropbox cloud index. Under on-demand (dehydrated) sync the fonts are


// cloud-only: they show in the UI via the cloud index but are absent from OPFS,


// so opfs.listDir alone misses them (which is why hydration found nothing).


opfs._listFontFiles = async function() {


  const names = new Set();


  const isFont = n => /\.(ttf|otf|ttc)$/i.test(n);


  try { for (const e of await opfs.listDir('sandpie/fonts')) if (e.kind === 'file' && isFont(e.name)) names.add(e.name); } catch (_) {}


  try {


    const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


    const idx = (sp && sp.cloudIndex) ? sp.cloudIndex() : null;


    if (idx) for (const key of Object.keys(idx)) {


      const rel = String(key).replace(/^\/+/, '').replace(/^files\//, '');


      const m = /^sandpie\/fonts\/([^/]+)$/.exec(rel);


      if (m && isFont(m[1]) && idx[key] && idx[key].kind === 'file') names.add(m[1]);


    }


  } catch (_) {}


  return [...names];


};





// Hydrate every font in sandpie/fonts/ so its real bytes are local before the


// engine boots. The engine (office-engine.html) reads OPFS directly and has no


// access to the sync provider, so a cloud-only (dehydrated) font would otherwise


// be absent/empty and never get injected. We pull them down here, page-side.


opfs._hydrateFontsFolder = async function() {


  for (const name of await opfs._listFontFiles()) {


    try { await opfs.readBytesHydrating('sandpie/fonts/' + name); } catch (_) {}


  }


};





opfs._officeEngine = function() {


  if (!self.crossOriginIsolated) return null;


  if (!opfs._officeEnginePromise) {


    opfs._officeEnginePromise = (async () => {


      // Fonts must be locally present before the engine reads them at boot.


      await opfs._hydrateFontsFolder();


      return new Promise((resolve, reject) => {


      const iframe = document.createElement('iframe');


      iframe.setAttribute('aria-hidden', 'true');


      iframe.style.cssText = 'position:fixed;width:0;height:0;border:0;visibility:hidden;left:-9999px;';


      iframe.src = '/convert/office-engine.html?v=3';


      const pending = new Map();


      let seq = 0, ready = false;


      const bootTimer = setTimeout(() => {


        if (!ready) { cleanup(); reject(new Error('office engine boot timed out')); }


      }, 180000);


      const onMsg = (e) => {


        if (e.source !== iframe.contentWindow) return;


        const d = e.data || {};


        if (d.type === 'engine-ready') { ready = true; clearTimeout(bootTimer); resolve(api); return; }


        if (d.type === 'engine-error') { cleanup(); reject(new Error(d.error || 'office engine error')); return; }


        if (d.type === 'converted-ok' || d.type === 'converted-err') {


          const cb = pending.get(d.id);


          if (cb) { pending.delete(d.id); cb(d); }


        }


      };


      const cleanup = () => {


        window.removeEventListener('message', onMsg);


        try { iframe.remove(); } catch (_) {}


        opfs._officeEnginePromise = null;   // allow a fresh boot next time


      };


      const api = {


        convert(bytes, ext, timeoutMs = 180000) {


          return new Promise((res, rej) => {


            const id = 'o' + (++seq);


            const timer = setTimeout(() => { pending.delete(id); rej(new Error('conversion timed out')); }, timeoutMs);


            pending.set(id, (msg) => {


              clearTimeout(timer);


              if (msg.type === 'converted-ok') res(msg.pdf);


              else rej(new Error(msg.error || 'conversion failed'));


            });


            iframe.contentWindow.postMessage({ type: 'convert', id, bytes, ext }, '*', [bytes]);


          });


        },


      };


      window.addEventListener('message', onMsg);


      document.body.appendChild(iframe);


      });


    })();


  }


  return opfs._officeEnginePromise;


};





// Tear down the warm engine so the next _officeEngine() boots fresh — needed


// after the user adds fonts to sandpie/fonts/, because LibreOffice caches its


// font list for the session (a font added to a running engine isn't picked up;


// the engine injects sandpie/fonts/ at boot via an Emscripten preRun hook).


opfs._resetOfficeEngine = function() {


  opfs._officeEnginePromise = null;


  document.querySelectorAll('iframe[src^="/convert/office-engine.html"]').forEach(f => { try { f.remove(); } catch (_) {} });


};





/* ---- font availability check (for the office→PDF converter) ---------------- */


// Fonts LibreOffice-WASM renders acceptably: its bundled families + the ubiquitous


// MS-core fonts it maps to metric-compatible bundled substitutes (Calibri→Carlito,


// Cambria→Caladea, Arial/Times/Courier→Liberation). Anything else has no good match


// → we warn. Names are normalized (lowercase, alnum-only).


const _normFont = s => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '');


const _LO_KNOWN_FONTS = new Set([


  'liberationsans', 'liberationserif', 'liberationmono', 'liberationsansnarrow',


  'carlito', 'caladea', 'dejavusans', 'dejavusansmono', 'dejavuserif', 'dejavumathtexgyre',


  'gentiumbasic', 'gentiumbookbasic', 'linuxbiolinumg', 'linuxlibertineg', 'opensymbol',


  'notosans', 'notoserif', 'notokufiarabic', 'notonaskharabic', 'notosansarabic', 'notosanshebrew',


  'amiri', 'rubik', 'reemkufi', 'scheherazade', 'alef', 'davidlibre', 'miriamlibre', 'frankruhlhofshi',


  'calibri', 'calibrilight', 'cambria', 'cambriamath', 'arial', 'timesnewroman', 'couriernew',


  'symbol', 'wingdings',


]);





opfs._ensureJSZip = async function() {


  if (!window.JSZip) await opfs._loadScript('https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js');


  if (!window.JSZip) throw new Error('zip library unavailable');


  return window.JSZip;


};





// Font family name(s) from an OpenType/TrueType file's `name` table (nameID 1 =


// family, 16 = typographic family), so we can tell whether a user-supplied font


// actually covers a referenced family — regardless of how the file is named.


opfs._fontFamilyNames = function(u8) {


  try {


    const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);


    let base = 0;


    if (dv.getUint32(0) === 0x74746366) base = dv.getUint32(12);   // 'ttcf' → first font


    const numTables = dv.getUint16(base + 4);


    let nameOff = 0;


    for (let i = 0; i < numTables; i++) {


      const rec = base + 12 + i * 16;


      if (dv.getUint32(rec) === 0x6e616d65) { nameOff = dv.getUint32(rec + 8); break; }   // 'name'


    }


    if (!nameOff) return [];


    const count = dv.getUint16(nameOff + 2);


    const strBase = nameOff + dv.getUint16(nameOff + 4);


    const out = new Set();


    for (let i = 0; i < count; i++) {


      const r = nameOff + 6 + i * 12;


      const platform = dv.getUint16(r), nameId = dv.getUint16(r + 6);


      if (nameId !== 1 && nameId !== 4 && nameId !== 16) continue;


      const len = dv.getUint16(r + 8), o = strBase + dv.getUint16(r + 10);


      let s = '';


      if (platform === 3 || platform === 0) { for (let j = 0; j + 1 < len; j += 2) s += String.fromCharCode(dv.getUint16(o + j)); }


      else { for (let j = 0; j < len; j++) s += String.fromCharCode(dv.getUint8(o + j)); }


      s = s.replace(/\0/g, '').trim();


      if (s) out.add(s);


    }


    return [...out];


  } catch (_) { return []; }


};





// Normalized family names of every font in sandpie/fonts/ (local + cloud-only).


opfs._fontFamiliesInFolder = async function() {


  const fams = new Set();


  for (const name of await opfs._listFontFiles()) {


    try {


      // Hydrate on read: under Dropbox on-demand a font may be cloud-only, so


      // readBytes alone returns nothing and the name-table parse silently fails —


      // making a present-but-dehydrated font look missing.


      const bytes = await opfs.readBytesHydrating('sandpie/fonts/' + name);


      for (const f of opfs._fontFamilyNames(bytes)) fams.add(_normFont(f));


    } catch (_) {}


    


  }


  fams.delete('');


  return fams;


};





// Font family names referenced by an office file (parsed from its OOXML/ODF zip).


opfs._fontsReferenced = async function(bytes, ext) {


  const JSZip = await opfs._ensureJSZip();


  const zip = await JSZip.loadAsync(bytes);


  const names = new Set();


  const scan = (xml, re) => { let m; while ((m = re.exec(xml || ''))) { const v = (m[1] || '').trim(); if (v) names.add(v); } };


  const read = async p => { const f = zip.file(p); return f ? await f.async('string') : ''; };


  ext = String(ext || '').toLowerCase();


  if (/^doc[xm]$|^dot[xm]$/.test(ext)) {


    scan(await read('word/fontTable.xml'), /w:font\s+w:name="([^"]+)"/g);


  } else if (/^xls[xm]$|^xlt[xm]$/.test(ext)) {


    scan(await read('xl/styles.xml'), /<name\s+val="([^"]+)"/g);


  } else if (/^ppt[xm]$|^pot[xm]$/.test(ext)) {


    for (const p of Object.keys(zip.files)) {


      if (/^ppt\/(theme|slides|slideLayouts|slideMasters)\/.*\.xml$/.test(p)) scan(await zip.file(p).async('string'), /typeface="([^"]+)"/g);


    }


  } else {


    for (const p of ['styles.xml', 'content.xml']) {


      const x = await read(p);


      scan(x, /style:font-name="([^"]+)"/g);


      scan(x, /svg:font-family="([^"]+)"/g);


    }


  }


  const out = [];


  for (let n of names) { n = n.replace(/^['"]+|['"]+$/g, '').trim(); if (n && !/^\+(mj|mn)-/.test(n)) out.push(n); }


  return out;


};





// Referenced fonts that LibreOffice can't match (not bundled, not a mapped MS-core


// font, not supplied in sandpie/fonts/). [] means "safe to convert as-is". Parse


// failures return [] — never block a conversion on our own inability to read fonts.


opfs._missingFonts = async function(bytes, ext) {


  let referenced;


  try { referenced = await opfs._fontsReferenced(new Uint8Array(bytes), ext); } catch (_) { return []; }


  if (!referenced.length) return [];


  const userFams = await opfs._fontFamiliesInFolder();


  const seen = new Set(), missing = [];


  for (const name of referenced) {


    const n = _normFont(name);


    if (!n || seen.has(n)) continue;


    seen.add(n);


    if (_LO_KNOWN_FONTS.has(n)) continue;


    let covered = userFams.has(n);


    // prefix fallback removed - exact match only


    if (!userFams.has(n)) missing.push(name);


  }


  return missing;


};





// Ensure sandpie/fonts/ exists (with a short README) so the user has somewhere to


// drop the fonts we ask for, and it shows up in the Files sidebar.


opfs._ensureFontsFolder = async function() {


  try {


    await opfs.mkdir('sandpie/fonts');


    if (!(await opfs.exists('sandpie/fonts/README.txt'))) {


      await opfs.write('sandpie/fonts/README.txt',


        'Drop .ttf / .otf font files here.\n\nThe in-app document converter (docx / xlsx / pptx → PDF) loads these so files\n' +


        'render with their intended fonts instead of substitutes. After adding a font,\nclick "Retry" in the converter.\n');


    }


    try { opfs.refreshFileList && opfs.refreshFileList(); } catch (_) {}


    try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', 'sandpie/fonts/README.txt'); } catch (_) {}


  } catch (_) {}


};





// The missing-font warning panel: lists the fonts, points at sandpie/fonts/, and


// offers Retry (re-boots the engine to pick up newly-added fonts) or Proceed


// (convert now with substitutes). `retry` re-invokes the render.


opfs._renderFontWarning = function(body, panel, missing, retry) {


  body.innerHTML = '';


  const box = document.createElement('div');


  box.className = 'font-warning';


  const title = document.createElement('div');


  title.className = 'fw-title';


  title.textContent = '⚠ Missing font' + (missing.length > 1 ? 's' : '');


  const p1 = document.createElement('p');


  p1.textContent = "This document uses font" + (missing.length > 1 ? 's' : '') + " that aren't available in the converter:";


  const ul = document.createElement('ul');


  for (const f of missing) { const li = document.createElement('li'); li.textContent = f; ul.appendChild(li); }


  const p2 = document.createElement('p');


  p2.innerHTML = 'Add the matching <b>.ttf/.otf</b> to the <b>sandpie/fonts</b> folder (Files sidebar), then Retry — ' +


    'or proceed now and it will be rendered with substitute fonts, which <b>may not look the same</b>.';


  const actions = document.createElement('div');


  actions.className = 'fw-actions';


  const retryBtn = document.createElement('button');


  retryBtn.className = 'fw-retry';


  retryBtn.textContent = 'I added the fonts — retry';


  retryBtn.onclick = () => { opfs._resetOfficeEngine(); retry(); };


  const proceedBtn = document.createElement('button');


  proceedBtn.className = 'fw-proceed';


  proceedBtn.textContent = 'Proceed with font substitutions';


  proceedBtn.onclick = () => { panel._fontProceed = true; retry(); };


  actions.append(retryBtn, proceedBtn);


  box.append(title, p1, ul, p2, actions);


  body.appendChild(box);


};





// Try to render an office file faithfully by converting it to PDF in the engine


// and showing that PDF inline (reuses the same <iframe> display as native PDFs).


// Returns true on success, false to signal the caller to fall back to its


// lightweight viewer. `body` already shows a spinner and the panel is mounted.


opfs._renderOfficePdf = async function(file, ext, name, body, panel) {


  if (!self.crossOriginIsolated) return false;


  try {


    body.innerHTML = '<div class="sp-loading">Loading<div class="sp-bar"></div></div>';


    const bytes = await file.arrayBuffer();


    // Font gate: warn (once, unless the user chose to proceed) if the document


    // references fonts the converter can't match, so output fidelity is a choice.


    if (panel && !panel._fontProceed) {


      let missing = [];


      try { missing = await opfs._missingFonts(bytes, ext); } catch (_) {}


      if (missing.length) {


        await opfs._ensureFontsFolder();


        opfs._renderFontWarning(body, panel, missing, () => opfs._renderOfficePdf(file, ext, name, body, panel));


        return true;   // handled: warning shown, awaiting the user's choice


      }


    }


    const engine = await opfs._officeEngine();


    const pdf = await engine.convert(bytes, ext);


    try {
      await opfs._renderPdfInto(pdf, body);
    } catch (_e) {
      const url = URL.createObjectURL(new Blob([pdf], { type: 'application/pdf' }));
      if (panel) panel.dataset.blobUrl = url;
      body.innerHTML = '';
      const f = document.createElement('iframe');
      f.setAttribute('data-chrome', '');
      f.src = url;
      f.style.cssText = 'width:100%;height:70vh;border:0;background:#fff';
      body.appendChild(f);
    }


    return true;


  } catch (e) {


    console.warn('[opfs] faithful office render failed, falling back:', e && e.message || e);


    return false;


  }


};








// Lazy-load SheetJS (Apache-2.0, ~900KB UMD). Reads xlsx/xls/ods workbooks


// client-side; we render each sheet to an HTML table. Exposes window.XLSX.


opfs.getSheetJS = function() {


  if (!window._sheetjsPromise) {


    window._sheetjsPromise = (async () => {


      await opfs._loadScript('https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js');


      if (!window.XLSX) throw new Error('SheetJS failed to initialize');


      return window.XLSX;


    })();


  }


  return window._sheetjsPromise;


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





// Announce a freshly uploaded/written OPFS file so it (a) shows up in the file


// sidebar and (b) is synced into the run_python (Pyodide) MEMFS mount at /files


// — so the model can read it the moment it replies. Every upload entry point


// (attach button, drag-and-drop, programmatic writes) routes through here. The


// SW only live-syncs once Pyodide has booted; before that the file is already in


// OPFS and gets picked up when the /files mount populates. The sidebar refresh


// Serve an OPFS file as a blob URL — replaces the /opfs/ SW fetch intercept.


// HTML files get the postMessage resize script injected so artifact iframes


// auto-size. Call URL.revokeObjectURL() on the returned URL when done.


// Page-side hydration for a dehydrated (cloud-only) file: pull its bytes down via


// the sync provider if they aren't local yet. No-op (returns false) when already


// local or no provider. Reusable — openFile/artifacts/toUrl all need it.


opfs.hydrate = async function(path) {


  const clean = String(path).replace(/^\/+/, '');


  const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


  if (sp && sp.hydrate) { try { return await sp.hydrate(clean); } catch (_) {} }


  return false;


};


// Read bytes, hydrating first if the file is missing or a 0-byte cloud placeholder.


opfs.readBytesHydrating = async function(path) {


  const clean = String(path).replace(/^\/+/, '');


  let bytes = null;


  try { bytes = await this.readBytes(clean); } catch (_) {}


  if (bytes == null || bytes.length === 0) {


    const ok = await opfs.hydrate(clean);


    if (ok || bytes == null) { try { bytes = await this.readBytes(clean); } catch (_) {} }


  }


  if (bytes == null) throw new Error('file not found: ' + clean);


  return bytes;


};





opfs.toUrl = async function(path) {


  const clean = String(path).replace(/^\/+/, '');


  const ext = (clean.split('.').pop() || '').toLowerCase();


  const mimeMap = {


    html:'text/html', htm:'text/html', svg:'image/svg+xml',


    png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg',


    gif:'image/gif', webp:'image/webp', csv:'text/csv',


    json:'application/json', txt:'text/plain',


  };


  const mime = mimeMap[ext] || 'application/octet-stream';


  // Hydrate a cloud-only artifact on demand — a just-shown or reloaded artifact


  // may not be local yet; without this the render fails with "file not found".


  const bytes = await this.readBytesHydrating(clean);


  if (ext === 'html' || ext === 'htm') {


    let text = new TextDecoder().decode(bytes);


    const script = `<script>(function(){` +


      `function report(){var h=Math.max(document.body?document.body.scrollHeight:0,` +


      `document.documentElement?document.documentElement.scrollHeight:0,100);` +


      `parent.postMessage({type:'sandpie-artifact-resize',h:h},'*');}` +


      `var ro=new ResizeObserver(function(){requestAnimationFrame(report);});` +


      `if(document.body)ro.observe(document.body);` +


      `if(document.documentElement)ro.observe(document.documentElement);` +


      `window.addEventListener('load',report);` +


      `setTimeout(report,50);setTimeout(report,300);` +


      `})();<\/script>`;


    if (/<\/body>/i.test(text)) text = text.replace(/<\/body>/i, script + '</body>');


    else text += script;


    return URL.createObjectURL(new Blob([text], { type: 'text/html' }));


  }


  return URL.createObjectURL(new Blob([bytes], { type: mime }));


};





// is debounced so a multi-file drop refreshes the list just once.


let _notifyRefreshT = null;


opfs.notifyUpload = function(path) {


  try { if (typeof Sandpie !== 'undefined') Sandpie.events.emit('file:changed', path); } catch (_) {}


  try {


    if (window._sandpieWorker) window._sandpieWorker.postMessage({ type: 'opfs-changed', paths: [path] });


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











// File-list sort mode (the right-click "Sort by" section). Folders always group


// first and sort by name; files sort by this mode. Persisted in localStorage.


const FILE_SORT_KEY = 'sandpie-files-sort';


function fileSortMode() { const m = localStorage.getItem(FILE_SORT_KEY); return (m === 'size' || m === 'mtime') ? m : 'name'; }


function setFileSortMode(m) { localStorage.setItem(FILE_SORT_KEY, (m === 'size' || m === 'mtime') ? m : 'name'); opfs.refreshFileList(); }





opfs.refreshFileList = async function() {


  const ul = document.getElementById('fileList');


  const path = opfs.currentPath();


  const frag = document.createDocumentFragment();





  const _sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


  const state = (_sp && _sp.getState) ? (_sp.getState() || {}) : {};


  const cidx = (_sp && _sp.cloudIndex) ? _sp.cloudIndex() : null;   // full Dropbox tree in dehydrated mode; null otherwise





  // Build the sorted entry list for ONE directory (local listing + dehydrated


  // cloud-index merge + per-item status/size). Kept separate from rendering so we


  // can list more than one directory into the same panel — the root view renders


  // the user's files, then lists sandpie/'s children under a collapsible section.


  async function computeEntries(dirPath) {


    let opfsList = [];


    try { opfsList = await opfs.listDir(dirPath); } catch {}


    const localMap = new Map();


    for (const e of opfsList) localMap.set(e.name, e.kind === 'directory' ? 'folder' : 'file');


    const prefix = dirPath ? dirPath + '/' : '';


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


    // Dehydrated mode: surface the full Dropbox tree (what the LLM sees) as cloud


    // placeholders even though the bytes aren't local. Exempt folders already come


    // from OPFS/state above, so skip them to avoid duplicates.


    if (cidx) {


      const pl = prefix.toLowerCase();


      for (const rel of Object.keys(cidx)) {


        if (_sp.isExempt && _sp.isExempt(rel)) continue;


        const rl = rel.toLowerCase();


        if (pl && !rl.startsWith(pl)) continue;


        const rest = rel.slice(prefix.length);


        if (!rest) continue;


        if (rest.includes('/')) {


          const firstSeg = rest.split('/')[0];


          if (!remoteMap.has(firstSeg) && !localMap.has(firstSeg)) remoteMap.set(firstSeg, 'folder');


        } else if (!remoteMap.has(rest)) {


          // Standalone index entry (no sub-path): trust its Dropbox kind so an


          // empty / childless-in-index folder (e.g. a freshly-moved sandpie/


          // artifacts) isn't mislabeled a file.


          remoteMap.set(rest, cidx[rel] && cidx[rel].kind === 'folder' ? 'folder' : 'file');


        }


      }


    }


    const names = new Set([...localMap.keys(), ...remoteMap.keys()]);


    const items = [];


    for (const name of names) {


      const local = localMap.get(name);


      const remote = remoteMap.get(name);


      const kind = local === 'folder' || remote === 'folder' ? 'folder' : 'file';


      const fullKey = opfsJoin(dirPath, name);


      items.push({ name, kind, fullKey, local, remote });


    }


    // Resolve per-item status + size concurrently. Folders show NO inline size


    // (Windows-Explorer style — computed on demand from the right-click menu).


    await Promise.all(items.map(async (it) => {


      const { local, remote, fullKey, kind } = it;


      if (kind === 'folder') {


        it.status = local && remote ? 'synced' : (local ? 'local' : 'cloud');


        it.size = undefined;


        it.mtime = 0;


        return;


      }


      it.size = await opfs.getFileSize(fullKey);


      it.mtime = local ? await opfs.lastModified(fullKey) : 0;


      if (!local) {


        it.status = 'cloud';


        if (cidx && cidx[fullKey]) {


          if (cidx[fullKey].size != null) it.size = cidx[fullKey].size;


          if (cidx[fullKey].cloudMtime) it.mtime = Date.parse(cidx[fullKey].cloudMtime) || 0;


        }


        return;


      }


      if (!remote) { it.status = 'local'; return; }


      const s = state[fullKey];


      it.status = it.mtime > 0 && s && s.syncedMtime != null && it.mtime <= s.syncedMtime ? 'synced' : 'modified';


    }));


    // Folders always group first + sort by name; files sort by the chosen mode


    // (size / last-modified descending). Set via the right-click "Sort by" section.


    const _mode = fileSortMode();


    items.sort((a, b) => {


      if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1;


      if (a.kind === 'folder') return a.name.localeCompare(b.name);


      if (_mode === 'size')  return (b.size || 0) - (a.size || 0) || a.name.localeCompare(b.name);


      if (_mode === 'mtime') return (b.mtime || 0) - (a.mtime || 0) || a.name.localeCompare(b.name);


      return a.name.localeCompare(b.name);


    });


    return items;


  }





  const renderItem = (it, liClass) => {


    const li = document.createElement('li');


    if (liClass) li.className = liClass;


    const btn = document.createElement('span');


    btn.className = 'name' + (it.kind === 'folder' ? ' folder' : '');


    const kindIcon = it.kind === 'folder' ? '📁 ' : '📄 ';


    btn.textContent = kindIcon + it.name;


    // Hydration is invisible to the user too: a not-yet-downloaded cloud file


    // looks like any other file (📄) and reports "synced" — clicking it fetches it


    // transparently (openFile → provider.hydrate).


    const statusLabel = it.status === 'cloud' ? 'synced' : it.status;


    btn.title = `${it.kind} · ${statusLabel}`;


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
      // Show the full filename first so long names are always readable.
      menuItems.push({ info: true, label: it.fullKey });


      // For folders, show the (recursively summed) size at the top — computed on


      // demand here so navigating the list never pays for the subtree walk.


      if (it.kind === 'folder') menuItems.push({ info: true, label: 'Size: …' });


      menuItems.push({ label: 'Copy path', action: () => { navigator.clipboard.writeText(it.fullKey).catch(() => {}); } });


      menuItems.push({ label: 'Upload files', action: () => opfs.promptUpload(opfsCurrentPath()) });


      menuItems.push({ label: 'New folder', action: () => opfs.createFolder() });


      menuItems.push({ label: 'New file', action: () => opfs.createFile() });


      if (it.kind === 'file') {


const itExt = (it.name.split('.').pop() || '').toLowerCase();

        if (opfs.OFFICE_ENGINE_EXTS.has(itExt)) {

          menuItems.push({

            label: 'Open in new tab',

            action: () => {

              window.open('/convert/office-viewer.html#file=' + encodeURIComponent(it.fullKey), '_blank');

            }

          });

        } else {

          menuItems.push({

            label: 'Open in new tab',

            action: async () => {

              try {

                let url;

                try {

                  url = await opfs.toUrl(it.fullKey);

                } catch (e) {

                  if (e.name !== 'NotFoundError') throw e;

                  const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;

                  if (sp && sp.hydrate) await sp.hydrate(it.fullKey);

                  url = await opfs.toUrl(it.fullKey);

                }

                window.open(url, '_blank');

                setTimeout(() => URL.revokeObjectURL(url), 60000);

              } catch (err) { console.error('[opfs] open in tab failed:', err); Sandpie.addMsg('err', 'Could not open ' + it.fullKey + ': ' + err.message); }

            }

          });

        }

        menuItems.push({


          label: 'Download',


          action: async () => {


            try {


              let bytes;


              try {


                bytes = await opfs.readBytes(it.fullKey);


              } catch (e) {


                if (e.name !== 'NotFoundError') throw e;


                const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;


                if (sp && sp.hydrate) await sp.hydrate(it.fullKey);


                bytes = await opfs.readBytes(it.fullKey);


              }


              const ext = it.name.split('.').pop().toLowerCase();


              const mime = ({html:'text/html', htm:'text/html', svg:'image/svg+xml',


                png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg', gif:'image/gif',


                webp:'image/webp', csv:'text/csv', json:'application/json',


                txt:'text/plain'})[ext] || 'application/octet-stream';


              const url = URL.createObjectURL(new Blob([bytes], { type: mime }));


              const a = document.createElement('a');


              a.href = url; a.download = it.name; a.style.display = 'none';


              document.body.appendChild(a); a.click();


              requestAnimationFrame(() => { a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); });


            } catch (e) { console.error('[opfs] download failed:', e); Sandpie.addMsg('err', 'Could not download ' + it.fullKey + ': ' + e.message); }


          }


        });


        if (it.name.endsWith('.tex')) {


          menuItems.push({


            label: 'Compile LaTeX → PDF',


            action: () => {


              const dirPath = it.fullKey.replace(/\/[^\/]+$/, '');


              window.open('/convert_latex/index.html?v=4#project=' + encodeURIComponent(dirPath), '_blank');


            }


          });


        }


      }


      if (it.kind === 'folder') {


        menuItems.push({ label: 'Download as zip', action: () => opfs.downloadFolderZip(it.fullKey) });


      }


      menuItems.push({ label: 'Delete', danger: true, action: async () => {


        try {


          // A dehydrated, cloud-only file has no local copy, so opfs.remove throws


          // NotFoundError — that must NOT abort the delete. Drop the local copy if


          // present, then ALWAYS emit file:deleted (→ Dropbox delete_v2 + removes


          // the cloud-index placeholder) and refresh.


          try { await opfs.remove(it.fullKey); } catch (_) {}


          if (window.Sandpie) Sandpie.events.emit('file:deleted', it.fullKey);


          await opfs.refreshFileList();


        } catch (e) { console.warn('delete failed:', it.fullKey, e); }


      }});


      // Sort-by (view setting for the whole list; folders always group first by


      // name, so this orders the files). Shown for both file and folder menus.


      const _sortMode = fileSortMode();


      menuItems.push({ info: true, label: 'Sort by' });


      menuItems.push({ label: (_sortMode === 'name'  ? '● ' : '○ ') + 'Alphabetical',  action: () => setFileSortMode('name') });


      menuItems.push({ label: (_sortMode === 'size'  ? '● ' : '○ ') + 'File size',     action: () => setFileSortMode('size') });


      menuItems.push({ label: (_sortMode === 'mtime' ? '● ' : '○ ') + 'Last modified', action: () => setFileSortMode('mtime') });


      const menu = opfs.showContextMenu(ev.clientX, ev.clientY, menuItems);


      if (it.kind === 'folder') {


        const infoEl = menu.querySelector('.ctx-info');


        opfs.getFolderSize(it.fullKey).then((sz) => {


          if (infoEl && infoEl.isConnected) infoEl.textContent = 'Size: ' + (opfs.formatSize(sz) || '0B');


        }).catch(() => { if (infoEl && infoEl.isConnected) infoEl.textContent = 'Size: —'; });


      }


    });


    frag.appendChild(li);


  };





  const items = await computeEntries(path);





  // At the root, lift the app's own sandpie/ folder into a collapsible "SANDPIE"


  // section (mirrors the conversations "Archived" toggle) so system files are


  // visually separated from the user's files, which render normally above it.


  const atRoot = !path;


  let sandpieEntry = null;


  let normalItems = items;


  if (atRoot) {


    sandpieEntry = items.find((it) => it.kind === 'folder' && it.name === 'sandpie') || null;


    if (sandpieEntry) normalItems = items.filter((it) => it !== sandpieEntry);


  }





  const fcEl = document.getElementById('fileCount');


  if (fcEl) fcEl.textContent = items.length ? `${items.length}` : '';





  if (!items.length) {


    const li = document.createElement('li');


    li.className = 'empty';


    li.textContent = (window.Sandpie && Sandpie.initialSyncDone()) ? '(empty)' : 'Loading…';


    ul.replaceChildren(li);


    return;


  }





  for (const it of normalItems) renderItem(it);





  // Collapsible SANDPIE section: a "▸ SANDPIE" header at the bottom that expands


  // in place to list sandpie/'s children (conversations, agents, skills, scripts,


  // artifacts, memory). State persists in localStorage; collapsed by default.


  if (sandpieEntry) {


    const SANDPIE_OPEN_KEY = 'sandpie-files-section-open';


    const open = localStorage.getItem(SANDPIE_OPEN_KEY) === '1';


    const toggle = document.createElement('li');


    toggle.className = 'sandpie-toggle';


    toggle.textContent = `${open ? '▾' : '▸'} SANDPIE`;


    toggle.title = "sandpie's own files — conversations, agents, skills, scripts, artifacts, memory";


    toggle.onclick = () => {


      const cur = localStorage.getItem(SANDPIE_OPEN_KEY) === '1';


      localStorage.setItem(SANDPIE_OPEN_KEY, cur ? '0' : '1');


      opfs.refreshFileList();


    };


    frag.appendChild(toggle);


    if (open) {


      const kids = await computeEntries('sandpie');


      if (!kids.length) {


        const li = document.createElement('li');


        li.className = 'empty sandpie-child';


        li.textContent = '(empty)';


        frag.appendChild(li);


      } else {


        for (const it of kids) renderItem(it, 'sandpie-child');


      }


    }


  }





  ul.replaceChildren(frag);


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







window.getFileSize = function(path) { return opfs.getFileSize(path); };


window.getFolderSize = function(path) { return opfs.getFolderSize(path); };


window.formatSize = function(bytes) { return opfs.formatSize(bytes); };


window.opfsCurrentPath = function() { return opfs.currentPath(); };


window.opfsJoin = function(base, child) { return base ? base + '/' + child : child; };


window.refreshFileList = function() { return opfs.refreshFileList(); };








window.opfs = opfs;


/* ---- opfs CLI commands (>>> ls, cd, mkdir, cat, rm) ----------------------- */


(function() {


  if (typeof SandpieCommands === 'undefined') return;





  let _cwd = '';





  function resolvePath(arg) {


    if (!arg) return _cwd;


    if (arg.startsWith('/')) return arg.replace(/^\/+/, '');


    return _cwd ? _cwd + '/' + arg : arg;


  }





  SandpieCommands.register({


    name: 'ls',


    module: 'opfs',


    help: 'List files in workspace or path',


    usage: '>>> ls [path]',


    async run(text, parts) {


      const path = resolvePath(parts[1] || '');


      try {


        const entries = await opfs.listDir(path);


        if (!entries.length) return path ? path + '/  (empty)' : '(workspace empty)';


        const rows = entries.map(e => {


          const p = path ? path + '/' + e.name : e.name;


          const icon = e.kind === 'directory' ? 'd' : '-';


          return icon + ' ' + p;


        });


        return _cwd ? 'cwd: ' + _cwd + '\n' + rows.join('\n') : rows.join('\n');


      } catch (err) {


        return 'Error: ' + err.message;


      }


    }


  });





  SandpieCommands.register({


    name: 'cd',


    module: 'opfs',


    help: 'Change working directory',


    usage: '>>> cd <path>',


    async run(text, parts) {


      if (!parts[1]) { _cwd = ''; return 'cwd: /'; }


      const target = resolvePath(parts[1]);


      try {


        await opfs.listDir(target);


        _cwd = target;


        return 'cwd: ' + (_cwd || '/');


      } catch (err) {


        return 'Error: ' + err.message;


      }


    }


  });





  SandpieCommands.register({


    name: 'mkdir',


    module: 'opfs',


    help: 'Create a folder',


    usage: '>>> mkdir <name>',


    async run(text, parts) {


      if (!parts[1]) return 'Usage: >>> mkdir <name>';


      const path = resolvePath(parts[1]);


      try {


        await opfs.mkdir(path);


        if (typeof refreshFileList === 'function') refreshFileList();


        return 'Created ' + path;


      } catch (err) {


        return 'Error: ' + err.message;


      }


    }


  });





  SandpieCommands.register({


    name: 'cat',


    module: 'opfs',


    help: 'View file contents',


    usage: '>>> cat <path>',


    async run(text, parts) {


      if (!parts[1]) return 'Usage: >>> cat <path>';


      const path = resolvePath(parts[1]);


      try {


        const text = await opfs.read(path);


        return text;


      } catch (err) {


        return 'Error: ' + err.message;


      }


    }


  });





  SandpieCommands.register({


    name: 'rm',


    module: 'opfs',


    help: 'Delete file or folder',


    usage: '>>> rm <path>',


    async run(text, parts) {


      if (!parts[1]) return 'Usage: >>> rm <path>';


      const path = resolvePath(parts[1]);


      if (!confirm('Delete "' + path + '"?')) return '(cancelled)';


      try {


        await opfs.remove(path);


        if (typeof refreshFileList === 'function') refreshFileList();


        return 'Deleted ' + path;


      } catch (err) {


        return 'Error: ' + err.message;


      }


    }


  });


})();








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


  document.addEventListener('DOMContentLoaded', () => { initFileBrowser(); sandpiePersistence.check(); });


} else {


  initFileBrowser();


  sandpiePersistence.check();


}


