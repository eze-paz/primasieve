/**
 * Artifacts Module for Sandpie
 *
 * Handles rendering, collapsing, expanding, and managing artifact previews
 * in conversation streams. Provides the
 * global artifact rendering API.
 *
 * Usage:
 *   - Global functions: renderArtifact, collapseArtifact, expandArtifact, etc.
 *   - Called from stream renderer when tool returns 'artifact:<path>'
 */

/* -------------------------------------------------------------------------- */
/*  Artifact iframe resize handler (from embedded artifacts via postMessage)   */
/* -------------------------------------------------------------------------- */

window.addEventListener('message', e => {
  if (!e.data || e.data.type !== 'sandpie-artifact-resize') return;
  for (const f of document.querySelectorAll('iframe.artifact-frame')) {
    if (f.dataset.consoleOnly === '1') continue;   // hidden console frame — never resize
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

// Visual deliverables the browser renders natively in a tab. These get the tall
// preview card (faux-page thumb) AND the ↗ open-in-new-tab mini-button. Other
// renderable-but-textual types (csv/json/txt) stay slim strips → side panel.
const TAB_VIEWABLE_EXTS = new Set(['html', 'htm', 'svg', 'png', 'jpg', 'jpeg', 'gif', 'webp']);

// V2 "preview thumbnail" artifact card — the body for panel-only office files and
// the collapsed representation of every artifact type: a faux-page preview banner
// on top, a footer that is just the plain filename (name + extension).
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
  // Not found locally (e.g. dehydrated). The sandpie/ prefix guess applies ONLY to
  // the app dirs that were actually migrated under sandpie/ — an old bare path like
  // "artifacts/x.html" should hydrate from "sandpie/artifacts/x.html". For EVERY
  // other path (real workspace files like "projects/foo/x.html") return it exactly
  // as stored: blindly prepending sandpie/ corrupts the path and 404s (the file it
  // asks for does not exist). This was returning "sandpie/<anything>" for all bare
  // paths — the reported "it appends sandpie/ to everything" bug.
  const LEGACY_MOVED = /^(?:artifacts|scripts|agents|skills|memory|_conversations)\//;
  if (!clean.startsWith('sandpie/') && LEGACY_MOVED.test(clean)) return 'sandpie/' + clean;
  // Dead-prefix fallback: sandpie/artifacts/ was migrated OUT to artifacts/
  // (migrateArtifactsOut) and the boot prune deletes anything recreated there,
  // so a stored path under that prefix can never exist — resolve it to the
  // migrated location instead of returning a guaranteed 404.
  if (clean.startsWith('sandpie/artifacts/')) return clean.slice('sandpie/'.length);
  return clean;
}

// The V2 artifact card. opts:
//   onOpen    — primary action (whole-card click / Enter / Space)
//   onNewTab  — optional secondary action; renders a small ↗ button that does NOT
//               trigger onOpen (stopPropagation). This is the ONLY inline control
//               now — pin / share / download / collapse live in the side panel.
//   showThumb — include the faux-page preview banner (the tall card). Omitted for
//               the slim strip used by non-renderable files.
function buildArtifactCard(clean, ext, opts) {
  opts = opts || {};
  const el = document.createElement('div');
  el.className = 'artifact-card-body';
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.title = 'Open ' + clean.split('/').pop();
  const ntBtn = opts.onNewTab
    ? '<button class="ac-newtab" title="Open in new tab" aria-label="Open in new tab" tabindex="-1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3h7v7"/><path d="M10 14L21 3"/><path d="M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6"/></svg></button>'
    : '';
  const thumb = opts.showThumb
    ? '<div class="ac-thumb"><div class="ac-page"><i class="t"></i><i class="m"></i><i class="s"></i><i class="m"></i><i class="s"></i></div>' +
      '<img class="ac-shot" alt="" aria-hidden="true" hidden>' +
      '<span class="ac-lx" hidden></span>' + ntBtn + '</div>'
    : '';
  // Footer: PLAIN FILENAME (name + extension, e.g. "Test.html") — the icon and
  // the filetype pill text ("Web page") are REMOVED (user decision 2026-09-16).
  el.innerHTML = thumb +
    '<div class="ac-ft"><span class="ac-sub"></span>' + (opts.showThumb ? '' : ntBtn) + '</div>';
  el.querySelector('.ac-sub').textContent = clean.split('/').pop();
  const open = (e) => { if (e) e.preventDefault(); if (opts.onOpen) opts.onOpen(); };
  el.onclick = open;
  el.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') open(e); };
  const nt = el.querySelector('.ac-newtab');
  if (nt && opts.onNewTab) nt.onclick = (e) => { e.stopPropagation(); e.preventDefault(); opts.onNewTab(); };
  if (opts.showThumb) _fillArtifactThumb(el, clean, ext);
  // The subtitle IS the filename (plain name + extension) since 2026-09-16 —
  // the old kind label ("Web page") + icon are gone from the cards.
  return el;
}

// Fill a card's .ac-thumb with a real preview image, replacing the faux-page
// placeholder. Images/SVG ARE their own thumbnail (point straight at the file, no
// capture). HTML is rasterized + cached in the CONVERSATION metadata by the
// conversations.js provider (SandpieArtifactThumbs) so it travels with the conv and
// replays without re-capturing. No provider (or capture unavailable) → faux page.
function _fillArtifactThumb(el, clean, ext) {
  const img = el.querySelector('.ac-shot');
  if (!img) return;
  if (ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif' || ext === 'webp' || ext === 'svg') {
    (async () => {
      try {
        const p = await resolveArtifactPath(clean);
        const url = (opfs.filesUrlReady && opfs.filesUrlReady()) ? opfs.filesUrl(p) : await opfs.toUrl(p);
        _applyArtifactShot(img, url);
      } catch (_) {}
    })();
    return;
  }
  if (ext === 'html' || ext === 'htm') {
    if (window.SandpieArtifactThumbs && SandpieArtifactThumbs.hydrate) SandpieArtifactThumbs.hydrate(img, clean);
  }
}

// Fade a captured/loaded image into a card thumb; on error leave the faux page.
function _applyArtifactShot(img, url) {
  if (!img || !url) return;
  img.onload = () => { img.hidden = false; img.classList.add('ready'); };
  img.onerror = () => { img.hidden = true; img.classList.remove('ready'); };
  img.src = url;
}
window._applyArtifactShot = _applyArtifactShot;

function renderArtifact(host, path, opts) {
  // V3 (2026-08): artifacts NEVER render an inline iframe in the conversation.
  // Every artifact is a single clickable card; the whole card opens the SIDE
  // PANEL (the rich view — pin / share / download / open-in-new-tab all live
  // there), and a small ↗ on the card opens a new tab directly. This strips the
  // old six-icon header bar (⊞ ↗ ⬇ − 📌 🔗) that made the stream feel loaded.
  // (opts.collapsed is now a no-op — kept so old callers don't break.)
  // Parentage guard (2026-09-13): never let a card spawn in whatever conv
  // happens to be focused. Fall back to the ACTIVE stream's host only when that
  // stream is the one actually mounted in a pane; otherwise render into a
  // detached container (the card is discarded — the owning conv re-renders its
  // cards from its persisted filesTouched list when it is next mounted).
  const _as = (typeof activeStream === 'function') ? activeStream() : _activeStream();
  const _ownHost = _as && _as.host && (typeof _streamOwnsPaneSlot === 'function' ? _streamOwnsPaneSlot(_as) : _as.host.isConnected);
  const target = host || (_ownHost ? _as.host : document.createElement('div'));
  const clean = path ? String(path).replace(/^\/+/, '') : '';
  // DEBUG-TRACE (remove once the cross-conv spawn is pinned down): log every card
  // render with its landing conv + creation stack.
  try {
    const _ch2 = target && target.closest ? target.closest('.conv-host') : null;
    console.debug('[artifact-trace] renderArtifact', clean, '-> conv',
      (_ch2 && _ch2.dataset.convId) || (target.id || 'detached/other'),
      'hostParam=', !!host, new Error().stack);
  } catch (_) {}
  // Resolve once (legacy artifacts/ → sandpie/artifacts/ remap); handlers await it.
  const resolvedP = clean ? resolveArtifactPath(clean) : Promise.resolve(clean);

  const wrap = document.createElement('div');
  wrap.className = 'artifact-wrap';
  wrap.style.cssText = 'position:relative;margin-top:0.5rem;border:1px solid var(--sp-border);border-radius:8px;overflow:hidden;max-width:100%;flex:none;align-self:stretch;';

  if (!target) {
    console.error('[artifact] renderArtifact: no target for path', path);
    return;
  }

  if (!clean) {
    const errEl = document.createElement('div');
    errEl.style.cssText = 'padding:10px 12px;font:12px monospace;color:#f85149;';
    errEl.textContent = '⚠ Artifact error: no file path provided.';
    wrap.appendChild(errEl);
    _append(target, wrap);
    return;
  }

  const ext = clean.split('.').pop().toLowerCase();
  const renderable = RENDERABLE_EXTS.has(ext);
  const viewable = TAB_VIEWABLE_EXTS.has(ext);      // browser can render it in a tab
  const showThumb = viewable || PANEL_ONLY_EXTS.has(ext);   // tall preview card

  wrap.dataset.artifactPath = clean;
  wrap.dataset.artifactCreated = String(Date.now());

  const openNewTab = async () => {
    try { await opfs.openInNewTab(await resolvedP); }
    catch (e) { console.error('[artifact] open in tab failed:', e); }
  };
  // Renderable files (html/svg/image/office/csv/json/txt) open the SIDE PANEL — the
  // rich view where pin/share/download/new-tab live. Everything else opens a new tab
  // (the browser renders it if it can, otherwise downloads).
  const openPanel = async () => openArtifactPanel(await resolvedP);
  const onOpen = renderable ? openPanel : openNewTab;
  // The ↗ mini-button (new tab) only makes sense for browser-viewable files.
  const onNewTab = viewable ? openNewTab : null;

  wrap.appendChild(buildArtifactCard(clean, ext, { onOpen, onNewTab, showThumb }));
  if (!showThumb) wrap.classList.add('artifact-compact');   // slim strip for data/text/code
  // Off-turn localization may have announced BEFORE this card existed (the worker
  // posts 'start' alongside the tool result) — pick the badge up now.
  _lxBadgeApply(wrap, _lxBadgeFor(clean));
  _append(target, wrap);

  // HTML tooling needs a live frame that the conversation no longer shows: the
  // html_console tool (readArtifactConsole) and the metacog console-note both read
  // window.__sandpieConsole from a loaded frame. Keep ONE hidden, offscreen frame
  // per HTML card — marked consoleOnly (screenshot capture + resize handler skip it).
  //
  // CRITICAL: it starts FROZEN and is NEVER auto-loaded. Auto-loading it here made
  // every HTML artifact EXECUTE TWICE at render — once in this frame and once in the
  // thumbnail capture (captureOffscreen) — so the page's external requests fired
  // twice and the second (single-use tokens / auth nonces / rate limits) came back
  // 401. The thumbnail capture is now the SINGLE render (one execution, same blob
  // context as the old inline view). readArtifactConsole self-heals by loading this
  // frame on demand only when the html_console tool is actually used.
  if (ext === 'html' || ext === 'htm') {
    const frame = document.createElement('iframe');
    frame.className = 'artifact-frame';
    frame.dataset.consoleOnly = '1';
    frame.dataset.frozen = '1';
    frame.setAttribute('aria-hidden', 'true');
    frame.tabIndex = -1;
    frame.style.cssText = 'position:absolute;left:-9999px;top:0;width:1px;height:1px;border:0;visibility:hidden;pointer-events:none;';
    wrap.appendChild(frame);
  }
}

// (Re)load an artifact's iframe from a fresh OPFS blob URL. Used both for the
// initial render and for auto-reload when a tool call rewrites the file (a blob
// URL is a snapshot of the bytes at creation — a new one is required for refresh).
async function loadArtifactFrame(wrap, frame, resolvedP, clean) {
  let p = null;
  // Clear any prior load-error strip so a retry (e.g. once the Dropbox sync
  // provider finally connects — see the sync:done handler) can succeed cleanly
  // instead of stacking error rows under the frame.
  for (const el of wrap.querySelectorAll(':scope > [data-artifact-error]')) el.remove();
  try {
    p = await resolvedP;
    wrap.dataset.artifactPath = p;
    const url = await opfs.toUrl(p);
    if (frame._blobUrl) URL.revokeObjectURL(frame._blobUrl);
    frame._blobUrl = url;
    frame.src = url;
    frame.style.display = 'block';
    delete frame.dataset.frozen;   // any load makes the frame live again (also self-heals readArtifactConsole)
    delete wrap.dataset.hydrateFailed;
    wrap.style.borderColor = '';
  } catch (e) {
    // A dehydrated (cloud-only) file that couldn't hydrate — most often because
    // the conversation loaded from history BEFORE the sync provider connected.
    // Mark it so the sync:done / account:signedin handler retries the load once a
    // provider is available, instead of leaving a permanent "file not found".
    wrap.dataset.hydrateFailed = '1';
    // Hidden console-only frame: NEVER surface a red 404 strip on the card. The
    // frame isn't shown, and a genuinely-deleted file is reflected by removing the
    // card (reflectFileDeletes), not by decorating it with an error.
    if (frame && frame.dataset.consoleOnly === '1') return;
    showArtifactError(wrap, frame, 'failed to load: ' + (clean || p || '') + ' — ' + (e && e.message || e));
  }
}

/* -------------------------------------------------------------------------- */
/*  Frame freeze / thaw — reclaim a hidden or off-screen artifact's memory     */
/* -------------------------------------------------------------------------- */

// Freezing an iframe is the real memory lever: display:none alone keeps the whole
// child document, its JS timers/RAF loops, and (crucially) any WebGL/WebGPU/canvas
// GPU context fully alive. Pointing src at about:blank and revoking the blob URL
// tears the renderer down, so a collapsed or scrolled-away artifact costs ~nothing.
// The path lives on wrap.dataset.artifactPath, so thawFrame can rebuild it verbatim.
function freezeFrame(frame) {
  if (!frame || frame.dataset.frozen === '1') return;
  frame.dataset.frozen = '1';
  if (frame._blobUrl) { URL.revokeObjectURL(frame._blobUrl); frame._blobUrl = null; }
  frame.src = 'about:blank';
}

// Reload a frozen frame from OPFS. No-op if it was never frozen (so expanding an
// already-live frame doesn't needlessly reload and re-run its scripts).
function thawFrame(wrap, frame) {
  if (!frame || frame.dataset.frozen !== '1') return;
  const p = wrap.dataset.artifactPath;
  if (p) loadArtifactFrame(wrap, frame, resolveArtifactPath(p), p);
  else delete frame.dataset.frozen;
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
  wrap.classList.add('artifact-compact');   // slim single-strip presentation (CSS)

  const frame = wrap.querySelector('.artifact-frame');
  const metaRow = wrap.querySelector('.artifact-meta-row');
  const colBtn = wrap.querySelector('.artifact-collapse-btn');

  if (frame) { frame.style.display = 'none'; freezeFrame(frame); }
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
  wrap.classList.remove('artifact-compact');

  const frame = wrap.querySelector('.artifact-frame');
  const metaRow = wrap.querySelector('.artifact-meta-row');
  const colBtn = wrap.querySelector('.artifact-collapse-btn');

  if (frame) { frame.style.display = 'block'; thawFrame(wrap, frame); }
  if (metaRow) metaRow.style.display = 'none';
  if (colBtn) { colBtn.textContent = '−'; colBtn.title = 'Collapse'; }
}

function toggleArtifactCollapse(wrap) {
  if (wrap.dataset.artifactCollapsed === '1') expandArtifact(wrap);
  else collapseArtifact(wrap);
  // User expand/collapse: keep the per-pane cap. If the expand pushed the open
  // count over the cap, auto-collapse the OLDEST open artifact (never the one
  // the user just toggled). See enforceArtifactCap.
  enforceArtifactCap(artifactPane(wrap), wrap);
}

/* -------------------------------------------------------------------------- */
/*  Per-pane open-artifact cap                                                */
/* -------------------------------------------------------------------------- */

// Low-end device detection: coarse, synchronous, free. deviceMemory is bucketed
// in GB (2/4/8…), hardwareConcurrency is logical cores. Either being small is a
// good proxy for "an artifact-heavy conversation will thrash this machine". Both
// can be undefined (Firefox has no deviceMemory) — default to the roomy branch so
// we never over-restrict a capable browser that just doesn't expose the hint.
const LOW_END_DEVICE = ((navigator.deviceMemory || 8) <= 4) || ((navigator.hardwareConcurrency || 8) <= 4);

// Max unminimized artifact frames per pane (#messages / #messagesSide). When a
// new show_artifact renders (or the user expands one) and the count would exceed
// this, the OLDEST open artifact is auto-collapsed back to its V2 card — newest
// N stay open. Panel-only / non-renderable artifacts have no inline frame, so
// they never count toward the cap. Low-end machines keep just ONE live frame:
// combined with freeze-on-collapse (see freezeFrame), that means at most one
// artifact renderer/GPU context is alive per pane on weak hardware.
const MAX_OPEN_ARTIFACTS_PER_PANE = LOW_END_DEVICE ? 1 : 3;

// Which pane a wrap lives in: 'side' (#messagesSide, the right conversation
// panel) or 'main' (#messages). Anything not inside the side panel counts as
// main — the cap is enforced separately per pane, so up to 2×N can be open.
function artifactPane(wrap) {
  return (wrap.closest && wrap.closest('#messagesSide')) ? 'side' : 'main';
}

// Wraps with a LIVE (non-frozen) .artifact-frame in this pane. These are the
// hidden HTML console frames — the only frames the conversation creates now.
function openArtifactFramesInPane(pane) {
  return Array.from(document.querySelectorAll('.artifact-wrap')).filter(w => {
    if (artifactPane(w) !== pane) return false;
    const f = w.querySelector('.artifact-frame');
    return f && f.dataset.frozen !== '1';
  });
}

// Enforce the cap for a pane. keepWrap (the artifact just rendered) is never a
// victim; the oldest OTHER live frames are FROZEN (src→about:blank, blob revoked)
// until only MAX_OPEN_ARTIFACTS_PER_PANE remain. Frozen frames self-heal: the
// html_console tool reloads them on demand. Purely a memory lever — the visible
// card is untouched. No-op when under the cap.
function enforceArtifactCap(pane, keepWrap) {
  const open = openArtifactFramesInPane(pane);
  if (open.length <= MAX_OPEN_ARTIFACTS_PER_PANE) return;
  const ordered = open.slice().sort((a, b) =>
    (parseInt(a.dataset.artifactCreated, 10) || 0) - (parseInt(b.dataset.artifactCreated, 10) || 0));
  let count = open.length;
  for (const wrap of ordered) {
    if (count <= MAX_OPEN_ARTIFACTS_PER_PANE) break;
    if (wrap === keepWrap) continue;
    const frame = wrap.querySelector('.artifact-frame');
    if (frame) freezeFrame(frame);
    count--;
  }
}

/* -------------------------------------------------------------------------- */
/*  Off-screen freezing (low-end devices only)                                */
/* -------------------------------------------------------------------------- */

// On weak hardware, even an under-the-cap open artifact costs memory while it sits
// scrolled far off-screen. A single shared IntersectionObserver freezes an EXPANDED
// frame once it leaves the viewport (plus ~a screenful of slack) and thaws it when
// it returns. Collapsed frames are skipped — the cap/collapse path already froze
// them and owns their lifecycle. Disabled on roomy devices: the reload-on-scroll-
// back flash isn't worth it when RAM is plentiful. rootMargin keeps a generous
// margin so normal scrolling near an artifact doesn't churn it.
let _artifactVisIO = null;
function observeArtifactVisibility(wrap) {
  if (!LOW_END_DEVICE || typeof IntersectionObserver === 'undefined') return;
  if (!_artifactVisIO) {
    _artifactVisIO = new IntersectionObserver((entries) => {
      for (const ent of entries) {
        const w = ent.target;
        if (w.dataset.artifactCollapsed === '1') continue;   // cap/collapse owns these
        const frame = w.querySelector('.artifact-frame');
        if (!frame) continue;
        if (ent.isIntersecting) thawFrame(w, frame);
        else freezeFrame(frame);
      }
    }, { rootMargin: '800px 0px' });
  }
  _artifactVisIO.observe(wrap);
}

/* -------------------------------------------------------------------------- */
/*  Error display                                                             */
/* -------------------------------------------------------------------------- */

function showArtifactError(wrap, frame, msg) {
  if (frame) frame.style.display = 'none';
  const errEl = document.createElement('div');
  errEl.dataset.artifactError = '1';   // so loadArtifactFrame can clear it on retry
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
  if (window.SandpieActivity) SandpieActivity.fire('artifact_open', 'view', clean);

  if (typeof sidePanel !== 'undefined' && sidePanel?.isOpen) sidePanel.close();
  if (typeof opfs !== 'undefined' && opfs.openFile) {
    opfs.openFile(clean, clean.split('/').pop(), { prefer: 'side' });
  }
}

function closeArtifactPanel() {
  if (typeof opfs !== 'undefined' && opfs.closeFile) opfs.closeFile();
}

// Remove every artifact card for the given path(s) — used when a file is deleted so
// the conversation reflects the deletion instead of leaving a card that 404s. Also
// drops the card's grid wrapper if it becomes empty. Matches with the usual
// sandpie/-prefix + files/ aliasing. Returns the number of cards removed.
function removeArtifactByPath(input) {
  const list = Array.isArray(input) ? input : [input];
  const norm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '');
  const strip = (p) => p.replace(/^sandpie\//, '');
  const wants = new Set();
  for (const p of list) { const n = norm(p); if (n) { wants.add(n); wants.add(strip(n)); } }
  if (!wants.size) return 0;
  let removed = 0;
  for (const wrap of document.querySelectorAll('.artifact-wrap')) {
    const c = norm(wrap.dataset.artifactPath || '');
    if (!c) continue;
    if (wants.has(c) || wants.has(strip(c))) {
      const grid = wrap.closest('.artifact-grid');
      wrap.remove();
      if (grid && !grid.querySelector('.artifact-wrap')) grid.remove();
      removed++;
    }
  }
  return removed;
}
window.removeArtifactByPath = removeArtifactByPath;

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
  // Normalize both the query AND the stored wrap path the same way: strip leading
  // slashes, a files/ prefix, a sandpie/ prefix, and trailing slashes. The stored
  // data-artifact-path is the RESOLVED path (loadArtifactFrame overwrites it), which
  // can carry a sandpie/ prefix the caller doesn't know about, or vice versa.
  const norm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '').replace(/^sandpie\//, '').replace(/\/+$/, '');
  const strip = (p) => String(p || '').replace(/^sandpie\//, '');
  const want = norm(path);
  const wraps = Array.from(document.querySelectorAll('.artifact-wrap'));
  let found = null;
  // Accepted forms of the requested path: normalized, stripped-of-sandpie, and (if
  // resolvable) the resolved form — covers the legacy artifacts/ → sandpie/artifacts/
  // remap and any alias the caller might use.
  const wantForms = new Set([want, strip(want)]);
  if (want) {
    try {
      const r = await resolveArtifactPath(want);
      if (r) { wantForms.add(norm(r)); wantForms.add(strip(norm(r))); }
    } catch (_) {}
  }
  for (const wrap of wraps) {
    const cur = wrap.dataset.artifactPath;
    if (!cur) continue;
    const c = norm(cur);
    if (want && !wantForms.has(c) && !wantForms.has(strip(c))) continue;
    const frame = wrap.querySelector('.artifact-frame');
    if (frame) { found = { wrap, frame }; break; }
  }
  if (!found && want) {
    // Auto-render: artifacts surface automatically at turn end now, so a mid-turn
    // console read may precede any card. Render the requested file expanded and
    // read from that fresh frame.
    try {
      // Render into the CURRENT conversation's mounted host (html_console is a
      // tool call of the focused conv); detached container if none is mounted.
      const _cs = (typeof activeStream === 'function') ? activeStream() : _activeStream();
      const _ch = (_cs && _cs.host && (typeof _streamOwnsPaneSlot === 'function' ? _streamOwnsPaneSlot(_cs) : _cs.host.isConnected)) ? _cs.host : document.createElement('div');
      renderArtifact(_ch, want);
      const wrap = Array.from(document.querySelectorAll('.artifact-wrap')).reverse().find(w => {
        const c = norm(w.dataset.artifactPath || '');
        return c && (wantForms.has(c) || wantForms.has(strip(c)));
      });
      const frame = wrap && wrap.querySelector('.artifact-frame');
      if (frame) {
        await new Promise(res => { frame.addEventListener('load', res, { once: true }); setTimeout(res, 5000); });
        found = { wrap, frame };
      }
    } catch (_) {}
  }
  if (!found) {
    const known = wraps.map(w => w.dataset.artifactPath).filter(Boolean).slice(0, 5);
    let detail;
    if (want) {
      detail = 'Artifacts currently in the DOM (max 5): ' + (known.length ? known.map(p => '"' + p + '"').join(', ') : 'none') + '. It could not be auto-rendered — check the exact path.';
    } else {
      detail = 'No path was given. Artifacts currently in the DOM (max 5): ' + (known.length ? known.map(p => '"' + p + '"').join(', ') : 'none') + '.';
    }
    return { error: want ? 'No artifact frame open for "' + path + '". ' + detail : detail };
  }
  try {
    let w = found.frame.contentWindow;
    if (!w || !w.__sandpieConsole) {
      // Self-heal: the frame may predate instrumentation (or the bootstrap failed to
      // inject). Reload it through opfs.toUrl — which ALWAYS injects the console
      // capture — and re-read. This makes the tool reliable regardless of when the
      // artifact was shown.
      const p = found.wrap.dataset.artifactPath || want;
      await new Promise((resolve) => {
        const onLoad = () => resolve();
        found.frame.addEventListener('load', onLoad, { once: true });
        loadArtifactFrame(found.wrap, found.frame, resolveArtifactPath(p), p).catch(() => {});
        setTimeout(resolve, 5000);   // safety net if the load event never fires
      });
      w = found.frame.contentWindow;
    }
    if (!w || !w.__sandpieConsole) return { error: 'This artifact has no console capture (loaded before instrumentation, or it is not an HTML file).' };
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
// ── Translating badge — deliverable localization runs off-turn, so the card
// shows the English file first. While a path sits on the worker's localization
// queue its card(s) carry a small "🌐 Translating…" badge in the header; the
// 'done' event clears it (the translated file swap follows via artifact:changed).
// _lxPending survives the start-event-before-card race: renderArtifact consults
// it when a new card is built.
const _lxPending = new Map();   // stripped path -> label
function _lxStrip(p) {
  const n = String(p || '').replace(/^\/+/, '').replace(/^files\//, '');
  return n.startsWith('sandpie/') ? n.slice('sandpie/'.length) : n;
}
// The "🌐 Translating…" badge now lives as an overlay on the card thumb (.ac-lx),
// built hidden by buildArtifactCard. Toggle its text/visibility per wrap.
function _lxBadgeApply(wrap, label) {
  if (!wrap) return;
  const b = wrap.querySelector('.ac-lx');
  if (!b) return;
  if (label) { b.textContent = '🌐 ' + label; b.hidden = false; }
  else { b.textContent = ''; b.hidden = true; }
}
function _lxBadgeFor(path) { return _lxPending.get(_lxStrip(path)) || null; }
if (typeof Sandpie !== 'undefined' && Sandpie.events) {
  Sandpie.events.on('artifact:localizing', (ev) => {
    if (!ev || !ev.path) return;
    const key = _lxStrip(ev.path);
    const label = ev.state === 'start' ? (ev.label || 'Translating…') : null;
    if (label) _lxPending.set(key, label); else _lxPending.delete(key);
    for (const wrap of document.querySelectorAll('.artifact-wrap')) {
      if (_lxStrip(wrap.dataset.artifactPath) === key) _lxBadgeApply(wrap, label);
    }
  });
}
// Card-integrity self-heal: if a wrap ever loses its card body (historically the
// missing-header bug after a same-file edit), rebuild it in place. Named
// _artifactEnsureHeader for back-compat with conversations.js callers.
function _artifactEnsureHeader(wrap) {
  try {
    if (!wrap || !wrap.isConnected || wrap.querySelector(':scope > .artifact-card-body')) return;
    const path = wrap.dataset.artifactPath;
    const target = wrap.parentElement;
    const next = wrap.nextSibling;
    wrap.remove();
    if (!path || !target) return;
    // Rebuild into a DETACHED container, then splice the fresh wrap back at the
    // recorded position. The old renderArtifact(null, path) + global
    // document.querySelectorAll search spawned the card in whatever conversation
    // happened to be focused (2026-09-13 cross-conv artifact bug).
    const pen = document.createElement('div');
    renderArtifact(pen, path);
    const fresh = pen.querySelector('.artifact-wrap');
    if (fresh) target.insertBefore(fresh, next);
  } catch (_) {}
}
window._artifactEnsureHeader = _artifactEnsureHeader;
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
        _artifactEnsureHeader(wrap);
        if (!wrap.isConnected) continue;   // self-heal replaced it; the fresh card just loaded
        const frame = wrap.querySelector('.artifact-frame');
        if (frame) loadArtifactFrame(wrap, frame, Promise.resolve(resolved), resolved);
        // Bytes changed → the cached thumbnail is stale. Invalidate + re-capture
        // (new file size misses the size-keyed cache) so the card preview refreshes.
        const shot = wrap.querySelector('.ac-shot');
        if (shot) {
          try { if (window.SandpieArtifactThumbs && SandpieArtifactThumbs.invalidate) SandpieArtifactThumbs.invalidate(cur); } catch (_) {}
          const ext = (cur.split('.').pop() || '').toLowerCase();
          shot.classList.remove('ready'); shot.hidden = true;
          _fillArtifactThumb(wrap.querySelector('.artifact-card-body') || wrap, cur, ext);
        }
      }
    }).catch(() => {});
  });
  // Retry artifacts that failed to hydrate because no sync provider was connected
  // yet (the classic symptom: open a conversation from history before Dropbox
  // finishes connecting → the .html artifact 404s / "file not found" forever).
  // Once a provider connects (account:signedin) or a sync completes (sync:done),
  // re-run the load for every frame still marked hydrate-failed. Bounded work
  // (only failed frames), idempotent (success clears the marker).
  const _retryFailedArtifacts = () => {
    for (const wrap of document.querySelectorAll('.artifact-wrap[data-hydrate-failed]')) {
      if (!wrap.isConnected) continue;
      const frame = wrap.querySelector('.artifact-frame');
      const p = wrap.dataset.artifactPath;
      if (frame && p) loadArtifactFrame(wrap, frame, resolveArtifactPath(p), p).catch(() => {});
    }
  };
  Sandpie.events.on('sync:done', _retryFailedArtifacts);
  Sandpie.events.on('account:signedin', _retryFailedArtifacts);
}
window.formatArtifactBytes = formatArtifactBytes;
window.formatArtifactAge = formatArtifactAge;
window.collapseArtifact = collapseArtifact;
window.expandArtifact = expandArtifact;
window.toggleArtifactCollapse = toggleArtifactCollapse;
window.showArtifactError = showArtifactError;
window.openArtifactPanel = openArtifactPanel;
window.closeArtifactPanel = closeArtifactPanel;
window.resolveArtifactPath = resolveArtifactPath;
