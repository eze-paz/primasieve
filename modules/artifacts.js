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

// Pane → the element content goes into (.conv-host when a conv is mounted), and a
// composer-safe append. Both come from conversations.js; a bare appendChild on a
// pane lands BELOW its sticky composer. Local fallbacks keep this module standalone.
function _paneScrollEl(pane) {
  if (typeof window.paneScrollEl === 'function') return window.paneScrollEl(pane);
  if (!pane) return null;
  return pane.querySelector(':scope > .conv-host') || pane;
}
function _append(target, el) {
  if (typeof window.appendContent === 'function') return window.appendContent(target, el);
  if (!target || !el) return el;
  const anchor = target.querySelector(':scope > .cmd-output') || target.querySelector(':scope > .composer');
  if (anchor) target.insertBefore(el, anchor); else target.appendChild(el);
  return el;
}

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

// V2 "preview thumbnail" artifact card — the body for panel-only office files and
// the collapsed representation of every artifact type: a faux-page preview banner
// on top, a footer with a type-tinted icon, a human label, and the file size.
const _ARTIFACT_KIND = {
  docx: 'doc', doc: 'doc', odt: 'doc', rtf: 'doc', txt: 'doc',
  pdf: 'pdf', xlsx: 'xls', xls: 'xls', ods: 'xls', csv: 'xls',
  pptx: 'ppt', ppt: 'ppt', odp: 'ppt',
  html: 'code', htm: 'code', svg: 'code', json: 'code',
  png: 'img', jpg: 'img', jpeg: 'img', gif: 'img', webp: 'img',
};
const _ARTIFACT_LABEL = {
  docx: 'Word document', doc: 'Word document', odt: 'Text document', rtf: 'Rich text', txt: 'Text file',
  pdf: 'PDF document', xlsx: 'Excel spreadsheet', xls: 'Excel spreadsheet', ods: 'Spreadsheet', csv: 'CSV data',
  pptx: 'PowerPoint', ppt: 'PowerPoint', odp: 'Presentation',
  html: 'Web page', htm: 'Web page', svg: 'SVG image', json: 'JSON', png: 'Image', jpg: 'Image', jpeg: 'Image', gif: 'Image', webp: 'Image',
};
const _ARTIFACT_ICON = {
  doc: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><line x1="9" y1="9" x2="10" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/>',
  xls: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 13l6 5M15 13l-6 5"/>',
  ppt: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><rect x="9" y="12" width="6" height="4" rx="1"/>',
  pdf: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 17v-4h1.5a1.5 1.5 0 0 1 0 3H9"/>',
  code: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M10 12l-2 2 2 2M14 12l2 2-2 2"/>',
  img: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>',
  generic: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/>',
};
// Legacy-path fallback: user files moved from /files/<dir>/ to /files/sandpie/<dir>/.
// Resolve a stored artifact path to whichever variant actually exists in OPFS, so
// old conversations replaying "artifact:artifacts/x.html" still find the file. If
// the file exists nowhere (e.g. dehydrated), fall back to trying the sandpie/-
// prefixed variant anyway when the original is a bare legacy path.
async function resolveArtifactPath(clean) {
  const candidates = [clean];
  if (!clean.startsWith('sandpie/')) candidates.push('sandpie/' + clean);
  else candidates.push(clean.slice('sandpie/'.length));
  for (const p of candidates) {
    try {
      const { parts, name } = splitPath(p);
      const dir = await opfs.resolveDir(parts);
      await dir.getFileHandle(name);
      return p;
    } catch (_) {}
  }
  return candidates[0].startsWith('sandpie/') ? candidates[0] : candidates[1] || candidates[0];
}

function buildArtifactCard(clean, ext, onOpen) {
  const kind = _ARTIFACT_KIND[ext] || 'generic';
  const label = _ARTIFACT_LABEL[ext] || (ext ? ext.toUpperCase() : 'File');
  const el = document.createElement('div');
  el.className = 'artifact-card-body';
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.title = 'Open ' + clean.split('/').pop();
  el.innerHTML =
    '<div class="ac-thumb"><div class="ac-page"><i class="t"></i><i class="m"></i><i class="s"></i><i class="m"></i><i class="s"></i></div></div>' +
    '<div class="ac-ft"><div class="ac-ic ac-t-' + kind + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + _ARTIFACT_ICON[kind] + '</svg></div>' +
    '<span class="ac-sub"></span><span class="ac-go">›</span></div>';
  el.querySelector('.ac-sub').textContent = label;
  const open = (e) => { if (e) e.preventDefault(); onOpen(); };
  el.onclick = open;
  el.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') open(e); };
  (async () => {
    try {
      const { parts, name } = splitPath(await resolveArtifactPath(clean));
      const dir = await opfs.resolveDir(parts);
      const file = await (await dir.getFileHandle(name)).getFile();
      const sub = el.querySelector('.ac-sub');
      if (sub && file.size > 0) sub.textContent = label + ' · ' + formatArtifactBytes(file.size);
    } catch (_) {}
  })();
  return el;
}

