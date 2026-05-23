// sandpie/images.js - Image handling module
// Extracted from sandpie.html for better organization and testability

const SandpieImages = (function() {
  'use strict';

  const $ = id => document.getElementById(id);

  // ============================================================
  // PRIVATE STATE
  // ============================================================

  let _attachedImage = null; // { opfsPath: string, file: File } or null

  // ============================================================
  // PRIVATE HELPERS
  // ============================================================

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
      webp: 'image/webp'
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
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = URL.createObjectURL(blob);
    });
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  /**
   * Get current attached image state
   * @returns {Object|null} Attached image or null
   */
  function getState() {
    return _attachedImage;
  }

  /**
   * Set attached image state
   * @param {Object|null} img - Image state or null
   */
  function setState(img) {
    _attachedImage = img;
  }

  /**
   * Handle file input selection
   * @param {Event} e - File input change event
   */
  async function handleImageSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async () => {
      // Save original to OPFS
      const filename = file.name || ('image_' + Date.now() + '.' + file.type.split('/')[1]);
      const opfsPath = 'images/' + filename;
      await opfs.write(opfsPath, new Uint8Array(await (await fetch(reader.result)).arrayBuffer()));

      // Create preview (compressed for display)
      try {
        const img = await loadImageFromBlob(new Blob([await (await fetch(reader.result)).arrayBuffer()]));
        const previewUrl = compressImage(img, 200, 0.7);

        _attachedImage = { opfsPath, file };

        const preview = $('imagePreview');
        preview.innerHTML = '<img src="' + previewUrl + '"><button type="button" onclick="SandpieImages.clear()" style="background:none;border:none;color:var(--sp-accent-neg);cursor:pointer;font-size:1rem">✕</button>';
        preview.style.display = '';
      } catch (err) {
        console.error('Failed to create image preview:', err);
      }
    };
    reader.readAsDataURL(file);
  }

  /**
   * Clear attached image
   */
  function clear() {
    _attachedImage = null;
    $('imagePreview').style.display = 'none';
    $('imagePreview').innerHTML = '';
    $('imageInput').value = '';
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
   * Compress attached image for sending to LLM
   * @returns {Promise<string|null>} Data URL or null if no image attached
   */
  async function compressForLLM() {
    if (!_attachedImage) return null;

    try {
      const bytes = await opfs.readBytes(_attachedImage.opfsPath);
      const blob = new Blob([bytes], { type: _attachedImage.file.type });
      const img = await loadImageFromBlob(blob);
      return compressImage(img, 1024, 0.75);
    } catch (e) {
      console.error('Failed to compress image for LLM:', e);
      return null;
    }
  }

  /**
   * Build multimodal content array for API
   * @param {string} text - User text message
   * @returns {Promise<string|Array>} Content (string or array with image)
   */
  async function buildContent(text) {
    if (!_attachedImage) return text;

    const dataUrl = await compressForLLM();
    if (!dataUrl) return text;

    return [
      { type: 'text', text: text || '' },
      { type: 'image_url', image_url: { url: dataUrl, detail: 'high' } }
    ];
  }

  /**
   * Check if an image is attached
   * @returns {boolean}
   */
  function hasImage() {
    return _attachedImage !== null;
  }

  /**
   * Initialize image handling module
   * Binds event listeners to DOM elements
   */
  function init() {
    const imageInput = $('imageInput');
    const attachBtn = $('attachBtn');

    if (imageInput) {
      imageInput.onchange = handleImageSelect;
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
    handleSelect: handleImageSelect,
    clear,
    saveToOpfs,
    dataUrlFromPath,
    compressForLLM,
    buildContent,
    hasImage,
    init
  };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', SandpieImages.init);
} else {
  SandpieImages.init();
}
