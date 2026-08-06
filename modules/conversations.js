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
          try {
            const { path } = JSON.parse(tc.function.arguments || '{}');
            if (path) {
              const target = host || paneScrollEl($('messages'));
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
    const target = host || paneScrollEl($('messages'));
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
  // A caller that wiped the host (clearActiveConvUI — rewind / compaction
  // re-render) destroyed the settled .msg-timer line, and nothing re-creates it:
  // endTotalTimer only fixes the DOM while the tick interval is alive, then nulls
  // stream.timerEl. But the data that built it (timerStart, lastUsage, todos)
  // survives on the stream, so rebuild the ~same .done line here. Skip when a
  // timer already exists (live or settled) — it's only ever needed after a wipe.
  rebuildSettledTimer(target, s);
}

// Rebuild a settled (.done) msg-timer line into `target` from the stream's
// surviving post-turn data. Mirrors the label/elapsed/[tok/s]/ctx/todos layout
// endTotalTimer builds, minus the "stopped" variant (the label is not persisted
// on the stream, so a rebuilt line reads "done" — the distinction is cosmetic).
// No-op when the stream has no completed turn (timerStart/lastUsage unset) or a
// timer is already mounted.
function rebuildSettledTimer(target, s) {
  if (!target || !s || target.querySelector('.msg-timer')) return;
  // The ONLY case where a conversation renders no timer line is a brand-new
  // empty chat (nothing has ever been sent). Any conversation with messages
  // must show the timer. Missing data points (elapsed, tok/s, label) degrade
  // gracefully to their defaults rather than suppressing the whole line.
  if (!s.messages || !s.messages.length) return;
  let sec = null, comp = null, label = 'done';
  // Live data (timerStart/lastUsage) from a warm stream takes precedence;
  // persisted data (lastTurn) covers a cold load after refresh.
  if (s.timerStart && s.lastUsage) {
    sec = (Date.now() - s.timerStart) / 1000;
    const u = s.lastUsage;
    comp = u && typeof u.completion_tokens === 'number' ? u.completion_tokens : 0;
  } else if (s.lastTurn) {
    sec = s.lastTurn.sec;
    comp = s.lastTurn.completionTokens || 0;
    label = s.lastTurn.label || 'done';
  }
  const rate = (comp > 0 && sec > 0.05) ? comp / sec : 0;
  const nnCls = 'mt-nn' + (thoughtsVisible ? ' on' : '');
  const nnTitle = thoughtsVisible ? 'Hide thoughts' : 'Show thoughts';
  const parts = [
    `<button class="${nnCls}" title="${nnTitle}" onclick="toggleThoughts()">${NN_SVG_INLINE}</button>`,
    `<span class="mt-label">${label}</span>`,
    `<span class="mt-sep">·</span><span class="mt-time">${sec == null ? '–' : fmtElapsed(sec, true)}</span>`,
  ];
  if (rate > 0) parts.push(`<span class="mt-sep">·</span><span class="mt-rate">${RATE_FMT(rate)}</span>`);
  parts.push('<span class="mt-sep">·</span><span class="mt-ctx">– ctx</span>');
  if (s.todos && s.todos.length) {
    const ip = s.todos.findIndex(t => t && t.status === 'in_progress');
    const cur = ip >= 0 ? ip + 1 : s.todos.filter(t => t && t.status === 'completed').length;
    parts.push(`<span class="mt-todos">${cur}/${s.todos.length}</span>`);
  }
  const el = document.createElement('div');
  el.className = 'msg-timer done';
  el.innerHTML = parts.join('');
  appendContent(target, el);
  _wireCtxCounter(el, s.id);
  if (s.todos && s.todos.length) {
    const badge = el.querySelector('.mt-todos');
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

// Load a conversation file's messages + compaction state onto a stream (with
// migration). Used by every load path so compaction always survives a reload.
function hydrateStreamFromData(s, data) {
  migrateCompactionData(data);
  s.messages = (data.messages || []).slice();
  s.compaction = data.compaction || null;
  s.todos = data.todos || null;
  s.lastTurn = data.lastTurn || null;
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
}
function mountConv(convId, pane = null) {
  activeConvId = convId;
  if (convId) {
    localStorage.setItem('sandpie-active-conv', convId);
    const s = ensureStream(convId);
    messages = s.messages;

    const target = pane || (sidePanel ? sidePanel.activeMountTarget() : $('messages'));
    if (s.host.parentNode !== target) _mountInPane(s.host, target);
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
  const mEl = paneScrollEl($('messages'));
  if (mEl) mEl.scrollTop = mEl.scrollHeight;
}
async function newConversation() {
  await saveActiveConv();
  // "+ New chat" always opens in the MAIN pane and leaves the side panel alone.
  // It used to mount into the FOCUSED pane, so with the focus on the right it
  // silently unmounted the conversation the user had docked there.
  const main = $('messages');
  parkPaneConv(main);
  const id = newConvId();
  ensureStream(id);
  mountConv(id, main);
  if (sidePanel?.isOpen && sidePanel.activeIsRight) sidePanel.focusPane(false);
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
  const span = document.createElement('span');
  span.className = 'name';
  span.textContent = (c.pinned ? '> ' : '') + c.title;
  span.title = c.updated || '';
  span.onclick = () => loadConv(c.id);
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
    // Show the dashed drop zone immediately, before the pointer even reaches the
    // messages area — so the user can see where they're allowed to drop.
    const w0 = $('messagesWrap'); if (w0) w0.classList.add('drop-target');
    // dragend always fires when the drag concludes (dropped, cancelled, or
    // released outside the drop zone) — guaranteed cleanup for the drop-target
    // dashed line so it can never get stuck on screen.
    const clearDrop = () => { const w = $('messagesWrap'); if (w) w.classList.remove('drop-target'); };
    li.addEventListener('dragend', clearDrop, { once: true });
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
    header.textContent = `Archived (${archived.length}) ${archivedExpanded ? '▾' : '▸'}`;
    header.onclick = () => { archivedExpanded = !archivedExpanded; refreshConversationList(); };
    frag.appendChild(header);
    if (archivedExpanded) archived.forEach((c, i) => frag.appendChild(buildConvLi(c, pinned.length + regular.length + i)));
  }
  ul.replaceChildren(frag);
}
function refreshSendButtonForActive() {
  refreshSendButtonFor('main');
  refreshSendButtonFor('side');
}
function refreshSendButtonFor(which) {
  const btn = which === 'side' ? $('sendBtnSide') : $('sendBtn');
  if (!btn) return;
  const convId = _composerConv(which);
  const s = convId ? convStreams.get(convId) : activeStream();
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
    stream.generating = true;
    // A new turn starts fresh — clear any stale pending-ask flag for this conv
    // (left behind if a previous turn was aborted mid-question).
    _askingConvs.delete(activeConvId);
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
  const composer = pane.querySelector(':scope > .composer');
  if (composer) pane.insertBefore(panel, composer); else pane.appendChild(panel);
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
async function handleSubmit(which = 'main') {
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
    if (convId && isResumableActive()) {
      const s = ensureStream(convId);
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
// Put the home lists where they belong: first child of the LEFT pane's conv-host
// when one is mounted (so they scroll with the conversation), else the left pane
// itself above its bottom cluster. Always the left pane — the home screen only
// ever lives there, so a host removed from the SIDE pane must not drag the lists
// into #messagesSide (that left the main pane empty and the lists stranded).
function _placeHome() {
  const hc = _homeEl();
  const pane = $('messages');
  if (!hc || !pane) return;
  const host = pane.querySelector(':scope > .conv-host');
  if (host) {
    if (hc.parentNode !== host || host.firstChild !== hc) host.insertBefore(hc, host.firstChild);
  } else if (hc.parentNode !== pane) {
    appendContent(pane, hc);
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
  if (s.generating && s.agentId && _canSteerActive()) {
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
  const el = addMsg('user', content, s.host);
  (s._pendingSteer = s._pendingSteer || []).push({ el, content, msg: null });
  try { getSandpieWorker().postMessage({ type: 'steer', id: s.agentId, content }); } catch (_) {}
}
function handleButtonClick(which = 'main') {
  const btn = which === 'side' ? $('sendBtnSide') : $('sendBtn');
  if (!btn) return;
  const convId = _composerConv(which);
  const s = convId ? convStreams.get(convId) : activeStream();
  if (btn.classList.contains('sending') && s) {
    // Stop only the message generating right now; queued messages stay and the
    // next one is sent immediately. To halt everything, press stop once per
    // in-flight + queued message.
    if (s.abort) s.abort.abort();
  } else {
    window.handleSubmit(which);
  }
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
  _sandpieWorker = new Worker('./modules/sandpie-worker.js?v=96');
  window._sandpieWorker = _sandpieWorker;

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

// Byte size of what will actually be sent (system prompt + resolved messages + tool defs). No pre-send byte cap — the token-based guard (maybeAutoCompact) protects the model context.
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
  let userBubbleEl = null;
  if (!opts?.resume) {
    const userMsg = { role: 'user', content: text };
    convMessages.push(userMsg);
    userBubbleEl = addMsg('user', text, host);
    bindBubble(userBubbleEl, userMsg);
    saveConv(convId).catch(() => {});
  }

  // If no model is selected but a configured provider has one, use it rather than
  // erroring; then validate. On failure the message above is preserved.
  if (typeof SandpieProviders !== 'undefined' && SandpieProviders.ensureUsable) {
    try { SandpieProviders.ensureUsable(); } catch (_) {}
  }
  const _active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.getActive) ? SandpieProviders.getActive() : null;
  if (!$('endpoint').value || !$('model').value || !$('apiKey').value) {
    addMsg('err', 'Add a provider (endpoint, model, and API key) in Settings before sending.', host);
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
    mk.textContent = '📷 → ' + ((config.model || 'vision model'));
    userBubbleEl.appendChild(mk);
  }
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
        // Budget = the provider's context WINDOW (converted to bytes at ~4 bytes/token, targeting base.pct% of it). No artificial byte-size cap — the token-based compaction (maybeAutoCompact) protects the model context.
    let budget = Infinity;
    try { const win = SandpieTokens.contextWindow && SandpieTokens.contextWindow(); if (win) budget = Math.min(budget, Math.round(win * (base.pct / 100) * 4)); } catch (_) {}
    // Shrink the kept tail until the request fits. keepTail=10 is only a STARTING
    // point: if the last 10 messages alone exceed the budget (big tool outputs),
    // halve it (10→5→2) so the boundary advances PAST them. "nothing to compact"
    // means the current keepTail still protects the whole over-budget slice → shrink
    // and retry, don't give up. Only stop on a real summarizer failure or at the
    // keepTail=2 floor (can't drop the current turn's own request/response).
    let keep = base.keepTail;
    for (let i = 0; i < 8; i++) {
      if (_sentRequestBytes(config) <= budget) break;
      const r = await _performCompaction(convId, { ...base, keepTail: keep });
      if (r && !r.ok && !/nothing/.test(r.reason || '')) break;   // real failure (e.g. summarizer down)
      config = await buildAgentConfig(stream.messages, stream.compaction, stream.todos, convId);
      if (keep <= 2) break;                                        // already at the floor
      keep = Math.max(2, Math.floor(keep / 2));
    }
  }

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

    { // always cloud worker — local engines removed
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
    }   // end cloud-worker-only block
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

    // local-LLM removed
    stream.agentId = null;   // no longer steerable once the loop has ended
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

    releaseWakeLock();
    endTotalTimer(stream, wasAborted ? 'stopped' : 'done');
    // Refresh the context readouts (sidebar week total + badge, and any open ctx
    // popup) now the provider has reported this turn's authoritative usage.
    try { if (typeof SandpieTokens !== 'undefined' && SandpieTokens.notify) SandpieTokens.notify(); } catch (_) {}
    setStreamSending(stream, false);
    flushIncrementalSave(convId);
    await saveConv(convId);

    // Name the conversation from its opening exchange, if it's still carrying the
    // derived placeholder title. Awaited (the UI was released above, so this costs
    // no visible latency) so the new title is on disk before the sync below —
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
  const active = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
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
  let effective = active;
  let routedViaVision = false;
  if (!canSee && currentHasImages && visionFallback) {
    effective = visionFallback;
    routedViaVision = true;
  }
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
          continue;                                   // history image → not for a text-only model
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
  const _ep = (effective && effective.endpoint) ? String(effective.endpoint).replace(/\/$/, '') : $('endpoint').value.replace(/\/$/, '');
  return {
    url: new URL(api(_ep + '/chat/completions'), location.href).href,
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ((effective && effective.apiKey) || $('apiKey').value) },
    // Managed (company sign-in) provider only: let the worker silently re-mint the
    // session token from the SSO cookie via /auth/token on a 401, so an expired JWT
    // never interrupts the user mid-generation. null for personal providers — a 401
    // there is a real bad-key error, not a refreshable session.
    authRefreshUrl: (effective && effective.managed) ? new URL('/auth/token', location.href).href : null,
    _hermesMode: !!(effective && effective.type === 'hermes'),
    model: (effective && effective.model) || $('model').value,
    systemPrompt: await buildSystemPrompt(convMessages),
    // Reply-language rule shipped separately so sandpie-worker.js can also
    // inject it into subagent system prompts (subagents never see the parent's
    // composed system message).
    languageRule: (typeof SandpieLanguage !== 'undefined' && SandpieLanguage.directive) ? SandpieLanguage.directive() : null,
    // Ephemeral per-round reminder (user role) appended to every request right
    // before generation; not persisted, not shown in the UI.
    languageReminder: (typeof SandpieLanguage !== 'undefined' && SandpieLanguage.reminder) ? SandpieLanguage.reminder() : null,
    messages: resolvedMessages,
    tools: toolDefs(),
    // Rerouted to the vision fallback for this turn (user attached an image to a
    // text-only model). The composer marks the user bubble; the worker just uses
    // this config as-is (url/headers/model already point at the fallback).
    routedViaVision: !!routedViaVision,
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
    // Stable per-conversation cache key, persisted in meta (ensureSessionId).
    // Reused across turns/refreshes/devices so OpenRouter prompt-cache holds.
    session_id: await ensureSessionId(convId || activeConvId),
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
    case 'round_end':     return renderer.endRound(ev.content);
    case 'message_added': return renderer.bindMessage(ev.message);
    case 'tool_started':  return renderer.markToolStarted(ev.tc);
    case 'tool_result':   return renderer.markToolDone(ev.id, ev.result, ev.artifacts);
    case 'subagent':      return renderSubagentEvent(host, ev);
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

  // Prefer the mounted .conv-host even when the caller didn't thread `host`
  // through (most addMsg('err', …) calls don't) — paneScrollEl resolves it.
  const target = host || (activeStream() && activeStream().host) || paneScrollEl($('messages'));

  let scrollHost = climbScrollEl(target);
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
  appendContent(target, div);

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
      const cur = ip >= 0 ? ip + 1 : (todos || []).filter(t => t && t.status === 'completed').length;
      badge.textContent = cur + '/' + todos.length;
      badge.title = (todos[ip] && todos[ip].content) || 'Checklist';
      badge.onclick = () => {
        showCmdPanelForEl(badge, buildTodosView(todos), 'Checklist');
      };
    }
  }
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
  const card = buildQuestionsView(questions || [], (answers) => {
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

  // --- Navigation dots ---
  const dots = document.createElement('div');
  dots.className = 'ask-dots';
  wrap.appendChild(dots);

  // --- Actions: Atrás + Siguiente/Responder ---
  const actions = document.createElement('div');
  actions.className = 'ask-actions';
  const backBtn = document.createElement('button');
  backBtn.className = 'ask-btn';
  backBtn.textContent = '\u2190 Atr\u00e1s';
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

    // Dots
    dots.innerHTML = '';
    for (let j = 0; j < qs.length; j++) {
      const dot = document.createElement('span');
      dot.className = 'ask-dot' + (j === i ? ' active' : '') + (state.answers[j] ? ' done' : '');
      dots.appendChild(dot);
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
    html += '<textarea class="ask-free-input" rows="1" wrap="soft" placeholder="Otro: escribe tu propia respuesta\u2026">' + tcEscape(prevFree) + '</textarea>';
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
      grow();
      freeInput.addEventListener('input', () => { saveAnswer(i); grow(); });
    }

    // Buttons
    const isLast = i === qs.length - 1;
    nextBtn.textContent = isLast ? 'Responder' : 'Siguiente \u2192';
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
  const done = (todos || []).filter(t => t && t.status === 'completed').length;
  head.textContent = 'Checklist \u00b7 ' + done + '/' + todos.length + ' done';
  wrap.appendChild(head);
  for (const t of (todos || [])) {
    const st = (t && t.status) || 'pending';
    if (st === 'deleted' || st === 'withdrawn') continue;   // dropped from the flat view
    const row = document.createElement('div');
    row.className = 'tool-todo tool-todo-' + st;
    const mark = document.createElement('span');
    mark.className = 'tool-todo-mark';
    mark.textContent = st === 'completed' ? '\u2713' : st === 'in_progress' ? '\u25b8' : '\u25cb';
    const txt = document.createElement('span');
    txt.className = 'tool-todo-text';
    txt.textContent = (t && (st === 'in_progress' && t.activeForm ? t.activeForm : t.content)) || '';
    row.append(mark, txt);
    // Dependency indicator: tasks still waiting on an open blocker.
    if (t && Array.isArray(t.blockedBy) && t.blockedBy.length) {
      const openBlk = t.blockedBy.filter(id => {
        const b = (todos || []).find(x => x && String(x.id) === String(id));
        return b && (b.status === 'pending' || b.status === 'in_progress');
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
  if (fname === 'load_image' || fname === 'write_todos' || fname === 'ask') div.classList.add('expanded');
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
    // The PREVIOUS round's bubble is created empty and only removed by endRound.
    // Any path that skips endRound (abort, a provider error that isn't retried)
    // leaves an empty assistant strip on screen, and startRound is where we lose
    // the last reference to it — so clear it here before taking a new one.
    // Checked after _flushAllPending, so genuinely-streamed text is never dropped.
    if (this.reply && !(this.content && this.content.trim())) this.reply.remove();
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
  // A mid-stream provider error killed the previous attempt of this round after
  // some deltas already rendered; the worker is retrying the same round. Remove
  // the partial bubbles so the retry doesn't paint a duplicate copy of the text.
  retryRound() {
    if (this.reply) { this.reply.remove(); this.reply = null; }
    if (this.thinkEl) { this.thinkEl.remove(); this.thinkEl = null; }
    for (const el of this.toolCallEls) if (el) el.remove();
    this.startRound();
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

    if (this.drainTimer) { clearTimeout(this.drainTimer); this.drainTimer = null; }
    this.toolsShouldClose = true;
    this._flushAllPending();
    this._finishThinking();
    // Full markdown render deferred from local inference — do it once now, then scroll.
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
      appendContent(this.host || paneScrollEl($('messages')), det);
    }
    this.thinkEl = det;
    this.thinkBody = body;
    this.thinkSummary = sum;
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
    if (this.drainTimer != null) return;
    // Each drain re-renders the WHOLE message — _extractMath + marked.parse +
    // DOMPurify.sanitize over all accumulated text (see renderMd). At a fixed 16ms
    // that is O(n²) across a long stream and burns a core on large responses.
    // Stretch the interval as the message grows so the expensive full re-render
    // (esp. the DOMPurify pass) runs far less often once content is big; the final
    // clean render still happens once at endRound, and streamDiff preserves the
    // user's text selection at any cadence. Cloud only — local defers markdown to
    // finalize (_paintContent), so its drains are already cheap.
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
  return pane.querySelector(':scope > .cmd-output') || pane.querySelector(':scope > .composer');
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
    // Reply-language rule, ALSO stated at the very top of the system message
    // (primacy): a model skimming a long prompt still reads it first.
    let langTop = '';
    if (typeof SandpieLanguage !== 'undefined' && SandpieLanguage.directiveShort) {
      try { langTop = SandpieLanguage.directiveShort() + '\n\n'; } catch (_) {}
    }
    content = langTop + 'The current local date and time is ' + stamp + (tz ? ' (' + tz + ')' : '') + '. Treat this as "now".\n\n' + content;
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
  // maybeConsolidate runs FIRE-AND-FORGET: it is an LLM housekeeping pass that can
  // take minutes (and 504), and awaiting it here blocked every completion — and
  // every ralph turn, which builds this prompt — behind it. The pruned store simply
  // lands on the NEXT prompt build; this one injects the current store as-is.
  if (typeof SandpieMemory !== 'undefined' && SandpieMemory.systemBlock) {
    // (consolidation is event-driven off memory writes now — no per-turn / clock trigger)
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
  if (typeof SandpieAugmentations !== 'undefined' && SandpieAugmentations.systemBlock) {
    try { content += await SandpieAugmentations.systemBlock(); }
    catch (e) { console.warn('[sandpie] augmentations block failed:', e); }
  }
  // Reply-language rule (Settings → Account → Reply language): appended LAST so
  // it is the final instruction the model reads — the LLM MUST reply in the
  // chosen language unless the user explicitly asks otherwise, regardless of
  // the language of tool results/materials. Applies to every provider, and to
  // the Ralph loop (loop-lab.js shares buildSystemPrompt).
  if (typeof SandpieLanguage !== 'undefined' && SandpieLanguage.directive) {
    try { content += '\n\n' + SandpieLanguage.directive(); }
    catch (e) { console.warn('[sandpie] language rule failed:', e); }
  }
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
    const out = await SandpieProviders.complete({ system: cfg.prompt, user: transcript, model: cfg.model || undefined });
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
  if (!id) { bar.style.display = 'none'; return; }   // no conversation mounted → no bar
  bar.style.display = 'flex';
  const title = (await _paneTitleFor(id)) || '';
  if (req !== bar._req) return;                       // a newer refresh won the race
  t.textContent = title || 'new chat';
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
    searchInput.addEventListener('input', () => refreshConversationList());
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

// let _localInferring = false;  // local-LLM removed

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
    // if (_localInferring) return;  // local-LLM removed
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
// buildSystemPrompt exposed so Loop Lab can inject the app's full system prompt
// (memories, lessons, skills index) into its harness-loop agents — read-only.
// getTitle/autoTitle are read/write access to a conversation's name for modules
// that only need that (notifications.js reads it for the toast body).
window.SandpieConversations = { compact: compactConversation, getCompaction, safeSplitIndex, maybeAutoCompact, buildSystemPrompt, getTitle: convTitle, autoTitle: maybeAutoTitle };
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
    '<span class="mt-todos"></span>';
  stream.host.appendChild(el);
  stream.timerEl = el;

  const timeEl = el.querySelector('.mt-time');
  // queueEl wiring removed (queue system removed)
  _wireCtxCounter(el, stream.id);
  const todosEl = el.querySelector('.mt-todos');
  stream.todosEl = todosEl;
  // Do NOT reset stream.todos here. It is the persistent checklist (task tree),
  // carried across turns + reloads (meta.todos → hydrate → s.todos) and seeded
  // into the worker via config.todos so write_todos OPS apply to the existing
  // tree. Nulling it (a relic of the old full-replace design) detached the
  // checklist every turn — buildAgentConfig, called right after this, would read
  // null → empty tree → the model rewrites and loses state.
  const set = (node, txt) => { if (node.textContent !== txt) node.textContent = txt; };

  const paint = () => {
    if (!stream.timerEl) return;
    // Self-heal: a mid-turn host re-render (e.g. a compaction that clears
    // s.host.innerHTML) detaches the live timer, and startTotalTimer's guard
    // then never rebuilds it — so it vanishes for the rest of the turn. If it's
    // been orphaned, re-append it to the (rebuilt) host at the next tick.
    if (!stream.timerEl.isConnected && stream.host) stream.host.appendChild(stream.timerEl);
    set(timeEl, fmtElapsed((Date.now() - stream.timerStart) / 1000));

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
          showCmdPanelForEl(badge, buildTodosView(snapshot), 'Checklist');
        };
      }
    }
    // Persist the finished turn's data so the timer can be rebuilt on cold
    // loads (refresh → hydrateStreamFromData → renderConversation).
    stream.lastTurn = { sec, label: typeof label === 'string' ? label : 'done', completionTokens: comp };
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
      refreshPaneBars();
    }
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
