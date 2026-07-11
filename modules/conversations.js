import { streamDiff } from './streamdiff.js';
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

// Unified loader → { id, title, updated, pinned, archived, compaction, todos,
// usage, messages, _format } or null. Callers don't care about on-disk format.
async function readConvData(id) {
  const loc = await convLocation(id);
  if (loc.format === 'new') {
    let meta = {}; try { meta = JSON.parse(await opfs.read(metaPath(id, loc.archived))); } catch {}
    let messages = []; try { messages = _parseJsonl(await opfs.read(jsonlPath(id, loc.archived))); } catch {}
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

// Lightweight list row. New format → read only the tiny meta file. Legacy → read
// the whole .json (unavoidable until it migrates). Message text for search is only
// pulled when a query is active.
async function readConvMetaRow(id, archived, format, wantSearch) {
  try {
    if (format === 'new') {
      const meta = JSON.parse(await opfs.read(metaPath(id, archived)));
      const row = { id: meta.id || id, title: meta.title || '(no title)', updated: meta.updated || '', pinned: !!meta.pinned, archived };
      if (wantSearch) { try { row.messageContent = _parseJsonl(await opfs.read(jsonlPath(id, archived))).map(m => _convText(m.content)).join(' ').toLowerCase(); } catch {} }
      return row;
    }
    const data = JSON.parse(await opfs.read(convPath(id, archived)));
    const row = { id: data.id || id, title: data.title || '(no title)', updated: data.updated || '', pinned: !!data.pinned, archived };
    if (wantSearch) row.messageContent = (data.messages || []).map(m => _convText(m.content)).join(' ').toLowerCase();
    return row;
  } catch { return null; }
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
async function saveConv(convId, { touchUpdated = true } = {}) {
  if (!convId) return;
  const s = convStreams.get(convId);
  const msgs = s ? s.messages : (convId === activeConvId ? messages : null);
  if (!msgs || !msgs.length) return;

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
  if (prevMeta && prevMeta.usage) meta.usage = prevMeta.usage;

  const metaStr = JSON.stringify(meta);
  if (metaStr !== prevMetaRaw) {
    await opfs.write(metaPath(convId, archived), metaStr);
    Sandpie.events.emit('file:changed', metaPath(convId, archived));
  }

  await refreshConversationList();
  // Distill lessons only on a turn-end save (touchUpdated:true) — never on the
  // ~1.2s mid-turn tick, which would snapshot a half-finished turn. The distiller
  // itself is cursor-gated so it re-runs each turn over only the NEW activity.
  if (touchUpdated && typeof SandpieAugmentations !== 'undefined') SandpieAugmentations.distillLessons(convId).catch(() => {});
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
    if (tcId) {
      if (content.startsWith('image:')) {
        const path = content.slice('image:'.length);
        if (path) appendToolResultImage(tcId, path, target);
      } else if (content.startsWith('todos:')) {
        const nl = content.indexOf('\n');
        const json = content.slice('todos:'.length, nl < 0 ? undefined : nl);
        let todos = null;
        try { todos = JSON.parse(json); } catch (_) {}
        const box = _toolBoxEl(tcId, target);
        if (todos) {
          if (box) { renderTodos(tcId, todos, target); }
          else { target.appendChild(buildTodosView(todos)); }
        }
      } else if (!content.startsWith('artifact:')) {
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
function renderConversation(msgs, compaction, host = null) {
  const comp = (compaction && compaction.boundary > 0 && compaction.boundary < msgs.length) ? compaction : null;
  if (!comp) { for (const m of msgs) renderHistoricalMessage(m, host); }
  else { renderCompactionBlock(comp, msgs, host); for (let i = comp.boundary; i < msgs.length; i++) renderHistoricalMessage(msgs[i], host); }
  // If the stream carries saved todos that never attached to a tool-call box
  // (orphaned by tcId mismatch on replay), append them as a standalone card.
  // Resolve the stream from the conversation being RENDERED (its host carries
  // dataset.convId), not activeStream() — otherwise rendering a non-active conv
  // (side panel, or mid-switch) staples the active conv's checklist onto it.
  const target = host || (activeStream() && activeStream().host) || $('messages');
  const s = convStreams.get(target && target.dataset && target.dataset.convId) || activeStream();
  if (s && s.todos && s.todos.length) {
    const hasTodos = !!(target && target.querySelector('.tool-todos'));
    if (!hasTodos) target.appendChild(buildTodosView(s.todos));
  }
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
  s.todos = data.todos || null;
  // Messages loaded from the new JSONL are already persisted; those from a legacy
  // .json are NOT in a .jsonl yet (persistedCount 0 → first save migrates them).
  s.persistedCount = (data && data._format === 'new') ? s.messages.length : 0;
  s._forceJsonlRewrite = false;
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
/* ---- harness-reminder note visibility (drift / no-plan / stop guard) ----- */
// The agentic loop emits `reminder` events when its guards fire. They are never
// stored or sent; this just controls whether they're drawn in the transcript.
// Hidden by default (debug-only); toggle with the `>>> drift` command.
function _reminderNotesVisible() {
  try { return localStorage.getItem('sandpie-show-reminders') === '1'; } catch (_) { return false; }
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
        if (s.abort) { s.queueAborted = true; s.abort.abort(); }
        s.queue.length = 0;
        updateQueueCount(s);
      }
      messages.length = idx;
      if (s && s.compaction && idx <= s.compaction.boundary) s.compaction = null;
      clearActiveConvUI();
      renderConversation(messages, s ? s.compaction : null);

      const messagesEl = $('messages');
      if (messagesEl && shouldAutoScroll(messagesEl)) messagesEl.scrollTop = messagesEl.scrollHeight;
      saveActiveConv().catch(() => {});

      if (rewindTexts.length) {
        const ta = $('input');
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
registerMetacogCommand();

async function loadConv(id) {
  if (id === activeConvId) return;

  if (sidePanel?.isOpen && id === sidePanel.sideId) { sidePanel.flip(); return; }

  await saveActiveConv();
  parkActiveConv();
  if (convStreams.has(id)) {
    mountConv(id);
  } else {
    const data = await readConvData(id);
    if (!data) {
      if (activeConvId) mountConv(activeConvId);
      addMsg('err', 'Failed to load conversation.');
      return;
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
  const searchActive = !!($('convSearch')?.value.trim());

  // Scan both dirs, collecting one entry per conversation id. A conv may have a new
  // meta file AND a legacy .json (kept as a backup); prefer the new format. Skip
  // .jsonl (reached via its meta) and classify .meta.json BEFORE plain .json (since
  // ".meta.json" also ends with ".json"). The list reads only the tiny meta files
  // for migrated convs — no more parsing every conversation in full.
  const found = new Map();   // id -> { archived, format }
  for (const [dir, archived] of [[CONV_DIR, false], [ARCHIVED_DIR, true]]) {
    let entries = [];
    try { entries = await opfs.listDir(dir); } catch { /* empty */ }
    for (const e of entries) {
      if (e.kind !== 'file') continue;
      let id = null, format = null;
      if (e.name.endsWith(META_SUFFIX)) { id = e.name.slice(0, -META_SUFFIX.length); format = 'new'; }
      else if (e.name.endsWith('.json')) { id = e.name.slice(0, -5); format = 'old'; }
      else continue;
      const prev = found.get(id);
      if (!prev || (prev.format === 'old' && format === 'new')) found.set(id, { archived, format });
    }
  }

  const rows = await Promise.all(
    [...found.entries()].map(([id, loc]) => readConvMetaRow(id, loc.archived, loc.format, searchActive)),
  );
  const out = rows.filter(Boolean);

  for (const c of out) {
    if (!convLastViewed.has(c.id)) convLastViewed.set(c.id, c.updated || '');
  }
  return out.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
}
let archivedExpanded = false;
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
    return;
  }
  if (loc.format === 'old') {
    const p = convPath(id, loc.archived);
    let data; try { data = JSON.parse(await opfs.read(p)); } catch { return; }
    Object.assign(data, patch);
    await opfs.write(p, JSON.stringify(data));
    Sandpie.events.emit('file:changed', p);
  }
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
  // Archive is a folder move. Relocate every file that exists for this conv (new
  // meta + jsonl, and/or a legacy .json backup) from one dir to the other, patching
  // the archived/pinned flags inside the JSON-shaped ones. Not data loss — a move.
  const from = currentlyArchived, to = !currentlyArchived;
  const pairs = [
    [metaPath(id, from), metaPath(id, to)],
    [jsonlPath(id, from), jsonlPath(id, to)],
    [convPath(id, from), convPath(id, to)],
  ];
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
    title: (data.title || title || '(no title)') + ' (copy)',
    created: now, updated: now, pinned: false,
    msgCount: (data.messages || []).length,
  };
  if (data.compaction) meta.compaction = data.compaction;
  if (data.todos) meta.todos = data.todos;
  const mp = metaPath(newId, false);
  await opfs.write(mp, JSON.stringify(meta));
  Sandpie.events.emit('file:changed', mp);
  await refreshConversationList();
}
async function deleteConv(id, title) {
  const dbxNote = Sandpie.syncProvider()?.isConnected?.() ? ' This will also remove the cloud copy.' : '';
  if (!confirm(`Delete conversation "${title}"?${dbxNote}`)) return;
  // Explicit user delete removes EVERY file for this id in both dirs — the new pair
  // AND any legacy .json backup. Leaving the .json behind would resurrect the conv
  // on the next list scan. (This is the one place old files are intentionally
  // removed; migration never does.)
  for (const archived of [false, true]) {
    for (const p of [metaPath(id, archived), jsonlPath(id, archived), convPath(id, archived)]) {
      try { if (await opfs.exists(p)) { await opfs.remove(p); Sandpie.events.emit('file:deleted', p); } } catch {}
    }
  }

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
  if (sidePanel?.isOpen && c.id === sidePanel.sideId) li.classList.add('in-panel');
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
  if (typeof SandpieCommands !== 'undefined' && text.startsWith('>>>')) {
    const handled = await SandpieCommands.dispatch(text);
    if (handled) {
      $('input').value = '';
      return;
    }
    // >>> is reserved. If it's not a real command, reject and show help.
    const rest = text.slice(3).trim();
    const cmdName = rest.split(/\s+/)[0] || '???';
    if (SandpieCommandView) {
      SandpieCommandView.show('"' + cmdName + '" is not a command.', 'help');
      SandpieCommands.dispatch('>>> help');
    }
    $('input').value = '';
    return;
  }
  if (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.showRelevance) SandpieAugmentations.showRelevance(text, activeConvId).catch(() => {});
  // Clear command output on normal chat submit
  if (SandpieCommandView) SandpieCommandView.hide();
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
  // Steer instead of queue: if a turn is already streaming via the worker, inject
  // this message into the running agent loop rather than waiting for the turn to
  // finish. The worker splices it in at the next round boundary — a safe point
  // that can't orphan a tool result — and echoes it back as message_added, so
  // array ordering + persistence stay worker-authoritative (see RoundRenderer).
  if (s.generating && s.agentId && _canSteerActive()) {
    steerActive(s, content);
    return;
  }
  // No active worker turn (idle, or a local-model turn with no steer channel):
  // fall back to the queue, which sends immediately when idle.
  s.queue.push(content);
  updateQueueCount(s);
  processQueueFor(s);
}
// Local in-page engines (LiteRT-LM / WebGPU) run their own loop with no steer
// channel, so a mid-turn send there falls back to the queue.
function _canSteerActive() {
  try {
    const a = (typeof SandpieProviders !== 'undefined' && SandpieProviders.getActive) ? SandpieProviders.getActive() : null;
    return !a || (a.type !== 'litertlm' && a.type !== 'webgpu');
  } catch (_) { return true; }
}
function steerActive(s, content) {
  // Render a provisional bubble now for immediate feedback; the authoritative
  // array insert + persistence happen when the worker echoes it back as a
  // message_added event (RoundRenderer.bindMessage reconciles against this list).
  const el = addMsg('user', content, s.host);
  (s._pendingSteer = s._pendingSteer || []).push({ el, content, msg: null });
  try { getSandpieWorker().postMessage({ type: 'steer', id: s.agentId, content }); } catch (_) {}
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
    window.handleSubmit();
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

function openQueueModal(stream) {
  if (!stream || stream.queue.length === 0) return;
  const existing = document.getElementById('queueModal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'queueModal';
  modal.className = 'modal';
  modal.style.display = 'flex';

  const items = stream.queue.map((item, idx) => {
    const text = typeof item === 'string' ? item : (item.text || JSON.stringify(item).slice(0, 200));
    return `
      <div class="qm-item" data-idx="${idx}">
        <div class="qm-number">${idx + 1}</div>
        <div class="qm-text">${escapeHtml(text)}</div>
        <div class="qm-actions">
          <button type="button" class="ghost qm-edit" data-idx="${idx}" title="Edit">Edit</button>
          <button type="button" class="ghost qm-cancel" data-idx="${idx}" title="Cancel">Cancel</button>
        </div>
      </div>`;
  }).join('');

  modal.innerHTML =
    '<div class="modal-backdrop"></div>' +
    '<div class="modal-content" style="max-width:560px; width:90%; max-height:70vh; display:flex; flex-direction:column; padding:0; overflow:hidden;">' +
      '<div style="display:flex; align-items:center; justify-content:space-between; padding:0.85rem 1.05rem; border-bottom:1px solid var(--sp-border);">' +
        '<h3 style="margin:0; font-size:1rem;">Queued Messages (' + stream.queue.length + ')</h3>' +
        '<button type="button" class="ghost qm-close" title="Close" style="font-size:1rem; line-height:1; padding:0.15rem 0.5rem;">&#215;</button>' +
      '</div>' +
      '<div style="flex:1; overflow-y:auto; padding:0.75rem 1rem;">' + items + '</div>' +
      '<div style="padding:0.75rem 1rem; border-top:1px solid var(--sp-border); display:flex; justify-content:flex-end; gap:0.5rem;">' +
        '<button type="button" class="ghost qm-clear">Clear All</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  // Wire up click handlers (module-scoped; inline onclick can't reach them)
  modal.querySelector('.modal-backdrop').addEventListener('click', closeQueueModal);
  modal.querySelector('.qm-close').addEventListener('click', closeQueueModal);
  modal.querySelector('.qm-clear').addEventListener('click', () => clearQueue(stream.id));

  const escHandler = (e) => { if (e.key === 'Escape') closeQueueModal(); };
  document.addEventListener('keydown', escHandler);
  modal._escHandler = escHandler;

  modal.querySelectorAll('.qm-cancel').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = +e.currentTarget.dataset.idx;
      stream.queue.splice(idx, 1);
      updateQueueCount(stream);
      const item = e.currentTarget.closest('.qm-item');
      if (item) item.remove();
      // Re-index remaining items so subsequent cancels target the right array slot
      modal.querySelectorAll('.qm-item').forEach((el, newIdx) => {
        el.dataset.idx = String(newIdx);
        const num = el.querySelector('.qm-number');
        if (num) num.textContent = String(newIdx + 1);
        el.querySelectorAll('.qm-edit, .qm-cancel').forEach(b => b.dataset.idx = String(newIdx));
      });
      if (stream.queue.length === 0) closeQueueModal();
    });
  });

  modal.querySelectorAll('.qm-edit').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = +e.target.dataset.idx;
      enterQueueEditMode(stream, idx, e.target.closest('.qm-item'));
    });
  });
}

