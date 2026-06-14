const CONV_DIR = '_conversations';
function newConvId() {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}
function convPath(id) { return `${CONV_DIR}/${id}.json`; }
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

  let prev = {};
  try { prev = JSON.parse(await opfs.read(convPath(convId))); } catch {}
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
  await opfs.write(convPath(convId), JSON.stringify(data));
  Sandpie.events.emit('file:changed', convPath(convId));
  await refreshConversationList();
}
function renderHistoricalMessage(m, host = null) {
  if (m.role === 'user') {
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
    if (!content.startsWith('artifact:') && !content.startsWith('image:')) {
      const t = content;
      const display = t.length > 500 ? t.slice(0, 500) + '…' : t;

      const target = host || $('messages');
      const toolCalls = target.querySelectorAll('.msg.tool-call');
      if (toolCalls.length > 0) {
        appendToolResult(toolCalls[toolCalls.length - 1].dataset.tcId, display);
      }
    }

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
    try { data = JSON.parse(await opfs.read(convPath(id))); }
    catch (e) {
      if (activeConvId) mountConv(activeConvId);
      addMsg('err', 'Failed to load conversation: ' + e.message);
      return;
    }
    const s = ensureStream(id);
    s.messages = (data.messages || []).slice();
    mountConv(id);
    for (const m of s.messages) renderHistoricalMessage(m);
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
  try { entries = await opfs.listDir(CONV_DIR); } catch { return []; }

  const searchActive = !!($('convSearch')?.value.trim());

  const reads = entries
    .filter(e => e.kind === 'file' && e.name.endsWith('.json'))
    .map(async (e) => {
      const id = e.name.slice(0, -5);
      try {
        const data = JSON.parse(await opfs.read(convPath(id)));
        const row = {
          id: data.id || id,
          title: data.title || '(no title)',
          updated: data.updated || '',
          pinned: !!data.pinned,
          archived: !!data.archived,
        };
        if (searchActive) {
          const messages = data.messages || [];
          row.messageContent = messages.map(m => m.content || '').join(' ').toLowerCase();
        }
        return row;
      } catch { return null; }
    });
  const out = (await Promise.all(reads)).filter(Boolean);

  for (const c of out) {
    if (!convLastViewed.has(c.id)) convLastViewed.set(c.id, c.updated || '');
  }
  return out.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
}
function refreshNewChatButton() {
  const btn = $('newChatBtn');
  if (!btn) return;
  const empty = messages.length === 0;
  btn.disabled = empty;
  btn.title = empty ? "Already a fresh chat — just start typing below." : '';
}
let archivedExpanded = false;
async function updateConvFile(id, patch) {
  let data;
  try { data = JSON.parse(await opfs.read(convPath(id))); }
  catch { return; }
  Object.assign(data, patch);
  await opfs.write(convPath(id), JSON.stringify(data));
  Sandpie.events.emit('file:changed', convPath(id));
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
  await updateConvFile(id, { archived: !currentlyArchived });
  await refreshConversationList();
}
async function duplicateConv(id, title) {
  let data;
  try { data = JSON.parse(await opfs.read(convPath(id))); }
  catch (e) { addMsg('err', 'Failed to duplicate: ' + e.message); return; }
  const newId = newConvId();
  data.id = newId;
  data.title = (data.title || title || '(no title)') + ' (copy)';
  data.pinned = false;
  data.archived = false;
  data.updated = new Date().toISOString();
  await opfs.write(convPath(newId), JSON.stringify(data));
  Sandpie.events.emit('file:changed', convPath(newId));
  await refreshConversationList();
}
async function deleteConv(id, title) {
  const dbxNote = Sandpie.syncProvider()?.isConnected?.() ? ' This will also remove the cloud copy.' : '';
  if (!confirm(`Delete conversation "${title}"?${dbxNote}`)) return;
  const path = convPath(id);
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
  refreshNewChatButton();
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
      if (el.querySelector('.tc-check')) continue;
      el.classList.remove('in-flight');
      renderTcDone(el, el.dataset.fname);
    }
  }
  if (stream === activeStream()) refreshSendButtonForActive();

  refreshConversationList();
}
async function handleSubmit() {
  const text = $('input').value.trim();
  if (!text && !SandpieImages.hasImage()) return;
  SandpieAugmentations.showRelevance(text, activeConvId).catch(() => {});
  $('input').value = '';

  const content = await SandpieImages.buildContent(text);

  if (SandpieImages.hasImage()) {
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

  const s = stream || activeStream();
  if (!s || !s.timerEl) return;
  const sec = Math.floor((Date.now() - s.timerStart) / 1000);
  const queueBadge = s.queue.length > 0 ? ` <span class="queue-pill">${s.queue.length} queued</span>` : '';
  s.timerEl.innerHTML = `${sec}s${queueBadge}`;
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
const SW_STREAM_PATH = './sandpie-stream';
let _swReady = (async () => {
  if (!('serviceWorker' in navigator)) {
    throw new Error('Service workers not supported in this browser — sandpie needs them. Try Chrome, Edge, Firefox, or Safari on a recent version.');
  }

  const regs = await navigator.serviceWorker.getRegistrations();
  for (const r of regs) {
    const url = r.active?.scriptURL || r.installing?.scriptURL || r.waiting?.scriptURL || '';
    if (/\/sandpie-sw\.js$/.test(url)) {
      await r.unregister();
      console.log('[sandpie] unregistered stale SW:', url);
    }
  }

  const reg = await navigator.serviceWorker.register('./sandpie.js', { updateViaCache: 'none' });
  await navigator.serviceWorker.ready;

  // A page can load UNCONTROLLED — typically a hard reload of an already-active
  // SW: clients.claim() ran before this page existed, so it won't re-fire and
  // navigator.serviceWorker.controller stays null. An uncontrolled page can't have
  // /sandpie-agent intercepted, so sends would silently never dispatch. Wait
  // briefly for a claim; if none comes, reload ONCE (a normal reload of an active,
  // claiming SW attaches deterministically). A sessionStorage guard prevents any
  // reload loop — worst case we proceed uncontrolled rather than thrash or hang.
  if (!navigator.serviceWorker.controller) {
    await new Promise((resolve) => {
      if (navigator.serviceWorker.controller) return resolve();
      const done = () => { clearTimeout(t); navigator.serviceWorker.removeEventListener('controllerchange', done); resolve(); };
      navigator.serviceWorker.addEventListener('controllerchange', done);
      const t = setTimeout(done, 1500);
    });
    if (!navigator.serviceWorker.controller && !sessionStorage.getItem('sandpie-sw-reattach')) {
      sessionStorage.setItem('sandpie-sw-reattach', '1');
      console.warn('[sandpie] SW not controlling this page — reloading once to attach.');
      location.reload();
      await new Promise(() => {});   // halt this load; the reload supersedes it
    }
  } else {
    sessionStorage.removeItem('sandpie-sw-reattach');   // healthy controlled load → reset the guard
  }
  console.log('[sandpie] SW ready — controller:', navigator.serviceWorker.controller?.scriptURL);
  return reg;
})();
_swReady.catch(e => console.error('[sandpie] SW registration failed:', e));
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
  const _isWllama = !!(_active && _active.type === 'wllama');
  const _isTransformersJS = !!(_active && _active.type === 'transformersjs');
  const _isLiteRTLM = !!(_active && _active.type === 'litertlm');
  const _isLocal = _isWllama || _isTransformersJS || _isLiteRTLM;
  if (!$('endpoint').value || !$('model').value || (!_isLocal && !$('apiKey').value)) {
    addMsg('err',
      _isWllama ? 'Pick a wllama model in Settings before sending.' :
      _isTransformersJS ? 'Pick a Transformers.js model in Settings before sending.' :
      _isLiteRTLM ? 'Pick a LiteRT-LM (Gemma) model in Settings before sending.' :
      'Add a provider (endpoint, model, and API key) in Settings before sending.', host);
    return;
  }
  requestWakeLock();
  setStreamSending(stream, true);
  startTotalTimer(stream);
  flightWrite(convId, text);

  const config = await buildAgentConfig(convMessages);

  const ctrl = new AbortController();
  stream.requestId = ctrl;
  const onAbort = () => ctrl.abort();
  if (stream.abort?.signal) {
    if (stream.abort.signal.aborted) onAbort();
    else stream.abort.signal.addEventListener('abort', onAbort, { once: true });
  }

  const renderer = new RoundRenderer(host, convMessages);

  let agentDoneSeen = false;
  let errorSeen = false;
  let lastInFlightTool = null;
  const dispatch = (ev) => {
    if (ev.type === 'agent_done')  agentDoneSeen = true;
    if (ev.type === 'error')        errorSeen = true;
    if (ev.type === 'tool_started') {
      lastInFlightTool = ev.tc?.function?.name || 'unknown';
      try { const a = JSON.parse(ev.tc?.function?.arguments || '{}'); if (ev.tc?.function?.name === 'run_python' && a.path) SandpieAugmentations.getConvMeta(activeConvId).scripts.add(a.path); } catch (_) {}
    }
    if (ev.type === 'tool_result') {
      lastInFlightTool = null;
      try { const m = String(ev.result || '').match(/Created:\s*([^\s]+)/); if (m) SandpieAugmentations.getConvMeta(activeConvId).files.add(m[1]); } catch (_) {}
    }
    if (ev.type === 'usage') Sandpie.events.emit('tokens:record', {convId, usage: ev.usage});
    dispatchAgentEvent(ev, renderer, host);
  };
  try {

    if (_isWllama && typeof SandpieWllama !== 'undefined' && SandpieWllama.runConversation) {
      // Local model: run the agent loop on the PAGE (wllama's WASM model
      // can't be reached from the service worker). It emits the same event
      // protocol, so `dispatch` + the renderer + the lifecycle below are
      // reused unchanged.
      await SandpieWllama.runConversation(
        { provider: _active, messages: config.messages, systemPrompt: config.systemPrompt, tools: config.tools, convId, signal: ctrl.signal },
        dispatch,
      );
    } else if (_isTransformersJS && typeof SandpieTransformersJS !== 'undefined' && SandpieTransformersJS.runConversation) {
      // Local model via Transformers.js (ONNX + WebGPU).
      // Same page-side agent loop pattern as wllama.
      await SandpieTransformersJS.runConversation(
        { provider: _active, messages: config.messages, systemPrompt: config.systemPrompt, tools: config.tools, convId, signal: ctrl.signal },
        dispatch,
      );
    } else if (_isLiteRTLM && typeof SandpieLiteRTLM !== 'undefined' && SandpieLiteRTLM.runConversation) {
      // Local Gemma via Google AI Edge LiteRT-LM (WebGPU). Same page-side loop.
      await SandpieLiteRTLM.runConversation(
        { provider: _active, messages: config.messages, systemPrompt: config.systemPrompt, tools: config.tools, convId, signal: ctrl.signal },
        dispatch,
      );
    } else {
    await _swReady;
    const res = await fetch('./sandpie-agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
      signal: ctrl.signal,
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      addMsg('err', `Error: ${res.status}: ${errText.slice(0, 300)}`, host);
      return;
    }

    await readAgentEvents(res.body, dispatch);

    if (!agentDoneSeen && !wasAborted && !errorSeen) {
      const trigger = lastInFlightTool
        ? ` while running \`${lastInFlightTool}\``
        : '';
      addMsg('err',
        `Service worker died mid-stream${trigger} — typically a Pyodide WASM crash that terminates the whole SW thread. The browser will spawn a fresh SW (with a clean Pyodide) on your next message. If the same code keeps killing it, that input is the culprit; rewrite or skip it.`,
        host,
      );
    }
    }
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

    renderer.finalize();

    releaseWakeLock();
    endTotalTimer(stream, wasAborted ? 'stopped' : 'done');
    setStreamSending(stream, false);
    await saveConv(convId);

    // Optional capability: notifications.js (if loaded) listens for this and
    // fires a system toast. No listener ⇒ no-op. saveConv ran first so the
    // listener can read the canonical (possibly renamed) conv title.
    Sandpie.events.emit('generation:complete', { convId, aborted: wasAborted });
    try { await Sandpie.sync(); } catch (e) { console.warn('sync failed:', e); }
  }
}
async function buildAgentConfig(convMessages) {
  const endpoint = $('endpoint').value.replace(/\/$/, '');
  const url = new URL(api(endpoint + '/chat/completions'), location.href).href;
  const resolvedMessages = [];
  for (const msg of convMessages) {
    if (msg.role === 'user' && Array.isArray(msg.content)) {
      const resolvedContent = [];
      for (const part of msg.content) {
        if (part.type === 'image_url' && part.image_url.url.startsWith('opfs://')) {
          const dataUrl = await SandpieImages.dataUrlFromPath(part.image_url.url.slice(7));
          if (dataUrl) {
            resolvedContent.push({ type: 'image_url', image_url: { url: dataUrl } });
          }
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
      timerEl: null, timerStart: 0, timerInterval: null,
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
    expanded.textContent = text;
    const collapsed = document.createElement('span');
    collapsed.className = 'tc-collapsed';
    div.appendChild(expanded);
    div.appendChild(collapsed);
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

function appendToolResult(tcId, result) {
  const toolCalls = document.querySelectorAll('.msg.tool-call');
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
  box.innerHTML = `<div class="tool-header">${tcEscape(name)}</div><div class="tool-code">${codeHtml}</div>`;
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
      '<span class="tc-meta"></span>';
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
      `<span class="tc-title">Using <b>${tcEscape(fname)}</b>…</span>`;
  }
}

function renderTcDone(div, fname) {
  const el = div && div.querySelector && div.querySelector('.tc-collapsed');
  if (!el) return;
  el.innerHTML =
    '<span class="tc-check">✓</span>' +
    `<span class="tc-title tc-dim">${tcEscape(fname || 'tool')}</span>`;
}

class RoundRenderer {
  constructor(host, convMessages) {
    this.host = host;
    this.convMessages = convMessages;

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
      if (path) {
        SandpieImages.dataUrlFromPath(path).then(dataUrl => {
          if (dataUrl) {
            SandpieImages.setState({ dataUrl, file: { name: path.split('/').pop() }, opfsPath: path });
            const preview = $('imagePreview');
            preview.innerHTML = '<img src="' + dataUrl + '"><button type="button" class="remove-btn" onclick="SandpieImages.clear()" title="Remove">✕</button>';
            preview.style.display = '';
          }
        });
      }
      return;
    }
    const display = text.length > 500 ? text.slice(0, 500) + '…' : text;
    if (idx >= 0 && this.toolCallEls[idx]) {
      appendToolResult(tcId, display);
    }
  }
  finalize() {

    if (this.drainTimer) { clearTimeout(this.drainTimer); this.drainTimer = null; }
    this.toolsShouldClose = true;
    this._flushAllPending();
    this._finishThinking();
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
    det.open = true;
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
      const n = Math.max(1, Math.ceil(this.pending.length / 30));
      this.displayed += this.pending.slice(0, n);
      this.pending = this.pending.slice(n);
      this._paintContent();
      if (this.pending.length > 0) anyPending = true;
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

    if (scrollHost && stick) scrollHost.scrollTop = scrollHost.scrollHeight;
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
const renderMd = text => {
  if (typeof DOMPurify === 'undefined' || typeof marked === 'undefined') {
    // Defer rendering until libraries are loaded
    return '&lt;div class="pending"&gt;Loading...&lt;/div&gt;';
  }
  return DOMPurify.sanitize(dedentPreBlocks(marked.parse(text)));
};

/* ---- scroll tracking (auto-stick to bottom unless the user scrolls up) ---- */
const _scrollLocked = new Set();
function isAtBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight <= 2; }
function lockScroll(el) { if (el) _scrollLocked.add(el); }
function unlockScroll(el) { if (el) _scrollLocked.delete(el); }
function shouldAutoScroll(el) { return _scrollLocked.has(el); }

/* ---- tool-call visibility toggle ---- */
let toolsMinimized = localStorage.getItem('sandpie-tools-minimized') !== '0';
function applyToolsMinimized() {

  document.body.classList.toggle('tools-minimized', toolsMinimized);
}

/* ---- system prompt (OPFS sandpie_memory.md + optional skills block) ---- */
async function buildSystemPrompt(convMessages) {
  let content;
  try {
    content = await opfs.read('sandpie_memory.md');
  } catch (e) {
    content = 'You are a helpful assistant that reasons through the users requests step-by-step.';
    await opfs.write('sandpie_memory.md', content);
  }
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
  try { data = JSON.parse(await opfs.read(convPath(id))); } catch { flightClear(id); return; }
  const s = ensureStream(id);
  s.messages = (data.messages || []).slice();
  if (!s.messages.length || s.messages[s.messages.length - 1].role !== 'user') {
    flightClear(id); return;
  }
  mountConv(id);
  for (const m of s.messages) renderHistoricalMessage(m);
  addMsg('info', 'Resuming generation…', s.host);
  sendSingle(ck.text, s, { resume: true });
}

/* ---- message bubble context menu (rewind / copy / tools / thoughts) ---- */
let _bubbleMenuTarget = null;
function onBubbleContextMenu(e) {
  e.preventDefault();
  e.stopPropagation();
  _bubbleMenuTarget = e.currentTarget;
  updateThoughtsMenuLabel();
  $('bubbleToggleToolsItem').textContent = toolsMinimized ? 'Show tool calls' : 'Hide tool calls';
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
  clearActiveConvUI();
  for (const m of messages) renderHistoricalMessage(m);

  const messagesEl = $('messages');
  if (messagesEl && shouldAutoScroll(messagesEl)) messagesEl.scrollTop = messagesEl.scrollHeight;
  await saveActiveConv();
}
/* ---- conversation compaction (compress older turns into a summary) -------
   Replace messages[0..split) with ONE user-role summary message, keeping the
   most recent `keepTail` messages verbatim, so the live context stays bounded
   and a chat can run indefinitely. The replaced span is stored as a restore
   point INSIDE the conversation file (data.compactions) — never a sidecar file
   (listConversations() treats every *.json in _conversations/ as a chat, so a
   sidecar would show up as a phantom conversation; in-file also means it
   deletes/archives/syncs with the conversation, leaving no orphans). Mutates
   `messages` IN PLACE so it stays the same array reference as the active
   stream's s.messages (see mountConv) — the same way rewindFromMenu persists. */
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
async function compactConversation(convId, { keepTail = 10, summary = '' } = {}) {
  if (!convId || convId !== activeConvId) return { ok: false, reason: 'not the active conversation' };
  const text = String(summary || '').trim();
  if (!text) return { ok: false, reason: 'empty summary' };
  const split = safeSplitIndex(messages, keepTail);
  if (split <= 1 || split >= messages.length) return { ok: false, reason: 'nothing safe to compact' };
  const removed = messages.slice(0, split).map(m => ({ ...m }));
  const summaryMsg = { role: 'user', content: SP_SUMMARY_MARKER + '\n\n' + text };
  // 1) persist the restore point first (file still holds the pre-compaction messages)
  let prev = {};
  try { prev = JSON.parse(await opfs.read(convPath(convId))); } catch {}
  const compactions = Array.isArray(prev.compactions) ? prev.compactions : [];
  compactions.push({ at: new Date().toISOString(), count: split, removed });
  while (compactions.length > 20) compactions.shift();   // bound file growth
  await updateConvFile(convId, { compactions });
  // 2) rewrite the live array IN PLACE (keeps the s.messages reference)
  messages.splice(0, split, summaryMsg);
  // 3) re-render exactly like rewind
  clearActiveConvUI();
  for (const m of messages) renderHistoricalMessage(m);
  const el = $('messages');
  if (el && shouldAutoScroll(el)) el.scrollTop = el.scrollHeight;
  // 4) persist the compacted messages (saveConv keeps `compactions` via ...prev)
  await saveActiveConv();
  return { ok: true, removed: split, kept: messages.length };
}
async function restoreLastCompaction(convId) {
  if (!convId || convId !== activeConvId) return { ok: false, reason: 'not the active conversation' };
  let data = {};
  try { data = JSON.parse(await opfs.read(convPath(convId))); } catch { return { ok: false }; }
  const comps = Array.isArray(data.compactions) ? data.compactions.slice() : [];
  const last = comps.pop();
  if (!last || !Array.isArray(last.removed)) return { ok: false, reason: 'no restore point' };
  const head = (messages[0] && typeof messages[0].content === 'string' && messages[0].content.startsWith(SP_SUMMARY_MARKER)) ? 1 : 0;
  messages.splice(0, head, ...last.removed);
  await updateConvFile(convId, { compactions: comps });
  clearActiveConvUI();
  for (const m of messages) renderHistoricalMessage(m);
  await saveActiveConv();
  return { ok: true, restored: last.removed.length };
}
function toggleToolsMinimizedFromMenu() {
  toolsMinimized = !toolsMinimized;
  localStorage.setItem('sandpie-tools-minimized', toolsMinimized ? '1' : '0');
  applyToolsMinimized();
  hideBubbleMenu();
}
let thoughtsVisible = true;
function toggleThoughtsFromMenu() {
  thoughtsVisible = !thoughtsVisible;
  var el = document.getElementById('bubbleToggleThoughtsItem');
  if (el) el.textContent = thoughtsVisible ? 'Hide thoughts' : 'Show thoughts';
  document.querySelectorAll('.msg.think').forEach(function(t) {
    t[thoughtsVisible ? 'removeAttribute' : 'setAttribute']('data-collapsed', '');
  });
}
function updateThoughtsMenuLabel() {
  var el = document.getElementById('bubbleToggleThoughtsItem');
  if (!el) return;
  var total = document.querySelectorAll('.msg.think').length;
  if (!total) { el.textContent = 'Show thoughts'; thoughtsVisible = true; return; }
  var open = document.querySelectorAll('.msg.think:not([data-collapsed])').length;
  el.textContent = (open === total) ? 'Hide thoughts' : 'Show thoughts';
  thoughtsVisible = (open === total);
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
    try { data = JSON.parse(await opfs.read(convPath(id))); }
    catch (e) { addMsg('err', 'Failed to load conv: ' + e.message); throw e; }
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
applyToolsMinimized();

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
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
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
window.toggleToolsMinimizedFromMenu = toggleToolsMinimizedFromMenu;
window.toggleThoughtsFromMenu = toggleThoughtsFromMenu;

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
window.SandpieConversations = { compact: compactConversation, restoreLast: restoreLastCompaction, safeSplitIndex };
window.renderHistoricalMessage = renderHistoricalMessage;
window.clearActiveConvUI = clearActiveConvUI;
window.parkActiveConv = parkActiveConv;
window.mountConv = mountConv;
window.loadConv = loadConv;
window.newConversation = newConversation;
window.listConversations = listConversations;
window.refreshNewChatButton = refreshNewChatButton;
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
function startTotalTimer(stream) {
  if (!stream || stream.timerEl) return;
  stream.timerStart = Date.now();
  const el = document.createElement('div');
  el.className = 'msg-timer';
  el.innerHTML = '0s' + (stream.queue.length > 0 ? ` <span class="queue-pill">${stream.queue.length} queued</span>` : '');
  stream.host.appendChild(el);
  stream.timerEl = el;
  stream.timerInterval = setInterval(() => {
    if (!stream.timerEl) return;
    const sec = Math.floor((Date.now() - stream.timerStart) / 1000);
    const queueBadge = stream.queue.length > 0 ? ` <span class="queue-pill">${stream.queue.length} queued</span>` : '';
    stream.timerEl.innerHTML = `${sec}s${queueBadge}`;
  }, 1000);
}

function endTotalTimer(stream, label) {
  if (!stream || !stream.timerEl) return;
  clearInterval(stream.timerInterval);
  stream.timerInterval = null;
  if (label === null) {
    stream.timerEl.remove();
  } else {
    const sec = (Date.now() - stream.timerStart) / 1000;
    const fmt = sec >= 10 ? `${Math.round(sec)}s` : `${sec.toFixed(1)}s`;
    stream.timerEl.textContent = `${label} · ${fmt}`;
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
        const data = JSON.parse(await opfs.read(convPath(restoreId)));
        s.messages = (data.messages || []).slice();
      } catch {  }
      mountConv(restoreId);
      for (const m of s.messages) renderHistoricalMessage(m);
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
  refreshNewChatButton,
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
