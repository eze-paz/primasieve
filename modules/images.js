// sandpie/images.js - Attachment handling module
// Despite the name (kept for its established public API), this owns the
// composer's attachments for ANY file type, and the app-wide drag-and-drop:
//   • the entire window is a drop zone — dropping file(s) anywhere attaches
//     them, exactly as the attach button does;
//   • images (png/jpg/gif/webp/bmp/avif/svg, and HEIC/HEIF after conversion)
//     keep the thumbnail path and are sent to the model as a vision image_url;
//   • every other file is saved to OPFS and referenced — small text files are
//     inlined at send time, everything else is handed to the model as a path it
//     can open with the run_python tool (the SW mounts OPFS at /files);
//   • every attached file is uploaded to OPFS (visible in the sidebar) and
//     synced into the run_python MEMFS mount via opfs.notifyUpload().
// Multiple attachments are supported. Send-time resolution lives in
// conversations.js (buildAgentConfig).

const SandpieImages = (function() {
  'use strict';

  const $ = id => document.getElementById(id);

  // ============================================================
  // PRIVATE STATE
  // ============================================================

  // Attachments (in order) PER COMPOSER — 'main' is the left pane, 'side' the
  // right. Both can be open on different conversations at once, so an attachment
  // belongs to the composer whose + button (or textarea) produced it. One shared
  // list showed every attachment in BOTH previews and made a single ✕ remove it
  // from both. Each entry:
  //   { kind:'image', opfsPath, name, mime, size, thumb, file:{name,type} }
  //   { kind:'file',  opfsPath, name, mime, size, isText, file:{name,type} }
  const _byPane = { main: [], side: [] };
  const _pane = w => (w === 'side' ? 'side' : 'main');
  const _list = w => _byPane[_pane(w)];
  const _previewEl = w => document.getElementById(_pane(w) === 'side' ? 'imagePreviewSide' : 'imagePreview');
  const _inputEl = w => document.getElementById(_pane(w) === 'side' ? 'imageInputSide' : 'imageInput');
  // Which composer a node belongs to, or null when it isn't inside one.
  const _paneOfEl = (el) => {
    if (!el || !el.closest) return null;
    const form = el.closest('.composer');
    if (form) return form.classList.contains('composer-side') ? 'side' : 'main';
    const host = el.closest('#messages, #messagesSide');
    if (host) return host.id === 'messagesSide' ? 'side' : 'main';
    return null;
  };
  // Fallback when there is no element to derive the pane from (a window-level
  // paste): whichever pane the app is focused on. body.active-right is set only
  // while the split is open, so this is 'main' in the single-pane case.
  const _activePane = () => {
    const b = document.body.classList;
    return (b.contains('side-open') && b.contains('active-right')) ? 'side' : 'main';
  };

  // Browser-renderable raster/vector image extensions (re-encoded to JPEG before
  // the model sees them) and the iPhone HEIC family (decoded via heic2any).
  const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'svg']);
  const HEIC_EXTS = new Set(['heic', 'heif']);

  // ============================================================
  // PRIVATE HELPERS
  // ============================================================

  const extOf = name => (String(name || '').split('.').pop() || '').toLowerCase();

  /**
   * Compress image to max dimension
   * @param {HTMLImageElement} img - Loaded image
   * @param {number} maxDim - Maximum width/height
   * @param {number} quality - JPEG quality (0-1)
   * @returns {string} Data URL
   */
  function compressImage(img, maxDim, quality) {
    let w = img.width, h = img.height;
    if (w > maxDim || h > maxDim) {
      if (w > h) {
        h = Math.round(h * maxDim / w);
        w = maxDim;
      } else {
        w = Math.round(w * maxDim / h);
        h = maxDim;
      }
    }
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';            // flatten any transparency — JPEG has no alpha
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    return canvas.toDataURL('image/jpeg', quality);
  }

  // Per-image base64 budget for an LLM request. Must stay well under the upstream
  // gateway's ~1 MB whole-body cap so the system prompt + tools + history still
  // fit alongside the image. Keep in sync with IMAGE_MAX_B64_BYTES in
  // sandpie-worker.js (the load_image tool path).
  const LLM_IMAGE_TARGET_B64 = 700 * 1024;

  // Downscale + re-encode `img` (JPEG) until the data URL fits `targetBytes`.
  // Walks smaller max-dimensions × qualities and returns the FIRST that fits (so
  // most images keep high resolution/quality), else the smallest achieved. The
  // data-URL prefix adds ~23 chars over the raw base64 — negligible vs the target.
  function compressImageToTarget(img, targetBytes) {
    const DIMS = [1568, 1024, 768, 512, 384];
    const QUALS = [0.7, 0.5];
    let best = null;
    for (const maxDim of DIMS) {
      for (const q of QUALS) {
        const url = compressImage(img, maxDim, q);
        if (url.length <= targetBytes) return url;
        if (!best || url.length < best.length) best = url;
      }
    }
    return best;
  }

  /**
   * Get MIME type from file extension
   * @param {string} path - File path
   * @returns {string} MIME type
   */
  function getMimeType(path) {
    const ext = path.split('.').pop().toLowerCase();
    const mimeTypes = {
      png: 'image/png',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
      gif: 'image/gif',
      webp: 'image/webp',
      bmp: 'image/bmp',
      avif: 'image/avif',
      svg: 'image/svg+xml',
    };
    return mimeTypes[ext] || 'image/jpeg';
  }

  /**
   * Load image from blob
   * @param {Blob} blob - Image blob
   * @returns {Promise<HTMLImageElement>}
   */
  function loadImageFromBlob(blob) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = URL.createObjectURL(blob);
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Failed to load image')); };
      img.src = url;
    });
  }

  // heic2any (libheif WASM, ~1.5MB) is lazy-loaded the first time a HEIC/HEIF is
  // attached — browsers other than Safari can't decode HEIC natively, so without
  // this the canvas path fails and the photo would attach as an opaque file.
  let _heicPromise = null;
  function loadHeic2any() {
    if (!_heicPromise) {
      _heicPromise = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/heic2any@0.0.4/dist/heic2any.min.js';
        s.onload = () => resolve(window.heic2any);
        s.onerror = () => { _heicPromise = null; reject(new Error('Could not load the HEIC decoder')); };
        document.head.appendChild(s);
      });
    }
    return _heicPromise;
  }

  // Resolve the folder new attachments should land in, fresh at call time
  // (just-in-time — the file-viewer's current folder can change between init and
  // the actual attach). Returns '' for root. Never a hidden bucket: if the path
  // can't be resolved we fall back to root, which is always visible in the
  // sidebar, so an attach can never "disappear" into a folder the user can't see.
  function currentBasePath() {
    try {
      if (typeof opfsCurrentPath === 'function') {
        return (opfsCurrentPath() || '').trim().replace(/^\/+|\/+$/g, '');
      }
    } catch (_) { /* #opfsPath not mounted yet — treat as root */ }
    return '';
  }

  // Pick a non-colliding OPFS path under dir/ so attaching never clobbers an
  // existing file with the same name. An empty dir means the OPFS root (no
  // leading slash).
  async function uniquePath(dir, name) {
    const safe = String(name).replace(/[\\/:*?"<>|]/g, '_') || 'file';
    const join = (d, f) => (d ? d + '/' + f : f);
    let p = join(dir, safe);
    if (!(await opfs.exists(p))) return p;
    const dot = safe.lastIndexOf('.');
    const base = dot > 0 ? safe.slice(0, dot) : safe;
    const ext = dot > 0 ? safe.slice(dot) : '';
    for (let i = 2; i < 1000; i++) {
      p = join(dir, `${base}-${i}${ext}`);
      if (!(await opfs.exists(p))) return p;
    }
    return join(dir, `${base}-${Date.now()}${ext}`);
  }

  // Decide whether a file's bytes are UTF-8 text (→ inline at send time) or
  // binary (→ reference by path). Mirrors opfs.openFile's heuristic: reject on a
  // NUL byte, else allow if the decoded sample is <2% replacement characters.
  function looksTextual(bytes) {
    const sample = bytes.subarray(0, 65536);
    for (let i = 0; i < Math.min(sample.length, 8000); i++) if (sample[i] === 0) return false;
    const text = new TextDecoder('utf-8').decode(sample);
    let bad = 0;
    for (const ch of text) if (ch === '�') bad++;
    return bad / Math.max(text.length, 1) < 0.02;
  }

  // Emoji glyph for a document chip, by extension/mime.
  function iconFor(name, mime) {
    const e = extOf(name);
    if (e === 'pdf') return '📕';
    if (['doc', 'docx', 'odt', 'rtf', 'pages'].includes(e)) return '📘';
    if (['xls', 'xlsx', 'ods', 'csv', 'tsv', 'numbers'].includes(e)) return '📊';
    if (['ppt', 'pptx', 'odp', 'key'].includes(e)) return '📙';
    if (['zip', 'gz', 'tgz', 'tar', 'rar', '7z', 'bz2', 'xz'].includes(e)) return '🗜️';
    if (['mp3', 'wav', 'ogg', 'oga', 'flac', 'm4a', 'aac'].includes(e)) return '🎵';
    if (['mp4', 'mov', 'webm', 'mkv', 'avi', 'm4v'].includes(e)) return '🎬';
    if ((mime || '').startsWith('image/') || IMAGE_EXTS.has(e) || HEIC_EXTS.has(e)) return '🖼️';
    return '📄';
  }

  // ============================================================
  // COMPOSER PREVIEW (multiple attachments)
  // ============================================================

  // Renders ONE pane's preview from that pane's list. Deliberately not a
  // querySelectorAll over every .image-preview: that is what mirrored a single
  // attachment into both composers.
  function renderPreviews(which) {
    const pv = _previewEl(which);
    if (!pv) return;
    const list = _list(which);
    pv.innerHTML = '';
    pv.style.display = list.length ? '' : 'none';
    if (!list.length) return;
    list.forEach((att, i) => {
      const item = document.createElement('span');
      item.className = 'attach-item';
      if (att.kind === 'image') {
        const img = document.createElement('img');
        img.src = att.thumb || '';
        img.alt = att.name || '';
        img.title = att.name || '';
        item.appendChild(img);
      } else {
        const chip = document.createElement('span');
        chip.className = 'file-chip';
        const icon = document.createElement('span');
        icon.className = 'fc-icon';
        icon.textContent = iconFor(att.name, att.mime);
        const nm = document.createElement('span');
        nm.className = 'fc-name';
        nm.textContent = att.name;
        const sz = document.createElement('span');
        sz.className = 'fc-size';
        sz.textContent = opfs.formatSize(att.size) || '';
        chip.append(icon, nm, sz);
        item.appendChild(chip);
      }
      const rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'remove-btn';
      rm.title = 'Remove';
      rm.textContent = '✕';
      rm.onclick = () => removeAt(which, i);
      item.appendChild(rm);
      pv.appendChild(item);
    });
  }

  // Removes from ONE pane. `which` is required in practice — the ✕ handlers above
  // always pass their own pane — but an omitted value falls back to the focused
  // pane rather than mutating both.
  function removeAt(which, i) {
    const list = _list(which);
    if (i < 0 || i >= list.length) return;
    list.splice(i, 1);
    renderPreviews(which);
  }

  // ============================================================
  // ATTACH PATHS (push to the pane's list; caller calls renderPreviews(pane) once)
  // ============================================================

  // If the ACTIVE model is text-only (vision:no) and has no vision fallback, warn
  // at attach time — the image would otherwise 400 at send. Silent when the model
  // can see, or a fallback exists (the send will reroute).
  function _warnVisionFallback(name) {
    try {
      if (typeof SandpieProviders === 'undefined') return;
      // Per-conversation provider: resolve the focused conversation's model
      // (resolve(null) → active conv), falling back to the catalog default.
      const act = SandpieProviders.resolve ? SandpieProviders.resolve(null)
                : (SandpieProviders.getActive ? SandpieProviders.getActive() : null);
      if (!act) return;
      const canSee = SandpieProviders.providerCanSee ? SandpieProviders.providerCanSee(act) : true;
      const hasFb = !!(SandpieProviders.resolveVisionFallback && SandpieProviders.resolveVisionFallback(act));
      if (!canSee && !hasFb) {
        const who = act.name || act.model || 'This model';
        if (typeof opfs !== 'undefined' && opfs._toast) opfs._toast('⚠ ' + who + " can't see images and has no vision fallback — set one in Settings → AI provider, or the send will fail.", 6000);
      }
    } catch (_) {}
  }

  async function attachImage(file, { basePath = null, addComposerChip = false, pane = null } = {}) {
    let blob = file;
    let name = file.name || ("image_" + Date.now() + ".jpg");
    if (HEIC_EXTS.has(extOf(name)) || /heic|heif/i.test(file.type || "")) {
      const convert = await loadHeic2any();
      const out = await convert({ blob: file, toType: "image/jpeg", quality: 0.9 });
      blob = Array.isArray(out) ? out[0] : out;
      name = name.replace(/\.(heic|heif)$/i, "") + ".jpg";
    }
    const bytes = new Uint8Array(await blob.arrayBuffer());
    // Validate it actually decodes (and produce the thumbnail). Throws for
    // formats the browser can't render – addFiles falls back to a file attach.
    const imgEl = await loadImageFromBlob(new Blob([bytes], { type: blob.type || getMimeType(name) }));
    const thumb = compressImage(imgEl, 200, 0.7);

    const dir = (basePath != null ? basePath : currentBasePath());
    const opfsPath = await uniquePath(dir, name);
    await opfs.write(opfsPath, bytes);
    opfs.notifyUpload(opfsPath);   // sidebar + run_python /files mount
    if (addComposerChip) {
      _list(pane).push({
        kind: "image", opfsPath, name, thumb,
        mime: blob.type || getMimeType(opfsPath), size: bytes.length,
        file: { name, type: blob.type || getMimeType(opfsPath) },
      });
      _warnVisionFallback(name);
    }
    return opfsPath;
  }

  async function attachDocument(file, { basePath = null } = {}) {
    const name = file.name || ('file_' + Date.now());
    const bytes = new Uint8Array(await file.arrayBuffer());
    // Land in the current file-viewer folder ('' = OPFS root). No hidden
    // fallback bucket: at worst the file appears at root, visible in the sidebar.
    const dir = (basePath != null ? basePath : currentBasePath());
    const opfsPath = await uniquePath(dir, name);
    await opfs.write(opfsPath, bytes);
    opfs.notifyUpload(opfsPath);   // sidebar + run_python /files mount
    return opfsPath;
  }

  /* ---------------------------------------------------------------------------
     Walk a FileSystemEntry (file or directory) recursively.
     --------------------------------------------------------------------------- */
  async function walkFileEntry(entry, basePath) {
    if (entry.isFile) {
      return new Promise((resolve) => {
        entry.file(async (file) => {
          try {
            const looksImage = IMAGE_EXTS.has(extOf(file.name)) || HEIC_EXTS.has(extOf(file.name)) || (file.type || '').startsWith('image/');
            const opfsPath = looksImage
              ? await attachImage(file, { basePath, addComposerChip: false })
              : await attachDocument(file, { basePath });
            resolve([opfsPath]);
          } catch (err) {
            console.warn('[sandpie] walkFileEntry failed:', file.name, err);
            resolve([]);
          }
        }, () => resolve([]));
      });
    }
    if (entry.isDirectory) {
      const reader = entry.createReader();
      const dirPath = basePath ? basePath + '/' + entry.name : entry.name;
      return new Promise((resolve) => {
        const children = [];
        function readMore() {
          reader.readEntries(async (results) => {
            if (!results.length) {
              const out = [];
              for (const c of children) {
                const paths = await walkFileEntry(c, dirPath);
                out.push(...paths);
              }
              resolve(out);
              return;
            }
            children.push(...Array.from(results));
            readMore();
          }, () => resolve([]));
        }
        readMore();
      });
    }
    return [];
  }

  /* ---------------------------------------------------------------------------
     Process items from a drop event (supports files and folders).
     --------------------------------------------------------------------------- */
  async function processDroppedItems(items) {
    const basePath = currentBasePath();
    const allPaths = [];
    let topFolderName = null;

    for (const item of items) {
      const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
      if (!entry) continue;
      if (entry.isDirectory && !topFolderName) topFolderName = entry.name;
      const paths = await walkFileEntry(entry, basePath);
      allPaths.push(...paths);
    }

    if (allPaths.length && typeof injectUploadMessage === 'function') {
      const folder = basePath || '/';
      if (topFolderName && allPaths.length > 1) {
        injectUploadMessage(`User added folder "${topFolderName}/" to /${folder}/ containing ${allPaths.length} files.`);
      } else {
        const names = allPaths.map(p => p.split('/').pop()).filter(Boolean).join(', ');
        injectUploadMessage(`User uploaded ${allPaths.length} file${allPaths.length > 1 ? 's' : ''} to /${folder}/: ${names}`);
      }
    }
  }

  /**
   * Attach one or more File objects (from the file picker or simple drag).
   * Each is written to OPFS under the current file-viewer folder.
   */
  async function addFiles(fileList, which) {
    const files = Array.from(fileList || []);
    const basePath = currentBasePath();
    const pane = _pane(which);
    const paths = [];
    for (const file of files) {
      const looksImage = IMAGE_EXTS.has(extOf(file.name)) || HEIC_EXTS.has(extOf(file.name)) || (file.type || '').startsWith('image/');
      try {
        const opfsPath = looksImage
          ? await attachImage(file, { basePath, addComposerChip: true, pane })
          : await attachDocument(file, { basePath });
        paths.push(opfsPath);
      } catch (err) {
        console.error('[sandpie] attach failed:', err);
        alert('Could not attach "' + (file.name || 'file') + '": ' + ((err && err.message) || err));
      }
    }
    renderPreviews(pane);

    if (paths.length && typeof injectUploadMessage === 'function') {
      const folder = basePath || '/';
      const names = paths.map(p => p.split('/').pop()).filter(Boolean).join(', ');
      injectUploadMessage(`User uploaded ${paths.length} file${paths.length > 1 ? 's' : ''} to /${folder}/: ${names}`);
    }
  }

  /**
   * <input type=file> change handler — accepts multiple.
   * @param {Event} e
   */
  async function handleSelect(e) {
    const files = e.target.files;
    // The <input type=file> lives inside its own composer, so the pane the user
    // clicked + in is right here on the event target — no guessing.
    const which = _paneOfEl(e.target) || (e.target.id === 'imageInputSide' ? 'side' : 'main');
    if (files && files.length) await addFiles(files, which);
    e.target.value = '';   // let the same file be picked again after removal
  }

  // ============================================================
  // WINDOW-WIDE DRAG & DROP
  // ============================================================

  // The whole window is a drop target: dropping file(s) anywhere attaches them
  // (same as the button). Only FILE drags are intercepted — text/element drags
  // (e.g. dragging a conversation in the sidebar) pass through untouched.
  function initWindowDrop() {
    if (document.getElementById('dropOverlay')) return;
    const overlay = document.createElement('div');
    overlay.id = 'dropOverlay';
    overlay.className = 'drop-overlay';
    overlay.innerHTML = '<div class="drop-overlay-inner"><span class="dz-icon">⬇</span><span>Drop files to attach</span></div>';
    document.body.appendChild(overlay);

    let depth = 0;   // dragenter/leave nest as the cursor crosses child elements
    const isFileDrag = e => Array.from((e.dataTransfer && e.dataTransfer.types) || []).includes('Files');

    window.addEventListener('dragenter', (e) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      depth++;
      overlay.classList.add('active');
    });
    window.addEventListener('dragover', (e) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      try { e.dataTransfer.dropEffect = 'copy'; } catch (_) {}
    });
    window.addEventListener('dragleave', (e) => {
      if (!isFileDrag(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) overlay.classList.remove('active');
    });
    window.addEventListener('drop', async (e) => {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      depth = 0;
      overlay.classList.remove('active');
      const items = (e.dataTransfer && e.dataTransfer.items) ? Array.from(e.dataTransfer.items) : [];
      if (!items.length) return;
      await processDroppedItems(items);
    });
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  // All pane-scoped entry points below default to the focused pane when `which`
  // is omitted, so a legacy no-arg call touches one composer instead of both.
  function getState(which) {
    return _list(which === undefined ? _activePane() : which);
  }

  // Add an attachment that already lives in OPFS (e.g. the load_image tool
  // result), or replace/clear the whole set. Tolerates the legacy single-object
  // image shape ({ opfsPath, file, dataUrl }).
  function setState(att, which) {
    const pane = _pane(which === undefined ? _activePane() : which);
    if (att == null) { clear(pane); return; }
    if (Array.isArray(att)) { _byPane[pane] = att; renderPreviews(pane); return; }
    if (!att.kind) att.kind = 'image';
    if (att.dataUrl && !att.thumb) att.thumb = att.dataUrl;
    _list(pane).push(att);
    renderPreviews(pane);
  }

  function clear(which) {
    const pane = _pane(which === undefined ? _activePane() : which);
    _byPane[pane] = [];
    const pv = _previewEl(pane);
    if (pv) { pv.style.display = 'none'; pv.innerHTML = ''; }
    const inp = _inputEl(pane);
    if (inp) inp.value = '';
  }

  /**
   * Save image to OPFS from data URL
   * @param {string} dataUrl - Base64 data URL
   * @param {string} filename - Target filename
   * @returns {Promise<string>} OPFS path
   */
  async function saveToOpfs(dataUrl, filename) {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    const path = 'images/' + filename;
    await opfs.write(path, new Uint8Array(await blob.arrayBuffer()));
    return path;
  }

  /**
   * Load image from OPFS and compress for LLM
   * @param {string} path - OPFS path
   * @returns {Promise<string|null>} Data URL or null on error
   */
  async function dataUrlFromPath(path) {
    try {
      const bytes = await opfs.readBytes(path);
      const mime = getMimeType(path);
      const blob = new Blob([bytes], { type: mime });

      const img = await loadImageFromBlob(blob);
      return compressImageToTarget(img, LLM_IMAGE_TARGET_B64);
    } catch (e) {
      console.error('Failed to load image from OPFS:', e);
      return null;
    }
  }

  /**
   * Compress the first attached image for sending to the LLM (legacy helper;
   * the send path now resolves opfs:// image refs in buildAgentConfig).
   * @returns {Promise<string|null>}
   */
  async function compressForLLM(which) {
    const a = _list(which === undefined ? _activePane() : which).find(x => x.kind === 'image');
    if (!a) return null;
    try {
      const bytes = await opfs.readBytes(a.opfsPath);
      const mime = (a.file && a.file.type) || getMimeType(a.opfsPath);
      const blob = new Blob([bytes], { type: mime });
      const img = await loadImageFromBlob(blob);
      return compressImageToTarget(img, LLM_IMAGE_TARGET_B64);
    } catch (e) {
      console.error('Failed to compress image for LLM:', e);
      return null;
    }
  }

  /**
   * Build the message content for the current attachments. Images become an
   * opfs:// image_url (resolved + compressed at send time by buildAgentConfig);
   * files become a { type:'file' } reference part that buildAgentConfig expands
   * into text. Returns the plain string when nothing is attached.
   * @param {string} text - User text message
   * @returns {Promise<string|Array>}
   */
  async function buildContent(text, which) {
    const list = _list(which === undefined ? _activePane() : which);
    if (!list.length) return text;
    const parts = [];
    if (text) parts.push({ type: 'text', text });
    for (const a of list) {
      if (a.kind === 'image') {
        // Element-pick attachments carry the element's HTML (htmlCode): the
        // snapshot is ONLY for the user to see in the chip — the model gets the
        // CODE, never the image.
        if (a.htmlCode) {
          parts.push({ type: 'text', text: 'HTML code of the element the user picked (snapshot attached for the user only — do not process it as an image):\n' + a.htmlCode });
        } else {
          parts.push({ type: 'image_url', image_url: { url: 'opfs://' + a.opfsPath } });
        }
      } else {
        parts.push({ type: 'file', file: { path: a.opfsPath, name: a.name, mime: a.mime, size: a.size, text: !!a.isText } });
      }
    }
    return parts;
  }

  /** @returns {boolean} whether anything is attached to this pane's composer */
  function hasAttachment(which) {
    return _list(which === undefined ? _activePane() : which).length > 0;
  }

  /** Legacy alias — true when any attachment is present on that composer. */
  function hasImage(which) {
    return hasAttachment(which);
  }

  /**
   * Initialize attachment handling — binds the file input + attach button and
   * the window-wide drop zone.
   */
  function initPaste() {
    window.addEventListener('paste', async (e) => {
      // Only intercept file pastes (screenshots, images copied from file explorer, etc.)
      // Text paste goes to the composer textarea as normal.
      const hasFiles = e.clipboardData && Array.from(e.clipboardData.types || []).includes('Files');
      if (!hasFiles) return;

      e.preventDefault();
      const files = e.clipboardData.files ? Array.from(e.clipboardData.files) : [];
      // Paste is window-level: prefer the composer the caret is in, else the pane
      // the user is focused on.
      const which = _paneOfEl(document.activeElement) || _activePane();
      if (files.length) await addFiles(files, which);
    });
  }

  function init() {
    document.querySelectorAll('input[type=file].attach-input').forEach(imageInput => {
      imageInput.onchange = handleSelect;
    });
    document.querySelectorAll('.attach-btn').forEach(attachBtn => {
      attachBtn.onclick = () => {
        const form = attachBtn.closest('form');
        const input = form ? form.querySelector('input[type=file].attach-input') : null;
        if (input) input.click();
      };
    });

    initWindowDrop();
    initPaste();
  }

  // Export public API
  return {
    getState,
    setState,
    handleSelect,
    addFiles,
    processDroppedItems,
    removeAt,
    clear,
    saveToOpfs,
    dataUrlFromPath,
    compressForLLM,
    buildContent,
    hasImage,
    hasAttachment,
    iconFor,
    init,
  };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', SandpieImages.init);
} else {
  SandpieImages.init();
}
