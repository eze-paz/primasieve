// sandpie OPFS core — filesystem primitives and path utilities





// File-viewer preview type sets + text-preview size cap (used by openFile below).


const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif']);


const VIDEO_EXTS = new Set(['mp4', 'webm', 'mov', 'm4v']);


const AUDIO_EXTS = new Set(['mp3', 'wav', 'ogg', 'oga', 'flac', 'm4a', 'aac']);







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


  // EVERY save in the app funnels through here, so this is where "a file changed"
  // is announced. Without it a write is invisible: the file viewer's Save, an
  // editor, a module writing a file — all left the sync state saying "clean", so
  // Dropbox never uploaded them (the mechanism was fine; nothing was telling it).
  // Listeners: dropbox.js (marks dirty → uploads on the next sync) and sharing.js
  // (pushes an installed team file back to the hub). Both filter what they own,
  // and both suppress their OWN writes, so downloads can't bounce back as uploads.
  async write(path, content) {


    const { parts, name } = splitPath(path);


    const dir = await this.resolveDir(parts, { create: true });


    const handle = await dir.getFileHandle(name, { create: true });


    const w = await handle.createWritable();


    await w.write(content);


    await w.close();


    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', path); } catch (_) {}


  },


  // Append to the end of a file (creating it if absent) WITHOUT rewriting existing
  // bytes. Preferred path: a dedicated worker holding a FileSystemSyncAccessHandle,
  // which writes in place at end-of-file — a true O(1) append with no swap file.
  // Fallback (worker unavailable / errored / SyncAccessHandle unsupported): open a
  // writable keeping existing data and do one positioned write at the current size.
  // That is O(new bytes) at the API level, but some Chromium versions copy the whole
  // file through a swap on close() — which is exactly what the worker path avoids.
  async append(path, content) {
    if (content == null || content === '') return;
    if (await this._appendViaWorker(path, content)) return;
    await this._appendViaWritable(path, content);
  },
  async _appendViaWritable(path, content) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts, { create: true });
    const handle = await dir.getFileHandle(name, { create: true });
    const size = (await handle.getFile()).size;
    const w = await handle.createWritable({ keepExistingData: true });
    await w.write({ type: 'write', position: size, data: content });
    await w.close();
  },
  // Lazily spin up the append worker and RPC one append across. Returns true on a
  // confirmed in-place append, false if the worker route is unavailable/failed (so
  // the caller falls back). Once construction fails we latch _appendWorker=false and
  // never retry — every subsequent append takes the writable path with no overhead.
  _appendWorker: undefined,        // undefined=untried, Worker=ready, false=disabled
  _appendSeq: 0,
  _appendPending: null,            // Map<seq, {resolve}>
  async _appendViaWorker(path, content) {
    try {
      if (this._appendWorker === false) return false;
      if (this._appendWorker === undefined) {
        // Feature-gate: SyncAccessHandle is worker-only and Chromium-specific.
        if (typeof Worker === 'undefined' || typeof navigator === 'undefined' || !navigator.storage || !navigator.storage.getDirectory) {
          this._appendWorker = false; return false;
        }
        this._appendPending = new Map();
        const w = new Worker('./modules/opfs-append-worker.js?v=1');
        w.onmessage = (e) => {
          const { seq, ok, error } = e.data || {};
          const p = this._appendPending.get(seq);
          if (!p) return;
          this._appendPending.delete(seq);
          if (ok) p.resolve(true); else p.reject(new Error(error || 'append failed'));
        };
        w.onerror = () => {
          // Worker died: fail every in-flight append so callers fall back, then latch off.
          this._appendWorker = false;
          for (const p of this._appendPending.values()) p.reject(new Error('append worker error'));
          this._appendPending.clear();
        };
        this._appendWorker = w;
      }
      const seq = ++this._appendSeq;
      await new Promise((resolve, reject) => {
        this._appendPending.set(seq, { resolve, reject });
        this._appendWorker.postMessage({ seq, path, data: content });
      });
      return true;
    } catch (_) {
      return false;   // fall back to the writable path for this one append
    }
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


      info.className = 'ctx-info' + (item.className ? ' ' + item.className : '');


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


// ── File viewer ──────────────────────────────────────────────────────────────
// The viewer proper lives in modules/file-viewer.js: ONE side pane, no modal.
// Office (docx/xlsx/…) render via LibreOffice-WASM (ZetaOffice); text files get
// an editable pane. The old in-place modal viewer (~940 lines) was removed; this
// stub keeps the historical entry point and signature for callers (artifacts.js,
// conversations.js file chips).
opfs.openFile = async function(fullKey, name, opts = {}) {
  if (window.SandpieFileViewer) return SandpieFileViewer.open(fullKey, name, opts);
  try { Sandpie.addMsg('err', 'file viewer module not loaded'); } catch (_) {}
};

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


// Rename a file or folder. OPFS has no native rename, so this is copy-to-new +
// remove-old, driven through the same file:changed / file:deleted events the rest
// of the app uses (so Dropbox sync uploads the new path and deletes the old). Pins
// pointing at a moved path are rewritten, and an open viewer follows the rename.
opfs.renameEntry = async function(fullKey, kind) {
  if (!fullKey) return;
  const base = fullKey.includes('/') ? fullKey.slice(0, fullKey.lastIndexOf('/')) : '';
  const cur = fullKey.split('/').pop();
  const input = prompt('Rename ' + (kind === 'folder' ? 'folder' : 'file') + ':', cur);
  if (input === null) return;                                  // cancelled
  const clean = input.trim().replace(/[\\/:*?"<>|]/g, '_');
  if (!clean || clean === cur) return;
  const newPath = base ? base + '/' + clean : clean;
  const movePin = (from, to) => { if (window.SandpiePins && SandpiePins.isPinned(from)) { SandpiePins.remove(from); SandpiePins.add(to); } };
  try {
    if (kind === 'folder') {
      const files = await opfs.list(fullKey);                  // recursive descendant file paths
      if (!files.length) { await opfs.mkdir(newPath); }
      for (const f of files) {
        const rel = f.slice(fullKey.length).replace(/^\/+/, '');
        const dest = rel ? newPath + '/' + rel : newPath;
        await opfs.write(dest, new Blob([await opfs.readBytes(f)]));
        if (window.Sandpie) Sandpie.events.emit('file:changed', dest);
        movePin(f, dest);
        if (window._openFilePath === f && opfs.openFile) { opfs.closeFile && opfs.closeFile(); opfs.openFile(dest, dest.split('/').pop()); }
      }
      await opfs.remove(fullKey);
      if (window.Sandpie) Sandpie.events.emit('file:deleted', fullKey);
    } else {
      // Guard against clobbering an existing file at the target name.
      let exists = false; try { await opfs.readBytes(newPath); exists = true; } catch (_) {}
      if (exists) { alert('A file named "' + clean + '" already exists here.'); return; }
      await opfs.write(newPath, new Blob([await opfs.readBytes(fullKey)]));
      await opfs.remove(fullKey);
      if (window.Sandpie) { Sandpie.events.emit('file:changed', newPath); Sandpie.events.emit('file:deleted', fullKey); }
      movePin(fullKey, newPath);
      if (window._openFilePath === fullKey && opfs.openFile) { opfs.closeFile && opfs.closeFile(); opfs.openFile(newPath, clean); }
    }
    await opfs.refreshFileList();
  } catch (e) { console.warn('rename failed:', fullKey, '→', newPath, e); alert('Could not rename: ' + (e && e.message || e)); }
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





// ── clean, shareable URLs for OPFS files ────────────────────────────────────
// sw.js serves /files/<path> straight out of OPFS (hydrating a cloud-only file
// via a page round-trip), so anything we'd otherwise hand out as an opaque
// blob: URL can be a real https://<host>/files/sandpie/artifacts/x.html instead:
// readable, copy-pasteable, reloadable, and — being a real same-origin URL —
// able to resolve its own sibling assets (../img/foo.png) through the SW too.
// Each segment is encoded; sw.js decodeURIComponent-s them back.
opfs.filesUrl = function(path) {
  return '/files/' + String(path).split('/').filter(Boolean).map(encodeURIComponent).join('/');
};

// Only usable while sw.js is actually CONTROLLING this page — with no controller
// a /files/ URL goes to the server, which knows nothing about OPFS and 404s. So
// every caller keeps the blob: path as a fallback (first load before the SW
// activates, a hard-reloaded page, an insecure context, SW registration failed).
opfs.filesUrlReady = function() {
  try { return !!(navigator.serviceWorker && navigator.serviceWorker.controller); }
  catch (_) { return false; }
};

// Open an OPFS file in a new tab: the clean /files/ URL when the SW can serve
// it, otherwise a blob: URL from the bytes. opts.blobUrl() overrides how the
// fallback URL is built (used by the viewer, which serves unsaved edits).
opfs.openInNewTab = async function(path, opts = {}) {
  const clean = String(path).replace(/^\/+/, '');
  if (opfs.filesUrlReady()) { window.open(opfs.filesUrl(clean), '_blank'); return true; }
  const url = opts.blobUrl ? await opts.blobUrl() : await opfs.toUrl(clean);
  window.open(url, '_blank');
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return false;
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


    // Console capture bootstrap — must run BEFORE the artifact's own scripts so
    // load-time console calls / errors are caught too. Buffers into
    // window.__sandpieConsole (read by the html_console tool via the page).
    const cap = `<script>(function(){` +
      `if(window.__sandpieConsole)return;` +
      `var __b=[],__cap=200;` +
      `function __p(lvl,args){var parts=[];for(var i=0;i<args.length;i++){var a=args[i],s;` +
      `try{if(typeof a==='string')s=a;else if(a&&a.message&&a.stack)s=a.message;else s=JSON.stringify(a);}catch(_){s=String(a);}parts.push(s);}` +
      `var line=lvl+': '+parts.join(' ');if(__b.length>=__cap)__b.shift();__b.push(line);}` +
      `['log','info','warn','error','debug'].forEach(function(m){var o=console[m]&&console[m].bind(console);` +
      `console[m]=function(){__p(m.toUpperCase(),arguments);if(o)o.apply(null,arguments);};});` +
      `window.addEventListener('error',function(e){__p('ERROR',[(e.message||'')+(e.filename?(' @ '+e.filename.split('/').pop()+(e.lineno?(':'+e.lineno):'')):'')]);},true);` +
      `window.addEventListener('unhandledrejection',function(e){var r=e.reason;__p('UNHANDLED',[(r&&r.message)||String(r)]);});` +
      `window.__sandpieConsole=__b;` +
      `})();<\/script>`;


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


    // Screenshot bootstrap (screenshot.js). The HEAD half patches getContext to
    // force preserveDrawingBuffer and MUST land before the artifact's own scripts,
    // or WebGL artifacts rasterize blank. The BODY half answers capture requests.
    const shotHead = (window.SandpieScreenshot && window.SandpieScreenshot.HEAD_BOOTSTRAP) || '';
    const shotBody = (window.SandpieScreenshot && window.SandpieScreenshot.BODY_BOOTSTRAP) || '';

    // console capture FIRST (before any artifact script), resize LAST (needs layout).
    // Function replacers, not string ones — a literal $& / $1 anywhere in an
    // injected script would otherwise be eaten as a replacement pattern.
    const head = cap + shotHead;
    const tail = script + shotBody;
    if (/<head[^>]*>/i.test(text)) text = text.replace(/<head([^>]*)>/i, (m, attrs) => '<head' + attrs + '>' + head);
    else text = head + text;
    if (/<\/body>/i.test(text)) text = text.replace(/<\/body>/i, () => tail + '</body>');
    else text += tail;
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


    btn.title = it.fullKey;


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


      if (it.kind === 'folder') menuItems.push({ info: true, label: 'Size: …', className: 'ctx-size' });


      menuItems.push({ label: 'Copy path', action: () => { navigator.clipboard.writeText(it.fullKey).catch(() => {}); } });


      // Share is offered on installed packages too (an editor can re-publish them);
      // only the 1:1 delivery inbox stays unpublishable.
      if (window.SandpieSharing && !it.fullKey.startsWith('sandpie/shared-incoming')) {
        menuItems.push({ label: '🔗 Share…', action: () => SandpieSharing.shareDialog(it.fullKey, it.kind === 'folder' ? undefined : 'artifact') });
      }


      menuItems.push({ label: 'Rename ' + (it.kind === 'folder' ? 'folder' : 'file'), action: () => opfs.renameEntry(it.fullKey, it.kind) });


      menuItems.push({ label: 'Upload files', action: () => opfs.promptUpload(opfsCurrentPath()) });


      menuItems.push({ label: 'New folder', action: () => opfs.createFolder() });


      menuItems.push({ label: 'New file', action: () => opfs.createFile() });


      if (it.kind === 'file') {


const _isPinned = !!(window.SandpiePins && SandpiePins.isPinned(it.fullKey));
        menuItems.push({ label: (_isPinned ? '📌 Unpin file' : '📌 Pin file'), action: () => { if (window.SandpiePins) SandpiePins.toggle(it.fullKey); } });
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

                // Clean /files/ URL when the SW is live (it hydrates a cloud-only
                // file itself); otherwise fall back to a blob URL, hydrating here.

                if (opfs.filesUrlReady()) { window.open(opfs.filesUrl(it.fullKey), '_blank'); return; }

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


      menuItems.push({ info: true, label: 'Sort by', className: 'ctx-sort-header' });


      menuItems.push({ label: (_sortMode === 'name'  ? '● ' : '○ ') + 'Alphabetical',  action: () => setFileSortMode('name') });


      menuItems.push({ label: (_sortMode === 'size'  ? '● ' : '○ ') + 'File size',     action: () => setFileSortMode('size') });


      menuItems.push({ label: (_sortMode === 'mtime' ? '● ' : '○ ') + 'Last modified', action: () => setFileSortMode('mtime') });


      const menu = opfs.showContextMenu(ev.clientX, ev.clientY, menuItems);


      if (it.kind === 'folder') {
        const sizeEl = menu.querySelector('.ctx-size');
        opfs.getFolderSize(it.fullKey).then((sz) => {
          if (sizeEl && sizeEl.isConnected) sizeEl.textContent = 'Size: ' + (opfs.formatSize(sz) || '0B');
        }).catch(() => { if (sizeEl && sizeEl.isConnected) sizeEl.textContent = 'Size: —'; });





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





  // Collapsible SANDPIE section: a "SANDPIE ▸" header at the bottom that expands


  // in place to list sandpie/'s children (conversations, agents, skills, scripts,


  // artifacts, memory). State persists in localStorage; collapsed by default.


  if (sandpieEntry) {


    const SANDPIE_OPEN_KEY = 'sandpie-files-section-open';


    const open = localStorage.getItem(SANDPIE_OPEN_KEY) === '1';


    const toggle = document.createElement('li');


    toggle.className = 'sandpie-toggle';


    toggle.textContent = `SANDPIE ${open ? '▾' : '▸'}`;


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





// Boot-time hygiene for sandpie/scripts/ (the run_python scratch dir): keep it
// FLAT — subfolders are not permitted and are deleted wholesale — and capped at
// 100 files (oldest overflow deleted). Runs once on page load, never on an
// interval. Deletion uses the canonical page-side pattern (opfs.remove + emit
// file:deleted), so the Dropbox provider trims its state/cloud index and issues
// delete_v2 — full propagation, identical to the context-menu Delete. In
// dehydrated mode most scripts are cloud-only placeholders (no local bytes), so
// the count merges the provider's sync state + cloud index; cloud-only entries
// still get deleted remotely (opfs.remove throws NotFound; the file:deleted
// event does the rest).
opfs.pruneScriptsDir = async function() {
  const DIR = 'sandpie/scripts';
  const MAX_FILES = 100;
  const _sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;
  const state = (_sp && _sp.getState) ? (_sp.getState() || {}) : {};
  const cidx = (_sp && _sp.cloudIndex) ? (_sp.cloudIndex() || {}) : null;
  const prefix = DIR + '/';
  const del = async (fullKey) => {
    try { await opfs.remove(fullKey); } catch (_) {}   // cloud-only → NotFound is fine
    if (window.Sandpie) Sandpie.events.emit('file:deleted', fullKey);
  };
  let local = [];
  try { local = await opfs.listDir(DIR); } catch (_) { return; }   // no scripts dir yet → nothing to do
  // Merge local OPFS + sync state + cloud index into the DIRECT children of DIR.
  const byName = new Map();
  for (const e of local) byName.set(e.name, { kind: e.kind === 'directory' ? 'folder' : 'file', local: true });
  const addRemote = (rel, kind) => {
    if (!String(rel).startsWith(prefix)) return;
    const rest = rel.slice(prefix.length);
    if (!rest || rest.includes('/')) return;          // not a direct child (subfolder contents ride with the folder)
    const cur = byName.get(rest);
    if (!cur) byName.set(rest, { kind });
    else if (kind === 'folder') cur.kind = 'folder';
  };
  for (const k of Object.keys(state)) addRemote(k, 'file');          // sync state only tracks files
  if (cidx) for (const k of Object.keys(cidx)) addRemote(k, cidx[k] && cidx[k].kind === 'folder' ? 'folder' : 'file');
  const folders = [], files = [];
  for (const [name, info] of byName) {
    const fullKey = prefix + name;
    if (info.kind === 'folder') { folders.push(fullKey); continue; }
    let mt = info.local ? await opfs.lastModified(fullKey) : 0;
    if (!mt && cidx && cidx[fullKey] && cidx[fullKey].cloudMtime) mt = Date.parse(cidx[fullKey].cloudMtime) || 0;
    if (!mt && state[fullKey] && state[fullKey].syncedMtime) mt = state[fullKey].syncedMtime;
    files.push({ fullKey, mt });
  }
  // Flatness: subfolders inside scripts/ are not permitted — delete them whole.
  for (const f of folders) { try { await del(f); } catch (_) {} }
  if (!files.length) return;
  // Cap at MAX_FILES: oldest first, delete the overflow.
  files.sort((a, b) => (a.mt - b.mt) || a.fullKey.localeCompare(b.fullKey));
  const overflow = files.length - MAX_FILES;
  for (let i = 0; i < overflow; i++) { try { await del(files[i].fullKey); } catch (_) {} }
  if (overflow > 0 || folders.length) { try { opfs.refreshFileList(); } catch (_) {} }
};




// Sandbox allowlist: /files/sandpie/ may contain ONLY these system folders (app data,
// hub-installed packages, share inbox). No loose files, no stray folders — anything
// else (created by a tool that slipped) is deleted wholesale via the canonical delete
// path, so it propagates to Dropbox through the delete handshake. sandpie/artifacts is
// deferred while the one-time migrateArtifactsOut() (dropbox.js, 'dbxfull-artifacts-out'
// flag) hasn't run — deleting it first would lose real deliverables.
const SANDBOX_ALLOW = new Set(['config', 'conversations', 'fonts', 'memory', 'scripts', 'secrets', 'shared-installed', 'skills', 'agents', 'shared-incoming']);
opfs.pruneSandboxFolders = async function() {
  const prefix = 'sandpie/';
  const _sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;
  const state = (_sp && _sp.getState) ? (_sp.getState() || {}) : {};
  const cidx = (_sp && _sp.cloudIndex) ? (_sp.cloudIndex() || {}) : null;
  const pendingMigration = !localStorage.getItem('dbxfull-artifacts-out');
  const del = async (fullKey) => {
    try { await opfs.remove(fullKey); } catch (_) {}   // cloud-only → NotFound is fine
    if (window.Sandpie) Sandpie.events.emit('file:deleted', fullKey);
  };
  let local = [];
  try { local = await opfs.listDir('sandpie'); } catch (_) { return; }   // no sandbox yet
  const byName = new Map();
  for (const e of local) byName.set(e.name, true);
  const addRemote = (rel) => {
    if (!String(rel).startsWith(prefix)) return;
    const rest = rel.slice(prefix.length);
    if (!rest || rest.includes('/')) return;   // only direct children
    byName.set(rest, true);
  };
  for (const k of Object.keys(state)) addRemote(k);
  if (cidx) for (const k of Object.keys(cidx)) addRemote(k);
  let changed = false;
  for (const name of byName.keys()) {
    if (SANDBOX_ALLOW.has(name)) continue;
    if (pendingMigration && name === 'artifacts') continue;   // let migrateArtifactsOut() move it first
    await del(prefix + name);
    changed = true;
  }
  if (changed) { try { opfs.refreshFileList(); } catch (_) {} }
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
  // Sidebar resize via drag handle
  const sidebar = document.querySelector('aside');
  const handle = document.getElementById('sidebarResizeHandle');
  if (sidebar && handle) {
    // Restore saved width
    const saved = localStorage.getItem('sandpie-sidebar-width');
    if (saved) {
      sidebar.style.setProperty('--sidebar-width', saved + 'px');
    }
    // Position handle on the right edge of <aside> (outside the scrollbar)
    const positionHandle = () => {
      const rect = sidebar.getBoundingClientRect();
      handle.style.left = (rect.right - 2) + 'px';
    };
    positionHandle();
    window.addEventListener('resize', positionHandle);
    // Observe attribute changes (e.g. collapsed class toggled)
    const observer = new MutationObserver(positionHandle);
    observer.observe(sidebar, { attributes: true, attributeFilter: ['class', 'style'] });
    let startX, startW;
    const onMouseMove = (e) => {
      const w = Math.max(160, Math.min(600, startW + (e.clientX - startX)));
      sidebar.style.setProperty('--sidebar-width', w + 'px');
      handle.style.left = (sidebar.getBoundingClientRect().right - 2) + 'px';
    };
    const onMouseUp = (e) => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      handle.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      // Save
      const w = parseInt(sidebar.style.getPropertyValue('--sidebar-width'));
      if (w) localStorage.setItem('sandpie-sidebar-width', w);
    };
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      startX = e.clientX;
      startW = sidebar.getBoundingClientRect().width;
      handle.classList.add('active');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  }

  refreshFileList();

  // Boot-time scripts-dir hygiene (one-shot on load — no running checks): cap
  // sandpie/scripts/ at 100 files and keep it flat. dropbox.js loads before
  // opfs.js, so by this point its boot() has attached the file:deleted listener
  // and every deletion below propagates to Dropbox (delete_v2 + index trim).
  try { if (window.opfs && opfs.pruneScriptsDir) opfs.pruneScriptsDir().catch((e) => console.warn('[opfs] scripts prune:', e)); } catch (_) {}

  // Boot-time sandbox allowlist (system-only folders under sandpie/). Deleting a stray
  // folder propagates to Dropbox via the delete handshake.
  try { if (window.opfs && opfs.pruneSandboxFolders) opfs.pruneSandboxFolders().catch((e) => console.warn('[opfs] sandbox prune:', e)); } catch (_) {}

}


if (document.readyState === 'loading') {


  document.addEventListener('DOMContentLoaded', () => { initFileBrowser(); sandpiePersistence.check(); });


} else {


  initFileBrowser();


  sandpiePersistence.check();


}