function closeQueueModal() {
  const m = document.getElementById('queueModal');
  if (!m) return;
  if (m._escHandler) document.removeEventListener('keydown', m._escHandler);
  m.remove();
}

function clearQueue(streamId) {
  const s = convStreams.get(streamId);
  if (!s) return;
  s.queue.length = 0;
  updateQueueCount(s);
  closeQueueModal();
}

function enterQueueEditMode(stream, idx, itemEl) {
  const current = stream.queue[idx];
  const text = typeof current === 'string' ? current : (current.text || '');

  itemEl.innerHTML =
    '<textarea class="qm-edit-textarea" style="width:100%; min-height:60px; background:var(--sp-bg); border:1px solid var(--sp-border); border-radius:5px; color:var(--sp-text); padding:0.5rem; font:inherit; resize:vertical;">' + escapeHtml(text) + '</textarea>' +
    '<div style="display:flex; gap:0.4rem; justify-content:flex-end; margin-top:0.4rem;">' +
      '<button type="button" class="ghost qm-save" data-idx="' + idx + '">Save</button>' +
      '<button type="button" class="ghost qm-cancel-edit" data-idx="' + idx + '">Cancel</button>' +
    '</div>';

  const ta = itemEl.querySelector('.qm-edit-textarea');
  ta.focus();

  itemEl.querySelector('.qm-save').addEventListener('click', () => {
    const newText = ta.value.trim();
    if (!newText) return;
    if (typeof current === 'string') {
      stream.queue[idx] = newText;
    } else {
      stream.queue[idx] = Object.assign({}, current, { text: newText });
    }
    openQueueModal(stream);
  });

  itemEl.querySelector('.qm-cancel-edit').addEventListener('click', () => {
    openQueueModal(stream);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
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
  _sandpieWorker = new Worker('./modules/sandpie-worker.js?v=51');
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

// Byte size of what will actually be sent (system prompt + resolved messages +
// tool defs), and the budget that keeps it under the upstream gateway's ~1 MB cap.
// Used to decide whether the compaction boundary needs advancing before a send.
const SEND_BYTE_BUDGET = 900 * 1024;
function _sentRequestBytes(config) {
  try { return new Blob([JSON.stringify(config.messages || []) + JSON.stringify(config.systemPrompt || '') + JSON.stringify(config.tools || [])]).size; }
  catch { try { return (JSON.stringify(config.messages || []) || '').length; } catch { return 0; } }
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
  flightWrite(convId, text);

  let config = await buildAgentConfig(convMessages, stream.compaction, stream.todos);
  // Reactive boundary correction. If the BUILT request is still over the gateway's
  // ~1 MB cap, the compaction boundary is behind where it should be — e.g. an older
  // chat whose mid-turn compactions never persisted a boundary, so buildAgentConfig
  // sliced from a stale point and loaded far more than the compacted tail. Advance
  // the boundary with a REAL compaction (summarize the aged span + persist it), then
  // rebuild so we send only [summary, …tail] — the content that's supposed to load,
  // not the whole history. Shrink the kept tail each pass until it fits or the
  // boundary can no longer advance. This permanently fixes an already-bloated chat
  // on its next send (the advanced boundary is saved).
  if (typeof SandpieCompactor !== 'undefined' && SandpieCompactor.isEnabled && SandpieCompactor.isEnabled()) {
    const base = SandpieCompactor.config();
    let keep = base.keepTail;
    for (let i = 0; i < 6 && _sentRequestBytes(config) > SEND_BYTE_BUDGET; i++) {
      const r = await _performCompaction(convId, { ...base, keepTail: keep });
      if (!r || !r.ok) break;                        // boundary can't advance further
      keep = Math.max(2, Math.floor(keep / 2));       // still too big → keep an even smaller tail next pass
      config = await buildAgentConfig(stream.messages, stream.compaction, stream.todos);
    }
  }

  const ctrl = new AbortController();
  stream.requestId = ctrl;
  const onAbort = () => ctrl.abort();
  if (stream.abort?.signal) {
    if (stream.abort.signal.aborted) onAbort();
    else stream.abort.signal.addEventListener('abort', onAbort, { once: true });
  }

  const renderer = new RoundRenderer(host, convMessages, _isLocal, convId);

  let agentDoneSeen = false;
  let errorSeen = false;
  let lastInFlightTool = null;
  const dispatch = (ev) => {
    if (ev.type === 'agent_done')  agentDoneSeen = true;
    if (ev.type === 'error')        errorSeen = true;
    // Worker mid-turn compaction uses the SAME spinner as pre-send compaction.
    if (ev.type === 'compaction_start') { showCompactionProgress(convId); return; }
    if (ev.type === 'compaction_end')   { hideCompactionProgress(convId); return; }
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
    if (ev.type === 'tool_result') {
      lastInFlightTool = null;
      if (typeof SandpieAugmentations !== 'undefined') SandpieAugmentations.logToolResult(activeConvId, ev.result);
    }
    if (ev.type === 'usage') {
      stream.lastUsage = ev.usage;   // authoritative counts → settled tok/s + ctx counter
      Sandpie.events.emit('tokens:record', {convId, usage: ev.usage});
      reportTurnUsage(convId, ev.usage, convMessages.length);
      // Round boundary: recordUsage just wrote the fresh reported size, so repaint
      // the live ctx counter now instead of waiting for the whole turn to end.
      if (stream.timerEl) _paintCtxCounter(stream.timerEl, convId);
    }
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
    stream.agentId = _agentId;   // steer target: enqueueForActive posts {type:'steer', id} here
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
    stream.agentId = null;   // no longer steerable once the loop has ended
    renderer.finalize();
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

    releaseWakeLock();
    endTotalTimer(stream, wasAborted ? 'stopped' : 'done');
    // Refresh the context readouts (sidebar week total + badge, and any open ctx
    // popup) now the provider has reported this turn's authoritative usage.
    try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.notify) SandpieTokens.notify(); } catch (_) {}
    setStreamSending(stream, false);
    flushIncrementalSave(convId);
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
async function buildAgentConfig(convMessages, compaction, curTodos) {
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
    // Managed (company sign-in) provider only: let the worker silently re-mint the
    // session token from the SSO cookie via /auth/token on a 401, so an expired JWT
    // never interrupts the user mid-generation. null for personal providers — a 401
    // there is a real bad-key error, not a refreshable session.
    authRefreshUrl: (active && active.managed) ? new URL('/auth/token', location.href).href : null,
    _hermesMode: !!(active && active.type === 'hermes'),
    model: $('model').value,
    systemPrompt: await buildSystemPrompt(convMessages),
    messages: resolvedMessages,
    tools: toolDefs(),
    maxTokens: (active && active.maxTokens) || 8192,
    temperature: (active && active.temperature != null) ? active.temperature : null,
    topP: (active && active.topP != null) ? active.topP : null,
    reasoningEffort: (active && active.reasoningEffort) || null,
    origin: location.origin,
    conversation_file_name: activeConvId,
    // Current checklist (task tree) so the worker can apply write_todos ops to it
    // instead of the model resending/overwriting the whole list.
    todos: Array.isArray(curTodos) ? curTodos : [],
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
        try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.contextWindow) window = SandpieTokens.contextWindow(); } catch (_) {}
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
function reportTurnUsage(convId, usage, turnIndex) {
  try {
    if (!convId || !usage || typeof usage.prompt_tokens !== 'number') return;
    const active = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    const details = usage.completion_tokens_details || {};
    const reasoning = details.reasoning_tokens != null ? details.reasoning_tokens
                    : (usage.reasoning_tokens != null ? usage.reasoning_tokens : undefined);
    const body = {
      conversation_id: convId,
      turn_index: turnIndex | 0,
      model: (typeof $ === 'function' && $('model')) ? $('model').value : (usage.model || null),
      provider_type: active ? (active.managed ? 'managed' : (active.type || 'personal')) : null,
      usage: {
        prompt_tokens: usage.prompt_tokens || 0,
        completion_tokens: usage.completion_tokens || 0,
        total_tokens: usage.total_tokens != null ? usage.total_tokens
                      : ((usage.prompt_tokens || 0) + (usage.completion_tokens || 0)),
        reasoning_tokens: reasoning,
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
    case 'reminder': {
      // A harness-injected guard fired (drift nudge / stop-with-open-todos /
      // give-up). Shown so the mechanism is observable while debugging, but NOT
      // pushed into convMessages — it is never persisted or resent (addMsg only
      // touches the DOM). Prefixed so it's unmistakably a harness event.
      const _rl = { 'stop-block': 'stop guard', 'stop-anyway': 'stop guard (gave up)', 'drift': 'drift reminder', 'no-plan': 'no-plan reminder', 'grind': 'grind nudge', 'reuse': 'reuse-a-tool nudge', 'remember': 'remember nudge' };
      const label = _rl[ev.kind] || 'reminder';
      try { console.debug('[sandpie reminder]', ev.kind, ev.meta || '', ev.text); } catch (_) {}
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
      queue: [], isProcessing: false, queueAborted: false,
      abort: null,
      compaction: null,
      timerEl: null, timerStart: 0, timerInterval: null,
      lastUsage: null,
      generating: false,
      // JSONL persistence: how many messages are already on disk, and a flag that
      // forces a full rewrite (rewind/edit) instead of an append on the next save.
      persistedCount: 0, _forceJsonlRewrite: false,
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
  for (const div of root.querySelectorAll('.msg.tool-call')) {
    if (div.dataset.tcId === ref) return div;
  }
  return null;
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
  const list = document.createElement('div');
  list.className = 'tool-todos';
  const done = (todos || []).filter(t => t && t.status === 'completed').length;
  const head = document.createElement('div');
  head.className = 'tool-todos-head';
  head.textContent = `Checklist · ${done}/${(todos || []).length} done`;
  list.appendChild(head);
  for (const t of (todos || [])) {
    const st = (t && t.status) || 'pending';
    const row = document.createElement('div');
    row.className = 'tool-todo tool-todo-' + st;
    const depth = t && t.id ? (String(t.id).match(/\./g) || []).length : 0;   // subtask indent
    if (depth) row.style.marginLeft = (depth * 16) + 'px';
    const mark = document.createElement('span');
    mark.className = 'tool-todo-mark';
    mark.textContent = st === 'completed' ? '✓' : st === 'in_progress' ? '▸' : st === 'withdrawn' ? '⊘' : '○';
    const txt = document.createElement('span');
    txt.className = 'tool-todo-text';
    txt.textContent = (t && t.content) || '';
    row.append(mark, txt);
    list.appendChild(row);
  }
  box.appendChild(sep);
  box.appendChild(list);

  // Live timer badge: show current checklist progress in the active timer.
  const ip = (todos || []).findIndex(t => t && t.status === 'in_progress');
  const liveTimer = (scopeEl || document).querySelector('.msg-timer:not(.done)');
  if (liveTimer && todos && todos.length) {
    const badge = liveTimer.querySelector('.mt-todos');
    if (badge) {
      const cur = ip >= 0 ? ip + 1 : (todos || []).filter(t => t && t.status === 'completed').length;
      badge.textContent = cur + '/' + todos.length;
      badge.title = (todos[ip] && todos[ip].content) || 'Checklist';
      badge.onclick = () => {
        if (typeof SandpieCommandView !== 'undefined') SandpieCommandView.show(buildTodosView(todos), 'Checklist');
      };
    }
  }
}

// Build a checklist DOM element from a todos array.
function buildTodosView(todos) {
  const wrap = document.createElement('div');
  wrap.className = 'tool-todos';
  const head = document.createElement('div');
  head.className = 'tool-todos-head';
  const done = (todos || []).filter(t => t && t.status === 'completed').length;
  head.textContent = 'Checklist \u00b7 ' + done + '/' + todos.length + ' done';
  wrap.appendChild(head);
  for (const t of (todos || [])) {
    const st = (t && t.status) || 'pending';
    const row = document.createElement('div');
    row.className = 'tool-todo tool-todo-' + st;
    const depth = t && t.id ? (String(t.id).match(/\./g) || []).length : 0;
    if (depth) row.style.marginLeft = (depth * 16) + 'px';
    const mark = document.createElement('span');
    mark.className = 'tool-todo-mark';
    mark.textContent = st === 'completed' ? '\u2713' : st === 'in_progress' ? '\u25b8' : st === 'withdrawn' ? '\u2298' : '\u25cb';
    const txt = document.createElement('span');
    txt.className = 'tool-todo-text';
    txt.textContent = (t && t.content) || '';
    row.append(mark, txt);
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

function buildToolBox(args, toolName) {
  const name = toolName || 'tool';
  const box = document.createElement('div');
  box.className = 'tool-box';
  // write_todos renders the result as a checklist card; raw JSON is noise.
  if (name === 'write_todos') return box;

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
  // Tools whose result IS the point of the call render it inside the expanded box,
  // so show it by default (other tools stay collapsed behind the header toggle).
  // The user can still collapse it by clicking the header.
  //   load_image  → the loaded image
  //   write_todos → the checklist card (otherwise the user never sees the todos)
  if (fname === 'load_image' || fname === 'write_todos') div.classList.add('expanded');
}

class RoundRenderer {
  constructor(host, convMessages, isLocal = false, convId = null) {
    this.host = host;
    this.convMessages = convMessages;
    this.isLocal = isLocal;
    this.convId = convId;

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
    const nnEl = document.querySelector('.msg-timer:not(.done) .mt-nn');
    if (nnEl) nnEl.classList.remove('thinking');
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
    // Persist the just-committed round so a mid-turn crash can't lose it.
    scheduleIncrementalSave(this.convId);
    // A steered mid-turn user message the worker just spliced into its loop and
    // echoed back. Bind it to the provisional bubble steerActive() already put on
    // screen (FIFO), or render one if none is pending; mark it reconciled so the
    // finally-block cleanup won't re-add it.
    if (msg.role === 'user' && msg._steer) {
      const s = convStreams.get(this.convId);
      const pend = s && s._pendingSteer && s._pendingSteer.find(p => !p.msg);
      if (pend) { pend.msg = msg; bindBubble(pend.el, msg); }
      else bindBubble(addMsg('user', msg.content, this.host), msg);
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
    renderTcRunning(this.toolCallEls[idx], tc.function.name);
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
      renderTcDone(el, (idx >= 0 && this.toolCalls[idx] && this.toolCalls[idx].function.name) || el.dataset.fname);
    }
    const text = String(result || '');

    if (text.startsWith('artifact:')) {
      const path = text.slice('artifact:'.length);
      if (path) renderArtifact(this.host, path);
      return;
    }

    if (text.startsWith('image:')) {
      const path = text.slice('image:'.length);
      if (path && el) appendToolResultImage(el, path, this.host);
      return;
    }

    if (text.startsWith('todos:')) {
      const nl = text.indexOf('\n');
      const json = text.slice('todos:'.length, nl < 0 ? undefined : nl);
      let todos = null;
      try { todos = JSON.parse(json); } catch (_) {}
      if (todos) {
        // Attribute todos to the conversation that PRODUCED them (this renderer's
        // own conv), not whatever is active now — otherwise switching away as a
        // turn finishes (or background/side-panel generation) leaks the checklist
        // onto the active conversation.
        const s = convStreams.get(this.convId);
        if (s) s.todos = todos;
      }
      if (todos && el) renderTodos(el, todos, this.host);
      return;
    }
    // Show the full tool result — the user sees exactly what the model sees.
    if (el) appendToolResult(el, text, this.host);
  }
  finalize() {

    if (this.drainTimer) { clearTimeout(this.drainTimer); this.drainTimer = null; }
    this.toolsShouldClose = true;
    this._flushAllPending();
    this._finishThinking();
    // Full markdown render deferred from local inference — do it once now, then scroll
    if (this.isLocal && this.reply && this.displayed) {
      streamDiff(this.reply.querySelector('.bubble') || this.reply, renderMd(this.displayed));
    }
    if (this.isLocal) {
      const sh = this._scrollHost();
      if (sh && shouldAutoScroll(sh)) requestAnimationFrame(() => { sh.scrollTop = sh.scrollHeight; });
    }
  }

  _appendReasoning(chunk) {
    if (!this.thinkEl) this._createThinkBox();
    this.reasoning += chunk;
    if (this.thinkBody.textContent !== this.reasoning) this.thinkBody.textContent = this.reasoning;
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
    const nnEl = document.querySelector('.msg-timer:not(.done) .mt-nn');
    if (nnEl) nnEl.classList.remove('thinking');
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
      streamDiff(bubble, `<div>${this.displayed}</div>`);
      return;
    }
    streamDiff(this.reply.querySelector('.bubble') || this.reply, renderMd(this.displayed));
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
    // The box is created on the first delta that carries a name; the id can arrive
    // in a later delta. Keep dataset.tcId in sync so the tool_result (matched by
    // id) still finds this box instead of silently dropping the output.
    if (this.toolCalls[i].id && this.toolCallEls[i].dataset.tcId !== this.toolCalls[i].id) {
      this.toolCallEls[i].dataset.tcId = this.toolCalls[i].id;
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
function isAtBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight <= 2; }
function lockScroll(el) { if (el) _scrollLocked.add(el); }
function unlockScroll(el) { if (el) _scrollLocked.delete(el); }
function shouldAutoScroll(el) { return _scrollLocked.has(el); }

const NN_SVG_INLINE = '<svg viewBox="0 0 24 24" class="ripple"><circle cx="12" cy="12" r="1.2" class="r-c"/><circle cx="12" cy="12" r="4" class="r r1"/><circle cx="12" cy="12" r="7" class="r r2"/><circle cx="12" cy="12" r="10" class="r r3"/></svg>';

let thoughtsVisible = false;
function toggleThoughts() {
  thoughtsVisible = !thoughtsVisible;
  document.body.classList.toggle('thoughts-visible', thoughtsVisible);
  document.querySelectorAll('.msg-timer .mt-nn').forEach(el => {
    el.classList.toggle('on', thoughtsVisible);
    el.title = thoughtsVisible ? 'Hide thoughts' : 'Show thoughts';
  });
}

/* ---- system prompt (editable, localStorage-cached; + optional skills block) ---- */
async function buildSystemPrompt(convMessages) {
  // The system prompt is an editable value cached in localStorage (Settings →
  // System prompt) — NOT a synced or browsable OPFS file. Falls back to the
  // default if the system-prompt module hasn't loaded yet.
  let content = (typeof SandpieSystemPrompt !== 'undefined' && SandpieSystemPrompt.get)
    ? SandpieSystemPrompt.get()
    : (localStorage.getItem('sandpie-system-prompt') || 'You are a helpful assistant that reasons through the users requests step-by-step.');
  // Current local time, prepended and rebuilt every turn, so the model can reason
  // about "now" (dates, staleness of recalled state, scheduling).
  try {
    const now = new Date();
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    const stamp = now.toLocaleString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    content = 'The current local date and time is ' + stamp + (tz ? ' (' + tz + ')' : '') + '. Treat this as "now".\n\n' + content;
  } catch (_) {}
  // Optional capability: context.js appends the skills block (enforced skill
  // index + an instruction telling the model to fetch a skill via the load_skill
  // tool when relevant). Module absent ⇒ plain memory prompt.
  if (typeof SandpieContext !== 'undefined' && SandpieContext.skillBlock) {
    try { content += await SandpieContext.skillBlock(convMessages); }
    catch (e) { console.warn('[sandpie] skills block failed:', e); }
  }
  // Optional capability: mindframe.js appends a Stage-0 AWARENESS directive that
  // forces the model to scan the prompt into nouns/verbs (and research unknown
  // nouns) before acting. Returns '' when the toggle is off ⇒ no behavior change.
  if (typeof SandpieMindframe !== 'undefined' && SandpieMindframe.systemBlock) {
    try { content += SandpieMindframe.systemBlock(convMessages); }
    catch (e) { console.warn('[sandpie] mindframe block failed:', e); }
  }
  // Optional capability: memory.js injects all durable facts (sandpie/memory/*.md).
  // maybeConsolidate first so an over-budget store is pruned before it's injected;
  // it's a cheap no-op when under budget. Returns '' when off/empty ⇒ no change.
  if (typeof SandpieMemory !== 'undefined' && SandpieMemory.systemBlock) {
    try { await SandpieMemory.maybeConsolidate(); } catch (e) { console.warn('[sandpie] memory consolidate failed:', e); }
    try { content += await SandpieMemory.systemBlock(); }
    catch (e) { console.warn('[sandpie] memory block failed:', e); }
  }
  if (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.systemBlock) {
    try { content += await SandpieAugmentations.systemBlock(); }
    catch (e) { console.warn('[sandpie] augmentations block failed:', e); }
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
  const data = await readConvData(id);
  if (!data) { flightClear(id); return; }
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
    const el = $('messages');
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
async function _performCompaction(convId, cfg) {
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
  _compacting.add(convId);
  emit('compaction:start');
  try {
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return { ok: false, reason: 'no completion provider available' };
    const out = await SandpieProviders.complete({ system: cfg.prompt, user: transcript, model: cfg.model || undefined, maxTokens: 2048 });
    if (!out || !out.trim()) return { ok: false, reason: 'summarizer returned empty' };
    const r = await compactConversation(convId, { keepTail: cfg.keepTail, summary: out });
    return (r && r.ok) ? { ok: true, removed: r.removed, kept: r.kept } : { ok: false, reason: (r && r.reason) || 'compaction failed' };
  } catch (e) {
    return { ok: false, reason: (e && e.message) || String(e) };
  } finally {
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
  let pct = null;
  try { pct = await _cmpContextPct(convId); } catch {}
  if (pct == null || pct < cfg.pct) return { triggered: false, ok: true };
  try {
    const r = await _performCompaction(convId, cfg);
    // "nothing new to compact" means the aged span is already summarized — the
    // threshold is met but there's nothing left to do, so don't block the send.
    if (r && !r.ok && r.reason && /nothing (new to compact|to summarize)/.test(r.reason)) return { triggered: false, ok: true };
    return { triggered: true, ok: !!(r && r.ok), reason: r && r.reason };
  } catch (e) {
    console.warn('[sandpie] auto-compaction failed:', e);
    return { triggered: true, ok: false, reason: (e && e.message) || String(e) };
  }
}
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
      const prompt = await buildSystemPrompt(messages);
      return '=== System prompt ===\n\n' + prompt.content;
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
      const r = await _performCompaction(convId, cfg);
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
    const data = await readConvData(id);
    if (!data) { addMsg('err', 'Failed to load conv.'); throw new Error('conv not found: ' + id); }
    const s = ensureStream(id);
    hydrateStreamFromData(s, data);
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
  ta.addEventListener('input', () => {
    autosize();
    if (lastTabMatches && !ta.value.startsWith('>>>')) {
      lastTabMatches = null;
      if (SandpieCommandView) SandpieCommandView.hide();
    }
  });

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
  // ---- Tab completion for >>> commands ----
  let lastTabMatches = null;
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
      window.handleSubmit();
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


/* expose moved page-glue for inline handlers (HTML onclick) + the host contract */
window.maybeResumeFlight = maybeResumeFlight;
window.anyStreamGenerating = anyStreamGenerating;

/* expose on window for inline script compatibility */
window.ensureStream = ensureStream;
window.activeStream = activeStream;
window.flightWrite = flightWrite;
window.flightRead = flightRead;
window.flightClear = flightClear;
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
window.SandpieConversations = { compact: compactConversation, getCompaction, safeSplitIndex, maybeAutoCompact };
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
  Promise.resolve(
    (typeof SandpieTokens !== 'undefined' && SandpieTokens.conversationTokens)
      ? SandpieTokens.conversationTokens(convId) : 0,
  ).then(t => { if (c.isConnected) c.textContent = t ? (TOK_FMT(t) + ' ctx') : '– ctx'; }).catch(() => {});
}
function _wireCtxCounter(el, convId) {
  const c = el && el.querySelector('.mt-ctx');
  if (!c) return;
  c.style.cursor = 'pointer';
  c.title = 'Conversation context — click for details';
  c.addEventListener('click', (e) => { e.stopPropagation(); openContextPopup(convId, c); });
  _paintCtxCounter(el, convId);
}

function startTotalTimer(stream) {
  if (!stream || stream.timerEl) return;
  stream.timerStart = Date.now();

  const el = document.createElement('div');
  el.className = 'msg-timer';
  // Built once; the tick mutates the leaf <span>s in place. No live tok/s — with
  // estimation removed there is no per-turn token count until the provider reports
  // usage at turn end (local WebGPU models report via the engine; see endTotalTimer).
  el.innerHTML =
    '<button class="mt-nn" title="Show thoughts" onclick="toggleThoughts()">' + NN_SVG_INLINE + '</button>' +
    '<span class="mt-time">0s</span>' +
    '<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>' +
    '<span class="mt-queue"></span>' +
    '<span class="mt-todos"></span>';
  stream.host.appendChild(el);
  stream.timerEl = el;

  const timeEl = el.querySelector('.mt-time');
  const queueEl = el.querySelector('.mt-queue');
  queueEl.style.cursor = 'pointer';
  queueEl.title = 'Click to view queued messages';
  queueEl.addEventListener('click', () => openQueueModal(stream));
  _wireCtxCounter(el, stream.id);
  const todosEl = el.querySelector('.mt-todos');
  stream.todosEl = todosEl;
  stream.todos = null;
  const set = (node, txt) => { if (node.textContent !== txt) node.textContent = txt; };

  const paint = () => {
    if (!stream.timerEl) return;
    set(timeEl, fmtElapsed((Date.now() - stream.timerStart) / 1000));
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
    // Settled line: label · elapsed · [tok/s] · ctx, dimmed via .done. tok/s comes
    // ONLY from the provider's reported completion_tokens (no estimate); omitted
    // when the provider reported no usage (e.g. some local paths).
    const u = stream.lastUsage;
    const comp = u && typeof u.completion_tokens === 'number' ? u.completion_tokens : 0;
    const rate = (comp > 0 && sec > 0.05) ? comp / sec : 0;
    const nnCls = 'mt-nn' + (thoughtsVisible ? ' on' : '');
    const nnTitle = thoughtsVisible ? 'Hide thoughts' : 'Show thoughts';
    const parts = [
      `<button class="${nnCls}" title="${nnTitle}" onclick="toggleThoughts()">${NN_SVG_INLINE}</button>`,
      `<span class="mt-label">${label}</span>`,
      `<span class="mt-sep">·</span><span class="mt-time">${fmtElapsed(sec, true)}</span>`,
    ];
    if (rate > 0) parts.push(`<span class="mt-sep">·</span><span class="mt-rate">${RATE_FMT(rate)}</span>`);
    parts.push('<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>');
    if (stream.todos && stream.todos.length) {
      const ip = stream.todos.findIndex(t => t && t.status === 'in_progress');
      const cur = ip >= 0 ? ip + 1 : stream.todos.filter(t => t && t.status === 'completed').length;
      parts.push(`<span class="mt-todos">${cur}/${stream.todos.length}</span>`);
    }
    stream.timerEl.innerHTML = parts.join('');
    stream.timerEl.classList.add('done');
    _wireCtxCounter(stream.timerEl, stream.id);
    if (stream.todos && stream.todos.length) {
      const badge = stream.timerEl.querySelector('.mt-todos');
      if (badge) {
        // Snapshot THIS turn's checklist so the finished badge always shows the
        // state at turn-end, immune to later turns reassigning/clearing
        // stream.todos (startTotalTimer resets it to null next turn).
        const snapshot = stream.todos.slice();
        badge.onclick = () => {
          if (typeof SandpieCommandView !== 'undefined') SandpieCommandView.show(buildTodosView(snapshot), 'Checklist');
        };
      }
    }
  }
  stream.timerEl = null;
}

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
  if (T) { try { used = await T.conversationTokens(convId); } catch (_) {} try { win = T.contextWindow(); } catch (_) {} }

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
      rows.push(`<div class="ctx-popup-row"><span>${pct.toFixed(pct < 10 ? 1 : 0)}% of ${TOK_FMT(win)}</span><span>${TOK_FMT(Math.max(0, win - used))} left</span></div>`);
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
// agent is summarizing (agents.js emits compaction:start/end). Pre-send compaction
// is awaited before the turn goes out, so without this the user just sees an
// unexplained pause. Removed on end (and harmlessly wiped by the post-compaction
// re-render, whichever comes first).
function showCompactionProgress(convId) {
  try {
    const s = convStreams.get(convId);
    const host = (s && s.host) || $('messages');
    if (!host || host.querySelector('.compaction-progress')) return;
    const el = document.createElement('div');
    el.className = 'compaction-progress';
    el.innerHTML = '<span class="cp-spin" aria-hidden="true"></span><span>Summarizing earlier messages to free up context…</span>';
    host.appendChild(el);
    if (shouldAutoScroll(host) || isAtBottom(host)) host.scrollTop = host.scrollHeight;
  } catch (_) {}
}
function hideCompactionProgress(convId) {
  try {
    const s = convStreams.get(convId);
    const host = (s && s.host) || $('messages');
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
function showBgProgress(convId, key, text) {
  try {
    const s = convStreams.get(convId);
    // Render only in the conversation this op belongs to. Fall back to the visible
    // #messages ONLY when it IS the active conversation — otherwise a background op
    // (e.g. lessons for a conv you just switched away from) would leak its banner
    // into the unrelated conversation you're now viewing (e.g. a fresh + New chat).
    const host = (s && s.host) || (convId === activeConvId ? $('messages') : null);
    if (!host || host.querySelector('.bg-progress[data-key="' + key + '"]')) return;
    const el = document.createElement('div');
    el.className = 'compaction-progress bg-progress';
    el.dataset.key = key;
    el.innerHTML = '<span class="cp-spin" aria-hidden="true"></span><span>' + text + '</span>';
    host.appendChild(el);
    if (shouldAutoScroll(host) || isAtBottom(host)) host.scrollTop = host.scrollHeight;
  } catch (_) {}
}
function hideBgProgress(convId, key) {
  try {
    const s = convStreams.get(convId || activeConvId);
    const host = (s && s.host) || $('messages');
    if (host) host.querySelectorAll('.bg-progress[data-key="' + key + '"]').forEach(e => e.remove());
  } catch (_) {}
}

function bootConversations() {
  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('compaction:start', ({ convId }) => showCompactionProgress(convId));
    Sandpie.events.on('compaction:end', ({ convId }) => hideCompactionProgress(convId));
    // Lessons distillation (augmentations.js) — silent post-turn LLM call. Name
    // the conversation so it's clear WHICH one is being distilled (it may not be
    // the one currently on screen).
    Sandpie.events.on('lessons:start', ({ convId }) => {
      const t = _shortConvTitle(convId);
      showBgProgress(convId, 'lessons', 'Distilling lessons' + (t ? ` from “${t}”` : ' from this session') + '…');
    });
    Sandpie.events.on('lessons:end', ({ convId }) => hideBgProgress(convId, 'lessons'));
    // Memory consolidation (memory.js) — events existed but had no indicator.
    Sandpie.events.on('memory:consolidate-start', () => showBgProgress(activeConvId, 'consolidate', 'Consolidating memory…'));
    Sandpie.events.on('memory:consolidate-end', () => hideBgProgress(activeConvId, 'consolidate'));
  }
  (async () => {
    await refreshConversationList();
    if (activeConvId) {
      const restoreId = activeConvId;
      activeConvId = null;
      const s = ensureStream(restoreId);
      try {
        const data = await readConvData(restoreId);
        if (data) hydrateStreamFromData(s, data);
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
