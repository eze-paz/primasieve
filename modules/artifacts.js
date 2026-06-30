/**
 * Artifacts Module for Sandpie
 *
 * Handles rendering, collapsing, expanding, and managing artifact previews
 * in conversation streams. Provides both a SandpieMenu section and the
 * global artifact rendering API.
 *
 * Usage:
 *   - Module auto-registers with SandpieMenu
 *   - Global functions: renderArtifact, collapseArtifact, expandArtifact, etc.
 *   - Called from stream renderer when tool returns 'artifact:<path>'
 */

/* -------------------------------------------------------------------------- */
/*  Artifact iframe resize handler (from embedded artifacts via postMessage)   */
/* -------------------------------------------------------------------------- */

window.addEventListener('message', e => {
  if (!e.data || e.data.type !== 'sandpie-artifact-resize') return;
  for (const f of document.querySelectorAll('iframe.artifact-frame')) {
    if (f.contentWindow === e.source) {
      const maxH = window.innerHeight * 0.5;
      f.style.height = Math.min(Math.max(60, e.data.h | 0), maxH) + 'px';
      f.style.overflow = 'auto';
      const wrap = f.closest('.artifact-wrap');
      if (wrap) { wrap.style.border = '1px solid var(--sp-border)'; wrap.style.background = 'transparent'; }
      return;
    }
  }
});

/* -------------------------------------------------------------------------- */
/*  Global helpers (expected to exist in host page)                           */
/* -------------------------------------------------------------------------- */

function _$(id) { return document.getElementById(id); }

function _activeStream() {
  // Try to get from global scope (host page defines these)
  if (typeof activeStream === 'function') return activeStream();
  if (typeof activeConvId !== 'undefined' && typeof convStreams !== 'undefined') {
    return activeConvId ? (convStreams.get(activeConvId) || null) : null;
  }
  return null;
}

/* -------------------------------------------------------------------------- */
/*  Artifact rendering                                                        */
/* -------------------------------------------------------------------------- */

const RENDERABLE_EXTS = new Set([
  'html', 'htm', 'svg', 'png', 'jpg', 'jpeg', 'gif', 'webp',
  'pdf', 'csv', 'txt', 'json', 'pptx', 'docx', 'xlsx', 'xls', 'ods'
]);

// Office formats that are OOXML/ODF zips, not browser-native — they can't render
// in a bare iframe, so they show a placeholder that opens the side-panel viewer
// (opfs.openFile), where the lazy-loaded docx-preview / SheetJS / pptx-viewer run.
const PANEL_ONLY_EXTS = new Set(['pptx', 'docx', 'xlsx', 'xls', 'ods']);
const PANEL_ONLY_LABELS = {
  pptx: '📊 PowerPoint presentation', docx: '📘 Word document',
  xlsx: '📊 Excel spreadsheet', xls: '📊 Excel spreadsheet', ods: '📊 Spreadsheet',
};

