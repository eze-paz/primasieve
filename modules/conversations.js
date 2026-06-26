const CONV_DIR = 'sandpie/conversations';
const ARCHIVED_DIR = 'sandpie/conversations/archived';
function newConvId() {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}
function convPath(id, archived = false) {
  return archived ? `${ARCHIVED_DIR}/${id}.json` : `${CONV_DIR}/${id}.json`;
}
async function ensureActiveConv() {
  if (activeConvId) return;
  activeConvId = newConvId();
  localStorage.setItem('sandpie-active-conv', activeConvId);
}
async function saveActiveConv() { return saveConv(activeConvId, { touchUpdated: false }); }
async function saveConv(convId, { touchUpdated = true } = {}) {
  if (!convId) return;
  const s = convStreams.get(convId);
  const msgs = s ? s.messages : (convId === activeConvId ? messages : null);
  if (!msgs || !msgs.length) return;

  // Preserve archived location if the conv is already in archived folder.
  const archived = await opfs.exists(convPath(convId, true));
  const path = convPath(convId, archived);

  let prev = {};
  try { prev = JSON.parse(await opfs.read(path)); } catch {}
  const firstUser = msgs.find(m => m.role === 'user');
  let derived = 'Untitled';
  if (firstUser && firstUser.content) {
    const text = typeof firstUser.content === 'string'
      ? firstUser.content
      : firstUser.content.filter(p => p.type === 'text').map(p => p.text).join('');
    derived = text.slice(0, 60);
  }
  const data = {
    ...prev,
    id: convId,
    title: prev.title || derived,
    updated: touchUpdated ? new Date().toISOString() : (prev.updated || new Date().toISOString()),
    messages: msgs,
  };
  delete data.compactions;   // legacy restore-stack — superseded by `compaction`
  if (s) { if (s.compaction) data.compaction = s.compaction; else delete data.compaction; }
  await opfs.write(path, JSON.stringify(data));
  Sandpie.events.emit('file:changed', path);
  await refreshConversationList();
}
function renderHistoricalMessage(m, host = null) {
  if (m.role === 'user') {
    if (m._loadedImage) return;   // model-only image (load_image); shown in its tool-call box, not as a bubble
    bindBubble(addMsg('user', m.content, host), m);
  } else if (m.role === 'assistant') {
    const contentStr = typeof m.content === 'string' ? m.content :
      m.content.filter(p => p.type === 'text').map(p => p.text).join('');
    if (contentStr && contentStr.trim()) {
      const div = addMsg('assistant', '', host);
      div.innerHTML = renderMd(contentStr);
      bindBubble(div, m);
    }
    if (m.tool_calls) {
      for (const tc of m.tool_calls) {
        if (tc.function.name === 'show_artifact') {
          try {
            const { path } = JSON.parse(tc.function.arguments || '{}');
            if (path) {
              const target = host || $('messages');
              const existing = target.querySelector('.artifact-wrap[data-artifact-path="' + path + '"]');
              if (!existing) renderArtifact(host, path);
            }
          } catch (_) {}
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
          renderTcDone(tcDiv, tc.function.name);
          bindBubble(tcDiv, m);
        }
      }
    }
  } else if (m.role === 'tool') {
    const content = String(m.content || '');
    const target = host || $('messages');
    const toolCalls = target.querySelectorAll('.msg.tool-call');
    if (content.startsWith('image:')) {
      const path = content.slice('image:'.length);
      if (path && toolCalls.length > 0) {
        appendToolResultImage(toolCalls[toolCalls.length - 1].dataset.tcId, path, target);
      }
    } else if (!content.startsWith('artifact:')) {
      const t = content;
      const display = t.length > 500 ? t.slice(0, 500) + '…' : t;
      if (toolCalls.length > 0) {
        appendToolResult(toolCalls[toolCalls.length - 1].dataset.tcId, display, target);
      }
    }

  }
}
// Render a whole conversation into `host` (default: the active stream's host),
// honouring compaction: messages before the boundary are NOT sent to the model —
// they render collapsed behind a toggle, with the summary that's sent in their
// place — and messages from the boundary on render normally (in context).
function renderConversation(msgs, compaction, host = null) {
  const comp = (compaction && compaction.boundary > 0 && compaction.boundary < msgs.length) ? compaction : null;
  if (!comp) { for (const m of msgs) renderHistoricalMessage(m, host); return; }
  renderCompactionBlock(comp, msgs, host);
  for (let i = comp.boundary; i < msgs.length; i++) renderHistoricalMessage(msgs[i], host);
}