function renderArtifact(host, path) {
  const target = host || (_activeStream() && _activeStream().host) || _paneScrollEl(_$('messages'));
  const clean = path ? String(path).replace(/^\/+/, '') : '';
  // Resolve once (legacy artifacts/ → sandpie/artifacts/ remap); handlers await it.
  const resolvedP = clean ? resolveArtifactPath(clean) : Promise.resolve(clean);

  const wrap = document.createElement('div');
  wrap.className = 'artifact-wrap';
  wrap.style.cssText = 'position:relative;margin-top:0.5rem;min-width:200px;min-height:250px;border:1px solid var(--sp-border);border-radius:4px;overflow:hidden;max-width:100%;';

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
    _append(target, wrap);
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
    panelBtn.onclick = async () => { collapseArtifact(wrap); openArtifactPanel(await resolvedP); };
    btns.appendChild(panelBtn);

    const openLink = document.createElement('a');
    openLink.href = '#';
    openLink.target = '_blank';
    openLink.title = 'Open in new tab';
    openLink.textContent = '↗';
    openLink.className = 'artifact-icon-btn';
    // Point the anchor at the file's real /files/ URL (served out of OPFS by
    // sw.js) as soon as the path resolves: a genuine href means the browser
    // handles the click — middle-click, ctrl-click and "Copy link address" all
    // work, and the new tab shows a readable URL instead of blob:…
    Promise.resolve(resolvedP).then(rp => { if (rp) openLink.href = opfs.filesUrl(rp); });
    openLink.onclick = async (e) => {
      if (opfs.filesUrlReady() && openLink.href && !openLink.href.endsWith('#')) return;   // let the real link through
      e.preventDefault();
      try {
        const url = await opfs.toUrl(await resolvedP);
        window.open(url, '_blank');
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
      const p = await resolvedP;
      const bytes = await opfs.readBytes(p);
      const ext2 = p.split('.').pop().toLowerCase();
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

  const pinBtn = document.createElement('button');
  pinBtn.className = 'artifact-icon-btn artifact-pin-btn';
  pinBtn.textContent = '📌';
  pinBtn.title = 'Pin file';
  // Pin the RESOLVED path (legacy artifacts/ → sandpie/artifacts/), so the
  // home-screen shortcut opens the file that actually exists on disk.
  Promise.resolve(resolvedP).then(rp => { if (window.SandpiePins) SandpiePins.bindButton(pinBtn, rp || clean); });
  btns.appendChild(pinBtn);

  const shareBtn = document.createElement('button');
  shareBtn.className = 'artifact-icon-btn artifact-share-btn';
  shareBtn.textContent = '🔗';
  shareBtn.title = 'Share';
  shareBtn.onclick = async () => { if (window.SandpieSharing) SandpieSharing.shareDialog((await resolvedP) || clean, 'artifact'); };
  btns.appendChild(shareBtn);

  header.appendChild(btns);
  wrap.appendChild(header);

  // File type never blocks showing an artifact: types we can't preview inline
  // still get the same clickable V2 card, which opens the file in a new tab (the
  // browser renders it if it can, otherwise downloads) — a link is always useful.
  if (!renderable) {
    const cb = wrap.querySelector('.artifact-collapse-btn');
    if (cb) cb.remove();
    wrap.appendChild(buildArtifactCard(clean, ext, async () => {
      try { await opfs.openInNewTab(await resolvedP); }
      catch (e) { console.error('[artifact] open failed:', e); }
    }));
    _append(target, wrap);
    return;
  }

  // Office zips (pptx/docx/xlsx/…) can't render in a bare iframe — the V2 card is
  // their whole body; clicking it opens the side-panel viewer. No inline body to
  // collapse, so drop the collapse toggle (the ⊞ header button also opens it).
  if (PANEL_ONLY_EXTS.has(ext)) {
    const cb = wrap.querySelector('.artifact-collapse-btn');
    if (cb) cb.remove();
    wrap.appendChild(buildArtifactCard(clean, ext, async () => openArtifactPanel(await resolvedP)));
    _append(target, wrap);
    return;
  }

  // Collapsed representation: the same V2 card (click to expand the inline view).
  const metaRow = document.createElement('div');
  metaRow.className = 'artifact-meta-row';
  metaRow.style.display = 'none';
  metaRow.appendChild(buildArtifactCard(clean, ext, () => toggleArtifactCollapse(wrap)));
  wrap.appendChild(metaRow);

  const frame = document.createElement('iframe');
  frame.className = 'artifact-frame';
  frame.style.cssText = 'width:100%;min-height:250px;border:0;background:transparent;display:block;';
  wrap.appendChild(frame);
  _append(target, wrap);
  // METACOG: if the NEWEST HTML artifact logs to the console, tell the worker
  // so it can inject a metacog note for the model (newest artifact only — a
  // superseded check is skipped by the seq guard).
  armConsoleNoteCheck(wrap, frame, clean);
  loadArtifactFrame(wrap, frame, resolvedP, clean);
}

// (Re)load an artifact's iframe from a fresh OPFS blob URL. Used both for the
// initial render and for auto-reload when a tool call rewrites the file (a blob
// URL is a snapshot of the bytes at creation — a new one is required for refresh).
async function loadArtifactFrame(wrap, frame, resolvedP, clean) {
  let p = null;
  try {
    p = await resolvedP;
    wrap.dataset.artifactPath = p;
    const url = await opfs.toUrl(p);
    if (frame._blobUrl) URL.revokeObjectURL(frame._blobUrl);
    frame._blobUrl = url;
    frame.src = url;
  } catch (e) {
    showArtifactError(wrap, frame, 'failed to load: ' + (clean || p || '') + ' — ' + (e && e.message || e));
  }
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
    metaRow.style.display = 'block';

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

// html_console tool (worker -> page): read the console buffer of an HTML
// artifact shown in the conversation. The buffer is captured by the bootstrap
// injected in opfs.toUrl (window.__sandpieConsole on the frame's contentWindow).
// Returns { entries: [...] } or { error: '...' }.
// ---- metacog: newest-artifact console note -------------------------------
// After the newest HTML artifact renders, wait for its load + a short settle
// window (async console output like setTimeout / load handlers), read the
// captured buffer, and if non-empty post an artifact-console-note to the
// worker. Only the newest artifact triggers: a seq guard skips superseded
// checks when several artifacts render in a row.
let _consoleNoteSeq = 0;
function armConsoleNoteCheck(wrap, frame, clean) {
  const ext = (String(clean || '').split('.').pop() || '').toLowerCase();
  if (ext !== 'html' && ext !== 'htm') return;              // only HTML has the bootstrap
  const seq = ++_consoleNoteSeq;
  wrap.dataset.consoleNoteSeq = String(seq);
  let done = false;
  const check = () => {
    if (done) return; done = true;
    if (String(wrap.dataset.consoleNoteSeq) !== String(seq)) return;   // superseded
    try {
      const w = frame.contentWindow;
      if (!w || !w.__sandpieConsole || !w.__sandpieConsole.length) return;
      let conv = ''; try { conv = localStorage.getItem('sandpie-active-conv') || ''; } catch (_) {}
      if (window._sandpieWorker && window._sandpieWorker.postMessage) {
        window._sandpieWorker.postMessage({ type: 'artifact-console-note', conversation_file_name: conv, path: clean, entries: w.__sandpieConsole.slice(0, 25) });
      }
    } catch (_) {}
  };
  frame.addEventListener('load', () => setTimeout(check, 800), { once: true });
  setTimeout(check, 5000);   // fallback if the frame never fires load
}

async function readArtifactConsole(path) {
  const norm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '');
  const want = norm(path);
  let found = null;
  for (const wrap of document.querySelectorAll('.artifact-wrap')) {
    const cur = wrap.dataset.artifactPath;
    if (!cur) continue;
    if (want && norm(cur) !== want) continue;
    const frame = wrap.querySelector('.artifact-frame');
    if (frame) { found = { wrap, frame }; break; }
  }
  if (!found) return { error: want ? 'No artifact frame open for "' + path + '". Show it with show_artifact first, or pass its exact path.' : 'No artifact frame open in the conversation.' };
  try {
    const w = found.frame.contentWindow;
    if (!w || !w.__sandpieConsole) return { error: 'This artifact has no console capture (loaded before instrumentation, or it is not an HTML file). Re-show it with show_artifact to instrument it.' };
    return { entries: w.__sandpieConsole.slice() };
  } catch (e) {
    return { error: 'Could not read artifact console: ' + ((e && e.message) || e) };
  }
}
window.readArtifactConsole = readArtifactConsole;

// Auto-reload: when a tool call (edit_file / write_file / run_python / …) rewrites
// an open artifact, swap in a fresh blob URL so every .artifact-frame iframe shows
// the new bytes. Paths arrive already debounced (conversations.js — max 1 reload
// per 5s per path, trailing edge). Only frames; V2 cards (panel-only / non-
// renderable) are static thumbnails and skip.
if (typeof Sandpie !== 'undefined' && Sandpie.events) {
  Sandpie.events.on('artifact:changed', (path) => {
    if (!path) return;
    const norm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '');
    const strip = (p) => p.startsWith('sandpie/') ? p.slice('sandpie/'.length) : p;
    resolveArtifactPath(norm(path)).then((resolved) => {
      const b = norm(resolved);
      for (const wrap of document.querySelectorAll('.artifact-wrap')) {
        const cur = wrap.dataset.artifactPath;
        if (!cur) continue;
        const a = norm(cur);
        if (a !== b && strip(a) !== strip(b)) continue;
        const frame = wrap.querySelector('.artifact-frame');
        if (frame) loadArtifactFrame(wrap, frame, Promise.resolve(resolved), resolved);
      }
    }).catch(() => {});
  });
}
window.formatArtifactBytes = formatArtifactBytes;
window.formatArtifactAge = formatArtifactAge;
window.collapseArtifact = collapseArtifact;
window.expandArtifact = expandArtifact;
window.toggleArtifactCollapse = toggleArtifactCollapse;
window.showArtifactError = showArtifactError;
window.openArtifactPanel = openArtifactPanel;
window.closeArtifactPanel = closeArtifactPanel;
