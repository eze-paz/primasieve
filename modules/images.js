// sandpie/images.js - Attachment handling module
// Despite the name (kept for its established public API), this owns the
// composer's single attachment slot for ANY file type:
//   • images (png/jpg/gif/webp/bmp/avif/svg, and HEIC/HEIF after conversion)
//     keep the thumbnail path and are sent to the model as a vision image_url;
//   • every other file is saved to OPFS and referenced — small text files are
//     inlined at send time, everything else is handed to the model as a path it
//     can open with the run_python tool (the SW mounts OPFS at /files).
// Conversion + send-time resolution live in conversations.js (buildAgentConfig);
// this module handles selection, OPFS storage, and the composer preview.

const SandpieImages = (function() {
  'use strict';

  const $ = id => document.getElementById(id);

  // ============================================================
  // PRIVATE STATE
  // ============================================================

  // The single attached item, or null. Shape:
  //   { kind:'image', opfsPath, name, mime, size, file:{name,type} }
  //   { kind:'file',  opfsPath, name, mime, size, isText, file:{name,type} }
  let _attached = null;

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
    ctx.drawImage(img, 0, 0, w, h);
    return canvas.toDataURL('image/jpeg', quality);
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

  // Pick a non-colliding OPFS path under dir/ so attaching never clobbers an
  // existing file with the same name.
  async function uniquePath(dir, name) {
    const safe = String(name).replace(/[\\/:*?"<>|]/g, '_') || 'file';
    let p = dir + '/' + safe;
    if (!(await opfs.exists(p))) return p;
    const dot = safe.lastIndexOf('.');
    const base = dot > 0 ? safe.slice(0, dot) : safe;
    const ext = dot > 0 ? safe.slice(dot) : '';
    for (let i = 2; i < 1000; i++) {
      p = `${dir}/${base}-${i}${ext}`;
      if (!(await opfs.exists(p))) return p;
    }
    return `${dir}/${base}-${Date.now()}${ext}`;
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
  // COMPOSER PREVIEW
  // ============================================================

  function makeRemoveBtn() {
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'remove-btn';
    rm.title = 'Remove';
    rm.textContent = '✕';
    rm.onclick = () => clear();
    return rm;
  }

  function showImagePreview(previewUrl, name) {
    const preview = $('imagePreview');
    if (!preview) return;
    preview.innerHTML = '';
    const img = document.createElement('img');
    img.src = previewUrl;
    img.alt = '';
    const fn = document.createElement('span');
    fn.className = 'filename';
    fn.textContent = name || 'Image';
    preview.append(img, fn, makeRemoveBtn());
    preview.style.display = '';
  }

  function showFilePreview(att) {
    const preview = $('imagePreview');
    if (!preview) return;
    preview.innerHTML = '';
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
    preview.append(chip, makeRemoveBtn());
    preview.style.display = '';
  }

  // ============================================================
  // ATTACH PATHS
  // ============================================================

  async function attachImage(file) {
    let blob = file;
    let name = file.name || ('image_' + Date.now() + '.jpg');
    if (HEIC_EXTS.has(extOf(name)) || /heic|heif/i.test(file.type || '')) {
      const convert = await loadHeic2any();
      const out = await convert({ blob: file, toType: 'image/jpeg', quality: 0.9 });
      blob = Array.isArray(out) ? out[0] : out;
      name = name.replace(/\.(heic|heif)$/i, '') + '.jpg';
    }
    const bytes = new Uint8Array(await blob.arrayBuffer());
    // Validate it actually decodes (and produce the thumbnail). Throws for
    // formats the browser can't render → handleSelect falls back to a file attach.
    const img = await loadImageFromBlob(new Blob([bytes], { type: blob.type || getMimeType(name) }));
    const previewUrl = compressImage(img, 200, 0.7);

    const opfsPath = await uniquePath('images', name);
    await opfs.write(opfsPath, bytes);
    _attached = {
      kind: 'image', opfsPath, name,
      mime: blob.type || getMimeType(opfsPath), size: bytes.length,
      file: { name, type: blob.type || getMimeType(opfsPath) },
    };
    showImagePreview(previewUrl, name);
  }

  async function attachDocument(file) {
    const name = file.name || ('file_' + Date.now());
    const bytes = new Uint8Array(await file.arrayBuffer());
    const opfsPath = await uniquePath('attachments', name);
    await opfs.write(opfsPath, bytes);
    // Surface the file to the in-browser Python tool: the SW mounts OPFS at
    // /files and syncs page writes into Pyodide's view on this notification.
    try {
      if (window.Sandpie) Sandpie.events.emit('file:changed', opfsPath);
      const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (sw) sw.postMessage({ type: 'opfs-changed', paths: [opfsPath] });
    } catch (_) {}

    _attached = {
      kind: 'file', opfsPath, name,
      mime: file.type || '', size: bytes.length, isText: looksTextual(bytes),
      file: { name, type: file.type || '' },
    };
    showFilePreview(_attached);
    try { if (typeof refreshFileList === 'function') refreshFileList(); } catch (_) {}
  }

  /**
   * Handle file input selection — routes to the image or document path.
   * @param {Event} e - File input change event
   */
  async function handleSelect(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const looksImage = IMAGE_EXTS.has(extOf(file.name)) || HEIC_EXTS.has(extOf(file.name)) || (file.type || '').startsWith('image/');
    try {
      if (looksImage) {
        try {
          await attachImage(file);
        } catch (err) {
          console.warn('[sandpie] image attach failed; attaching as a generic file:', err);
          await attachDocument(file);
        }
      } else {
        await attachDocument(file);
      }
    } catch (err) {
      console.error('[sandpie] attach failed:', err);
      alert('Could not attach "' + (file.name || 'file') + '": ' + ((err && err.message) || err));
    } finally {
      e.target.value = '';   // let the same file be picked again after removal
    }
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  function getState() {
    return _attached;
  }

  function setState(att) {
    // Tolerate the legacy image-only shape ({ opfsPath, file, dataUrl }) that the
    // load_image tool-result handler still passes.
    if (att && !att.kind) att.kind = 'image';
    _attached = att;
  }

  function clear() {
    _attached = null;
    const preview = $('imagePreview');
    if (preview) { preview.style.display = 'none'; preview.innerHTML = ''; }
    const input = $('imageInput');
    if (input) input.value = '';
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
      return compressImage(img, 1024, 0.75);
    } catch (e) {
      console.error('Failed to load image from OPFS:', e);
      return null;
    }
  }

  /**
   * Compress the attached image for sending to the LLM.
   * @returns {Promise<string|null>} Data URL, or null if the attachment isn't an image
   */
  async function compressForLLM() {
    if (!_attached || _attached.kind !== 'image') return null;
    try {
      const bytes = await opfs.readBytes(_attached.opfsPath);
      const mime = (_attached.file && _attached.file.type) || getMimeType(_attached.opfsPath);
      const blob = new Blob([bytes], { type: mime });
      const img = await loadImageFromBlob(blob);
      return compressImage(img, 1024, 0.75);
    } catch (e) {
      console.error('Failed to compress image for LLM:', e);
      return null;
    }
  }

  /**
   * Build the message content for the current attachment.
   * Images become an opfs:// image_url (resolved + compressed at send time by
   * buildAgentConfig); files become a { type:'file' } reference part that
   * buildAgentConfig expands into text. Returns the plain string when nothing
   * is attached.
   * @param {string} text - User text message
   * @returns {Promise<string|Array>}
   */
  async function buildContent(text) {
    if (!_attached) return text;

    if (_attached.kind === 'file') {
      const a = _attached;
      const ref = { type: 'file', file: { path: a.opfsPath, name: a.name, mime: a.mime, size: a.size, text: !!a.isText } };
      return text ? [{ type: 'text', text }, ref] : [ref];
    }

    // image — keep a lightweight opfs:// reference in the stored message
    return [
      { type: 'text', text: text || '' },
      { type: 'image_url', image_url: { url: 'opfs://' + _attached.opfsPath } },
    ];
  }

  /** @returns {boolean} whether anything is attached */
  function hasAttachment() {
    return _attached !== null;
  }

  /** Legacy alias — true when any attachment is present. */
  function hasImage() {
    return _attached !== null;
  }

  /**
   * Initialize attachment handling — binds the file input + attach button.
   */
  function init() {
    const imageInput = $('imageInput');
    const attachBtn = $('attachBtn');

    if (imageInput) {
      imageInput.onchange = handleSelect;
    }

    if (attachBtn) {
      attachBtn.onclick = () => {
        if (imageInput) imageInput.click();
      };
    }
  }

  // Export public API
  return {
    getState,
    setState,
    handleSelect,
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