function renderArtifact(host, path) {
  const target = host || (_activeStream() && _activeStream().host) || _$('messages');
  const clean = path ? String(path).replace(/^\/+/, '') : '';

  const wrap = document.createElement('div');
  wrap.className = 'artifact-wrap';
  wrap.style.cssText = 'position:relative;margin-top:0.5rem;min-width:200px;min-height:60px;border:1px solid var(--sp-border);border-radius:4px;overflow:hidden;max-width:100%;';

  const header = document.createElement('div');
  header.className = 'artifact-header';
  header.style.cssText = 'padding:2px 8px;font:11px monospace;color:var(--sp-text-dim);background:var(--sp-panel);border-bottom:1px solid var(--sp-border);display:flex;align-items:center;justify-content:space-between;';

  const label = document.createElement('span');
  label.textContent = '📎 Artifact' + (clean ? ' — ' + clean.split('/').pop() : '');
  header.appendChild(label);

  if (!target) {
    console.error('[artifact] renderArtifact: no target for path', path);
    return;
  }

  if (!clean) {
    const errEl = document.createElement('div');
    errEl.style.cssText = 'padding:10px 12px;font:12px monospace;color:#f85149;';
    errEl.textContent = '⚠ Artifact error: no file path provided.';
    wrap.appendChild(header);
    wrap.appendChild(errEl);
    target.appendChild(wrap);
    return;
  }

  const ext = clean.split('.').pop().toLowerCase();
  const renderable = RENDERABLE_EXTS.has(ext);

  wrap.dataset.artifactPath = clean;
  wrap.dataset.artifactCreated = String(Date.now());

  const btns = document.createElement('span');
  btns.style.cssText = 'display:flex;gap:5px;align-items:center;';

  if (renderable) {
    const panelBtn = document.createElement('button');
    panelBtn.className = 'artifact-icon-btn artifact-panel-btn';
    panelBtn.title = 'Open in side panel';
    panelBtn.textContent = '⊞';
    panelBtn.onclick = () => { collapseArtifact(wrap); openArtifactPanel(clean); };
    btns.appendChild(panelBtn);

    const openLink = document.createElement('a');
    openLink.href = '#';
    openLink.target = '_blank';
    openLink.title = 'Open in new tab';
    openLink.textContent = '↗';
    openLink.className = 'artifact-icon-btn';
    openLink.onclick = async (e) => {
      e.preventDefault();
      try {
        const url = await opfs.toUrl(clean);
        const win = window.open(url, '_blank');
        // Revoke after a minute — enough for the new tab to finish loading.
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (err) { console.error('[artifact] open in tab failed:', err); }
    };
    btns.appendChild(openLink);
  }

  const dlBtn = document.createElement('span');
  dlBtn.title = 'Download';
  dlBtn.textContent = '⬇';
  dlBtn.className = 'artifact-icon-btn';
  dlBtn.onclick = async () => {
    try {
      const bytes = await opfs.readBytes(clean);
      const ext2 = clean.split('.').pop().toLowerCase();
      const mime = ({html:'text/html',htm:'text/html',svg:'image/svg+xml',png:'image/png',
        jpg:'image/jpeg',jpeg:'image/jpeg',gif:'image/gif',webp:'image/webp',
        csv:'text/csv',json:'application/json',txt:'text/plain'})[ext2] || 'application/octet-stream';
      const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
      const a = document.createElement('a');
      a.href = url; a.download = clean.split('/').pop(); a.style.display = 'none';
      document.body.appendChild(a); a.click();
      requestAnimationFrame(() => { a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
    } catch (e) { console.error('[artifact] download failed:', e); }
  };
  btns.appendChild(dlBtn);

  if (renderable) {
    const collapseBtn = document.createElement('button');
    collapseBtn.className = 'artifact-icon-btn artifact-collapse-btn';
    collapseBtn.title = 'Collapse';
    collapseBtn.textContent = '−';
    collapseBtn.onclick = () => toggleArtifactCollapse(wrap);
    btns.appendChild(collapseBtn);
  }

  header.appendChild(btns);
  wrap.appendChild(header);

  if (!renderable) {
    const dlRow = document.createElement('div');
    dlRow.style.cssText = 'padding:12px 14px;font:12px monospace;color:var(--sp-text-dim);';
    dlRow.textContent = ext.toUpperCase() + ' file — not previewable in browser. Use ⬇ to download.';
    wrap.appendChild(dlRow);
    target.appendChild(wrap);
    return;
  }

  // Office zips (pptx/docx/xlsx/…) can't render in a bare iframe. Show a
  // placeholder with a button to open in the side panel (where the lazy-loaded
  // viewer runs). The ⊞ button in the header also does this.
  if (PANEL_ONLY_EXTS.has(ext)) {
    const placeholder = document.createElement('div');
    placeholder.style.cssText = 'padding:16px 14px;font:12px monospace;color:var(--sp-text-dim);text-align:center;';
    const btn = document.createElement('button');
    btn.textContent = '▶ View';
    btn.style.cssText = 'margin-top:6px;padding:4px 12px;font:12px monospace;background:var(--sp-accent);color:#fff;border:none;border-radius:3px;cursor:pointer;';
    btn.onclick = () => openArtifactPanel(clean);
    placeholder.innerHTML = (PANEL_ONLY_LABELS[ext] || '📄 Document') + '<br>';
    placeholder.appendChild(btn);
    wrap.appendChild(placeholder);
    target.appendChild(wrap);
    return;
  }

  const metaRow = document.createElement('div');
  metaRow.className = 'artifact-meta-row';
  metaRow.style.display = 'none';

  const showBtn = document.createElement('button');
  showBtn.className = 'artifact-show-btn';
  showBtn.textContent = '▼ Show artifact';
  showBtn.onclick = () => toggleArtifactCollapse(wrap);

  const metaInfo = document.createElement('span');
  metaInfo.className = 'artifact-meta-info';
  metaInfo.textContent = clean.split('/').pop();

  metaRow.appendChild(showBtn);
  metaRow.appendChild(metaInfo);
  wrap.appendChild(metaRow);

  const frame = document.createElement('iframe');
  frame.className = 'artifact-frame';
  frame.style.cssText = 'width:100%;min-height:60px;border:0;background:transparent;display:block;';
  wrap.appendChild(frame);
  target.appendChild(wrap);
  // Load async: read from OPFS, create blob URL, revoke old one on refresh.
  (async () => {
    try {
      const url = await opfs.toUrl(clean);
      if (frame._blobUrl) URL.revokeObjectURL(frame._blobUrl);
      frame._blobUrl = url;
      frame.src = url;
    } catch (e) {
      showArtifactError(wrap, frame, 'failed to load: ' + clean + ' — ' + (e && e.message || e));
    }
  })();
}

/* -------------------------------------------------------------------------- */
/*  Formatting helpers                                                        */
/* -------------------------------------------------------------------------- */

function formatArtifactBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatArtifactAge(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 10) return 'just now';
  if (s < 60) return s + 's ago';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  return Math.floor(s / 3600) + 'h ago';
}

/* -------------------------------------------------------------------------- */
/*  Collapse / expand                                                         */
/* -------------------------------------------------------------------------- */

function collapseArtifact(wrap) {
  if (!wrap || wrap.dataset.artifactCollapsed === '1') return;
  wrap.dataset.artifactCollapsed = '1';

  const frame = wrap.querySelector('.artifact-frame');
  const metaRow = wrap.querySelector('.artifact-meta-row');
  const colBtn = wrap.querySelector('.artifact-collapse-btn');

  if (frame) frame.style.display = 'none';
  if (colBtn) { colBtn.textContent = '+'; colBtn.title = 'Expand'; }
  if (metaRow) {
    metaRow.style.display = 'flex';

    const path = wrap.dataset.artifactPath;
    const ts = parseInt(wrap.dataset.artifactCreated || '0', 10);
    const info = metaRow.querySelector('.artifact-meta-info');
    if (info) {
      const age = ts ? ' · ' + formatArtifactAge(ts) : '';
      (async () => {
        try {
          const { parts, name } = splitPath(path);
          const dir = await opfs.resolveDir(parts);
          const file = await (await dir.getFileHandle(name)).getFile();
          const size = file.size > 0 ? ' · ' + formatArtifactBytes(file.size) : '';
          if (info) info.textContent = path.split('/').pop() + size + age;
        } catch {
          if (info) info.textContent = path.split('/').pop() + age;
        }
      })();
    }
  }
}

function expandArtifact(wrap) {
  if (!wrap || wrap.dataset.artifactCollapsed !== '1') return;
  delete wrap.dataset.artifactCollapsed;

  const frame = wrap.querySelector('.artifact-frame');
  const metaRow = wrap.querySelector('.artifact-meta-row');
  const colBtn = wrap.querySelector('.artifact-collapse-btn');

  if (frame) frame.style.display = 'block';
  if (metaRow) metaRow.style.display = 'none';
  if (colBtn) { colBtn.textContent = '−'; colBtn.title = 'Collapse'; }
}

function toggleArtifactCollapse(wrap) {
  if (wrap.dataset.artifactCollapsed === '1') expandArtifact(wrap);
  else collapseArtifact(wrap);
}

/* -------------------------------------------------------------------------- */
/*  Error display                                                             */
/* -------------------------------------------------------------------------- */

function showArtifactError(wrap, frame, msg) {
  if (frame) frame.style.display = 'none';
  const errEl = document.createElement('div');
  errEl.style.cssText = 'padding:10px 12px;font:12px monospace;color:#f85149;';
  errEl.textContent = '⚠ Artifact error: ' + msg;
  wrap.appendChild(errEl);
  wrap.style.borderColor = '#f85149';
}

/* -------------------------------------------------------------------------- */
/*  Side panel                                                                */
/* -------------------------------------------------------------------------- */

// Both the file browser and artifacts route through the one viewer (opfs.openFile):
// prefer:'side' opens beside the chat on desktop, and falls back to the modal on
// mobile (where the side panel is blocked). The viewer renders html/svg live in an
// iframe, so artifacts look the same as the old dedicated panel.
function openArtifactPanel(path) {
  const clean = String(path).replace(/^\/+/, '');
  if (typeof sidePanel !== 'undefined' && sidePanel?.isOpen) sidePanel.close();
  if (typeof opfs !== 'undefined' && opfs.openFile) {
    opfs.openFile(clean, clean.split('/').pop(), { prefer: 'side' });
  }
}

function closeArtifactPanel() {
  if (typeof opfs !== 'undefined' && opfs.closeFile) opfs.closeFile();
}

/* -------------------------------------------------------------------------- */
/*  Expose globals (expected by sandpie.html inline scripts)                  */
/* -------------------------------------------------------------------------- */

window.renderArtifact = renderArtifact;
window.formatArtifactBytes = formatArtifactBytes;
window.formatArtifactAge = formatArtifactAge;
window.collapseArtifact = collapseArtifact;
window.expandArtifact = expandArtifact;
window.toggleArtifactCollapse = toggleArtifactCollapse;
window.showArtifactError = showArtifactError;
window.openArtifactPanel = openArtifactPanel;
window.closeArtifactPanel = closeArtifactPanel;
