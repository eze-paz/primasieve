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
  'pdf', 'csv', 'txt', 'json'
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
  dlBtn.onclick = async () => {
    try {
      const resp = await fetch('opfs/' + clean);
      if (!resp.ok) throw new Error('SW returned ' + resp.status);
      const a = document.createElement('a');
      a.href = 'opfs/' + clean;
      a.target = '_blank';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      console.error('[artifact] download failed:', err);
    }
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

function openArtifactPanel(path) {
  const clean = String(path).replace(/^\/+/, '');

  if (typeof sidePanel !== 'undefined' && sidePanel?.isOpen) sidePanel.close();

  const frame = document.getElementById('artifactPanelFrame');
  const title = document.getElementById('artifactPanelTitle');
  const link = document.getElementById('artifactOpenLink');

  if (frame) frame.src = 'opfs/' + clean;
  if (title) title.textContent = clean.split('/').pop();
  if (link) link.href = 'opfs/' + clean;

  const side = document.getElementById('messagesSide');
  if (side) side.classList.add('artifact-mode');
  document.body.classList.add('artifact-side-open');
}

function closeArtifactPanel() {
  const side = document.getElementById('messagesSide');
  const frame = document.getElementById('artifactPanelFrame');
  if (side) side.classList.remove('artifact-mode');
  if (frame) frame.src = 'about:blank';
  document.body.classList.remove('artifact-side-open');
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
