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
  'pdf', 'csv', 'txt', 'json', 'pptx'
]);

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
    openLink.href = 'opfs/' + clean;
    openLink.target = '_blank';
    openLink.title = 'Open in new tab';
    openLink.textContent = '↗';
    openLink.className = 'artifact-icon-btn';
    btns.appendChild(openLink);
  }

  const dlBtn = document.createElement('span');
  dlBtn.title = 'Download';
  dlBtn.textContent = '⬇';
  dlBtn.className = 'artifact-icon-btn';
  dlBtn.onclick = () => {
    const a = document.createElement('a');
    a.href = 'opfs/' + clean + '?download=1';
    a.download = clean.split('/').pop();
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    requestAnimationFrame(() => a.remove());
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

  // PPTX can't render in a bare iframe (it's a zip, not a browser-native format).
  // Show a placeholder with a button to open in the side panel (where the PPTX
  // viewer runs). The ⊞ button in the header also does this.
  if (ext === 'pptx') {
    const placeholder = document.createElement('div');
    placeholder.style.cssText = 'padding:16px 14px;font:12px monospace;color:var(--sp-text-dim);text-align:center;';
    const btn = document.createElement('button');
    btn.textContent = '▶ View presentation';
    btn.style.cssText = 'margin-top:6px;padding:4px 12px;font:12px monospace;background:var(--sp-accent);color:#fff;border:none;border-radius:3px;cursor:pointer;';
    btn.onclick = () => openArtifactPanel(clean);
    placeholder.innerHTML = '📊 PowerPoint presentation<br>';
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
  frame.src = 'opfs/' + clean;
  frame.addEventListener('load', () => {
    fetch('opfs/' + clean, { method: 'HEAD' }).then(r => {
      if (!r.ok) showArtifactError(wrap, frame, '404 — file not found: ' + clean);
    }).catch(() => {});
  });
  wrap.appendChild(frame);
  target.appendChild(wrap);
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
      fetch('opfs/' + path, { method: 'HEAD' }).then(r => {
        const len = r.headers.get('content-length');
        const size = len ? ' · ' + formatArtifactBytes(parseInt(len, 10)) : '';
        if (info) info.textContent = path.split('/').pop() + size + age;
      }).catch(() => {
        if (info) info.textContent = path.split('/').pop() + age;
      });
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

/* -------------------------------------------------------------------------- */
/*  SandpieMenu registration                                                  */
/* -------------------------------------------------------------------------- */

function initMenu() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Artifacts module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(initMenu, 500);
    return;
  }

  SandpieMenu.add('artifactsSection', {
    title: 'Artifacts',
    badge: '0',
    open: false,
    html: '<p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0;">WIP</p>',
    onRender(bodyEl) {
      console.log('Artifacts section rendered');
    }
  });

  console.log('Artifacts module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMenu);
} else {
  initMenu();
}

window.SandpieArtifacts = {
  setCount(n) {
    SandpieMenu.updateBadge('artifactsSection', String(n));
  },
  increment() {
    const el = SandpieMenu.get('artifactsSection');
    if (!el) return;
    const badge = el.querySelector('summary span');
    const current = parseInt(badge?.textContent || '0', 10);
    SandpieMenu.updateBadge('artifactsSection', String(current + 1));
  }
};
