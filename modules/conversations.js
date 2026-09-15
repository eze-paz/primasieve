// ---- streamDiff (was streamdiff.js) — minimal DOM diff/patch for preserving
// selection during streaming. Receives a live DOM element and a new HTML string.
// Parses the HTML into a temp fragment, then walks both trees to apply only the
// minimal set of attribute/child mutations needed. Text nodes that haven't
// changed are left untouched, so any active user text selection survives.
// ---------------------------------------------------------------------------
const _SD_DIV = document.createElement('div');

function _sdPatchAttrs(el, ref) {
  const keep = new Set();
  for (const a of ref.attributes || []) {
    keep.add(a.name);
    if (el.getAttribute(a.name) !== a.value) el.setAttribute(a.name, a.value);
  }
  for (const a of Array.from(el.attributes)) {
    if (!keep.has(a.name)) el.removeAttribute(a.name);
  }
}

function _sdPatchKids(el, ref) {
  const oldN = el.childNodes.length;
  const newN = ref.childNodes.length;
  const min = Math.min(oldN, newN);

  for (let i = 0; i < min; i++) {
    const o = el.childNodes[i];
    const n = ref.childNodes[i];
    const sameType = o.nodeType === n.nodeType;

    if (sameType && o.nodeType === Node.TEXT_NODE) {
      if (o.nodeValue !== n.nodeValue) o.nodeValue = n.nodeValue;
      continue;
    }

    if (sameType && o.nodeType === Node.ELEMENT_NODE && o.tagName === n.tagName) {
      _sdPatchAttrs(o, n);
      _sdPatchKids(o, n);
      continue;
    }

    el.replaceChild(n.cloneNode(true), o);
  }

  while (el.childNodes.length > min) el.removeChild(el.lastChild);

  for (let i = min; i < newN; i++) {
    el.appendChild(ref.childNodes[i].cloneNode(true));
  }
}

function streamDiff(rootEl, html) {
  _SD_DIV.innerHTML = html;
  _sdPatchKids(rootEl, _SD_DIV);
}
const CONV_DIR = 'sandpie/conversations';
const ARCHIVED_DIR = 'sandpie/conversations/archived';
function newConvId() {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}
function convPath(id, archived = false) {
  return archived ? `${ARCHIVED_DIR}/${id}.json` : `${CONV_DIR}/${id}.json`;
}

/* ===========================================================================
   Conversation storage — meta sidecar + append-only JSONL.

   Each conversation is TWO files:
     <id>.meta.json  — small, mutable metadata (title/updated/pinned/compaction/…)
     <id>.jsonl      — append-only message log, one message object per line
   Rename/pin/archive/compaction rewrite only the tiny meta; appending a message
   appends one line (O(new bytes)) instead of re-serializing the whole chat; and
   the sidebar list reads only the tiny meta files instead of every chat in full.

   Legacy monolithic <id>.json files are still READ (fallback), and MIGRATED on
   first save (a new pair is written alongside) but are NEVER deleted — they remain
   as frozen backups. convLocation() prefers the new format when both exist.
   =========================================================================== */
const META_SUFFIX = '.meta.json';
function metaPath(id, archived = false) { return `${archived ? ARCHIVED_DIR : CONV_DIR}/${id}${META_SUFFIX}`; }
function jsonlPath(id, archived = false) { return `${archived ? ARCHIVED_DIR : CONV_DIR}/${id}.jsonl`; }

function _convText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.filter(p => p && p.type === 'text').map(p => p.text || '').join(' ');
  return '';
}
function _parseJsonl(text) {
  const out = [];
  for (const line of String(text).split('\n')) {
    const t = line.trim(); if (!t) continue;
    try { out.push(JSON.parse(t)); } catch (_) { /* tolerate a torn trailing line (crash mid-append) */ }
  }
  return out;
}
// Read + parse a conversation JSONL, retrying once when a line fails to parse.
// Incremental saves append every ~1.2s DURING a turn, so a load that races an
// in-flight append can read a torn trailing line. _parseJsonl silently DROPS
// such a line — and the last message of a round is often the write_todos tool
// result carrying the checklist JSON — so the box rendered empty "sometimes"
// (same file, different timing). Retry after the append settles, then degrade
// gracefully exactly as before.
async function readConvJsonl(path) {
  let text = '', torn = true;
  for (let attempt = 0; attempt < 2 && torn; attempt++) {
    try { text = await opfs.read(path); } catch (_) { return []; }
    torn = false;
    for (const line of String(text).split('\n')) {
      const t = line.trim(); if (!t) continue;
      try { JSON.parse(t); } catch (_) { torn = true; }
    }
    if (torn && attempt === 0) await new Promise(r => setTimeout(r, 300));
  }
  const msgs = [];
  for (const line of String(text).split('\n')) {
    const t = line.trim(); if (!t) continue;
    try { msgs.push(JSON.parse(t)); } catch (_) { /* tolerate a torn trailing line */ }
  }
  return msgs;
}
function _serializeJsonl(msgs) { return msgs.length ? msgs.map(m => JSON.stringify(m)).join('\n') + '\n' : ''; }

function _deriveTitle(msgs) {
  const firstUser = (msgs || []).find(m => m.role === 'user');
  if (firstUser && firstUser.content) return (_convText(firstUser.content).slice(0, 60)) || 'Untitled';
  return 'Untitled';
}

// Where a conversation lives + its format. Prefers the new meta format; falls back
// to a legacy .json. Returns { archived, format: 'new' | 'old' | null }.
async function convLocation(id) {
  if (await opfs.exists(metaPath(id, false))) return { archived: false, format: 'new' };
  if (await opfs.exists(metaPath(id, true)))  return { archived: true,  format: 'new' };
  if (await opfs.exists(convPath(id, false))) return { archived: false, format: 'old' };
  if (await opfs.exists(convPath(id, true)))  return { archived: true,  format: 'old' };
  return { archived: false, format: null };
}

// Just the metadata object, whichever format the conversation is stored in — no
// messages read (a legacy .json carries both, the new format keeps meta tiny).
// null when the conversation isn't on disk yet or the file is unreadable.
async function readConvMeta(id) {
  const loc = await convLocation(id);
  if (!loc.format) return null;
  const p = loc.format === 'new' ? metaPath(id, loc.archived) : convPath(id, loc.archived);
  try { return JSON.parse(await opfs.read(p)); } catch (_) { return null; }
}
// The conversation's stored title ('' when unknown) — for callers that only need
// the name, e.g. the completion notification.
async function convTitle(id) { const m = await readConvMeta(id); return (m && m.title) || ''; }

// Unified loader → { id, title, updated, pinned, archived, compaction, todos,
// usage, messages, _format } or null. Callers don't care about on-disk format.
async function readConvData(id) {
  const loc = await convLocation(id);
  await ensureLocalConvFile(loc.format === 'new' ? jsonlPath(id, loc.archived) : convPath(id, loc.archived));
  if (loc.format === 'new') {
    let meta = {}; try { meta = JSON.parse(await opfs.read(metaPath(id, loc.archived))); } catch {}
    let messages = []; try { messages = await readConvJsonl(jsonlPath(id, loc.archived)); } catch {}
    return { ...meta, id, archived: loc.archived, messages, _format: 'new' };
  }
  if (loc.format === 'old') {
    let data; try { data = JSON.parse(await opfs.read(convPath(id, loc.archived))); } catch { return null; }
    migrateCompactionData(data);
    data.id = id; data.archived = loc.archived; data._format = 'old';
    if (!Array.isArray(data.messages)) data.messages = [];
    return data;
  }
  return null;
}

// Per-conversation prompt-cache key (OpenRouter session_id). Generated once as
// <random>-<convId> and persisted in the conversation meta so it stays stable
// across turns, refreshes, and devices — without it, every send regenerates
// the id and the cached system+history prefix is recomputed from scratch.
// Duplicates/rewinds behave correctly for free: duplicateConv writes a clean
// meta (no session_id) so the copy gets its own key; rewind keeps the same
// conversation's meta, so it reuses the same key.
function newSessionId(convId) {
  return (Math.random().toString(36).slice(2, 10)) + '-' + (convId || 'unknown');
}
async function ensureSessionId(convId) {
  if (!convId) return null;
  const loc = await convLocation(convId);
  const mp = metaPath(convId, loc.archived);
  let meta = null;
  try { meta = JSON.parse(await opfs.read(mp)); } catch {}
  if (meta && meta.session_id) return meta.session_id;
  const sid = newSessionId(convId);
  const updated = Object.assign({}, meta || {}, { id: convId, session_id: sid });
  // A >>> lite toggle on a brand-new conversation (no meta yet) is honored here:
  if (liteMetaCache.get(convId) === true) updated.lite = true;
  await opfs.write(mp, JSON.stringify(updated));
  Sandpie.events.emit('file:changed', mp);
  return sid;
}

// Lightweight list row. New format → read only the tiny meta file. Legacy → read
// the whole .json (unavoidable until it migrates). Message text for search is only
// pulled when a query is active.
async function readConvMetaRow(id, archived, format, wantSearch) {
  try {
    if (format === 'new') {
      const meta = JSON.parse(await opfs.read(metaPath(id, archived)));
      const row = { id: meta.id || id, title: meta.title || '(no title)', updated: meta.updated || '', pinned: !!meta.pinned, archived, projectRoot: meta.projectRoot || null };
      if (wantSearch) { try { row.messageContent = _parseJsonl(await opfs.read(jsonlPath(id, archived))).map(m => _convText(m.content)).join(' ').toLowerCase(); } catch {} }
      return row;
    }
    const data = JSON.parse(await opfs.read(convPath(id, archived)));
    const row = { id: data.id || id, title: data.title || '(no title)', updated: data.updated || '', pinned: !!data.pinned, archived, projectRoot: data.projectRoot || null };
    if (wantSearch) row.messageContent = (data.messages || []).map(m => _convText(m.content)).join(' ').toLowerCase();
    return row;
  } catch { return null; }
}

// Hydrate-then-read support (archive-dehydration step 3): conversation files may
// exist only in Dropbox (body purged locally). Fetch one into OPFS; false when
// it isn't local AND isn't in the cloud index (or the cloud is unreachable) —
// callers degrade to today's behavior, never lose data.
async function ensureLocalConvFile(p) {
  try { if (await opfs.exists(p)) return true; } catch {}
  try {
    const sp = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
    if (!sp || !sp.cloudConnected || !sp.cloudConnected() || !sp.cloudDownload) return false;
    const e = (sp.cloudIndex && sp.cloudIndex()) ? sp.cloudIndex()[p] : null;
    if (!e || e.kind !== 'file') return false;   // not in the cloud either
    const bytes = await sp.cloudDownload(e.path || ((sp.workingRoot() || '') + '/' + p), { team: false });
    await opfs.write(p, bytes);
    return true;
  } catch (_) { return false; }
}

async function rewriteConvJsonl(id, archived, messages) {
  const p = jsonlPath(id, archived);
  await opfs.write(p, _serializeJsonl(messages || []));
  Sandpie.events.emit('file:changed', p);
}
async function appendConvMessages(id, archived, msgs) {
  if (!msgs || !msgs.length) return;
  const p = jsonlPath(id, archived);
  await opfs.append(p, _serializeJsonl(msgs));
  Sandpie.events.emit('file:changed', p);
}
async function ensureActiveConv() {
  if (activeConvId) return;
  activeConvId = newConvId();
  localStorage.setItem('sandpie-active-conv', activeConvId);
}
async function saveActiveConv() { return saveConv(activeConvId, { touchUpdated: false }); }
// Throttled mid-turn persistence. The final saveConv only runs when a turn ends,
// so a crash/tab-close mid-turn used to lose every round streamed since the last
// user message. Persist committed rounds as they arrive (bindMessage → here),
// coalesced to at most one write per conversation per ~1.2s. touchUpdated:false
// keeps the sidebar timestamp stable until the turn actually completes; the
// byte-identical no-op guard in saveConv absorbs redundant ticks.
const _incSaveTimers = new Map();
function scheduleIncrementalSave(convId) {
  if (!convId || _incSaveTimers.has(convId)) return;
  _incSaveTimers.set(convId, setTimeout(() => {
    _incSaveTimers.delete(convId);
    saveConv(convId, { touchUpdated: false }).catch(() => {});
  }, 1200));
}
function flushIncrementalSave(convId) {
  const t = _incSaveTimers.get(convId);
  if (t) { clearTimeout(t); _incSaveTimers.delete(convId); }
}
// ── Cross-TAB single-writer lock per conversation ───────────────────────────
// The save chain below serializes saves within ONE tab, but two tabs (or a
// reload racing a not-yet-dead tab) each hold their own persistedCount and both
// append — duplicating whole history blocks in the JSONL (seen in the wild:
// ptruyol 2026-08-28, 42% of a 446-message conversation was byte-identical
// duplicates). Web Locks arbitrate: the first tab to mount or save a
// conversation becomes its writer for the tab's lifetime (locks auto-release on
// tab close); other tabs view read-only — sends are refused and saves skipped.
// Fail-open when the API is missing so a single-tab session never regresses.
const _convWriterLocks = new Map();   // convId → release() while this tab holds the lock
const _convLockAcquiring = new Map(); // convId → in-flight acquisition Promise<bool> (single-flight)
function _convLockName(id) { return 'sandpie-conv-writer:' + id; }
async function acquireConvWriterLock(convId) {
  if (!convId || typeof navigator === 'undefined' || !navigator.locks || !navigator.locks.request) return true;
  if (_convWriterLocks.has(convId)) return true;
  // SINGLE-FLIGHT: one tab calls this from mount, send, AND save, often before
  // the first call's lock callback has populated _convWriterLocks. Without
  // coalescing, each call issues its OWN navigator.locks.request with
  // ifAvailable:true; the first grabs the (tab-lifetime) lock and every later
  // concurrent request sees it as unavailable → resolves FALSE → the tab wrongly
  // decides "another tab owns this", skips the save / refuses the send, and the
  // just-generated reply is never persisted (vanishes on the next render). Share
  // ONE acquisition across all concurrent callers so the whole tab agrees.
  if (_convLockAcquiring.has(convId)) return _convLockAcquiring.get(convId);
  const p = (async () => {
    try {
      return await new Promise((resolve) => {
        navigator.locks.request(_convLockName(convId), { ifAvailable: true }, (lock) => {
          if (!lock) { resolve(false); return; }
          resolve(true);
          // Returned promise keeps the lock held until releaseConvWriterLock().
          return new Promise((release) => { _convWriterLocks.set(convId, release); });
        }).catch(() => resolve(true));   // request itself failed → fail open
      });
    } catch (_) { return true; }
  })().finally(() => _convLockAcquiring.delete(convId));
  _convLockAcquiring.set(convId, p);
  return p;
}
function releaseConvWriterLock(convId) {
  const release = _convWriterLocks.get(convId);
  if (release) { _convWriterLocks.delete(convId); try { release(); } catch (_) {} }
}
// Read-only notice. DOM-guarded (not flag-guarded): the cold-load path calls
// renderConversation AFTER the mount-time acquire resolves, wiping the host —
// so the notice must be re-assertable and idempotent against what's on screen.
function _notifyReadOnlyConv(s) {
  if (!s || !s.host) return;
  if (s.host.querySelector('.conv-readonly-note')) return;
  const el = addMsg('err', 'This conversation is owned by another open tab or window — viewing read-only here. Close it there (or close that tab) and try again.', s.host);
  if (el && el.classList) el.classList.add('conv-readonly-note');
}

// Serialize saves per conversation. saveConv is async (convLocation + opfs
// append), and two concurrent calls — the ~1.2s incremental timer racing the
// turn-end save in sendSingle's finally — could BOTH read the same
// persistedCount and append the same tail, duplicating a whole round in the
// JSONL (seen in the wild: identical tool_call ids, same [rN] results twice).
// Chaining per conv makes each save see the previous one's persistedCount.
const _saveChains = new Map();
function saveConv(convId, opts = {}) {
  const prev = _saveChains.get(convId) || Promise.resolve();
  const next = prev.then(() => _saveConv(convId, opts)).catch((e) => console.warn('[sandpie] saveConv failed:', e && e.message));
  _saveChains.set(convId, next);
  return next;
}
async function _saveConv(convId, { touchUpdated = true } = {}) {
  if (!convId) return;
  const s = convStreams.get(convId);
  const msgs = s ? s.messages : (convId === activeConvId ? messages : null);
  if (!msgs || !msgs.length) return;

  // Another tab owns this conversation: writing would append our (stale) tail
  // after its rounds, duplicating history — the exact corruption the writer
  // lock exists to stop. Skip; the owner tab is persisting its own copy.
  if (!(await acquireConvWriterLock(convId))) {
    console.warn('[sandpie] save skipped — conversation is owned by another tab:', convId);
    if (s) _notifyReadOnlyConv(s);
    return;
  }

  const loc = await convLocation(convId);
  const archived = loc.archived;

  // Previous metadata + the raw meta bytes (for a no-op guard). For a legacy conv
  // we read its .json ONCE here to carry title/created/usage forward; the write
  // below migrates it to the new pair (the old .json is left as a frozen backup).
  let prevMeta = null, prevMetaRaw = null;
  if (loc.format === 'new') { try { prevMetaRaw = await opfs.read(metaPath(convId, archived)); prevMeta = JSON.parse(prevMetaRaw); } catch {} }
  else if (loc.format === 'old') { try { prevMeta = JSON.parse(await opfs.read(convPath(convId, archived))); } catch {} }

  // How many messages are already in the JSONL on disk. null on a freshly-created
  // or legacy-loaded stream → treat as 0 so the first save writes them all.
  if (s && s.persistedCount == null) s.persistedCount = (loc.format === 'new') ? msgs.length : 0;
  const persisted = s ? s.persistedCount : (loc.format === 'new' ? msgs.length : 0);

  // Append the new tail, or rewrite when history was truncated (rewind) or a full
  // rewrite was requested. A legacy conv (persisted 0, no jsonl) migrates via the
  // append-from-0 path, which creates the .jsonl with every message.
  if ((s && s._forceJsonlRewrite) || persisted > msgs.length) {
    await rewriteConvJsonl(convId, archived, msgs);
  } else if (persisted < msgs.length) {
    await appendConvMessages(convId, archived, msgs.slice(persisted));
  }
  if (s) { s.persistedCount = msgs.length; s._forceJsonlRewrite = false; }

  // Build + write the (tiny) meta. Guarded so a no-op save (e.g. saveActiveConv on
  // focus switch) writes nothing and emits no spurious file:changed → no Dropbox churn.
  const meta = {
    id: convId,
    title: (prevMeta && prevMeta.title) || _deriveTitle(msgs),
    created: (prevMeta && (prevMeta.created || prevMeta.updated)) || new Date().toISOString(),
    updated: touchUpdated ? new Date().toISOString() : ((prevMeta && prevMeta.updated) || new Date().toISOString()),
    pinned: prevMeta ? !!prevMeta.pinned : false,
    msgCount: msgs.length,
  };
  const comp = s ? s.compaction : (prevMeta && prevMeta.compaction);
  const todos = s ? s.todos : (prevMeta && prevMeta.todos);
  if (comp) meta.compaction = comp;
  if (todos) meta.todos = todos;
  const filesT = s ? s.filesTouched : (prevMeta && prevMeta.filesTouched);
  if (filesT && filesT.length) meta.filesTouched = filesT;
  // Artifact thumbnails (captured HTML previews) live in the conv meta so they
  // travel/sync with the conversation and replay without re-capturing.
  const thumbs = s ? s.artifactThumbs : (prevMeta && prevMeta.artifactThumbs);
  if (thumbs && Object.keys(thumbs).length) meta.artifactThumbs = thumbs;
  if (prevMeta && prevMeta.usage) meta.usage = prevMeta.usage;
  // Persist the last-turn timer snapshot so it survives refresh and can be
  // rebuilt by rebuildSettledTimer on cold load.
  if (s && s.lastTurn) meta.lastTurn = s.lastTurn;
  // Keep the stable cache key across saves; otherwise the first save after
  // ensureSessionId() rewrites meta and would drop session_id.
  if (prevMeta && prevMeta.session_id) meta.session_id = prevMeta.session_id;
  // Same reason: meta is rebuilt from scratch here, so the "this title is real,
  // don't auto-title over it" flag (set by renameConv / maybeAutoTitle) has to be
  // carried forward — otherwise every save would make the conversation eligible
  // for auto-titling again.
  if (prevMeta && prevMeta.titleLocked) meta.titleLocked = true;
  // The conversation's project folder (absolute Dropbox path + namespace): meta is
  // rebuilt from scratch here, so carry it forward, preferring a warm stream's value.
  const projRoot = (s && s.projectRoot) || (prevMeta && prevMeta.projectRoot);
  if (projRoot) {
    meta.projectRoot = projRoot;
    meta.projectNs = (s && s.projectNs) || (prevMeta && prevMeta.projectNs) || 'home';
  }
  // PER-CONVERSATION provider: carried forward like projectRoot (meta is rebuilt
  // from scratch on every save). null → the catalog default applies.
  // Stale-save guard: the stream value only wins when THIS tab explicitly picked
  // it (setProviderId sets _provDirty). Otherwise another tab/browser may have
  // written a fresher providerId to meta.json since our stream loaded — the fresh
  // meta value must win, so a background save can't silently revert that change.
  let provId;
  if (s && s._provDirty) { provId = s.providerId || null; s._provDirty = false; }
  else provId = (prevMeta && prevMeta.providerId) || (s && s.providerId) || null;
  if (provId) meta.providerId = provId;
  // PER-CONVERSATION project: carried forward like providerId (meta is rebuilt
  // from scratch on every save). null → projectless.
  let projId;
  if (s && s._projDirty) { projId = s.projectId || null; s._projDirty = false; }
  else projId = (prevMeta && prevMeta.projectId) || (s && s.projectId) || null;
  if (projId) meta.projectId = projId;
  // PER-CONVERSATION reasoning effort: carried forward like providerId (meta is
  // rebuilt from scratch on every save). null → the app default applies.
  let rsnLvl;
  if (s && s._rsnDirty) { rsnLvl = s.reasoningLevel || null; s._rsnDirty = false; }
  else rsnLvl = (prevMeta && prevMeta.reasoningLevel) || (s && s.reasoningLevel) || null;
  if (rsnLvl) meta.reasoningLevel = rsnLvl;
  // Paths touched by tools in this conversation (from augmentations.js)
  const convPaths = (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.getConvPaths)
    ? SandpieAugmentations.getConvPaths(convId)
    : (prevMeta && prevMeta.paths) || [];
  if (convPaths && convPaths.length) meta.paths = convPaths;

  const metaStr = JSON.stringify(meta);
  if (metaStr !== prevMetaRaw) {
    await opfs.write(metaPath(convId, archived), metaStr);
    Sandpie.events.emit('file:changed', metaPath(convId, archived));
  }

  await refreshConversationList();
  refreshPaneBars();
}
// show_artifact calls seen during history replay, keyed by tool-call id; the
// matching tool RESULT decides whether the artifact actually renders (a
// blocked call renders nothing — same contract as the live path).
const _histArtifacts = new Map();

// ---- Local-file references in replies --------------------------------------
// After a reply paints, its OPFS references come alive:
//   <img src="projects/…/x.svg">  (markdown ![](path)) → loads the real file
//   <a href="local/path">, <code>local/path.ext</code> → click opens the viewer
// Idempotent (data-lr-done) so the streaming repaint can call it every tick.
const _lrBlobUrls = new Map();   // normalized path → blob URL (session cache)
const _LR_PATHISH = /^[\w.\-][\w.\- ()]*(?:\/[\w.\- ()]+)+\.[A-Za-z0-9]{1,8}$/;
const _LR_IMG_MIME = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml', avif: 'image/avif', bmp: 'image/bmp', ico: 'image/x-icon' };
function _lrNorm(p) {
  p = String(p || '').trim();
  try { p = decodeURIComponent(p); } catch (_) {}
  return p.replace(/^\.\//, '').replace(/^\/?files\//, '').replace(/^opfs:\/\//, '').replace(/^\/+/, '');
}
async function _lrBlobUrl(path, raw) {
  if (_lrBlobUrls.has(path)) return _lrBlobUrls.get(path);
  const mime = _LR_IMG_MIME[path.split('.').pop().toLowerCase()];
  if (!mime) return null;
  const cache = (bytes) => { const url = URL.createObjectURL(new Blob([bytes], { type: mime })); _lrBlobUrls.set(path, url); return url; };
  try { return cache(await opfs.readBytes(path)); } catch (_) {}
  return null;
}
async function _lrOpen(path, raw) {
  try { if (typeof SandpieFileViewer !== 'undefined' && _LR_PATHISH.test(path)) SandpieFileViewer.open(path); } catch (_) {}
}
function hydrateLocalRefs(root) {
  if (!root || !root.querySelectorAll) return;
  for (const img of root.querySelectorAll('img[src]')) {
    if (img.dataset.lrDone) continue;
    const raw = img.getAttribute('src') || '';
    if (/^(https?:|data:|blob:)/i.test(raw)) { img.dataset.lrDone = '1'; continue; }
    const path = _lrNorm(raw);
    if (!_LR_PATHISH.test(path) || !_LR_IMG_MIME[path.split('.').pop().toLowerCase()]) { img.dataset.lrDone = '1'; continue; }
    img.dataset.lrDone = '1';
    img.style.maxWidth = 'min(320px, 100%)';
    img.style.maxHeight = '240px';
    _lrBlobUrl(path, raw).then(u => {
      if (u) {
        img.src = u; img.title = path; img.style.cursor = 'pointer';
        img.onclick = () => _lrOpen(path, raw);
      } else {
        img.alt = '(image not found: ' + path + ')';
      }
    });
  }
  for (const el of root.querySelectorAll('a[href], code')) {
    if (el.dataset.lrDone) continue;
    const isA = el.tagName === 'A';
    if (!isA && el.parentElement && el.parentElement.tagName === 'PRE') continue;   // fenced blocks: leave alone
    const raw = isA ? (el.getAttribute('href') || '') : (el.textContent || '');
    if (isA && /^(https?:|mailto:|data:|blob:|#)/i.test(raw)) { el.dataset.lrDone = '1'; continue; }
    if (!_LR_PATHISH.test(_lrNorm(raw))) { if (isA) el.dataset.lrDone = '1'; continue; }
    el.dataset.lrDone = '1';
    el.classList.add('lr-file');
    el.title = 'Open ' + _lrNorm(raw);
    // Resolve the path AT CLICK TIME — a code span painted mid-stream may still
    // be growing when this handler is attached.
    el.addEventListener('click', (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      const rawNow = isA ? (el.getAttribute('href') || '') : (el.textContent || '');
      _lrOpen(_lrNorm(rawNow), rawNow);
    });
  }
}
/* ---- selection-triggered toolbar on user bubbles ------------------------ */
function getSelectionTextIn(el) {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return '';
  const r = sel.getRangeAt(0);
  if (el.contains(r.commonAncestorContainer)) return sel.toString();
  return '';
}
function hideUserSelToolbar(acts) {
  acts.classList.remove('show');
  const sel = window.getSelection();
  if (sel && sel.rangeCount && acts.parentNode && acts.parentNode.contains(sel.getRangeAt(0).commonAncestorContainer)) sel.removeAllRanges();
}
function rewindToUserMessage(div) {
  // Rewind so THIS user message is the last one kept: drop everything after
  // it (its own assistant reply included) and restore its text in the
  // composer — the same end state as ">>> rewind N" from the bottom.
  const s = activeStream();
  if (!s || !messages.length) return;
  const host = div.closest('.conv-host') || s.host;
  if (!host || !host.contains(div)) return;
  let idx = -1, seen = 0;
  const hostDivs = [...host.querySelectorAll(':scope > .msg.user')];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role !== 'user') continue;
    if (hostDivs[hostDivs.length - 1 - seen] === div) { idx = i; break; }
    seen++;
  }
  if (idx < 0) return;
  const m = messages[idx];
  let txt = '';
  if (typeof m.content === 'string') txt = m.content;
  else if (Array.isArray(m.content)) txt = m.content
    .filter(p => p && p.type === 'text' && p.text).map(p => p.text).join('\n');
  const removed = messages.length - idx;
  if (!confirm(`Remove the last ${removed} message(s)?`)) return;
  if (s.abort) s.abort.abort();
  messages.length = idx;
  if (s.compaction && idx <= s.compaction.boundary) s.compaction = null;
  clearActiveConvUI();
  renderConversation(messages, s.compaction);
  const messagesEl = paneScrollEl($('messages'));
  if (messagesEl && shouldAutoScroll(messagesEl)) messagesEl.scrollTop = messagesEl.scrollHeight;
  saveActiveConv().catch(() => {});
  if (txt.trim()) {
    const ta = (s.host && s.host.parentNode === $('messagesSide')) ? $('inputSide') : $('input');
    if (ta) {
      ta.value = txt.trim();
      ta.style.height = 'auto';
      ta.style.height = ta.scrollHeight + 'px';
      ta.focus();
    }
  }
}
document.addEventListener('selectionchange', () => {
  const sel = window.getSelection();
  // Only HIDE when a real (non-collapsed) selection exists somewhere else —
  // a collapsed selection must never close a toolbar that a tap/click opened
  // (this was breaking mobile: the tap's selection collapse fired
  // selectionchange and instantly hid the just-opened toolbar).
  document.querySelectorAll('.msg.user > .msg-actions.show').forEach(acts => {
    const bubble = acts.parentNode.querySelector(':scope > .bubble');
    if (!bubble) { acts.classList.remove('show'); return; }
    if (sel && sel.rangeCount && !sel.isCollapsed && !bubble.contains(sel.getRangeAt(0).commonAncestorContainer)) acts.classList.remove('show');
  });
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
  const node = sel.getRangeAt(0).commonAncestorContainer;
  const bubble = (node.nodeType === 1 ? node : node.parentNode)?.closest?.('.msg.user > .bubble');
  if (!bubble) return;
  const acts = bubble.parentNode.querySelector(':scope > .msg-actions');
  if (acts) acts.classList.add('show');
});

// Click/tap-to-open: a plain click (no text selection) on a message toggles
// its toolbar, so the actions are reachable without selecting text (this is
// the primary path on touch devices, where there is no hover). Only one
// toolbar is open at a time; clicking anywhere else closes it. A click that
// ends a drag-selection is ignored — selectionchange already handled it.
document.addEventListener('click', (e) => {
  if (e.target.closest?.('.msg-actions')) return;
  const msg = e.target.closest?.('.msg.user');
  const openActs = document.querySelectorAll('.msg.user > .msg-actions.show');
  if (!msg) {
    openActs.forEach(a => a.classList.remove('show'));
    return;
  }
  const sel = window.getSelection();
  if (sel && sel.rangeCount && !sel.isCollapsed && msg.contains(sel.getRangeAt(0).commonAncestorContainer)) return;
  const acts = msg.querySelector(':scope > .msg-actions');
  if (!acts) return;
  const wasOpen = acts.classList.contains('show');
  openActs.forEach(a => a.classList.remove('show'));
  if (!wasOpen) acts.classList.add('show');
});

function renderHistoricalMessage(m, host = null) {
  // STRICT parentage (2026-09-13 follow-up): every caller passes a real host
  // (a conv-host or a detached fragment). A null host used to fall back to the
  // MAIN pane's mounted conversation, so a background conv's replayed history —
  // including its show_artifact cards — spawned inside whatever conv was on
  // screen. Refuse to render without an explicit host instead of misrouting.
  if (!host) return;
  if (m.role === 'user') {
    if (m._loadedImage) return;   // model-only image (load_image); shown in its tool-call box, not as a bubble
    bindBubble(addMsg('user', m.content, host), m);
  } else if (m.role === 'assistant') {
    const contentStr = typeof m.content === 'string' ? m.content :
      m.content.filter(p => p.type === 'text').map(p => p.text).join('');
    if (contentStr && contentStr.trim()) {
      const div = addMsg('assistant', '', host);
      // Render INTO the bubble span addMsg left empty, so the hover copy
      // strip it appended stays a sibling — historical and live replies
      // keep the same DOM shape (.bubble + .msg-actions).
      const bub = div.querySelector(':scope > .bubble') || div;
      bub.innerHTML = renderMd(contentStr);
      hydrateLocalRefs(div);
      bindBubble(div, m);
    }
    // Saved reasoning (chain of thought) — cloud tool-call turns persist it as
    // m.reasoning. Render it as a collapsed thinking block matching the live
    // <details class="msg think"> shape, so a reloaded conversation reads the
    // same as it streamed.
    if (m.reasoning && m.reasoning.trim()) {
      const det = document.createElement('details');
      det.className = 'msg think done';
      det.open = false;
      const sum = document.createElement('summary');
      sum.textContent = 'Thought';
      const body = document.createElement('div');
      body.className = 'think-body';
      body.textContent = m.reasoning;
      det.append(sum, body);
      appendContent(host || (activeStream() && activeStream().host) || paneScrollEl($('messages')), det);
    }
    if (m.tool_calls) {
      for (const tc of m.tool_calls) {
        if (tc.function.name === 'show_artifact') {
          // Defer to the tool RESULT (below) — same contract as the live path,
          // which renders only on the 'artifact:' sentinel. Rendering from the
          // call's args here made a BLOCKED show_artifact (plan-first gate)
          // appear on reload despite never showing live.
          try {
            const { path } = JSON.parse(tc.function.arguments || '{}');
            if (path && tc.id) _histArtifacts.set(tc.id, path);
          } catch (_) {}
        } else if (tc.function.name === 'respond') {
          /* respond(): its text is rendered as the assistant reply bubble from
             m.content above — never as a tool box. */
        } else {
          const tcDiv = addMsg('tool-call', '', host);
          tcDiv.dataset.fname = tc.function.name;
          tcDiv.dataset.tcId = tc.id;
          const box = buildToolBox(tc.function.arguments || '{}', tc.function.name);
          const expanded = tcDiv.querySelector('.tc-expanded');
          if (expanded) {
            expanded.innerHTML = '';
            expanded.appendChild(box);
          }
          renderTcDone(tcDiv, tc.function.name, tc.function.arguments);
          bindBubble(tcDiv, m);
        }
      }
    }
  } else if (m.role === 'tool') {
    const content = String(m.content || '');
    // respond()'s tool ack carries no user-visible output (the reply was rendered
    // from the assistant content) — skip it so it doesn't staple onto another box.
    if (content === '[respond delivered]') return;
    const target = host || paneScrollEl($('messages'));
    // show_artifact settles here, exactly like live: render only when the call
    // actually succeeded (a 'Blocked:' result renders nothing).
    if (m.tool_call_id && _histArtifacts.has(m.tool_call_id)) {
      const apath = _histArtifacts.get(m.tool_call_id);
      _histArtifacts.delete(m.tool_call_id);
      if (!content.replace(/^\[r\d+\]\s*/, '').startsWith('Blocked:')) {
        const existing = target.querySelector && target.querySelector('.artifact-wrap[data-artifact-path="' + apath + '"]');
        if (!existing) renderArtifact(host, apath);
      }
      return;
    }
    const toolCalls = target.querySelectorAll('.msg.tool-call');
    // Attach this result to ITS OWN tool call, matched by tool_call_id. The old
    // code matched positionally to the LAST rendered box, so in a turn with
    // several tool calls every result but the last landed on the wrong box (and
    // overwrote it) — e.g. multi-call agent turns like the sandpie_ssh skill,
    // where all but the final call then showed no output. Fall back to the last
    // box only when the id is missing/unmatched (older saved data).
    let tcId = m.tool_call_id || '';
    if (tcId) {
      let ok = false;
      for (const div of toolCalls) if (div.dataset.tcId === tcId) { ok = true; break; }
      if (!ok) tcId = '';
    }
    if (!tcId && toolCalls.length > 0) tcId = toolCalls[toolCalls.length - 1].dataset.tcId;
    // Sentinel checks ignore the citable result-id tag ("[rN] ") the worker
    // prepends to tool results — it lands BEFORE "artifact:"/"image:".
    const sent = content.replace(/^\[r\d+\]\s*/, '');
    if (tcId) {
      if (sent.startsWith('image:')) {
        // Path = everything after 'image:' up to the first newline — caption
        // branches append the caption on following lines after the bare path.
        const path = sent.slice('image:'.length).split('\n')[0].trim();
        if (path) appendToolResultImage(tcId, path, target);
      } else if (sent.startsWith('todos:')) {
        const nl = sent.indexOf('\n');
        const json = sent.slice('todos:'.length, nl < 0 ? undefined : nl);
        let todos = null;
        try { todos = JSON.parse(json); } catch (_) {}
        // Fallback: the persisted 'todos:' JSON may be missing/truncated (a torn
        // JSONL read mid-append, or a pre-fix result cut past 30kB). Render the
        // conversation's restored checklist (meta.todos -> stream.todos) instead
        // of an empty box; resolve from the host's own convId so a side-panel /
        // background load never staples the ACTIVE conv's checklist on.
        if (!(todos && todos.length)) {
          const s = convStreams.get(target && target.dataset ? target.dataset.convId : '');
          if (s && Array.isArray(s.todos) && s.todos.length) todos = s.todos;
        }
        const box = _toolBoxEl(tcId, target);
        if (todos) {
          if (box) { renderTodos(tcId, todos, target); }
          else { target.appendChild(buildTodosView(todos)); }
          tgOnTodos(target, todos);
        }
      } else if (sent.startsWith('answers:')) {
        // Tool result: answered questions. The box already shows the human-readable
        // summary (markToolDone for live turns); here we REMOVE the standalone
        // question card and, for historical replays (no markToolDone), render the
        // summary into the box.
        const nl = sent.indexOf('\n');
        const json = sent.slice('answers:'.length, nl < 0 ? undefined : nl);
        let answers = null;
        try { answers = JSON.parse(json); } catch (_) {}
        const card = target.querySelector('.ask-card[data-ask-tc-id="' + tcId + '"]') || target.querySelector('.ask-card');
        if (card) card.remove();
        if (Array.isArray(answers) && answers.length) renderAnswers(tcId, answers, target);
        else appendToolResult(tcId, content, target);
      } else if (!sent.startsWith('artifact:')) {
        // Full result, untruncated — the user sees exactly what the model sees.
        appendToolResult(tcId, content, target);
      }
    }
  }
}
// Render a whole conversation into `host` (default: the active stream's host),
// honouring compaction: messages before the boundary are NOT sent to the model —
// they render collapsed behind a toggle, with the summary that's sent in their
// place — and messages from the boundary on render normally (in context).
// After a reload or an aborted turn, an ask() that was never answered leaves a
// dangling empty tool-box (the worker died, the card is gone). Mark those boxes
// with a stale notice so the conversation doesn't look broken, and disable any
// live question card that survived an abort (its worker round-trip is dead).
// Detect an unanswered ask() at the END of a conversation: the newest assistant
// message's last tool call is 'ask' and no tool result followed it. Walks back
// past trailing user messages (a steer typed while the question was pending),
// stops at the first tool result (already answered) or a final assistant text
// (turn completed). The questions come from the tool call's own arguments.
function findPendingAsk(msgs) {
  if (!Array.isArray(msgs) || !msgs.length) return null;
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (!m || typeof m !== 'object') continue;
    if (m.role === 'tool') return null;                        // answered already
    if (m.role === 'user') continue;                           // steer typed while pending
    if (m.role === 'assistant' && Array.isArray(m.tool_calls) && m.tool_calls.length) {
      const last = m.tool_calls[m.tool_calls.length - 1];
      if (last && last.function && last.function.name === 'ask') {
        let questions = null;
        try { questions = JSON.parse(last.function.arguments || '{}').questions; } catch (_) {}
        if (Array.isArray(questions) && questions.length) return { tcId: last.id || '', questions };
      }
      return null;                                             // last tool call wasn't ask
    }
    if (m.role === 'assistant') return null;                   // final text → turn done
  }
  return null;
}

// Answer a question whose original turn died (reload / abort): append the tool
// result to the conversation, persist + render it into the ask box, then RESUME
// the agent loop — the model sees a complete exchange and continues the work.
async function resolveStoredAsk(convId, tcId, answers) {
  if (!convId || !tcId) return;
  const s = ensureStream(convId);
  const toolMsg = { role: 'tool', tool_call_id: tcId, content: 'answers:' + JSON.stringify(answers) };
  s.messages.push(toolMsg);
  await saveConv(convId);
  // Render the result into the DOM (the worker won't re-emit this synthetic
  // message): renderHistoricalMessage's 'answers:' branch removes the card and
  // draws the Q → A summary into the ask box.
  renderHistoricalMessage(toolMsg, s.host);
  _askingConvs.delete(convId);
  refreshConversationList();
  await sendSingle('', s, { resume: true });
}

// Fallback ONLY for genuinely unrecoverable asks (no detectable pending tool_call
// and no card): label the empty box. Surviving cards are re-wired to
// resolveStoredAsk instead of being disabled.
function markStaleAsks(host) {
  const root = host || document;
  for (const box of root.querySelectorAll('.msg.tool-call')) {
    if ((box.dataset.fname || '') !== 'ask') continue;
    const inner = box.querySelector('.tool-box');
    if (!inner) continue;
    if (inner.querySelector('.ask-answered, .tool-result')) continue;   // has a result
    if (root.querySelector('.ask-card')) continue;                       // card still live
    if (inner.querySelector('.ask-stale')) continue;
    const stale = document.createElement('div');
    stale.className = 'ask-stale';
    stale.textContent = '\u2753 Pregunta no respondida \u2014 la generaci\u00f3n se interrumpi\u00f3.';
    inner.appendChild(stale);
  }
}

function renderConversation(msgs, compaction, host = null) {
  // Fresh replay: drop any Task Register state left from a previous render of
  // this target — groups AND the replayed-todos snapshot that titles them.
  const rhost = _tgResolveTarget(host);
  tgReset(rhost);
  // A full replay must start from a CLEAN host. Every caller is a
  // load/rewind/compaction replay of the whole message list, but some reach
  // here racing another load of the same conversation (boot-restore vs a
  // sidebar click, side-pane open vs loadConv) — appending onto the earlier
  // render showed the conversation twice. Only conv hosts are wiped, and the
  // home lists are evacuated first (they can live inside the main-pane host).
  if (rhost && rhost.dataset && rhost.dataset.convId && rhost.firstChild) {
    _evacuateHome(rhost);
    rhost.innerHTML = '';
    // _evacuateHome APPENDS the home lists to the pane (below the host); re-tuck
    // them as the host's first child now so they sit above the replayed messages,
    // not stranded at the bottom of the conversation.
    _placeHome();
  }
  const comp = (compaction && compaction.boundary > 0 && compaction.boundary < msgs.length) ? compaction : null;
  if (!comp) { for (const m of msgs) renderHistoricalMessage(m, host); }
  else { renderCompactionBlock(comp, msgs, host); for (let i = comp.boundary; i < msgs.length; i++) renderHistoricalMessage(msgs[i], host); }
  // If the stream carries saved todos that never attached to a tool-call box
  // (orphaned by tcId mismatch on replay), append them as a standalone card.
  // Resolve the stream from the conversation being RENDERED (its host carries
  // dataset.convId), not activeStream() — otherwise rendering a non-active conv
  // (side panel, or mid-switch) staples the active conv's checklist onto it.
  const target = host || (activeStream() && activeStream().host) || paneScrollEl($('messages'));
  const s = convStreams.get(target && target.dataset && target.dataset.convId) || activeStream();
  // Persistent pending question: if the newest exchange is an unanswered ask()
  // tool call (survived a reload/abort), re-render the LIVE card so the user can
  // answer hours later. Only when it's unrecoverable does markStaleAsks label
  // the empty box.
  const targetConvId = (target && target.dataset && target.dataset.convId) || (s && s.id) || '';
  const pending = findPendingAsk(s ? s.messages : msgs);
  if (pending && pending.tcId && targetConvId) {
    _askingConvs.add(targetConvId);   // open-then-badge: '?' in the sidebar for this conv
    if (!target.querySelector('.ask-card[data-ask-tc-id="' + pending.tcId + '"]')) {
      renderQuestions(pending.tcId, pending.questions, (result) => {
        let answers = [];
        try { answers = JSON.parse(String(result || '').replace(/^answers:/, '')); } catch (_) {}
        resolveStoredAsk(targetConvId, pending.tcId, answers);
      }, targetConvId);
    }
  } else {
    markStaleAsks(target);
  }
  // Touched-files cards (replaces show_artifact): re-render the conversation's
  // deduped file list at the bottom — newest last, .html/images expanded, the
  // rest collapsed clickable cards. Cards rendered from legacy persisted
  // 'artifact:' results earlier in the replay are deduped away here.
  if (s && Array.isArray(s.filesTouched) && s.filesTouched.length) {
    try { renderFilesTouched(target, s.filesTouched); } catch (_) {}
  }
  // A caller that wiped the host (clearActiveConvUI — rewind / compaction
  // re-render) destroyed the settled .msg-timer line, and nothing re-creates it:
  // endTotalTimer only fixes the DOM while the tick interval is alive, then nulls
  // stream.timerEl. But the data that built it (timerStart, lastUsage, todos)
  // survives on the stream, so rebuild the ~same .done line here. Skip when a
  // timer already exists (live or settled) — it's only ever needed after a wipe.
  rebuildSettledTimer(target, s);
}

// ── Touched-files surfacing (replaces show_artifact) ───────────────────────
// The worker emits 'files_touched' at turn end: every file the turn wrote,
// deduped, oldest-first. One artifact card per file; only .html and images
// auto-expand inline, everything else starts as the collapsed clickable card.
// Conversation-wide dedupe: a re-touched file's old card is removed and the
// fresh one lands at the bottom (most recently edited last).
const FT_AUTO_EXPAND = new Set(['html', 'htm', 'svg', 'png', 'jpg', 'jpeg', 'gif', 'webp']);
// Files that stay as their own artifact card — the "interesting" deliverables:
// HTML + images auto-expand inline, office/docs render as a collapsed card.
// EVERYTHING ELSE (code, data, csv, json, logs, …) folds into ONE shared bundle
// card (renderFileBundle), from the very first file — see _ftIndividual.
const FT_OFFICE = new Set(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'rtf']);
const _ftIndividual = ext => FT_AUTO_EXPAND.has(ext) || FT_OFFICE.has(ext);
// Human-readable label for a bundled file's extension in the bundle's type line.
const _CODE_FILE_LABELS = {
  py: 'Python', js: 'JavaScript', mjs: 'JavaScript', cjs: 'JavaScript',
  ts: 'TypeScript', tsx: 'TypeScript', jsx: 'JavaScript',
  json: 'JSON', jsonl: 'JSONL', md: 'Markdown', markdown: 'Markdown',
  txt: 'text', csv: 'CSV', tsv: 'TSV', yaml: 'YAML', yml: 'YAML',
  toml: 'TOML', ini: 'INI', cfg: 'config', sh: 'shell', bash: 'shell',
  zsh: 'shell', ps1: 'PowerShell', bat: 'batch', css: 'CSS', scss: 'SCSS',
  less: 'LESS', xml: 'XML', c: 'C', h: 'C header', cpp: 'C++', cc: 'C++',
  hpp: 'C++ header', rs: 'Rust', go: 'Go', java: 'Java', rb: 'Ruby',
  php: 'PHP', lua: 'Lua', sql: 'SQL', r: 'R',
  gz: 'gzip', zip: 'zip', tar: 'tar', parquet: 'Parquet', log: 'log',
  bin: 'binary', npy: 'NumPy', npz: 'NumPy', pkl: 'pickle', pickle: 'pickle',
  ipynb: 'notebook', xml2: 'XML',
};
function _codeFileLabel(ext) {
  const e = String(ext || '').toLowerCase();
  return _CODE_FILE_LABELS[e] || (e ? e.toUpperCase() + ' file' : 'file');
}
function mergeFilesTouched(stream, files) {
  if (!stream || !Array.isArray(files) || !files.length) return [];
  const cur = new Map((stream.filesTouched || []).map(f => [f.path, f.ts || 0]));
  for (const f of files) { if (f && f.path) cur.set(f.path, f.ts || Date.now()); }
  stream.filesTouched = [...cur.entries()].sort((a, b) => a[1] - b[1]).map(([path, ts]) => ({ path, ts }));
  return files;
}
// ── Artifact thumbnail provider ────────────────────────────────────────────
// Captured HTML previews cached in the CONVERSATION metadata (stream.artifactThumbs
// → meta.artifactThumbs), keyed by path and file size so a byte change misses and
// re-captures. artifacts.js cards call SandpieArtifactThumbs.hydrate(img, path);
// images/SVG never reach here (they point straight at the file). Captures are
// serialized (one offscreen render at a time) and a debounced meta save persists
// them so they survive reload + sync with the conversation.
const _thumbNorm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '').replace(/^sandpie\//, '');
let _thumbQueue = Promise.resolve();
function _enqueueThumbCapture(fn) { const r = _thumbQueue.then(fn, fn); _thumbQueue = r.catch(() => {}); return r; }
let _thumbSaveT = null;
function _scheduleThumbSave() { clearTimeout(_thumbSaveT); _thumbSaveT = setTimeout(() => { try { saveActiveConv(); } catch (_) {} }, 1500); }
function _downscaleDataUrl(dataUrl, maxW) {
  return new Promise((resolve) => {
    const im = new Image();
    im.onload = () => {
      try {
        const iw = im.naturalWidth || maxW, ih = im.naturalHeight || maxW;
        const scale = Math.min(1, maxW / iw);
        const w = Math.max(1, Math.round(iw * scale)), h = Math.max(1, Math.round(ih * scale));
        const c = document.createElement('canvas'); c.width = w; c.height = h;
        c.getContext('2d').drawImage(im, 0, 0, w, h);
        resolve(c.toDataURL('image/jpeg', 0.72));
      } catch (_) { resolve(dataUrl); }
    };
    im.onerror = () => resolve(dataUrl);
    im.src = dataUrl;
  });
}
window.SandpieArtifactThumbs = {
  async hydrate(img, path) {
    try {
      const stream = activeStream(); if (!stream) return;
      const key = _thumbNorm(path);
      let size = -1;
      try { const rp = window.resolveArtifactPath ? await window.resolveArtifactPath(key) : key; size = await opfs.getFileSize(rp); } catch (_) {}
      const store = stream.artifactThumbs || (stream.artifactThumbs = {});
      const hit = store[key];
      if (hit && hit.d && (size < 0 || hit.s === size)) { window._applyArtifactShot(img, hit.d); return; }
      if (!(window.SandpieScreenshot && window.SandpieScreenshot.capture)) return;
      await _enqueueThumbCapture(async () => {
        const st = activeStream(); const cur = (st && st.artifactThumbs && st.artifactThumbs[key]);
        if (cur && cur.d && (size < 0 || cur.s === size)) { window._applyArtifactShot(img, cur.d); return; }
        let shot = null;
        try { shot = await window.SandpieScreenshot.capture(key, { width: 1200, height: 800, wait_ms: 500, exact_width: true }); } catch (_) {}
        if (shot && shot.dataUrl) {
          const small = await _downscaleDataUrl(shot.dataUrl, 600);
          const s2 = activeStream();
          if (s2) { (s2.artifactThumbs || (s2.artifactThumbs = {}))[key] = { s: size, d: small }; _scheduleThumbSave(); }
          window._applyArtifactShot(img, small);
        }
      });
    } catch (_) {}
  },
  invalidate(path) { try { const st = activeStream(); if (st && st.artifactThumbs) delete st.artifactThumbs[_thumbNorm(path)]; } catch (_) {} },
};

// A file was deleted (delete_file tool or python os.remove): reflect it everywhere
// so nothing 404s — remove its card(s) and drop it from the conversation's tracking
// (filesTouched) + cached thumbnail, persisting affected conversations.
function reflectFileDeletes(paths) {
  if (!Array.isArray(paths) || !paths.length) return;
  const norm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '').replace(/^sandpie\//, '');
  const wants = new Set(paths.map(norm).filter(Boolean));
  if (!wants.size) return;
  const match = (p) => wants.has(norm(p));
  try { if (typeof window.removeArtifactByPath === 'function') window.removeArtifactByPath(paths); } catch (_) {}
  // A deletion changed grid membership — recompute the +N overflow on any grid.
  try { for (const g of document.querySelectorAll('.artifact-grid')) applyGridFolding(g); } catch (_) {}
  try {
    for (const [cid, stream] of convStreams) {
      if (!stream) continue;
      let changed = false;
      if (Array.isArray(stream.filesTouched)) {
        const before = stream.filesTouched.length;
        stream.filesTouched = stream.filesTouched.filter(f => !match(f && f.path));
        if (stream.filesTouched.length !== before) changed = true;
      }
      if (stream.artifactThumbs) {
        for (const k of Object.keys(stream.artifactThumbs)) { if (match(k)) { delete stream.artifactThumbs[k]; changed = true; } }
      }
      if (changed) saveConv(cid, { touchUpdated: false });
    }
  } catch (_) {}
}

// The single "open" per-turn artifact grid in a pane (create if absent, placed
// composer-safe). Closed by clearing data-ft-open at the turn's final emit.
function _ftOpenGrid(target) {
  let g = target.querySelector('.artifact-grid[data-ft-open="1"]');
  if (g) return g;
  g = document.createElement('div');
  g.className = 'artifact-grid';
  g.dataset.ftOpen = '1';
  appendContent(target, g);
  return g;
}

// Overflow cap: a turn that drops a flood of deliverables would otherwise fill the
// transcript with cards. Show the first GRID_CAP and fold the rest behind a "+N"
// tile in the next cell; clicking it expands (and offers "Show less"). State lives
// on grid.dataset.expanded so re-renders/deletes preserve it. Re-run after any
// change to a grid's membership (via applyGridFolding, which stacks images first;
// cards folded into the image stack don't count toward the cap).
const GRID_CAP = 7;
function applyGridOverflow(grid) {
  if (!grid || !grid.isConnected) return;
  const cards = [...grid.querySelectorAll(':scope > .artifact-wrap:not(.ac-stacked)')];
  let more = grid.querySelector(':scope > .ac-more');
  const expanded = grid.dataset.expanded === '1';
  const overflow = cards.length > GRID_CAP;
  cards.forEach((c, i) => c.classList.toggle('ac-hidden', overflow && !expanded && i >= GRID_CAP));
  if (!overflow) { if (more) more.remove(); return; }
  if (!more) {
    more = document.createElement('div');
    more.className = 'ac-more';
    more.tabIndex = 0;
    more.setAttribute('role', 'button');
    more.addEventListener('click', () => {
      grid.dataset.expanded = grid.dataset.expanded === '1' ? '' : '1';
      applyGridOverflow(grid);
    });
    more.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); more.click(); } });
  }
  grid.appendChild(more);   // always the last cell (after the visible cards)
  const hidden = cards.length - GRID_CAP;
  more.innerHTML = expanded
    ? '<span class="ac-more-n">‹</span><span class="ac-more-lbl">Show less</span>'
    : '<span class="ac-more-n">+' + hidden + '</span><span class="ac-more-lbl">more</span>';
  more.title = expanded ? 'Show fewer' : hidden + ' more file' + (hidden !== 1 ? 's' : '');
}
// Image stack: a turn (or a replayed conversation) that wrote a pile of images —
// screenshots, crops, probes — used to put one auto-expanded card per image in
// the grid, so a conversation opened later was mostly visual noise. When a grid
// holds more than two image cards they fold into ONE "N images" tile showing a
// mosaic of the newest four; clicking it unfolds the individual cards (and offers
// "Collapse"). The cards stay in the DOM (class ac-stacked hides them), so the
// re-touch dedupe, delete reflection and side-panel open paths are unchanged.
// State lives on grid.dataset.stackOpen, like the "+N" tile's dataset.expanded.
const IMAGE_STACK_MIN = 3;
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg']);
const _isImageCard = w => IMAGE_EXTS.has(String(w.dataset.artifactPath || '').split('.').pop().toLowerCase());
const IMG_STACK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>';
function applyImageStack(grid) {
  if (!grid || !grid.isConnected) return;
  const imgs = [...grid.querySelectorAll(':scope > .artifact-wrap')].filter(_isImageCard);
  let tile = grid.querySelector(':scope > .ac-stack');
  const open = grid.dataset.stackOpen === '1';
  if (imgs.length < IMAGE_STACK_MIN) {
    imgs.forEach(w => w.classList.remove('ac-stacked'));
    if (tile) tile.remove();
    return;
  }
  imgs.forEach(w => w.classList.toggle('ac-stacked', !open));
  if (!tile) {
    tile = document.createElement('div');
    tile.className = 'ac-stack';
    tile.tabIndex = 0;
    tile.setAttribute('role', 'button');
    tile.innerHTML = '<div class="ac-stack-mosaic"></div>' +
      '<div class="ac-ft"><div class="ac-ic ac-t-img">' + IMG_STACK_SVG + '</div><span class="ac-sub"></span><span class="ac-go">›</span></div>';
    tile.addEventListener('click', () => {
      grid.dataset.stackOpen = grid.dataset.stackOpen === '1' ? '' : '1';
      applyGridFolding(grid);
    });
    tile.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tile.click(); } });
  }
  // The tile sits where the first image card is; the cards follow it when open.
  if (imgs[0].previousElementSibling !== tile) grid.insertBefore(tile, imgs[0]);
  tile.classList.toggle('ac-stack-open', open);
  const n = imgs.length;
  tile.querySelector('.ac-sub').textContent = open ? 'Collapse ' + n + ' images' : n + ' images';
  tile.title = open ? 'Fold the images back into one tile' : 'Show all ' + n + ' images';
  // Mosaic of the newest four — rebuilt only when membership changes.
  const newest = imgs.slice(-4).map(w => w.dataset.artifactPath);
  const mosaic = tile.querySelector('.ac-stack-mosaic');
  const key = newest.join('|') + '#' + n;
  if (mosaic.dataset.key !== key) {
    mosaic.dataset.key = key;
    mosaic.innerHTML = '';
    for (const clean of newest) {
      const cell = document.createElement('div');
      cell.className = 'ac-stack-cell';
      const img = document.createElement('img');
      img.alt = ''; img.hidden = true;
      cell.appendChild(img);
      mosaic.appendChild(cell);
      (async () => {
        try {
          const rp = await resolveArtifactPath(clean);
          const url = (opfs.filesUrlReady && opfs.filesUrlReady()) ? opfs.filesUrl(rp) : await opfs.toUrl(rp);
          if (window._applyArtifactShot) window._applyArtifactShot(img, url);
        } catch (_) {}
      })();
    }
    if (n > 4) {
      const badge = document.createElement('span');
      badge.className = 'ac-stack-n';
      badge.textContent = '+' + (n - 4);
      mosaic.lastElementChild.appendChild(badge);
    }
  }
}
// Every fold a grid needs, in order: images into their stack first, then the
// "+N more" cap over whatever is still individually visible.
function applyGridFolding(grid) {
  applyImageStack(grid);
  applyGridOverflow(grid);
}
function renderFilesTouched(host, files, opts) {
  if (!Array.isArray(files) || !files.length) return;
  const partial = !!(opts && opts.partial);
  // Parentage guard: fall back to the ACTIVE stream's host only when it is the
  // conversation actually mounted on screen — never park cards into a detached
  // host or a pane showing a different conversation (2026-09-13 cross-conv bug).
  const _as = activeStream();
  const target = host || ((_as && _as.host && _streamOwnsPaneSlot(_as)) ? _as.host : null);
  try { const _ch = target && target.closest ? target.closest('.conv-host') : null;
    console.debug('[artifact-trace] renderFilesTouched -> conv',
      (_ch && _ch.dataset.convId) || (target && target.id) || 'null/detached',
      'hostParam=', !!host, JSON.stringify((files||[]).map(f => f && f.path)), new Error().stack); } catch (_) {}
  if (!target) return;
  tgBreak(target);   // file cards end the current tool-group run
  // Individual cards = HTML / images / office (the deliverables). Everything else
  // (code, data, csv, json, logs, …) folds into ONE shared bundle card.
  const bundleFiles = [];
  const individualFiles = [];
  for (const f of files) {
    const clean = String((f && f.path) || '').replace(/^\/+/, '');
    if (!clean) continue;
    const ext = clean.split('.').pop().toLowerCase();
    if (_ftIndividual(ext)) { individualFiles.push(f); }
    else { bundleFiles.push(f); }
  }
  // Render the individual deliverable cards into a per-turn WRAPPING grid: several
  // HTML/image cards flow side by side instead of a tall column. One grid stays
  // "open" across this turn's partial emits; the final (non-partial) emit closes it
  // so the next turn starts fresh. A single card fills the row (auto-fit 1fr).
  let grid = individualFiles.length ? _ftOpenGrid(target) : null;
  for (const f of individualFiles) {
    const clean = String((f && f.path) || '').replace(/^\/+/, '');
    if (!clean) continue;
    const olds = [...target.querySelectorAll('.artifact-wrap')].filter(old => {
      const p = old.dataset && old.dataset.artifactPath;
      return p && (p === clean || p.replace(/^sandpie\//, '') === clean || 'sandpie/' + clean === p);
    });
    if (partial && olds.length) {
      if (typeof window._artifactEnsureHeader === 'function') for (const o of olds) window._artifactEnsureHeader(o);
      continue;
    }
    for (const old of olds) { const g = old.closest('.artifact-grid'); old.remove(); if (g && g !== grid && !g.querySelector('.artifact-wrap')) g.remove(); }
    const ext = clean.split('.').pop().toLowerCase();
    if (!grid) grid = _ftOpenGrid(target);
    try { renderArtifact(grid, clean, { collapsed: !FT_AUTO_EXPAND.has(ext) }); } catch (_) {}
  }
  if (!partial && grid) grid.removeAttribute('data-ft-open');
  if (grid && !grid.querySelector('.artifact-wrap')) grid.remove();
  else if (grid) applyGridFolding(grid);
  // Fold code + data + everything else into ONE shared bundle (from the 1st file).
  // Rebuilt only on the final (non-partial) emit so it doesn't churn mid-turn.
  if (bundleFiles.length) {
    if (partial) return;
    // Dedupe any legacy individual card for a now-bundled path (a pre-bundle
    // conversation that surfaced a data/code file as its own `artifact:` card on
    // replay) so it doesn't double-render alongside its bundle row.
    for (const f of bundleFiles) {
      const clean = String((f && f.path) || '').replace(/^\/+/, '');
      if (!clean) continue;
      for (const old of [...target.querySelectorAll('.artifact-wrap')]) {
        const p = old.dataset && old.dataset.artifactPath;
        if (p && (p === clean || p.replace(/^sandpie\//, '') === clean || 'sandpie/' + clean === p)) old.remove();
      }
    }
    const oldGroup = target.querySelector('.file-bundle');
    if (oldGroup) oldGroup.remove();
    renderFileBundle(target, bundleFiles);
  }
}


// ── Shared file bundle card (Option C: stacked pile + count badge) ──────────────
// Every touched file that ISN'T a standalone deliverable (HTML/images/office) —
// i.e. all code + data + logs + everything else — folds into ONE collapsible
// "N other files" pile, from the first file. Keeps the boring stuff out of the
// transcript while one click reveals the full list (name · size · open).
function renderFileBundle(target, bundleFiles) {
  const count = bundleFiles.length;
  const extMap = {};
  for (const f of bundleFiles) {
    const clean = String((f && f.path) || '').replace(/^\/+/, '');
    const ext = clean.split('.').pop().toLowerCase();
    extMap[ext] = (extMap[ext] || 0) + 1;
  }
  // Distinct human type labels for the subtitle, most-common first, capped at 4.
  const seen = new Set(); const distinct = [];
  for (const [e] of Object.entries(extMap).sort((a, b) => b[1] - a[1])) {
    const label = _codeFileLabel(e);
    if (!seen.has(label)) { seen.add(label); distinct.push(label); }
  }
  let typeLabel = distinct.slice(0, 4).join(', ') + (distinct.length > 4 ? ', +' + (distinct.length - 4) + ' more' : '');
  // Hard cap the rendered label length — long type names (e.g. GIT/OBJECTS hashes) blow out the subtitle
  const TYPE_LABEL_MAX = 60;
  if (typeLabel.length > TYPE_LABEL_MAX) typeLabel = typeLabel.slice(0, TYPE_LABEL_MAX - 1).replace(/[\s,]+$/, '') + '\u2026';
  const badge = count > 99 ? '99+' : String(count);

  const wrap = document.createElement('div');
  wrap.className = 'file-bundle';
  wrap.dataset.fileBundle = '1';

  // Header / toggle — layered pile + count badge, title, size·types, Show all
  const header = document.createElement('div');
  header.className = 'fb-head';
  header.innerHTML =
    '<span class="fb-pile"><b></b><b></b><b><span class="fb-num">' + badge + '</span></b></span>' +
    '<span class="fb-body">' +
      '<span class="fb-title"><b>' + count + ' other file' + (count !== 1 ? 's' : '') + '</b> created or edited</span>' +
      '<span class="fb-sub"><span class="fb-size"></span>' + (typeLabel ? '<span class="fb-types">' + typeLabel + '</span>' : '') + '</span>' +
    '</span>' +
    '<span class="fb-cta"><span class="fb-lbl-hide">Hide</span>' +
      '<span class="fb-chevron"><svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></span>';
  wrap.appendChild(header);

  // File list (hidden by default)
  const list = document.createElement('div');
  list.className = 'fb-list';
  list.style.display = 'none';

  let totalBytes = 0, sizedCount = 0;
  const sizeEl = header.querySelector('.fb-size');
  for (const f of bundleFiles) {
    const clean = String((f && f.path) || '').replace(/^\/+/, '');
    if (!clean) continue;
    const ext = clean.split('.').pop().toLowerCase();
    const name = clean.split('/').pop();
    const labelUC = ext.toUpperCase().slice(0, 4);

    const row = document.createElement('div');
    row.className = 'fb-row';
    row.dataset.artifactPath = clean;
    row.dataset.artifactCreated = String(f && f.ts ? f.ts : Date.now());
    row.innerHTML =
      '<span class="fb-row-icon">' + labelUC + '</span>' +
      '<span class="fb-row-name">' + name + '</span>' +
      '<span class="fb-row-size"></span>' +
      '<button class="fb-row-expand" title="Open">↗</button>';
    list.appendChild(row);

    // Fetch size asynchronously; accumulate into the header total as sizes land.
    (async () => {
      try {
        const { parts, name: fname } = splitPath(await resolveArtifactPath(clean));
        const dir = await opfs.resolveDir(parts);
        const file = await (await dir.getFileHandle(fname)).getFile();
        const szEl = row.querySelector('.fb-row-size');
        if (szEl && file.size > 0) szEl.textContent = formatArtifactBytes(file.size);
        if (file.size > 0) { totalBytes += file.size; sizedCount++; if (sizeEl) sizeEl.textContent = formatArtifactBytes(totalBytes) + ' · '; }
      } catch (_) {}
    })();

    // Open in new tab
    const expandBtn = row.querySelector('.fb-row-expand');
    expandBtn.onclick = async (e) => {
      e.stopPropagation();
      try {
        const resolved = await resolveArtifactPath(clean);
        const bytes = await opfs.readBytes(resolved);
        const url = URL.createObjectURL(new Blob([bytes], { type: 'text/plain' }));
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (_) {}
    };
    // Make row clickable
    row.onclick = (e) => { if (e.target !== expandBtn) expandBtn.click(); };
    row.style.cursor = 'pointer';
  }
  wrap.appendChild(list);

  // Toggle expand/collapse
  header.onclick = () => {
    const open = list.style.display !== 'none';
    list.style.display = open ? 'none' : '';
    wrap.classList.toggle('fb-open', !open);
  };

  appendContent(target, wrap);
}

// ===================== Project selector (UI only) =====================
// A quiet chip at the far right of the msg-timer row, aligned with the
// composer's right edge. UI-only for now: the list is a static stub and the
// selection is kept in-memory (per conversation id) until the backend lands.
// No colors, no search, no keyboard hints - plain names, dashed ghost when
// the conversation has no project.
// Registry-backed (sandpie/config/projects.json via SandpieProjects, the
// projects.js module). Conversations bind by STABLE project id (meta.projectId /
// stream.projectId, providerId pattern) — never by root or name, so renaming or
// re-pointing a project never orphans them.
let _projPanelEl = null;              // singleton picker panel
let _projPanelFor = null;             // convId the panel was opened for
const _projById = (id) => { try { return (window.SandpieProjects && SandpieProjects.byId(id)) || null; } catch { return null; } };
const _projName = (id) => { const p = _projById(id); return p ? p.name : ''; };
// byId() reads projects.js's in-memory cache, which is only filled by an async
// OPFS read (loadRegistry/list) — so before the picker has ever been opened a
// bound project id resolves to nothing and the chip silently reads as the
// default project. Warm the registry once per session; callers repaint when it
// lands. cached() === null is the "never loaded" sentinel (an empty registry
// caches as []).
let _projWarming = null;
function _warmProjRegistry() {
  if (_projWarming) return _projWarming;
  if (!window.SandpieProjects) return null;
  _projWarming = SandpieProjects.loadRegistry().catch((e) => { console.warn('[projects] registry warm failed:', e); return null; });
  return _projWarming;
}

const escHtml = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const escAttr = escHtml;
// Bind/unbind a conversation's project (stable project id). Same contract as the
// provider bridge: convId null → home-state default in localStorage, which new
// chats inherit. touch() refreshes the registry MRU so the picker lists the
// most recently used project first.
function _setProjBinding(convId, projectId) {
  // Placeholder-painted chips carry convId null — resolve to the focused
  // conversation so a pick on an idle/new-chat slot still binds something real.
  if (convId == null || convId === '') convId = activeConvId;
  const id = '' + (convId == null ? '' : convId);
  if (!id) {
    try {
      if (projectId) localStorage.setItem('sandpie-default-project', projectId);
      else localStorage.removeItem('sandpie-default-project');
    } catch (_) {}
    return;
  }
  const s = ensureStream(id);
  s.projectId = projectId || null;
  s._projDirty = true;   // stale-save guard: this tab's explicit pick wins the next _saveConv
  saveConv(id, { touchUpdated: false }).catch(() => {});
  if (projectId && window.SandpieProjects) SandpieProjects.touch(projectId).catch(() => {});
}

function _projChipHtml(convId) {
  if (convId == null || convId === '') convId = activeConvId;
  const s = convStreams.get('' + (convId == null ? '' : convId));
  // No explicit project → the DEFAULT project (the sync workspace root, e.g.
  // "sandpie"). There is no "no project" state anymore.
  const p = (s && s.projectId && _projById(s.projectId)) || (window.SandpieProjects ? SandpieProjects.defaultProject() : null);
  const name = p ? p.name : '';
  return '<span class="mt-proj" title="Project">' + escHtml(name) + '<span class="mt-proj-caret">▾</span></span>';
}
// Append (or refresh) the project chip on a timer slot. The timer row is ONE
// persistent element per pane, rebuilt wholesale by every paint path - so the
// chip is re-stamped after each rebuild instead of being a separate node.
function _paintProjChip(slot, convId) {
  if (!slot) return;
  if (convId == null || convId === '') convId = activeConvId;
  let chip = slot.querySelector('.mt-proj');
  const html = _projChipHtml(convId);
  if (!chip) {
    slot.insertAdjacentHTML('beforeend', html);
    chip = slot.querySelector('.mt-proj');
    if (chip) chip.addEventListener('click', (e) => { e.stopPropagation(); _toggleProjPanel(chip, convId); });
  } else {
    const open = chip.classList.contains('open');
    chip.outerHTML = open ? html.replace('"mt-proj', '"mt-proj open') : html;
    const fresh = slot.querySelector('.mt-proj');
    if (fresh && !fresh._wired) {
      fresh._wired = true;
      fresh.addEventListener('click', (e) => { e.stopPropagation(); _toggleProjPanel(fresh, convId); });
    }
  }
  // This conversation is bound to a project the registry hasn't produced yet:
  // load it once, then repaint with the real name. After the warm, cached() is
  // non-null, so this never loops (an id that is genuinely gone keeps the
  // default-project fallback).
  const s = convStreams.get('' + (convId == null ? '' : convId));
  const pid = s && s.projectId;
  if (pid && !_projById(pid) && window.SandpieProjects && SandpieProjects.cached() === null) {
    const w = _warmProjRegistry();
    if (w) w.then(() => { if (slot.isConnected) _paintProjChip(slot, convId); });
  }
}
function _closeProjPanel() {
  if (_projPanelEl) { _projPanelEl.remove(); _projPanelEl = null; _projPanelFor = null; }
  document.querySelectorAll('.mt-proj.open').forEach(el => el.classList.remove('open'));
}
function _toggleProjPanel(chip, convId) {
  if (convId == null || convId === '') convId = activeConvId;
  if (_projPanelFor === '' + (convId == null ? '' : convId)) { _closeProjPanel(); return; }
  _closeProjPanel();
  const r = chip.getBoundingClientRect();
  const panel = document.createElement('div');
  panel.className = 'proj-panel mp-panel visible';
  panel.innerHTML = '<div class="proj-item" style="opacity:.5"><span class="nm">Loading…</span></div>';
  const s = convStreams.get('' + (convId == null ? '' : convId));
  const current = (s && s.projectId) || '';
  const fill = (reg) => {
    if (_projPanelEl !== panel) return;   // panel was closed/reopened while loading
    let html = '';
    for (const p of reg) {
      const isDefault = p.id === 'default';
      html += '<div class="proj-item' + (p.id === current ? ' sel' : '') + '" data-proj="' + escAttr(p.id) + '" title="' + escAttr(p.root || '') + '">' +
        '<span class="nm">' + escHtml(p.name) + '</span>' +
        (isDefault ? '' : '<button class="proj-del" data-del="' + escAttr(p.id) + '" title="Remove from list">✕</button>') +
        '</div>';
    }
    html += '<div class="proj-add" title="Pick a Dropbox folder"><span class="plus">＋</span> New project</div>';
    panel.innerHTML = html;
  };
  panel.addEventListener('click', async (e) => {
    e.stopPropagation();
    if (e.target.closest('.proj-add')) {
      // Real creation flow (projects.js): Dropbox folder picker → name → registry.
      if (!window.SandpieProjects) { console.warn('[projects] module not loaded'); return; }
      const created = await SandpieProjects.newProjectFlow();
      if (created) {
        _setProjBinding(convId, created.id);
        _closeProjPanel();
        const slot = chip.closest('.msg-timer');
        if (slot) _paintProjChip(slot, convId);
      }
      return;
    }
    const del = e.target.closest('.proj-del');
    if (del) {
      const id = del.dataset.del;
      if (id && id !== 'default' && confirm('Remove this project from the list? (Conversations stay; they fall back to the default project.)')) {
        await SandpieProjects.remove(id);
        const reg = await SandpieProjects.list();
        fill(reg); place();
      }
      return;
    }
    const item = e.target.closest('.proj-item');
    if (!item) return;
    _setProjBinding(convId, item.dataset.proj || '');
    _closeProjPanel();
    const slot = chip.closest('.msg-timer');
    if (slot) _paintProjChip(slot, convId);
  });
  document.body.appendChild(panel);
  // Fixed-position, right-aligned under the chip (escapes the timer row's overflow).
  const place = () => {
    const pw = panel.offsetWidth, ph = panel.offsetHeight;
    let left = r.right - pw;
    left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
    let top = r.bottom + 4;
    if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 4);
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
  };
  place();
  chip.classList.add('open');
  _projPanelEl = panel; _projPanelFor = '' + (convId == null ? '' : convId);
  // Registry is async (OPFS read) — fill when it lands, re-place, and cache for
  // the chip's name lookup.
  (async () => {
    try {
      if (!window.SandpieProjects) { fill([]); place(); return; }
      const reg = await SandpieProjects.list();
      fill(reg); place();
    } catch (e) { console.warn('[projects] registry load failed:', e); fill([]); place(); }
  })();
}
document.addEventListener('click', (e) => {
  if (_projPanelEl && !_projPanelEl.contains(e.target) && !(e.target.closest && e.target.closest('.mt-proj'))) _closeProjPanel();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') _closeProjPanel(); });
// =================== end project selector (UI only) ===================
// Rebuild a settled (.done) msg-timer line into `target` from the stream's
// surviving post-turn data. Mirrors the label/elapsed/[tok/s]/ctx/todos layout
// endTotalTimer builds, minus the "stopped" variant (the label is not persisted
// on the stream, so a rebuilt line reads "done" — the distinction is cosmetic).
// No-op when the stream has no completed turn (timerStart/lastUsage unset) or a
// timer is already mounted.
// The thoughts-toggle button — shared by the live line, the settled line, and the
// placeholder so every timer state carries the same leading icon.
function _timerNnBtn(svg) {
  const nnCls = 'mt-nn' + (svg ? ' tick' : '') + (thoughtsVisible ? ' on' : '');
  const nnTitle = thoughtsVisible ? 'Hide thoughts' : 'Show thoughts';
  return `<button class="${nnCls}" title="${nnTitle}" onclick="toggleThoughts()">${svg || NN_SVG_INLINE}</button>`;
}
// Tick mark shown in place of the ripple icon once a turn settles (done/stopped).
const TICK_SVG_INLINE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>';
// Resting placeholder for a slot with no live/finished turn to show. Mirrors the
// settled timer's shape (nn icon · idle · 0s · – ctx) and dims via .done, so an
// idle conversation shows a real-looking bar — never a bare "· idle ·".
function _fillPlaceholderTimer(slot, convId) {
  if (!slot) return;
  slot.classList.add('done');
  slot.dataset.convId = convId == null ? '' : '' + convId;
  slot.innerHTML =
    _timerNnBtn() +
    '<span class="mt-sep">·</span><span class="mt-time">0s</span>' +
    '<span class="mt-sep">·</span><span class="mt-rate">0 tok/s</span>' +
    '<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>';
  _wireCtxCounter(slot, convId);
  _paintProjChip(slot, convId);
}
// Seed both pane timer slots with the resting placeholder when empty, so the bar
// is present in the DOM from first paint — not only once a conversation mounts.
function _ensureTimerPlaceholders() {
  for (const id of ['msgTimerMain', 'msgTimerSide']) {
    const wrap = document.getElementById(id);
    const slot = wrap && wrap.querySelector('.msg-timer');
    if (slot && !slot.innerHTML.trim()) _fillPlaceholderTimer(slot, null);
  }
}
function rebuildSettledTimer(target, s) {
  if (!s) return;
  const slot = _timerSlotFor(s);
  if (!slot) return;
  // A live turn owns the slot via startTotalTimer's ticking paint — never stamp a
  // settled replica or placeholder over it.
  if (s.generating) return;
  // No finished turn to show (brand-new chat, or a conv that never ran this
  // session) → resting placeholder, not a blank slot.
  if (!s.lastTurn && !(s.timerStart && s.lastUsage)) {
    _fillPlaceholderTimer(slot, s.id);
    return;
  }
  let sec = null, comp = null, label = 'done';
  // Persisted lastTurn is authoritative for a finished turn; timerStart/lastUsage
  // is the warm-stream fallback (its sec would otherwise keep growing post-turn).
  if (s.lastTurn) {
    sec = s.lastTurn.sec;
    comp = s.lastTurn.completionTokens || 0;
    label = s.lastTurn.label || 'done';
  } else {
    sec = (Date.now() - s.timerStart) / 1000;
    const u = s.lastUsage;
    comp = u && typeof u.completion_tokens === 'number' ? u.completion_tokens : 0;
  }
  const rate = (s.lastTurn && s.lastTurn.rate > 0) ? s.lastTurn.rate
    : ((comp > 0 && sec > 0.05) ? comp / sec : 0);
  // Cold rebuild: the live stream's _turnProfile is gone, but the profile was
  // persisted inside lastTurn — restore it so the popup works after a reload.
  if (!s._turnProfile && s.lastTurn && s.lastTurn.profile) s._turnProfile = s.lastTurn.profile;
  const parts = [
    _timerNnBtn(TICK_SVG_INLINE),   // settled: tick mark replaces the ripple icon (still toggles thoughts)
    `<span class="mt-sep">·</span><span class="mt-time">${sec == null ? '–' : fmtElapsed(sec, true)}</span>`,
  ];
  parts.push(`<span class="mt-sep">·</span><span class="mt-rate">${RATE_FMT(rate > 0 ? rate : 0)}</span>`);   // ALWAYS present: 0 tok/s when unknown
  parts.push(`<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>`);   // was dropped with the report-button cleanup: the ring vanished on done/idle
  if (s.todos && s.todos.length) {
    const cur = s.todos.filter(t => t && t.status === 'completed').length;   // completed only — match the checklist card; an active task is not "done"
    parts.push(`<span class="mt-sep">·</span><span class="mt-todos">${cur}/${s.todos.length}</span>`);
  }
  // Fill the persistent per-pane slot (never create a timer element).
  slot.classList.add('done');
  slot.dataset.convId = '' + s.id;
  slot.innerHTML = parts.join('');
  _wireCtxCounter(slot, s.id);
  _paintProjChip(slot, s.id);
  _wireRateClick(slot, s.id);
  if (s.todos && s.todos.length) {
    const badge = slot.querySelector('.mt-todos');
    if (badge) {
      const snapshot = s.todos.slice();
      badge.onclick = () => {
        showCmdPanelForEl(badge, buildTodosView(snapshot), 'Checklist');
      };
    }
  }
}

function renderCompactionBlock(comp, msgs, host) {
  const target = host || (activeStream() && activeStream().host) || paneScrollEl($('messages'));
  const n = comp.boundary;
  const label = (open) => `${open ? '▾' : '▸'} ${n} earlier message${n === 1 ? '' : 's'} — compacted out of the model's context`;
  const wrap = document.createElement('div');
  wrap.className = 'compaction-block';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'compaction-toggle';
  toggle.textContent = label(false);
  const archived = document.createElement('div');
  archived.className = 'compaction-archived';
  for (let i = 0; i < n; i++) renderHistoricalMessage(msgs[i], archived);
  toggle.onclick = () => { const open = wrap.classList.toggle('open'); toggle.textContent = label(open); };
  const sum = document.createElement('div');
  sum.className = 'compaction-summary';
  const lab = document.createElement('div');
  lab.className = 'cs-label';
  lab.textContent = 'Summary sent to the model in place of the above ↓';
  const txt = document.createElement('div');
  txt.className = 'cs-text';
  txt.textContent = comp.summary;
  sum.appendChild(lab);
  sum.appendChild(txt);
  wrap.appendChild(toggle);
  wrap.appendChild(archived);
  wrap.appendChild(sum);
  appendContent(target, wrap);
}

// Migrate the OLD compaction format (a data.compactions[] stack of removed heads,
// with data.messages already spliced down to [summary, …tail]) to the new one
// (data.messages = the FULL conversation + a single data.compaction {boundary,
// summary}). In-memory only; the next saveConv persists the new shape.
function migrateCompactionData(data) {
  if (!data || data.compaction || !Array.isArray(data.compactions) || !data.compactions.length) return data;
  const msgs = Array.isArray(data.messages) ? data.messages : [];
  const isSummary = (m) => m && typeof m.content === 'string' && m.content.startsWith(SP_SUMMARY_MARKER);
  const originals = [];
  for (const c of data.compactions) {
    if (!c || !Array.isArray(c.removed)) continue;
    for (const m of c.removed) if (!isSummary(m)) originals.push(m);
  }
  const headSummary = isSummary(msgs[0]);
  const summary = headSummary ? msgs[0].content.slice(SP_SUMMARY_MARKER.length).replace(/^\s+/, '') : '';
  const tail = headSummary ? msgs.slice(1) : msgs.slice();
  data.messages = [...originals, ...tail];
  data.compaction = summary ? { boundary: originals.length, summary } : null;
  delete data.compactions;
  return data;
}

// ── Duplicate-history repair (runs on every conversation load) ──────────────
// Before the cross-tab writer lock existed, two tabs on the same conversation
// each appended their own stale tail to the JSONL, duplicating whole history
// blocks (ptruyol 2026-08-28: 171 of 446 messages were byte-identical copies,
// 42% of a 260k-token context). Repair in place:
//   1. an assistant message whose tool_call ids ALL appeared earlier is a
//      duplicate by construction (ids are unique per generation);
//   2. a second tool RESULT for an already-answered tool_call_id likewise;
//   3. any run of ≥3 consecutive messages byte-identical to an earlier
//      consecutive window (catches user/plain-assistant blocks — the length
//      floor keeps legitimate small repeats like a user typing "ok" twice).
// compaction.boundary counts messages before the summary cut, so it shifts down
// by the number of drops that fell before it. Returns the number removed; the
// caller persists via _forceJsonlRewrite so the repair sticks on disk.
function repairDuplicateHistory(msgs, compaction) {
  if (!Array.isArray(msgs) || msgs.length < 4) return 0;
  let keys;
  try { keys = msgs.map((m) => JSON.stringify(m)); } catch (_) { return 0; }
  const drop = new Array(msgs.length).fill(false);

  // 1 + 2: tool-call-id based (sharpest signal, catches single duplicated rounds)
  const seenCallIds = new Set(), seenResultIds = new Set();
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    if (m && m.role === 'assistant' && Array.isArray(m.tool_calls) && m.tool_calls.length) {
      const ids = m.tool_calls.map((tc) => tc && tc.id).filter(Boolean);
      if (ids.length && ids.every((id) => seenCallIds.has(id))) { drop[i] = true; continue; }
      for (const id of ids) seenCallIds.add(id);
    } else if (m && m.role === 'tool' && m.tool_call_id) {
      if (seenResultIds.has(m.tool_call_id)) { drop[i] = true; continue; }
      seenResultIds.add(m.tool_call_id);
    }
  }

  // 3: consecutive runs identical to an earlier window
  const firstAt = new Map();
  for (let i = 0; i < msgs.length; i++) {
    if (drop[i]) continue;
    const k = keys[i];
    if (!firstAt.has(k)) { firstAt.set(k, i); continue; }
    const j = firstAt.get(k);
    let len = 0;
    while (i + len < msgs.length && j + len < i && keys[i + len] === keys[j + len]) len++;
    if (len >= 3) { for (let d = 0; d < len; d++) drop[i + d] = true; i += len - 1; }
  }

  let removed = 0, beforeBoundary = 0;
  const boundary = (compaction && typeof compaction.boundary === 'number') ? compaction.boundary : -1;
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (!drop[i]) continue;
    msgs.splice(i, 1); removed++;
    if (boundary >= 0 && i < boundary) beforeBoundary++;
  }
  if (removed && boundary >= 0) compaction.boundary = Math.max(0, boundary - beforeBoundary);
  return removed;
}

// Load a conversation file's messages + compaction state onto a stream (with
// migration). Used by every load path so compaction always survives a reload.
function hydrateStreamFromData(s, data) {
  migrateCompactionData(data);
  s.messages = (data.messages || []).slice();
  s.compaction = data.compaction || null;
  s.todos = data.todos || null;
  s.scratchpad = data.scratchpad || '';
  s.filesTouched = data.filesTouched || null;
  s.artifactThumbs = data.artifactThumbs || null;
  s.lastTurn = data.lastTurn || null;
  if ('projectRoot' in data) s.projectRoot = data.projectRoot || null;
  if ('projectNs' in data) s.projectNs = data.projectNs || null;
  // Messages loaded from the new JSONL are already persisted; those from a legacy
  // .json are NOT in a .jsonl yet (persistedCount 0 → first save migrates them).
  s.persistedCount = (data && data._format === 'new') ? s.messages.length : 0;
  s._forceJsonlRewrite = false;
  // Repair duplicated history blocks (see repairDuplicateHistory). Force a full
  // JSONL rewrite on the next save so the repaired shape is what's on disk.
  const removed = repairDuplicateHistory(s.messages, s.compaction);
  if (removed) {
    console.warn('[sandpie] repaired conversation', s.id, '— removed', removed, 'duplicated messages');
    s.persistedCount = s.messages.length;
    s._forceJsonlRewrite = true;
  }
}

function clearActiveConvUI() {

  const s = activeStream();
  if (s && s.host) s.host.innerHTML = '';
}
function parkActiveConv() {
  const s = activeStream();
  if (!s) return;
  s.messages = messages;
  if (s.host && s.host.parentNode) {
    // The parked host may carry the home lists — get them out BEFORE detaching it.
    _evacuateHome(s.host);
    s.host.parentNode.removeChild(s.host);
    _placeHome();
  }
}
// Unmount whatever conversation a pane is showing, saving its messages first.
// Used by "+ New chat", which must clear the MAIN pane specifically rather than
// "the focused conversation" — the latter would unmount a docked side panel conv.
function parkPaneConv(pane) {
  const id = paneConvId(pane);
  if (!id) return;
  const s = convStreams.get(id);
  if (!s) return;
  if (id === activeConvId) s.messages = messages;
  if (s.host && s.host.parentNode) {
    _evacuateHome(s.host);
    s.host.parentNode.removeChild(s.host);
    _placeHome();
  }
  // Detach the parked conversation from the pane's timer slot. Without this, a
  // still-generating stream keeps stream.timerEl + its _tickTimer interval alive
  // and re-claims the shared slot on its next tick — painting the OLD conv's
  // tok/s and ctx ring into the NEW chat's bar (2026-09-12 bug). Nulling
  // timerEl makes the tick's _streamViewed/paint guards skip, and endTotalTimer
  // already handles timerEl == null (persists lastTurn, skips painting);
  // rebuildSettledTimer repaints the settled line when the conv is re-opened.
  s.timerEl = null;
  const slot = pane.querySelector(':scope > .msg-timer-slot .msg-timer');
  if (slot && slot.dataset.convId === '' + id) _fillPlaceholderTimer(slot, null);
}
function mountConv(convId, pane = null) {
  // Conversation switch: blank a stale timer only in the pane being mounted —
  // never the other pane's slot, which may still hold a live side-pane conv.
  const mountTarget = convId ? (pane || (sidePanel ? sidePanel.activeMountTarget() : document.getElementById('messages'))) : null;
  const isSide = !!(mountTarget && mountTarget.id === 'messagesSide');
  const slotId = isSide ? 'msgTimerSide' : 'msgTimerMain';
  if (convId !== activeConvId) {
    const wrap = document.getElementById(slotId);
    const t = wrap && wrap.querySelector('.msg-timer');
    if (t && t.dataset.convId && t.dataset.convId !== '' + convId) {
      t.innerHTML = '';
      t.classList.remove('done');
      delete t.dataset.convId;
    }
  }
  activeConvId = convId;
  if (convId) {
    _loadLiteFlag(convId).catch(() => {});   // preload lite flag for the next turn
    localStorage.setItem('sandpie-active-conv', convId);
    const s = ensureStream(convId);
    messages = s.messages;
    // Claim (or learn we can't claim) writership now, so the read-only notice
    // shows on open rather than only when a send bounces. Fire-and-forget —
    // mountConv must stay synchronous for the instant panel switch.
    acquireConvWriterLock(convId).then((ok) => {
      s.readOnlyViewer = !ok;
      if (!ok) _notifyReadOnlyConv(s);
    }).catch(() => {});

    const target = pane || (sidePanel ? sidePanel.activeMountTarget() : $('messages'));
    if (s.host.parentNode !== target) _mountInPane(s.host, target);
    // Sync the pane's timer slot to the conversation now on screen: re-attach the
    // live ticking timer if it is still generating (so switching back restores the
    // running timer instead of a blank/placeholder bar), otherwise paint its
    // settled line or the resting placeholder.
    if (s.generating && typeof s._tickTimer === 'function') s._tickTimer();
    else rebuildSettledTimer(target, s);
  } else {
    localStorage.removeItem('sandpie-active-conv');
    messages = [];
    // No conversation mounted (home) → reset the main pane's timer bar to the
    // resting placeholder rather than leaving a stale conversation's line.
    const mainSlot = document.querySelector('#msgTimerMain .msg-timer');
    if (mainSlot) _fillPlaceholderTimer(mainSlot, null);
  }
  refreshSendButtonForActive();
  if (typeof SandpieTokens !== 'undefined') SandpieTokens.notify();
  // PER-CONVERSATION provider: tag the pane's model-picker host with the conv now
  // mounted (providers.js reads data-conv-id to resolve + set that conv's model)
  // and repaint both pickers so each shows its own conversation's model.
  try {
    const mpHost = document.getElementById(isSide ? 'modelPickerSide' : 'modelPicker');
    if (mpHost) mpHost.dataset.convId = convId || '';
    if (window.SandpieProviders && SandpieProviders.refreshPickers) SandpieProviders.refreshPickers();
  } catch (_) {}
}
/* ---- harness-reminder note visibility (drift / no-plan / stop guard) ----- */
// The agentic loop emits `reminder` events when its guards fire. They are never
// stored or sent; this just controls whether they're drawn in the transcript.
// Hidden by default (debug-only); toggle with the `>>> drift` command.
function _reminderNotesVisible() {
  try { return localStorage.getItem('sandpie-show-reminders') === '1'; } catch (_) { return false; }
}
/* ---- sandpie folder visibility in the file viewer (>>> hidden) ----------- */
// The SANDPIE section in the sidebar Files list is hidden by default; reveal it
// with `>>> hidden on` (hide again with `>>> hidden off`, or toggle with no arg).
function _sandpieSectionVisible() {
  try { return localStorage.getItem('sandpie-files-section-visible') === '1'; } catch (_) { return false; }
}
function registerHiddenCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'hidden',
    module: 'core',
    help: 'Show/hide the sandpie/ system-folder section in the sidebar file viewer',
    usage: '>>> hidden [on|off]',
    run(text, parts) {
      let on;
      if (parts.length > 1) on = /^(on|1|true|yes|show)$/i.test(parts[1]);
      else on = !_sandpieSectionVisible();   // no arg → toggle
      try { localStorage.setItem('sandpie-files-section-visible', on ? '1' : '0'); } catch (_) {}
      if (window.opfs && opfs.refreshFileList) opfs.refreshFileList().catch(() => {});
      return 'sandpie/ system folders are now ' + (on ? 'VISIBLE' : 'hidden')
        + ' in the file viewer.\n(' + (on
          ? 'The SANDPIE section appears at the bottom of the Files list.'
          : 'The SANDPIE section is hidden again — reveal it anytime with `>>> hidden on`.') + ')';
    }
  });
}

function registerDriftCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'drift',
    module: 'core',
    help: 'Toggle visibility of harness reminder notes (drift / no-plan / stop guard)',
    usage: '>>> drift [on|off]',
    run(text, parts) {
      let on;
      if (parts.length > 1) on = /^(on|1|true|yes|show)$/i.test(parts[1]);
      else on = !_reminderNotesVisible();   // no arg → toggle
      try { localStorage.setItem('sandpie-show-reminders', on ? '1' : '0'); } catch (_) {}
      return 'Harness reminder notes are now ' + (on ? 'VISIBLE' : 'hidden')
        + '.\n(drift / no-plan / stop-guard events. They still fire and log to the console either way;'
        + ' this only controls whether they appear in the transcript. Applies to reminders from here on.)';
    }
  });
}

/* ---- metacognition triggers on/off (grind / reuse-tool / remember) ------- */
function registerMetacogCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'metacog',
    module: 'core',
    help: 'Enable/disable the metacognition nudges (grind / reuse-a-tool / remember)',
    usage: '>>> metacog [on|off]',
    run(text, parts) {
      let on;
      if (parts.length > 1) on = /^(on|1|true|yes)$/i.test(parts[1]);
      else { try { on = localStorage.getItem('sandpie-metacog') === 'off'; } catch (_) { on = true; } }  // toggle
      try { localStorage.setItem('sandpie-metacog', on ? 'on' : 'off'); } catch (_) {}
      return 'Metacognition nudges are now ' + (on ? 'ON' : 'OFF')
        + '.\n(grind / reuse-a-tool / remember. Takes effect on the next turn. `>>> drift` controls whether their notes are shown.)';
    }
  });
}

/* ---- LITE MODE (per-conversation fast path) ------------------------------ */
// >>> lite toggles a per-conversation flag stored in <id>.meta.json. When ON,
// the turn is sent WITHOUT the tool schema, skills block and memory block, and
// with a minimal system prompt — cutting the request from ~30-60K tokens to
// ~1-2K so simple queries (translations, quick questions) answer in seconds.
// Tools are unavailable while lite is on; turn it off to restore full power.
function _liteOn(id) {
  try { const m = liteMetaCache.get(id || activeConvId); return m === true; } catch (_) { return false; }
}
const liteMetaCache = new Map();   // convId -> boolean (best-effort read cache)
async function _loadLiteFlag(id) {
  if (liteMetaCache.has(id)) return liteMetaCache.get(id);
  let on = false;
  try { const m = await readConvMeta(id); on = !!(m && m.lite); } catch (_) {}
  liteMetaCache.set(id, on);
  return on;
}
async function _setLite(id, on) {
  const loc = await convLocation(id);
  if (!loc.format) { liteMetaCache.set(id, !!on); return; }   // brand-new conv: cache only (ensureSessionId persists it on first send)
  if (loc.format === 'old') {
    // Legacy single-file format: readConvMeta() reads the .json for these, so
    // the flag must live inside it (a sidecar meta would never be read back).
    const cp = convPath(id, loc.archived);
    let data = null; try { data = JSON.parse(await opfs.read(cp)); } catch (_) {}
    if (data) {
      data.lite = !!on;
      await opfs.write(cp, JSON.stringify(data));
      try { Sandpie.events.emit('file:changed', cp); } catch (_) {}
    }
    liteMetaCache.set(id, !!on);
    return;
  }
  const mp = metaPath(id, loc.archived);
  let meta = null; try { meta = JSON.parse(await opfs.read(mp)); } catch (_) {}
  const updated = Object.assign({}, meta || {}, { id, lite: !!on });
  await opfs.write(mp, JSON.stringify(updated));
  try { Sandpie.events.emit('file:changed', mp); } catch (_) {}
  liteMetaCache.set(id, !!on);
}
/* ---- lite quick-toggle button (bolt next to the mic) -------------------- */
const LITE_BOLT_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>';
function liteBtnRefresh() {
  const b = document.getElementById('liteBtn');
  if (!b) return;
  const on = _liteOn();
  b.classList.toggle('active', on);
  b.title = on ? 'FAST mode is ON for this conversation - click to turn it off'
               : 'Enable FAST mode for this conversation (no tools/skills/memories)';
}
function registerLiteButton() {
  const bar = document.querySelector('form.composer:not(.composer-side) .input-bar');
  if (!bar) return false;
  let btn = document.getElementById('liteBtn');
  if (btn && btn.parentNode === bar) { liteBtnPlace(btn, bar); return true; }
  if (!btn) {
    btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'liteBtn';
    btn.className = 'attach-btn lite-btn';
    btn.title = 'Enable FAST mode for this conversation (no tools/skills/memories)';
    btn.setAttribute('aria-label', 'Toggle FAST mode');
    btn.innerHTML = LITE_BOLT_SVG;
    btn.addEventListener('click', (e) => {
      e.stopPropagation(); e.preventDefault();
      // Home screen (fresh boot / hard refresh): no conversation is mounted
      // (boot no longer restores the last chat). Instead of dying silently,
      // materialize a new conversation and toggle FAST on it.
      if (!activeConvId) {
        newConversation().then(() => {
          const cid = activeConvId;
          if (!cid) return;
          _setLite(cid, true).then(() => {
            liteBtnRefresh();
            try { if (SandpieCommandView) SandpieCommandView.show(
              'FAST mode is now ON for this conversation.', 'fast');
            } catch (_) {}
          }).catch(() => {});
        }).catch(() => {});
        return;
      }
      const cid = activeConvId;
      const on = !_liteOn(cid);
      _setLite(cid, on).then(() => {
        liteBtnRefresh();
        try { if (SandpieCommandView) SandpieCommandView.show(
          'FAST mode is now ' + (on ? 'ON' : 'OFF') + ' for this conversation.', 'fast');
        } catch (_) {}
      }).catch(() => {});
    });
  }
  // Always park it right after the model picker first, so it is never left of
  // the attach button while the mic has not been injected yet; liteBtnPlace()
  // then moves it to the right of the mic as soon as the mic exists.
  const picker = document.getElementById('modelPicker');
  if (picker && picker.parentNode === bar) picker.insertAdjacentElement('afterend', btn);
  else bar.appendChild(btn);
  return true;
}
// The bolt's slot is IMMEDIATELY AFTER the mic button (speech-to-text.js injects
// micBtn after the model picker). If the mic is not there yet, wait for it and
// re-place — never fall back to bar.firstChild (that puts the bolt left of the
// attach "+", where a misclick opens the file picker).
function liteBtnPlace(btn, bar) {
  const mic = document.getElementById('micBtn');
  if (mic && mic.parentNode === bar && mic.nextElementSibling !== btn) {
    mic.insertAdjacentElement('afterend', btn);
    liteBtnRefresh();
  }
}
setInterval(() => { liteBtnRefresh(); const b = document.getElementById("liteBtn"); const bar = b && b.closest(".input-bar"); if (b && bar) liteBtnPlace(b, bar); }, 700);
try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.on('file:changed', liteBtnRefresh); } catch (_) {}

function registerLiteCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'fast',
    module: 'core',
    help: 'Toggle FAST mode for this conversation (no tools/skills/memories - fast answers)',
    usage: '>>> fast [on|off]',
    run(text, parts) {
      const cid = activeConvId;
      if (!cid) return 'FAST mode applies per conversation - open (or start) a conversation first, then run >>> fast.';
      let on;
      if (parts.length > 1) on = /^(on|1|true|yes)$/i.test(parts[1]);
      else on = !_liteOn(cid);   // no arg -> toggle
      const apply = () => _setLite(cid, on).then(() =>
        'FAST mode is now ' + (on ? 'ON' : 'OFF') + ' for this conversation.'
        + '\n(' + (on
          ? 'No tools, skills or memories are sent - simple queries answer in seconds. Turn it off with >>> fast off when you need files, Python or search.'
          : 'Full power restored: tools, skills and memories are back on the next turn.') + ')');
      // New conversation (no meta yet): flush the pending conv creation first if needed.
      return _loadLiteFlag(cid).then(() => apply());
    }
  });
}

/* ---- command registration: rewind -------------------------------------- */
function registerRewindCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'rewind',
    module: 'core',
    help: 'Rewind conversation N turns back',
    usage: '>>> rewind [N]',
    run(text, parts) {
      const n = parts.length > 1 ? parseInt(parts[1], 10) : 1;
      if (Number.isNaN(n) || n < 1) {
        return 'Usage: >>> rewind [N] — removes the last N user-assistant pairs.';
      }

      const s = activeStream();
      if (!s || !messages.length) return 'Nothing to rewind.';

      // The rewound conversation lives in whichever pane its stream host is
      // mounted in (#messages left / #messagesSide right). Capture it BEFORE
      // the re-render wipes the host, so the restored text lands in THAT
      // pane's composer instead of always the left one.
      const rewindPane = s.host ? s.host.parentNode : null;

      let userCount = 0;
      let idx = messages.length;
      while (idx > 0 && userCount < n) {
        idx--;
        if (messages[idx].role === 'user') userCount++;
      }
      if (userCount === 0) return 'No user messages found to rewind.';

      const removed = messages.length - idx;
      if (!confirm(`Remove the last ${removed} message(s)?`)) return '(cancelled)';

      // Collect user messages that are about to be removed for restoration
      const rewindTexts = [];
      if (idx < messages.length) {
        for (let i = messages.length - 1; i >= idx; i--) {
          const m = messages[i];
          if (m.role !== 'user' || !m.content) continue;
          let txt = '';
          if (typeof m.content === 'string') {
            txt = m.content;
          } else if (Array.isArray(m.content)) {
            txt = m.content
              .filter(p => p && p.type === 'text' && p.text)
              .map(p => p.text)
              .join('\n');
          }
          if (txt.trim()) rewindTexts.unshift(txt.trim());
        }
      }

      if (s) {
        if (s.abort) { s.abort.abort(); }
      }
      messages.length = idx;
      if (s && s.compaction && idx <= s.compaction.boundary) s.compaction = null;
      clearActiveConvUI();
      renderConversation(messages, s ? s.compaction : null);

      const messagesEl = paneScrollEl($('messages'));
      if (messagesEl && shouldAutoScroll(messagesEl)) messagesEl.scrollTop = messagesEl.scrollHeight;
      saveActiveConv().catch(() => {});

      if (rewindTexts.length) {
        const ta = rewindPane === $('messagesSide') ? $('inputSide') : $('input');
        if (ta) {
          const combined = rewindTexts.join('\n\n');
          ta.value = combined;
          ta.style.height = 'auto';
          ta.style.height = ta.scrollHeight + 'px';
          ta.select();
          ta.focus();
        }
      }
      return removed > 1 ? `Removed ${removed} messages.` : 'Removed last turn.';
    }
  });
}
registerRewindCommand();
registerDriftCommand();
registerHiddenCommand();
registerMetacogCommand();
registerLiteCommand();
registerLiteButton();
// Scroll a conversation's host to its end. The host is the scroll container, so
// this targets the pane the conversation was actually mounted in (main OR side)
// — loadConv used to scroll #messages unconditionally and left a conversation
// mounted into the focused right pane sitting at the top. Images render with no
// reserved height and fill in asynchronously, so re-pin when one loads if the
// view is still at the bottom (within that image's own height — i.e. the growth
// came from the image, not from the user scrolling up to read).
function scrollConvToEnd(s) {
  const host = s && s.host;
  if (!host || !host.parentNode) return;
  host.scrollTop = host.scrollHeight;
  host.querySelectorAll('img').forEach(img => {
    img.addEventListener('load', () => {
      const gap = host.scrollHeight - host.scrollTop - host.clientHeight;
      if (gap <= img.getBoundingClientRect().height + 2) host.scrollTop = host.scrollHeight;
    }, { once: true });
  });
}
async function loadConv(id) {
  if (id === activeConvId) return;

  if (sidePanel?.isOpen && id === sidePanel.sideId) { sidePanel.flip(); return; }

  const prevId = activeConvId;

  // ── INSTANT UI SWITCH: all synchronous, no awaits before the panel changes.
  parkActiveConv();
  mountConv(id);                       // sets activeConvId, mounts the (possibly empty) host
  localStorage.setItem('sandpie-active-conv', id);
  convLastViewed.set(id, new Date().toISOString());
  document.body.classList.remove('sidebar-open');
  const btn = document.querySelector('.hamburger');
  if (btn) btn.textContent = '☰';

  const s = ensureStream(id);
  if (convStreams.has(id) && s.messages.length) {
    // Warm — content already loaded; just scroll + refresh the sidebar.
    scrollConvToEnd(s);
    await refreshConversationList();
    return;
  }

  // ── COLD: load in the background — the panel has already switched. ──
  if (s._loading) return;   // a load for this conv is already in flight — it will render when done
  s._loading = true;
  (async () => {
    try {
      // Save the PREVIOUS conversation in the background (its data is still in
      // its stream); no longer blocks the switch.
      if (prevId) { try { await saveConv(prevId, { touchUpdated: false }); } catch (_) {} }

      const loc = await convLocation(id);
      if (!loc.format) {
        addMsg('err', 'Failed to load conversation.');
        if (prevId) mountConv(prevId);
        return;
      }
      // Dehydrated archive: fetch the body from the cloud before the size probe
      // (getFileSize returns 0 for a missing file → would render as empty).
      await ensureLocalConvFile(loc.format === 'new' ? jsonlPath(id, loc.archived) : convPath(id, loc.archived));

      // Read the tiny meta file first (title, compaction, msgCount, etc.)
      let meta = {};
      if (loc.format === 'new') {
        try { meta = JSON.parse(await opfs.read(metaPath(id, loc.archived))); } catch {}
      } else {
        // Legacy .json: no incremental path — fall back to full load
        const data = await readConvData(id);
        if (!data) { addMsg('err', 'Failed to load conversation.'); if (prevId) mountConv(prevId); return; }
        hydrateStreamFromData(s, data);
        if (activeConvId === id) messages = s.messages;
        renderConversation(s.messages, s.compaction, s.host);
        if (s.readOnlyViewer) _notifyReadOnlyConv(s);   // render wiped the mount-time notice
        scrollConvToEnd(s);
        await refreshConversationList();
        return;
      }

      // ── Incremental load: read the END of the JSONL first ──
      const jp = jsonlPath(id, loc.archived);
      const fileSize = await opfs.getFileSize(jp);
      s.compaction = meta.compaction || null;
      s.todos = meta.todos || null;
      s.scratchpad = meta.scratchpad || '';
      s.filesTouched = meta.filesTouched || null;
      s.artifactThumbs = meta.artifactThumbs || null;
      s.lastTurn = meta.lastTurn || null;
      s.projectId = meta.projectId || null;
      s.providerId = meta.providerId || null;
      s.reasoningLevel = meta.reasoningLevel || null;

      if (!fileSize) {
        // Empty conversation (no messages yet)
        s.messages = [];
        s.persistedCount = 0;
        s._forceJsonlRewrite = false;
        if (activeConvId === id) messages = s.messages;
        renderConversation(s.messages, s.compaction, s.host);
        if (s.readOnlyViewer) _notifyReadOnlyConv(s);   // render wiped the mount-time notice
        await refreshConversationList();
        return;
      }

      // Atomic load: read the WHOLE JSONL and render it in one pass, then scroll to
      // the bottom. No progressive chunking / prepends — that caused a load-time
      // jiggle that couldn't be fully tamed. Mirrors the legacy .json full-load
      // path above; renderConversation handles compaction + pending asks + timer.
      let text = '';
      try { text = await opfs.read(jp); } catch (_) {}
      const allMsgs = [];   // chronological (oldest→newest), as stored
      for (const line of text.split('\n')) {
        const t = line.trim();
        if (!t) continue;
        try { allMsgs.push(JSON.parse(t)); } catch (_) { /* tolerate a torn trailing line */ }
      }
      s.messages = allMsgs;
      s.persistedCount = meta.msgCount || allMsgs.length;
      s._forceJsonlRewrite = false;
      // Repair duplicated history blocks and persist the repair right away (the
      // save chain keeps it ordered before any subsequent turn's writes).
      const dupRemoved = repairDuplicateHistory(allMsgs, s.compaction);
      if (dupRemoved) {
        console.warn('[sandpie] repaired conversation', id, '— removed', dupRemoved, 'duplicated messages');
        s.persistedCount = allMsgs.length;
        s._forceJsonlRewrite = true;
        saveConv(id, { touchUpdated: false }).catch(() => {});
      }
      if (activeConvId === id) messages = s.messages;
      renderConversation(allMsgs, s.compaction, s.host);
      if (s.readOnlyViewer) _notifyReadOnlyConv(s);   // render wiped the mount-time notice
      scrollConvToEnd(s);
      await refreshConversationList();
    } finally {
      s._loading = false;
    }
  })();
}

async function newConversation() {
  await saveActiveConv();
  // "+ New chat" always opens in the MAIN pane and leaves the side panel alone.
  // It used to mount into the FOCUSED pane, so with the focus on the right it
  // silently unmounted the conversation the user had docked there.
  const main = $('messages');
  parkPaneConv(main);
  const id = newConvId();
  const s = ensureStream(id);
  mountConv(id, main);
  if (sidePanel?.isOpen && sidePanel.activeIsRight) sidePanel.focusPane(false);
  convLastViewed.set(id, new Date().toISOString());
  await refreshConversationList();
}
// Conversation-list row cache (see listConversations). Rows are keyed by
// archived-state + id and invalidated by file:changed/file:deleted on
// conversation meta paths (registered in bootConversations). JSONL appends are
// filtered out — they fire constantly during a turn but never change a row.
const _convRowCache = new Map();

// --- Archived content search via the Dropbox API (archive-dehydration step 1) ---
// Archived conversations are matched by CLOUD content search (files/search_v2
// scoped to the archived folder) instead of reading every archived .jsonl from
// OPFS. Used by the Settings → Archive tab search (the sidebar never lists
// archived rows). Results are cached per query string (invalidated by any
// file:changed/file:deleted under the archived dir). Returns a Set of
// conversation ids whose content matched the query.
const _archSearchCache = { q: null, ids: null };
function _archSearchInvalidate() { _archSearchCache.q = null; _archSearchCache.ids = null; }
async function searchArchivedCloud(q) {
  q = String(q || '').trim().toLowerCase();
  if (!q) return new Set();
  if (_archSearchCache.q === q && _archSearchCache.ids) return _archSearchCache.ids;
  const ids = new Set();
  try {
    const sp = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
    if (sp && sp.cloudConnected && sp.cloudConnected() && sp.cloudSearch && sp.workingRoot) {
      const scope = sp.workingRoot() + '/' + ARCHIVED_DIR;
      const r = await sp.cloudSearch(q, scope, { maxResults: 500 });
      for (const p of r.paths || []) {
        const name = (p.split('/').pop() || '');
        const id = name.replace(/\.(?:jsonl|meta\.json|json)$/, '');
        if (id) ids.add(id);
      }
    }
  } catch (_) { /* cloud leg is best-effort: title matching still applies */ }
  _archSearchCache.q = q; _archSearchCache.ids = ids;
  return ids;
}

// MODULE SCOPE (not nested in listConversations): the bootConversations
// file:changed/file:deleted listener and the Archive tab both call
// _archSearchInvalidate()/searchArchivedCloud() outside that function.
async function listConversations() {
  const searchActive = !!($('convSearch')?.value.trim());

  // Scan the ACTIVE dir only. The sidebar never lists archived conversations
  // (archive management lives in the Settings → Archive tab), so the archived
  // dir is not scanned here at all — at 10k+ conversations re-reading archived
  // metas on every keystroke would dominate the search path. listArchived()
  // owns the archived listing. A conv may have a new meta file AND a legacy
  // .json (kept as a backup); prefer the new format. Classify .meta.json BEFORE
  // plain .json (since ".meta.json" also ends with ".json").
  const found = new Map();   // id -> { archived: false, format }
  {
    let entries = [];
    try { entries = await opfs.listDir(CONV_DIR); } catch { /* empty */ }
    for (const e of entries) {
      if (e.kind !== 'file') continue;
      let id = null, format = null;
      if (e.name.endsWith(META_SUFFIX)) { id = e.name.slice(0, -META_SUFFIX.length); format = 'new'; }
      else if (e.name.endsWith('.json')) { id = e.name.slice(0, -5); format = 'old'; }
      else continue;
      const prev = found.get(id);
      if (!prev || (prev.format === 'old' && format === 'new')) found.set(id, { archived: false, format });
    }
  }

  // Steady-state refreshes reuse cached rows instead of re-reading every meta
  // (that was ~3.4s of the conversation-switch cost with many convs). Search
  // bypasses the cache (it needs the jsonl content) for active conversations.
  const rows = await Promise.all(
    [...found.entries()].map(async ([id, loc]) => {
      const key = 'n:' + id;
      if (!searchActive && _convRowCache.has(key)) return _convRowCache.get(key);
      const row = await readConvMetaRow(id, false, loc.format, searchActive);
      if (row && !searchActive) _convRowCache.set(key, row);
      return row;
    }),
  );
  // Prune rows for conversations that no longer exist (deleted / moved archive).
  const alive = new Set([...found.entries()].map(([id]) => 'n:' + id));
  for (const key of _convRowCache.keys()) if (!alive.has(key)) _convRowCache.delete(key);
  const out = rows.filter(Boolean);

  for (const c of out) {
    if (!convLastViewed.has(c.id)) convLastViewed.set(c.id, c.updated || '');
  }
  return out.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
}
// Patch conversation metadata (title / pinned / archived / compaction / …). New
// format → rewrite ONLY the tiny meta file (O(1), regardless of chat size — this
// is what makes rename/pin instant). Legacy → patch the .json in place (still O(N)
// until the conv migrates on its next full save/open). Never touches messages.
async function updateConvFile(id, patch) {
  const loc = await convLocation(id);
  if (loc.format === 'new') {
    let meta = {}; try { meta = JSON.parse(await opfs.read(metaPath(id, loc.archived))); } catch { return; }
    Object.assign(meta, patch);
    const p = metaPath(id, loc.archived);
    await opfs.write(p, JSON.stringify(meta));
    Sandpie.events.emit('file:changed', p);
    // Keep a warm stream's mirrored fields in step so its next save doesn't revert them.
    const s = convStreams.get(id);
    if (s && 'compaction' in patch) s.compaction = patch.compaction || null;
    _refreshPaneBarsFor(id);
    return;
  }
  if (loc.format === 'old') {
    const p = convPath(id, loc.archived);
    let data; try { data = JSON.parse(await opfs.read(p)); } catch { return; }
    Object.assign(data, patch);
    await opfs.write(p, JSON.stringify(data));
    Sandpie.events.emit('file:changed', p);
    _refreshPaneBarsFor(id);
  }
}
async function renameConv(id, current) {
  const next = prompt('Rename conversation', current);
  if (next == null) return;
  const trimmed = next.trim();
  if (!trimmed || trimmed === current) return;
  // titleLocked: a title the user typed is final — auto-titling must never
  // overwrite it, however the conversation is used later.
  await updateConvFile(id, { title: trimmed, titleLocked: true });
  await refreshConversationList();
}
async function togglePinConv(id, currentlyPinned) {
  await updateConvFile(id, { pinned: !currentlyPinned });
  await refreshConversationList();
}
async function toggleArchiveConv(id, currentlyArchived) {
  // Archive is a folder move. Relocate every file that exists for this conv (new
  // meta + jsonl, and/or a legacy .json backup) from one dir to the other, patching
  // the archived/pinned flags inside the JSON-shaped ones. Not data loss — a move.
  const from = currentlyArchived, to = !currentlyArchived;
  const pairs = [
    [metaPath(id, from), metaPath(id, to)],
    [jsonlPath(id, from), jsonlPath(id, to)],
    [convPath(id, from), convPath(id, to)],
  ];
  // Dehydrated archive: fetch cloud-only source files first — the move below
  // skips unreadable files, which would leave the body behind in the archive.
  for (const p of [metaPath(id, from), jsonlPath(id, from), convPath(id, from)]) {
    await ensureLocalConvFile(p);
  }
  for (const [src, dst] of pairs) {
    let content; try { content = await opfs.read(src); } catch { continue; }
    if (src.endsWith(META_SUFFIX) || src.endsWith('.json')) {
      try { const o = JSON.parse(content); o.archived = to; if (to) delete o.pinned; content = JSON.stringify(o); } catch {}
    }
    try {
      await opfs.write(dst, content); Sandpie.events.emit('file:changed', dst);
      await opfs.remove(src); Sandpie.events.emit('file:deleted', src);
    } catch (e) { console.warn('toggleArchiveConv move failed:', src, e); }
  }
  await refreshConversationList();
}
async function duplicateConv(id, title) {
  const data = await readConvData(id);
  if (!data) { addMsg('err', 'Failed to duplicate conversation.'); return; }
  const newId = newConvId();
  const now = new Date().toISOString();
  await rewriteConvJsonl(newId, false, data.messages || []);
  const meta = {
    id: newId,
    title: '(copy) ' + (data.title || title || '(no title)'),
    created: now, updated: now, pinned: false,
    msgCount: (data.messages || []).length,
  };
  if (data.compaction) meta.compaction = data.compaction;
  if (data.todos) meta.todos = data.todos;
  if (data.filesTouched) meta.filesTouched = data.filesTouched;
  if (data.artifactThumbs) meta.artifactThumbs = data.artifactThumbs;
  if (data.scratchpad != null) meta.scratchpad = data.scratchpad;
  // A duplicate stays in the same project as its original.
  if (data.projectRoot) { meta.projectRoot = data.projectRoot; meta.projectNs = data.projectNs || 'home'; }
  // Intentionally do NOT copy session_id: the duplicate is a distinct
  // conversation and must get its own cache key (ensureSessionId on first send).
  const mp = metaPath(newId, false);
  await opfs.write(mp, JSON.stringify(meta));
  Sandpie.events.emit('file:changed', mp);
  await refreshConversationList();
}
async function deleteConv(id, title) {
  const dbxNote = Sandpie.syncProvider()?.isConnected?.() ? ' This will also remove the cloud copy.' : '';
  if (!confirm(`Delete conversation "${title}"?${dbxNote}`)) return;
  await _deleteConvFiles(id);
}
async function _deleteConvFiles(id) {
  releaseConvWriterLock(id);   // gone conversations shouldn't pin a writer lock
  // Explicit user delete removes EVERY file for this id in both dirs — the new pair
  // AND any legacy .json backup. Leaving the .json behind would resurrect the conv
  // on the next list scan. (This is the one place old files are intentionally
  // removed; migration never does.)
  for (const archived of [false, true]) {
    for (const p of [metaPath(id, archived), jsonlPath(id, archived), convPath(id, archived)]) {
      try { await opfs.remove(p); } catch {}   // NotFound is fine (cloud-only file)
      Sandpie.events.emit('file:deleted', p);   // unconditional: deletes the Dropbox copy too
    }
  }

  const stream = convStreams.get(id);
  if (stream) {
    if (stream.abort) stream.abort.abort();
    if (stream.timerInterval) clearInterval(stream.timerInterval);
    if (stream.host && stream.host.parentNode) {
      _evacuateHome(stream.host);   // deleting a conv must not delete the home lists
      stream.host.parentNode.removeChild(stream.host);
      _placeHome();
    }
    convStreams.delete(id);
  }

  if (sidePanel) sidePanel.notifyDeleted(id);
  if (id === activeConvId) {
    activeConvId = null;
    localStorage.removeItem('sandpie-active-conv');
    messages = [];

    const promoted = sidePanel?.promoteSideToActive();
    if (!promoted) {
      refreshSendButtonForActive();
    } else {

    }
  }
  await refreshConversationList();
}
// ---- Bulk actions over a multi-conversation selection ----
// Pin every selected conversation (idempotent). One list refresh at the end.
async function bulkPinConvs(ids) {
  for (const id of ids) await updateConvFile(id, { pinned: true });
  _selClear();
  await refreshConversationList();
}
async function bulkArchiveConvs(ids) {
  for (const id of ids) await toggleArchiveConv(id, false);
  _selClear();
  await refreshConversationList();
}
async function bulkDuplicateConvs(ids) {
  for (const id of ids) await duplicateConv(id, '');
  _selClear();
  await refreshConversationList();
}
async function bulkDeleteConvs(ids) {
  const n = ids.length;
  const dbxNote = Sandpie.syncProvider()?.isConnected?.() ? ' This will also remove the cloud copy.' : '';
  if (n === 1) { await deleteConv(ids[0], '(selected)'); return; }
  if (!confirm(`Delete ${n} conversations?${dbxNote}`)) return;
  for (const id of ids) await _deleteConvFiles(id);
  _selClear();
  await refreshConversationList();
}
function fmtRelTime(iso) {
  if (!iso) return '';
  const then = new Date(iso);
  const now = new Date();
  const sec = Math.floor((now - then) / 1000);
  if (sec < 60) return 'now';
  const min = Math.floor(sec / 60);
  if (min < 60) return min + 'm';
  const hr = Math.floor(min / 60);
  if (hr < 24) return hr + 'h';
  const day = Math.floor(hr / 24);
  if (day < 7) return day + 'd';
  const wk = Math.floor(day / 7);
  if (wk < 5) return wk + 'w';
  const mo = Math.floor(day / 30);
  if (mo <= 12) return mo + 'mo';
  return Math.floor(day / 365) + 'y';
}
// Sibling to fmtRelTime() above. That renders a past instant as a coarse
// "time ago" (5m, 2h); this renders an elapsed DURATION (seconds, possibly
// fractional) as a compact h/m/s string — 45s, 1m0s, 1h10m0s. It is the single
// home for the hour/minute/second breakdown so the live message timer and its
// settled "done" label stay in lockstep. Pass tenths=true to keep one decimal
// on sub-10s durations (used for the final settled time, e.g. 3.4s).
function fmtElapsed(totalSec, tenths = false) {
  totalSec = Math.max(0, totalSec || 0);
  if (totalSec < 60) {
    return (tenths && totalSec < 10) ? `${totalSec.toFixed(1)}s` : `${Math.floor(totalSec)}s`;
  }
  const s = Math.floor(totalSec % 60);
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  return h > 0 ? `${h}h${m}m${s}s` : `${m}m${s}s`;
}
// ---- Multi-conversation selection (shift/ctrl click + shift-drag rubber band) ----
// PC-first: shift+click = range (anchor to row), ctrl/cmd+click = toggle, 
// ---- Collapsible sidebar groups (Pinned / Today / Yesterday / months / years) ----
// State lives per DEVICE in localStorage, keyed by the group LABEL, because the
// labels are what persist across renders -- the rows under "Today" are different
// conversations tomorrow, but "Today" is still the group the user closed.
//
// The rows stay in the DOM and are hidden with a class. `hidden` as an attribute
// would NOT work: ul.fs-list li sets display:flex, which beats [hidden]'s
// display:none.
const _CG_KEY = 'sandpie-conv-collapsed';
let _cgCollapsed = new Set();
try { _cgCollapsed = new Set(JSON.parse(localStorage.getItem(_CG_KEY) || '[]')); } catch (e) {}
function _cgSave() {
  try { localStorage.setItem(_CG_KEY, JSON.stringify([..._cgCollapsed])); } catch (e) {}
}
// Rows belonging to a header = every sibling until the next header.
function _cgRowsOf(head) {
  const out = [];
  let n = head.nextElementSibling;
  while (n && !n.classList.contains('conv-group')) { out.push(n); n = n.nextElementSibling; }
  return out;
}
function _cgApply(head) {
  const label = head.dataset.group || '';
  const closed = _cgCollapsed.has(label);
  const rows = _cgRowsOf(head);
  for (const r of rows) r.classList.toggle('conv-row-hidden', closed);
  head.classList.toggle('cg-closed', closed);
  head.setAttribute('aria-expanded', closed ? 'false' : 'true');
  // The count only appears while closed -- open, the rows speak for themselves.
  const n = head.querySelector('.cg-n');
  if (n) n.textContent = closed ? String(rows.length) : '';
}
function _cgToggle(head) {
  const label = head.dataset.group || '';
  if (_cgCollapsed.has(label)) _cgCollapsed.delete(label);
  else {
    _cgCollapsed.add(label);
    // Never leave a selection hidden behind a closed header: a bulk action on
    // rows the user cannot see is exactly the kind of surprise to design out.
    let touched = false;
    for (const r of _cgRowsOf(head)) {
      if (r.dataset.cid && _selConvs.delete(r.dataset.cid)) touched = true;
    }
    if (touched) _selHighlight();
  }
  _cgSave();
  _cgApply(head);
}
// Re-apply every header after the list is rebuilt.
function _cgApplyAll() {
  const ul = $('convList');
  if (ul) for (const h of ul.querySelectorAll('li.conv-group')) _cgApply(h);
}

// shift+drag on empty list space = rubber-band, right-click on selection = bulk
// actions (Pin all / Archive all / Duplicate all / Delete all). Plain click opens.
const _selConvs = new Set();
let _selAnchor = -1;
function _selectedRowCids() {
  const out = [];
  const ul = $('convList');
  if (ul) for (const li of ul.querySelectorAll('li[data-cid]')) out.push(li.dataset.cid);
  return out;
}
function _selIndex(cid) { return _selectedRowCids().indexOf(cid); }
function _selHighlight() {
  const ul = $('convList');
  if (ul) for (const li of ul.querySelectorAll('li[data-cid]'))
    li.classList.toggle('selected', _selConvs.has(li.dataset.cid));
}
function _selClear() { _selConvs.clear(); _selAnchor = -1; _selHighlight(); }
function _selRangeTo(i, j, add) {
  const rows = _selectedRowCids();
  const lo = Math.min(i, j), hi = Math.max(i, j);
  for (let k = lo; k <= hi; k++) {
    const id = rows[k];
    if (id && add) _selConvs.add(id);
  }
  _selAnchor = hi;
  _selHighlight();
}
// ---- conversation-row drag state -------------------------------------------
// A native HTML5 drag belongs to its SOURCE element: the browser dispatches
// `dragend` to the very <li> the drag started on. refreshConversationList()
// rebuilds the sidebar with replaceChildren(), so any refresh that lands while a
// drag is in flight destroys that node — `dragend` is then never dispatched, the
// drag session is never torn down, and the page stops responding to the mouse
// with nothing in the console (the dashed drop outline just stays up). The drop
// handler itself ends in refreshConversationList(), so this fired on EVERY drop.
// Refreshes requested during a drag are therefore deferred to dragend.
let _convDragging = false;
let _convRefreshPending = false;
function _endConvDrag() {
  if (!_convDragging) return;
  _convDragging = false;
  const w = $('messagesWrap'); if (w) w.classList.remove('drop-target');
  if (_convRefreshPending) { _convRefreshPending = false; refreshConversationList(); }
}
// Nets for a drag that never delivers `dragend` to the row that started it
// (re-render races, drags that leave the window, an OS drag loop that ends
// without notifying the page). `mouseup`, `pointerdown` and `keydown` cannot
// fire while a drag is in flight, so any one of them arriving proves the drag is
// over — without them a missed dragend would freeze the sidebar permanently.
if (typeof document !== 'undefined') {
  for (const t of ['dragend', 'mouseup', 'pointerdown', 'keydown']) {
    document.addEventListener(t, _endConvDrag, true);
  }
  window.addEventListener('blur', _endConvDrag);
}
function buildConvLi(c, idx) {

  const li = document.createElement('li');
  li.dataset.cid = c.id;
  if (c.id === activeConvId) li.classList.add('active');
  if (sidePanel?.isOpen && c.id === sidePanel.sideId) li.classList.add('in-panel');
  if (c.archived) li.classList.add('archived');
  if (_selConvs.has(c.id)) li.classList.add('selected');
  li.dataset.selorder = String(idx);
  const span = document.createElement('span');
  span.className = 'name';
  span.textContent = (c.pinned ? '> ' : '') + c.title;
  span.title = c.updated || '';
  li.appendChild(span);
  // This conversation was just auto-titled: play the landing animation on the row
  // we're building (the old one is already gone — see maybeAutoTitle). The final
  // title is set above first, so if anything interrupts the animation the correct
  // text is what's left on screen.
  if (_titleAnim.has(c.id) && typeof SandpieAutoTitle !== 'undefined' && SandpieAutoTitle.animateRetitle) {
    _titleAnim.delete(c.id);
    SandpieAutoTitle.animateRetitle(li, span, span.textContent);
  }

  const meta = document.createElement('span');
  meta.className = 'conv-meta';
  const stream = convStreams.get(c.id);
  // Pending ask() question: show the accent '?' whether or not generation is
  // running — the question survives a reload, so the badge must too.
  if (_askingConvs.has(c.id)) {
    meta.textContent = '?';
    meta.title = 'Pregunta pendiente de respuesta';
    meta.style.color = 'var(--sp-accent)';
    meta.style.fontWeight = '700';
  } else if (stream && stream.generating) {
    // Render the pulsing dot INSIDE the fixed-width conv-meta so the dot's
    // width (0/7px) never collapses the meta to min-width:0.
    const dot = document.createElement('span');
    dot.className = 'gen-dot';
    meta.appendChild(dot);
    meta.title = 'Still generating…';
  } else {
    meta.textContent = fmtRelTime(c.updated);
    const lastViewed = convLastViewed.get(c.id);
    const hasNew = c.updated && (!lastViewed || new Date(c.updated) > new Date(lastViewed));
    if (hasNew && c.id !== activeConvId) meta.classList.add('unseen');
  }
  li.prepend(meta); // meta leads the row (left side), name fills the rest

  // Row click: multi-select aware (shift = range, ctrl/cmd = toggle). Plain click
  // either opens the conversation or, if it lands on a selected row, keeps the
  // selection (so bulk actions stay usable).
  li.addEventListener('click', (ev) => {
    if (ev.button !== undefined && ev.button !== 0) return;
    const idx = parseInt(li.dataset.selorder || '-1', 10);
    if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
      ev.preventDefault(); ev.stopPropagation();
      if (ev.shiftKey) {
        if (_selConvs.size === 0) { _selConvs.add(c.id); _selAnchor = idx; _selHighlight(); }
        else _selRangeTo(_selAnchor, idx, true);
      } else {
        if (_selConvs.has(c.id)) _selConvs.delete(c.id); else _selConvs.add(c.id);
        _selAnchor = idx;
        _selHighlight();
      }
      return;
    }
    // Plain click: if this row is part of a selection, keep selection (no open).
    if (_selConvs.size > 0 && _selConvs.has(c.id)) {
      ev.preventDefault(); ev.stopPropagation();
      return;
    }
    // Plain click outside a selection: clear selection, then open normally.
    _selClear();
    loadConv(c.id);
  });
  const _openConvMenu = (ev) => {
    // Right-clicking a row that is NOT part of the current selection collapses the
    // selection to just that row (standard multi-select UX).
    if (_selConvs.size > 0 && !_selConvs.has(c.id)) {
      _selConvs.clear(); _selConvs.add(c.id); _selHighlight();
    }
    if (_selConvs.size > 1) {
      const ids = [..._selConvs];
      const items = [
        { info: true, label: _selConvs.size + ' conversations selected' },
        { label: 'Pin all',           action: () => bulkPinConvs(ids) },
        { label: 'Archive all',       action: () => bulkArchiveConvs(ids) },
        { label: 'Duplicate all',     action: () => bulkDuplicateConvs(ids) },
        { label: 'Delete all', danger: true, action: () => bulkDeleteConvs(ids) },
      ];
      showContextMenu(ev.clientX, ev.clientY, items);
      return;
    }
    const items = [
      { label: 'Rename',                             action: () => renameConv(c.id, c.title) },
      { label: c.pinned ? 'Unpin' : 'Pin',           action: () => togglePinConv(c.id, c.pinned) },
      { label: c.archived ? 'Unarchive' : 'Archive', action: () => toggleArchiveConv(c.id, c.archived) },
      { label: 'Duplicate',                          action: () => duplicateConv(c.id, c.title) },
    ];
    const sideOpen = sidePanel?.isOpen;
    const inActive = c.id === activeConvId;
    const inSide   = sideOpen && c.id === sidePanel.sideId;
    if (!isMobileViewport() && !inActive && !inSide) {
      items.push({ label: 'View in side panel', action: () => sidePanel.open(c.id) });
    }
    if (inSide) {
      items.push({ label: 'Close side panel', action: () => sidePanel.close() });
    }
    items.push({ label: 'Delete', danger: true, action: () => deleteConv(c.id, c.title) });
    showContextMenu(ev.clientX, ev.clientY, items);
  };
  li.addEventListener('contextmenu', (ev) => { ev.preventDefault(); _openConvMenu(ev); });
  attachLongPress(li, _openConvMenu);

  li.draggable = true;
  li.addEventListener('dragstart', (ev) => {
    // Shift+drag on a row is a selection gesture, not a panel drag.
    if (ev.shiftKey) { ev.preventDefault(); return; }
    ev.dataTransfer.setData('text/sandpie-conv-id', c.id);
    ev.dataTransfer.effectAllowed = 'copy';
    // Freeze sidebar rebuilds for the duration of the drag — see _endConvDrag.
    _convDragging = true;
    // Show the dashed drop zone immediately, before the pointer even reaches the
    // messages area — so the user can see where they're allowed to drop.
    const w0 = $('messagesWrap'); if (w0) w0.classList.add('drop-target');
    // dragend always fires when the drag concludes (dropped, cancelled, or
    // released outside the drop zone) — guaranteed cleanup for the drop-target
    // dashed line so it can never get stuck on screen.
    li.addEventListener('dragend', _endConvDrag, { once: true });
  });
  return li;
}
// Auto-archive conversations older than AUTO_ARCHIVE_DAYS that aren't pinned.
// Triggered once per boot by the 'sync:done' event (fires after the initial
// Dropbox sync completes, while the splash is still visible). Pinned
// conversations are always exempt — pinning is an explicit "keep visible"
// signal. Moving a conv to the archive is reversible (Settings → Archive →
// Unarchive) and never deletes data.
const AUTO_ARCHIVE_DAYS = 14; // 2 weeks: auto-archive conversations untouched for >14 days
// Eviction MINIMUM: even past the cutoff, the newest N unpinned conversations
// always stay in the active list. With only a handful of chats, archiving them
// all reads as "my stuff was deleted" — the archive must never look like data
// loss, so a small list is never touched at all.
const AUTO_ARCHIVE_MIN_KEEP = 25;
let _autoArchiveDone = false;
async function autoArchiveStale() {
  if (_autoArchiveDone) return;
  _autoArchiveDone = true;
  let list;
  try { list = await listConversations(); } catch { return; }
  const cutoff = Date.now() - AUTO_ARCHIVE_DAYS * 86_400_000;
  const stale = list.filter(c =>
    !c.archived && !c.pinned && c._format !== 'old' && c.updated &&
    new Date(c.updated).getTime() < cutoff
  );
  if (!stale.length) return;
  // Apply the eviction minimum: keep the newest N stale conversations active
  // regardless of age; only the older surplus is archived.
  stale.sort((a, b2) => new Date(b2.updated).getTime() - new Date(a.updated).getTime());
  if (stale.length <= AUTO_ARCHIVE_MIN_KEEP) return;
  stale = stale.slice(AUTO_ARCHIVE_MIN_KEEP);
  for (const c of stale) {
    try { await toggleArchiveConv(c.id, false); }
    catch (e) { console.warn('autoArchiveStale failed for', c.id, e); }
  }
  console.info("[sandpie] Auto-archived " + stale.length + " conversation(s) older than " + AUTO_ARCHIVE_DAYS + " days");
  await refreshConversationList();
}

// ── "finished while you were looking elsewhere" ─────────────────────────────
// A turn that ENDS while its conversation is neither the main pane's nor the
// side pane's is work nobody has seen yet. Those ids collect here and surface as
// a count on the sidebar toggle, which is the only sidebar affordance left once
// the list is collapsed. Opening the conversation in either pane clears it.
const _doneUnseen = new Set();
function _convOnScreen(id) {
  if (!id) return false;
  if (id === activeConvId) return true;
  return !!(sidePanel && sidePanel.isOpen && id === sidePanel.sideId);
}
// liveIds (when given) drops conversations that no longer exist, so a delete can
// never strand a phantom in the count. The on-screen sweep makes this
// self-correcting: anything now visible falls out here even if a hook was missed.
function updateConvAlerts(liveIds) {
  if (liveIds) for (const id of [..._doneUnseen]) if (!liveIds.has(id)) _doneUnseen.delete(id);
  for (const id of [..._doneUnseen]) if (_convOnScreen(id)) _doneUnseen.delete(id);
  const n = _doneUnseen.size;
  for (const el of document.querySelectorAll('.sp-badge')) {
    el.textContent = n > 99 ? '99+' : String(n);
    el.hidden = n === 0;
    el.title = n === 1 ? '1 conversation finished' : n + ' conversations finished';
  }
}

// ── Sidebar date grouping ───────────────────────────────────────────────────
// Buckets are Today / Yesterday / This week / Last week / Older, walked
// newest-first over an already date-sorted list, so one pass assigns them all.
// A bucket with no rows renders NO header — that is what stops a Monday (when
// "This week" can only hold today, which is already its own group) from showing
// an empty heading. Day and week starts go through setDate/setHours rather than
// millisecond arithmetic so they stay on local midnight across a DST change.
function _startOfDay(t, offsetDays) {
  const d = new Date(t);
  d.setHours(0, 0, 0, 0);
  if (offsetDays) d.setDate(d.getDate() + offsetDays);
  return d.getTime();
}
// Weeks start Monday: getDay() puts Sunday at 0, so shift it to the end.
function _startOfWeek(t, offsetWeeks) {
  const d = new Date(t);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + (offsetWeeks || 0) * 7);
  return d.getTime();
}
function _convGroupBounds(now) {
  const n = now || Date.now();
  return {
    today:     _startOfDay(n, 0),
    yesterday: _startOfDay(n, -1),
    thisWeek:  _startOfWeek(n, 0),
    lastWeek:  _startOfWeek(n, -1),
  };
}
function _convGroupLabel(iso, b) {
  const t = iso ? new Date(iso).getTime() : NaN;
  if (!t) return 'Older';                  // undated rows sink to the bottom group
  if (t >= b.today)     return 'Today';
  if (t >= b.yesterday) return 'Yesterday';
  if (t >= b.thisWeek)  return 'This week';
  if (t >= b.lastWeek)  return 'Last week';
  // Older than last week: label by calendar month (SEPTEMBER), or by year
  // once the month is not the current one (2025, 2024). The list is walked
  // newest-first, so same-month rows collapse under one header naturally.
  const d = new Date(t);
  const now = new Date();
  if (d.getFullYear() !== now.getFullYear()) return String(d.getFullYear());
  return _MONTHS[d.getMonth()];
}
const _MONTHS = ['JANUARY','FEBRUARY','MARCH','APRIL','MAY','JUNE','JULY','AUGUST','SEPTEMBER','OCTOBER','NOVEMBER','DECEMBER'];

// Panel head counter ("19 · 1 pinned"). The sidebar head is a label for the
// list, so it has to move whenever the list does — every exit of
// refreshConversationList calls this, including the empty path.
function _setConvCount(total, pinned) {
  const el = $('convCount');
  if (!el) return;
  if (!total) { el.textContent = ''; return; }
  el.textContent = pinned ? total + ' \u00b7 ' + pinned + ' pinned' : String(total);
}

async function refreshConversationList() {
  const ul = $('convList');
  if (!ul) return;
  // Never replace the rows while a row is being dragged: the dragged <li> is the
  // drag's source node, and destroying it kills `dragend` and hangs the whole
  // drag session. Replay once the drag finishes (_endConvDrag).
  if (_convDragging) { _convRefreshPending = true; return; }
  let list = await listConversations();
  updateConvAlerts(new Set(list.map(c => c.id)));   // before the search filter narrows it

  const searchInput = $('convSearch');
  const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
  if (query) {
    list = list.filter(c =>
      c.title.toLowerCase().includes(query) ||
      (c.messageContent && c.messageContent.includes(query))
    );
  }

  // listConversations() scans the ACTIVE conversation dir only, so nothing here
  // is ever archived — the archive is reachable from the link row below and from
  // Settings → Archive, which has its own (cloud-backed) search.
  const pinned   = list.filter(c => c.pinned);
  const regular  = list.filter(c => !c.pinned);


  const frag = document.createDocumentFragment();
  if (!list.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = query
      ? 'No chats match "' + query + '"'
      : (Sandpie.initialSyncDone() ? '(no chats yet)' : 'Loading…');
    frag.appendChild(li);
    if (query) frag.appendChild(_archiveSearchLink(query));
    ul.replaceChildren(frag);
    _setConvCount(0, 0);
    return;
  }
  // selorder must stay the row's position among [data-cid] rows in DOM order —
  // the click handler uses it to index _selectedRowCids() for shift-ranges. One
  // running counter across every group keeps that true; group headers carry no
  // data-cid, so every selection path (highlight, range, rubber band) skips them
  // already, without needing to know they exist.
  let order = 0;
  const addRow  = (c) => frag.appendChild(buildConvLi(c, order++));
  const addHead = (text) => {
    const li = document.createElement('li');
    li.className = 'conv-group';
    li.dataset.group = text;
    // The header row is the control itself -- no inner button. role+tabindex
    // keep it operable by keyboard; the rubber band still works because its
    // listener is on the <ul> and only bails inside an li[data-cid].
    li.setAttribute('role', 'button');
    li.tabIndex = 0;
    li.innerHTML = '<span class="cg-label"></span><span class="cg-n"></span>';
    li.querySelector('.cg-label').textContent = text;
    li.addEventListener('click', (ev) => {
      if (ev.shiftKey) return;        // leave shift for selection gestures
      ev.stopPropagation();
      _cgToggle(li);
    });
    li.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      ev.preventDefault();
      _cgToggle(li);
    });
    frag.appendChild(li);
  };

  if (query) {
    // Flat while searching: matches span every bucket, so date headers would
    // shatter the results into one-row groups that say nothing.
    pinned.forEach(addRow);
    regular.forEach(addRow);
    frag.appendChild(_archiveSearchLink(query));
  } else {
    if (pinned.length) addHead('Pinned');
    pinned.forEach(addRow);
    const bounds = _convGroupBounds();
    let group = null;
    for (const c of regular) {
      const label = _convGroupLabel(c.updated, bounds);
      if (label !== group) { addHead(label); group = label; }
      addRow(c);
    }
  }
  ul.replaceChildren(frag);
  _cgApplyAll();               // headers are only walkable once they are in the DOM
  _setConvCount(order, pinned.length);
}
// Search only covers the active conversations the sidebar holds. Rather than
// quietly return nothing for something that aged out, every search ends with a
// row into Settings → Archive, carrying the query — that tab already searches
// archived content through the cloud, which the sidebar cannot do locally.
function _archiveSearchLink(query) {
  const li = document.createElement('li');
  li.className = 'conv-arch-link';
  li.textContent = 'Search the archive for "' + query + '"';
  li.title = 'Archived conversations are not in this list';
  li.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (window.SandpieArchive) SandpieArchive.openWith(query);
    else if (window.SandpieSettings) SandpieSettings.open('archive');
  });
  return li;
}
function refreshSendButtonForActive() {
  refreshSendButtonFor('main');
  refreshSendButtonFor('side');
}
function refreshSendButtonFor(which) {
  const btn = which === 'side' ? $('sendBtnSide') : $('sendBtn');
  if (!btn) return;
  const convId = _composerConv(which);
  // Resolve STRICTLY to this pane's own mounted conversation — never fall back to
  // activeStream(). activeStream() follows whichever pane is FOCUSED (focusPane
  // sets activeConvId), so an empty pane would borrow the OTHER pane's state: e.g.
  // an empty side pane (or the home-screen main pane) showing Stop (■) because the
  // other pane's conversation is generating. A pane with no conversation is idle
  // (▶); its composer starts/sends into that pane.
  const s = convId ? convStreams.get(convId) : null;
  if (s && s.generating) {
    btn.innerHTML = '<span class="ic-stop"></span>';
    btn.title = 'Stop';
    btn.classList.add('sending');
    btn.disabled = false;
  } else {
    btn.innerHTML = '<span class="ic-play"></span>';
    btn.title = 'Send';
    btn.classList.remove('sending');
    btn.disabled = false;
  }
}
function setStreamSending(stream, sending) {
  if (!stream) return;
  if (sending) {
    stream.abort = new AbortController();
    stream.generating = true;
    // Streaming drives scroll manually (token-by-token scroll-to-bottom), so turn
    // OFF the conv-host's default overflow-anchor for the turn — anchoring would
    // fight the follow. Single source of truth for the class (tracks generating).
    try { if (stream.host) stream.host.classList.add('sp-streaming'); } catch (_) {}
    // A new turn starts fresh — clear any stale pending-ask flag for this conv
    // (left behind if a previous turn was aborted mid-question).
    _askingConvs.delete(activeConvId);
  } else {
    stream.abort = null;
    stream.generating = false;
    // Ends off-screen (including an abort — the work stopped either way, and
    // there is something to come back to) → it becomes a badge on the toggle.
    try {
      if (stream.id && !_convOnScreen(stream.id)) _doneUnseen.add(stream.id);
      updateConvAlerts();
    } catch (_) {}
    // Turn ended (normal or abort) → restore default anchoring so reading/loading
    // never jiggles.
    try { if (stream.host) stream.host.classList.remove('sp-streaming'); } catch (_) {}

    for (const el of stream.host.querySelectorAll('.tool-call')) {
      if (el.querySelector('.tc-prompt')) continue;
      el.classList.remove('in-flight');
      renderTcDone(el, el.dataset.fname);
    }
    // Settle every register's strip (no pulsing cells after the turn ends) and
    // end the current group so the next turn opens a fresh block.
    for (const g of stream.host.querySelectorAll('.msg.tool-group')) tgUpdate(g);
    tgBreak(stream.host);
  }
  // Repaint the composer buttons unconditionally. Gating this on
  // `stream === activeStream()` meant a turn that ended while its conversation
  // wasn't the active one left the Stop (■) button stuck; refreshSendButtonFor*
  // re-resolves each pane's own conversation state, so an unconditional call is
  // both correct and idempotent, and guarantees ■ → ▶ on every turn end.
  refreshSendButtonForActive();

  refreshConversationList();
}
// Resume eligibility: a turn is resumable iff its last message did NOT finish
// normally. finish_reason is 'stop' only for a completed final assistant turn; any
// other case (user/tool tail, tool_calls/length, or a truncated message with no
// recorded finish_reason) resumes. Single guard, per design.
function isResumable(messages) {
  const m = messages[messages.length - 1];
  if (!m) return false;
  return m.finish_reason !== 'stop';
}
function isResumableActive() {
  const s = activeStream();
  return !!(s && s.messages && s.messages.length && isResumable(s.messages));
}

// The conversation a pane is actually showing, read from the DOM: whichever
// .conv-host is mounted in it. The DOM is the single source of truth — deriving
// this from activeConvId/sideId instead is how the main composer ended up
// appending to the conversation displayed in the OTHER pane.
// Returns null when the pane shows no conversation (home screen); callers then
// create one, rather than hijacking the other pane's.
function paneConvId(pane) {
  const host = pane && pane.querySelector && pane.querySelector(':scope > .conv-host');
  const id = host && host.dataset ? host.dataset.convId : '';
  return (id && convStreams.has(id)) ? id : null;
}
// Which conversation a composer submits into: 'main' → #messages, 'side' → #messagesSide.
function _composerConv(which) {
  return paneConvId(which === 'side' ? $('messagesSide') : $('messages'));
}
// There is a single #commandOutput panel, so it has to FOLLOW the pane that ran
// the command — otherwise a `>>>` command typed in the side panel printed its
// output into the main pane. Always lands directly above that pane's composer.
function _commandPanelTo(pane) {
  const panel = $('commandOutput');
  if (!panel || !pane || panel.parentNode === pane) return;
  // Insert ABOVE the msg-timer-slot, not the composer: the cluster order the rest
  // of the code relies on is [.cmd-output, .msg-timer-slot, .composer] — that is
  // what paneBottomAnchor anchors conv-host mounts against. Dropping the panel
  // between slot and composer left the slot ABOVE the next mounted conv-host
  // (the "timer bar renders at the top of the conversation" bug).
  const anchor = pane.querySelector(':scope > .msg-timer-slot') || pane.querySelector(':scope > .composer');
  if (anchor) pane.insertBefore(panel, anchor); else pane.appendChild(panel);
}
// Route the shared command panel to the pane that an element lives in, then
// show content there. Used by timer badges (mt-todos) that can sit in either
// pane — without this the single #commandOutput stays parked in the main pane
// and the side panel's checklist opens in the wrong conversation.
function showCmdPanelForEl(el, content, title) {
  const pane = el && el.closest ? el.closest('#messages, #messagesSide') : null;
  if (pane) _commandPanelTo(pane);
  if (typeof SandpieCommandView !== 'undefined') SandpieCommandView.show(content, title);
}
// The command panel shows a checklist SNAPSHOT (the badge click builds it once),
// so a write_todos landing while it's open would leave stale rows on screen.
// Called from renderTodos on every checklist update: if the panel is open, is
// showing the Checklist, and lives in the same pane as the conversation that
// updated (the panel is a single shared element — the OTHER pane's checklist
// must not be overwritten), rebuild its content in place.
function refreshOpenChecklistPanel(todos, scopeEl) {
  const panel = $('commandOutput');
  if (!panel || panel.style.display === 'none') return;
  const prompt = panel.querySelector('.cmd-prompt');
  if (!prompt || prompt.textContent !== '>>> Checklist') return;
  const panelPane = panel.closest('#messages, #messagesSide');
  const convPane = scopeEl && scopeEl.closest ? scopeEl.closest('#messages, #messagesSide') : null;
  if (panelPane && convPane && panelPane !== convPane) return;
  if (typeof SandpieCommandView !== 'undefined') SandpieCommandView.show(buildTodosView(todos || []), 'Checklist');
}
async function handleSubmit(which = 'main') {
  // Sending must end any live dictation first - stopRecording flushes the
  // dictated tail into the box before the text below is read. It is idempotent
  // and a no-op when dictation is already idle.
  try { if (window.SandpieSpeech) window.SandpieSpeech.stopRecording(); } catch (_) {}
  const ta = which === 'side' ? $('inputSide') : $('input');
  const pane = which === 'side' ? $('messagesSide') : $('messages');
  if (!ta || !pane) return;
  _commandPanelTo(pane);   // `>>>` output belongs in the pane it was typed in
  const text = ta.value.trim();
  // No fallback to activeConvId: when this pane shows nothing, submitting must
  // start a fresh conversation here, not append to whatever the other pane shows.
  const convId = _composerConv(which);
  if (!text && !SandpieImages.hasAttachment(which)) {
    // Empty submit resumes an interrupted turn instead of doing nothing — but only
    // when the conversation is resumable (last message didn't finish with 'stop').
    // No auto-resume on load; the user opts in by pressing Enter / send.
    // Resumability is checked on THIS pane's own conversation, NOT isResumableActive()
    // (which reads activeStream = the FOCUSED pane) — otherwise an empty Enter in one
    // pane could resume based on the OTHER pane's state (cross-pane coupling).
    const s = convId ? ensureStream(convId) : null;
    if (s && isResumable(s.messages)) {
      if (s.generating) return;   // a turn is already running — never start a second loop
      if (s.host.parentNode !== pane) _mountInPane(s.host, pane);
      await sendSingle('', s, { resume: true });
    }
    return;
  }
  if (typeof SandpieCommands !== 'undefined' && text.startsWith('>>>')) {
    const handled = await SandpieCommands.dispatch(text);
    if (handled) {
      // A command may itself populate the composer (>>> rewind restores the
      // rewound text into the pane's input box). Only clear the typed command
      // when the command didn't replace it — otherwise the restored text is
      // written and then wiped in the same task and never visibly lands.
      if (ta.value.trim() === text) ta.value = '';
      return;
    }
    // >>> is reserved. If it's not a real command, reject and show help.
    const rest = text.slice(3).trim();
    const cmdName = rest.split(/\s+/)[0] || '???';
    if (SandpieCommandView) {
      SandpieCommandView.show('"' + cmdName + '" is not a command.', 'help');
      SandpieCommands.dispatch('>>> help');
    }
    ta.value = '';
    return;
  }
  if (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.showRelevance) SandpieAugmentations.showRelevance(text, convId).catch(() => {});
  // Clear command output on normal chat submit
  if (SandpieCommandView) SandpieCommandView.hide();
  ta.value = '';

  // Attachments are per-composer: build and clear THIS pane's, or submitting in
  // one pane would consume (and wipe) whatever the other pane had staged.
  const content = await SandpieImages.buildContent(text, which);

  if (SandpieImages.hasAttachment(which)) {
    SandpieImages.clear(which);
  }
  const scEl = paneScrollEl(pane);
  lockScroll(scEl);
  scEl.scrollTop = scEl.scrollHeight;
  // Typing into a pane focuses it — otherwise the send/stop button and the
  // conversation list would keep tracking the other pane. Must run BEFORE the
  // round is awaited: after `await enqueueFor(...)` it only executed when the
  // round FINISHED, and stole focus back from whatever pane the user had moved
  // to in the meantime (the round-end focus-shift bug).
  if (sidePanel?.isOpen && sidePanel.activeIsRight !== (which === 'side')) {
    sidePanel.focusPane(which === 'side');
  }
  await enqueueFor(convId, content, pane);

  if (ta) ta.style.height = 'auto';
}
// Mount a conv host into a pane, keeping the pane's bottom cluster (command panel
// + sticky composer) pinned below it.
function _mountInPane(host, pane) {
  if (!host || !pane) return;
  if (host.parentNode !== pane) {
    if (host.parentNode) host.parentNode.removeChild(host);
    // A pane may hold at most one conversation host. Evict ANY other host
    // already mounted here, so a misrouted mount can never stack two
    // conversations in the same pane (this is the structural guarantee the
    // callers rely on — the double-conv-host drag bug was a caller failing it).
    if (pane.querySelectorAll) {
      for (const el of Array.from(pane.querySelectorAll(':scope > .conv-host'))) {
        if (el === host) continue;
        _evacuateHome(el);
        el.parentNode.removeChild(el);
      }
    }
    appendContent(pane, host);
  }
  // The conv-host is now the scroll container — its lock/unlock listeners have
  // to live on it, not on the pane. Guard against double-binding on re-mount.
  if (!host.dataset.spTracked) { setupScrollTracking(host); host.dataset.spTracked = '1'; }
  _placeHome();
  refreshPaneBar(pane);
}
// #homeCenter (pinned grid + shared/team inbox) is CACHED by reference, never
// re-looked-up by id: once it rides a conv-host out of the document,
// getElementById can't see it any more and the home lists vanish for good.
let _homeCenterEl = null;
function _homeEl() {
  if (!_homeCenterEl || !_homeCenterEl.isConnected) {
    _homeCenterEl = _homeCenterEl || document.getElementById('homeCenter');
  }
  return _homeCenterEl;
}
// First live user message lands in a fresh conversation: fade the home screen
// (pinned grid + shared lists) out instead of letting it stay anchored above the
// first bubble. Runs ONLY from the live send path (addMsg animate=true); a load
// replay can't trigger it. A brand-new chat gets a new empty host, so re-arm is
// automatic (._placeHome clears .home-leave + --home-h when the host has no
// message yet, letting the box spring back open).
function _fadeHomeOnFirst(host) {
  if (!host) return;
  const hc = _homeEl();
  if (!hc || !hc.isConnected) return;
  if (host._homeFading || !host.contains(hc)) return;
  let first = true;
  for (const c of host.children) {
    if (c !== hc && c.classList && c.classList.contains('msg')) { first = false; break; }
  }
  if (!first) return;                       // only the very first message retires it
  host._homeFading = true;
  // Drive the collapse from the home page's own measured height so the outgoing
  // box closes cleanly and the first message below rides up into its place —
  // not snapping once a display:none retirement drops the whole list at once.
  try { hc.style.setProperty('--home-h', Math.ceil(hc.getBoundingClientRect().height) + 'px'); } catch (_) {}
  hc.classList.remove('home-leave');
  void hc.offsetWidth;                      // restart the animation if re-shown
  hc.classList.add('home-leave');
}
// Put the home lists where they belong: first child of the LEFT pane's conv-host
// when one is mounted (so they scroll with the conversation), else the left pane
// itself above its bottom cluster. Always the left pane — the home screen only
// ever lives there, so a host removed from the SIDE pane must not drag the lists
// into #messagesSide (that left the main pane empty and the lists stranded).
function _placeHome() {
  const hc = _homeEl();
  const pane = $('messages');
  if (!hc || !pane) return;
  // Undo a fade-out retire (_fadeHomeOnFirst): clear the collapse class + the
  // measured height so the box springs back open and takes up space again.
  const unretire = () => {
    if (hc.classList.contains('home-leave')) hc.classList.remove('home-leave');
    try { if (hc.style.getPropertyValue('--home-h')) hc.style.removeProperty('--home-h'); } catch (_) {}
  };
  const host = pane.querySelector(':scope > .conv-host');
  if (host) {
    if (hc.parentNode !== host || host.firstChild !== hc) host.insertBefore(hc, host.firstChild);
    // Show the home screen ONLY for the welcome state: no conversation, or a
    // brand-new chat with zero messages. Decide from the STREAM, not the DOM —
    // a historical load wipes the host (innerHTML='') and only re-renders the
    // messages AFTER _placeHome() returns, so a DOM-only check reads an empty
    // host at that instant and wrongly springs the home box back open above a
    // loaded conversation.
    const convId = host.dataset && host.dataset.convId;
    const st = convId ? convStreams.get(convId) : null;
    const hasMsg = (st && st.messages && st.messages.length > 0)
      || [...host.children].some(c => c !== hc && c.classList && c.classList.contains('msg'));
    if (!hasMsg) {
      host._homeFading = false;
      unretire();   // welcome / brand-new empty chat
    } else if (!hc.classList.contains('home-leave')) {
      // A conversation with messages is on screen — the welcome box must stay
      // retired (collapsed to 0 height). Force it even on a fresh host mount of
      // an old conversation (boot restore of a historical conv), so its loaded
      // transcript never reveals the home screen above it.
      try { hc.style.setProperty('--home-h', Math.ceil(hc.getBoundingClientRect().height) + 'px'); } catch (_) {}
      hc.classList.add('home-leave');
      host._homeFading = true;
    }
  } else {
    if (hc.parentNode !== pane) appendContent(pane, hc);
    // No conversation mounted → the home screen IS the pane's content and must be
    // visible. Deleting a conv whose first message had faded the home box used to
    // evacuate it back STILL COLLAPSED (opacity 0, max-height 0): nothing filled
    // the pane and the timer-slot + composer cluster floated to the top.
    unretire();
  }
}
// Move the home lists out of a host that is about to be detached, so they stay
// in the document. Call BEFORE removeChild, never after.
function _evacuateHome(host) {
  const hc = _homeEl();
  if (hc && host && host !== hc && host.contains(hc)) appendContent($('messages'), hc);
  if (host && host.parentNode) refreshPaneBar(host.parentNode);
}
async function enqueueFor(convId, content, pane) {
  if (!convId) { await ensureActiveConv(); convId = activeConvId; }
  const s = ensureStream(convId);
  if (pane) _mountInPane(s.host, pane);
  // Steer into the active agent loop when generating, otherwise send directly.
  // No agentId requirement: in the pre-send window (compaction/config build)
  // steerActive buffers, and sendSingle posts the buffer once the loop starts —
  // falling through to sendSingle here would spawn a second concurrent loop and
  // orphan the running turn's stop wiring.
  if (s.generating && _canSteerActive()) {
    steerActive(s, content);
    return;
  }
  await sendSingle(content, s);
}
async function enqueueForActive(content) {
  await ensureActiveConv();
  await enqueueFor(activeConvId, content, $('messages'));
}
// Every provider is steerable now that local engines are removed.
function _canSteerActive() { return true; }
function steerActive(s, content) {
  // Render a provisional bubble now for immediate feedback; the authoritative
  // array insert + persistence happen when the worker echoes it back as a
  // message_added event (RoundRenderer.bindMessage reconciles against this list).
  const el = addMsg('user', content, s.host, true);
  (s._pendingSteer = s._pendingSteer || []).push({ el, content, msg: null });
  // No agentId yet — the turn is in its pre-send window (compaction / config
  // build). Buffer the steer; sendSingle posts it the moment the loop starts.
  // Posting to a null id would silently drop the user's message.
  if (!s.agentId) { (s._earlySteer = s._earlySteer || []).push(content); return; }
  try { getSandpieWorker().postMessage({ type: 'steer', id: s.agentId, content }); } catch (_) {}
}
function handleButtonClick(which = 'main') {
  const btn = which === 'side' ? $('sendBtnSide') : $('sendBtn');
  if (!btn) return;
  const convId = _composerConv(which);
  // STRICTLY this pane's own conversation — never activeStream(). activeStream()
  // follows the FOCUSED pane, so an empty pane's button (with convId null) used to
  // act on the OTHER pane's turn. Each pane's button controls only its own pane.
  const s = convId ? convStreams.get(convId) : null;
  // Stop ONLY this pane's turn. sandpie runs an independent per-conversation loop
  // per pane (single-flight is per-conv), so a turn generating in the OTHER pane
  // is a separate, valid turn — this button must never cancel it. (The old global
  // stop cancelled EVERY live turn on any click — the button "entanglement".)
  if (s && s.generating) {
    // Abort this turn's page-side pre-send fetches too (the pool self-drains and
    // pre-send work is brief), then stop this pane's stream. Other panes untouched.
    for (const c of Array.from(_pageAbortPool)) { try { c.abort(); } catch (_) {} }
    stopStream(s);
    refreshSendButtonFor(which);
    return;
  }
  // Stale ■ (button says sending but this pane's stream isn't live — an orphaned
  // worker loop after a tab freeze). Best-effort abort THIS pane's last known
  // agent id (idempotent on the worker), then resync the button. No other pane.
  if (btn.classList.contains('sending')) {
    const aid = s && (s.agentId || s._lastAgentId);
    if (aid) { try { getSandpieWorker().postMessage({ type: 'abort', id: aid }); } catch (_) {} }
    refreshSendButtonFor(which);
    return;
  }
  // Idle → submit into THIS pane. A second loop on the same conversation is
  // prevented by sendSingle's per-conversation single-flight, so no global stop is
  // needed here.
  window.handleSubmit(which);
}


// One stop channel helper shared by the pane-local and the global stop path: the
// page-side controller (errors the event bridge → 'Stopped.'), plus a direct
// worker abort by agent id in case this turn's bridge was ever orphaned. The
// worker handler is idempotent, so a double abort is harmless. Falls back to the
// last known id if agentId was cleared out from under a still-live loop.
function stopStream(s) {
  if (s.abort) s.abort.abort();
  const aid = s.agentId || s._lastAgentId;
  if (aid) { try { getSandpieWorker().postMessage({ type: 'abort', id: aid }); } catch (_) {} }
}

// Page-side pre-send fetches (compaction summary, auto-title) run BEFORE the
// turn has a worker agent id, so a worker abort cannot reach them. They register
// their AbortController here so a Stop click can cancel them directly.
const _pageAbortPool = new Set();

// The one true "stop everything" used by every stop path: kill page-side
// pre-send fetches, the pane's own stream, any OTHER generating stream, and
// (belt-and-braces) post abort-all so the worker kills every live agent even if
// an id was lost. Every post is idempotent on the worker.
function stopEverything(s) {
  for (const c of Array.from(_pageAbortPool)) { try { c.abort(); } catch (_) {} }
  if (s) stopStream(s);
  for (const st of convStreams.values()) {
    if (st !== s && st.generating) stopStream(st);
  }
  try { getSandpieWorker().postMessage({ type: 'abort-all' }); } catch (_) {}
}
// ---- Sandpie Web Worker — Pyodide + tools + agent loop ----------------------
// Created once per page load. Other modules reach it via window._sandpieWorker.
let _askingConvs = new Set();    // conversation ids with a pending ask( ) question
let _sandpieWorker = null;
function getSandpieWorker() {
  if (_sandpieWorker) return _sandpieWorker;
  // Lives under modules/ (served wholesale by sandpie-server) rather than the
  // web root, where brand-new files have no route and 404. Path resolves against
  // the document base (root) → /modules/sandpie-worker.js.
  _sandpieWorker = new Worker('./modules/sandpie-worker.js?v=232');
  window._sandpieWorker = _sandpieWorker;

  /* ---- Suspension labeling: forward page visibility to the worker. The worker's
     per-turn heartbeat measures HOW LONG the turn was frozen; this tells it WHY —
     hidden (tab backgrounded / Chrome froze it) vs a foreground stall. Both
     visibilitychange and the Page-Lifecycle freeze/resume events feed one flag;
     freeze always implies hidden, resume restores the true visibility state. ---- */
  {
    const postVis = (hidden) => {
      try { _sandpieWorker.postMessage({ type: 'visibility', hidden: !!hidden }); } catch (_) {}
    };
    postVis(document.hidden);   // seed initial state
    document.addEventListener('visibilitychange', () => postVis(document.hidden));
    document.addEventListener('freeze', () => postVis(true));
    document.addEventListener('resume', () => postVis(document.hidden));
  }

  /* ---- Artifact auto-reload (rendered mode) — per-path trailing-edge debounce.
     Worker writes (edit_file / write_file / run_python / copy_to_workspace /
     remember) that touch an OPEN artifact fire at most one reload per path per
     ARTIFACT_RELOAD_MS, but a change arriving INSIDE the window still schedules a
     trailing reload once the window closes — so the final state of an LLM turn is
     always shown, never cancelled by an earlier reload. ---- */
  const ARTIFACT_RELOAD_MS = 5000;
  const _artifactReload = new Map();   // path -> { last, pending, timer }
  function artifactChanged(path) {
    if (!path) return;
    const now = Date.now();
    let st = _artifactReload.get(path);
    if (!st) { st = { last: 0, pending: false, timer: null }; _artifactReload.set(path, st); }
    if (now - st.last >= ARTIFACT_RELOAD_MS) {
      if (st.timer) { clearTimeout(st.timer); st.timer = null; }
      st.last = now; st.pending = false;
      emitArtifactChanged(path);
      return;
    }
    st.pending = true;
    if (!st.timer) {
      st.timer = setTimeout(() => {
        st.timer = null;
        if (st.pending) { st.pending = false; st.last = Date.now(); emitArtifactChanged(path); }
      }, st.last + ARTIFACT_RELOAD_MS - now);
    }
    // Bounded map: drop the oldest entry once a session has touched many paths.
    if (_artifactReload.size > 500) { const k = _artifactReload.keys().next().value; if (k !== undefined) _artifactReload.delete(k); }
  }
  function emitArtifactChanged(path) {
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('artifact:changed', path); } catch (_) {}
  }
  _sandpieWorker.addEventListener('message', (event) => {
    const msg = event.data;
    if (!msg) return;
    if (msg.type === 'sandpie-worker-log') {
      const fn = console[msg.level] || console.log;
      fn.call(console, '[worker]', msg.text);
      return;
    }
    if (msg.type === 'artifact-localizing') {
      // Deliverable localization runs off-turn (worker _lxQueue): the artifact
      // card shows English first, so surface a "translating…" badge until the
      // translated file swaps in.
      try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('artifact:localizing', { path: msg.path, state: msg.state, label: 'Translating…' }); } catch (_) {}
      return;
    }
    if (msg.type === 'forward-to-page') {
      // Relay opfs-deleted-by-python / sw-opfs-changed to existing SW message
      // listeners (dropbox.js) by dispatching onto navigator.serviceWorker.
      try { navigator.serviceWorker.dispatchEvent(new MessageEvent('message', { data: msg.payload })); } catch (_) {}
      // A worker write to sandpie/memory/*.md (e.g. remember()) reaches the page
      // ONLY as this sw-opfs-changed relay — surface it as memory:changed so the
      // sidebar refreshes and consolidation triggers (event-driven, not a clock).
      try {
        const paths = (msg.payload && msg.payload.type === 'sw-opfs-changed' && Array.isArray(msg.payload.paths)) ? msg.payload.paths : [];
        if (paths.some(p => /(^|\/)sandpie\/memory\/[^/]+\.md$/.test(p)) && typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('memory:changed', {});
        // Artifact auto-reload: forward worker writes to the open viewers,
        // debounced per path (leading edge now, trailing edge after the window).
        for (const p of paths) artifactChanged(p);
        // File deletion (delete_file tool OR python os.remove, relayed as the
        // historically-named opfs-deleted-by-python): reflect it — drop the card(s)
        // and the tracking entry so no 404 lingers.
        if (msg.payload.type === 'opfs-deleted-by-python' && Array.isArray(msg.payload.paths)) {
          reflectFileDeletes(msg.payload.paths);
        }
      } catch (_) {}
      // share() tool: the worker posts a share-request; perform it here (the page
      // owns Dropbox + sharing.js) and reply with the publish result.
      if (msg.payload && msg.payload.type === 'share-request') {
        const pr = msg.payload;
        (async () => {
          const reply = (result) => { try { _sandpieWorker.postMessage({ type: 'share-result', id: pr.id, result }); } catch (_) {} };
          try {
            const s = window.SandpieSharing;
            if (!s || typeof s.publish !== 'function') { reply('Error: sharing is not available on this page (SandpieSharing missing or not yet loaded).'); return; }
            // 1:1 was removed — the share tool publishes to a DEPARTMENT only.
            const dept = Array.isArray(pr.args.recipients) ? pr.args.recipients[0] : (pr.args.recipients || '');
            if (!dept) throw new Error('share: a department name is required (e.g. ["IT"]).');
            const out = await s.publish(pr.args.path, dept, { title: String(pr.args.path).split('/').pop(), pinFile: pr.args.pinFile || undefined });
            try { await s.autoSync(); } catch (_) {}
            reply('Shared "' + pr.args.path + '" to ' + dept + (out && out.id ? ' (' + out.id + ')' : '') + '.');
          } catch (e) {
            reply('Error sharing "' + pr.args.path + '": ' + ((e && e.message) || e));
          }
        })();
        return;
      }
      // html_console tool: the worker posts a console-request; the page reads the
      // artifact frame's captured console (readArtifactConsole in artifacts.js)
      // and replies with the entries.
      if (msg.payload && msg.payload.type === 'console-request') {
        const pr = msg.payload;
        (async () => {
          const reply = (result) => { try { _sandpieWorker.postMessage({ type: 'console-result', id: pr.id, result }); } catch (_) {} };
          try {
            const fn = window.readArtifactConsole;
            if (typeof fn !== 'function') { reply('Error: readArtifactConsole is not available on this page (artifacts.js not loaded or outdated).'); return; }
            const out = await fn(pr.args && pr.args.path);
            if (out && out.error) { reply('Error: ' + out.error); return; }
            const entries = (out && out.entries) || [];
            if (!entries.length) reply('(no console output captured — the artifact logged nothing, or its console buffer is empty)');
            else reply('Console for "' + (pr.args && pr.args.path || 'artifact') + '" (' + entries.length + ' entries):\n' + entries.join('\n'));
          } catch (e) {
            reply('Error reading console: ' + ((e && e.message) || e));
          }
        })();
        return;
      }
      // screenshot tool: the worker posts a screenshot-request; the page rasterizes
      // the artifact (screenshot.js) and replies with a JPEG data URL, its
      // dimensions, and any fidelity caveats worth telling the model about.
      if (msg.payload && msg.payload.type === 'screenshot-request') {
        const pr = msg.payload;
        (async () => {
          const reply = (payload) => { try { _sandpieWorker.postMessage({ type: 'screenshot-result', id: pr.id, payload }); } catch (_) {} };
          try {
            const s = window.SandpieScreenshot;
            if (!s || typeof s.capture !== 'function') {
              reply({ ok: false, error: 'screenshot.js is not loaded on this page' });
              return;
            }
            const out = await s.capture(pr.args && pr.args.path, (pr.args && pr.args.opts) || {});
            reply({ ok: true, dataUrl: out.dataUrl, width: out.width, height: out.height, warnings: out.warnings || [], mode: out.mode || 'fresh-render' });
          } catch (e) {
            reply({ ok: false, error: (e && e.message) || String(e) });
          }
        })();
        return;
      }
      // walios office→PDF: the worker posts an office-convert-request on behalf of a
      // guest (`import soffice` in run_python, or `soffice --convert-to pdf` in the
      // walios shell). Convert with the same ZetaOffice engine the file viewer uses
      // (opfs._officeEngine) and hand the PDF bytes back; the worker writes them into
      // OPFS, where the guest's /root sees them.
      if (msg.payload && msg.payload.type === 'office-convert-request') {
        const pr = msg.payload;
        (async () => {
          const reply = (payload) => { try { _sandpieWorker.postMessage({ type: 'office-convert-result', id: pr.id, payload }); } catch (_) {} };
          try {
            const o = window.opfs;
            if (!o || typeof o._officeEngine !== 'function') { reply({ ok: false, error: 'opfs.js on this page has no office engine (outdated assets — hard-reload the page)' }); return; }
            if (!self.crossOriginIsolated) { reply({ ok: false, error: 'this page is not cross-origin isolated, so LibreOffice-WASM cannot run here (it needs the COOP/COEP headers prod and coiserver.py send)' }); return; }
            const engine = await o._officeEngine();
            if (!engine) { reply({ ok: false, error: 'the office engine is unavailable on this page' }); return; }
            const pdf = await engine.convert(pr.args.bytes, pr.args.ext);
            reply({ ok: true, pdf });
          } catch (e) {
            reply({ ok: false, error: (e && e.message) || String(e) });
          }
        })();
        return;
      }
      // ask tool: the worker posts a ask-question; the page renders the question
      // card into the conversation and waits for the user to click an option.
      if (msg.payload && msg.payload.type === 'ask-question') {
        const pr = msg.payload;
        // The generating conversation — NOT the currently-active one. The worker
        // includes its conv id; without it a background/side-panel ask would
        // render into whatever conversation is focused now.
        const convId = pr.convId || activeConvId;
        if (convId) _askingConvs.add(convId);
        // Reply is wired DIRECTLY into the card as its onAnswer callback — no
        // setTimeout/wireAsk* indirection (that path had a TDZ ReferenceError
        // that made the final 'Responder' button a silent no-op).
        const reply = (result) => {
          if (convId) _askingConvs.delete(convId);
          refreshConversationList();
          try { _sandpieWorker.postMessage({ type: 'ask-result', id: pr.id, result }); } catch (_) {}
        };
        renderQuestions(pr.tcId, pr.args && pr.args.questions, reply, pr.convId);
        refreshConversationList();
        return;
      }
      // Unhandled payload type. This happens when the worker is newer than the
      // page (a tool exists in sandpie-worker.js but its page-side handler is not
      // in this cached build) — previously the tool just hung until its timeout
      // with no clue why. Any worker that names its reply channel gets a fast,
      // explanatory failure instead of silence.
      if (msg.payload && msg.payload.replyType && msg.payload.id) {
        try {
          _sandpieWorker.postMessage({
            type: msg.payload.replyType,
            id: msg.payload.id,
            result: 'Error: this page build has no handler for "' + msg.payload.type + '". sandpie.html is running cached assets older than the worker — hard-reload the page (or unregister the service worker) to pick up the current build.',
            payload: { ok: false, error: 'page build has no handler for "' + msg.payload.type + '" (stale cached assets — hard-reload the page)' },
          });
        } catch (_) {}
      }
      return;
    }
    if (msg.type === 'managed-token-refreshed') {
      // The worker silently re-minted the managed session token after a 401; keep
      // the page-side provider + hidden #apiKey in sync so the next request is fresh.
      try { window.SandpieAccount?.applyRefreshedToken?.(msg.token); } catch (_) {}
      return;
    }
  });
  _sandpieWorker.postMessage({ type: 'flush-logs' });
  return _sandpieWorker;
}
// Eagerly create the Worker so Pyodide starts preloading on page boot.
// Stale-SW eviction (an old fetch handler intercepting the sandpie-worker.js
// request and stalling it as 'pending') is handled earlier by the kill-switch
// guard inlined at the top of sandpie.html's <head>, which runs before any
// module loads and unregisters every SW regardless of name/scope. By the time
// this module executes the page is already uncontrolled (or the guard has
// exhausted its retries), so we just create the Worker.
getSandpieWorker();

// Build a ReadableStream that bridges Worker {type:'event'} messages into the
// NDJSON format that readAgentEvents() expects, so the rest of sendSingle()
// works unchanged. When the abort signal fires the stream errors with AbortError.
function workerAgentStream(worker, id, signal) {
  const queue = [];
  let streamDone = false;
  let notify = null;      // resolve of the pull promise currently awaiting an event
  let failPull = null;    // reject of that same promise — used to ABORT it (see onAbort)
  let cleaned = false;

  // Idempotent teardown. `sendAbort` posts {type:'abort', id} so the worker's
  // agent loop actually stops (cascades to run_python kills, shell/fetch aborts
  // via _agentAborts). Detaches the message listener AND the abort listener so
  // neither leaks across turns.
  const cleanup = (sendAbort) => {
    if (cleaned) return;
    cleaned = true;
    worker.removeEventListener('message', messageHandler);
    if (signal) signal.removeEventListener('abort', onAbort);
    if (sendAbort) { try { worker.postMessage({ type: 'abort', id }); } catch (_) {} }
  };

  // When the turn's signal fires we CANNOT rely on the ReadableStream's cancel()
  // to reach the worker: aborting rejects pull(), which *errors* the stream, and
  // per the Streams spec an errored stream never invokes the source's cancel().
  // So do the worker abort + listener teardown here, directly off the signal.
  const onAbort = () => {
    cleanup(true);
    // REJECT the pending pull — do NOT resolve it. Resolving a pull that neither
    // enqueues nor closes does NOT make the ReadableStream pull again (no read
    // request arrives during the pull, so pullAgain is never set), so the stream
    // silently stalls: readAgentEvents' await reader.read() hangs forever, the
    // turn's finally never runs, and the UI stays stuck "generating" (Stop ■
    // frozen, timer counting, content frozen — the long-standing stop-feedback
    // bug). Rejecting errors the stream so read() rejects with AbortError, which
    // unwinds to sendSingle's catch → finally → the UI reset.
    const rej = failPull; notify = null; failPull = null;
    if (rej) rej(new DOMException('aborted', 'AbortError'));
  };

  const messageHandler = (event) => {
    const msg = event.data;
    if (!msg || msg.id !== id || msg.type !== 'event') return;
    queue.push(JSON.stringify(msg.event) + '\n');
    if (msg.event.type === 'agent_done' || msg.event.type === 'error') {
      streamDone = true;
      cleanup(false);   // natural end: detach listeners, worker already stopped
    }
    if (notify) { const n = notify; notify = null; failPull = null; n(); }
  };
  worker.addEventListener('message', messageHandler);
  if (signal) {
    if (signal.aborted) onAbort();   // aborted before we even wired up → stop the worker now
    else signal.addEventListener('abort', onAbort, { once: true });
  }

  const enc = new TextEncoder();
  return new ReadableStream({
    async pull(controller) {
      while (queue.length > 0) controller.enqueue(enc.encode(queue.shift()));
      if (streamDone) { controller.close(); return; }
      // Block until next event or abort signal fires.
      await new Promise((resolve, reject) => {
        notify = resolve;
        failPull = reject;
        // If the turn was already aborted between pulls, fail immediately.
        // Otherwise onAbort (registered once on the signal) rejects THIS promise
        // via failPull when the abort fires — that is what unwinds the stream.
        if (signal && signal.aborted) { failPull = null; reject(new DOMException('aborted', 'AbortError')); }
      });
      while (queue.length > 0) controller.enqueue(enc.encode(queue.shift()));
      if (streamDone) controller.close();
    },
    cancel() { cleanup(true); },
  });
}

async function sendSingle(text, stream, opts = {}) {
  // Single-flight per conversation: starting a second loop while one is
  // generating would replace stream.abort/stream.agentId and ORPHAN the running
  // turn's stop wiring — the stop button then aborts only the newest loop and
  // the old one becomes unstoppable. Reachable via the empty-composer resume,
  // resolveStoredAsk while a new turn runs, or the pre-agentId window below.
  // Steer real text into the running loop instead; drop redundant resumes.
  if (stream.generating) {
    const hasText = Array.isArray(text) ? text.length > 0 : !!(text && String(text).trim());
    if (hasText && !opts?.resume) steerActive(stream, text);
    return;
  }
  // Cross-tab single-writer: refuse to start a turn when another tab owns this
  // conversation (a second concurrent writer is how history blocks get
  // duplicated). Re-attempted on every send, so once the owning tab closes the
  // lock frees and this tab takes over seamlessly.
  if (!(await acquireConvWriterLock(stream.id))) {
    _notifyReadOnlyConv(stream);
    // Put the typed text back in this pane's composer so nothing is lost.
    if (typeof text === 'string' && text.trim()) {
      const pane = stream.host && stream.host.parentNode;
      const ta = (pane && pane.id === 'messagesSide') ? $('inputSide') : $('input');
      if (ta && !ta.value) ta.value = text;
    }
    return;
  }
  const { id: convId, messages: convMessages, host } = stream;

  // Render the user's message FIRST so it can never be lost. Even if the provider
  // config turns out to be incomplete, the message stays in the conversation and
  // the error appears after it — never in place of it.
  let wasAborted = false;
  let turnAgentId = null;   // this turn's worker agent id — used to guarantee the
                            // worker loop is aborted on EVERY exit path (see finally),
                            // so a finalized turn can never leave an orphaned loop.
  let userBubbleEl = null;
  if (!opts?.resume) {
    const userMsg = { role: 'user', content: text };
    convMessages.push(userMsg);
    userBubbleEl = addMsg('user', text, host, true);
    bindBubble(userBubbleEl, userMsg);
    // Awaited: the worker now appends committed messages to the JSONL itself,
    // starting from persisted_count. If this user-message save were still in
    // flight when the worker's first assistant reply lands, the reply would be
    // written at EOF BEFORE the user message — wrong order in the file.
    await saveConv(convId).catch(() => {});

    // Name the conversation NOW, from the user message alone, concurrently with
    // the generation below — so the sidebar shows a real title while the reply is
    // still streaming instead of after the turn ends. Fire-and-forget: it needs
    // nothing from this turn, and maybeAutoTitle itself is a no-op for anything
    // already titled/locked. The turn-end call remains as the retry fallback.
    // (History: reverted in 104c044 on a wrong diagnosis — the "thinks 3x" bug
    // was the force-respond retry loop, fixed in 6c4cc0d, not this concurrency.)
    maybeAutoTitle(convId).catch(() => {});
  }

  // Validate THIS conversation's provider (per-conv model; no global default).
  // On failure the message above is preserved.
  let _prov = null;
  try { _prov = SandpieProviders.resolve(convId); } catch (_) {}
  // Track the last-used provider as the app default: new chats (and convs that
  // never picked) follow whatever was actually used most recently.
  try { if (_prov && _prov.id) localStorage.setItem('sandpie-default-provider', _prov.id); } catch (_) {}
  if (!_prov || !(_prov.model || '').trim() || !(_prov.endpoint || '').trim()) {
    addMsg('err', 'This conversation has no usable model — pick one in the composer model picker (or add one in Settings → AI provider).', host);
    return;
  }
  requestWakeLock();
  setStreamSending(stream, true);

  // Proactive compaction: if the context threshold is met, run it BEFORE this turn
  // goes out so we never ship an over-limit request (and a conversation already at
  // the limit can still continue). Awaited so the now-smaller context is what gets
  // built below. Runs before startTotalTimer because compaction re-renders the
  // conversation host, which would otherwise drop a timer added first.
  // Compaction is NEVER skipped: if it was triggered but failed, halt the send with
  // a visible error rather than silently shipping an over-limit request.
  const _cmp = await maybeAutoCompact(convId);
  if (_cmp && _cmp.triggered && !_cmp.ok) {
    addMsg('err', 'Context is over the compaction threshold but summarizing the earlier turns failed (' + (_cmp.reason || 'unknown error') + '). The message was not sent — try again, or shorten the conversation.', host);
    setStreamSending(stream, false);
    releaseWakeLock();
    return;
  }

  startTotalTimer(stream);

  let config = await buildAgentConfig(convMessages, stream.compaction, stream.todos, convId);
  // Rerouted to the vision fallback — mark the user's bubble so the switch is visible.
  if (config.routedViaVision && userBubbleEl) {
    const mk = document.createElement('span');
    mk.style.cssText = 'display:block;font-size:0.7rem;color:var(--sp-text-dim);margin-top:0.25rem;';
    mk.textContent = '📷 described by ' + ((config.vision && config.vision.fallback && config.vision.fallback.model) || 'the vision model');
    userBubbleEl.appendChild(mk);
  }
  // Context limits are guarded three ways: maybeAutoCompact above (reported
  // tokens only), maybeCompactMidTurn in the worker (per-round reported tokens),
  // and the worker's reactive compact-and-retry on any over-context rejection
  // (413 or a 400 "maximum context length…").

  const ctrl = new AbortController();
  stream.requestId = ctrl;
  const onAbort = () => ctrl.abort();
  if (stream.abort?.signal) {
    if (stream.abort.signal.aborted) onAbort();
    else stream.abort.signal.addEventListener('abort', onAbort, { once: true });
  }

  const renderer = new RoundRenderer(host, convMessages, false, convId);

  let agentDoneSeen = false;
  let errorSeen = false;
  let lastInFlightTool = null;
  const dispatch = (ev) => {
    if (ev.type === 'agent_done')  agentDoneSeen = true;
    if (ev.type === 'error')        errorSeen = true;
    // Worker mid-turn compaction uses the SAME spinner as pre-send compaction.
    if (ev.type === 'compaction_start') { showCompactionProgress(convId); return; }
    if (ev.type === 'compaction_end')   { hideCompactionProgress(convId); return; }
    // Vision pre-step: the fallback described the attached image(s). Persist the
    // description ON the user message so later turns can ship it in place of the
    // image (see the stripImages branch in buildAgentConfig).
    if (ev.type === 'vision_caption') {
      const um = [...convMessages].reverse().find(m => m && m.role === 'user' && Array.isArray(m.content) && m.content.some(p => p && p.type === 'image_url'));
      if (um && Array.isArray(ev.captions)) {
        um._visionCaptions = ev.captions; um._visionModel = ev.model || '';
        // The user message is already on disk: an append-only save would skip it,
        // so force a full JSONL rewrite on the next save.
        const st = convStreams.get(convId); if (st) st._forceJsonlRewrite = true;
        scheduleIncrementalSave(convId);
      }
      return;
    }
    // Worker compacted its active slice mid-turn — advance the PAGE's persisted
    // boundary to match, so the NEXT send ships only [summary, …tail] and not
    // everything this turn piled up (the "sends way more than the active context"
    // bug). The worker keeps its NEWEST `kept` messages; those are the last `kept`
    // of convMessages, so boundary = convMessages.length - kept. Persisted by the
    // turn-end saveConv (reads stream.compaction).
    if (ev.type === 'message_compacted') {
      const kept = Math.max(0, ev.kept | 0);
      const boundary = convMessages.length - kept;
      if (boundary > 0 && ev.summary) {
        stream.compaction = { boundary, summary: ev.summary, at: new Date().toISOString() };
        // The stale reported usage still reflects the pre-compaction size; drop it so
        // the context meter + the pre-send trigger read the reduced send size.
        try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.forget) SandpieTokens.forget(convId); } catch (_) {}
      }
      return;
    }
    if (ev.type === 'tool_started') {
      lastInFlightTool = ev.tc?.function?.name || 'unknown';
      if (typeof SandpieAugmentations !== 'undefined') SandpieAugmentations.logToolStarted(activeConvId, ev.tc);
    }
    if (ev.type === 'scratchpad') { stream.scratchpad = ev.text || ''; }
    if (ev.type === 'tool_result') {
      lastInFlightTool = null;
      if (typeof SandpieAugmentations !== 'undefined') SandpieAugmentations.logToolResult(activeConvId, ev.result);
    }
    if (ev.type === 'usage') {
      stream.lastUsage = ev.usage;   // authoritative counts → settled tok/s + ctx counter
      Sandpie.events.emit('tokens:record', {convId, usage: ev.usage});
      reportTurnUsage(convId, ev.usage, convMessages.length, ev.model);
      // Round boundary: recordUsage just wrote the fresh reported size, so repaint
      // the live ctx counter now instead of waiting for the whole turn to end.
      { const _sl = _streamOwnsPaneSlot(stream) ? _timerSlotFor(stream) : null;
        if (_sl) _paintCtxCounter(_sl, convId); }
    }
    if (ev.type === 'rate') {
      // Per-round live tok/s (exact completion tokens / decode span). Accumulated
      // across the turn's rounds so the settled line shows the decode-only rate
      // (real model speed) instead of completion tokens over whole-turn wall time
      // (which dilutes the number with tool + queue time).
      const _ms = ev.decode_ms | 0;
      const _tk = ev.completion_tokens | 0;
      // Plausibility gate: some providers batch-report usage (or count cached
      // prefill as completion), yielding absurd burst rates (seen live: ~22k
      // tok/s). A round only counts when it streamed a plausible token count
      // over a plausible decode span; otherwise the previous rate is kept.
      if (_ms >= 250 && _tk >= 16 && (ev.bench || _tk / (_ms / 1000) < 400)) {
        stream.lastRate = _tk / (_ms / 1000);
        stream._turnToks = (stream._turnToks || 0) + _tk;
        stream._turnDecodeMs = (stream._turnDecodeMs || 0) + _ms;
        { const _sl = _streamOwnsPaneSlot(stream) ? _timerSlotFor(stream) : null;
          if (_sl) _paintRate(_sl, stream.lastRate, convId); }
      }
    }
    if (ev.type === 'degeneration') {
      reportDegeneration(ev);
    }
    if (ev.type === 'timing') {
      stream._turnProfile = ev.timing || null;   // kept for the rate popup (turn-time breakdown)
      reportTurnTiming(convId, ev.timing, convMessages.length);
    }
    if (ev.type === 'files_touched') {
      // File surfacing (replaces show_artifact): merge into the conversation's
      // deduped list (persisted via meta) and render cards. Partial events fire
      // mid-turn as files first appear (existing cards are left in place — the
      // artifact auto-reload keeps their content fresh); the final event
      // consolidates order (dedupe, most recently edited last).
      mergeFilesTouched(stream, ev.files);
      try { renderFilesTouched(host, ev.files, { partial: !!ev.partial }); } catch (_) {}
    }
    dispatchAgentEvent(ev, renderer, host);
  };
  try {

    { // always cloud worker — local engines removed
    const worker = getSandpieWorker();
    const _agentId = Math.random().toString(36).slice(2);
    stream.agentId = _agentId;   // steer target: enqueueForActive posts {type:'steer', id} here
    turnAgentId = _agentId;      // for the finally-abort safety net (survives agentId=null)
    stream._lastAgentId = _agentId;  // for the stop button to reach a loop even after finalize
    worker.postMessage({ type: 'agent', id: _agentId, config });
    // Steers buffered during the pre-agentId window (see steerActive) go out now,
    // after the 'agent' message, so the worker splices them at its first round
    // boundary. Their bubbles are already on screen via _pendingSteer.
    if (stream._earlySteer && stream._earlySteer.length) {
      for (const c of stream._earlySteer) { try { worker.postMessage({ type: 'steer', id: _agentId, content: c }); } catch (_) {} }
      stream._earlySteer = [];
    }
    const workerStream = workerAgentStream(worker, _agentId, ctrl.signal);
    await readAgentEvents(workerStream, dispatch);

    if (!agentDoneSeen && !wasAborted && !errorSeen) {
      const trigger = lastInFlightTool ? ` while running \`${lastInFlightTool}\`` : '';
      addMsg('err',
        `Worker died mid-stream${trigger} — typically a Pyodide WASM crash. The worker will be restarted on your next message.`,
        host,
      );
    }
    }   // end cloud-worker-only block
  } catch (e) {
    if (e && (e.name === 'AbortError' || ctrl.signal.aborted)) {
      wasAborted = true;
      // No "Stopped." info bubble — the settled timer already shows the stopped
      // state; a persisted info message here is just noise in the transcript.
    } else {
      console.error('[sandpie] agent fetch error:', e);
      addMsg('err', 'Error: ' + ((e && (e.message || String(e))) || 'unknown'), host);
    }
  } finally {

    if (stream.abort?.signal) stream.abort.signal.removeEventListener('abort', onAbort);
    stream.requestId = null;

    // local-LLM removed
    stream.agentId = null;   // no longer steerable once the loop has ended
    // Safety net: unconditionally tell the worker to abort THIS turn's loop on
    // every exit path (natural end, error, abort, or a "worker died mid-stream"
    // false positive after a tab freeze). The worker's abort handler is idempotent
    // — a no-op if the loop already finished — so this can only ever STOP a loop
    // the page has stopped tracking, never kill a live turn. Without it, a worker
    // loop that outlives its page-side stream (e.g. still retrying a connection
    // dropped while the tab was frozen) becomes an orphan the stop button can't
    // reach, because `generating` is already false.
    if (turnAgentId) { try { getSandpieWorker().postMessage({ type: 'abort', id: turnAgentId }); } catch (_) {} }
    // DOM/state reconciliation (finalize render, ask cards, steer replay) is wrapped
    // so a throw here can NEVER skip the UI teardown below (endTotalTimer +
    // setStreamSending). Without this, any error in finalize/reconcile stranded the
    // turn in the generating state — Stop looked dead: button stuck on ■, timer
    // still counting — even though the worker had aborted correctly.
    try {
      renderer.finalize();
      // A surviving ask card (turn aborted mid-question): keep it ANSWERABLE.
      // Answering appends the tool result and resumes the turn via resolveStoredAsk.
      for (const card of (stream.host ? stream.host.querySelectorAll('.ask-card') : [])) {
        if (!card._askState || card._askState.settled) continue;
        const tcId = card.dataset.askTcId;
        if (!tcId) continue;
        card._askState.settled = true;   // guard: wire once
        card._askState.onAnswer = (answers) => { resolveStoredAsk(convId, tcId, answers); };
      }
      // Reconcile any steer messages the loop never got to inject (turn aborted or
      // the worker died before the next round boundary): keep them in the history
      // so the user's input isn't lost — the next send will include them. Their
      // provisional bubbles are already on screen.
      if (stream._pendingSteer && stream._pendingSteer.length) {
        for (const p of stream._pendingSteer) {
          const already = stream.messages.includes(p.msg);
          if (!already) { const m = { role: 'user', content: p.content }; bindBubble(p.el, m); stream.messages.push(m); }
        }
        stream._pendingSteer = [];
      }
      // Any steer still buffered pre-post (agentId was already null) was just
      // reconciled into history above — drop the buffer or the NEXT turn's drain
      // would post it again on top of the history copy.
      stream._earlySteer = [];
      releaseWakeLock();
    } catch (e) { console.error('[sandpie] turn teardown reconcile error (UI still reset below):', e); }

    endTotalTimer(stream, wasAborted ? 'stopped' : 'done');
    // Refresh the context readouts (sidebar week total + badge, and any open ctx
    // popup) now the provider has reported this turn's authoritative usage.
    try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.notify) SandpieTokens.notify(); } catch (_) {}
    setStreamSending(stream, false);
    flushIncrementalSave(convId);
    await saveConv(convId);

    // Fallback titling pass: the title normally lands at send time (see above),
    // concurrently with the generation. This retries the ones that missed — the
    // send-time attempt failed (offline, unusable answer) or is still in flight
    // (the _titling guard makes this a no-op then). Awaited (the UI was released
    // above, so this costs no visible latency) so the new title is on disk before the sync below —
    // one write, one sync — and before the notification reads it.
    const _newTitle = await maybeAutoTitle(convId);

    // Optional capability: notifications.js (if loaded) listens for this and
    // fires a system toast. No listener ⇒ no-op. saveConv ran first so the
    // listener can read the canonical (possibly renamed) conv title.
    Sandpie.events.emit('generation:complete', { convId, aborted: wasAborted, title: _newTitle || undefined });
    try { await Sandpie.sync(); } catch (e) { console.warn('sync failed:', e); }
  }
}
// Expand a { type:'file' } attachment reference into a text part at send time.
// Small UTF-8 text files are inlined directly; binaries (and oversized text) are
// handed to the model as a workspace path it can open with the run_python tool —
// the SW mounts OPFS at /files (the tool's working dir), so the stored OPFS path
// is exactly what open() expects.
const ATTACH_INLINE_CAP = 200_000;   // chars of text inlined before falling back to a path reference
async function resolveFilePart(f) {
  const size = opfs.formatSize(f.size) || `${f.size || 0} B`;
  if (f.text) {
    try {
      const content = await opfs.read(f.path);
      if (content.length <= ATTACH_INLINE_CAP) {
        return `[Attached file "${f.name}" — saved at ${f.path}]\n\n${content}`;
      }
      return `[Attached file "${f.name}" — ${size} of text, saved at ${f.path}. Too large to inline; read it with the run_python tool, e.g. open(${JSON.stringify(f.path)}).read().]`;
    } catch (_) {
      return `[Attached file "${f.name}" is no longer available in the workspace.]`;
    }
  }
  return `[Attached file "${f.name}" — ${f.mime || 'binary'}, ${size}, saved at ${f.path}. Use the run_python tool to read it if you need its contents, e.g. open(${JSON.stringify(f.path)}, "rb").read().]`;
}
// Claude-mode (DEFAULT): swap the write_todos definition for a faithful clone
// of Claude Code's TodoWrite — same name so dispatch/grammar are untouched;
// the worker pairs it with the blind-replace tool implementation and drops the
// plan-first gate + open-todos stop guard (config.todoMode = 'claude').
// window.__todoV2 = 1 restores the guarded v2 tool (reconcile/delta/gates).
function _todoV2() { return !!(typeof window !== 'undefined' && window.__todoV2); }
function _todoLabTools(defs) {
  return (defs || []).map(d => {
    if (!d || !d.function || d.function.name !== 'write_todos') return d;
    return { ...d, function: { ...d.function,
      description: `Use this tool to create and manage a structured task list for your current session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:
1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work. Ideally you should only have one todo as in_progress at a time
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool
Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

## Task States and Management
1. Task States: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully
2. Task Management:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
3. Task Completion Requirements:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - Never mark a task as completed if tests are failing or implementation is partial
4. Task Breakdown:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names
   - Each task needs both "content" (imperative form, e.g. "Run tests") and "activeForm" (present continuous, e.g. "Running tests")

You send the FULL updated list on every call — it replaces the previous list.
LANGUAGE: author "content"/"activeForm" per the system language directive — in ENGLISH when an author-in-English directive is active (the checklist is translated for display), otherwise directly in the user's language.
When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully.`,
      parameters: {
        type: 'object',
        properties: {
          todos: {
            type: 'array',
            description: 'The updated todo list (replaces the previous list entirely).',
            items: {
              type: 'object',
              properties: {
                content:    { type: 'string', description: 'The task, in imperative form (e.g. "Run tests").' },
                status:     { type: 'string', enum: ['pending', 'in_progress', 'completed'], description: 'Task state. Only ONE task may be in_progress at a time.' },
                activeForm: { type: 'string', description: 'Present continuous form shown while in progress (e.g. "Running tests").' },
              },
              required: ['content', 'status', 'activeForm'],
            },
          },
        },
        required: ['todos'],
      },
    } };
  });
}
async function buildAgentConfig(convMessages, compaction, curTodos, convId) {
  // Non-destructive compaction: send [summary, …in-context tail] in place of the
  // full history so the model's context stays bounded. The full convMessages
  // still drives the system prompt (skill detection) below.
  let sendMessages = convMessages;
  if (compaction && compaction.boundary > 0 && compaction.boundary < convMessages.length) {
    sendMessages = [
      { role: 'user', content: SP_SUMMARY_MARKER + '\n\n' + compaction.summary },
      ...convMessages.slice(compaction.boundary),
    ];
  }
  // ---- Vision routing gate (yes/no only) --------------------------------
  // A model that can't see (vision:no, or a local in-browser engine) reroutes the
  // WHOLE turn to its configured vision fallback when the CURRENT message carries
  // images; text-only turns sent to it strip image_url parts from the history so
  // old image turns don't 400. An unset vision field keeps legacy behavior (can
  // see) — see SandpieProviders.providerCanSee.
  // PER-CONVERSATION provider: this conversation's own model (composer picker),
  // falling back to the catalog default when the conv has none set.
  const active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve)
    ? SandpieProviders.resolve(convId) : null;
  const canSee = (active && typeof SandpieProviders.providerCanSee === 'function')
    ? SandpieProviders.providerCanSee(active) : true;
  // "Current" means the message being sent NOW: the last user message, whatever
  // shape its content has. This used to search for the last user message with
  // ARRAY content, which silently skipped every plain-text follow-up (a typed
  // message is a string — SandpieImages.buildContent only returns an array when
  // something is attached). So once a conversation contained one image message it
  // stayed "current" forever: every later turn was rerouted to the vision
  // fallback, and stripImages below — the guard written for exactly this case —
  // never fired, so the image was re-resolved to base64 and resent every turn.
  const lastUser = [...sendMessages].reverse().find(m => m.role === 'user');
  const currentHasImages = !!(lastUser && Array.isArray(lastUser.content)
    && lastUser.content.some(p => p.type === 'image_url'));
  const visionFallback = (!canSee && typeof SandpieProviders.resolveVisionFallback === 'function')
    ? SandpieProviders.resolveVisionFallback(active) : null;
  // The conversation's OWN model is ALWAYS the turn's provider. When the current
  // message carries an image it cannot see, the worker asks the vision fallback
  // (config.vision.fallback, below) ONCE, with no tools, to describe the image, and
  // the description replaces the image for the whole agent loop. Routing the turn
  // itself here was the bug: one pasted screenshot moved every round of a 20-round
  // agentic turn to the fallback model (aezequiel, 2026-09-11).
  const effective = active;
  const routedViaVision = !!(!canSee && currentHasImages && visionFallback);
  const stripImages = !canSee && !currentHasImages;   // never silently drop a fresh attachment
  const resolvedMessages = [];
  for (const msg of sendMessages) {
    if (msg.role === 'user' && Array.isArray(msg.content)) {
      // A load_image result from an EARLIER turn: collapse the pixels back to a
      // text note. buildAgentConfig runs once per turn, before the worker adds
      // anything, so any _loadedImage message here already had its turn — the
      // model read it then, and re-sending the base64 on every later turn costs
      // context and bandwidth for an image nobody asked about again. It can always
      // call load_image on the same path to look again (the tool description says
      // so). Not applied to lastUser: an interrupted turn resumed right after
      // load_image still needs the real pixels.
      const collapseLoaded = !!msg._loadedImage && msg !== lastUser;
      const resolvedContent = [];
      for (const part of msg.content) {
        if (part.type === 'image_url' && collapseLoaded) {
          const p = String(part.image_url.url || '').replace(/^opfs:\/\//, '');
          resolvedContent.push({ type: 'text', text: '[image ' + p + ' was loaded earlier in this conversation and is no longer attached — call load_image("' + p + '") again to re-examine it]' });
          continue;
        }
        if (part.type === 'image_url' && stripImages) {
          // history image → not for a text-only model. If the vision pre-step described
          // it (persisted on the message as _visionCaptions), keep the description.
          const caps = Array.isArray(msg._visionCaptions) ? msg._visionCaptions : null;
          const idx = msg.content.filter(p => p.type === 'image_url').indexOf(part);
          if (caps && caps[idx]) resolvedContent.push({ type: 'text', text: '[Attached image ' + (idx + 1) + ', described by the vision model ' + (msg._visionModel || '') + ':\n' + caps[idx] + ']' });
          continue;
        }
        if (part.type === 'image_url' && part.image_url.url.startsWith('opfs://')) {
          const dataUrl = await SandpieImages.dataUrlFromPath(part.image_url.url.slice(7));
          if (dataUrl) {
            resolvedContent.push({ type: 'image_url', image_url: { url: dataUrl } });
          }
        } else if (part.type === 'file' && part.file) {
          resolvedContent.push({ type: 'text', text: await resolveFilePart(part.file) });
        } else {
          resolvedContent.push(part);
        }
      }
      resolvedMessages.push({ ...msg, content: resolvedContent });
    } else {
      resolvedMessages.push(msg);
    }
  }
  // PER-CONVERSATION reasoning effort: the composer model-picker slider stores
  // 'off'|'low'|'medium'|'high' on the stream/meta; null → the app default
  // (localStorage 'sandpie-default-reasoning'). Shipped to the worker, which
  // turns it into the OpenRouter `reasoning` / `reasoning_effort` param.
  const _rsnLevel = (() => {
    try {
      const cid = convId || activeConvId;
      const s = cid ? convStreams.get(cid) : null;
      const lv = (s && s.reasoningLevel) || null;
      if (lv) return lv;
      return (localStorage.getItem('sandpie-default-reasoning') || '').trim() || null;
    } catch (_) { return null; }
  })();
  const _ep = effective ? String(effective.endpoint || '').replace(/\/$/, '') : '';
  const _liteCfg = _liteOn(convId || activeConvId);
  const _sysPrompt = await buildSystemPrompt(convMessages, null);
  return {
    url: new URL(api(_ep + '/chat/completions', effective && effective.proxyUrl), location.href).href,
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ((effective && effective.apiKey) || '') },
    localize: null,   // display-side translation layer removed; language = system-prompt directive
    // Session reply language + the model's fluent set, for the worker's
    // per-call language rules (respond guard, subagent clause, deliverable
    // localization gate) — needed even when localize is null.
    replyLanguage: _replyLocale(),
    fluent: _modelFluent(),
    // Managed (company sign-in) provider only: let the worker silently re-mint the
    // session token from the SSO cookie via /auth/token on a 401, so an expired JWT
    // never interrupts the user mid-generation. null for personal providers — a 401
    // there is a real bad-key error, not a refreshable session.
    authRefreshUrl: (effective && effective.managed) ? new URL('/auth/token', location.href).href : null,
    _hermesMode: !!(effective && effective.type === 'hermes'),
    model: (effective && effective.model) || '',
    // Reasoning effort for this conversation ('off'|'low'|'medium'|'high'|null).
    // The worker maps it to the OpenRouter-native `reasoning` param (or
    // `reasoning_effort` for OpenAI-shape upstreams); null sends nothing.
    reasoningEffort: _rsnLevel || null,
    systemPrompt: _sysPrompt,
    messages: resolvedMessages,
    tools: _liteCfg ? [] : (_todoV2() ? toolDefs() : _todoLabTools(toolDefs())),
    // Todos run in CLAUDE MODE by default (2026-08-28 A/B: deepseek fully
    // complies with the trust-based TodoWrite contract — 5 turns/27s vs
    // 7/39s under the gated v2): blind full replace, no plan-first gate, no
    // open-todos stop guard. window.__todoV2 = 1 (console) restores the
    // guarded v2 tool for comparison/rollback.
    todoMode: _todoV2() ? '' : 'claude',
    // The user attached an image to a text-only model: the worker's vision pre-step
    // describes it via vision.fallback (below) before the loop. Marks the user bubble.
    routedViaVision: !!routedViaVision,
    // Python backend for run_python: walios, the WARM interpreter -- native-wasm
    // numpy/pandas/matplotlib with imports paid once per session rather than once per
    // call, and globals that survive between calls. There is no preference to set and no
    // fallback: a page that cannot start walios gets an error from the tool saying so,
    // rather than a quietly different interpreter than the description it was handed.
    pythonBackend: 'walios',
    // web_search primary backend: the first configured OpenRouter provider's
    // endpoint+key (active provider preferred), so the tool gets real Exa-backed
    // results even when the active model is NOT on OpenRouter. The worker calls
    // OpenRouter DIRECTLY (CORS-open, no proxy hop) with a cheap helper model —
    // override it via localStorage 'sandpie-web-search-model'. null → the worker
    // uses only the /proxy/ multi-engine scrape fallback.
    webSearch: (() => {
      try {
        const cands = [effective, active,
                       ...((typeof SandpieProviders !== 'undefined' && SandpieProviders.list) ? SandpieProviders.list() : [])].filter(Boolean);
        const or = cands.find(p => /(^https?:\/\/|\.)openrouter\.ai(\/|$)/i.test(String(p.endpoint || '').trim() + '/')
                                   && String(p.apiKey || '').trim());
        if (!or) return null;
        let model = '';
        try { model = (localStorage.getItem('sandpie-web-search-model') || '').trim(); } catch (_) {}
        return {
          url: String(or.endpoint).trim().replace(/\/$/, '') + '/chat/completions',
          apiKey: String(or.apiKey).trim(),
          model: model || 'openai/gpt-4o-mini',
        };
      } catch (_) { return null; }
    })(),
    // Vision facts for the worker's tools: can the active model see, and where can
    // a caption be requested from when it can't (tool_load_image uses this).
    vision: {
      canSee: !!canSee,
      fallback: visionFallback ? {
        endpoint: visionFallback.endpoint || '', apiKey: visionFallback.apiKey || '',
        model: visionFallback.model || '', proxyUrl: visionFallback.proxyUrl || '',
      } : null,
    },
    // Only what the provider config explicitly sets — no invented default. Absent
    // means absent on the wire (OpenAI-spec default: the model's own maximum).
    maxTokens: (effective && effective.maxTokens != null) ? effective.maxTokens : null,
    temperature: (effective && effective.temperature != null) ? effective.temperature : null,
    topP: (effective && effective.topP != null) ? effective.topP : null,
    reasoningEffort: (effective && effective.reasoningEffort) || null,
    // OpenRouter upstream routing, already in wire shape ({ order, allow_fallbacks })
    // so the worker can drop it straight into the request body's `provider` field.
    providerRouting: (effective && Array.isArray(effective.providerOrder) && effective.providerOrder.length)
      ? { order: effective.providerOrder, allow_fallbacks: effective.allowFallbacks !== false }
      : null,
    reasoning: (effective && effective.reasoning) || null,
    origin: location.origin,
    conversation_file_name: convId || activeConvId,
    // Conversation title for the /admin/transcripts Sessions table (server
    // stores it per session; best-effort, absent on brand-new untitled convs).
    conversation_title: (typeof convTitle === 'function') ? await convTitle(convId || activeConvId) : '',
    // Worker-side JSONL persistence: the completions worker appends each
    // committed message to the conversation file itself (O(1) SyncAccessHandle
    // at EOF) as it streams — no throttled page timer to starve while hidden,
    // no giant backlog to serialize when the user stops. jsonl_path = where to
    // append; persisted_count = messages already on disk so the worker's
    // counter stays in sync with the page (subagents inherit the fields but the
    // worker refuses to persist when maxRounds is set).
    jsonl_path: await (async () => {
      try {
        const cid = convId || activeConvId;
        const loc = await convLocation(cid);
        return (loc && loc.format) ? jsonlPath(cid, loc.archived) : '';
      } catch { return ''; }
    })(),
    persisted_count: (convStreams.get(convId || activeConvId) || {}).persistedCount || 0,
    // Stable per-conversation cache key, persisted in meta (ensureSessionId).
    // Reused across turns/refreshes/devices so OpenRouter prompt-cache holds.
    session_id: await ensureSessionId(convId || activeConvId),
    // (volatileContext removed 2026-09-02: the Recent-paths block is no longer
    // injected anywhere. The worker still adds the minute-level clock.)
    // Current checklist (task tree) so the worker can apply write_todos ops to it
    // instead of the model resending/overwriting the whole list.
    todos: Array.isArray(curTodos) ? curTodos : [],
    scratchpad: (typeof stream !== 'undefined' && stream.scratchpad) || '',
    // Base URL of the local relay the `shell` tool runs commands through (run it
    // in your target env, e.g. WSL). The worker has no localStorage, so pass it in.
    shellRelayUrl: (typeof SandpieTools !== 'undefined' && SandpieTools.shellRelayUrl) ? SandpieTools.shellRelayUrl() : 'http://localhost:8765',
    // Metacognition nudges (grind / reuse-a-tool / remember). Enabled unless the
    // user turns them off with `>>> metacog off`. Tunable knobs live here.
    metacog: (function () {
      try { return { enabled: localStorage.getItem('sandpie-metacog') !== 'off', grindK: 3, grindFloor: 12, grindCold: 40, shapeN: 4, rememberAfterDone: 3, rememberAfterCalls: 30 }; }
      catch (_) { return { enabled: true, grindK: 3, grindFloor: 12, grindCold: 40, shapeN: 4, rememberAfterDone: 3, rememberAfterCalls: 30 }; }
    })(),
    // Mid-turn compaction: the worker re-checks context at every round and, if the
    // agentic loop pushes past the threshold DURING a turn, summarizes its own
    // active message slice in place so a long tool-heavy turn can't overflow.
    // Pre-send maybeAutoCompact still handles the between-turns case. null = off.
    compaction: (function () {
      try {
        if (typeof SandpieCompactor === 'undefined' || !SandpieCompactor.isEnabled()) return null;
        let window = null;
        try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.contextWindow) window = SandpieTokens.contextWindow(convId); } catch (_) {}
        if (!window) return null;
        const c = SandpieCompactor.config();
        return { enabled: true, pct: c.pct, keepTail: c.keepTail, prompt: c.prompt, model: c.model || '', window, marker: SP_SUMMARY_MARKER };
      } catch (_) { return null; }
    })(),
  };
}

// Report accurate per-turn token usage to the server for the admin analytics
// panel (conversation_usage table). Best-effort + fire-and-forget: a failure
// NEVER affects the chat. Fires for EVERY provider that emits a `usage` event
// (managed or personal), attributed to the signed-in user via the same-origin
// session cookie. We do NOT send the provider apiKey as a Bearer header — for a
// personal provider that's the user's own key, which our server must never see;
// the cookie is the right credential. Anonymous (/guest) sessions have no cookie
// → the server 401s and we silently ignore it. The server derives the per-turn
// *incremental* prompt cost from these rows (LAG over turn_index), so we just
// forward the raw provider usage as reported.
// ── Report provider degeneration (client → /api/usage/degeneration) ────────
// The worker's degeneration detector tripped mid-stream (looping output) and
// aborted the attempt. Reported out-of-band so the server can reclassify the
// captured transcript turn as an error and attribute it to the upstream
// provider (see /admin → Degenerations by provider). Best-effort.
function reportDegeneration(ev) {
  try {
    if (!ev || !ev.session_id) return;
    fetch(new URL('/api/usage/degeneration', location.href).href, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: ev.session_id, model: ev.model || null,
        reason: ev.reason || null, words: ev.words || 0,
        ratio: ev.ratio != null ? ev.ratio : null,
      }),
      keepalive: true,
    }).catch(() => {});
  } catch (_) { /* analytics must never break the chat */ }
}

function reportTurnUsage(convId, usage, turnIndex, routedModel) {
  try {
    if (!convId || !usage || typeof usage.prompt_tokens !== 'number') return;
    const active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve) ? SandpieProviders.resolve(convId) : null;
    const details = usage.completion_tokens_details || {};
    const reasoning = details.reasoning_tokens != null ? details.reasoning_tokens
                    : (usage.reasoning_tokens != null ? usage.reasoning_tokens : undefined);
    const body = {
      conversation_id: convId,
      turn_index: turnIndex | 0,
      // The model that actually served the round (worker reports it per round —
      // a vision-routed round runs on the fallback, not the picker model).
      model: routedModel || (active && active.model) || usage.model || null,
      provider_type: active ? (active.managed ? 'managed' : (active.type || 'personal')) : null,
      usage: {
        prompt_tokens: usage.prompt_tokens || 0,
        completion_tokens: usage.completion_tokens || 0,
        total_tokens: usage.total_tokens != null ? usage.total_tokens
                      : ((usage.prompt_tokens || 0) + (usage.completion_tokens || 0)),
        reasoning_tokens: reasoning,
        cost: (typeof usage.cost === 'number' && isFinite(usage.cost)) ? usage.cost : null,
      },
    };
    fetch(new URL('/api/usage/turn', location.href).href, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  } catch (_) { /* analytics must never break the chat */ }
}

// ── Report conversation (client → /api/report/conversation) ─────────────────
// Lets any signed-in user flag the CURRENT conversation for developer review.
// The report carries the stable session_id (per-conversation cache key) plus the
// active model and an optional reason. Best-effort: a failure must never break
// the chat. False-y when the conversation/model aren't resolved yet.
async function reportConversation(reason) {
  try {
    const cid = activeConvId || (activeStream() && activeStream().id);
    if (!cid) return;
    const session_id = await ensureSessionId(cid);
    if (!session_id) return;
    const active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve) ? SandpieProviders.resolve(cid) : null;
    const model = (active && active.model) || null;
    const res = await fetch(new URL('/api/report/conversation', location.href).href, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id, model: model || null, reason: reason || null }),
      keepalive: true,
    });
    return res.ok;
  } catch (_) { return false; }
}

// Report per-turn PROFILING to the server for the admin panel. The worker splits
// the turn's wall time into completion (waiting on the model stream), tool compute
// (per tool — run_python is the pyodide cost), and mid-turn compaction, and emits
// it as a `timing` event at turn end. Same transport contract as reportTurnUsage:
// same-origin cookie auth (never the provider key), best-effort, fire-and-forget —
// a failure NEVER touches the chat. `timing.session_id` is the stable per-conv
// cache key the transcript capture also stores, so the server joins the two.
function reportTurnTiming(convId, timing, turnIndex) {
  try {
    if (!convId || !timing || typeof timing.wall_ms !== 'number') return;
    // Stash the current session id so the always-on suspension monitor can label
    // its gaps with the conversation they happened in (best-effort — last known).
    if (timing.session_id) window.__sandpieActiveSessionId = timing.session_id;
    const active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve) ? SandpieProviders.resolve(convId) : null;
    const body = {
      conversation_id: convId,
      session_id: timing.session_id || null,
      turn_index: turnIndex | 0,
      model: (active && active.model) || null,
      provider_type: active ? (active.managed ? 'managed' : (active.type || 'personal')) : null,
      timing: {
        completion_ms: timing.completion_ms | 0,
        completion_calls: timing.completion_calls | 0,
        // Split of completion_ms into prefill (wait for 1st token) vs decode
        // (streaming). MUST be forwarded or the server stores 0 and the panel
        // can't split the green completion bar.
        prefill_ms: timing.prefill_ms | 0,
        decode_ms: timing.decode_ms | 0,
        compaction_ms: timing.compaction_ms | 0,
        tool_ms: timing.tool_ms | 0,
        tool_calls: timing.tool_calls | 0,
        wall_ms: timing.wall_ms | 0,
        rounds: timing.rounds | 0,
        // Suspension (throttled/frozen-tab) fields — MUST be forwarded or the
        // server stores 0. This passthrough was the reason the panel never showed
        // a suspension despite the worker heartbeat measuring them correctly.
        suspend_ms: timing.suspend_ms | 0,
        suspend_hidden_ms: timing.suspend_hidden_ms | 0,
        suspend_events: timing.suspend_events | 0,
        suspend_max_ms: timing.suspend_max_ms | 0,
        tools: timing.tools && typeof timing.tools === 'object' ? timing.tools : {},
      },
    };
    fetch(new URL('/api/usage/timing', location.href).href, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  } catch (_) { /* analytics must never break the chat */ }
}

// ── Always-on browser-suspension monitor ────────────────────────────────────
// The real problem with turn-scoped detection: a suspended tab's turn often
// dies (stream lost) and its data with it, and the data only ships at turn end.
// This runs from page load, independent of any turn: the MAIN thread's own timer
// drift IS the suspension (background throttle, Chrome tab freeze, OS sleep), and
// each gap is beaconed IMMEDIATELY so it survives a tab close. Mild background
// throttling (timers clamped to ~1/s) stays under the 2s interval and does NOT
// register — only genuine freezes/suspends produce >1s of drift. `hidden` records
// whether the tab was backgrounded at any point across the gap (on resume the tab
// is usually focused again, so document.hidden alone would miss it).
// Validate from the DevTools console (freezes the main thread ~6s):
//     { const e = Date.now() + 6000; while (Date.now() < e) {} }
(function suspensionMonitor() {
  try {
    if (typeof window === 'undefined' || window.__sandpieSuspendMon) return;
    window.__sandpieSuspendMon = true;
    const HB = 2000, FLOOR = 1000;
    let last = Date.now();
    let sawHidden = (typeof document !== 'undefined') && document.hidden;
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => { if (document.hidden) sawHidden = true; });
    }
    setInterval(() => {
      const now = Date.now();
      const drift = now - last - HB;
      const hiddenDuringGap = sawHidden || (typeof document !== 'undefined' && document.hidden);
      last = now;
      sawHidden = (typeof document !== 'undefined') && document.hidden;
      if (drift <= FLOOR) return;
      try {
        const sid = (typeof window.__sandpieActiveSessionId === 'string') ? window.__sandpieActiveSessionId : null;
        fetch(new URL('/api/usage/suspend', location.href).href, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gap_ms: Math.round(drift), hidden: !!hiddenDuringGap, session_id: sid }),
          keepalive: true,
        }).catch(() => {});
      } catch (_) {}
    }, HB);
    console.log('[sandpie] suspension monitor active (main-thread heartbeat, ' + HB + 'ms)');
  } catch (_) {}
})();

async function readAgentEvents(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let lineBuf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    lineBuf += decoder.decode(value, { stream: true });
    const lines = lineBuf.split('\n');
    lineBuf = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      try { onEvent(JSON.parse(line)); }
      catch (e) { console.warn('[sandpie] bad event line:', line, e); }
    }
  }
}
// Render one subagent (spawn_subagent) event into a collapsible panel nested
// under the parent tool-call box. The panel is ephemeral — like reminders and
// live reasoning, it is not persisted; on reload only the spawn_subagent call
// and its final result (the tool result) remain. Keyed by subId so a fan-out of
// several subagents each gets its own panel.
function renderSubagentEvent(host, ev) {
  if (!host) return;
  const sub = ev.sub || {};
  const esc = (x) => (typeof CSS !== 'undefined' && CSS.escape) ? CSS.escape(String(x)) : String(x);
  const subId = ev.subId || 'sub';
  let panel = host.querySelector('.subagent-panel[data-sub-id="' + esc(subId) + '"]');
  if (!panel) {
    panel = document.createElement('div');
    panel.className = 'subagent-panel open';
    panel.dataset.subId = subId;
    const head = document.createElement('div');
    head.className = 'subagent-head';
    head.textContent = '▸ subagent: ' + (ev.agent || '?');
    head.addEventListener('click', () => panel.classList.toggle('open'));
    const log = document.createElement('div');
    log.className = 'subagent-log';
    panel.append(head, log);
    // Mount inside the parent spawn_subagent box if it exists yet, else at the
    // end of the host (a later re-mount is not attempted — best-effort live view).
    let anchor = null;
    if (ev.tcId) {
      const box = host.querySelector('.msg.tool-call[data-tc-id="' + esc(ev.tcId) + '"]');
      anchor = box ? (box.querySelector('.tc-expanded') || box) : null;
    }
    (anchor || host).appendChild(panel);
  }
  const log = panel.querySelector('.subagent-log');
  const head = panel.querySelector('.subagent-head');
  const line = (cls, txt) => { const d = document.createElement('div'); d.className = 'subagent-line' + (cls ? ' ' + cls : ''); d.textContent = txt; log.appendChild(d); };
  const argPreview = (a) => { let s = typeof a === 'string' ? a : JSON.stringify(a || {}); s = s.replace(/\s+/g, ' ').trim(); return s.length > 80 ? s.slice(0, 80) + '…' : s; };
  const trimResult = (r) => { let s = String(r || '').replace(/^\[r\d+\]\s*/, '').replace(/\s+/g, ' ').trim(); return s.length > 300 ? s.slice(0, 300) + '…' : s; };
  switch (sub.type) {
    case 'subagent_begin': line('sa-brief', '⌖ ' + String(sub.prompt || '').replace(/\s+/g, ' ').trim().slice(0, 300)); break;
    case 'message_added': {
      const m = sub.message || {};
      if (m.role === 'assistant' && typeof m.content === 'string' && m.content.trim()) line('sa-assistant', m.content.trim());
      break;   // role:'tool' messages surface via tool_result below (avoid dupes)
    }
    case 'tool_started': { const tc = sub.tc || {}; line('sa-tool', '→ ' + ((tc.function && tc.function.name) || 'tool') + '(' + argPreview(tc.function && tc.function.arguments) + ')'); break; }
    case 'tool_result':  line('sa-result', trimResult(sub.result)); break;
    case 'error':        line('sa-err', 'Error: ' + (sub.message || '')); break;
    case 'agent_done':   if (head) head.textContent = '✓ subagent: ' + (ev.agent || '?'); panel.classList.remove('open'); break;
    default: break;   // round-cap / reminder / round_start etc. — not logged
  }
}

function dispatchAgentEvent(ev, renderer, host) {
  switch (ev.type) {
    case 'round_start':   return renderer.startRound();
    case 'round_retry':   return renderer.retryRound();
    case 'delta':         return renderer.applyDelta(ev.delta);
    case 'round_end':     return renderer.endRound(ev.content, ev.locale);
    case 'message_added': {
      // Worker-side persistence: the event carries the worker's running JSONL
      // line count — keep the page's persistedCount in lockstep so the turn-end
      // saveConv finds nothing left to append. bindMessage falls back to the
      // 1.2s incremental save only when the worker couldn't persist (no count).
      const _st = convStreams.get(renderer.convId);
      if (_st && typeof ev.persistedCount === 'number') _st.persistedCount = ev.persistedCount;
      return renderer.bindMessage(ev.message, typeof ev.persistedCount === 'number');
    }
    case 'tool_started':  return renderer.markToolStarted(ev.tc);
    case 'tool_result':   return renderer.markToolDone(ev.id, ev.result, ev.artifacts);
    case 'subagent':      return renderSubagentEvent(host, ev);
    case 'agent_done': {
      // Final sync: the worker reports where it stopped appending, so the
      // turn-end saveConv never re-appends what the worker already wrote.
      const _st = convStreams.get(renderer.convId);
      if (_st && typeof ev.persistedCount === 'number') _st.persistedCount = ev.persistedCount;
      return;
    }
    case 'error':         return addMsg('err', 'Error: ' + (ev.message || 'unknown'), host);
    case 'info': {
      if (ev.message) {
        if (!renderer._retryNotice) renderer._retryNotice = addMsg('info', ev.message, host);
        else renderer._retryNotice.textContent = ev.message;
      } else if (renderer._retryNotice) {
        renderer._retryNotice.remove();
        renderer._retryNotice = null;
      }
      return;
    }
    case 'reminder': {
      // A harness-injected guard fired (drift nudge / stop-with-open-todos /
      // give-up). Shown so the mechanism is observable while debugging, but NOT
      // pushed into convMessages — it is never persisted or resent (addMsg only
      // touches the DOM). Prefixed so it's unmistakably a harness event.
      const _rl = { 'stop-block': 'stop guard', 'stop-anyway': 'stop guard (gave up)', 'drift': 'drift reminder', 'no-plan': 'no-plan reminder', 'grind': 'grind nudge', 'reuse': 'reuse-a-tool nudge', 'remember': 'remember nudge' };
      const label = _rl[ev.kind] || 'reminder';
      // Console copy follows the same visibility flag as the transcript
      // (`>>> drift`); silent by default, re-enabled with `>>> drift on`.
      if (_reminderNotesVisible()) {
        try { console.debug('[sandpie reminder]', ev.kind, ev.meta || '', ev.text); } catch (_) {}
      }
      // Hidden by default — toggle with the `>>> drift` command. When off, the
      // guard still fires and is logged to the console; it just isn't rendered.
      if (_reminderNotesVisible()) {
        addMsg('info', '⟳ ' + label + (ev.meta && ev.meta.attempt ? ' ' + ev.meta.attempt : '') + ': ' + (ev.text || '').replace(/<\/?system-reminder>/g, '').trim(), host);
      }
      return;
    }
    case 'session_expired': {
      // Managed SSO session has lapsed for good. Redirect to login instead of
      // leaving a red 401 error in the conversation.
      window.location.href = '/auth/login';
      return;
    }
  }
}


/* -------------------------------------------------------------------------- */
/*  Extracted from sandpie-test.html inline script                           */
/* -------------------------------------------------------------------------- */
function ensureStream(id) {
  let s = convStreams.get(id);
  if (!s) {
    const host = document.createElement('div');
    host.className = 'conv-host';
    host.dataset.convId = id;
    s = {
      id, host,
      messages: [],
      abort: null,
      compaction: null,
      timerEl: null, timerStart: 0, timerInterval: null,
      lastUsage: null,
      generating: false,
      // JSONL persistence: how many messages are already on disk, and a flag that
      // forces a full rewrite (rewind/edit) instead of an append on the next save.
      persistedCount: 0, _forceJsonlRewrite: false,
      // The conversation's project (stable registry id, null until filed).
      projectId: null,
      // PER-CONVERSATION provider: which catalog model this conversation uses
      // (composer model picker). null → providers.js defaultProvider() applies.
      providerId: null,
      // PER-CONVERSATION reasoning effort: 'off'|'low'|'medium'|'high' (composer
      // model picker slider). null → the app default (localStorage) applies.
      reasoningLevel: null,
    };
    convStreams.set(id, s);
  }
  return s;
}

function activeStream() { return activeConvId ? (convStreams.get(activeConvId) || null) : null; }
// Render an attached-document part ({ type:'file' }) as a clickable chip in a
// message bubble. Clicking opens it in the OPFS file viewer. Images use the
// <img> path above; this is for everything else.
function buildFileChip(f) {
  const chip = document.createElement('span');
  chip.className = 'file-chip';
  const icon = document.createElement('span');
  icon.className = 'fc-icon';
  icon.textContent = (typeof SandpieImages !== 'undefined' && SandpieImages.iconFor)
    ? SandpieImages.iconFor(f.name, f.mime) : '📄';
  const nm = document.createElement('span');
  nm.className = 'fc-name';
  nm.textContent = f.name || 'file';
  const sz = document.createElement('span');
  sz.className = 'fc-size';
  sz.textContent = f.size ? (opfs.formatSize(f.size) || '') : '';
  chip.append(icon, nm, sz);
  if (f.path) {
    chip.title = 'Open ' + (f.name || 'file');
    chip.style.cursor = 'pointer';
    chip.onclick = () => { try { opfs.openFile(f.path, f.name); } catch (_) {} };
  }
  return chip;
}

function addMsg(role, text = '', host = null, animate = false) {

  // Prefer the mounted .conv-host even when the caller didn't thread `host`
  // through (most addMsg('err', …) calls don't) — paneScrollEl resolves it.
  const target = host || (activeStream() && activeStream().host) || paneScrollEl($('messages'));

  let scrollHost = climbScrollEl(target);
  const visible = !!scrollHost;
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  // Task Register: tool calls mount inside the current group's log; any other
  // message ends the run so the next call opens a fresh group.
  const mount = role === 'tool-call' ? tgLogFor(target) : (tgBreak(target), target);
  if (role === 'tool-call') {

    const expanded = document.createElement('span');
    expanded.className = 'tc-expanded';
    const collapsed = document.createElement('span');
    collapsed.className = 'tc-collapsed';
    div.appendChild(collapsed);
    div.appendChild(expanded);
    // Collapsed by default; click the header (tc-collapsed) to toggle.
    collapsed.addEventListener('click', (ev) => {
      ev.stopPropagation();
      div.classList.toggle('expanded');
    });
  } else {
    const bubble = document.createElement('span');
    bubble.className = 'bubble';
    if (Array.isArray(text)) {

      for (const part of text) {
        if (part.type === 'text' && part.text) {
          const span = document.createElement('span');
          span.textContent = part.text;
          span.style.display = 'block';
          span.style.marginBottom = '0.5rem';
          bubble.appendChild(span);
        } else if (part.type === 'image_url') {
          const img = document.createElement('img');
          const url = part.image_url.url;
          if (url.startsWith('opfs://')) {

            img.src = '';
            img.alt = '(loading image...)';
            img.style.maxWidth = '200px';
            img.style.maxHeight = '150px';
            img.style.borderRadius = '4px';
            img.style.display = 'block';
            SandpieImages.dataUrlFromPath(url.slice(7)).then(dataUrl => {
              if (dataUrl) { img.src = dataUrl; img.alt = ''; }
              else { img.alt = '(image not found)'; }
            });
          } else {
            img.src = url;
          }
          img.style.maxWidth = '200px';
          img.style.maxHeight = '150px';
          img.style.borderRadius = '4px';
          img.style.display = 'block';
          bubble.appendChild(img);
        } else if (part.type === 'file' && part.file) {
          bubble.appendChild(buildFileChip(part.file));
        }
      }
    } else {
      bubble.textContent = text;
    }
    div.appendChild(bubble);
    if (role === 'user') {
      // Floating toolbar (copy / rewind): hidden until hover (PC), tap
      // (mobile) or a text selection inside this bubble. Same .msg-actions/
      // .act-copy material as the assistant toolbar; rendered below the bubble.
      const acts = document.createElement('div');
      acts.className = 'msg-actions';
      const copy = document.createElement('button');
      copy.type = 'button';
      copy.className = 'act-copy';
      copy.title = 'Copy selection';
      copy.setAttribute('aria-label', 'Copy selection');
      copy.innerHTML = '<svg viewBox="0 0 24 24"><path d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"/></svg>';
      copy.addEventListener('click', () => {
        const sel = getSelectionTextIn(bubble);
        navigator.clipboard.writeText(sel || bubble.innerText.trim()).then(() => {
          copy.classList.add('done');
          const prev = copy.innerHTML;
          copy.innerHTML = '<svg viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
          setTimeout(() => { copy.innerHTML = prev; copy.classList.remove('done'); hideUserSelToolbar(acts); }, 1300);
        }).catch(() => {});
      });
      acts.appendChild(copy);
      const rewind = document.createElement('button');
      rewind.type = 'button';
      rewind.className = 'act-copy act-rewind';
      rewind.title = 'Rewind to this message';
      rewind.setAttribute('aria-label', 'Rewind to this message');
      rewind.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>';
      rewind.addEventListener('click', () => {
        hideUserSelToolbar(acts);
        rewindToUserMessage(div);
      });
      acts.appendChild(rewind);
      div.appendChild(acts);
    }
    if (role === 'assistant') {
      // Hover-reveal copy action: copy this reply as plain text.
      const acts = document.createElement('div');
      acts.className = 'msg-actions';
      const copy = document.createElement('button');
      copy.type = 'button';
      copy.className = 'act-copy';
      copy.title = 'Copy this reply';
      copy.setAttribute('aria-label', 'Copy this reply');
      copy.innerHTML = '<svg viewBox="0 0 24 24"><path d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"/></svg>';
      copy.addEventListener('click', () => {
        const bub = div.querySelector(':scope > .bubble');
        const text = (bub ? bub.innerText : div.innerText).trim();
        const NL = String.fromCharCode(10);
        const parts = text.split(NL);
        const out = [];
        for (let i = 0; i < parts.length; i++) {
          const ln = parts[i].trim();
          if (ln) { out.push(ln); continue; }
          if (out.length && out[out.length-1]) out.push('');
        }
        navigator.clipboard.writeText(out.join(NL)).then(() => {
          copy.classList.add('done');
          const prev = copy.innerHTML;
          copy.innerHTML = '<svg viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
          setTimeout(() => { copy.innerHTML = prev; copy.classList.remove('done'); }, 1300);
        }).catch(() => {});
      });
      acts.appendChild(copy);
      // Hover-reveal rewind action: same as typing ">>> rewind" (removes the
      // last user-assistant pair and restores the user text in the composer).
      const rewind = document.createElement('button');
      rewind.type = 'button';
      rewind.className = 'act-copy act-rewind';
      rewind.title = 'Rewind last turn';
      rewind.setAttribute('aria-label', 'Rewind last turn');
      rewind.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>';
      rewind.addEventListener('click', () => {
        if (typeof SandpieCommands === 'undefined' || !SandpieCommands.get('rewind')) return;
        SandpieCommands.dispatch('>>> rewind');
      });
      acts.appendChild(rewind);
      // Report (thumbs-down) action: moved here from the idle-bar timer — it
      // belongs with the other per-reply actions (copy / rewind).
      const report = document.createElement('button');
      report.type = 'button';
      report.className = 'act-copy act-report-btn';
      report.title = 'Report this conversation for developer review';
      report.setAttribute('aria-label', 'Report this conversation');
      report.innerHTML = REPORT_SVG_INLINE;
      report.addEventListener('click', async () => {
        const prev = report.innerHTML;
        report.disabled = true;
        report.classList.add('done');
        const ok = await reportConversation('msg-actions');
        report.innerHTML = ok
          ? '<svg viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>'
          : '<span style="font-size:11px">✗</span>';
        report.title = ok ? 'Reported — thank you' : 'Report failed (not signed in?)';
        setTimeout(() => { report.disabled = false; report.innerHTML = prev; report.classList.remove('done'); }, 1300);
      });
      acts.appendChild(report);
      div.appendChild(acts);
    }
  }
  if (role === 'user' && animate) {
    // LIVE user bubble (Enter-to-send only — load replays pass animate=false):
    // entrance animation + (if this is the first message of a fresh conversation)
    // fade the home screen out. Probe BEFORE the bubble is appended so the
    // first-message scan doesn't count the bubble it is about to add.
    div.classList.add('msg-enter');
    _fadeHomeOnFirst(target);
  }
  if (mount !== target) { mount.appendChild(div); tgUpdate(mount.parentNode); }
  else appendContent(target, div);

  const timer = target.querySelector(':scope > .msg-timer:not(.done)');
  if (timer) appendContent(target, timer);
  if (visible && shouldAutoScroll(scrollHost)) scrollHost.scrollTop = scrollHost.scrollHeight;
  return div;
}

function bindBubble(div, msgRef) {
  if (!div) return div;

  if (!div._listenersAttached) {
    div._listenersAttached = true;
  }
  if (msgRef) div._msg = msgRef;
  return div;
}

function tcEscape(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// Resolve a tool-call box. Accepts the element directly (preferred — the live
// renderer already holds it, so rendering can't be lost to a tcId/dataset
// mismatch) OR a tcId string (used by history replay), matched against
// data-tc-id within scope.
function _toolBoxEl(ref, scopeEl) {
  if (ref && ref.nodeType === 1) return ref;
  const root = scopeEl || document;
  let found = null;
  for (const div of root.querySelectorAll('.msg.tool-call')) {
    // Last match wins: a round persisted twice (concurrent-append race) yields
    // duplicate tool_call ids, and each result must attach to ITS OWN box — the
    // first match left the later duplicate box EMPTY.
    if (div.dataset.tcId === ref) found = div;
  }
  return found;
}

function appendToolResult(tcId, result, scopeEl) {
  const toolCallDiv = _toolBoxEl(tcId, scopeEl);
  if (!toolCallDiv) return;
  const expanded = toolCallDiv.querySelector('.tc-expanded');
  if (!expanded) return;
  let box = expanded.querySelector('.tool-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'tool-box';
    expanded.innerHTML = '';
    expanded.appendChild(box);
  }

  const existingSep = box.querySelector('.tool-sep');
  const existingResult = box.querySelector('.tool-result');
  if (existingSep) existingSep.remove();
  if (existingResult) existingResult.remove();

  const sep = document.createElement('div');
  sep.className = 'tool-sep';
  const resultDiv = document.createElement('div');
  resultDiv.className = 'tool-result';
  resultDiv.textContent = result;
  box.appendChild(sep);
  box.appendChild(resultDiv);
}

// Render the write_todos checklist inside its tool-call box, in place of a text
// result. Each write_todos call gets its own card attached to that call, so the
// history reads as a running log of the plan; replay rebuilds each from the tool
// message content.
/* == Reply-language resolution ================================================
   The Reply language is the SOLE authority for the language sandpie replies in and
   delivers files in. It comes from the Account-picker selector (SandpieLanguage: an
   explicit choice, or the browser/OS language auto-selected once on first run, then
   editable). NOTHING is auto-detected from message content - a message that merely
   mentions another language must NEVER change it. The only per-deliverable override is
   an explicit 'language' argument on a respond / show_artifact call, applied at delivery.
   ---------------------------------------------------------------------------------- */
// Languages the ACTIVE model generates reliably (models.json `fluent`, carried
// onto the managed provider def by account.js). null = unknown (personal
// providers, old servers) — treated as English-only, the historically safe
// default: everything non-English gets localized.
function _modelFluent() {
  try {
    const p = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve) ? SandpieProviders.resolve(activeConvId) : null;
    if (!p || !Array.isArray(p.fluent) || !p.fluent.length) return null;
    return p.fluent.map(c => String(c).split(/[-_]/)[0].toLowerCase());
  } catch (_) { return null; }
}
function _replyLocale() {
  try {
    if (typeof window === 'undefined') return { code: 'en', name: 'English' };
    const SL = window.SandpieLanguage;
    const eff = (SL && SL.effective && SL.effective()) || 'en';
    const code = String(eff).split(/[-_]/)[0] || 'en';
    const nm = (SL && SL.name && SL.name(code)) || (code === 'en' ? 'English' : code);
    return { code: code, name: nm };
  } catch (_) { return { code: 'en', name: 'English' }; }
}
function renderTodos(tcId, todos, scopeEl) {
  const toolCallDiv = _toolBoxEl(tcId, scopeEl);
  if (!toolCallDiv) return;
  const expanded = toolCallDiv.querySelector('.tc-expanded');
  if (!expanded) return;
  let box = expanded.querySelector('.tool-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'tool-box';
    expanded.innerHTML = '';
    expanded.appendChild(box);
  }
  const existingSep = box.querySelector('.tool-sep');
  const existingResult = box.querySelector('.tool-result');
  const existingTodos = box.querySelector('.tool-todos');
  if (existingSep) existingSep.remove();
  if (existingResult) existingResult.remove();
  if (existingTodos) existingTodos.remove();

  const sep = document.createElement('div');
  sep.className = 'tool-sep';
  const list = buildTodosView(todos || []);
  box.appendChild(sep);
  box.appendChild(list);

  // Live timer badge: show current checklist progress in the active timer.
  const ip = (todos || []).findIndex(t => t && t.status === 'in_progress');
  const liveTimer = (scopeEl || document).querySelector('.msg-timer:not(.done)');
  if (liveTimer && todos && todos.length) {
    const badge = liveTimer.querySelector('.mt-todos');
    if (badge) {
      const cur = (todos || []).filter(t => t && t.status === 'completed').length;   // completed only — match the checklist card
      badge.textContent = cur + '/' + todos.length;
      badge.title = (todos[ip] && todos[ip].content) || 'Checklist';
      badge.onclick = () => {
        showCmdPanelForEl(badge, buildTodosView(todos), 'Checklist');
      };
    }
  }
  // An already-open checklist panel tracks the update instead of going stale.
  refreshOpenChecklistPanel(todos, scopeEl);
}

// Build a checklist DOM element from a todos array.
// Render the ask question card inside a tool-call box, in place of a text result.
// Render the ask question card as a STANDALONE element in the conversation.
// It is NOT injected into a tool-call box: the worker events that create the
// box flow through an async NDJSON stream (workerAgentStream), while the
// forward-to-page asks-question is processed synchronously — so the box may
// not exist yet, and a last-box fallback can target the wrong (write_todos)
// box. A standalone card is deterministic and matches the conversational
// direction: the empty 'ask' tool-box header stays, and the card sits below it.
function renderQuestions(tcId, questions, reply, convId) {
  // Render into the GENERATING conversation's host — the stream that produced
  // the ask tool call — not the currently-active conversation. The user may
  // have switched panels/conversations while the question was pending.
  const stream = (convId && convStreams.get(convId)) || activeStream();
  const host = (stream && stream.host) || paneScrollEl($('messages')) || $('messages');
  if (!host) return null;
  const qs = questions || [];
  const card = buildQuestionsView(qs, (answers) => {
    try { reply('answers:' + JSON.stringify(answers)); } catch (_) {}
  });
  if (tcId) card.dataset.askTcId = tcId;
  host.appendChild(card);
  return card;
}

// Human-readable summary of answered questions — rendered into the ask
// tool-call box in place of the raw 'answers:[...]' JSON (the model still
// receives the JSON, the user sees the Q → A pairs).
function buildAnswersSummary(answers) {
  const wrap = document.createElement('div');
  wrap.className = 'ask-answered';
  for (const a of (answers || [])) {
    // One question row, then its answer on its own row — no arrow.
    const q = document.createElement('div');
    q.className = 'ask-answered-q';
    q.textContent = a.question || '';
    const ans = document.createElement('div');
    ans.className = 'ask-answered-a';
    ans.textContent = a.answer || '';
    wrap.append(q, ans);
  }
  return wrap;
}

function renderAnswers(tcIdOrEl, answers, scopeEl) {
  const toolCallDiv = (tcIdOrEl && tcIdOrEl.nodeType === 1) ? tcIdOrEl : _toolBoxEl(tcIdOrEl, scopeEl);
  if (!toolCallDiv) return;
  const expanded = toolCallDiv.querySelector('.tc-expanded');
  if (!expanded) return;
  let box = expanded.querySelector('.tool-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'tool-box';
    expanded.innerHTML = '';
    expanded.appendChild(box);
  }
  const existingSep = box.querySelector('.tool-sep');
  const existingResult = box.querySelector('.tool-result');
  const existingAnswers = box.querySelector('.ask-answered');
  if (existingSep) existingSep.remove();
  if (existingResult) existingResult.remove();
  if (existingAnswers) existingAnswers.remove();
  const sep = document.createElement('div');
  sep.className = 'tool-sep';
  box.appendChild(sep);
  box.appendChild(buildAnswersSummary(answers));
}

// Build a multiple-choice question card DOM element from a questions array.
// Mockup B (revised): conversational bubble, one question at a time (wizard),
// full-width chips, 'Otro:' free text ALWAYS available (the model cannot gate
// it), question text in the header, no 'recomendado' line, no 'Usar
// recomendados' button. onAnswer receives the collected answers array.
function buildQuestionsView(questions, onAnswer) {
  const wrap = document.createElement('div');
  wrap.className = 'ask-card';
  const qs = questions || [];
  const state = { questions: qs, current: 0, answers: qs.map(() => null), onAnswer: onAnswer || null };
  wrap._askState = state;

  // --- Header: [? icon] [question text] [1/N] ---
  const head = document.createElement('div');
  head.className = 'ask-card-head';
  const qIcon = document.createElement('span');
  qIcon.className = 'ask-q-icon';
  qIcon.textContent = '?';
  const qTitle = document.createElement('span');
  qTitle.className = 'ask-q-title';
  const qCount = document.createElement('span');
  qCount.className = 'ask-qcount';
  head.append(qIcon, qTitle, qCount);
  wrap.appendChild(head);

  // --- Body (chips + free text) ---
  const body = document.createElement('div');
  body.className = 'ask-body';
  wrap.appendChild(body);

  // --- Navigation dots (only appended when there are 2+ questions) ---
  const dots = document.createElement('div');
  dots.className = 'ask-dots';
  if (qs.length > 1) wrap.appendChild(dots);

  // --- Actions: Atrás + Siguiente/Responder ---
  const actions = document.createElement('div');
  actions.className = 'ask-actions';
  const backBtn = document.createElement('button');
  backBtn.className = 'ask-btn';
  backBtn.textContent = '\u2190';
  const nextBtn = document.createElement('button');
  nextBtn.className = 'ask-btn primary';
  actions.append(backBtn, nextBtn);
  wrap.appendChild(actions);

  function renderQuestion() {
    const i = state.current;
    const q = qs[i];
    if (!q) { body.innerHTML = ''; return; }
    qTitle.textContent = q.question || '';
    qCount.textContent = (i + 1) + '/' + qs.length;

    // Dots — only when there are 2+ questions (a single question needs no progress dots)
    dots.innerHTML = '';
    if (qs.length > 1) {
      for (let j = 0; j < qs.length; j++) {
        const dot = document.createElement('span');
        dot.className = 'ask-dot' + (j === i ? ' active' : '') + (state.answers[j] ? ' done' : '');
        dots.appendChild(dot);
      }
    }

    // Chips (full-width rows; recommended dashed + 'rec', default pre-selected)
    let html = '<div class="ask-q">';
    html += '<div class="ask-chips">';
    const prev = state.answers[i] ? state.answers[i].answer : null;
    for (const opt of (q.options || [])) {
      const sel = opt === (prev || q.default) ? ' selected' : '';
      const rec = opt === q.default && q.options.length > 2 ? ' data-rec="1"' : '';
      html += '<div class="ask-chip' + sel + '"' + rec + ' data-value="' + tcEscape(opt) + '">';
      html += '<span class="chip-radio">' + (sel ? '\u25cf' : '\u25cb') + '</span>';
      html += '<span class="chip-label">' + tcEscape(opt) + '</span>';
      if (rec) html += '<span class="chip-rec">rec</span>';
      html += '</div>';
    }
    html += '</div>';
    // Free text ALWAYS available (never disabled); 'Otro:' lives in the placeholder
    const prevFree = (state.answers[i] && state.answers[i]._freeText) ? state.answers[i]._freeText : '';
    // language-agnostic placeholder: just an ellipsis, no words
    html += '<textarea class="ask-free-input" rows="1" wrap="soft" placeholder="\u2026">' + tcEscape(prevFree) + '</textarea>';
    html += '</div>';
    body.innerHTML = html;

    // Wire chips
    body.querySelectorAll('.ask-chip').forEach(chip => {
      chip.onclick = () => {
        body.querySelectorAll('.ask-chip').forEach(c => {
          c.classList.remove('selected');
          const r = c.querySelector('.chip-radio'); if (r) r.textContent = '\u25cb';
        });
        chip.classList.add('selected');
        const r = chip.querySelector('.chip-radio'); if (r) r.textContent = '\u25cf';
        // Free text and chips are mutually exclusive: picking a chip clears the text
        const fi = body.querySelector('.ask-free-input');
        if (fi) { fi.value = ''; fi.classList.remove('selected'); }
        saveAnswer(i);
      };
    });

    // Wire textarea: auto-grow vertically + keep the answer in sync
    const freeInput = body.querySelector('.ask-free-input');
    if (freeInput) {
      const grow = () => {
        freeInput.style.height = 'auto';
        freeInput.style.height = (freeInput.scrollHeight + 2) + 'px';
      };
      if (prevFree) freeInput.classList.add('selected');
      grow();
      freeInput.addEventListener('input', () => {
        // Typing selects the free-text option: deselect chips, highlight the input
        body.querySelectorAll('.ask-chip').forEach(c => {
          c.classList.remove('selected');
          const r = c.querySelector('.chip-radio'); if (r) r.textContent = '\u25cb';
        });
        freeInput.classList.toggle('selected', !!freeInput.value.trim());
        saveAnswer(i); grow();
      });

      // Enter submits the current answer (Shift+Enter = newline). Mirrors the
      // next/check button: on the last question this responds and closes the card.
      freeInput.addEventListener('keydown', (ev) => {
        if (ev.key !== 'Enter' || ev.shiftKey) return;
        ev.preventDefault();
        saveAnswer(i);
        if (isLast) returnAnswers();
        else { state.current++; renderQuestion(); }
      });
    }

    // Buttons
    const isLast = i === qs.length - 1;
    nextBtn.textContent = isLast ? '\u2713' : '\u2192';   // ✓ respond / → next — language-agnostic
    backBtn.style.display = i === 0 ? 'none' : '';
    nextBtn.onclick = () => {
      saveAnswer(i);
      if (isLast) returnAnswers();
      else { state.current++; renderQuestion(); }
    };
    backBtn.onclick = () => { saveAnswer(i); state.current--; renderQuestion(); };
    wrap.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function saveAnswer(i) {
    const q = qs[i];
    if (!q) return;
    const qBlock = body.querySelector('.ask-q');
    const selected = qBlock ? qBlock.querySelector('.ask-chip.selected') : null;
    const freeInput = qBlock ? qBlock.querySelector('.ask-free-input') : null;
    let answer = q.default || (q.options && q.options[0]) || '';
    let _freeText = '';
    if (freeInput && freeInput.value.trim()) {
      answer = freeInput.value.trim();
      _freeText = freeInput.value.trim();
    } else if (selected) {
      answer = selected.dataset.value || (selected.querySelector('.chip-label') && selected.querySelector('.chip-label').textContent.trim()) || answer;
    }
    state.answers[i] = { question: q.question, answer, _freeText };
  }

  function returnAnswers() {
    saveAnswer(state.current);
    const answers = state.answers.filter(Boolean).map(a => ({ question: a.question, answer: a.answer }));
    wrap._answers = answers;
    // Click = disappear, unconditionally: the card is removed before any worker
    // round-trip (the summary still renders into the tool-call box afterwards).
    wrap.remove();
    if (state.onAnswer) state.onAnswer(answers);
  }

  renderQuestion();
  return wrap;
}

function buildTodosView(todos) {
  const wrap = document.createElement('div');
  wrap.className = 'tool-todos';
  const head = document.createElement('div');
  head.className = 'tool-todos-head';
  const live = (todos || []).filter(t => t && t.status !== 'deleted' && t.status !== 'withdrawn');
  const done = live.filter(t => t.status === 'completed').length;
  head.textContent = 'Checklist \u00b7 ' + done + '/' + live.length + ' done';
  wrap.appendChild(head);
  for (const t of (todos || [])) {
    const st = (t && t.status) || 'pending';
    if (st === 'deleted' || st === 'withdrawn') continue;   // dropped from the flat view
    const row = document.createElement('div');
    row.className = 'tool-todo tool-todo-' + (st === 'blocked' ? 'wait' : st);
    const mark = document.createElement('span');
    mark.className = 'tool-todo-mark';
    mark.textContent = st === 'completed' ? '\u2713' : st === 'in_progress' ? '\u25b8' : st === 'blocked' ? '\u23f8' : '\u25cb';
    const txt = document.createElement('span');
    txt.className = 'tool-todo-text';
    const label = (t && (st === 'in_progress' && t.activeForm ? t.activeForm : t.content)) || '';
    txt.textContent = label + (st === 'blocked' && t && t.reason ? ' \u2014 ' + t.reason : '');
    row.append(mark, txt);
    // Dependency indicator: tasks still waiting on an open blocker.
    if (t && Array.isArray(t.blockedBy) && t.blockedBy.length) {
      const openBlk = t.blockedBy.filter(id => {
        const b = (todos || []).find(x => x && String(x.id) === String(id));
        return b && (b.status === 'pending' || b.status === 'in_progress' || b.status === 'blocked');
      });
      if (openBlk.length) {
        const bb = document.createElement('span');
        bb.className = 'tool-todo-blocked';
        bb.textContent = '\u26d3 ' + openBlk.join(', ');
        bb.title = 'Blocked by task(s) ' + openBlk.join(', ');
        row.appendChild(bb);
      }
    }
    // Claims get a badge (CLAIM → CONFIRMED/REFUTED); ANY task closed with
    // cited evidence shows the [rN] ids it cited.
    if (t && t.kind === 'claim') {
      const badge = document.createElement('span');
      badge.className = 'tool-todo-claim-badge' + (t.verdict ? ' claim-' + t.verdict : '');
      badge.textContent = t.verdict ? t.verdict.toUpperCase() : 'CLAIM';
      row.appendChild(badge);
    }
    // Auto-adversary outcome. Completed items carry auditNote (pass/override/
    // skip/unavailable); open items carry auditFails when a close attempt was
    // rejected by the audit. Click a badge to read the full audit transcript
    // (t.auditLog, kept by the worker — last 4 entries incl. rejections).
    const _auditBadge = (cls, label, title) => {
      const a = document.createElement('span');
      a.className = 'tool-todo-audit-badge' + (cls ? ' ' + cls : '');
      a.textContent = label;
      a.title = title;
      const log = Array.isArray(t.auditLog) && t.auditLog.length ? t.auditLog : (t.auditNote ? [t.auditNote] : null);
      if (log && typeof SandpieCommandView !== 'undefined') {
        a.classList.add('audit-clickable');
        a.onclick = (e) => {
          e.stopPropagation();
          const pre = document.createElement('pre');
          pre.className = 'tool-todo-audit-log';
          pre.textContent = log.join('\n\n' + '─'.repeat(40) + '\n\n');
          SandpieCommandView.show(pre, 'Adversary audit — ' + ((t.content || '').slice(0, 60) || t.id));
        };
      }
      row.appendChild(a);
    };
    if (t && t.auditNote) {
      const pass = /^auto-audit: supported/.test(t.auditNote);
      const over = t.auditNote.includes('OVERRIDDEN');
      _auditBadge(pass ? 'audit-pass' : over ? 'audit-override' : '', pass ? 'AUDIT ✓' : over ? 'AUDIT !' : 'AUDIT ·', t.auditNote);
    } else if (t && t.auditFails && t.status !== 'completed' && t.status !== 'withdrawn') {
      _auditBadge('audit-fail', 'AUDIT ×' + t.auditFails, 'Close attempt(s) rejected by the automatic adversarial audit — click for the full audit');
    }
    if (t && Array.isArray(t.evidence) && t.evidence.length) {
      const ev = document.createElement('span');
      ev.className = 'tool-todo-evidence';
      ev.textContent = t.evidence.join(' ');
      ev.title = 'Evidence: tool results cited to close this task';
      row.appendChild(ev);
    }
    wrap.appendChild(row);
  }
  return wrap;
}

// Render a loaded image (load_image tool) inline inside its tool-call box, in
// place of a text result. The thumbnail is resolved from OPFS page-side.
function appendToolResultImage(tcId, path, scopeEl) {
  const toolCallDiv = _toolBoxEl(tcId, scopeEl);
  if (!toolCallDiv) return;
  const expanded = toolCallDiv.querySelector('.tc-expanded');
  if (!expanded) return;
  let box = expanded.querySelector('.tool-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'tool-box';
    expanded.innerHTML = '';
    expanded.appendChild(box);
  }
  const existingSep = box.querySelector('.tool-sep');
  const existingResult = box.querySelector('.tool-result');
  if (existingSep) existingSep.remove();
  if (existingResult) existingResult.remove();

  const sep = document.createElement('div');
  sep.className = 'tool-sep';
  const resultDiv = document.createElement('div');
  resultDiv.className = 'tool-result tool-result-image';
  const img = document.createElement('img');
  img.alt = path;
  img.className = 'tool-image';
  SandpieImages.dataUrlFromPath(path).then(dataUrl => {
    if (dataUrl) img.src = dataUrl;
    else resultDiv.textContent = '(image not found: ' + path + ')';
  });
  resultDiv.appendChild(img);
  box.appendChild(sep);
  box.appendChild(resultDiv);
}

// Friendly display labels for tool-call boxes. Maps the raw API tool name to
// the words the USER sees — a verb phrase ("doing" while running, "done" after),
// optionally suffixed with a target pulled from the call's args (the file's
// basename for `path`, or the value of `name`). The raw tool name is still kept
// on div.dataset.fname and surfaced as a hover title, so power users lose nothing.
// Unknown tools fall back to the raw name (never blank).
const TC_LABELS = {
  run_python:        { doing: 'Running code',        done: 'Ran code' },
  pyodide:           { doing: 'Running code',        done: 'Ran code' },   // former wire name of run_python
  run_walios:        { doing: 'Running a script',    done: 'Ran script' },  // shell script in the in-browser Linux
  walios:            { doing: 'Running a script',    done: 'Ran script' },  // former name of run_walios
  write_file:        { doing: 'Creating',            done: 'Created',        target: 'path' },
  edit_file:         { doing: 'Editing',             done: 'Edited',         target: 'path' },
  read_file:         { doing: 'Reading',             done: 'Read',           target: 'path' },
  list_files:        { doing: 'Browsing files',      done: 'Listed files' },
  search:            { doing: 'Searching files',     done: 'Searched files' },
  show_artifact:     { doing: 'Opening preview',     done: 'Showed',         target: 'path' },
  screenshot:        { doing: 'Taking a screenshot', done: 'Screenshot',     target: 'path' },
  html_console:      { doing: 'Checking the page',   done: 'Checked console' },
  load_image:        { doing: 'Looking at',          done: 'Viewed',         target: 'path' },
  load_skill:        { doing: 'Loading skill',       done: 'Loaded skill',   target: 'name' },
  copy_to_workspace: { doing: 'Importing file',      done: 'Imported file' },
  share:             { doing: 'Sharing',             done: 'Shared',         target: 'path' },
  spawn_subagent:    { doing: 'Asking a helper',     done: 'Helper done' },
  shell:             { doing: 'Running a command',   done: 'Ran command' },
  remember:          { doing: 'Saving to memory',    done: 'Saved to memory' },
  recall:            { doing: 'Recalling',           done: 'Recalled' },
  write_todos:       { doing: 'Planning',            done: 'Planned' },
  ask:               { doing: 'Asking you',          done: 'Asked you' },
  web_search:        { doing: 'Searching the web',   done: 'Searched the web', target: 'query' },
};
// Localized verbs, keyed by base language code, mapping the canonical English
// phrase (from TC_LABELS) → its translation. The tool-call label sits inline in
// the message stream next to the model's own reply, so it should follow the
// conversation language (SandpieLanguage), not stay English like the static
// chrome. English is the fallback: any phrase or language not listed here shows
// the canonical English. Adding a language = one object of the ~38 phrases.
const TC_I18N = {
  es: {
    'Running code': 'Ejecutando código',      'Ran code': 'Código ejecutado',
    'Creating': 'Creando',                     'Created': 'Creado',
    'Editing': 'Editando',                     'Edited': 'Editado',
    'Reading': 'Leyendo',                      'Read': 'Leído',
    'Browsing files': 'Explorando archivos',   'Listed files': 'Archivos listados',
    'Searching files': 'Buscando en archivos', 'Searched files': 'Búsqueda completada',
    'Opening preview': 'Abriendo vista previa','Showed': 'Mostrado',
    'Taking a screenshot': 'Capturando pantalla', 'Screenshot': 'Captura',
    'Checking the page': 'Revisando la página','Checked console': 'Consola revisada',
    'Looking at': 'Viendo',                    'Viewed': 'Visto',
    'Loading skill': 'Cargando habilidad',     'Loaded skill': 'Habilidad cargada',
    'Importing file': 'Importando archivo',    'Imported file': 'Archivo importado',
    'Sharing': 'Compartiendo',                 'Shared': 'Compartido',
    'Asking a helper': 'Consultando a un ayudante', 'Helper done': 'Ayudante listo',
    'Running a command': 'Ejecutando un comando', 'Ran command': 'Comando ejecutado',
    'Running a script': 'Ejecutando un script',   'Ran script': 'Script ejecutado',
    'Saving to memory': 'Guardando en memoria','Saved to memory': 'Guardado en memoria',
    'Recalling': 'Recuperando',                'Recalled': 'Recuperado',
    'Planning': 'Planificando',                'Planned': 'Planificado',
    'Asking you': 'Preguntándote',             'Asked you': 'Te preguntó',
    'Searching the web': 'Buscando en la web', 'Searched the web': 'Búsqueda web completada',
  },
  ca: {
    'Running code': 'Executant codi',          'Ran code': 'Codi executat',
    'Creating': 'Creant',                      'Created': 'Creat',
    'Editing': 'Editant',                      'Edited': 'Editat',
    'Reading': 'Llegint',                      'Read': 'Llegit',
    'Browsing files': 'Explorant fitxers',     'Listed files': 'Fitxers llistats',
    'Searching files': 'Cercant als fitxers',  'Searched files': 'Cerca completada',
    'Opening preview': 'Obrint vista prèvia',  'Showed': 'Mostrat',
    'Taking a screenshot': 'Capturant pantalla', 'Screenshot': 'Captura',
    'Checking the page': 'Revisant la pàgina', 'Checked console': 'Consola revisada',
    'Looking at': 'Veient',                    'Viewed': 'Vist',
    'Loading skill': 'Carregant habilitat',    'Loaded skill': 'Habilitat carregada',
    'Importing file': 'Important fitxer',      'Imported file': 'Fitxer importat',
    'Sharing': 'Compartint',                   'Shared': 'Compartit',
    'Asking a helper': 'Consultant un ajudant','Helper done': 'Ajudant llest',
    'Running a command': 'Executant una ordre','Ran command': 'Ordre executada',
    'Running a script': 'Executant un script',  'Ran script': 'Script executat',
    'Saving to memory': 'Desant a la memòria', 'Saved to memory': 'Desat a la memòria',
    'Recalling': 'Recuperant',                 'Recalled': 'Recuperat',
    'Planning': 'Planificant',                 'Planned': 'Planificat',
    'Asking you': 'Preguntant-te',             'Asked you': "T'ha preguntat",
    'Searching the web': 'Cercant al web',     'Searched the web': 'Cerca web completada',
  },
};
// Base language code the conversation is in (e.g. 'es' from 'es'/'es-419').
// Falls back to 'en' whenever the language module is unavailable.
function tcLang() {
  try {
    const code = window.SandpieLanguage && SandpieLanguage.effective && SandpieLanguage.effective();
    return String(code || 'en').split(/[-_]/)[0];
  } catch (_) { return 'en'; }
}
function tcBasename(p) {
  const s = String(p || '').replace(/\/+$/, '');
  const i = s.lastIndexOf('/');
  return i >= 0 ? s.slice(i + 1) : s;
}
// → { verb, target } — verb is shown plain, target (if any) bolded after it.
// The verb is localized to the conversation language; English is the fallback.
function tcLabelParts(fname, phase, args) {
  const spec = TC_LABELS[fname];
  if (!spec) return { verb: fname || 'tool', target: '' };
  const en = phase === 'done' ? spec.done : spec.doing;
  const dict = TC_I18N[tcLang()];
  const verb = (dict && dict[en]) || en;
  let target = '';
  if (spec.target) {
    try {
      const v = JSON.parse(args || '{}')[spec.target];
      if (v) target = spec.target === 'path' ? tcBasename(v) : String(v);
    } catch (_) {}
  }
  return { verb, target };
}
// HTML for the header title: "<verb> <b><target></b>" (target optional).
// Stashes a resolved target on the box so a later re-render that has no args in
// hand (e.g. the on-abort sweep) can still show the filename instead of dropping
// to the bare verb.
function tcLabelHtml(div, fname, phase, args) {
  const parts = tcLabelParts(fname, phase, args);
  if (args !== undefined) {
    if (parts.target && div) div.dataset.tcTarget = parts.target;
  } else if (!parts.target && div && div.dataset.tcTarget) {
    parts.target = div.dataset.tcTarget;
  }
  return tcEscape(parts.verb) + (parts.target ? ' <b>' + tcEscape(parts.target) + '</b>' : '');
}

function buildToolBox(args, toolName) {
  const name = toolName || 'tool';
  const box = document.createElement('div');
  box.className = 'tool-box';
  // write_todos renders the result as a checklist card; raw JSON is noise.
  if (name === 'write_todos' || name === 'ask') return box;

  let code = '';
  try {
    const parsed = JSON.parse(args);
    if (parsed.code) code = parsed.code;                 // run_python — real code
    else if (parsed.cmd) code = parsed.cmd;              // shell — real command
    else code = JSON.stringify(parsed, null, 2);         // everything else — raw args JSON, no fabricated signature
  } catch (e) {
    code = args;                                         // non-JSON (blob) → raw tool-call text
  }
  const lines = code.split('\n').filter(l => l.trim());
  const codeHtml = lines.map(l => `<div class="line">${tcEscape(l)}</div>`).join('');
  box.innerHTML = `<div class="tool-code">${codeHtml}</div>`;
  return box;
}

// Python-REPL "thinking" loader: three chevrons with a sweep of emphasis.
// Replaces the old rotating-circle spinner; reused for tool calls and the
// thinking box. Styled by .repl-loader / @keyframes repl-sweep in sandpie.css.
const REPL_LOADER = (cls) => `<span class="repl-loader${cls ? ' ' + cls : ''}"><i>&gt;</i><i>&gt;</i><i>&gt;</i></span>`;

// write_todos renders as a normal tool call again (2026-08-31) — no longer
// suppressed as a hidden "plan" bookkeeping row. Kept as a no-op that clears any
// stale tc-plan class so existing callers (renderTcPreparing/Running/Done) are
// undisturbed.
function tcMarkPlan(div, fname) {
  if (div && div.classList) div.classList.remove('tc-plan');
}

function renderTcPreparing(div, fname, args) {
  tcMarkPlan(div, fname);
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;

  const tok = Math.ceil((args ? String(args).length : 0) / 4);

  if (!el.querySelector('.repl-loader')) {
    el.innerHTML =
      REPL_LOADER('tc-dim') +
      `<span class="tc-title tc-dim" title="${tcEscape(fname || 'tool')}">${tcLabelHtml(div, fname, 'doing', args)}…</span>` +
      '<span class="tc-meta"></span>' +
      ';
  }
  const meta = el.querySelector('.tc-meta');
  if (meta) meta.textContent = tok > 0 ? `~${tok} tok` : '';
}

function renderTcRunning(div, fname, args) {
  tcMarkPlan(div, fname);
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;
  if (!el.querySelector('.repl-loader')) {
    el.innerHTML =
      REPL_LOADER() +
      `<span class="tc-title" title="${tcEscape(fname || 'tool')}">${tcLabelHtml(div, fname, 'doing', args)}…</span>` +
      ';
  }
}

function renderTcDone(div, fname, args) {
  tcMarkPlan(div, fname);
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;
  el.innerHTML =
    '<span class="tc-prompt">&gt;&gt;&gt;</span>' +
    `<span class="tc-title tc-dim" title="${tcEscape(fname || 'tool')}">${tcLabelHtml(div, fname, 'done', args)}</span>` +
    ';
  // Tools whose result IS the point of the call render it inside the expanded box,
  // so show it by default (other tools stay collapsed behind the header toggle).
  // The user can still collapse it by clicking the header.
  //   load_image → the loaded image
  //   ask        → the pending question card
  // (write_todos used to auto-expand too — removed: the checklist card now
  //  starts collapsed like every other tool's box.)
  if (fname === 'load_image' || fname === 'ask') div.classList.add('expanded');
}

// ---- Task Register ---------------------------------------------------------
// Consecutive tool calls render inside ONE block (.msg.tool-group) titled by
// the active checklist item, instead of N loose rows each paying the conv-host
// 1rem flex gap. State is per render target (a .conv-host or a history
// DocumentFragment): the current group, its title, and the checklist as of the
// last write_todos seen ON THAT TARGET — deliberately not stream.todos, which
// during a history replay already holds the FINAL checklist and would title
// early groups with a task that hadn't started yet.
// A group ends when: a non-tool message renders (addMsg), the active checklist
// item changes (tgOnTodos), or the turn ends (the turn-end sweep). If something
// rendered after the group (thinking box, artifact, ask card), the next call
// re-anchors the group to the bottom rather than splitting it.
const _tgByTarget = new WeakMap();
const TG_CALLS = { en: ['call', 'calls'], es: ['llamada', 'llamadas'], ca: ['crida', 'crides'] };

function _tgResolveTarget(host) {
  // Mirror addMsg's target resolution so all hooks key the same element.
  return host || (activeStream() && activeStream().host) || paneScrollEl($('messages'));
}
function _tgState(target) {
  let st = _tgByTarget.get(target);
  if (!st) { st = { group: null, title: '', todos: null }; _tgByTarget.set(target, st); }
  return st;
}
function tgActiveTitle(todos) {
  const t = (todos || []).find(x => x && x.status === 'in_progress');
  return t ? (t.activeForm || t.content || '') : '';
}
// Any non-tool message ends the current run of calls. Also drops the pace
// anchor so an idle gap (user typing) never enters the ETA median.
function tgBreak(target) {
  const st = _tgByTarget.get(target);
  if (st) { st.group = null; st.lastDoneT = 0; }
}
// Full reset (conversation re-render): drop the group AND the replayed todos.
function tgReset(target) {
  if (target) _tgByTarget.set(target, { group: null, title: '', todos: null });
}
// A write_todos result landed on this target: adopt the checklist, refresh the
// open group's header, and end the group if the active item changed.
function tgOnTodos(host, todos) {
  const target = _tgResolveTarget(host);
  if (!target || !Array.isArray(todos)) return;
  const st = _tgState(target);
  st.todos = todos;
  if (st.group) {
    tgUpdate(st.group);
    if (tgActiveTitle(todos) !== st.title) st.group = null;
  }
}
// The mount point for a new tool-call div: the current group's log, creating or
// re-anchoring the group as needed. Falls back to the bare target if the DOM
// shape is unexpected, so a tool call is never silently dropped.
function tgLogFor(target) {
  const st = _tgState(target);
  // The pane was cleared/re-rendered under us (contains() also works on fragments).
  if (st.group && !target.contains(st.group)) st.group = null;
  // No checklist item in_progress → an UNTITLED register. Visible (Claude-mode
  // todos have no plan-first gate, so real work can run before/without a
  // checklist): the header self-titles from the latest call's own label
  // (tgUpdate). A group holding only planning/bookkeeping hides via .tg-empty.
  const title = tgActiveTitle(st.todos);
  const untitled = !title;
  if (st.group && (st.group.classList.contains('tg-untitled') !== untitled
                   || (!untitled && st.title !== title))) st.group = null;
  if (!st.group) {
    // Merge instead of duplicating: if the last VISIBLE thing in the pane is
    // already a register with this exact title (the run was broken by something
    // invisible — a hidden reminder, a collapsed/hidden thinking box, a mid-turn
    // compaction), adopt it rather than stacking a second same-title block.
    // Any visible element between (a user bubble, a reply) stops the scan and a
    // fresh block is correct.
    let prev = null;
    const inDoc = !!target.isConnected;   // offsetParent is meaningless inside a fragment
    for (let n = target.lastElementChild; n; n = n.previousElementSibling) {
      if (n.classList && (n.classList.contains('msg-timer') || n.classList.contains('think'))) continue;
      if (inDoc && n.offsetParent === null && !(n.classList && n.classList.contains('tool-group'))) continue;
      prev = n;
      break;
    }
    if (prev && prev.classList && prev.classList.contains('tool-group')
        && (untitled
            ? prev.classList.contains('tg-untitled')
            : (!prev.classList.contains('tg-untitled')
               // Compare the ENGLISH title (dataset.tgEn), not the visible .tg-title,
               // which may already be localized — else the merge would never match.
               && ((prev.dataset && prev.dataset.tgEn != null ? prev.dataset.tgEn : (prev.querySelector('.tg-title') || {}).textContent) === title)))) {
      st.group = prev;
      st.title = untitled ? '' : title;
      prev.dataset.tgEn = st.title;
      prev._tgSt = st;
    } else {
      st.title = untitled ? '' : title;
      st.group = _tgBuild(st.title, st);
      if (untitled) st.group.classList.add('tg-untitled');
      appendContent(target, st.group);
    }
  } else {
    // Something (thinking box, artifact, ask card) rendered below the group —
    // move the group back to the bottom so the run stays one block.
    let n = st.group.nextElementSibling;
    while (n && n.classList && n.classList.contains('msg-timer')) n = n.nextElementSibling;
    if (n) appendContent(target, st.group);
  }
  return st.group.querySelector(':scope > .tg-log') || target;
}
function _tgBuild(title, st) {
  const g = document.createElement('div');
  g.className = 'msg tool-group';
  g._tgSt = st;
  g.dataset.tgEn = title || '';
  const hd = document.createElement('div');
  hd.className = 'tg-hd';
  // Tray layout: row 1 is pure text (prompt + title + chevron, title wrapping
  // internally); the cells + counter live in a tinted footer tray beneath a
  // hairline, so the machinery reads as its own stratum.
  hd.innerHTML =
    '<span class="tg-row">' +
      '<span class="tg-prompt">&gt;&gt;&gt;</span>' +
      `<span class="tg-title" title="${tcEscape(title)}">${tcEscape(title)}</span>` +
    '</span>' +
    '<span class="tg-tray">' +
      '<span class="tg-strip"></span>' +
      '<span class="tg-count"></span>' +
    '</span>';
  hd.addEventListener('click', (ev) => { ev.stopPropagation(); g.classList.toggle('tg-open'); });
  const log = document.createElement('div');
  log.className = 'tg-log';
  g.append(hd, log);
  return g;
}
// Repaint a group's header (call count, checklist progress, cell strip) from
// its current DOM. Cheap enough to run per tool event; an emptied group (its
// only call was a removed respond box) removes itself.
function tgUpdate(group) {
  if (!group || !group.classList || !group.classList.contains('tool-group')) return;
  const log = group.querySelector(':scope > .tg-log');
  const all = log ? [...log.querySelectorAll(':scope > .msg.tool-call')] : [];
  if (!all.length) {
    if (group._tgSt && group._tgSt.group === group) group._tgSt.group = null;
    group.remove();
    return;
  }
  // write_todos is a normal tool call again (2026-08-31): it renders in the log,
  // counts, and appears in the cell strip like any other tool. (Previously it was
  // suppressed as bookkeeping via tc-plan.)
  const calls = [];
  for (const el of all) {
    el.classList.remove('tc-plan');
    calls.push(el);
  }
  group.classList.toggle('tg-empty', !calls.length);
  // Untitled register: the header mirrors the LATEST call's own label ("Saving
  // to memory…" → "Saved to memory") instead of a fabricated task name.
  if (group.classList.contains('tg-untitled')) {
    const last = calls[calls.length - 1];
    const t = last ? ((last.querySelector('.tc-title') || {}).textContent || '') : '';
    const titleEl = group.querySelector('.tg-title');
    if (titleEl && titleEl.textContent !== t) { titleEl.textContent = t; titleEl.title = t; }
  }
  // ETA: only the register of the CURRENTLY ACTIVE task measures itself
  // against the model's est (expected tool calls, declared in write_todos);
  // settled and untitled registers show a plain count.
  const tds = (group._tgSt && group._tgSt.todos) || [];
  const act = tds.find(t => t && t.status === 'in_progress');
  const est = (!group.classList.contains('tg-untitled')
               && act && (act.activeForm || act.content || '') === (group._tgSt && group._tgSt.title)
               && Number.isFinite(+act.est) && +act.est > 0) ? Math.round(+act.est) : 0;
  // Counter: "[14/~20 · ≈17s]" while under the estimate, an honest "[23/20+]"
  // past it (no negative countdown), plain "[6]" otherwise. Pops on change.
  // The brackets ARE the label -- they mark the figure as the machine's own
  // counter (same voice as the [s] mark and the >>> prompt), which is why the
  // word "calls" is gone from the row. It is not lost: the localised long form
  // moves to the title attribute, so hovering still says "6 calls".
  const countEl = group.querySelector('.tg-count');
  if (countEl) {
    const w = TG_CALLS[tcLang()] || TG_CALLS.en;
    const word = calls.length + ' ' + (calls.length === 1 ? w[0] : w[1]);
    let txt;
    if (est && calls.length > est) txt = calls.length + '/' + est + '+';
    else if (est) {
      txt = calls.length + '/~' + est;
      const eta = _tgEtaText(group._tgSt, est - calls.length);
      if (eta) txt += ' · ≈' + eta;
    } else txt = String(calls.length);
    txt = '[' + txt + ']';
    if (countEl.title !== word) countEl.title = word;
    if (countEl.textContent !== txt) {
      countEl.textContent = txt;
      countEl.classList.remove('tick');
      void countEl.offsetWidth;
      countEl.classList.add('tick');
    }
  }
  // One cell per call, uncapped, plus HOLLOW cells for the estimated remainder
  // (they fill left-to-right as calls land — a truthful progress meter; none
  // once the estimate is exceeded). Reconciled INCREMENTALLY, never rebuilt:
  // existing cells keep their DOM node so only a genuinely new cell plays the
  // entrance animation (tg-cell-in stretches the block smoothly).
  const strip = group.querySelector('.tg-strip');
  if (strip) {
    const hollow = est > calls.length ? Math.min(est - calls.length, 60) : 0;
    const total = calls.length + hollow;
    let cells = strip.querySelectorAll(':scope > .tg-cell');
    for (let i = cells.length; i < total; i++) {
      strip.appendChild(Object.assign(document.createElement('span'), { className: 'tg-cell' }));
    }
    for (let i = cells.length - 1; i >= total; i--) cells[i].remove();
    cells = strip.querySelectorAll(':scope > .tg-cell');
    cells.forEach((c, i) => {
      const call = calls[i];
      c.classList.toggle('est', !call);
      c.classList.toggle('run', !!(call && call.classList.contains('in-flight')));
    });
  }
}
// Median observed seconds-per-call on this target × remaining estimated calls
// → "17s" / "2m 05s". '' until at least two live samples exist (history replay
// records none), so a reload never shows a made-up time.
function _tgEtaText(st, remaining) {
  const d = st && st.durs;
  if (!d || d.length < 2 || remaining <= 0) return '';
  const s = d.slice().sort((a, b) => a - b);
  const sec = Math.round(s[Math.floor(s.length / 2)] * remaining);
  if (sec < 1) return '';
  if (sec < 60) return sec + 's';
  return Math.floor(sec / 60) + 'm ' + String(sec % 60).padStart(2, '0') + 's';
}

class RoundRenderer {
  constructor(host, convMessages, isLocal = false, convId = null) {
    this.host = host;
    this.convMessages = convMessages;
    this.isLocal = isLocal;
    this.convId = convId;

    this.reply = null;
    this._streamReveal = false;

    this.content = '';
    this.displayed = '';
    this.pending = '';
    this.toolCalls = [];
    this.toolCallEls = [];
    this.toolDisplayed = [];
    this.toolPending = [];
    this.toolsShouldClose = false;
    this.drainTimer = null;
    this.pendingToolResultDiv = null;
    this.reasoning = '';
    this.thinkEl = null;
    this.thinkBody = null;
    this.thinkSummary = null;
    this.thinkStart = 0;
    this._thinkDone = false;
  }

  startRound() {
    if (this.drainTimer) { clearTimeout(this.drainTimer); this.drainTimer = null; }
    this._flushAllPending();
    // The PREVIOUS round's bubble is created empty and only removed by endRound.
    // Any path that skips endRound (abort, a provider error that isn't retried)
    // leaves an empty assistant strip on screen, and startRound is where we lose
    // the last reference to it — so clear it here before taking a new one.
    // Checked after _flushAllPending, so genuinely-streamed text is never dropped.
    if (this.reply && !(this.content && this.content.trim())) this.reply.remove();
    // Created lazily by _ensureReply() only once there's real content to show, so
    // an empty <div class="msg assistant"> never sits in the DOM during generation
    // (cloud turns route content to the thinking box, so many rounds have none).
    this.reply = null;
    this.content = '';
    this.displayed = '';
    this.pending = '';
    this.toolCalls.length = 0;
    this.toolCallEls.length = 0;
    this.toolDisplayed.length = 0;
    this.toolPending.length = 0;
    this.toolsShouldClose = false;
    this.reasoning = '';
    this.thinkEl = null;
    this.thinkBody = null;
    this.thinkSummary = null;
    this._thinkNode = null;
    this.thinkStart = 0;
    this._thinkDone = false;
    this._streamReveal = false;
    this._liveT0 = 0;   // live render-rate window — reset per round (see _trackLiveRate)
    const nnEl = document.querySelector('.msg-timer:not(.done) .mt-nn');
    if (nnEl) nnEl.classList.remove('thinking');
  }
  // A mid-stream provider error killed the previous attempt of this round after
  // some deltas already rendered; the worker is retrying the same round. Remove
  // the partial bubbles so the retry doesn't paint a duplicate copy of the text.
  retryRound() {
    if (this.reply) { this.reply.remove(); this.reply = null; }
    if (this.thinkEl) { this.thinkEl.remove(); this.thinkEl = null; }
    // Collect the registers holding this round's boxes BEFORE removing them, so
    // an emptied group can remove itself (tgUpdate) instead of lingering.
    const groups = new Set();
    for (const el of this.toolCallEls) if (el) { const g = el.closest('.msg.tool-group'); if (g) groups.add(g); el.remove(); }
    for (const g of groups) tgUpdate(g);
    this.startRound();
  }
  applyDelta(delta) {
    if (!delta) return;
    this._trackLiveRate(delta);
    // Intrinsic reasoners (DeepSeek/Kimi/GLM via OpenRouter) stream their chain
    // of thought as reasoning_content (or reasoning). Render it live, but never
    // fold it into this.content — it must not be replayed back to the model.
    const r = (typeof delta.reasoning_content === 'string' && delta.reasoning_content)
           || (typeof delta.reasoning === 'string' && delta.reasoning);
    if (r) this._appendReasoning(r);
    if (delta.content) {
      // Cloud turns force respond(): the ONLY visible reply is respond()'s text
      // (painted at round end from round.content). The model's own content is NOT
      // the reply — but it isn't thrown away either: fold it into the thinking box
      // like chain-of-thought, so nothing is lost, just tucked away collapsed.
      // Local models have no respond()/tool_choice, so they stream normally.
      if (this.isLocal) { this._finishThinking(); this._appendContent(delta.content); }
      else this._appendReasoning(delta.content);
    }
    if (delta.tool_calls) {
      for (const tc of delta.tool_calls) this._applyToolCallDelta(tc);
    }
  }
  // Live streaming tok/s — the REAL page-side ingest/render rate, measured from
  // the deltas actually applied on the main thread (est. chars/4 tokens over
  // wall time since the round's first delta). Unlike the per-round `rate` event
  // (worker: completion_tokens/decode_ms, gated <400 tok/s for batch-report
  // artifacts, and only at round END) this updates continuously — so a stream
  // that never ends a round (e.g. the bench plain/reason providers) still shows
  // a number, and it is NOT capped, so a true high rate is visible. Written into
  // stream.lastRate so the existing timer tick paints it; the round/settled paths
  // still overwrite it at their boundaries.
  _trackLiveRate(delta) {
    const n = (typeof delta.content === 'string' ? delta.content.length : 0)
            + (typeof delta.reasoning_content === 'string' ? delta.reasoning_content.length : 0)
            + (typeof delta.reasoning === 'string' ? delta.reasoning.length : 0);
    if (n <= 0) return;
    const now = performance.now();
    if (!this._liveT0) { this._liveT0 = now; this._liveChars = n; this._liveLastPaint = now; return; }
    this._liveChars += n;
    if (now - this._liveLastPaint < 250) return;   // repaint at most ~4x/s
    this._liveLastPaint = now;
    const secs = (now - this._liveT0) / 1000;
    if (secs < 0.25) return;
    const rate = (this._liveChars / 4) / secs;     // ~tokens/s, UNCAPPED (real render rate)
    const s = convStreams.get(this.convId);
    if (s) { s.lastRate = rate;
      const _sl = _streamOwnsPaneSlot(s) ? _timerSlotFor(s) : null;
      if (_sl) _paintRate(_sl, rate, this.convId); }
  }
  endRound(finalContent, localeOverride) {
    this._finishThinking();
    // CASE A - the reply from a respond()/cloud turn. The worker delivers the whole
    // ready answer in ONE hunk (cloud deltas go to the reasoning box, never into
    // this.content), so nothing was live-typed. Paint it ONCE, synchronously —
    // no typewriter reveal (removed 2026-09-02: the reveal re-ran the full
    // marked+DOMPurify render every drain tick, O(n²) on long replies).
    if (typeof finalContent === 'string' && finalContent && !(this.content && this.content.trim())) {
      // ONE-SHOT paint (2026-09-02): the reply arrives complete at round end, so
      // render it once — no typewriter reveal, no pending/drain churn. The old
      // reveal re-ran renderMd (marked+DOMPurify over ALL text) every 16-400ms
      // tick, O(n²) across the reveal; the full render now happens exactly once.
      this._streamReveal = false;
      this.content = finalContent;   // CANONICAL (English) — persisted/re-sent; never localized
      this.displayed = finalContent;
      this.pending = '';
      this.toolsShouldClose = true;
      // Language behavior is carried by the system-prompt directive only
      // (author-in-English / native regimes): the reply is painted as authored,
      // once. No display-side translation layer.
      this._paintContent();
      this._unveilLadder();
      return;
    }
    // CASE B - anything already live-typed (local models, or completions that leaked
    // native tool-call tokens). Force-complete the typewriter tail now, synchronously
    // (see drain comments), then reconcile the authoritative final content.
    this._flushAllPending();
    if (typeof finalContent === 'string' && finalContent !== this.content) {
      this.content = finalContent;
      this.displayed = finalContent;
      this.pending = '';
      this._paintContent();
    }
    this.toolsShouldClose = true;
    this._scheduleDrain();

    if (this.reply && (!this.content || !this.content.trim())) {
      this.reply.remove();
      this.reply = null;
    }
  }

  bindMessage(msg, workerPersisted) {
    this.convMessages.push(msg);
    // Persist the just-committed round so a mid-turn crash can't lose it. When
    // the completions worker owns persistence (workerPersisted=true) the JSONL
    // is already written by it — no page timer needed. Fall back to the 1.2s
    // incremental save only when the worker couldn't append (no jsonl_path or
    // a write error), so nothing is ever lost.
    if (!workerPersisted) scheduleIncrementalSave(this.convId);
    // A steered mid-turn user message the worker just spliced into its loop and
    // echoed back. Bind it to the provisional bubble steerActive() already put on
    // screen (FIFO), or render one if none is pending; mark it reconciled so the
    // finally-block cleanup won't re-add it.
    if (msg.role === 'user' && msg._steer) {
      const s = convStreams.get(this.convId);
      const pend = s && s._pendingSteer && s._pendingSteer.find(p => !p.msg);
      if (pend) { pend.msg = msg; bindBubble(pend.el, msg); }
      else bindBubble(addMsg('user', msg.content, this.host, true), msg);
      return;
    }
    if (msg.role === 'assistant') {
      this._boundMessage = msg;   // so tool boxes created later (leaked calls) can bind too
      if (this.reply) bindBubble(this.reply, msg);
      for (const el of this.toolCallEls) if (el) bindBubble(el, msg);
    } else if (msg.role === 'tool' && this.pendingToolResultDiv) {
      bindBubble(this.pendingToolResultDiv, msg);
      this.pendingToolResultDiv = null;
    }
  }
  markToolStarted(tc) {
    // respond() has no box (rendered as the reply bubble) — don't let the
    // no-box fallback build one for it.
    if (tc && tc.function && tc.function.name === 'respond') return;
    let idx = this.toolCalls.findIndex(t => t && t.id === tc.id);
    // No box for this call yet — happens when the model emitted its tool calls as
    // leaked/Hermes TEXT rather than structured streaming deltas, so _applyToolCallDelta
    // never ran. Build one now from the authoritative tc (id + name + arguments) so
    // the call — and its result in markToolDone — actually render. Without this the
    // tool executes and the model sees the output, but the user sees nothing.
    if (idx < 0 || !this.toolCallEls[idx]) {
      idx = this._ensureToolBox(tc);
      if (idx < 0) return;
    }
    this.toolCallEls[idx].classList.add('in-flight');
    renderTcRunning(this.toolCallEls[idx], tc.function.name, tc.function.arguments);
    tgUpdate(this.toolCallEls[idx].closest('.msg.tool-group'));
  }
  // Create a tool-call box for a call that never streamed as deltas. Returns its
  // index (or -1 if it can't be built). Mirrors _applyToolCallDelta's box setup.
  _ensureToolBox(tc) {
    if (!tc || !tc.function || !tc.function.name) return -1;
    const i = this.toolCalls.length;
    this.toolCalls[i] = { id: tc.id || '', type: 'function', function: { name: tc.function.name, arguments: tc.function.arguments || '' } };
    this.toolCallEls[i] = addMsg('tool-call', '→ ' + tc.function.name + '(', this.host);
    this.toolCallEls[i].dataset.fname = tc.function.name;
    this.toolCallEls[i].dataset.tcId = tc.id || '';
    this.toolDisplayed[i] = '';
    this.toolPending[i] = '';
    this._paintTool(i);
    if (this._boundMessage) bindBubble(this.toolCallEls[i], this._boundMessage);
    return i;
  }
  markToolDone(tcId, result) {
    // respond(): the reply is already painted into the assistant bubble by
    // endRound (the worker set round.content to respond's text before round_end),
    // and respond has no tool box. Just drop any box that slipped through for this
    // id and stop — never fall through to the "attach to an in-flight box"
    // fallback below, which would staple this result onto a different tool.
    if (String(result || '').replace(/^\[r\d+\]\s*/, '').startsWith('respond:')) {
      const j = this.toolCalls.findIndex(t => t && t.id === tcId);
      if (j >= 0 && this.toolCallEls[j]) {
        const g = this.toolCallEls[j].closest('.msg.tool-group');
        this.toolCallEls[j].remove(); this.toolCallEls[j] = null;
        tgUpdate(g);   // an emptied group removes itself
      }
      return;
    }
    let idx = this.toolCalls.findIndex(t => t && t.id === tcId);
    let el = idx >= 0 ? this.toolCallEls[idx] : null;
    // Fallback: if the result's id doesn't match a tracked call (the executed
    // tool-call id can diverge from what streamed — e.g. leaked/normalized ids),
    // attach to the box that's still in-flight so the output is NEVER silently
    // dropped. Without this the tool runs, the model sees the result, and the
    // user sees an empty tool box.
    if (!el) {
      for (let k = this.toolCallEls.length - 1; k >= 0; k--) {
        if (this.toolCallEls[k] && this.toolCallEls[k].classList.contains('in-flight')) { el = this.toolCallEls[k]; idx = k; break; }
      }
    }
    if (el) {
      el.classList.remove('in-flight');
      const g = el.closest('.msg.tool-group');
      // Pace sample for the ETA: the gap between CONSECUTIVE call completions,
      // not the tool's own execution time — most tools finish in milliseconds,
      // while the real per-call cost is the model round-trip between calls
      // (timing only execution made every ETA round to 0s and never show).
      // The 2-minute cap keeps a stall/pause from poisoning the median, and
      // tgBreak clears lastDoneT so cross-turn idle gaps never enter. Live-only
      // by construction: history replay never passes through here.
      if (g && g._tgSt) {
        const st = g._tgSt, now = performance.now();
        if (st.lastDoneT && now - st.lastDoneT < 120000) {
          const durs = st.durs || (st.durs = []);
          durs.push((now - st.lastDoneT) / 1000);
          if (durs.length > 20) durs.shift();
        }
        st.lastDoneT = now;
      }
      renderTcDone(el, (idx >= 0 && this.toolCalls[idx] && this.toolCalls[idx].function.name) || el.dataset.fname, (idx >= 0 && this.toolCalls[idx] && this.toolCalls[idx].function.arguments) || undefined);
      tgUpdate(g);
    }
    const text = String(result || '');
    // Sentinel checks ignore the citable result-id tag ("[rN] ") the worker
    // prepends to tool results — it lands BEFORE "artifact:"/"image:".
    const sent = text.replace(/^\[r\d+\]\s*/, '');

    if (sent.startsWith('artifact:')) {
      const path = sent.slice('artifact:'.length);
      if (path) renderArtifact(this.host, path);
      return;
    }

    if (sent.startsWith('image:')) {
      // Path = everything after 'image:' up to the first newline — caption
      // branches append the caption on following lines after the bare path.
      const path = sent.slice('image:'.length).split('\n')[0].trim();
      if (path && el) appendToolResultImage(el, path, this.host);
      return;
    }

    if (sent.startsWith('todos:')) {
      const nl = sent.indexOf('\n');
      const json = sent.slice('todos:'.length, nl < 0 ? undefined : nl);
      let todos = null;
      try { todos = JSON.parse(json); } catch (_) {}
      // Fallback: missing/truncated 'todos:' JSON (torn JSONL read mid-append,
      // or a result cut past 30kB) renders the stream's restored checklist
      // instead of an empty box.
      if (!(todos && todos.length)) {
        const s = convStreams.get(this.convId);
        if (s && Array.isArray(s.todos) && s.todos.length) todos = s.todos;
      }
      if (todos) {
        // Attribute todos to the conversation that PRODUCED them (this renderer's
        // own conv), not whatever is active now — otherwise switching away as a
        // turn finishes (or background/side-panel generation) leaks the checklist
        // onto the active conversation.
        const s = convStreams.get(this.convId);
        if (s) s.todos = todos;
      }
      if (todos && el) renderTodos(el, todos, this.host);
      if (todos) tgOnTodos(this.host, todos);
      return;
    }

    if (sent.startsWith('answers:')) {
      // Answered ask questions — render a human-readable Q → A summary into the
      // box (the raw 'answers:[...]' JSON stays model-only).
      const nl = sent.indexOf('\n');
      const json = sent.slice('answers:'.length, nl < 0 ? undefined : nl);
      let answers = null;
      try { answers = JSON.parse(json); } catch (_) {}
      if (Array.isArray(answers) && answers.length && el) renderAnswers(el, answers, this.host);
      else if (el) appendToolResult(el, text, this.host);
      return;
    }
    // Show the full tool result — the user sees exactly what the model sees.
    if (el) appendToolResult(el, text, this.host);
  }
  finalize() {

    if (this._streamReveal) {
      // A respond()/cloud reply is mid-typewriter-reveal: endRound enqueued it
      // into pending and the scheduled drain is already running to type it out. This
      // turn is terminal - nothing after it starves the drain - so just let the
      // reveal finish on its own. Do NOT flush or cancel the scheduled drain.
      this._streamReveal = false;
      this._scheduleDrain();
      return;
    }
    if (this.drainTimer) { clearTimeout(this.drainTimer); this.drainTimer = null; }
    this.toolsShouldClose = true;
    this._flushAllPending();
    this._finishThinking();
    // Full markdown render deferred from local inference — do it once now, then scroll.
    if (this.isLocal && this.reply && this.displayed) {
      streamDiff(this.reply.querySelector('.bubble') || this.reply, renderMd(this.displayed));
      hydrateLocalRefs(this.reply);
    }
    if (this.isLocal) {
      const sh = this._scrollHost();
      if (sh && shouldAutoScroll(sh)) requestAnimationFrame(() => { sh.scrollTop = sh.scrollHeight; });
    }
  }

  _appendReasoning(chunk) {
    if (!this.thinkEl) this._createThinkBox();
    this.reasoning += chunk;
    // Append-only paint: keep ONE text node and appendData each chunk. The old
    // `thinkBody.textContent = this.reasoning` re-serialized the WHOLE reasoning
    // on every delta — O(n) per delta = O(n²) per stream, the main-thread bottleneck
    // at high token rates. Plain text node: no markdown/KaTeX by design.
    if (!this._thinkNode || this._thinkNode.parentNode !== this.thinkBody) {
      this._thinkNode = document.createTextNode('');
      this.thinkBody.appendChild(this._thinkNode);
    }
    this._thinkNode.appendData(chunk);
    const sh = this._scrollHost();
    if (sh && shouldAutoScroll(sh)) sh.scrollTop = sh.scrollHeight;
  }
  _createThinkBox() {
    this.thinkStart = performance.now();
    const det = document.createElement('details');
    det.className = 'msg think';
    det.open = false;
    const sum = document.createElement('summary');
    sum.innerHTML = 'Thinking ' + REPL_LOADER();
    const body = document.createElement('div');
    body.className = 'think-body';
    det.appendChild(sum);
    det.appendChild(body);
    // Sit the box just above this round's reply bubble so thinking reads first.
    const nnEl = document.querySelector('.msg-timer:not(.done) .mt-nn');
    if (nnEl) nnEl.classList.add('thinking');
    if (this.reply && this.reply.parentNode) {
      this.reply.parentNode.insertBefore(det, this.reply);
    } else {
      appendContent(this.host || paneScrollEl($('messages')), det);
    }
    this.thinkEl = det;
    this.thinkBody = body;
    this.thinkSummary = sum;
    this._thinkNode = null;
  }
  _finishThinking() {
    if (!this.thinkEl || this._thinkDone) return;
    this._thinkDone = true;
    // A box with no thinking in it is just an empty strip on screen. Providers do
    // emit reasoning deltas that are only whitespace (or a lone newline), and
    // _appendReasoning creates the box on the first one — so the box can outlive
    // having anything to show. Drop it instead of finishing it.
    if (!this.reasoning || !this.reasoning.trim()) {
      this.thinkEl.remove();
      this.thinkEl = null;
      this.thinkBody = null;
      this.thinkSummary = null;
      const nn0 = document.querySelector('.msg-timer:not(.done) .mt-nn');
      if (nn0) nn0.classList.remove('thinking');
      return;
    }
    const secs = Math.round((performance.now() - this.thinkStart) / 1000);
    this.thinkSummary.textContent = secs > 0 ? ('Thought for ' + secs + 's') : 'Thought';
    this.thinkEl.classList.add('done');
    const nnEl = document.querySelector('.msg-timer:not(.done) .mt-nn');
    if (nnEl) nnEl.classList.remove('thinking');
    this.thinkEl.open = false;
  }

  _appendContent(chunk) {

    this.content += chunk;
    this.pending += chunk;
    this._scheduleDrain();
  }
  // Create the assistant reply div on demand. Never called for empty content, so
  // the DOM never holds an empty <div class="msg assistant">.
  _ensureReply() {
    if (this.reply && this.reply.parentNode) return this.reply;
    this.reply = addMsg('assistant', '', this.host);
    if (this._boundMessage) bindBubble(this.reply, this._boundMessage);
    return this.reply;
  }
  // Line Ladder unveil — stagger-reveal the top-level blocks of a freshly
  // painted respond() reply. Pure visual overlay on the already-rendered DOM:
  // no re-render, no layout properties animated. Blocks = direct children of
  // the bubble; a <table> (or <pre>) adopts the sibling right before it so a
  // table never detaches from its intro/caption line. Lists reveal as ONE
  // block (per-<li> staggering made bullets appear detached from markers).
  // Idempotent: re-entry while a reveal runs finishes it instantly first.
  _unveilLadder() {
    const el = this.reply;
    if (!el || !el.isConnected) return;
    if (this._llTimer) { clearTimeout(this._llTimer); this._llTimer = null; }
    el.classList.remove('ll-play');
    const bubble = el.querySelector('.bubble') || el;
    const kids = Array.from(bubble.children);
    if (kids.length < 2) return;                       // single-block reply: nothing to ladder
    const groups = [];
    for (const k of kids) {
      const prev = groups[groups.length - 1];
      if (prev && (k.tagName === 'TABLE' || k.tagName === 'PRE') && !prev._llKeep) {
        prev.appendChild(k); prev._llKeep = true;      // table/pre travels with its intro
      } else {
        const g = document.createElement('div');
        g.className = 'll-block';
        bubble.replaceChild(g, k); g.appendChild(k);
        groups.push(g);
      }
    }
    const STEP = 120;
    groups.forEach((g, i) => { g.style.setProperty('--ll-d', (i * STEP) + 'ms'); });
    void bubble.offsetWidth;                           // commit hidden state before playing
    el.classList.add('ll-play');
    this._llTimer = setTimeout(() => {
      this._llTimer = null;
      el.classList.remove('ll-play');
      for (const g of groups) {                        // unwrap: restore original DOM
        while (g.firstChild) bubble.insertBefore(g.firstChild, g);
        g.remove();
      }
    }, groups.length * STEP + 450);
  }
  _paintContent() {
    // Nothing to show yet → don't materialize an empty bubble; drop a stale empty one.
    if (!this.displayed) {
      if (this.reply && !(this.content && this.content.trim())) { this.reply.remove(); this.reply = null; }
      return;
    }
    this._ensureReply();
    if (this.isLocal) {
      // Skip marked+DOMPurify per token — main thread stays free for GPU inference.
      // Full markdown render happens once in finalize() when generation is done.
      const bubble = this.reply.querySelector('.bubble') || this.reply;
      streamDiff(bubble, `<div>${this.displayed}</div>`);
      return;
    }
    streamDiff(this.reply.querySelector('.bubble') || this.reply, renderMd(this.displayed));
    hydrateLocalRefs(this.reply);
  }
  _applyToolCallDelta(tc) {
    const i = tc.index || 0;
    if (!this.toolCalls[i]) {
      this.toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
    }
    if (tc.id) this.toolCalls[i].id = tc.id;
    if (tc.function?.name) this.toolCalls[i].function.name += tc.function.name;
    if (tc.function?.arguments) this.toolCalls[i].function.arguments += tc.function.arguments;
    if (!this.toolCalls[i].function.name) return;
    // respond() is never drawn as a tool box — its text renders as the assistant
    // reply bubble (endRound). Bail before creating a box so no raw {"text":…}
    // JSON flashes on screen. The prefix test also covers partially-streamed names
    // ("r","re"…); r-prefixed real tools (read_file/recall/remember) diverge within
    // a char or two and get their box then, a sub-frame later.
    { const nm = this.toolCalls[i].function.name;
      if (nm === 'respond' || 'respond'.startsWith(nm)) return; }
    if (!this.toolCallEls[i]) {

      this.toolCallEls[i] = addMsg('tool-call', '→ ' + this.toolCalls[i].function.name + '(', this.host);
      this.toolCallEls[i].dataset.fname = this.toolCalls[i].function.name;
      this.toolCallEls[i].dataset.tcId = this.toolCalls[i].id;
      this.toolDisplayed[i] = '';
      this.toolPending[i] = '';
    }
    // The box is created on the first delta that carries a name; the id can arrive
    // in a later delta. Keep dataset.tcId in sync so the tool_result (matched by
    // id) still finds this box instead of silently dropping the output.
    if (this.toolCalls[i].id && this.toolCallEls[i].dataset.tcId !== this.toolCalls[i].id) {
      this.toolCallEls[i].dataset.tcId = this.toolCalls[i].id;
    }
    // Same for the name: it can stream in pieces, and the register's planning
    // filter (tc-plan) keys off dataset.fname — keep it current.
    if (this.toolCallEls[i].dataset.fname !== this.toolCalls[i].function.name) {
      this.toolCallEls[i].dataset.fname = this.toolCalls[i].function.name;
      tgUpdate(this.toolCallEls[i].closest('.msg.tool-group'));
    }
    if (tc.function?.arguments) {
      this.toolPending[i] = (this.toolPending[i] || '') + tc.function.arguments;
      this._scheduleDrain();
    }
    if (!this.toolCallEls[i].classList.contains('in-flight')) {
      renderTcPreparing(this.toolCallEls[i], this.toolCalls[i].function.name, this.toolCalls[i].function.arguments);
    }
  }
  _scheduleDrain() {
    if (this.drainTimer != null) return;
    // Cloud replies are painted ONE-SHOT at endRound (no typewriter), so on cloud
    // the drain only trickles tool-call args into their boxes (cheap: JSON.parse +
    // escape, no marked/DOMPurify). Local inference still streams content through
    // here and defers markdown to finalize (_paintContent), so its drains are cheap
    // too. The growth-stretched interval stays as a safety valve for long arg streams.
    const n = this.isLocal ? 0 : this.displayed.length;
    const delay = n > 120000 ? 400 : n > 40000 ? 200 : n > 12000 ? 80 : 16;
    this.drainTimer = setTimeout(() => this._drainTick(), delay);
  }
  _drainTick() {
    this.drainTimer = null;
    let anyPending = false;

    const scrollHost = this._scrollHost();
    const stick = shouldAutoScroll(scrollHost);

    if (this.pending.length > 0) {
      if (this.isLocal) {
        // Local inference: tokens arrive steadily one-by-one, no burst — show all at once.
        // The /30 trickle was designed for bursty cloud streams; here it just delays display.
        this.displayed += this.pending;
        this.pending = '';
      } else {
        const n = Math.max(1, Math.ceil(this.pending.length / 30));
        this.displayed += this.pending.slice(0, n);
        this.pending = this.pending.slice(n);
        if (this.pending.length > 0) anyPending = true;
      }
      this._paintContent();
    }

    for (let i = 0; i < this.toolPending.length; i++) {
      const buf = this.toolPending[i];
      if (!buf || buf.length === 0) continue;
      const n = Math.max(1, Math.ceil(buf.length / 30));
      this.toolDisplayed[i] = (this.toolDisplayed[i] || '') + buf.slice(0, n);
      this.toolPending[i] = buf.slice(n);
      this._paintTool(i);
      if (this.toolPending[i].length > 0) anyPending = true;
    }
    this._appendCloseParensIfReady();

    if (scrollHost && stick && !this.isLocal) scrollHost.scrollTop = scrollHost.scrollHeight;
    if (anyPending) this._scheduleDrain();
  }

  _scrollHost() {
    return climbScrollEl(this.reply || this.host);
  }

  _flushAllPending() {

    if (this.pending.length > 0) {
      this.displayed += this.pending;
      this.pending = '';
      this._paintContent();
    }

    for (let i = 0; i < this.toolPending.length; i++) {
      const buf = this.toolPending[i] || '';
      if (buf.length > 0) {
        this.toolDisplayed[i] = (this.toolDisplayed[i] || '') + buf;
        this.toolPending[i] = '';
        this._paintTool(i);
      }
    }
    this._appendCloseParensIfReady();
  }
  _paintTool(i) {
    if (!this.toolCallEls[i] || !this.toolCalls[i]) return;
    const tc = this.toolCalls[i];
    const box = buildToolBox(tc.function.arguments, tc.function.name);
    const expanded = this.toolCallEls[i].querySelector('.tc-expanded');
    if (expanded) {

      const existingBox = expanded.querySelector('.tool-box');
      const existingSep = existingBox ? existingBox.querySelector('.tool-sep') : null;
      // Preserve whatever result was already appended — plain text, image, or the
      // todos checklist card — so a re-paint of the args doesn't wipe it.
      const existingResult = existingBox ? existingBox.querySelector('.tool-result, .tool-result-image, .tool-todos') : null;
      expanded.innerHTML = '';
      expanded.appendChild(box);
      if (existingSep) box.appendChild(existingSep);
      if (existingResult) box.appendChild(existingResult);
    }
  }
  _appendCloseParensIfReady() {
    if (!this.toolsShouldClose) return;
    for (let i = 0; i < this.toolCallEls.length; i++) {
      const el = this.toolCallEls[i];
      if (!el || el._tcClosed) continue;
      if ((this.toolPending[i] || '').length === 0) {
        el._tcClosed = true;
      }
    }
  }
}


/* =============================================================================
   UI + page glue moved out of sandpie-test.html. These were page-inline globals
   that this module already consumed (renderMd, scroll tracking, the chat input,
   the side-by-side panel, the bubble context menu, flight resume, the system
   prompt). Consolidating them here keeps the host page thin and the conversation
   surface self-contained.

   NOTE: the shared conversation STATE (messages / convStreams / convLastViewed /
   activeConvId) intentionally stays host-global in sandpie-test.html — other
   modules (artifacts, context, augmentations, mobile) read it as bare globals,
   so it can't live solely in this module.
   ============================================================================= */

/* ---- markdown rendering ---- */
function dedentPreBlocks(html) {
  const wrap = document.createElement('div');
  wrap.innerHTML = html;
  for (const pre of wrap.querySelectorAll('pre')) {
    const root = pre.querySelector('code') || pre;
    const original = root.textContent;
    if (!original) continue;
    const lines = original.split('\n');
    let minIndent = Infinity;
    for (const line of lines) {
      if (!line.trim()) continue;
      const m = line.match(/^[ \t]*/);
      if (m && m[0].length < minIndent) minIndent = m[0].length;
    }
    if (!isFinite(minIndent) || minIndent === 0) continue;
    root.textContent = lines.map(
      l => l.length >= minIndent ? l.slice(minIndent) : l,
    ).join('\n');
  }
  return wrap.innerHTML;
}
// Pull LaTeX math out of the RAW text before markdown so marked/DOMPurify can't
// mangle it (underscores, backslashes, $$ blocks). Code spans (fenced ``` and
// inline `…`) are left verbatim, so "$x$" inside code stays literal. Each math
// span becomes a private-use-char placeholder that survives marked + DOMPurify as
// plain text; renderMd swaps in the KaTeX HTML afterwards. Delimiters: $$…$$ and
// \[…\] (display), \(…\) and $…$ (inline). The $…$ rule forbids a space just
// inside the delimiters so prices like "$5 and $10" aren't captured.
const _MATH_SENTINEL = '';
function _extractMath(text) {
  const math = [];
  const stash = (latex, display, raw) => {
    const ph = _MATH_SENTINEL + 'KX' + math.length + _MATH_SENTINEL;
    math.push({ ph, latex: latex.trim(), display, raw });
    return ph;
  };
  const parts = String(text).split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  for (let i = 0; i < parts.length; i += 2) {          // even indices = non-code text
    let s = parts[i];
    if (!s || (s.indexOf('$') < 0 && s.indexOf('\\(') < 0 && s.indexOf('\\[') < 0)) continue;
    s = s.replace(/\$\$([\s\S]+?)\$\$/g, (full, m) => stash(m, true, full));
    s = s.replace(/\\\[([\s\S]+?)\\\]/g, (full, m) => stash(m, true, full));
    s = s.replace(/\\\(([\s\S]+?)\\\)/g, (full, m) => stash(m, false, full));
    s = s.replace(/(?<![\\$])\$(?!\s)([^$\n]*?[^$\n\s])\$(?!\d)/g, (full, m) => stash(m, false, full));
    parts[i] = s;
  }
  return { text: parts.join(''), math };
}
const _escHtml = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const renderMd = text => {
  if (typeof DOMPurify === 'undefined' || typeof marked === 'undefined') {
    // Defer rendering until libraries are loaded
    return '&lt;div class="pending"&gt;Loading...&lt;/div&gt;';
  }
  const { text: pretext, math } = _extractMath(text);
  let html = DOMPurify.sanitize(dedentPreBlocks(marked.parse(pretext)));
  // Swap each placeholder for KaTeX HTML (generated by KaTeX, trust:false ⇒ safe;
  // inserted post-sanitize so DOMPurify doesn't strip KaTeX's markup). Falls back
  // to the escaped source if KaTeX isn't loaded or the LaTeX is invalid.
  for (const m of math) {
    let rep;
    if (typeof katex !== 'undefined') {
      try { rep = katex.renderToString(m.latex, { displayMode: m.display, throwOnError: false, output: 'htmlAndMathml' }); }
      catch (_) { rep = _escHtml(m.raw); }
    } else {
      rep = _escHtml(m.raw);
    }
    html = html.split(m.ph).join(rep);
  }
  return html;
};

/* ---- scroll tracking (auto-stick to bottom unless the user scrolls up) ---- */
const _scrollLocked = new Set();
// The scroll container of a pane is its .conv-host when a conversation is
// mounted; fall back to the pane itself (home screen / nothing mounted).
function paneScrollEl(pane) {
  if (!pane) return null;
  const host = pane.querySelector(':scope > .conv-host');
  return host || pane;
}
// The pinned bottom cluster of a pane: the command-output panel (when shown) and
// the sticky composer. Everything else — the conv-host, home lists, stray error
// bubbles — must go ABOVE it, so this returns the first node of the cluster to
// insert before. Returns null for a .conv-host (no cluster; plain append).
function paneBottomAnchor(pane) {
  if (!pane || !pane.querySelector) return null;
  return pane.querySelector(':scope > .cmd-output') || pane.querySelector(':scope > .msg-timer-slot') || pane.querySelector(':scope > .composer');
}
// Append content into a target that may be a PANE (#messages / #messagesSide)
// rather than a .conv-host. A pane's last children are the command panel and the
// sticky composer, so a bare appendChild there renders the node BELOW the composer
// — which is how errors and banners used to escape the message column.
function appendContent(target, el) {
  if (!target || !el) return el;
  const anchor = paneBottomAnchor(target);
  if (anchor) target.insertBefore(el, anchor); else target.appendChild(el);
  return el;
}
// Climb from any element to the scroll container that holds it (.conv-host,
// else the pane mapped through paneScrollEl).
function climbScrollEl(el) {
  while (el && !(el.classList && el.classList.contains('conv-host')) && el.id !== 'messages' && el.id !== 'messagesSide') {
    el = el.parentNode;
  }
  if (!el) return null;
  if (el.classList && el.classList.contains('conv-host')) return el;
  return paneScrollEl(el);
}
function isAtBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight <= 2; }
function lockScroll(el) { if (el) _scrollLocked.add(el); }
function unlockScroll(el) { if (el) _scrollLocked.delete(el); }
function shouldAutoScroll(el) { return _scrollLocked.has(el); }

const NN_SVG_INLINE = '<svg viewBox="0 0 24 24" class="ripple"><circle cx="12" cy="12" r="1.2" class="r-c"/><circle cx="12" cy="12" r="4" class="r r1"/><circle cx="12" cy="12" r="7" class="r r2"/><circle cx="12" cy="12" r="10" class="r r3"/></svg>';

let thoughtsVisible = false;
function toggleThoughts() {
  // The class flip makes every hidden .msg.think take real space. Most boxes sit
  // ABOVE the current view, so the transcript grows upward.
  //
  // Anchoring is handled by ONE of two paths, chosen per pane:
  //  - NATIVE: browsers with overflow-anchor support and a host not mid-stream
  //    (.sp-streaming) let the BROWSER pin the viewport (measured 0px drift).
  //    Any manual correction here DOUBLES the shift — trust it, touch nothing.
  //  - MANUAL: Safari (no overflow-anchor) and streaming hosts (overflow-anchor:
  //    none) get a synchronous pin of the first visible non-think message, PLUS
  //    a settle window that re-applies the same deltas while async content
  //    (artifact iframes, KaTeX, images) finishes growing — cancelled at the
  //    instant the user scrolls.
  // A host at the bottom (or scroll-locked while a turn streams) always STAYS at
  // the bottom, waiting for the next turn.
  const _nativeOK = (() => { try { return typeof CSS !== 'undefined' && CSS.supports('overflow-anchor', 'auto'); } catch (_) { return false; } })();
  const atBottom = h => h.scrollHeight - h.scrollTop - h.clientHeight <= 2;
  const pins = [];          // {host, anchor|null, anchorTop, scrollTop} — manual re-anchor
  const follows = [];       // hosts that must stay at the bottom
  for (const pane of [$('#messages'), $('#messagesSide')]) {
    if (!pane) continue;
    const h = pane.querySelector(':scope > .conv-host');
    if (!h || !h.isConnected || h.clientHeight === 0) continue;   // hidden pane: skip
    let nativeHere = _nativeOK;
    if (nativeHere) { try { nativeHere = getComputedStyle(h).overflowAnchor !== 'none'; } catch (_) {} }
    if (nativeHere) continue;   // the browser already pins this host
    if (atBottom(h) || shouldAutoScroll(h)) { follows.push(h); continue; }
    const hr = h.getBoundingClientRect();
    let anchor = null, anchorTop = 0;
    for (const c of h.children) {
      if (c.classList && c.classList.contains('think')) continue;
      const r = c.getBoundingClientRect();
      if (r.bottom > hr.top + 1 && r.top < hr.bottom - 1) { anchor = c; anchorTop = r.top; break; }
    }
    pins.push({ host: h, anchor, anchorTop, scrollTop: h.scrollTop });
  }

  // Turning thoughts ON re-opens every FINISHED box the user had expanded before
  // hiding — their full old bodies would flash for a frame on this very event.
  // Collapse them pre-flip (one click re-expands); the live box keeps its state.
  // Measured BEFORE the flip so the deltas below also absorb the collapse shrink.
  if (!thoughtsVisible) {
    document.querySelectorAll('.msg.think[open].done').forEach(b => { b.open = false; });
  }

  thoughtsVisible = !thoughtsVisible;
  document.body.classList.toggle('thoughts-visible', thoughtsVisible);
  document.querySelectorAll('.msg-timer .mt-nn').forEach(el => {
    el.classList.toggle('on', thoughtsVisible);
    el.title = thoughtsVisible ? 'Hide thoughts' : 'Show thoughts';
  });

  // Synchronous re-anchor in the SAME task (exact even without native anchoring).
  let needSettle = false;
  for (const p of pins) {
    if (p.anchor) {
      const d = p.anchor.getBoundingClientRect().top - p.anchorTop;
      if (Math.abs(d) > 0.5) { p.host.scrollTop += d; needSettle = true; }
    } else {
      p.host.scrollTop = p.scrollTop;   // nothing visible to anchor to — hold the offset
      needSettle = true;
    }
  }
  for (const h of follows) if (!atBottom(h)) h.scrollTop = h.scrollHeight;

  // Settle window: async layout (iframes/images/KaTeX) can keep growing the
  // transcript AFTER the flip. Re-apply the same deltas until stable; cancel at
  // the first USER scroll. Listeners attach after the writes above, so our own
  // scrollTop changes don't cancel it.
  if (needSettle || follows.length) {
    let own = false, cancelled = false;
    const cbs = [];
    for (const h of [...pins.map(p => p.host), ...follows]) {
      const f = () => { if (!own) cancelled = true; };
      h.addEventListener('scroll', f, { passive: true });
      cbs.push([h, f]);
    }
    const done = () => { for (const [h, f] of cbs) h.removeEventListener('scroll', f); };
    const step = d => setTimeout(() => {
      if (cancelled) { done(); return; }
      own = true;
      let still = false;
      for (const p of pins) {
        if (p.anchor) { const dd = p.anchor.getBoundingClientRect().top - p.anchorTop; if (Math.abs(dd) > 0.5) { p.host.scrollTop += dd; still = true; } }
        else { p.host.scrollTop = p.scrollTop; still = true; }
      }
      for (const h of follows) if (!atBottom(h)) { h.scrollTop = h.scrollHeight; still = true; }
      own = false;
      if (still) step(Math.min(d * 2, 400)); else done();
    }, d);
    step(32);
  }
}

/* ---- system prompt (editable, localStorage-cached; + optional skills block) ---- */
async function buildSystemPrompt(convMessages, localizeTarget) {
  // The system prompt is an editable value cached in localStorage (Settings →
  // System prompt) — NOT a synced or browsable OPFS file. The single DEFAULT
  // literal lives in system-prompt.js (SandpieSystemPrompt.DEFAULT); the
  // fallback below only honors a stored prompt if that module somehow missed.
  // LITE MODE: minimal system prompt (no skills, no memories, no base prompt).
  // The reply-language directive below still applies (it is appended after this).
  const _liteCid = (typeof activeConvId !== 'undefined' && activeConvId) || null;
  let content;
  if (_liteCid && _liteOn(_liteCid)) {
    // LITE MODE: minimal system prompt (no skills, no memories, no base prompt).
    // The reply-language directive below still applies (it is appended after this).
    content = 'You are sandpie, a fast assistant in FAST mode. Answer directly, concisely and completely. '
      + 'You have NO tools in this mode: if the request needs files, code execution, web/search or any tool, say so in one short line and tell the user to press the FAST-mode bolt icon (next to the composer) to turn it off. '
      + 'Do not invent tool results.';
  } else {
    content = (typeof SandpieSystemPrompt !== 'undefined' && SandpieSystemPrompt.get)
      ? await SandpieSystemPrompt.get()
      : (localStorage.getItem('sandpie-system-prompt') || '');   // the DEFAULT literal lives only in SandpieSystemPrompt (this branch is unreachable — the module always loads first)
  }
  // Current local DATE (day granularity), prepended. Deliberately NOT the time:
  // this line sits at byte ~0 of every request, and provider prompt-caching only
  // works on a byte-stable prefix — a minute-level stamp here invalidated the
  // whole conversation's cache every turn. The minute-level clock now rides in
  // the ephemeral volatile-context reminder the worker appends at the END of
  // each request (see config.volatileContext), where it can't invalidate anything.
  try {
    const now = new Date();
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    const stamp = now.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    content = 'The current date is ' + stamp + (tz ? ' (' + tz + ')' : '') + '. Treat this as today; the precise time arrives with each request.\n\n' + content;
  } catch (_) {}
  const _lite = !!(_liteCid && _liteOn(_liteCid));
  // Optional capability: context.js appends the skills block (enforced skill
  // index + an instruction telling the model to fetch a skill via the load_skill
  // tool when relevant). Module absent ⇒ plain memory prompt.
  if (!_lite && typeof SandpieContext !== 'undefined' && SandpieContext.skillBlock) {
    try { content += await SandpieContext.skillBlock(convMessages); }
    catch (e) { console.warn('[sandpie] skills block failed:', e); }
  }
  // Optional capability: mindframe.js appends a Stage-0 AWARENESS directive that
  // forces the model to scan the prompt into nouns/verbs (and research unknown
  // nouns) before acting. Returns '' when the toggle is off ⇒ no behavior change.
  if (!_lite && typeof SandpieMindframe !== 'undefined' && SandpieMindframe.systemBlock) {
    try { content += SandpieMindframe.systemBlock(convMessages); }
    catch (e) { console.warn('[sandpie] mindframe block failed:', e); }
  }
  // Optional capability: memory.js injects durable facts (sandpie/memory/*.md),
  // TIERED: standing user/feedback in full, active-project facts promoted up to a
  // budget, the rest as a one-line index (recall() expands). Consolidation is
  // deterministic and event-driven off memory writes — nothing per-turn here.
  if (!_lite && typeof SandpieMemory !== 'undefined' && SandpieMemory.systemBlock) {
    // Context for tiered injection: the latest user message (keyword activation) +
    // the files touched recently (path activation) decide which project's memories
    // get promoted to full this turn (the rest are indexed). Both best-effort.
    let memCtx = {};
    try {
      const lastUser = [...(convMessages || [])].reverse().find(m => m && m.role === 'user');
      const c = lastUser && lastUser.content;
      memCtx.message = typeof c === 'string' ? c : Array.isArray(c) ? c.map(p => (p && p.text) || '').join(' ') : '';
    } catch (_) {}
    // Use THIS conversation's touched files (getConvPaths), NOT the global recent-paths
    // accumulator — in a fresh chat the global list is full of past-conversation work and
    // would wrongly activate every project. Conversation-scoped = empty on a new chat, so
    // only the current message drives activation until this chat actually touches files.
    try { if (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.getConvPaths) memCtx.paths = SandpieAugmentations.getConvPaths(activeConvId); } catch (_) {}
    try { content += await SandpieMemory.systemBlock(memCtx); }
    catch (e) { console.warn('[sandpie] memory block failed:', e); }
  }
  // NOTE: the augmentations block (Recent paths) is no longer appended here.
  // That list reshuffles on every tool call, which churned the system prompt —
  // the cached-prefix killer. It now travels in config.volatileContext and is
  // injected by the worker at the END of each request instead.
  // Reply-language directive — three regimes, decided by the model's `fluent`
  // set (models.json): (1) English session, (2) NATIVE: a fluent language the
  // model authors directly, (3) LOCALIZE: a non-fluent language (e.g. Catalan)
  // the model authors in English and the gemini localizer translates. The
  // directive text is stable per (language, model), so prompt caching survives.
  try {
    const _rl = _replyLocale();
    const _nm = (_rl && _rl.name) || 'English';
    const _cd = (_rl && _rl.code) || 'en';
    const _lx = localizeTarget || null;
    // One-off other-language deliveries. In the localize regime the hard rule
    // stays absolute (author English, ALWAYS — the system translates every
    // delivery); in the native/English regimes fluent languages are authored
    // directly and only non-fluent ones go through the translator.
    const _fluentNote = (_lx && _lx.code)
      ? "\nIf ONE deliverable/reply is requested in a DIFFERENT language, the same rule applies: author it in ENGLISH and set that language code on the delivery (\"language\" on respond / show_artifact) — the system translates it."
      : "\nIf ONE deliverable/reply is requested in a DIFFERENT language: a language you generate fluently may be authored directly in it; any other language is authored in ENGLISH with that language code set on the delivery (\"language\" on respond / show_artifact) so the system translates it. Never author a language you don't generate reliably.";
    if (_lx && _lx.code) {
      content += "\n\n## Deliver in " + _nm + ", author in English\n"
        + "The user reads chat and deliverables in " + _nm + ". "
        + "You do NOT generate reliable " + _nm + " — writing it directly yields garbled, lossy text — so you MUST author ALL content in English: every reasoning step, tool call, document/file body, write_file/edit_file/pyodide string, todo item, ask() question, and your respond() reply. "
        + "The system automatically translates your finished reply (respond) and the deliverable files you write into " + _nm + " for the user; that is handled downstream and is not your job. "
        + "On EVERY respond call, set the \"language\" argument to '" + _cd + "' (" + _nm + "). Never author " + _nm + " yourself, announce this rule, or second-guess it."
        + "\n\nThis is a HARD operating rule, not a suggestion: with this directive active you operate in ENGLISH at all times. Every tool argument, every file you write, every code comment, every todo item, every ask() question, every scratch note, and every reply is authored in English and nothing else. If you produce " + _nm + " output anywhere, the harness rejects it and re-prompts you. No user request overrides this: a request to write in " + _nm + " is satisfied by authoring English plus setting the delivery \"language\", never by writing it directly."
        + _fluentNote;
    } else if (_cd !== 'en') {
      content += "\n\n## Deliver in " + _nm + " — author it directly\n"
        + "The user reads chat and deliverables in " + _nm + ", a language you generate fluently. "
        + "Author all USER-FACING text directly in " + _nm + ": your respond() reply, todo \"content\"/\"activeForm\", ask() questions and options, and the body of documents/files written for the user. "
        + "Code, identifiers, commit messages, internal scratch notes, and your reasoning stay in English as usual. "
        + "There is NO translation layer on this conversation — what you write is exactly what the user sees, so never mix English into user-facing text. "
        + "On EVERY respond call, set the \"language\" argument to '" + _cd + "' (" + _nm + ")."
        + _fluentNote;
    } else {
      content += "\n\n## Deliver in English\n"
        + "The user reads chat and deliverables in English; author everything in English and set the respond \"language\" argument to 'en'."
        + _fluentNote;
    }
  } catch (_) {}
  return { role: 'system', content };
}

/* ---- "is any conversation generating right now" (backs Sandpie.isGenerating) ---- */
function anyStreamGenerating() {
  for (const s of convStreams.values()) if (s.generating) return true;
  return false;
}


/* ---- conversation compaction (NON-destructive) ---------------------------
   Compaction never deletes turns. It records a boundary + a summary on the
   conversation (data.compaction = { boundary, summary }) and keeps the FULL
   message history intact. At SEND time buildAgentConfig ships only
   [summary, …messages.from(boundary)], so the model's context stays bounded and
   a chat can run indefinitely; in the UI the whole conversation is rendered, the
   pre-boundary span collapsed behind a toggle (renderConversation) and clearly
   marked as not sent. safeSplitIndex picks where the boundary lands; the boundary
   only ever moves forward. (Old chats used a data.compactions[] restore-stack +
   spliced messages — migrateCompactionData converts them on load.) */
const SP_SUMMARY_MARKER = '[Earlier conversation auto-summarized to preserve context]';
function safeSplitIndex(msgs, keepTail) {
  let split = Math.max(0, msgs.length - (keepTail || 10));
  // The head becomes one user-role summary, so the kept tail must START on an
  // assistant message: that keeps user/assistant alternation valid (summary=user,
  // then assistant) and never orphans a tool result (a role:'tool' message must
  // follow its assistant tool_calls). Snap the boundary forward to the next
  // assistant message.
  while (split < msgs.length && (!msgs[split] || msgs[split].role !== 'assistant')) split++;
  return split;
}
function getCompaction(convId) {
  const s = convStreams.get(convId);
  return (s && s.compaction) || null;
}
// Resolve a conversation's live messages + compaction for compaction, whether it
// is the active conv, has a warm (but backgrounded) stream, or lives only on
// disk. For a warm stream we operate on the SAME array the UI/send path uses so
// the boundary advance is seen immediately; for a cold conv we read the file.
// Returns { msgs, compaction, stream } or null if the conv can't be found.
async function _resolveConvForCompaction(convId) {
  if (!convId) return null;
  const s = convStreams.get(convId);
  if (s && Array.isArray(s.messages) && s.messages.length) {
    return { msgs: s.messages, compaction: s.compaction || null, stream: s };
  }
  const data = await readConvData(convId);
  if (!data) return null;
  return { msgs: (data.messages || []), compaction: data.compaction || null, stream: null };
}
async function compactConversation(convId, { keepTail = 10, summary = '' } = {}) {
  const text = String(summary || '').trim();
  if (!text) return { ok: false, reason: 'empty summary' };
  const res = await _resolveConvForCompaction(convId);
  if (!res) return { ok: false, reason: 'conversation not found' };
  const msgs = res.msgs;
  const boundary = safeSplitIndex(msgs, keepTail);
  const prevBoundary = (res.compaction && res.compaction.boundary) || 0;
  if (boundary <= prevBoundary || boundary >= msgs.length) return { ok: false, reason: 'nothing new to compact' };
  // Non-destructive: keep the full history, just advance the boundary + summary.
  const compaction = { boundary, summary: text, at: new Date().toISOString() };
  if (res.stream) {
    // Warm stream (active or backgrounded): mutate it and persist messages +
    // compaction together so disk can never disagree with the live boundary.
    res.stream.compaction = compaction;
    await saveConv(convId, { touchUpdated: false });
  } else {
    // Cold conv — patch only the compaction field on the on-disk file.
    await updateConvFile(convId, { compaction, compactions: undefined });
  }
  // Re-render only when this is the on-screen active conversation; a background
  // or cold conv has no live UI to refresh (it re-reads compaction on next open).
  if (convId === activeConvId) {
    clearActiveConvUI();
    renderConversation(messages, compaction);
    const el = paneScrollEl($('messages'));
    if (el && shouldAutoScroll(el)) el.scrollTop = el.scrollHeight;
  }
  // The recorded usage still reflects the PRE-compaction (larger) context — drop
  // it so the context %-meters (and the compactor's own threshold) read the
  // reduced send size instead of a stale-high value that would re-trigger next send.
  try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.forget) SandpieTokens.forget(convId); } catch {}
  return { ok: true, removed: boundary, kept: msgs.length - boundary };
}

/* ---- native auto-compaction (pre-send) -----------------------------------
   Promoted from the old opt-in `sink: compact` agent into the harness. Config
   lives in SandpieCompactor (localStorage, on by default). The composer awaits
   maybeAutoCompact right before a turn is sent: if context is over the threshold,
   summarize the aged span and advance the compaction boundary so the outgoing
   request stays bounded. Pre-send (not reactive) so a chat already at the limit
   can still continue — a reactive check only fires AFTER a turn, too late to save
   the turn that overflows.

   The lock is PER-CONVERSATION (a Set of convIds), not a single global flag:
   several conversations can be generating in the background at once, and each
   must be free to compact when IT crosses the threshold regardless of which one
   is on screen. Focus/active-ness affects only what the UI renders, never whether
   a conversation compacts. */
const _compacting = new Set();
function _cmpTextOf(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(p => (p && p.type === 'text') ? (p.text || '') : '').join(' ');
  return '';
}
function _cmpTranscript(msgs, fromIdx, uptoIdx) {
  const out = [];
  for (let i = fromIdx; i < uptoIdx; i++) {
    const m = msgs[i];
    if (!m || (m.role !== 'user' && m.role !== 'assistant')) continue;
    const t = _cmpTextOf(m.content).trim();
    if (t) out.push((m.role === 'user' ? 'USER: ' : 'ASSISTANT: ') + t);
  }
  let s = out.join('\n\n');
  const CAP = 12000;
  if (s.length > CAP) s = '…[earlier turns truncated]\n\n' + s.slice(s.length - CAP);
  return s;
}
// Current context usage as a % of the active provider's window, or null when the
// window is unknown or nothing has been reported. Reported provider usage only
// (SandpieTokens.contextPct) — no client-side estimate — and per conversation, so
// a BACKGROUND conversation is measured against its own reported size.
async function _cmpContextPct(convId) {
  if (typeof SandpieTokens === 'undefined' || !SandpieTokens.contextPct) return null;
  try { return await SandpieTokens.contextPct(convId); } catch { return null; }
}
// Summarize the span between the current boundary and the protected tail and
// advance the compaction boundary — regardless of the % threshold. Shared by
// the pre-send auto path (gated on %) and the manual `>>> compact` command
// (no gate). Building on any prior summary so old context isn't lost when only
// newly-aged turns are re-summarized. Returns {ok, reason?, removed?, kept?}.
async function _performCompaction(convId, cfg, triggerReason = 'native compaction') {
  const res = await _resolveConvForCompaction(convId);
  if (!res) return { ok: false, reason: 'conversation not found' };
  const msgs = res.msgs;
  const to = safeSplitIndex(msgs, cfg.keepTail);
  const comp = res.compaction;
  const from = (comp && comp.boundary) || 0;
  if (to <= from) return { ok: false, reason: 'nothing new to compact' };
  let transcript = _cmpTranscript(msgs, from, to);
  if (comp && comp.summary) transcript = '[Summary of the conversation so far]\n' + comp.summary + '\n\n[New turns to fold into the summary]\n' + transcript;
  if (!transcript.trim()) return { ok: false, reason: 'nothing to summarize' };
  const emit = (type) => { try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit(type, { convId }); } catch (_) {} };
  // Native/pre-send, resume, and manual compactions do not pass through the
  // worker's mid-turn logger. Log here instead: this is the common engine for
  // every page-side compaction trigger, including the first send after resume.
  const cmpLog = async (event, extra = {}) => {
    try {
      const provider = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve) ? SandpieProviders.resolve(convId) : null;
      const sid = (typeof ensureSessionId === 'function') ? await ensureSessionId(convId) : null;
      const title = (typeof convTitle === 'function') ? await convTitle(convId) : null;
      console.log('[compaction] ' + event + ' ' + JSON.stringify({
        src: 'page-native', conv: convId, session_id: sid, title: title || null,
        reason: triggerReason, provider: provider ? (provider.model || provider.name || provider.id || null) : null,
        context_pct: await _cmpContextPct(convId), ...extra,
      }));
    } catch (_) {}
  };
  _compacting.add(convId);
  // Abortable summarizer fetch: registered in _pageAbortPool so a Stop click
  // kills this pre-send request too (it runs before the turn has an agent id,
  // so a worker abort can't reach it).
  const _cmpAbort = new AbortController();
  _pageAbortPool.add(_cmpAbort);
  await cmpLog('trigger', { from_boundary: from, to_boundary: to, transcript_chars: transcript.length });
  emit('compaction:start');
  try {
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) {
      await cmpLog('failed', { error: 'no completion provider available' });
      return { ok: false, reason: 'no completion provider available' };
    }
    const out = await SandpieProviders.complete({ system: cfg.prompt, user: transcript, model: cfg.model || undefined, signal: _cmpAbort.signal });
    if (!out || !out.trim()) {
      await cmpLog('failed', { error: 'summarizer returned empty' });
      return { ok: false, reason: 'summarizer returned empty' };
    }
    const r = await compactConversation(convId, { keepTail: cfg.keepTail, summary: out });
    if (r && r.ok) {
      await cmpLog('done', { removed: r.removed, kept: r.kept });
      return { ok: true, removed: r.removed, kept: r.kept };
    }
    const reason = (r && r.reason) || 'compaction failed';
    await cmpLog('failed', { error: reason });
    return { ok: false, reason };
  } catch (e) {
    const reason = (e && e.message) || String(e);
    await cmpLog('failed', { error: reason, status: (e && e.status) || null });
    return { ok: false, reason };
  } finally {
    _pageAbortPool.delete(_cmpAbort);
    emit('compaction:end');
    _compacting.delete(convId);
  }
}
// Returns { triggered, ok, reason? }. triggered=false means the threshold was not
// met (no compaction attempted). triggered=true + ok=false means it WAS needed but
// failed — the caller must not ship the over-limit turn. NOTE: no active-conv gate
// — any conversation compacts when it crosses the threshold, foreground or not.
async function maybeAutoCompact(convId) {
  if (!convId || _compacting.has(convId)) return { triggered: false, ok: true };
  if (typeof SandpieCompactor === 'undefined') return { triggered: false, ok: true };
  const cfg = SandpieCompactor.config();
  if (!cfg.enabled) return { triggered: false, ok: true };
  // Reported pct: the last turn's provider-measured prompt_tokens ÷ window.
  // The ONLY gate — no client-side estimate.
  let pct = null;
  try { pct = await _cmpContextPct(convId); } catch {}
  if (pct == null || pct < cfg.pct) return { triggered: false, ok: true };
  try {
    const r = await _performCompaction(convId, cfg, 'threshold: pre-send context usage');
    // "nothing new to compact" means the aged span is already summarized — the
    // threshold is met but there's nothing left to do, so don't block the send.
    if (r && !r.ok && r.reason && /nothing (new to compact|to summarize)/.test(r.reason)) return { triggered: false, ok: true };
    return { triggered: true, ok: !!(r && r.ok), reason: r && r.reason };
  } catch (e) {
    console.warn('[sandpie] auto-compaction failed:', e);
    return { triggered: true, ok: false, reason: (e && e.message) || String(e) };
  }
}
/* ---- automatic conversation titles -------------------------------------- */
// A conversation's stored title starts life as _deriveTitle() — the first user
// message clipped to 60 chars — which reads as a truncated sentence in the
// sidebar. Once an opening exchange exists, ask the model for a real one
// (auto-title.js owns the prompt, the budget and the call) and lock it in.
//
// Eligibility is a property of the STORED TITLE, not of the turn number: a title
// is replaceable while it is still the derived placeholder and nothing has locked
// it. So a failed attempt (offline, empty answer) simply retries on the next turn,
// and a conversation that predates this feature gets named the next time it's
// used — while a hand-typed title (renameConv sets titleLocked, and saveConv
// carries it forward) is never touched. force:true ignores all of that, for
// `>>> retitle`.
const _titling = new Set();
// Conversations whose next rendered row should play the retitle animation. Held
// only across the one refreshConversationList() that follows the meta write.
const _titleAnim = new Set();
async function maybeAutoTitle(convId, { force = false } = {}) {
  if (!convId || _titling.has(convId)) return '';
  if (typeof SandpieAutoTitle === 'undefined' || !SandpieAutoTitle.generate) return '';
  if (!force && !SandpieAutoTitle.isEnabled()) return '';
  _titling.add(convId);
  // Abortable title fetch: registered in _pageAbortPool so a Stop click kills
  // this pre-send request too (no agent id exists yet at this point).
  const _titleAbort = new AbortController();
  _pageAbortPool.add(_titleAbort);
  try {
    // Warm stream or cold conv on disk — same resolver the compactor uses.
    const res = await _resolveConvForCompaction(convId);
    const msgs = (res && res.msgs) || [];
    const firstUser = msgs.find(m => m.role === 'user' && _convText(m.content).trim());
    if (!firstUser) return '';               // nothing to name it after
    const meta = await readConvMeta(convId);
    if (!meta) return '';                    // not persisted yet — nothing to patch
    const stored = meta.title || '';
    if (!force) {
      if (meta.titleLocked) return '';
      // A title that isn't the derived placeholder was set deliberately — by a
      // rename made before titleLocked existed, or by a previous auto-title.
      if (stored && stored !== _deriveTitle(msgs)) return '';
    }
    const firstAsst = msgs.find(m => m.role === 'assistant' && _convText(m.content).trim());
    const title = await SandpieAutoTitle.generate({
      userText: _convText(firstUser.content),
      assistantText: firstAsst ? _convText(firstAsst.content) : '',
      sessionId: 'Retitle:' + (await ensureSessionId(convId)),   // parent-session marker for /admin/transcripts
      signal: _titleAbort.signal,
    });
    if (!title || title === stored) return '';
    await updateConvFile(convId, { title, titleLocked: true });
    // Flag the row for its landing animation BEFORE the refresh: the refresh
    // rebuilds every <li> from scratch, so buildConvLi is the only place that can
    // animate the row that will actually be on screen.
    _titleAnim.add(convId);
    await refreshConversationList();
    _titleAnim.delete(convId);   // consumed by buildConvLi; never animate twice
    return title;
  } catch (e) {
    // Best-effort: the conversation keeps its derived title and stays eligible.
    console.warn('[sandpie] auto-title failed:', e);
    return '';
  } finally {
    _pageAbortPool.delete(_titleAbort);
    _titling.delete(convId);
  }
}
/* ---- command registration: retitle -------------------------------------- */
function registerRetitleCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'retitle',
    module: 'core',
    help: 'Regenerate a conversation title from its opening exchange, ignoring the usual "only if untouched" rule (and even when auto-titling is off). Defaults to the active conversation; pass a conversation file name/id/title to retitle another.',
    usage: '>>> retitle [conversation]',
    async run(text, parts) {
      if (typeof SandpieAutoTitle === 'undefined') return 'Auto-titling is not available.';
      let targetId = null;
      for (const p of parts.slice(1)) {
        if (targetId != null) continue;
        const rid = await _resolveConvArg(p);
        if (!rid) return `No conversation matched "${p}". Pass the file name, id, or exact title.`;
        targetId = rid;
      }
      const convId = targetId || activeConvId;
      if (!convId) return 'No active conversation to retitle — pass a conversation file name.';
      if (_titling.has(convId)) return 'A title is already being generated for that conversation — try again in a moment.';
      const before = await convTitle(convId);
      const title = await maybeAutoTitle(convId, { force: true });
      if (!title) return 'Could not generate a title — the model returned nothing usable (the current title is unchanged).';
      return `Retitled: "${before}" → "${title}"`;
    }
  });
}
registerRetitleCommand();

/* ---- command registration: compact ------------------------------------- */
// Manually force a compaction NOW, at any context %, ignoring the auto trigger
// (and even when auto-compaction is disabled). Optional arg overrides keepTail.

function registerInspectPromptCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'inspect-prompt',
    module: 'core',
    help: 'Show the complete system prompt that will be sent to the model for the next turn',
    usage: '>>> inspect-prompt',
    async run(text, parts) {
      if (activeConvId) await _loadLiteFlag(activeConvId).catch(() => {});
      const prompt = await buildSystemPrompt(messages);
      const lite = activeConvId && _liteOn(activeConvId);
      return '=== System prompt ' + (lite ? '(FAST MODE ON - minimal)' : '') + ' ===\n\n' + prompt.content;
    },
  });
}
registerInspectPromptCommand();


// Resolve a `>>> compact` argument to a conversation id. Accepts the raw id, the
// file name (`<id>.json`), or a case-insensitive exact/prefix title match. Returns
// the id if a conversation file exists, else null.
async function _resolveConvArg(arg) {
  if (!arg) return null;
  let id = String(arg).trim();
  if (id.toLowerCase().endsWith('.json')) id = id.slice(0, -5);
  // Direct id / filename hit.
  try { if (await opfs.exists(convPath(id, false)) || await opfs.exists(convPath(id, true))) return id; } catch {}
  // Fall back to matching a title.
  let convs = [];
  try { convs = await listConversations(); } catch {}
  const needle = String(arg).trim().toLowerCase();
  const exact = convs.find(c => (c.title || '').toLowerCase() === needle);
  if (exact) return exact.id;
  const pre = convs.filter(c => (c.title || '').toLowerCase().startsWith(needle));
  if (pre.length === 1) return pre[0].id;
  return null;
}
function registerCompactCommand() {
  if (typeof SandpieCommands === 'undefined') return;
  SandpieCommands.register({
    name: 'compact',
    module: 'core',
    help: 'Compact a conversation now, at any %, ignoring the auto threshold. Defaults to the active conversation; pass a conversation file name/id/title to compact another.',
    usage: '>>> compact [conversation] [keepTail]',
    async run(text, parts) {
      if (typeof SandpieCompactor === 'undefined') return 'Compaction is not available.';

      // Parse args: an optional conversation name/id and an optional numeric
      // keepTail, in either order. A bare number is keepTail for the active conv.
      const cfg = SandpieCompactor.config();
      let targetId = null;
      const rest = parts.slice(1);
      for (const p of rest) {
        const n = parseInt(p, 10);
        if (String(n) === p && n >= 2) { cfg.keepTail = n; continue; }
        if (Number.isFinite(n) && String(n) === p) return 'keepTail must be ≥ 2 (messages to keep verbatim).';
        if (targetId == null) {
          const rid = await _resolveConvArg(p);
          if (!rid) return `No conversation matched "${p}". Pass the file name, id, or exact title.`;
          targetId = rid;
        }
      }
      const convId = targetId || activeConvId;
      if (!convId) return 'No active conversation to compact — pass a conversation file name.';
      if (_compacting.has(convId)) return 'A compaction is already in progress for that conversation — try again in a moment.';

      let before = null; try { before = await _cmpContextPct(convId); } catch {}
      const r = await _performCompaction(convId, cfg, 'manual: compact command');
      if (!r || !r.ok) return 'Nothing compacted: ' + ((r && r.reason) || 'unknown reason') + '.';
      let after = null; try { after = await _cmpContextPct(convId); } catch {}
      const delta = (before != null && after != null) ? ` Context ${Math.round(before)}% → ${Math.round(after)}%.` : '';
      const who = convId === activeConvId ? '' : ` in ${convId}`;
      return `Compacted ${r.removed} message(s) into a summary${who}; kept the last ${r.kept} verbatim.${delta}`;
    }
  });
}
registerCompactCommand();

/* ---- side-by-side conversation panel ---- */
class SidePanel {
  constructor() {
    this.left = $('messages');
    this.right = $('messagesSide');
    this.wrap = $('messagesWrap');
    this._open = false;
    this._sideId = null;
    this._activeIsRight = false;
    this._render();
    this._wireEvents();
  }

  // isOpen is its OWN flag, never derived from _sideId. _sideId means "the
  // conversation in the non-focused pane", and null is a legitimate value for it
  // (that pane is on the home screen). Deriving isOpen from it made a single
  // click on the side pane read as "panel closed" whenever the main pane had no
  // conversation — the panel vanished and its conversation went with it.
  get isOpen() { return this._open; }
  get sideId() { return this._sideId; }
  get activeIsRight() { return this._activeIsRight; }

  activeMountTarget() { return this._activeIsRight ? this.right : this.left; }

  // Point the focus at a pane and resync every id FROM THE DOM. Both panes may
  // legitimately be empty or occupied in any combination, so the mounted hosts —
  // not a blind id swap — decide what activeConvId and _sideId become.
  focusPane(isRight) {
    const leftId = paneConvId(this.left);
    const rightId = paneConvId(this.right);
    this._activeIsRight = !!isRight;
    activeConvId = isRight ? rightId : leftId;
    this._sideId   = isRight ? leftId : rightId;
    if (activeConvId) localStorage.setItem('sandpie-active-conv', activeConvId);
    messages = (activeConvId && convStreams.get(activeConvId)?.messages) || [];
    this._render();
    refreshSendButtonForActive();
    refreshConversationList();
    if (typeof SandpieTokens !== 'undefined') SandpieTokens.notify();
  }

  async open(id) {
    if (!id) return;
    if (id === activeConvId) return;
    if (id === this._sideId) return;
    if (this._activeIsRight) return;

    closeArtifactPanel();

    if (this._sideId) {
      const prev = convStreams.get(this._sideId);
      if (prev?.host?.parentNode) { _evacuateHome(prev.host); prev.host.parentNode.removeChild(prev.host); }
    }
    await this._lazyLoad(id);
    this._open = true;
    this._sideId = id;
    const s = convStreams.get(id);
    if (s?.host) _mountInPane(s.host, this.right);
    // The side-pane load path (unlike the main pane's renderConversation) never
    // builds the settled msg-timer — _lazyLoad renders messages but has no
    // renderConversation to trigger rebuildSettledTimer. Do it here, AFTER the
    // host is mounted into #messagesSide, so the slot lookup resolves the SIDE
    // slot; the main-pane code path already covers its own.
    if (s) rebuildSettledTimer(s.host, s);
    this._render();

    requestAnimationFrame(() => { const se = paneScrollEl(this.right); if (se) se.scrollTop = se.scrollHeight; });
    refreshConversationList();
  }
  close() {
    if (!this.isOpen) return;
    // Closing with the ONLY conversation in the right pane would leave nothing on
    // screen, so move it into the main pane instead of discarding the view. This
    // is an explicit user action, so the move is expected — unlike a stray click.
    if (!paneConvId(this.left) && paneConvId(this.right) && this.promoteSideToActive()) return;
    if (this._activeIsRight) this.focusPane(false);
    const s = convStreams.get(paneConvId(this.right));
    if (s?.host?.parentNode) { _evacuateHome(s.host); s.host.parentNode.removeChild(s.host); }
    _placeHome();
    this._open = false;
    this._sideId = null;
    this._activeIsRight = false;
    this._render();
    refreshConversationList();
  }
  // Move the focus to the other pane. Nothing moves in the DOM and nothing is
  // closed — both panes stay exactly as they are, which is the whole point of a
  // split view.
  flip() {
    if (!this.isOpen) return;
    this.focusPane(!this._activeIsRight);
  }

  // A conversation was deleted (its host is already detached). If the right pane
  // is now empty there is no split left to show; otherwise just resync the ids
  // against what is still mounted.
  notifyDeleted(id) {
    if (!this._open) return;
    if (id !== this._sideId && id !== activeConvId) return;
    if (!paneConvId(this.right)) {
      // Right pane is empty now — there is no split left to show.
      this._open = false;
      this._sideId = null;
      this._activeIsRight = false;
      _placeHome();
      this._render();
      // Whatever the main pane still shows becomes the active conversation:
      // activeConvId must never be left pointing at a deleted one.
      const leftId = paneConvId(this.left);
      if (leftId) {
        activeConvId = leftId;
        messages = convStreams.get(leftId)?.messages || [];
        localStorage.setItem('sandpie-active-conv', leftId);
        refreshSendButtonForActive();
      }
      return;
    }
    // The right pane survives. If the deleted conversation was the FOCUSED one,
    // leave activeConvId alone — deleteConv checks it right after this call and
    // promotes the survivor into the main pane. Clearing it here made that check
    // fail, which left the split standing with an empty main pane.
    if (id === this._sideId) this.focusPane(this._activeIsRight);
  }

  // Move the right pane's conversation into the main pane and end the split.
  // Refuses when the left pane is still occupied — two conv-hosts stacked in one
  // pane is worse than leaving the split alone.
  promoteSideToActive() {
    if (!this.isOpen) return false;
    const sId = paneConvId(this.right);
    if (!sId) return false;
    const leftId = paneConvId(this.left);
    if (leftId && leftId !== sId) return false;
    const s = convStreams.get(sId);
    if (s && s.host) {
      if (s.host.parentNode) { _evacuateHome(s.host); s.host.parentNode.removeChild(s.host); }
      _mountInPane(s.host, this.left);   // _placeHome() re-tucks the lists into it
    }
    activeConvId = sId;
    messages = (s && s.messages) || [];
    if (activeConvId) localStorage.setItem('sandpie-active-conv', activeConvId);
    this._open = false;
    this._sideId = null;
    this._activeIsRight = false;
    this._render();
    refreshSendButtonForActive();
    return true;
  }

  async _lazyLoad(id) {
    // Warm — or a load is already in flight and will render when it resolves.
    // The stream is registered SYNCHRONOUSLY below, before any await, so two
    // rapid opens (or an open racing loadConv's cold path) can never both run
    // the load: that raced and rendered every message twice into one host.
    if (convStreams.has(id)) return;
    const s = ensureStream(id);
    s._loading = true;
    try {
      const data = await readConvData(id);
      if (!data) { addMsg('err', 'Failed to load conv.'); throw new Error('conv not found: ' + id); }
      hydrateStreamFromData(s, data);
      tgReset(s.host);
      _evacuateHome(s.host);
      s.host.innerHTML = '';
      _placeHome();   // evacuation appends the home lists to the pane bottom — re-tuck them
      for (const m of s.messages) renderHistoricalMessage(m, s.host);
    } catch (e) {
      // Failed load: don't leave an empty registered stream behind — a later
      // open would see it as "warm" and show a blank conversation forever.
      if (!s.messages.length) convStreams.delete(id);
      throw e;
    } finally {
      s._loading = false;
    }
  }

  _render() {
    const b = document.body.classList;
    b.toggle('side-open',     this.isOpen);
    b.toggle('active-left',   this.isOpen && !this._activeIsRight);
    b.toggle('active-right',  this.isOpen &&  this._activeIsRight);

    if (this.isOpen) {
      b.remove('artifact-side-open');
      this.right.classList.remove('artifact-mode');
    }
  }

  // Load a conversation into the LEFT (main) pane as the active conversation.
  // Used when the user drops a convo on the left pane with the split open — the
  // right pane keeps its own convo (unless the dropped convo was docked there,
  // in which case the split closes).
  async openInLeft(id) {
    if (!id) return;
    // Dragging the convo that's currently docked in the RIGHT pane into the
    // LEFT: swap the two panes instead of closing the split — the dragged convo
    // becomes the active (left) convo and whatever the left was showing moves
    // over to the right. The split stays open. Which pane holds which conv is
    // read from the DOM: _sideId is only the right pane's conv while the focus
    // is on the left — with the focus on the right it names the LEFT pane's
    // conv, and swapping on that stacked two conv-hosts in one pane.
    if (id === paneConvId(this.right)) {
      const s = convStreams.get(id);
      const leftId = paneConvId(this.left);
      const leftS = leftId ? convStreams.get(leftId) : null;
      if (s?.host?.parentNode) { _evacuateHome(s.host); s.host.parentNode.removeChild(s.host); }
      if (leftS?.host?.parentNode) { _evacuateHome(leftS.host); leftS.host.parentNode.removeChild(leftS.host); }
      if (s?.host) _mountInPane(s.host, this.left);
      if (leftS?.host) _mountInPane(leftS.host, this.right);
      _placeHome();
      this._activeIsRight = false;
      activeConvId = id;
      this._sideId = leftId || null;
      if (activeConvId) localStorage.setItem('sandpie-active-conv', activeConvId);
      messages = (s && s.messages) || [];
      // Left was empty (home screen) → right is now empty too → no split left.
      this._open = !!leftId;
      this._render();
      refreshSendButtonForActive();
      refreshConversationList();
      if (typeof SandpieTokens !== 'undefined') SandpieTokens.notify();
      return;
    }
    // Normal case: mount the convo into the left (main) pane as the active
    // conversation; the right pane keeps its own convo.
    this.focusPane(false);
    await loadConv(id);
  }

  // Load a conversation into the RIGHT (side) pane — the drop counterpart of
  // open(), minus the _activeIsRight guard, so dropping on the right pane always
  // updates it regardless of which pane currently has focus. Which pane holds
  // which conv is read from the DOM (paneConvId), never from _sideId: _sideId is
  // the NON-focused pane's conv, which is only the right pane's while the focus
  // sits on the left. With the focus on the right, evicting _sideId's host
  // removed the LEFT pane's conv and then stacked a second host on top of the
  // right pane's real one — the two-conv-host-in-one-pane bug.
  async openInRight(id) {
    if (!id) return;
    const rightId = paneConvId(this.right);
    const leftId  = paneConvId(this.left);
    if (id === rightId) return;   // already docked here
    // Dragging the convo currently in the LEFT pane into the RIGHT: swap the
    // two panes — the dragged convo becomes the side convo and the old side
    // convo moves to the left as the active one. The split stays open.
    if (id === leftId) {
      const s = convStreams.get(id);
      const rightS = rightId ? convStreams.get(rightId) : null;
      if (s?.host?.parentNode) { _evacuateHome(s.host); s.host.parentNode.removeChild(s.host); }
      if (rightS?.host?.parentNode) { _evacuateHome(rightS.host); rightS.host.parentNode.removeChild(rightS.host); }
      if (rightS?.host) _mountInPane(rightS.host, this.left);
      if (s?.host) _mountInPane(s.host, this.right);
      _placeHome();
      this._activeIsRight = false;
      activeConvId = rightId || null;
      this._sideId = id;
      if (activeConvId) localStorage.setItem('sandpie-active-conv', activeConvId);
      else localStorage.removeItem('sandpie-active-conv');
      messages = (activeConvId && convStreams.get(activeConvId)?.messages) || [];
      // The right pane always ends up holding the dragged convo → the split
      // stays open.
      this._open = true;
      this._render();
      refreshSendButtonForActive();
      refreshConversationList();
      if (typeof SandpieTokens !== 'undefined') SandpieTokens.notify();
      return;
    }
    closeArtifactPanel();
    // Normal case: evict whatever is ACTUALLY mounted in the right pane (the
    // DOM is the source of truth), then mount the dropped convo there.
    if (rightId) {
      const prev = convStreams.get(rightId);
      if (prev?.host?.parentNode) { _evacuateHome(prev.host); prev.host.parentNode.removeChild(prev.host); }
    }
    await this._lazyLoad(id);
    this._open = true;
    const s = convStreams.get(id);
    if (s?.host) _mountInPane(s.host, this.right);
    // Same as open(): rebuild the settled timer into the side slot after mount.
    if (s) rebuildSettledTimer(s.host, s);
    this._render();
    requestAnimationFrame(() => { const se = paneScrollEl(this.right); if (se) se.scrollTop = se.scrollHeight; });
    refreshConversationList();
  }

  _wireEvents() {
    if (!this.wrap || !this.left || !this.right) return;

    // Interacting with a pane focuses it. Clicking its composer — or tabbing into
    // its textarea — is the STRONGEST "I want to work here" signal there is, so
    // those must not be excluded: doing that left the pane you were typing in
    // still dimmed. Only a floating context menu (which overlays a pane it does
    // not belong to) and an in-progress text selection are exempt.
    const focusFromEvent = (targetIsRight) => (ev) => {
      if (!this.isOpen) return;
      if (targetIsRight === this._activeIsRight) return;
      if (ev.target.closest && ev.target.closest('.context-menu')) return;
      if (ev.type === 'click') {
        const sel = window.getSelection?.().toString();
        if (sel && sel.length > 0) return;   // dragging a selection, not switching panes
      }
      this.focusPane(targetIsRight);
    };
    for (const [pane, isRight] of [[this.left, false], [this.right, true]]) {
      pane.addEventListener('click', focusFromEvent(isRight));
      // focusin covers keyboard Tab and programmatic focus, and fires before the
      // click on a mousedown-focus, so the pane is never left dimmed while its
      // textarea holds the caret.
      pane.addEventListener('focusin', focusFromEvent(isRight));
    }
    this.wrap.addEventListener('dragover', (ev) => {
      if (!ev.dataTransfer?.types.includes('text/sandpie-conv-id')) return;
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'copy';
      this.wrap.classList.add('drop-target');
    });
    this.wrap.addEventListener('dragleave', (ev) => {
      // Clear only when the pointer truly leaves the wrap (moving over a child
      // of the wrap fires dragleave on the wrap too, but relatedTarget is still
      // inside it — must keep the dashed line up).
      if (!this.wrap.contains(ev.relatedTarget)) this.wrap.classList.remove('drop-target');
    });
    this.wrap.addEventListener('drop', (ev) => {
      this.wrap.classList.remove('drop-target');
      if (isMobileViewport()) return;
      const id = ev.dataTransfer?.getData('text/sandpie-conv-id');
      if (!id) return;
      ev.preventDefault();
      const t = ev.target;
      const inSide = !!(t && t.closest && t.closest('#messagesSide'));
      const inMain = !!(t && t.closest && t.closest('#messages'));
      if (!this.isOpen) {
        // Single panel — create the side panel (drop lands in the right pane).
        this.open(id);
      } else if (inSide) {
        // Split open + dropped on the right pane → update the right pane.
        this.openInRight(id);
      } else {
        // Split open + dropped on the left pane (or the wrap itself) → update
        // the left pane.
        this.openInLeft(id);
      }
    });
  }
}
/* ---- per-pane titlebar (conversation title + ✕, top-right of each pane) ---- */
// The bar inherits the fv-header/artifact-header look (sandpie.css .pane-titlebar);
// it renders only while a conversation is mounted in the pane, is hidden on
// mobile, and is suppressed in artifact/viewer modes by the same `> *:not(...)`
// rules that hide everything else in those modes.
const _paneBars = { messages: null, messagesSide: null };
function _paneBarEl(pane) {
  if (!pane) return null;
  const key = pane.id === 'messagesSide' ? 'messagesSide' : 'messages';
  if (!_paneBars[key] || !_paneBars[key].isConnected) {
    _paneBars[key] = pane.querySelector(':scope > .pane-titlebar');
  }
  return _paneBars[key];
}
// Stored title first; fall back to the derived placeholder while the very first
// save is still pending (a fresh conversation has no meta file yet).
async function _paneTitleFor(id) {
  const stored = await convTitle(id);
  if (stored) return stored;
  const s = convStreams.get(id);
  if (s && s.messages && s.messages.length) return _deriveTitle(s.messages);
  return '';
}
async function refreshPaneBar(pane) {
  const bar = _paneBarEl(pane);
  if (!bar) return;
  const t = bar.querySelector('.pt-title');
  if (!t) return;
  const id = paneConvId(pane);
  bar._req = (bar._req || 0) + 1;
  const req = bar._req;
  if (!id) { bar.style.display = 'flex'; t.textContent = 'New chat'; t.classList.add('fresh'); return; }   // bar always shows on desktop; empty pane = new chat
  bar.style.display = 'flex';
  const title = (await _paneTitleFor(id)) || '';
  if (req !== bar._req) return;                       // a newer refresh won the race
  t.textContent = title || 'New chat';
  t.classList.toggle('fresh', !title);
  const x = bar.querySelector('.artifact-icon-btn');
  if (x) x.title = pane.id === 'messagesSide'
    ? 'Close side panel'
    : (sidePanel && sidePanel.isOpen ? 'Close left panel' : 'Start a new chat');
}
function _refreshPaneBarsFor(convId) {
  for (const pane of [$('messages'), $('messagesSide')]) {
    if (pane && paneConvId(pane) === convId) refreshPaneBar(pane);
  }
}
function refreshPaneBars() {
  refreshPaneBar($('messages'));
  refreshPaneBar($('messagesSide'));
}
// ✕ behavior: right pane closes the side panel; left pane closes the LEFT pane
// (its conversation is parked, the right pane's is promoted to the main pane);
// with a single pane open, ✕ behaves exactly like "+ New chat".
function paneBarClose(pane) {
  if (!pane) return;
  if (pane.id === 'messagesSide') {
    if (sidePanel && sidePanel.isOpen) sidePanel.close();
    else if (typeof closeArtifactPanel === 'function') closeArtifactPanel();
    return;
  }
  if (sidePanel && sidePanel.isOpen) {
    parkPaneConv($('messages'));
    sidePanel.close();
  } else {
    newConversation();
  }
}
// Delegated ✕ clicks on either pane's titlebar.
document.addEventListener('click', (e) => {
  const btn = e.target && e.target.closest ? e.target.closest('.pane-titlebar .artifact-icon-btn') : null;
  if (!btn) return;
  const bar = btn.closest('.pane-titlebar');
  const pane = bar && bar.parentNode;
  if (!pane) return;
  e.preventDefault();
  e.stopPropagation();
  paneBarClose(pane);
});
let sidePanel = null;

/* =============================================================================
   Module boot — runs at deferred-module eval time (after the document is parsed
   but before DOMContentLoaded), so every #id these touch already exists.
   ============================================================================= */

(function setupInput() {
  function wireComposer(which) {
    const ta = which === 'side' ? $('inputSide') : $('input');
    const pane = which === 'side' ? $('messagesSide') : $('messages');
    if (!ta || !pane) return;
    let lastTabMatches = null;
    function autosize() {
      ta.style.height = 'auto';
      const maxH = 12 * parseFloat(getComputedStyle(ta).lineHeight || '1.4');
      const newH = Math.min(ta.scrollHeight, maxH);
      ta.style.height = newH + 'px';
      ta.style.overflowY = ta.scrollHeight > maxH ? 'auto' : 'hidden';
      if (shouldAutoScroll(pane)) { const se = paneScrollEl(pane); if (se) se.scrollTop = se.scrollHeight; }
    }
    ta.addEventListener('input', () => {
      autosize();
      if (lastTabMatches && !ta.value.startsWith('>>>')) {
        lastTabMatches = null;
        if (SandpieCommandView) SandpieCommandView.hide();
      }
    });
    // ---- Tab completion for >>> commands ----
    ta.addEventListener('keydown', e => {
      if (e.key === 'Tab' && ta.value.startsWith('>>>')) {
        e.preventDefault();
        if (typeof SandpieCommands === 'undefined' || !SandpieCommands.complete) return;
        const result = SandpieCommands.complete(ta.value);
        if (!result) {
          lastTabMatches = null;
          if (SandpieCommandView) SandpieCommandView.hide();
          return;
        }
        const typed = ta.value.slice(3).trim();
        if (result.prefix !== typed) {
          ta.value = '>>> ' + result.prefix;
          ta.selectionStart = ta.selectionEnd = ta.value.length;
        }
        if (result.single) {
          ta.value = '>>> ' + result.matches[0] + ' ';
          ta.selectionStart = ta.selectionEnd = ta.value.length;
          if (SandpieCommandView) SandpieCommandView.hide();
          lastTabMatches = null;
        } else {
          const list = result.matches.map(m => '  >>> ' + m).join('\n');
          // Completions belong to the pane being typed in, same as command output.
          _commandPanelTo(pane);
          if (SandpieCommandView) SandpieCommandView.show(list, 'commands');
          lastTabMatches = result.matches;
        }
        return;
      }
      if (e.key !== 'Enter' || e.isComposing) return;
      // Alt+Enter → newline, same as Shift+Enter. Browsers insert a newline for
      // Shift+Enter natively but NOT for Alt+Enter, so do it explicitly here.
      if (e.altKey) {
        e.preventDefault();
        ta.setRangeText('\n', ta.selectionStart, ta.selectionEnd, 'end');
        ta.dispatchEvent(new Event('input', { bubbles: true }));   // fire autosize
        return;
      }
      // Plain Enter submits; Shift+Enter falls through to the native newline.
      if (!e.shiftKey) {
        e.preventDefault();
        window.handleSubmit(which);
      }
    });

    const observer = new MutationObserver(autosize);
    observer.observe(ta, { attributes: true, attributeFilter: ['value'] });
    ta.form?.addEventListener('submit', () => setTimeout(autosize, 0));
    autosize();
  }
  wireComposer('main');
  wireComposer('side');

  const searchInput = $('convSearch');
  if (searchInput) {
    // Debounced: each keystroke with a query triggers a Dropbox content search
    // over the archive — coalesce to one request per 350ms pause.
    let _searchTimer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(() => refreshConversationList(), 350);
    });
  }
})();

// Scroll lock/unlock tracking follows the SCROLL CONTAINER — now the pane's
// .conv-host (or the pane itself when nothing is mounted, e.g. the home screen).
function setupScrollTracking(el) {
  if (!el) return;
  lockScroll(el);
  el.addEventListener('scroll', () => { if (isAtBottom(el)) lockScroll(el); }, { passive: true });
  el.addEventListener('wheel', e => { if (e.deltaY < 0) unlockScroll(el); }, { passive: true });
  let _ty = 0;
  el.addEventListener('touchstart', e => { _ty = e.touches[0].clientY; }, { passive: true });
  el.addEventListener('touchmove', e => { if (e.touches[0].clientY > _ty) unlockScroll(el); }, { passive: true });
}
// Attach tracking to a pane's scroll element AND to its homeCenter (home lists
// scroll themselves now that the pane doesn't).
function trackPaneScroll(pane) {
  const sc = paneScrollEl(pane);
  if (sc) setupScrollTracking(sc);
  const home = pane && pane.querySelector('#homeCenter');
  if (home && home !== sc) setupScrollTracking(home);
}
trackPaneScroll($('messages'));
trackPaneScroll($('messagesSide'));



sidePanel = new SidePanel();
window.sidePanel = sidePanel;

(function () {
  const resizer = $('sideResizer');
  const panel   = $('messagesSide');
  if (!resizer || !panel) return;
  // Pointer events + setPointerCapture: a plain mousedown/mousemove/mouseup
  // drag BREAKS when an artifact is open in the sidepanel — the artifact iframe
  // (file-viewer's .fv-panel > iframe, not the legacy #artifactPanelFrame)
  // swallows mouse events, so the parent's mouseup never fires and the resize
  // stays stuck in the 'dragging' state. setPointerCapture retargets EVERY
  // pointer event (move/up/cancel) to the resizer for the whole gesture, even
  // over an iframe or outside the window — the drag always ends cleanly.
  resizer.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;   // left button only
    e.preventDefault();
    const startX = e.clientX;
    const startW = panel.offsetWidth;
    panel.style.flex  = 'none';
    panel.style.width = startW + 'px';
    resizer.classList.add('dragging');
    document.body.style.cursor     = 'col-resize';
    document.body.style.userSelect = 'none';

    // Belt & suspenders: knock pointer events off every sidepanel iframe while
    // dragging (capture is the real fix; this covers older engines).
    const sideIframes = document.querySelectorAll('#messagesSide iframe');
    sideIframes.forEach(f => f.style.pointerEvents = 'none');
    try { resizer.setPointerCapture(e.pointerId); } catch (_) {}

    function onMove(ev) {
      const wrap = $('messagesWrap');
      const minW = 200;
      const maxW = (wrap ? wrap.offsetWidth : window.innerWidth) - 300;
      const newW = Math.max(minW, Math.min(startW + (startX - ev.clientX), maxW));
      panel.style.width = newW + 'px';
    }
    function onUp() {
      resizer.classList.remove('dragging');
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';
      document.querySelectorAll('#messagesSide iframe').forEach(f => f.style.pointerEvents = '');
      try { resizer.releasePointerCapture(e.pointerId); } catch (_) {}
      resizer.removeEventListener('pointermove', onMove);
      resizer.removeEventListener('pointerup',   onUp);
      resizer.removeEventListener('pointercancel', onUp);
    }
    resizer.addEventListener('pointermove', onMove);
    resizer.addEventListener('pointerup',   onUp);
    resizer.addEventListener('pointercancel', onUp);
  });
})();



/* expose moved page-glue for inline handlers (HTML onclick) + the host contract */
window.anyStreamGenerating = anyStreamGenerating;

/* expose on window for inline script compatibility */
window.ensureStream = ensureStream;
window.activeStream = activeStream;
/* ---------------------------------------------------------------------------
   Inject a synthetic user message (used for file upload notifications).
   --------------------------------------------------------------------------- */
function injectUploadMessage(text) {
  const s = activeStream();
  if (!s) return;
  const msg = { role: 'user', content: text };
  s.messages.push(msg);
  bindBubble(addMsg('user', text, s.host), msg);
  saveConv(s.id).catch(() => {});
}
window.injectUploadMessage = injectUploadMessage;
window.addMsg = addMsg;
// Pane-render helpers other modules need (artifacts, pins): a bare appendChild on
// a pane lands BELOW its sticky composer, so they must resolve/insert through these.
window.paneScrollEl = paneScrollEl;
window.appendContent = appendContent;
// The one progress pill in the app (compaction spinner), for host-level ops.
window.showAppProgress = showAppProgress;
window.hideAppProgress = hideAppProgress;
window.bindBubble = bindBubble;
window.tcEscape = tcEscape;
window.appendToolResult = appendToolResult;
window.appendToolResultImage = appendToolResultImage;
window.buildToolBox = buildToolBox;
window.renderTcPreparing = renderTcPreparing;
window.renderTcRunning = renderTcRunning;
window.renderTcDone = renderTcDone;

/* ---- expose to window for inline handlers / legacy code ---- */
window.newConvId = newConvId;
window.convPath = convPath;
window.ensureActiveConv = ensureActiveConv;
window.saveActiveConv = saveActiveConv;
window.saveConv = saveConv;
// getTitle/autoTitle are read/write access to a conversation's name for modules
// that only need that (notifications.js reads it for the toast body).
// PER-CONVERSATION provider bridge — providers.js reads/sets the model through
// this (the composer model picker is per conversation; there is no global model).
// convId null means "the conversation the caller is focused on" (activeConvId).
window.SandpieConv = {
  getProviderId(convId) {
    const id = convId || activeConvId;
    if (!id) return null;
    const s = convStreams.get(id);
    return (s && s.providerId) || null;
  },
  setProviderId(convId, providerId) {
    const id = convId || activeConvId;
    if (!id) {
      // No conversation yet (home screen / brand-new chat): remember the choice
      // as the app default — resolveProvider reads it so THIS picker updates
      // immediately, and the conversation the next message creates uses it.
      try { if (providerId) localStorage.setItem('sandpie-default-provider', providerId); } catch (_) {}
      return;
    }
    const s = ensureStream(id);
    s.providerId = providerId || null;
    // Stale-save guard: mark this tab's explicit pick so the next _saveConv gives
    // it precedence over a concurrent meta.json change written by another
    // tab/browser (see the PER-CONVERSATION provider merge in _saveConv).
    s._provDirty = true;
    saveConv(id, { touchUpdated: false }).catch(() => {});
  },
  // PER-CONVERSATION project bridge — the timer-row chip reads/sets the project
  // through this. Same contract as the provider bridge: convId null → home-state
  // default in localStorage (sandpie-default-project).
  getProjectId(convId) {
    const id = convId || activeConvId;
    if (!id) return null;
    const s = convStreams.get(id);
    return (s && s.projectId) || null;
  },
  setProjectId(convId, projectId) {
    _setProjBinding(convId, projectId);
    const slot = _timerSlotFor({ id: convId || activeConvId, host: document.getElementById('messages') });
    if (slot) _paintProjChip(slot, convId || activeConvId);
  },
  // PER-CONVERSATION reasoning effort bridge — providers.js reads/sets the level
  // through this (slider inside the composer model picker). Same contract as the
  // provider bridge: convId null → home-state default in localStorage.
  getReasoningLevel(convId) {
    const id = convId || activeConvId;
    if (!id) return null;
    const s = convStreams.get(id);
    return (s && s.reasoningLevel) || null;
  },
  setReasoningLevel(convId, level) {
    const LV = ['off', 'low', 'medium', 'high'];
    if (!LV.includes(level)) level = null;
    const id = convId || activeConvId;
    if (!id) {
      // No conversation yet (home screen / brand-new chat): remember the choice
      // as the app default — the picker reads it so THIS slider updates
      // immediately, and the conversation the next message creates uses it.
      try {
        if (level) localStorage.setItem('sandpie-default-reasoning', level);
        else localStorage.removeItem('sandpie-default-reasoning');
      } catch (_) {}
      return;
    }
    const s = ensureStream(id);
    s.reasoningLevel = level;
    // Stale-save guard: same pattern as _provDirty (see _saveConv merge).
    s._rsnDirty = true;
    saveConv(id, { touchUpdated: false }).catch(() => {});
  },
};

window.SandpieConversations = { compact: compactConversation, getCompaction, safeSplitIndex, maybeAutoCompact, getTitle: convTitle, autoTitle: maybeAutoTitle };
window.renderHistoricalMessage = renderHistoricalMessage;
window.clearActiveConvUI = clearActiveConvUI;
window.parkActiveConv = parkActiveConv;
window.lockScroll = lockScroll;
window.mountConv = mountConv;
window.loadConv = loadConv;
window.newConversation = newConversation;
window.listConversations = listConversations;
window.updateConvFile = updateConvFile;
window.renameConv = renameConv;
window.togglePinConv = togglePinConv;
window.toggleArchiveConv = toggleArchiveConv;
window.duplicateConv = duplicateConv;
window.deleteConv = deleteConv;
window.fmtRelTime = fmtRelTime;
window.buildConvLi = buildConvLi;
window.refreshConversationList = refreshConversationList;
window.refreshSendButtonForActive = refreshSendButtonForActive;
window.setStreamSending = setStreamSending;
window.handleSubmit = handleSubmit;
window.renderFilesTouched = renderFilesTouched;   // debug/test handle (touched-files surfacing)
window.enqueueForActive = enqueueForActive;
window.handleButtonClick = handleButtonClick;
window.sendSingle = sendSingle;
window.buildAgentConfig = buildAgentConfig;
window.readAgentEvents = readAgentEvents;
window.dispatchAgentEvent = dispatchAgentEvent;

/* =============================================================================
   Total-interaction timer (covers all rounds + tool execution)
   Per-stream: each conversation's timer lives on its stream record so a
   background conv keeps ticking against its own bubble host without colliding
   with whichever conv is currently visible.
   ============================================================================= */
const TIMER_TICK_MS = 1000; // 1s: numeric readouts don't need frame-rate updates
const TOK_FMT = n => Math.round(n).toLocaleString('en-US');
const RATE_FMT = r => (r >= 10 ? String(Math.round(r)) : r.toFixed(1)) + ' tok/s';

// The ctx counter shows the conversation's REAL context size — the provider's
// last-reported prompt+completion tokens (see SandpieTokens.conversationTokens),
// never a client-side estimate. It only changes when a turn reports usage, so it
// is refreshed once when the timer is (re)built and stays put during generation
// (no live-growing estimate). Clicking it opens the per-conversation context popup.
// Repaint just the number from the latest reported usage. Called at turn start,
// at turn end, and — via the dispatch usage handler — at every ROUND boundary, so
// a multi-round tool turn climbs the counter as each round reports (not only when
// the whole turn finishes).
function _paintCtxCounter(el, convId) {
  const c = el && el.querySelector('.mt-ctx');
  if (!c) return;
  // convId == null (resting placeholder / no conversation mounted) must stay
  // "– ctx": conversationTokens(null) would fall back to the STALE
  // sandpie-active-conv id in localStorage and paint the previous session's
  // context size on the home screen (2026-09-02 boot-ctx bug).
  if (convId == null) { c.innerHTML = _CTX_RING_SVG(0); c.classList.remove('warn', 'hot'); c.title = 'Conversation context — click for details'; return; }
  Promise.resolve(
    (typeof SandpieTokens !== 'undefined' && SandpieTokens.contextPct)
      ? SandpieTokens.contextPct(convId) : null,
  ).then(pct => {
    if (!c.isConnected) return;
    const p = (pct == null || !isFinite(pct)) ? 0 : Math.max(0, Math.min(100, pct));
    c.innerHTML = _CTX_RING_SVG(p);
    c.classList.toggle('warn', p >= 75 && p < 90);
    c.classList.toggle('hot', p >= 90);
    c.title = 'Conversation context — click for details';
  }).catch(() => {});
}
// Pie-ring markup for the ctx counter: r=6, C=2*pi*6=37.699. The dash offset
// encodes the used fraction of the context window (mockup A, no % text — the
// exact count stays in the ctx popup + tooltip).
const _CTX_RING_C = 37.699;
const _CTX_RING_SVG = (pct) =>
  '<svg viewBox="0 0 16 16" aria-hidden="true">' +
  '<circle class="ctx-track" cx="8" cy="8" r="6" stroke-width="2.5" fill="none"/>' +
  '<circle class="ctx-fill" cx="8" cy="8" r="6" stroke-width="2.5" fill="none" stroke-dasharray="' + _CTX_RING_C + '" stroke-dashoffset="' + (_CTX_RING_C * (1 - pct / 100)).toFixed(2) + '"/>' +
  '</svg>';
// Live per-round tok/s: painted from the worker's `rate` event (exact
// completion_tokens over the round's decode span). Hidden until the first round
// of the turn reports; re-asserted by the tick paint so it survives the slot
// rebuilds a conversation switch triggers. Clicking it opens the turn-time
// profile popup (prefill / decode / tools / compaction split of the wall time).
function _paintRate(el, rate, convId) {
  const sep = el && el.querySelector('.mt-rate-sep');
  const c = el && el.querySelector('.mt-rate');
  if (!c) return;
  // ALWAYS visible: an unknown/zero rate renders as "0 tok/s" instead of hiding
  // the readout (the slot must keep a stable width and the indicator must never
  // pop in/out).
  const show = true;
  if (sep) sep.hidden = false;
  c.hidden = false;
  {
    c.textContent = RATE_FMT(rate && rate > 0 ? rate : 0);
    if (convId != null && !c._rateWired) {
      c._rateWired = true;
      c.style.cursor = 'pointer';
      c.title = 'Decode-only speed — click for the turn-time profile';
      c.addEventListener('click', (e) => { e.stopPropagation(); openRatePopup(convId, c); });
    }
  }
}
// Wire a SETTLED .mt-rate span (endTotalTimer / rebuildSettledTimer rebuild the
// slot HTML from scratch, so the live line's wiring is lost) to open the same
// turn-profile popup as the live readout.
function _wireRateClick(el, convId) {
  const c = el && el.querySelector('.mt-rate');
  if (!c || c._rateWired) return;
  c._rateWired = true;
  c.style.cursor = 'pointer';
  c.title = 'Decode-only speed — click for the turn-time profile';
  c.addEventListener('click', (e) => { e.stopPropagation(); openRatePopup(convId, c); });
}
function _wireCtxCounter(el, convId) {
  const c = el && el.querySelector('.mt-ctx');
  if (!c) return;
  c.style.cursor = 'pointer';
  c.title = 'Conversation context — click for details';
  c.addEventListener('click', (e) => { e.stopPropagation(); openContextPopup(convId, c); });
  _paintCtxCounter(el, convId);
}

// The msg-timer no longer lives inside the scrollable conv-host. Each PANE has
// one persistent slot above its composer (#msgTimerMain / #msgTimerSide) that
// is always present in the markup and is only ever FILLED (never created or
// removed) by conversation logic. Which slot a stream owns follows the pane
// hosting its .conv-host; unmounted/ambiguous defaults to the main pane.
function _timerSlotFor(stream) {
  let h = stream && stream.host;
  while (h && h.id !== 'messages' && h.id !== 'messagesSide') h = h.parentElement;
  const side = !!(h && h.id === 'messagesSide');
  const slot = document.getElementById(side ? 'msgTimerSide' : 'msgTimerMain');
  return slot ? slot.querySelector('.msg-timer') : null;
}
// True when the stream's conversation is CURRENTLY on screen. _mountInPane removes
// a non-viewed conv's host from the DOM, so isConnected is a reliable "is viewed"
// signal. The per-pane timer slot is shared across conversations, so the live
// timer must only ever touch it while its own conversation is the one shown —
// otherwise a backgrounded generating conv would clobber the viewed one, or write
// to detached nodes (the "· idle ·" on switch-back bug).
// STRONGER than _streamViewed: true only when this stream's host is the
// conversation ACTUALLY MOUNTED in a pane right now (pane's .conv-host === s.host).
// This is the pull-guard for every timer paint: a background generating conv can
// never paint the shared per-pane slot, even if its host is still connected
// somewhere or its stale timerEl survived a park (2026-09-13 tok/s/ctx leak).
function _streamOwnsPaneSlot(s) {
  if (!s || !s.host || !s.host.isConnected) return false;
  const pane = s.host.closest && s.host.closest('#messages, #messagesSide');
  if (!pane) return false;
  const mounted = pane.querySelector(':scope > .conv-host');
  return !!mounted && mounted === s.host;
}
function _streamViewed(s) {
  if (!s || !s.host || !s.host.isConnected) return false;
  // The host must still sit INSIDE a pane (#messages / #messagesSide). A detached
  // host would fall through _timerSlotFor's ancestor walk to the main-pane slot
  // as a default — which let a parked (unmounted) generating conv re-claim the
  // new chat's timer bar. Requiring a real pane ancestor closes that path.
  return !!(s.host.closest && s.host.closest('#messages, #messagesSide'));
}

// Live-line markup, rebuilt into the slot whenever this conversation owns it.
const _LIVE_TIMER_HTML = () =>
  _timerNnBtn() +
  '<span class="mt-sep">·</span><span class="mt-time">0s</span>' +
  '<span class="mt-sep mt-rate-sep">·</span><span class="mt-rate">0 tok/s</span>' +
  '<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>' +
  '<span class="mt-sep mt-todos-sep" hidden>·</span><span class="mt-todos"></span>';

function startTotalTimer(stream) {
  if (!stream || stream.timerEl) return;
  const el = _timerSlotFor(stream);
  if (!el) return;
  stream.timerStart = Date.now();
  stream.lastRate = null; stream._turnToks = 0; stream._turnDecodeMs = 0;   // fresh per-turn rate accumulators
  stream._turnProfile = null;   // timing payload arrives at turn end (rate popup)
  stream.timerEl = el;
  // Do NOT reset stream.todos here. It is the persistent checklist (task tree),
  // carried across turns + reloads (meta.todos → hydrate → s.todos) and seeded
  // into the worker via config.todos so write_todos OPS apply to the existing
  // tree. Nulling it (a relic of the old full-replace design) detached the
  // checklist every turn — buildAgentConfig, called right after this, would read
  // null → empty tree → the model rewrites and loses state.
  const set = (node, txt) => { if (node && node.textContent !== txt) node.textContent = txt; };

  // Ownership-aware, self-healing paint. The timer slot is ONE persistent element
  // per pane, shared across conversations, so:
  //  - only paint when THIS conversation is the one on screen (_streamViewed) —
  //    a backgrounded generating conv must not clobber the viewed one, nor write
  //    to nodes another conv has since replaced;
  //  - re-resolve the slot each tick and re-assert the live structure if a
  //    conversation switch blanked it / stamped a settled or placeholder line —
  //    this is what re-attaches the ticking timer when you return to a still-
  //    generating conversation (the "shows · idle · on switch-back" bug).
  const paint = () => {
    if (!_streamOwnsPaneSlot(stream)) return;
    const slot = _timerSlotFor(stream);
    if (!slot) return;
    stream.timerEl = slot;
    // Never steal a slot another conversation owns: only rebuild when the slot is
    // ours or unowned. mountConv blanks a stale slot before re-attaching, so the
    // switch-back path still works.
    if (slot.dataset.convId && slot.dataset.convId !== '' + (stream.id || '')) return;
    if (slot.dataset.convId !== '' + (stream.id || '') || slot.classList.contains('done') || !slot.querySelector('.mt-time')) {
      slot.classList.remove('done');
      slot.dataset.convId = '' + (stream.id || '');
      slot.innerHTML = _LIVE_TIMER_HTML();
      _wireCtxCounter(slot, stream.id);
      _paintProjChip(slot, stream.id);
    }
    // Ripple while a completion is actively streaming (respond()/plain content),
    // not only while a thought box is open. `generating` is the single source of
    // truth — true from send until the stream ends/aborts — re-asserted each tick
    // because the live line may have just been rebuilt above.
    const _snn = slot.querySelector('.mt-nn');
    if (_snn) _snn.classList.toggle('streaming', !!stream.generating);
    set(slot.querySelector('.mt-time'), fmtElapsed((Date.now() - stream.timerStart) / 1000));
    _paintRate(slot, stream.lastRate, stream.id);
    const todosEl = slot.querySelector('.mt-todos');
    if (todosEl) {
      const t = stream.todos;
      const tsep = slot.querySelector('.mt-todos-sep');
      if (tsep) tsep.hidden = !t || !t.length;
      if (!t || !t.length) { set(todosEl, ''); }
      else {
        const cur = t.filter(x => x && x.status === 'completed').length;   // completed only — match the checklist card
        set(todosEl, cur + '/' + t.length);
        if (!todosEl._mtTodosWired) {
          todosEl._mtTodosWired = true;
          todosEl.style.cursor = 'pointer';
          todosEl.title = 'Checklist — click for details';
          todosEl.addEventListener('click', (e) => {
            e.stopPropagation();
            showCmdPanelForEl(todosEl, buildTodosView((stream.todos || []).slice()), 'Checklist');
          });
        }
      }
    }
  };
  stream._tickTimer = paint;   // so a conversation switch can re-attach immediately

  paint();
  stream.timerInterval = setInterval(paint, TIMER_TICK_MS);
}

function endTotalTimer(stream, label) {
  if (!stream) return;
  // Stop the tick FIRST — BEFORE the timerEl guard below. If the live slot was
  // never painted (timerEl still null, e.g. the bar wasn't on screen when the
  // turn ended), an early return here would leave the interval running and the
  // timer would keep counting after the turn is over. Seen on Stop mid-stream:
  // the worker aborts correctly but the bar never settles.
  clearInterval(stream.timerInterval);
  stream.timerInterval = null;
  stream._tickTimer = null;
  if (!stream.timerEl) return;
  const sec = (Date.now() - stream.timerStart) / 1000;
  const u = stream.lastUsage;
  const comp = u && typeof u.completion_tokens === 'number' ? u.completion_tokens : 0;
  // Always persist the finished turn so the settled line can be rebuilt later
  // (cold load, or switching back to this conversation) — even if this turn
  // finished while another conversation was on screen.
  // Settled rate prefers the turn's accumulated decode-only tok/s (exact tokens
  // over decode spans = real model speed); falls back to completion/wall when a
  // provider never reported per-round usage.
  const rate = (stream._turnToks > 0 && stream._turnDecodeMs > 0)
    ? stream._turnToks / (stream._turnDecodeMs / 1000)
    : ((comp > 0 && sec > 0.05) ? comp / sec : 0);
  if (label !== null) stream.lastTurn = { sec, label: typeof label === 'string' ? label : 'done', completionTokens: comp, rate, profile: stream._turnProfile || null };
  // Only touch the shared per-pane slot if THIS conversation is the one on screen;
  // a backgrounded turn finishing must not overwrite the viewed conversation's bar.
  // When it isn't viewed, rebuildSettledTimer paints the settled line from lastTurn
  // the moment the user switches back.
  const slot = _streamOwnsPaneSlot(stream) ? _timerSlotFor(stream) : null;
  if (!slot) { stream.timerEl = null; return; }
  if (label === null) {
    // Turn cancelled with nothing to show → resting placeholder (never a bare slot).
    _fillPlaceholderTimer(slot, stream.id);
    stream.timerEl = null;
    return;
  }
  // Settled line: label · elapsed · [tok/s] · ctx, dimmed via .done. `rate` was
  // computed above (decode-only when available, else completion/wall fallback).

  const parts = [
    _timerNnBtn(TICK_SVG_INLINE),   // settled: tick mark replaces the ripple icon (still toggles thoughts)
    `<span class="mt-sep">·</span><span class="mt-time">${fmtElapsed(sec, true)}</span>`,
  ];
  parts.push(`<span class="mt-sep">·</span><span class="mt-rate">${RATE_FMT(rate > 0 ? rate : 0)}</span>`);   // ALWAYS present: 0 tok/s when unknown
  parts.push(`<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>`);   // ALWAYS present: the ring must never vanish on settle (matches rebuildSettledTimer)
  if (stream.todos && stream.todos.length) {
    const cur = stream.todos.filter(t => t && t.status === 'completed').length;   // completed only — match the checklist card
    parts.push(`<span class="mt-sep">·</span><span class="mt-todos">${cur}/${stream.todos.length}</span>`);
  }
  slot.innerHTML = parts.join('');
  slot.classList.add('done');
  slot.dataset.convId = '' + (stream.id || '');
  _wireCtxCounter(slot, stream.id);
  _paintProjChip(slot, stream.id);
  _wireRateClick(slot, stream.id);
  if (stream.todos && stream.todos.length) {
    const badge = slot.querySelector('.mt-todos');
    if (badge) {
      // Snapshot THIS turn's checklist so the finished badge always shows the
      // state at turn-end, immune to later turns reassigning stream.todos.
      const snapshot = stream.todos.slice();
      badge.onclick = () => {
        showCmdPanelForEl(badge, buildTodosView(snapshot), 'Checklist');
      };
    }
  }
  stream.timerEl = null;
}

// ---- report-conversation button in the idle timer bar (next to ctx) ----
// A permanent escape hatch for flagging the current conversation, because the bubble-embedded
// report action was removed (2026-09-02) — the idle-bar flag is now the ONLY report entry point.
// Same transport as the old bubble action: best-effort POST via reportConversation, never breaks the chat.
const REPORT_SVG_INLINE = '<svg viewBox="0 -960 960 960"><path d="M242-840h444v512L408-40l-39-31q-6-5-9-14t-3-22v-10l45-211H103q-24 0-42-18t-18-42v-81.84q0-7.16-1.5-14.66T43-499l126-290q8.88-21.25 29.59-36.13Q219.31-840 242-840Zm384 60H229L103-481v93h373l-53 249 203-214v-427Zm0 427v-427 427Zm60 25v-60h133v-392H686v-60h193v512H686Z"/></svg>';

// Per-conversation context popup — the breakdown that used to live in the sidebar,
// now anchored to the conversation's own ctx counter. Reported tokens only: size,
// % of the window, and headroom. Dismisses on outside click / Escape / scroll.
let _ctxPopupEl = null, _ctxPopupCleanup = null;
function _closeContextPopup() {
  if (_ctxPopupCleanup) { try { _ctxPopupCleanup(); } catch (_) {} _ctxPopupCleanup = null; }
  if (_ctxPopupEl) { _ctxPopupEl.remove(); _ctxPopupEl = null; }
}
async function openContextPopup(convId, anchorEl) {
  if (_ctxPopupEl) { _closeContextPopup(); return; }   // toggle off if already open
  const T = (typeof SandpieTokens !== 'undefined') ? SandpieTokens : null;
  let used = 0, win = null;
  if (T) { try { used = await T.conversationTokens(convId); } catch (_) {} try { win = T.contextWindow(convId); } catch (_) {} }

  const pop = document.createElement('div');
  pop.className = 'ctx-popup';
  const rows = [];
  if (!used) {
    rows.push('<div class="ctx-popup-note">No token usage reported for this conversation yet.</div>');
  } else {
    rows.push(`<div class="ctx-popup-row"><span>Context size</span><b>${TOK_FMT(used)} tokens</b></div>`);
    if (win) {
      const pct = Math.min(100, (used / win) * 100);
      rows.push(`<div class="ctx-popup-bar"><div style="width:${pct.toFixed(1)}%"></div></div>`);
      rows.push(`<div class="ctx-popup-row"><span>${pct.toFixed(pct < 10 ? 1 : 0)}% of ${TOK_FMT(win)}</span></div>`);
    } else {
      rows.push('<div class="ctx-popup-note">Context window unknown for this model.</div>');
    }
  }
  pop.innerHTML = `<div class="ctx-popup-title">Context</div>${rows.join('')}`;
  document.body.appendChild(pop);
  _ctxPopupEl = pop;

  // Position above the anchor, clamped to the viewport.
  const r = anchorEl.getBoundingClientRect();
  const pr = pop.getBoundingClientRect();
  let top = r.top - pr.height - 8;
  if (top < 8) top = r.bottom + 8;                         // flip below if no room above
  let left = Math.min(Math.max(8, r.left), window.innerWidth - pr.width - 8);
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';

  const onDocClick = (e) => { if (_ctxPopupEl && !_ctxPopupEl.contains(e.target) && e.target !== anchorEl) _closeContextPopup(); };
  const onKey = (e) => { if (e.key === 'Escape') _closeContextPopup(); };
  setTimeout(() => document.addEventListener('mousedown', onDocClick), 0);
  document.addEventListener('keydown', onKey);
  window.addEventListener('scroll', _closeContextPopup, { capture: true, once: true });
  _ctxPopupCleanup = () => { document.removeEventListener('mousedown', onDocClick); document.removeEventListener('keydown', onKey); };
}

// Turn-time profile popup — where the turn's wall time went, from the worker's
// `timing` event (the same payload the admin panel consumes): prefill (queue +
// connect + prompt processing) vs decode (token generation) vs tool execution
// vs mid-turn compaction, plus the residual (steer waits, suspension, gaps).
// Anchored to the clicked tok/s readout; shares the ctx-popup chrome/dismissal.
function _rateRows(p) {
  const P = v => Math.max(0, Math.round(v || 0));
  const wall = P(p.wall_ms), comp = P(p.completion_ms), dec = P(p.decode_ms);
  const pre = Math.max(0, comp - dec);   // same derivation as the admin panel
  const tool = P(p.tool_ms), cx = P(p.compaction_ms);
  const idle = Math.max(0, wall - comp - tool - cx);
  const pct = ms => wall > 0 ? ((ms / wall) * 100).toFixed(ms / wall < 0.1 ? 1 : 0) + '%' : '–';
  const fmt = ms => ms >= 10000 ? (ms / 1000).toFixed(1) + 's' : Math.round(ms) + 'ms';
  const row = (label, ms, cls) => `<div class="ctx-popup-row"><span>${label}</span><b class="${cls || ''}">${fmt(ms)} · ${pct(ms)}</b></div>`;
  const rows = [];
  rows.push(`<div class="ctx-popup-row"><span>Turn wall time</span><b>${fmt(wall)}</b></div>`);
  rows.push(row('Prefill (queue + prompt)', pre, 'rp-prefill'));
  rows.push(row('Decode (generation)', dec, 'rp-decode'));
  rows.push(row('Tool execution', tool, 'rp-tool'));
  if (cx > 0) rows.push(row('Compaction', cx, 'rp-cx'));
  rows.push(row('Other / idle', idle));
  if (p.completion_tokens > 0 && dec > 0) rows.push(`<div class="ctx-popup-note">Decode rate ${RATE_FMT(p.completion_tokens / (dec / 1000))} · ${p.completion_tokens.toLocaleString('en-US')} tokens over ${p.rounds || '?'} round(s)</div>`);
  return rows.join('');
}
function openRatePopup(convId, anchorEl) {
  if (_ctxPopupEl) { _closeContextPopup(); return; }   // toggle off if already open
  const s = convStreams.get(convId);
  const p = s && s._turnProfile;
  const pop = document.createElement('div');
  pop.className = 'ctx-popup';
  pop.innerHTML = '<div class="ctx-popup-title">Turn profile</div>' +
    (p ? _rateRows(p) : '<div class="ctx-popup-note">' + (s && s.generating
      ? 'No turn profile yet — it appears once the current turn finishes.'
      : 'No turn profile recorded for this turn.') + '</div>');
  document.body.appendChild(pop);
  _ctxPopupEl = pop;
  const r = anchorEl.getBoundingClientRect();
  const pr = pop.getBoundingClientRect();
  let top = r.top - pr.height - 8;
  if (top < 8) top = r.bottom + 8;                         // flip below if no room above
  let left = Math.min(Math.max(8, r.left), window.innerWidth - pr.width - 8);
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
  const onDocClick = (e) => { if (_ctxPopupEl && !_ctxPopupEl.contains(e.target) && e.target !== anchorEl) _closeContextPopup(); };
  const onKey = (e) => { if (e.key === 'Escape') _closeContextPopup(); };
  setTimeout(() => document.addEventListener('mousedown', onDocClick), 0);
  document.addEventListener('keydown', onKey);
  window.addEventListener('scroll', _closeContextPopup, { capture: true, once: true });
  _ctxPopupCleanup = () => { document.removeEventListener('mousedown', onDocClick); document.removeEventListener('keydown', onKey); };
}

/* expose timer globals for sandpie-test.html inline scripts */
window.toggleThoughts = toggleThoughts;
window.startTotalTimer = startTotalTimer;
window.endTotalTimer = endTotalTimer;

/* =============================================================================
   Boot — render the conversation list and restore the last-open chat. Runs on
   DOMContentLoaded (NOT at module-eval) so artifacts.js has loaded before a
   restored message can call renderArtifact(). The saved theme is restored
   separately by themes.js.
   ============================================================================= */
// Compaction progress banner: shown in a conversation's host while a compact-sink
// agent is summarizing (pre-send compaction emits these events). Pre-send compaction
// is awaited before the turn goes out, so without this the user just sees an
// unexplained pause. Removed on end (and harmlessly wiped by the post-compaction
// re-render, whichever comes first).
function showCompactionProgress(convId) {
  try {
    const s = convStreams.get(convId);
    const host = (s && s.host) || paneScrollEl($('messages'));
    if (!host || host.querySelector('.compaction-progress')) return;
    const el = document.createElement('div');
    el.className = 'compaction-progress';
    el.innerHTML = '<span class="cp-spin" aria-hidden="true"></span><span>Summarizing earlier messages to free up context…</span>';
    appendContent(host, el);
    if (shouldAutoScroll(host) || isAtBottom(host)) host.scrollTop = host.scrollHeight;
  } catch (_) {}
}
function hideCompactionProgress(convId) {
  try {
    const s = convStreams.get(convId);
    const host = (s && s.host) || paneScrollEl($('messages'));
    if (host) host.querySelectorAll('.compaction-progress').forEach(e => e.remove());
  } catch (_) {}
}

// Generic background-op indicator (reuses the compaction spinner styling). Used
// for lessons distillation and memory consolidation, which are silent LLM calls
// the user should see running. Keyed so multiple ops don't collide.
// Short title for a conversation (first user message, clipped), from its live
// stream. Returns '' if the stream is gone — the banner then omits the name.
function _shortConvTitle(convId) {
  try {
    const s = convStreams.get(convId);
    const msgs = s && s.messages;
    const fu = msgs && msgs.find(m => m.role === 'user');
    if (!fu) return '';
    const t = typeof fu.content === 'string'
      ? fu.content
      : (Array.isArray(fu.content) ? fu.content.filter(p => p && p.type === 'text').map(p => p.text).join(' ') : '');
    const clipped = (t || '').trim().slice(0, 40);
    return clipped && (t.trim().length > 40) ? clipped + '…' : clipped;
  } catch (_) { return ''; }
}
// App-level background-op pill, for work that belongs to no particular
// conversation (the pre-reload flush). Same spinner as compaction / lessons /
// memory-consolidation — there is only one progress affordance in the app.
// activeConvId may be null on the home screen; showBgProgress handles that (the
// convId === activeConvId test passes null === null and falls back to the pane).
function showAppProgress(key, text) { return showBgProgress(activeConvId, key, text); }
function hideAppProgress(key)       { return hideBgProgress(activeConvId, key); }
function showBgProgress(convId, key, text) {
  try {
    const s = convStreams.get(convId);
    // Render only in the conversation this op belongs to. Fall back to the visible
    // #messages ONLY when it IS the active conversation — otherwise a background op
    // (e.g. lessons for a conv you just switched away from) would leak its banner
    // into the unrelated conversation you're now viewing (e.g. a fresh + New chat).
    const host = (s && s.host) || (convId === activeConvId ? paneScrollEl($('messages')) : null);
    if (!host || host.querySelector('.bg-progress[data-key="' + key + '"]')) return;
    const el = document.createElement('div');
    el.className = 'compaction-progress bg-progress';
    el.dataset.key = key;
    el.innerHTML = '<span class="cp-spin" aria-hidden="true"></span><span>' + text + '</span>';
    appendContent(host, el);
    if (shouldAutoScroll(host) || isAtBottom(host)) host.scrollTop = host.scrollHeight;
  } catch (_) {}
}
function hideBgProgress(convId, key) {
  try {
    const s = convStreams.get(convId || activeConvId);
    const host = (s && s.host) || paneScrollEl($('messages'));
    if (host) host.querySelectorAll('.bg-progress[data-key="' + key + '"]').forEach(e => e.remove());
  } catch (_) {}
}


// ---------------------------------------------------------------------------
// Settings → Archive tab. The sidebar "Archived (N)" row opens this modal tab
// (SandpieSettings.open('archive')) — archive management moved out of the
// sidebar. Lists archived convs via a dedicated scan of ARCHIVED_DIR (reuses
// the shared row cache), with filter chips, sort, archive-scoped search, a
// quiet pager and per-row actions (Unarchive / Open / Delete).
// ---------------------------------------------------------------------------
// One-time backfill: give every archived legacy .json a tiny meta sidecar so no
// listing path ever has to read the (potentially huge) body again. Runs chunked
// after the initial sync; idempotent (skips ids that already have a sidecar) and
// leaves the .json in place as a frozen backup (existing convention).
let _archBackfillDone = false;
async function backfillArchivedMetas() {
  if (_archBackfillDone) return;
  _archBackfillDone = true;
  try {
    const entries = await opfs.listDir(ARCHIVED_DIR).catch(() => []);
    const legacy = entries.filter(e => e.kind === 'file' && e.name.endsWith('.json') && !e.name.endsWith(META_SUFFIX));
    if (!legacy.length) return;
    let done = 0;
    for (const e of legacy) {
      const id = e.name.slice(0, -5);
      if (await opfs.exists(metaPath(id, true)).catch(() => false)) continue;
      try {
        const data = JSON.parse(await opfs.read(convPath(id, true)));
        const meta = {
          id,
          title: data.title || '(no title)',
          created: data.created || data.updated || '',
          updated: data.updated || '',
          msgCount: (data.messages || []).length,
        };
        if (data.pinned) meta.pinned = true;
        const mp = metaPath(id, true);
        await opfs.write(mp, JSON.stringify(meta));
        Sandpie.events.emit('file:changed', mp);
        done++;
      } catch (_) { /* unreadable body: leave it; the lazy path still lists the id */ }
      if (done % 10 === 0) await new Promise(r => setTimeout(r, 0));   // yield: never block a turn
    }
    if (done) console.info('[sandpie] Archived-meta backfill: ' + done + ' legacy conversation(s) sidecar-ed');
  } catch (e) { console.warn('[sandpie] archived backfill failed:', e); }
}

// Lazy archived listing (archive-dehydration step 2). Phase 1 is a pure name
// scan of ARCHIVED_DIR — zero file reads; ids are ISO timestamps, so sorting by
// id IS sorting by date. Phase 2 reads metas ONLY for the ids a caller asks for
// (one page at a time); a background fill then reads the rest in idle chunks so
// counts / alpha sort / title search converge. Cloud-only rows (meta dehydrated
// to Dropbox) merge in from the sync provider's cloud index with no marker and
// hydrate on demand when opened.
const _archScan = { ids: null, cloudIds: null };   // ordered newest-first id lists
function _archScanInvalidate() { _archScan.ids = null; _archScan.cloudIds = null; }
async function _archLocalIds() {
  if (_archScan.ids) return _archScan.ids;
  let entries = [];
  try { entries = await opfs.listDir(ARCHIVED_DIR); } catch { /* empty */ }
  const ids = [], seen = new Set();
  for (const e of entries) {
    if (e.kind !== 'file') continue;
    if (e.name.endsWith(META_SUFFIX)) { const id = e.name.slice(0, -META_SUFFIX.length); if (!seen.has(id)) { seen.add(id); ids.push(id); } }
    else if (e.name.endsWith('.json')) {
      const id = e.name.slice(0, -5);
      if (!seen.has(id)) { seen.add(id); ids.push(id); }   // legacy .json (meta sidecar may come later)
    }
  }
  ids.sort((a, b) => b.localeCompare(a));   // id = ISO timestamp → newest first
  _archScan.ids = ids;
  return ids;
}
async function _archCloudIds() {
  if (_archScan.cloudIds) return _archScan.cloudIds;
  const ids = [];
  try {
    const sp = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
    const idx = sp && sp.cloudIndex && sp.cloudIndex();
    if (idx) {
      const prefix = ARCHIVED_DIR + '/';
      const seen = new Set();
      for (const rel of Object.keys(idx)) {
        if (!rel.startsWith(prefix)) continue;
        const name = rel.slice(prefix.length);
        const id = name.replace(/\.(?:jsonl|meta\.json|json)$/, '');
        if (id && !seen.has(id)) { seen.add(id); ids.push(id); }
      }
    }
  } catch (_) { /* cloud merge is best-effort */ }
  ids.sort((a, b) => b.localeCompare(a));
  _archScan.cloudIds = ids;
  return ids;
}
// Instant listing: every archived id as a skeleton row (title '(loading…)' until
// its meta is read). Never blocks on file I/O beyond the single listDir.
async function listArchived() {
  const [local, cloud] = await Promise.all([_archLocalIds(), _archCloudIds()]);
  const seen = new Set();
  const out = [];
  for (const id of [...local, ...cloud]) {
    if (seen.has(id)) continue;
    seen.add(id);
    const key = 'a:' + id;
    const cached = _convRowCache.get(key);
    out.push(cached || { id, title: '(loading…)', updated: id, pinned: false, archived: true, _format: null, _pending: true });
  }
  return out;
}
// Read the real rows for a set of ids (one page). Returns the rows found.
async function readArchivedRows(ids) {
  const rows = await Promise.all(ids.map(async (id) => {
    const key = 'a:' + id;
    if (_convRowCache.has(key)) return _convRowCache.get(key);
    let format = null;
    if (await opfs.exists(metaPath(id, true)).catch(() => false)) format = 'new';
    else if (await opfs.exists(convPath(id, true)).catch(() => false)) format = 'old';
    const row = format ? await readConvMetaRow(id, true, format, false) : null;
    if (row) { _convRowCache.set(key, row); return row; }
    return null;   // cloud-only or unreadable: stays a skeleton row
  }));
  return rows.filter(Boolean);
}
// Background fill: read remaining metas in small chunks so counts / alpha sort /
// title search converge without ever blocking the interaction path.
let _archFillRunning = false;
async function fillArchivedRows(onProgress, onDone) {
  if (_archFillRunning) return;
  _archFillRunning = true;
  try {
    const ids = await _archLocalIds();
    for (let i = 0; i < ids.length; i += 10) {
      const chunk = ids.slice(i, i + 10).filter(id => !_convRowCache.has('a:' + id));
      if (chunk.length) await readArchivedRows(chunk);
      if (onProgress) onProgress();
      await new Promise(r => setTimeout(r, 0));
    }
    if (onDone) onDone();
  } finally { _archFillRunning = false; }
}

function registerArchiveSettingsTab() {
  if (typeof SandpieSettings === 'undefined' || !SandpieSettings.register) return;
  const CHUNK = 50;
  const state = { filter: 'all', sort: 'date-desc', query: '', shown: CHUNK };
  const FILTERS = [
    { id: 'all',   label: 'All',        test: () => true },
    { id: 'week',  label: 'Last week',  test: c => Date.now() - new Date(c.updated).getTime() < 7 * 86400000 },
    { id: 'month', label: 'Last month', test: c => Date.now() - new Date(c.updated).getTime() < 30 * 86400000 },
    { id: '3mo',   label: '3 months',   test: c => Date.now() - new Date(c.updated).getTime() < 90 * 86400000 },
    { id: 'older', label: 'Older',      test: c => Date.now() - new Date(c.updated).getTime() >= 90 * 86400000 },
  ];
  const SORTERS = {
    'date-desc': (a, b) => (b.updated || '').localeCompare(a.updated || ''),
    'date-asc':  (a, b) => (a.updated || '').localeCompare(b.updated || ''),
    'alpha':     (a, b) => (a.title || '').toLowerCase().localeCompare((b.title || '').toLowerCase()),
  };
  let chipsEl = null, segEl = null, searchEl = null, listEl = null, countEl = null;

  // Entry point for the sidebar's "Search the archive for …" row: seed the tab's
  // own search state, open it, then refresh so the query runs immediately.
  window.SandpieArchive = {
    openWith(q) {
      state.query = String(q || '').trim().toLowerCase();
      state.filter = 'all';
      state.shown = CHUNK;
      if (window.SandpieSettings) SandpieSettings.open('archive');
      if (searchEl) searchEl.value = state.query;
      refresh();
    }
  };

  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function highlight(title) {
    if (!state.query) return esc(title);
    const idx = title.toLowerCase().indexOf(state.query);
    if (idx < 0) return esc(title);
    return esc(title.slice(0, idx)) + '<span style="background:var(--sp-accent-dim);border-radius:2px;padding:0 1px;">'
      + esc(title.slice(idx, idx + state.query.length)) + '</span>' + esc(title.slice(idx + state.query.length));
  }
  function filtered(list) {
    const f = FILTERS.find(x => x.id === state.filter) || FILTERS[0];
    let pool = list.filter(c => f.test(c));
    if (state.query) pool = pool.filter(c => c._cloudHit || (c.title || '').toLowerCase().includes(state.query));
    return pool.slice().sort(SORTERS[state.sort] || SORTERS['date-desc']);
  }

  let _lastFillRefresh = 0;
  async function refresh() {
    let list = await listArchived();
    // Archive-scoped search: titles match locally (metas), CONTENT matches come
    // from the cloud (files/search_v2 over the archived folder) — no jsonl reads.
    // Cloud-matched rows are kept even while their title is still '(loading…)'.
    if (state.query) {
      const cloudIds = await searchArchivedCloud(state.query);
      list = list.filter(c => (c.title || '').toLowerCase().includes(state.query) || cloudIds.has(c.id));
      for (const c of list) if (cloudIds.has(c.id)) c._cloudHit = true;
    }
    countEl.textContent = list.length + ' conversation' + (list.length === 1 ? '' : 's');
    // filter chips with live counts
    chipsEl.replaceChildren();
    for (const f of FILTERS) {
      const n = list.filter(c => f.test(c)).length;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'arch-chip' + (f.id === state.filter ? ' active' : '');
      b.innerHTML = esc(f.label) + ' <span class="n">' + n + '</span>';
      b.onclick = () => { state.filter = f.id; state.shown = CHUNK; refresh(); };
      chipsEl.appendChild(b);
    }
    let pool = filtered(list);
    let shownNow = Math.min(state.shown, pool.length);
    // Hydrate the VISIBLE page's skeleton rows (one page of meta reads — never
    // the whole archive), then re-filter so hydrated titles land in place. A
    // throttled background fill converges counts / alpha sort / search meanwhile.
    const pageIds = pool.slice(0, shownNow).filter(c => c._pending).map(c => c.id);
    if (pageIds.length) {
      await readArchivedRows(pageIds);
      list = await listArchived();
      if (state.query) {
        const cloudIds = await searchArchivedCloud(state.query);
        list = list.filter(c => (c.title || '').toLowerCase().includes(state.query) || cloudIds.has(c.id));
        for (const c of list) if (cloudIds.has(c.id)) c._cloudHit = true;
      }
      pool = filtered(list);
      shownNow = Math.min(state.shown, pool.length);
      fillArchivedRows(() => {
        if (listEl && Date.now() - _lastFillRefresh > 800) { _lastFillRefresh = Date.now(); refresh(); }
      }, () => { if (listEl) refresh(); });
    }
    const frag = document.createDocumentFragment();
    if (!pool.length) {
      const li = document.createElement('li');
      li.className = 'arch-empty';
      li.textContent = state.query ? 'No archived conversations match "' + state.query + '"' : 'No conversations in this range';
      frag.appendChild(li);
    } else {
      for (let i = 0; i < shownNow; i++) {
        const c = pool[i];
        const li = document.createElement('li');
        const name = document.createElement('span');
        name.className = 'name'; name.innerHTML = highlight(c.title || '(no title)'); name.title = c.title || '';
        const meta = document.createElement('span');
        meta.className = 'conv-meta'; meta.textContent = fmtRelTime(c.updated);
        li.append(name, meta);
        li.onclick = (ev) => {
          ev.stopPropagation();
          const items = [
            { label: 'Unarchive', action: async () => { await toggleArchiveConv(c.id, true); refresh(); } },
            { label: 'Open conversation', action: () => { if (window.SandpieSettings) SandpieSettings.close(); loadConv(c.id); } },
            { label: 'Delete', danger: true, action: () => deleteConv(c.id, c.title) },
          ];
          showContextMenu(ev.clientX, ev.clientY, items);
        };
        frag.appendChild(li);
      }
      if (pool.length > shownNow) {
        const p = document.createElement('li');
        p.className = 'arch-pager';
        const more = document.createElement('span');
        more.className = 'more-link'; more.textContent = 'show more';
        more.onclick = (e) => { e.stopPropagation(); state.shown = Math.min(pool.length, state.shown + CHUNK); refresh(); };
        const sep1 = document.createElement('span'); sep1.className = 'more-sep'; sep1.textContent = '·';
        const all = document.createElement('span');
        all.className = 'more-link'; all.textContent = 'show all';
        all.onclick = (e) => { e.stopPropagation(); state.shown = pool.length; refresh(); };
        const sep2 = document.createElement('span'); sep2.className = 'more-sep'; sep2.textContent = '·';
        const cnt = document.createElement('span'); cnt.className = 'more-count'; cnt.textContent = shownNow + '/' + pool.length;
        p.append(more, sep1, all, sep2, cnt);
        frag.appendChild(p);
      }
    }
    listEl.replaceChildren(frag);
  }

  SandpieSettings.register({
    id: 'archive', title: 'Archive', order: 19,
    render(panel) {
      panel.innerHTML = '';
      const head = document.createElement('div');
      head.className = 'arch-head';
      const h = document.createElement('h3'); h.textContent = 'Archive';
      countEl = document.createElement('span'); countEl.className = 'arch-total';
      head.append(h, countEl);
      chipsEl = document.createElement('div'); chipsEl.className = 'arch-chips';
      const tools = document.createElement('div'); tools.className = 'arch-tools';
      segEl = document.createElement('div'); segEl.className = 'arch-seg';
      for (const [id, label] of [['date-desc', 'Date ↓'], ['date-asc', 'Date ↑'], ['alpha', 'A–Z']]) {
        const b = document.createElement('button');
        b.type = 'button'; b.dataset.sort = id; b.textContent = label;
        b.className = id === state.sort ? 'active' : '';
        b.onclick = () => { state.sort = id; refresh(); };
        segEl.appendChild(b);
      }
      searchEl = document.createElement('input');
      searchEl.type = 'text'; searchEl.placeholder = 'Search archive…'; searchEl.autocomplete = 'off';
      searchEl.oninput = () => { state.query = searchEl.value.trim().toLowerCase(); state.shown = CHUNK; refresh(); };
      tools.append(segEl, searchEl);
      listEl = document.createElement('ul'); listEl.className = 'arch-list';
      panel.append(head, chipsEl, tools, listEl);
      refresh();
    },
    // onShow re-runs on EVERY activation so the list is current after
    // archive/unarchive happened elsewhere while the modal was open.
    onShow() { if (listEl) refresh(); },
  });
}

// ---- Rubber-band multi-select (shift+drag on empty sidebar space) + clear ----//
// A translucent band is drawn from the press point as the pointer drags, and every
// conv row its rectangle intersects joins the selection. Drops the band on release.
// Also: Esc in the sidebar clears the current selection.
let _rbActive = false, _rbStart = null;
function _installConvListGestures() {
  const ul = $('convList');
  if (!ul) return;
  const band = document.createElement('div');
  band.className = 'conv-rubber';
  band.style.display = 'none';
  document.body.appendChild(band);
  const styleBand = (x, y) => {
    const a = _rbStart;
    const left = Math.min(a.x, x), top = Math.min(a.y, y);
    band.style.left = left + 'px'; band.style.top = top + 'px';
    band.style.width = (Math.abs(x - a.x)) + 'px';
    band.style.height = (Math.abs(y - a.y)) + 'px';
    band.style.display = 'block';
    const rbRect = band.getBoundingClientRect();
    _selConvs.clear();
    for (const li of ul.querySelectorAll('li[data-cid]')) {
      const lr = li.getBoundingClientRect();
      const hit = !(lr.right < rbRect.left || lr.left > rbRect.right ||
                    lr.bottom < rbRect.top || lr.top > rbRect.bottom);
      if (hit) _selConvs.add(li.dataset.cid);
    }
    _selHighlight();
  };
  ul.addEventListener('pointerdown', (ev) => {
    if (!ev.shiftKey) return;                 // only shift+drag selects
    if (ev.target !== ul && ev.target.closest('li[data-cid]')) { return; } // starting on a row: let normal click handle it
    _rbActive = true; _rbStart = { x: ev.clientX, y: ev.clientY };
    ev.preventDefault();
  });
  ul.addEventListener('pointermove', (ev) => {
    if (!_rbActive) return;
    styleBand(ev.clientX, ev.clientY);
  });
  const _rbEnd = () => {
    if (!_rbActive) return;
    _rbActive = false;
    band.style.display = 'none';
    _rbStart = null;
  };
  ul.addEventListener('pointerup', _rbEnd);
  ul.addEventListener('pointercancel', _rbEnd);
  // Click on empty sidebar space clears the selection (same as Esc).
  ul.addEventListener('click', (ev) => {
    if (ev.target === ul && _selConvs.size) _selClear();
  });
  // Clicking ANYWHERE outside the conversation list clears the selection -
  // a mousedown on the document that is not inside a conv-list row. Listens on
  // the whole document so the sidebar header, messages pane, etc. dismiss it.
  document.addEventListener('mousedown', (ev) => {
    if (!_selConvs.size) return;
    if (ev.target.closest && ev.target.closest('ul#convList')) return;
    _selClear();
  });
  // Esc clears the current multi-selection.
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && _selConvs.size) _selClear();
  });
}
function bootConversations() {
  registerArchiveSettingsTab();
  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('compaction:start', ({ convId }) => showCompactionProgress(convId));
    Sandpie.events.on('compaction:end', ({ convId }) => hideCompactionProgress(convId));
    // Memory consolidation (memory.js) — events existed but had no indicator.
    Sandpie.events.on('memory:consolidate-start', () => showBgProgress(activeConvId, 'consolidate', 'Consolidating memory…'));
    Sandpie.events.on('memory:consolidate-end', () => hideBgProgress(activeConvId, 'consolidate'));
    // Invalidate the sidebar row cache when a conversation's meta changes
    // (title/updated/pinned) or is deleted. Only meta paths: `.jsonl` appends
    // fire constantly during a turn but never change a row.
    const invalidateConvRow = (path) => {
      const p = String(path || '');
      if (!p.includes('/conversations/') || !p.endsWith('.json')) return;
      const id = (p.split('/').pop() || '').replace(/\.(?:meta\.)?json$/, '');
      if (!id) return;
      _convRowCache.delete('a:' + id);
      _convRowCache.delete('n:' + id);
      if (p.includes('/conversations/archived/')) { _archSearchInvalidate(); _archScanInvalidate(); }
    };
    Sandpie.events.on('file:changed', invalidateConvRow);
    Sandpie.events.on('file:deleted', invalidateConvRow);
    // PER-CONV provider: keep WARM streams in sync with meta.json changes made by
    // ANOTHER tab (shared OPFS) or another browser (Dropbox sync pulls the meta).
    // Without this the stale in-memory providerId both displays the wrong model
    // and can overwrite the fresher meta on the next saveConv (last-writer-wins
    // with a stale value). Only the provider is synced here — title/messages
    // stay per-pane as they are.
    const syncWarmProvider = async (path) => {
      try {
        const p = String(path || '');
        if (!p.includes('/conversations/') || !p.endsWith('.json')) return;
        const id = (p.split('/').pop() || '').replace(/\.(?:meta\.)?json$/, '');
        if (!id) return;
        const s = convStreams.get(id);
        if (!s || !s.messages || !s.messages.length) return;   // cold: mount reads meta fresh
        if (s._provDirty) return;                              // this tab has a newer explicit pick; its save wins
        const loc = await convLocation(id);
        if (!loc || loc.format !== 'new') return;              // legacy .json convs carry no provider meta
        const meta = JSON.parse(await opfs.read(metaPath(id, loc.archived)));
        const pid = meta.providerId || null;
        if ((s.providerId || null) !== pid) s.providerId = pid;
        const rl = meta.reasoningLevel || null;
        if ((s.reasoningLevel || null) !== rl) s.reasoningLevel = rl;
        const prj = meta.projectId || null;
        if ((s.projectId || null) !== prj) s.projectId = prj;
        if (((s.providerId || null) !== pid || (s.reasoningLevel || null) !== rl)
            && window.SandpieProviders && SandpieProviders.refreshPickers) SandpieProviders.refreshPickers();
      } catch (_) {}
    };
    Sandpie.events.on('file:changed', syncWarmProvider);
    // Auto-archive stale conversations once, after the initial Dropbox sync
    // completes (splash still visible) — not on a timer.
    Sandpie.events.on('sync:done', () => { backfillArchivedMetas().then(() => autoArchiveStale()); });
    _installConvListGestures();
  }
  // Boot starts on a FRESH conversation (home screen, ctx 0). The last-open
  // chat is NOT auto-restored anymore (2026-09-02: opening the app used to
  // remount the previous conversation and show its ctx counter instead of 0).
  // The stale pointer is cleared BEFORE anything paints (the resting timer
  // placeholder reads it as a fallback), so the home screen always shows "– ctx".
  try { localStorage.removeItem('sandpie-active-conv'); } catch (_) {}
  (async () => {
    await refreshConversationList();
    refreshPaneBars();   // bar always shows on desktop from first paint — 'New chat' when no conversation is mounted
    _ensureTimerPlaceholders();   // resting timer bar present in the DOM from first paint, even with no conversation mounted
    const scrollEnd = () => { const m = paneScrollEl($('messages')); if (m) m.scrollTop = m.scrollHeight; };
    requestAnimationFrame(() => requestAnimationFrame(scrollEnd));
    document.querySelectorAll('#messages img').forEach(img => {
      if (!img.complete) img.addEventListener('load', scrollEnd, { once: true });
    });
    window._sandpieBootDone = true;
  })();
  // Resume any in-flight generation after a tab refresh.

}
if (document.readyState === 'complete') {
  bootConversations();
} else {
  document.addEventListener('DOMContentLoaded', bootConversations, { once: true });
}

export {
  newConvId,
  convPath,
  ensureActiveConv,
  saveActiveConv,
  saveConv,
  renderHistoricalMessage,
  clearActiveConvUI,
  parkActiveConv,
  mountConv,
  loadConv,
  newConversation,
  listConversations,
  updateConvFile,
  renameConv,
  togglePinConv,
  toggleArchiveConv,
  duplicateConv,
  deleteConv,
  fmtRelTime,
  buildConvLi,
  refreshConversationList,
  refreshSendButtonForActive,
  setStreamSending,
  handleSubmit,
  enqueueForActive,
  handleButtonClick,

  sendSingle,
  buildAgentConfig,
  readAgentEvents,
  dispatchAgentEvent
};