function renderCompactionBlock(comp, msgs, host) {
  const target = host || (activeStream() && activeStream().host) || $('messages');
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
  target.appendChild(wrap);
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

// Load a conversation file's messages + compaction state onto a stream (with
// migration). Used by every load path so compaction always survives a reload.
function hydrateStreamFromData(s, data) {
  migrateCompactionData(data);
  s.messages = (data.messages || []).slice();
  s.compaction = data.compaction || null;
}

function clearActiveConvUI() {

  const s = activeStream();
  if (s && s.host) s.host.innerHTML = '';
}
function parkActiveConv() {
  const s = activeStream();
  if (!s) return;
  s.messages = messages;
  if (s.host && s.host.parentNode) s.host.parentNode.removeChild(s.host);
}
function mountConv(convId) {
  activeConvId = convId;
  if (convId) {
    localStorage.setItem('sandpie-active-conv', convId);
    const s = ensureStream(convId);
    messages = s.messages;

    const target = sidePanel ? sidePanel.activeMountTarget() : $('messages');
    if (s.host.parentNode !== target) target.appendChild(s.host);
  } else {
    localStorage.removeItem('sandpie-active-conv');
    messages = [];
  }
  refreshSendButtonForActive();
  if (typeof SandpieTokens !== 'undefined') SandpieTokens.notify();
}
async function loadConv(id) {
  if (id === activeConvId) return;

  if (sidePanel?.isOpen && id === sidePanel.sideId) { sidePanel.flip(); return; }

  await saveActiveConv();
  parkActiveConv();
  if (convStreams.has(id)) {
    mountConv(id);
  } else {
    let data;
    // Try archived path first, then active.
    let path = convPath(id, true);
    try { data = JSON.parse(await opfs.read(path)); }
    catch {
      path = convPath(id, false);
      try { data = JSON.parse(await opfs.read(path)); }
      catch (e) {
        if (activeConvId) mountConv(activeConvId);
        addMsg('err', 'Failed to load conversation: ' + e.message);
        return;
      }
    }
    const s = ensureStream(id);
    hydrateStreamFromData(s, data);
    mountConv(id);
    renderConversation(s.messages, s.compaction);
  }
  activeConvId = id;
  localStorage.setItem('sandpie-active-conv', id);
  convLastViewed.set(id, new Date().toISOString());
  await refreshConversationList();
  document.body.classList.remove('sidebar-open');
  const btn = document.querySelector('.hamburger');
  if (btn) btn.textContent = '☰';
  const mEl = $('messages');
  mEl.scrollTop = mEl.scrollHeight;
}
async function newConversation() {
  await saveActiveConv();
  parkActiveConv();
  const id = newConvId();
  ensureStream(id);
  mountConv(id);
  convLastViewed.set(id, new Date().toISOString());
  await refreshConversationList();
}
async function listConversations() {
  let entries = [];
  try { entries = await opfs.listDir(CONV_DIR); } catch { /* empty */ }
  let archivedEntries = [];
  try { archivedEntries = await opfs.listDir(ARCHIVED_DIR); } catch { /* empty */ }

  const searchActive = !!($('convSearch')?.value.trim());

  const reads = [entries, archivedEntries]
    .flatMap((list, idx) =>
      list.filter(e => e.kind === 'file' && e.name.endsWith('.json'))
        .map(async (e) => {
          const id = e.name.slice(0, -5);
          const archived = idx === 1;
          try {
            const data = JSON.parse(await opfs.read(convPath(id, archived)));
            const row = {
              id: data.id || id,
              title: data.title || '(no title)',
              updated: data.updated || '',
              pinned: !!data.pinned,
              archived,
            };
            if (searchActive) {
              const messages = data.messages || [];
              row.messageContent = messages.map(m => m.content || '').join(' ').toLowerCase();
            }
            return row;
          } catch { return null; }
        })
    );
  const out = (await Promise.all(reads)).filter(Boolean);

  for (const c of out) {
    if (!convLastViewed.has(c.id)) convLastViewed.set(c.id, c.updated || '');
  }
  return out.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
}
let archivedExpanded = false;
async function updateConvFile(id, patch) {
  let data, path = convPath(id, true);
  try { data = JSON.parse(await opfs.read(path)); }
  catch {
    path = convPath(id, false);
    try { data = JSON.parse(await opfs.read(path)); }
    catch { return; }
  }
  Object.assign(data, patch);
  await opfs.write(path, JSON.stringify(data));
  Sandpie.events.emit('file:changed', path);
}
async function renameConv(id, current) {
  const next = prompt('Rename conversation', current);
  if (next == null) return;
  const trimmed = next.trim();
  if (!trimmed || trimmed === current) return;
  await updateConvFile(id, { title: trimmed });
  await refreshConversationList();
}
async function togglePinConv(id, currentlyPinned) {
  await updateConvFile(id, { pinned: !currentlyPinned });
  await refreshConversationList();
}
async function toggleArchiveConv(id, currentlyArchived) {
  // Archive is now a folder move, not a JSON property.
  const fromPath = convPath(id, currentlyArchived);
  const toPath = convPath(id, !currentlyArchived);
  let data;
  try { data = JSON.parse(await opfs.read(fromPath)); }
  catch { return; }
  // Keep the old JSON property for backward compatibility during transition.
  data.archived = !currentlyArchived;
  delete data.pinned;             // archived convs cannot stay pinned
  try {
    await opfs.write(toPath, JSON.stringify(data));
    Sandpie.events.emit('file:changed', toPath);
    await opfs.remove(fromPath);
    Sandpie.events.emit('file:deleted', fromPath);
  } catch (e) { console.warn('toggleArchiveConv failed:', e); }
  await refreshConversationList();
}
async function duplicateConv(id, title) {
  let data;
  // Try archived path first.
  let srcPath = convPath(id, true);
  try { data = JSON.parse(await opfs.read(srcPath)); }
  catch {
    srcPath = convPath(id, false);
    try { data = JSON.parse(await opfs.read(srcPath)); }
    catch (e) { addMsg('err', 'Failed to duplicate: ' + e.message); return; }
  }
  const newId = newConvId();
  data.id = newId;
  data.title = (data.title || title || '(no title)') + ' (copy)';
  data.pinned = false;
  data.archived = false;
  data.updated = new Date().toISOString();
  await opfs.write(convPath(newId, false), JSON.stringify(data));
  Sandpie.events.emit('file:changed', convPath(newId, false));
  await refreshConversationList();
}
async function deleteConv(id, title) {
  const dbxNote = Sandpie.syncProvider()?.isConnected?.() ? ' This will also remove the cloud copy.' : '';
  if (!confirm(`Delete conversation "${title}"?${dbxNote}`)) return;
  // Try archived path first, then active.
  let path = convPath(id, true);
  if (!(await opfs.exists(path))) path = convPath(id, false);
  try { await opfs.remove(path); } catch {}
  Sandpie.events.emit('file:deleted', path);

  const stream = convStreams.get(id);
  if (stream) {
    if (stream.abort) stream.abort.abort();
    if (stream.timerInterval) clearInterval(stream.timerInterval);
    if (stream.host && stream.host.parentNode) stream.host.parentNode.removeChild(stream.host);
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
  if (wk < 4) return wk + 'w';
  const mo = Math.floor(day / 30);
  if (mo < 12) return mo + 'mo';
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
function buildConvLi(c, idx) {
  const li = document.createElement('li');
  li.dataset.cid = c.id;
  if (c.id === activeConvId) li.classList.add('active');
  if (c.archived) li.classList.add('archived');
  const num = document.createElement('span');
  num.className = 'conv-num';
  num.textContent = String(idx).padStart(2, '0');
  const span = document.createElement('span');
  span.className = 'name';
  span.textContent = (c.pinned ? '* ' : '') + c.title;
  span.title = c.updated || '';
  span.onclick = () => loadConv(c.id);
  li.appendChild(num);
  li.appendChild(span);

  const meta = document.createElement('span');
  meta.className = 'conv-meta';
  const stream = convStreams.get(c.id);
  if (stream && stream.generating) {
    meta.classList.add('gen-dot');
    meta.title = 'Still generating…';
  } else {
    meta.textContent = fmtRelTime(c.updated);
    const lastViewed = convLastViewed.get(c.id);
    const hasNew = c.updated && (!lastViewed || new Date(c.updated) > new Date(lastViewed));
    if (hasNew && c.id !== activeConvId) meta.classList.add('unseen');
  }
  li.appendChild(meta);
  const _openConvMenu = (ev) => {
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
    ev.dataTransfer.setData('text/sandpie-conv-id', c.id);
    ev.dataTransfer.effectAllowed = 'copy';
  });
  return li;
}
async function refreshConversationList() {
  const ul = $('convList');
  if (!ul) return;
  let list = await listConversations();

  const searchInput = $('convSearch');
  if (searchInput && searchInput.value.trim()) {
    const query = searchInput.value.trim().toLowerCase();
    list = list.filter(c =>
      c.title.toLowerCase().includes(query) ||
      (c.messageContent && c.messageContent.includes(query))
    );
  }

  const pinned   = list.filter(c => c.pinned && !c.archived);
  const regular  = list.filter(c => !c.pinned && !c.archived);
  const archived = list.filter(c => c.archived);

  const visible = pinned.length + regular.length;
  $('convCount').textContent = visible ? `${visible}` : '';
  const frag = document.createDocumentFragment();
  if (!list.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = Sandpie.initialSyncDone() ? '(no chats yet)' : 'Loading…';
    frag.appendChild(li);
    ul.replaceChildren(frag);
    return;
  }
  pinned.forEach((c, i) => frag.appendChild(buildConvLi(c, i)));
  if (pinned.length && regular.length) {
    const sep = document.createElement('li');
    sep.style.cssText = 'height:6px; margin:0; cursor:default; pointer-events:none;';
    sep.setAttribute('aria-hidden', 'true');
    frag.appendChild(sep);
  }
  regular.forEach((c, i) => frag.appendChild(buildConvLi(c, pinned.length + i)));
  if (archived.length) {
    const header = document.createElement('li');
    header.className = 'archived-toggle';
    header.textContent = `${archivedExpanded ? '▾' : '▸'} Archived (${archived.length})`;
    header.onclick = () => { archivedExpanded = !archivedExpanded; refreshConversationList(); };
    frag.appendChild(header);
    if (archivedExpanded) archived.forEach((c, i) => frag.appendChild(buildConvLi(c, pinned.length + regular.length + i)));
  }
  ul.replaceChildren(frag);
}
function refreshSendButtonForActive() {
  const btn = $('sendBtn');
  if (!btn) return;
  const s = activeStream();
  if (s && s.generating) {
    btn.textContent = '■';
    btn.title = 'Stop';
    btn.classList.add('sending');
    btn.disabled = false;
  } else {
    btn.textContent = '▶';
    btn.title = 'Send';
    btn.classList.remove('sending');
    btn.disabled = false;
  }
}
function setStreamSending(stream, sending) {
  if (!stream) return;
  if (sending) {
    stream.abort = new AbortController();
    stream.queueAborted = false;
    stream.generating = true;
  } else {
    stream.abort = null;
    stream.generating = false;

    for (const el of stream.host.querySelectorAll('.tool-call')) {
      if (el.querySelector('.tc-prompt')) continue;
      el.classList.remove('in-flight');
      renderTcDone(el, el.dataset.fname);
    }
  }
  if (stream === activeStream()) refreshSendButtonForActive();

  refreshConversationList();
}
async function handleSubmit() {
  const text = $('input').value.trim();
  if (!text && !SandpieImages.hasAttachment()) return;
  if (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.showRelevance) SandpieAugmentations.showRelevance(text, activeConvId).catch(() => {});
  $('input').value = '';

  const content = await SandpieImages.buildContent(text);

  if (SandpieImages.hasAttachment()) {
    SandpieImages.clear();
  }
  const m = $('messages');
  lockScroll(m);
  m.scrollTop = m.scrollHeight;
  enqueueForActive(content);

  const ta = $('input');
  if (ta) {
    ta.style.height = 'auto';
  }
}
async function enqueueForActive(content) {
  await ensureActiveConv();
  const s = ensureStream(activeConvId);

  if (s.host.parentNode !== $('messages')) mountConv(activeConvId);
  s.queue.push(content);
  updateQueueCount(s);
  processQueueFor(s);
}
function handleButtonClick() {
  const btn = $('sendBtn');
  const s = activeStream();
  if (btn.classList.contains('sending') && s) {
    // Stop only the message generating right now; queued messages stay and the
    // next one is sent immediately. To halt everything, press stop once per
    // in-flight + queued message.
    if (s.abort) s.abort.abort();
    updateQueueCount(s);
  } else {
    handleSubmit();
  }
}
function updateQueueCount(stream) {
  // Refresh just the queue pill inside the live timer. The timer's own tick
  // (startTotalTimer→paint) also keeps this in sync; this gives an instant
  // update when the queue changes without rebuilding the timer's other spans.
  const s = stream || activeStream();
  if (!s || !s.timerEl) return;
  const queueEl = s.timerEl.querySelector('.mt-queue, .queue-pill');
  if (!queueEl) return;
  const q = s.queue.length;
  queueEl.dataset.q = String(q);
  queueEl.className = q > 0 ? 'queue-pill' : 'mt-queue';
  queueEl.textContent = q > 0 ? `${q} queued` : '';
}
async function processQueueFor(stream) {
  if (!stream || stream.isProcessing || stream.queue.length === 0) return;
  stream.isProcessing = true;
  stream.queueAborted = false;
  updateQueueCount(stream);
  try {
    while (stream.queue.length > 0) {
      const text = stream.queue.shift();
      updateQueueCount(stream);
      await sendSingle(text, stream);
      // No break on stop: aborting the current generation advances to the next
      // queued message. The queue is only emptied by an explicit rewind.
    }
  } finally {
    stream.isProcessing = false;
    updateQueueCount(stream);
  }

  if (stream.queue.length > 0) processQueueFor(stream);
}
// ---- Sandpie Web Worker — Pyodide + tools + agent loop ----------------------
// Created once per page load. Other modules reach it via window._sandpieWorker.
let _sandpieWorker = null;
function getSandpieWorker() {
  if (_sandpieWorker) return _sandpieWorker;
  // Lives under modules/ (served wholesale by sandpie-server) rather than the
  // web root, where brand-new files have no route and 404. Path resolves against
  // the document base (root) → /modules/sandpie-worker.js.
  _sandpieWorker = new Worker('./modules/sandpie-worker.js?v=18');
  window._sandpieWorker = _sandpieWorker;
  _sandpieWorker.addEventListener('message', (event) => {
    const msg = event.data;
    if (!msg) return;
    if (msg.type === 'sandpie-worker-log') {
      const fn = console[msg.level] || console.log;
      fn.call(console, '[worker]', msg.text);
      return;
    }
    if (msg.type === 'forward-to-page') {
      // Relay opfs-deleted-by-python / sw-opfs-changed to existing SW message
      // listeners (dropbox-full.js) by dispatching onto navigator.serviceWorker.
      try { navigator.serviceWorker.dispatchEvent(new MessageEvent('message', { data: msg.payload })); } catch (_) {}
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
  let notify = null;

  const messageHandler = (event) => {
    const msg = event.data;
    if (!msg || msg.id !== id || msg.type !== 'event') return;
    queue.push(JSON.stringify(msg.event) + '\n');
    if (msg.event.type === 'agent_done' || msg.event.type === 'error') {
      streamDone = true;
      worker.removeEventListener('message', messageHandler);
    }
    if (notify) { const n = notify; notify = null; n(); }
  };
  worker.addEventListener('message', messageHandler);

  const cleanup = () => {
    worker.removeEventListener('message', messageHandler);
    try { worker.postMessage({ type: 'abort', id }); } catch (_) {}
  };

  const enc = new TextEncoder();
  return new ReadableStream({
    async pull(controller) {
      while (queue.length > 0) controller.enqueue(enc.encode(queue.shift()));
      if (streamDone) { controller.close(); return; }
      // Block until next event or abort signal fires.
      await new Promise((resolve, reject) => {
        notify = resolve;
        if (signal) {
          if (signal.aborted) { reject(new DOMException('aborted', 'AbortError')); return; }
          signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
        }
      });
      while (queue.length > 0) controller.enqueue(enc.encode(queue.shift()));
      if (streamDone) controller.close();
    },
    cancel() { cleanup(); },
  });
}

async function sendSingle(text, stream, opts = {}) {
  const { id: convId, messages: convMessages, host } = stream;

  // Render the user's message FIRST so it can never be lost. Even if the provider
  // config turns out to be incomplete, the message stays in the conversation and
  // the error appears after it — never in place of it.
  let wasAborted = false;
  if (!opts?.resume) {
    const userMsg = { role: 'user', content: text };
    convMessages.push(userMsg);
    bindBubble(addMsg('user', text, host), userMsg);
    saveConv(convId).catch(() => {});
  }

  // If no model is selected but a configured provider has one, use it rather than
  // erroring; then validate. On failure the message above is preserved.
  if (typeof SandpieProviders !== 'undefined' && SandpieProviders.ensureUsable) {
    try { SandpieProviders.ensureUsable(); } catch (_) {}
  }
  const _active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.getActive) ? SandpieProviders.getActive() : null;
  const _isLiteRTLM = !!(_active && _active.type === 'litertlm');
  const _isWebGPU = !!(_active && _active.type === 'webgpu');
  const _isLocal = _isLiteRTLM || _isWebGPU;
  if (_isLocal) _localInferring = true;
  if (!$('endpoint').value || !$('model').value || (!_isLocal && !$('apiKey').value)) {
    addMsg('err',
      _isLiteRTLM ? 'Pick a LiteRT-LM (Gemma) model in Settings before sending.' :
      _isWebGPU ? 'Pick a WebGPU (Qwen3.5) model in Settings before sending.' :
      'Add a provider (endpoint, model, and API key) in Settings before sending.', host);
    return;
  }
  requestWakeLock();
  setStreamSending(stream, true);

  // Proactive compaction: if a compactor agent's context threshold is met, run
  // it BEFORE this turn goes out so we never ship an over-limit request (and a
  // conversation already at the limit can still continue). Awaited so the
  // now-smaller context is what gets built below. Runs before startTotalTimer
  // because compaction re-renders the conversation host, which would otherwise
  // drop a timer added first.
  if (typeof SandpieAgents !== 'undefined' && SandpieAgents.maybeCompactBeforeSend) {
    try { await SandpieAgents.maybeCompactBeforeSend(convId); }
    catch (e) { console.warn('[sandpie] pre-send compaction failed:', e); }
  }

  // Snapshot the conversation's token size NOW (after any compaction) as the
  // baseline for the live CONTEXT meter; the paint loop pushes baseline +
  // generated-so-far while the turn runs. Clear any stale live override first so
  // we read the authoritative size.
  if (typeof SandpieTokens !== 'undefined') {
    try { SandpieTokens.clearLiveTokens && SandpieTokens.clearLiveTokens(); } catch (_) {}
    try { stream.tokBaseline = SandpieTokens.conversationTokens ? await SandpieTokens.conversationTokens() : 0; }
    catch (_) { stream.tokBaseline = 0; }
  }

  startTotalTimer(stream);
  flightWrite(convId, text);

  const config = await buildAgentConfig(convMessages, stream.compaction);

  const ctrl = new AbortController();
  stream.requestId = ctrl;
  const onAbort = () => ctrl.abort();
  if (stream.abort?.signal) {
    if (stream.abort.signal.aborted) onAbort();
    else stream.abort.signal.addEventListener('abort', onAbort, { once: true });
  }

  const renderer = new RoundRenderer(host, convMessages, _isLocal);

  let agentDoneSeen = false;
  let errorSeen = false;
  let lastInFlightTool = null;
  const dispatch = (ev) => {
    accountStreamTokens(stream, ev);
    if (ev.type === 'agent_done')  agentDoneSeen = true;
    if (ev.type === 'error')        errorSeen = true;
    if (ev.type === 'tool_started') {
      lastInFlightTool = ev.tc?.function?.name || 'unknown';
      try { const a = JSON.parse(ev.tc?.function?.arguments || '{}'); if (ev.tc?.function?.name === 'run_python' && a.path && typeof SandpieAugmentations !== 'undefined') SandpieAugmentations.getConvMeta(activeConvId).scripts.add(a.path); } catch (_) {}
    }
    if (ev.type === 'tool_result') {
      lastInFlightTool = null;
      try { const m = String(ev.result || '').match(/Created:\s*([^\s]+)/); if (m && typeof SandpieAugmentations !== 'undefined') SandpieAugmentations.getConvMeta(activeConvId).files.add(m[1]); } catch (_) {}
    }
    if (ev.type === 'usage') Sandpie.events.emit('tokens:record', {convId, usage: ev.usage});
    dispatchAgentEvent(ev, renderer, host);
  };
  try {

    if (_isLiteRTLM && typeof SandpieLiteRTLM !== 'undefined' && SandpieLiteRTLM.runConversation) {
      // Local Gemma via Google AI Edge LiteRT-LM (WebGPU). Same page-side loop.
      try { await SandpieQwen3?.unload?.(); } catch (_) {}
      await SandpieLiteRTLM.runConversation(
        { provider: _active, messages: config.messages, systemPrompt: config.systemPrompt, tools: config.tools, convId, signal: ctrl.signal },
        dispatch,
      );
    } else {
    const _isDense = _isWebGPU && typeof SandpieQwen3 !== 'undefined' && SandpieQwen3.DEFAULT_MODELS
      && SandpieQwen3.DEFAULT_MODELS.some(m => m.modelId === _active.endpoint);
    if (_isDense && SandpieQwen3.runConversation) {
      await SandpieQwen3.runConversation(
        { provider: _active, messages: config.messages, systemPrompt: config.systemPrompt, tools: config.tools, convId, signal: ctrl.signal },
        dispatch,
      );
    } else {
    const worker = getSandpieWorker();
    const _agentId = Math.random().toString(36).slice(2);
    worker.postMessage({ type: 'agent', id: _agentId, config });
    const workerStream = workerAgentStream(worker, _agentId, ctrl.signal);
    await readAgentEvents(workerStream, dispatch);

    if (!agentDoneSeen && !wasAborted && !errorSeen) {
      const trigger = lastInFlightTool ? ` while running \`${lastInFlightTool}\`` : '';
      addMsg('err',
        `Worker died mid-stream${trigger} — typically a Pyodide WASM crash. The worker will be restarted on your next message.`,
        host,
      );
    }
    }   // end inner cloud else
    }   // end outer else (litertlm not active)
  } catch (e) {
    if (e && (e.name === 'AbortError' || ctrl.signal.aborted)) {
      wasAborted = true;
      addMsg('info', 'Stopped.', host);
    } else {
      console.error('[sandpie] agent fetch error:', e);
      addMsg('err', 'Error: ' + ((e && (e.message || String(e))) || 'unknown'), host);
    }
  } finally {

    if (stream.abort?.signal) stream.abort.signal.removeEventListener('abort', onAbort);
    stream.requestId = null;
    flightClear(convId);

    _localInferring = false;
    renderer.finalize();

    releaseWakeLock();
    endTotalTimer(stream, wasAborted ? 'stopped' : 'done');
    // Drop the live CONTEXT override so the panel shows the authoritative
    // provider-reported size now the turn is done.
    try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.clearLiveTokens) SandpieTokens.clearLiveTokens(convId); } catch (_) {}
    setStreamSending(stream, false);
    await saveConv(convId);

    // Optional capability: notifications.js (if loaded) listens for this and
    // fires a system toast. No listener ⇒ no-op. saveConv ran first so the
    // listener can read the canonical (possibly renamed) conv title.
    Sandpie.events.emit('generation:complete', { convId, aborted: wasAborted });
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
async function buildAgentConfig(convMessages, compaction) {
  const endpoint = $('endpoint').value.replace(/\/$/, '');
  const url = new URL(api(endpoint + '/chat/completions'), location.href).href;
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
  const resolvedMessages = [];
  for (const msg of sendMessages) {
    if (msg.role === 'user' && Array.isArray(msg.content)) {
      const resolvedContent = [];
      for (const part of msg.content) {
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
  const active = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
  return {
    url,
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + $('apiKey').value },
    model: $('model').value,
    systemPrompt: await buildSystemPrompt(convMessages),
    messages: resolvedMessages,
    tools: toolDefs(),
    maxTokens: (active && active.maxTokens) || 8192,
    temperature: (active && active.temperature != null) ? active.temperature : null,
    reasoningEffort: (active && active.reasoningEffort) || null,
    origin: location.origin,
    conversation_file_name: activeConvId,
  };
}
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
function dispatchAgentEvent(ev, renderer, host) {
  switch (ev.type) {
    case 'round_start':   return renderer.startRound();
    case 'delta':         return renderer.applyDelta(ev.delta);
    case 'round_end':     return renderer.endRound(ev.content);
    case 'message_added': return renderer.bindMessage(ev.message);
    case 'tool_started':  return renderer.markToolStarted(ev.tc);
    case 'tool_result':   return renderer.markToolDone(ev.id, ev.result, ev.artifacts);
    case 'agent_done':    return;
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
      queue: [], isProcessing: false, queueAborted: false,
      abort: null,
      compaction: null,
      timerEl: null, timerStart: 0, timerInterval: null,
      genChars: 0, tokTarget: 0, tokShown: 0, rateShown: 0, tokBaseline: 0,
      generating: false,
    };
    convStreams.set(id, s);
  }
  return s;
}

function activeStream() { return activeConvId ? (convStreams.get(activeConvId) || null) : null; }
function flightWrite(id, text) {
  try { localStorage.setItem(SP_FLIGHT_KEY(id), JSON.stringify({t: Date.now(), text})); } catch(_) {}
}

function flightRead(id) {
  try { const v = localStorage.getItem(SP_FLIGHT_KEY(id)); return v ? JSON.parse(v) : null; } catch(_) { return null; }
}

function flightClear(id) { try { localStorage.removeItem(SP_FLIGHT_KEY(id)); } catch(_) {} }

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

function addMsg(role, text = '', host = null) {

  const target = host || (activeStream() && activeStream().host) || $('messages');

  let scrollHost = target;
  while (scrollHost && scrollHost.id !== 'messages' && scrollHost.id !== 'messagesSide') {
    scrollHost = scrollHost.parentNode;
  }
  const visible = !!scrollHost;
  const div = document.createElement('div');
  div.className = 'msg ' + role;
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
  }
  target.appendChild(div);

  const timer = target.querySelector(':scope > .msg-timer:not(.done)');
  if (timer) target.appendChild(timer);
  if (visible && shouldAutoScroll(scrollHost)) scrollHost.scrollTop = scrollHost.scrollHeight;
  return div;
}

function bindBubble(div, msgRef) {
  if (!div) return div;

  if (!div._listenersAttached) {
    div._listenersAttached = true;

    div.addEventListener('contextmenu', onBubbleContextMenu);
  }
  if (msgRef) div._msg = msgRef;
  return div;
}

function tcEscape(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function appendToolResult(tcId, result, scopeEl) {
  const root = scopeEl || document;
  const toolCalls = root.querySelectorAll('.msg.tool-call');
  let toolCallDiv = null;
  for (const div of toolCalls) {
    if (div.dataset.tcId === tcId) {
      toolCallDiv = div;
      break;
    }
  }
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

// Render a loaded image (load_image tool) inline inside its tool-call box, in
// place of a text result. The thumbnail is resolved from OPFS page-side.
function appendToolResultImage(tcId, path, scopeEl) {
  const root = scopeEl || document;
  const toolCalls = root.querySelectorAll('.msg.tool-call');
  let toolCallDiv = null;
  for (const div of toolCalls) {
    if (div.dataset.tcId === tcId) { toolCallDiv = div; break; }
  }
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

function buildToolBox(args, toolName) {
  let code = '';
  try {
    const parsed = JSON.parse(args);
    if (parsed.code) code = parsed.code;
    else if (parsed.cmd) code = parsed.cmd;
    else if (parsed.path) code = `run_python(path="${parsed.path}", args=${JSON.stringify(parsed.args || [])})`;
    else code = JSON.stringify(parsed, null, 2);
  } catch (e) {
    code = args;
  }
  const lines = code.split('\n').filter(l => l.trim());
  const codeHtml = lines.map(l => `<div class="line">${tcEscape(l)}</div>`).join('');
  const name = toolName || 'tool';
  const box = document.createElement('div');
  box.className = 'tool-box';
  box.innerHTML = `<div class="tool-code">${codeHtml}</div>`;
  return box;
}

// Python-REPL "thinking" loader: three chevrons with a sweep of emphasis.
// Replaces the old rotating-circle spinner; reused for tool calls and the
// thinking box. Styled by .repl-loader / @keyframes repl-sweep in sandpie.css.
const REPL_LOADER = (cls) => `<span class="repl-loader${cls ? ' ' + cls : ''}"><i>&gt;</i><i>&gt;</i><i>&gt;</i></span>`;

function renderTcPreparing(div, fname, args) {
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;

  const tok = Math.ceil((args ? String(args).length : 0) / 4);

  if (!el.querySelector('.repl-loader')) {
    el.innerHTML =
      REPL_LOADER('tc-dim') +
      `<span class="tc-title tc-dim">Preparing <b>${tcEscape(fname || 'tool')}</b>…</span>` +
      '<span class="tc-meta"></span>' +
      '<span class="tc-chevron">▸</span>';
  }
  const meta = el.querySelector('.tc-meta');
  if (meta) meta.textContent = tok > 0 ? `~${tok} tok` : '';
}

function renderTcRunning(div, fname) {
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;
  if (!el.querySelector('.repl-loader')) {
    el.innerHTML =
      REPL_LOADER() +
      `<span class="tc-title">Using <b>${tcEscape(fname)}</b>…</span>` +
      '<span class="tc-chevron">▸</span>';
  }
}

function renderTcDone(div, fname) {
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;
  el.innerHTML =
    '<span class="tc-prompt">&gt;&gt;&gt;</span>' +
    `<span class="tc-title tc-dim">${tcEscape(fname || 'tool')}</span>` +
    '<span class="tc-chevron">▸</span>';
}

class RoundRenderer {
  constructor(host, convMessages, isLocal = false) {
    this.host = host;
    this.convMessages = convMessages;
    this.isLocal = isLocal;

    this.reply = null;

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
    this.reply = addMsg('assistant', '', this.host);
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
    this.thinkStart = 0;
    this._thinkDone = false;
  }
  applyDelta(delta) {
    if (!delta) return;
    // Intrinsic reasoners (DeepSeek/Kimi/GLM via OpenRouter) stream their chain
    // of thought as reasoning_content (or reasoning). Render it live, but never
    // fold it into this.content — it must not be replayed back to the model.
    const r = (typeof delta.reasoning_content === 'string' && delta.reasoning_content)
           || (typeof delta.reasoning === 'string' && delta.reasoning);
    if (r) this._appendReasoning(r);
    if (delta.content) {
      this._finishThinking();
      this._appendContent(delta.content);
    }
    if (delta.tool_calls) {
      for (const tc of delta.tool_calls) this._applyToolCallDelta(tc);
    }
  }
  endRound(finalContent) {
    this._finishThinking();
    // The SW may rewrite this round's content — e.g. stripping a model's leaked
    // native tool-call tokens after recovering them into structured calls. When
    // the authoritative final content differs from what we live-typed, reconcile
    // so those raw tokens don't linger on screen. No-op in the normal case.
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
  bindMessage(msg) {
    this.convMessages.push(msg);
    if (msg.role === 'assistant') {
      if (this.reply) bindBubble(this.reply, msg);
      for (const el of this.toolCallEls) if (el) bindBubble(el, msg);
    } else if (msg.role === 'tool' && this.pendingToolResultDiv) {
      bindBubble(this.pendingToolResultDiv, msg);
      this.pendingToolResultDiv = null;
    }
  }
  markToolStarted(tc) {
    const idx = this.toolCalls.findIndex(t => t && t.id === tc.id);
    if (idx < 0 || !this.toolCallEls[idx]) return;
    this.toolCallEls[idx].classList.add('in-flight');
    renderTcRunning(this.toolCallEls[idx], tc.function.name);
  }
  markToolDone(tcId, result) {
    const idx = this.toolCalls.findIndex(t => t && t.id === tcId);
    if (idx >= 0 && this.toolCallEls[idx]) {
      this.toolCallEls[idx].classList.remove('in-flight');
      renderTcDone(this.toolCallEls[idx], this.toolCalls[idx].function.name);
    }
    const text = String(result || '');

    if (text.startsWith('artifact:')) {
      const path = text.slice('artifact:'.length);
      if (path) renderArtifact(this.host, path);
      return;
    }

    if (text.startsWith('image:')) {
      const path = text.slice('image:'.length);
      if (path && idx >= 0 && this.toolCallEls[idx]) appendToolResultImage(tcId, path, this.host);
      return;
    }
    const display = text.length > 500 ? text.slice(0, 500) + '…' : text;
    if (idx >= 0 && this.toolCallEls[idx]) {
      appendToolResult(tcId, display, this.host);
    }
  }
  finalize() {

    if (this.drainTimer) { clearTimeout(this.drainTimer); this.drainTimer = null; }
    this.toolsShouldClose = true;
    this._flushAllPending();
    this._finishThinking();
    // Full markdown render deferred from local inference — do it once now, then scroll
    if (this.isLocal && this.reply && this.displayed) {
      this.reply.innerHTML = renderMd(this.displayed);
    }
    if (this.isLocal) {
      const sh = this._scrollHost();
      if (sh && shouldAutoScroll(sh)) requestAnimationFrame(() => { sh.scrollTop = sh.scrollHeight; });
    }
  }

  _appendReasoning(chunk) {
    if (!this.thinkEl) this._createThinkBox();
    this.reasoning += chunk;
    this.thinkBody.textContent = this.reasoning;
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
    if (this.reply && this.reply.parentNode) {
      this.reply.parentNode.insertBefore(det, this.reply);
    } else {
      (this.host || $('messages')).appendChild(det);
    }
    this.thinkEl = det;
    this.thinkBody = body;
    this.thinkSummary = sum;
  }
  _finishThinking() {
    if (!this.thinkEl || this._thinkDone) return;
    this._thinkDone = true;
    const secs = Math.round((performance.now() - this.thinkStart) / 1000);
    this.thinkSummary.textContent = secs > 0 ? ('Thought for ' + secs + 's') : 'Thought';
    this.thinkEl.classList.add('done');
    this.thinkEl.open = false;
  }

  _appendContent(chunk) {

    this.content += chunk;
    this.pending += chunk;
    this._scheduleDrain();
  }
  _paintContent() {
    if (!this.reply) return;
    if (this.isLocal) {
      // Skip marked+DOMPurify per token — main thread stays free for GPU inference.
      // Full markdown render happens once in finalize() when generation is done.
      const bubble = this.reply.querySelector('.bubble') || this.reply;
      bubble.textContent = this.displayed;
      return;
    }
    this.reply.innerHTML = renderMd(this.displayed);
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
    if (!this.toolCallEls[i]) {

      this.toolCallEls[i] = addMsg('tool-call', '→ ' + this.toolCalls[i].function.name + '(', this.host);
      this.toolCallEls[i].dataset.fname = this.toolCalls[i].function.name;
      this.toolCallEls[i].dataset.tcId = this.toolCalls[i].id;
      this.toolDisplayed[i] = '';
      this.toolPending[i] = '';
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
    if (this.drainTimer == null) this.drainTimer = setTimeout(() => this._drainTick(), 16);
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
    let el = this.reply || this.host;
    while (el && el.id !== 'messages' && el.id !== 'messagesSide') {
      el = el.parentNode;
    }
    return el;
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
      const existingResult = existingBox ? existingBox.querySelector('.tool-result') : null;
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
function isAtBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight <= 2; }
function lockScroll(el) { if (el) _scrollLocked.add(el); }
function unlockScroll(el) { if (el) _scrollLocked.delete(el); }
function shouldAutoScroll(el) { return _scrollLocked.has(el); }

/* ---- system prompt (editable, localStorage-cached; + optional skills block) ---- */
async function buildSystemPrompt(convMessages) {
  // The system prompt is an editable value cached in localStorage (Settings →
  // System prompt) — NOT a synced or browsable OPFS file. Falls back to the
  // default if the system-prompt module hasn't loaded yet.
  let content = (typeof SandpieSystemPrompt !== 'undefined' && SandpieSystemPrompt.get)
    ? SandpieSystemPrompt.get()
    : (localStorage.getItem('sandpie-system-prompt') || 'You are a helpful assistant that reasons through the users requests step-by-step.');
  // Optional capability: context.js appends the skills block (enforced skill
  // index + an instruction telling the model to fetch a skill via the load_skill
  // tool when relevant). Module absent ⇒ plain memory prompt.
  if (typeof SandpieContext !== 'undefined' && SandpieContext.skillBlock) {
    try { content += await SandpieContext.skillBlock(convMessages); }
    catch (e) { console.warn('[sandpie] skills block failed:', e); }
  }
  return { role: 'system', content };
}

/* ---- "is any conversation generating right now" (backs Sandpie.isGenerating) ---- */
function anyStreamGenerating() {
  for (const s of convStreams.values()) if (s.generating) return true;
  return false;
}

/* ---- resume-on-refresh flight checkpointing (pairs with flightWrite/Read/Clear) ---- */
const SP_FLIGHT_KEY = (id) => 'sp-flight-' + id;
async function maybeResumeFlight(id) {
  if (!id) return;
  const ck = flightRead(id);
  if (!ck) return;
  if (Date.now() - ck.t > 5 * 60 * 1000) { flightClear(id); return; }
  let data;
  let path = convPath(id, true);
  try { data = JSON.parse(await opfs.read(path)); }
  catch {
    path = convPath(id, false);
    try { data = JSON.parse(await opfs.read(path)); } catch { flightClear(id); return; }
  }
  const s = ensureStream(id);
  hydrateStreamFromData(s, data);
  if (!s.messages.length || s.messages[s.messages.length - 1].role !== 'user') {
    flightClear(id); return;
  }
  mountConv(id);
  renderConversation(s.messages, s.compaction);
  addMsg('info', 'Resuming generation…', s.host);
  sendSingle(ck.text, s, { resume: true });
}

/* ---- message bubble context menu (rewind / copy / tools / thoughts) ---- */
let _bubbleMenuTarget = null;
function onBubbleContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  _bubbleMenuTarget = e.currentTarget;
  const menu = $('bubbleContextMenu');
  menu.style.display = '';
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
}
function hideBubbleMenu() {
  $('bubbleContextMenu').style.display = 'none';
  _bubbleMenuTarget = null;
}
async function rewindFromMenu() {
  const target = _bubbleMenuTarget;
  hideBubbleMenu();
  if (!target) return;

  if (!target._msg) {
    const s = activeStream();
    addMsg('info', 'Tool call still being drafted — hit Stop to cancel this round.', s && s.host);
    return;
  }
  const idx = messages.indexOf(target._msg);
  if (idx < 0) return;
  const after = messages.length - idx - 1;
  const msg = after === 0
    ? 'Remove this message?'
    : `Remove this message and ${after} message(s) after it?`;
  if (!confirm(msg)) return;

  const s = activeStream();
  if (s) {
    if (s.abort) { s.queueAborted = true; s.abort.abort(); }
    s.queue.length = 0;
    updateQueueCount(s);
  }
  messages.length = idx;
  // Rewinding into (or before) the compacted span invalidates the summary —
  // drop the compaction so the remaining (now short) history is sent in full.
  if (s && s.compaction && idx <= s.compaction.boundary) s.compaction = null;
  clearActiveConvUI();
  renderConversation(messages, s ? s.compaction : null);

  const messagesEl = $('messages');
  if (messagesEl && shouldAutoScroll(messagesEl)) messagesEl.scrollTop = messagesEl.scrollHeight;
  await saveActiveConv();
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
async function compactConversation(convId, { keepTail = 10, summary = '' } = {}) {
  if (!convId || convId !== activeConvId) return { ok: false, reason: 'not the active conversation' };
  const text = String(summary || '').trim();
  if (!text) return { ok: false, reason: 'empty summary' };
  const s = activeStream();
  const boundary = safeSplitIndex(messages, keepTail);
  const prevBoundary = (s && s.compaction && s.compaction.boundary) || 0;
  if (boundary <= prevBoundary || boundary >= messages.length) return { ok: false, reason: 'nothing new to compact' };
  // Non-destructive: keep the full history, just advance the boundary + summary.
  const compaction = { boundary, summary: text, at: new Date().toISOString() };
  if (s) s.compaction = compaction;
  await updateConvFile(convId, { compaction, compactions: undefined });
  // Re-render the whole conversation: pre-boundary span collapsed (not sent),
  // the rest in context.
  clearActiveConvUI();
  renderConversation(messages, compaction);
  const el = $('messages');
  if (el && shouldAutoScroll(el)) el.scrollTop = el.scrollHeight;
  await saveActiveConv();
  // The recorded usage still reflects the PRE-compaction (larger) context — drop
  // it so the context %-meters (and the compactor's own threshold) read the
  // reduced send size instead of a stale-high value that would re-trigger next send.
  try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.forget) SandpieTokens.forget(convId); } catch {}
  return { ok: true, removed: boundary, kept: messages.length - boundary };
}
async function copyFromMenu() {
  const target = _bubbleMenuTarget;
  hideBubbleMenu();
  if (!target) return;
  let text;

  const expanded = target.querySelector && target.querySelector('.tc-expanded');
  if (expanded && expanded.textContent) {
    text = expanded.textContent;
  } else if (target._msg && typeof target._msg.content === 'string') {
    text = target._msg.content;
  } else {
    text = target.innerText || target.textContent || '';
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {

    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch {}
    ta.remove();
  }
}

/* ---- side-by-side conversation panel ---- */
class SidePanel {
  constructor() {
    this.left = $('messages');
    this.right = $('messagesSide');
    this.wrap = $('messagesWrap');
    this._sideId = null;
    this._activeIsRight = false;
    this._render();
    this._wireEvents();
  }

  get isOpen() { return this._sideId !== null; }
  get sideId() { return this._sideId; }
  get activeIsRight() { return this._activeIsRight; }

  activeMountTarget() { return this._activeIsRight ? this.right : this.left; }

  async open(id) {
    if (!id) return;
    if (id === activeConvId) return;
    if (id === this._sideId) return;
    if (this._activeIsRight) return;

    closeArtifactPanel();

    if (this._sideId) {
      const prev = convStreams.get(this._sideId);
      prev?.host?.parentNode?.removeChild(prev.host);
    }
    await this._lazyLoad(id);
    this._sideId = id;
    const s = convStreams.get(id);
    if (s?.host) this.right.appendChild(s.host);
    this._render();

    requestAnimationFrame(() => { this.right.scrollTop = this.right.scrollHeight; });
    refreshConversationList();
  }
  close() {
    if (!this.isOpen) return;
    if (this._activeIsRight) this.flip();
    const s = convStreams.get(this._sideId);
    s?.host?.parentNode?.removeChild(s.host);
    this._sideId = null;
    this._activeIsRight = false;
    this._render();
    refreshConversationList();
  }
  flip() {
    if (!this.isOpen) return;

    [activeConvId, this._sideId] = [this._sideId, activeConvId];
    this._activeIsRight = !this._activeIsRight;
    if (activeConvId) localStorage.setItem('sandpie-active-conv', activeConvId);
    const s = convStreams.get(activeConvId);
    messages = s?.messages || [];
    this._render();
    refreshSendButtonForActive();
    refreshConversationList();
    if (typeof SandpieTokens !== 'undefined') SandpieTokens.notify();
  }

  notifyDeleted(id) {
    if (id === this._sideId) {
      this._sideId = null;
      this._activeIsRight = false;
      this._render();
    }
  }

  promoteSideToActive() {
    if (!this.isOpen) return false;
    const sId = this._sideId;
    const s = convStreams.get(sId);
    if (s && s.host) {

      if (s.host.parentNode) s.host.parentNode.removeChild(s.host);
      this.left.appendChild(s.host);
    }
    activeConvId = sId;
    messages = (s && s.messages) || [];
    if (activeConvId) localStorage.setItem('sandpie-active-conv', activeConvId);
    this._sideId = null;
    this._activeIsRight = false;
    this._render();
    refreshSendButtonForActive();
    return true;
  }

  async _lazyLoad(id) {
    if (convStreams.has(id)) return;
    let data;
    let path = convPath(id, true);
    try { data = JSON.parse(await opfs.read(path)); }
    catch {
      path = convPath(id, false);
      try { data = JSON.parse(await opfs.read(path)); }
      catch (e) { addMsg('err', 'Failed to load conv: ' + e.message); throw e; }
    }
    const s = ensureStream(id);
    s.messages = (data.messages || []).slice();
    for (const m of s.messages) renderHistoricalMessage(m, s.host);
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

  _wireEvents() {
    if (!this.wrap || !this.left || !this.right) return;

    const onPanelClick = (targetIsRight) => (ev) => {
      if (!this.isOpen) return;
      if (targetIsRight === this._activeIsRight) return;
      const sel = window.getSelection?.().toString();
      if (sel && sel.length > 0) return;
      if (ev.target.closest('.context-menu, button, a, input, textarea')) return;
      this.flip();
    };
    this.left.addEventListener('click',  onPanelClick(false));
    this.right.addEventListener('click', onPanelClick(true));

    this.wrap.addEventListener('dragover', (ev) => {
      if (!ev.dataTransfer?.types.includes('text/sandpie-conv-id')) return;
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'copy';
      this.wrap.classList.add('drop-target');
    });
    this.wrap.addEventListener('dragleave', (ev) => {
      if (ev.target === this.wrap) this.wrap.classList.remove('drop-target');
    });
    this.wrap.addEventListener('drop', (ev) => {
      this.wrap.classList.remove('drop-target');
      if (isMobileViewport()) return;
      const id = ev.dataTransfer?.getData('text/sandpie-conv-id');
      if (!id) return;
      ev.preventDefault();
      this.open(id);
    });
  }
}
let sidePanel = null;

/* =============================================================================
   Module boot — runs at deferred-module eval time (after the document is parsed
   but before DOMContentLoaded), so every #id these touch already exists.
   ============================================================================= */

(function setupInput() {
  const ta = $('input');
  if (!ta) return;
  function autosize() {
    const m = $('messages');
    ta.style.height = 'auto';
    const maxH = 12 * parseFloat(getComputedStyle(ta).lineHeight || '1.4');
    const newH = Math.min(ta.scrollHeight, maxH);
    ta.style.height = newH + 'px';
    ta.style.overflowY = ta.scrollHeight > maxH ? 'auto' : 'hidden';
    if (shouldAutoScroll(m)) m.scrollTop = m.scrollHeight;
  }
  ta.addEventListener('input', autosize);

  const searchInput = $('convSearch');
  if (searchInput) {
    searchInput.addEventListener('input', () => refreshConversationList());
  }
  function setupScrollTracking(el) {
    if (!el) return;
    lockScroll(el);
    el.addEventListener('scroll', () => { if (isAtBottom(el)) lockScroll(el); }, { passive: true });
    el.addEventListener('wheel', e => { if (e.deltaY < 0) unlockScroll(el); }, { passive: true });
    let _ty = 0;
    el.addEventListener('touchstart', e => { _ty = e.touches[0].clientY; }, { passive: true });
    el.addEventListener('touchmove', e => { if (e.touches[0].clientY > _ty) unlockScroll(el); }, { passive: true });
  }
  setupScrollTracking($('messages'));
  setupScrollTracking($('messagesSide'));
  ta.addEventListener('keydown', e => {
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
      handleSubmit();
    }
  });

  const observer = new MutationObserver(autosize);
  observer.observe(ta, { attributes: true, attributeFilter: ['value'] });

  ta.form?.addEventListener('submit', () => setTimeout(autosize, 0));
  autosize();
})();

sidePanel = new SidePanel();
window.sidePanel = sidePanel;

(function () {
  const resizer = $('sideResizer');
  const panel   = $('messagesSide');
  if (!resizer || !panel) return;
  resizer.addEventListener('mousedown', e => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panel.offsetWidth;
    panel.style.flex  = 'none';
    panel.style.width = startW + 'px';
    resizer.classList.add('dragging');
    document.body.style.cursor     = 'col-resize';
    document.body.style.userSelect = 'none';

    const frame = $('artifactPanelFrame');
    if (frame) frame.style.pointerEvents = 'none';
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
      const frame = $('artifactPanelFrame');
      if (frame) frame.style.pointerEvents = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  });
})();

let _localInferring = false;

(function() {
  const messages = document.getElementById('messages');
  if (!messages) return;
  const state = new Map();
  let animating = false;
  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }
  function updateTargets() {
    const parallaxMsgs = messages.querySelectorAll('.msg.user');
    const vh = window.innerHeight;
    const center = vh / 2;
    for (const msg of parallaxMsgs) {
      const rect = msg.getBoundingClientRect();
      const msgCenter = rect.top + rect.height / 2;
      const ny = (msgCenter - center) / (vh / 2);
      const target = clamp(ny, -0.6, 0.6);
      if (!state.has(msg)) {
        state.set(msg, { current: target, target: target });
      } else {
        state.get(msg).target = target;
      }
    }
  }
  function tick() {
    let moving = false;
    for (const [msg, s] of state) {

      const diff = s.target - s.current;
      if (Math.abs(diff) > 0.001) {
        s.current += diff * 0.12;
        moving = true;
      } else {
        s.current = s.target;
      }
      msg.style.setProperty('--py', s.current.toFixed(3));
    }
    if (moving) {
      requestAnimationFrame(tick);
    } else {
      animating = false;
    }
  }
  function onScroll() {
    if (_localInferring) return;
    updateTargets();
    if (!animating) {
      animating = true;
      requestAnimationFrame(tick);
    }
  }
  messages.addEventListener('scroll', onScroll, { passive: true });

  updateTargets();
  tick();
})();

document.addEventListener('click', hideBubbleMenu);

/* expose moved page-glue for inline handlers (HTML onclick) + the host contract */
window.maybeResumeFlight = maybeResumeFlight;
window.anyStreamGenerating = anyStreamGenerating;
window.rewindFromMenu = rewindFromMenu;
window.copyFromMenu = copyFromMenu;

/* expose on window for inline script compatibility */
window.ensureStream = ensureStream;
window.activeStream = activeStream;
window.flightWrite = flightWrite;
window.flightRead = flightRead;
window.flightClear = flightClear;
window.addMsg = addMsg;
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
window.SandpieConversations = { compact: compactConversation, getCompaction, safeSplitIndex };
window.renderHistoricalMessage = renderHistoricalMessage;
window.clearActiveConvUI = clearActiveConvUI;
window.parkActiveConv = parkActiveConv;
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
window.enqueueForActive = enqueueForActive;
window.handleButtonClick = handleButtonClick;
window.updateQueueCount = updateQueueCount;
window.processQueueFor = processQueueFor;
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
const TIMER_TICK_MS = 66;   // ~15fps: smooth token easing at trivial cost
const TOK_EASE = 0.2;       // fraction of the remaining gap the shown count closes per tick
const TOK_FMT = n => Math.round(n).toLocaleString('en-US');
const RATE_FMT = r => (r >= 10 ? String(Math.round(r)) : r.toFixed(1)) + ' tok/s';

// Generated-token bookkeeping for the live counter. Every backend (the local
// WebGPU engine AND the SW/API path) funnels its stream through sendSingle's
// `dispatch`, so counting here is universal. The local backend emits no `usage`
// events, so a chars/4 estimate — the same heuristic
// SandpieTokens.estimateTokens uses — is the only signal available; we use it
// for every backend so the readout behaves identically everywhere. genChars
// only grows, so tokTarget is monotonic. (Authoritative provider usage still
// flows to SandpieTokens/Context untouched — this counter is a live HUD, not a
// billing figure.)
function accountStreamTokens(stream, ev) {
  if (!stream || ev.type !== 'delta' || !ev.delta) return;
  const d = ev.delta;
  let n = 0;
  if (typeof d.content === 'string') n += d.content.length;
  if (typeof d.reasoning_content === 'string') n += d.reasoning_content.length;
  else if (typeof d.reasoning === 'string') n += d.reasoning.length;
  if (Array.isArray(d.tool_calls)) {
    for (const tc of d.tool_calls) {
      n += (tc.function?.arguments || '').length + (tc.function?.name || '').length;
    }
  }
  if (!n) return;
  stream.genChars += n;
  stream.tokTarget = Math.ceil(stream.genChars / 4);
}

function startTotalTimer(stream) {
  if (!stream || stream.timerEl) return;
  stream.timerStart = Date.now();
  stream.genChars = 0;
  stream.tokTarget = 0;
  stream.tokShown = 0;
  stream.rateShown = 0;

  const el = document.createElement('div');
  el.className = 'msg-timer';
  // Built once; the tick mutates the leaf <span>s in place rather than
  // re-rendering innerHTML ~15×/s (which would thrash layout and the queue pill).
  el.innerHTML =
    '<span class="mt-time">0s</span>' +
    '<span class="mt-sep">·</span><span class="mt-tok">0 tok</span>' +
    '<span class="mt-sep">·</span><span class="mt-rate">0 tok/s</span>' +
    '<span class="mt-queue"></span>';
  stream.host.appendChild(el);
  stream.timerEl = el;

  const timeEl = el.querySelector('.mt-time');
  const tokEl = el.querySelector('.mt-tok');
  const rateEl = el.querySelector('.mt-rate');
  const queueEl = el.querySelector('.mt-queue');
  const reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const set = (node, txt) => { if (node.textContent !== txt) node.textContent = txt; };

  const paint = () => {
    if (!stream.timerEl) return;
    const elapsed = (Date.now() - stream.timerStart) / 1000;
    set(timeEl, fmtElapsed(elapsed));

    // Total tokens — ease the shown value up toward the target so bursty API
    // chunks or fast local decode read as a smooth climb. Strictly monotonic:
    // never tick backward.
    const target = stream.tokTarget;
    if (reduce || target <= stream.tokShown) stream.tokShown = target;
    else stream.tokShown = Math.min(target, stream.tokShown + Math.max((target - stream.tokShown) * TOK_EASE, 1));
    set(tokEl, TOK_FMT(stream.tokShown) + ' tok');

    // tok/s — aggregate throughput over the interaction. The timer spans tool
    // execution too, so this honestly eases down while a tool runs.
    const inst = elapsed > 0.4 ? target / elapsed : 0;
    stream.rateShown = reduce ? inst : stream.rateShown + (inst - stream.rateShown) * TOK_EASE;
    set(rateEl, RATE_FMT(stream.rateShown));

    // Live CONTEXT meter: baseline + generated-so-far, pushed only for the
    // visible conversation (SandpieTokens throttles the panel re-render). Cleared
    // in sendSingle's finally → the panel snaps to the authoritative size.
    if (stream.id === activeConvId && typeof SandpieTokens !== 'undefined' && SandpieTokens.setLiveTokens) {
      SandpieTokens.setLiveTokens(stream.id, (stream.tokBaseline || 0) + target);
    }

    const q = stream.queue.length;
    if (queueEl.dataset.q !== String(q)) {
      queueEl.dataset.q = String(q);
      queueEl.className = q > 0 ? 'queue-pill' : 'mt-queue';
      queueEl.textContent = q > 0 ? `${q} queued` : '';
    }
  };

  paint();
  stream.timerInterval = setInterval(paint, TIMER_TICK_MS);
}

function endTotalTimer(stream, label) {
  if (!stream || !stream.timerEl) return;
  clearInterval(stream.timerInterval);
  stream.timerInterval = null;
  if (label === null) {
    stream.timerEl.remove();
  } else {
    const sec = (Date.now() - stream.timerStart) / 1000;
    const tok = stream.tokTarget || 0;
    const rate = sec > 0.05 ? tok / sec : 0;
    // Settled line: label · elapsed · tokens · rate, dimmed via .done. The token
    // pair is dropped on a pure-tool round (no text generated) — "0 tok · 0 tok/s"
    // is noise.
    const parts = [
      `<span class="mt-label">${label}</span>`,
      `<span class="mt-sep">·</span><span class="mt-time">${fmtElapsed(sec, true)}</span>`,
    ];
    if (tok > 0) {
      parts.push(`<span class="mt-sep">·</span><span class="mt-tok">${TOK_FMT(tok)} tok</span>`);
      parts.push(`<span class="mt-sep">·</span><span class="mt-rate">${RATE_FMT(rate)}</span>`);
    }
    stream.timerEl.innerHTML = parts.join('');
    stream.timerEl.classList.add('done');
  }
  stream.timerEl = null;
}

/* expose timer globals for sandpie-test.html inline scripts */
window.startTotalTimer = startTotalTimer;
window.endTotalTimer = endTotalTimer;

/* =============================================================================
   Boot — render the conversation list and restore the last-open chat. Runs on
   DOMContentLoaded (NOT at module-eval) so artifacts.js has loaded before a
   restored message can call renderArtifact(). The saved theme is restored
   separately by themes.js.
   ============================================================================= */
function bootConversations() {
  (async () => {
    await refreshConversationList();
    if (activeConvId) {
      const restoreId = activeConvId;
      activeConvId = null;
      const s = ensureStream(restoreId);
      try {
        let path = convPath(restoreId, true);
        let data;
        try { data = JSON.parse(await opfs.read(path)); }
        catch {
          path = convPath(restoreId, false);
          data = JSON.parse(await opfs.read(path));
        }
        hydrateStreamFromData(s, data);
      } catch {  }
      mountConv(restoreId);
      renderConversation(s.messages, s.compaction);
    }
    const scrollEnd = () => { const m = $('messages'); m.scrollTop = m.scrollHeight; };
    requestAnimationFrame(() => requestAnimationFrame(scrollEnd));
    document.querySelectorAll('#messages img').forEach(img => {
      if (!img.complete) img.addEventListener('load', scrollEnd, { once: true });
    });
    window._sandpieBootDone = true;
  })();
  // Resume any in-flight generation after a tab refresh.
  setTimeout(() => { if (activeConvId) maybeResumeFlight(activeConvId); }, 300);
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
  updateQueueCount,
  processQueueFor,
  sendSingle,
  buildAgentConfig,
  readAgentEvents,
  dispatchAgentEvent
};
