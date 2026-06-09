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

    s.queueAborted = true;
    if (s.abort) s.abort.abort();
    s.queue.length = 0;
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
      if (stream.queueAborted) break;
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

  let reg = await navigator.serviceWorker.register('./sandpie.js', { updateViaCache: 'none' });
  await navigator.serviceWorker.ready;

  if (!navigator.serviceWorker.controller) {
    console.log('[sandpie] no controller after .ready — forcing fresh install to attach.');
    await reg.unregister();
    reg = await navigator.serviceWorker.register('./sandpie.js', { updateViaCache: 'none' });
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise(resolve => {
        navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true });
      });
    }
  }
  console.log('[sandpie] SW ready — controller:', navigator.serviceWorker.controller?.scriptURL);
  return reg;
})();
_swReady.catch(e => console.error('[sandpie] SW registration failed:', e));
async function sendSingle(text, stream, opts = {}) {

  if (!$('endpoint').value || !$('model').value || !$('apiKey').value) {
    addMsg('err', 'Fill in endpoint, model, and API key.', stream && stream.host);
    return;
  }
  const { id: convId, messages: convMessages, host } = stream;

  let wasAborted = false;
  if (!opts?.resume) {
    const userMsg = { role: 'user', content: text };
    convMessages.push(userMsg);
    bindBubble(addMsg('user', text, host), userMsg);
    saveConv(convId).catch(() => {});
  }
  requestWakeLock();
  setStreamSending(stream, true);
  startTotalTimer(stream);
  flightWrite(convId, text);

  const config = await buildAgentConfig(convMessages);

  await _swReady;
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
      try { const a = JSON.parse(ev.tc?.function?.arguments || '{}'); if (ev.tc?.function?.name === 'run_python' && a.path) SandpieAugmentations.SandpieAugmentations.SandpieAugmentations.SandpieAugmentations.getConvMeta(activeConvId).scripts.add(a.path); } catch (_) {}
    }
    if (ev.type === 'tool_result') {
      lastInFlightTool = null;
      try { const m = String(ev.result || '').match(/Created:\s*([^\s]+)/); if (m) SandpieAugmentations.SandpieAugmentations.SandpieAugmentations.SandpieAugmentations.getConvMeta(activeConvId).files.add(m[1]); } catch (_) {}
    }
    if (ev.type === 'usage') Sandpie.events.emit('tokens:record', {convId, usage: ev.usage});
    dispatchAgentEvent(ev, renderer, host);
  };
  try {

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
    systemPrompt: await buildSystemPrompt(),
    messages: resolvedMessages,
    tools: toolDefs(),
    maxTokens: (active && active.maxTokens) || 8192,
    temperature: (active && active.temperature != null) ? active.temperature : null,
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

/* ---- expose to window for inline handlers / legacy code ---- */
window.newConvId = newConvId;
window.convPath = convPath;
window.ensureActiveConv = ensureActiveConv;
window.saveActiveConv = saveActiveConv;
window.saveConv = saveConv;
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
