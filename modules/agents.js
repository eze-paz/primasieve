/**
 * Agents Module for Sandpie — modular, OPFS-defined background automations.
 *
 * Each agent is a config file: agents/<id>.md  (id = filename, lowercase a-z0-9_-)
 *   ---                         frontmatter = config
 *   name: Memory distiller
 *   enabled: false              opt-in
 *   every_messages: 10          trigger — fire every N messages
 *   at_context_pct:             trigger — fire at >= P% of the context window
 *   every_minutes:              trigger — fire every M minutes (best-effort)
 *   input: since_last_run       since_last_run | conversation | last_<n>
 *   sink: memory                memory | note | compact | append:<path>
 *   keep_tail:                  (compact only) recent messages kept verbatim
 *   model:                      optional model override
 *   ---
 *   <the prompt body>           everything below = the zero-shot prompt
 *
 * The body-as-prompt means multi-line prompts need no escaping, and because an
 * agent is just a file, the main LLM can list/read/create/tune agents with the
 * read_file / write_file / edit_file tools — no special plumbing. The sidebar
 * lists agents and edits the raw file (generic to any field we add later).
 *
 * Sinks: `memory` parses {topic,note} JSON -> appends memory/<topic>.md;
 * `append:<path>` appends the raw output to a file; `note` just surfaces it.
 *
 * Guardrails: opt-in; idle-only (runs on generation:complete, skips while
 * generating); single-flight; gated (a per-(agent,conversation) cursor so a
 * span isn't reprocessed); loop-proof (a direct non-streaming call — never the
 * conversation stream — emits no generation:complete; agents write to memory/ or
 * append paths, never agents/); cancellable; failure-isolated; malformed agents
 * are flagged and never run.
 *
 * Usage: <script type="module" src="modules/agents.js"></script>
 */

const AGENTS_DIR = 'sandpie/agents';
const ID_RE = /^[a-z0-9][a-z0-9_-]*$/;

// ---- small helpers ---------------------------------------------------------
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

function textOf(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(p => (p && p.type === 'text') ? (p.text || '') : '').join(' ');
  return '';
}

function buildTranscript(msgs, fromIdx, uptoIdx) {
  const out = [];
  for (let i = fromIdx; i < uptoIdx; i++) {
    const m = msgs[i];
    if (!m || (m.role !== 'user' && m.role !== 'assistant')) continue;
    const t = textOf(m.content).trim();
    if (t) out.push((m.role === 'user' ? 'USER: ' : 'ASSISTANT: ') + t);
  }
  let s = out.join('\n\n');
  const CAP = 12000;
  if (s.length > CAP) s = '…[earlier turns truncated]\n\n' + s.slice(s.length - CAP);
  return s;
}

const slugTopic = (t) => String(t || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48);
const nowDate = () => new Date().toISOString().slice(0, 10);
const nowStamp = () => new Date().toISOString().slice(0, 16).replace('T', ' ');

const FM_RE = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/;
function parseFrontmatter(text) {
  const m = FM_RE.exec(text);
  if (!m) return null;
  const fm = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*)$/.exec(line);
    if (!kv) continue;
    let v = kv[2].trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    fm[kv[1].toLowerCase()] = v;
  }
  return fm;
}

// ---- agent config parsing + validation ------------------------------------
function parseAgent(id, text) {
  const fm = parseFrontmatter(text) || {};
  const body = text.replace(FM_RE, '').trim();
  const errors = [];
  const num = (k) => { const v = fm[k]; if (v == null || v === '') return null; const n = parseInt(v, 10); return Number.isFinite(n) ? n : null; };

  const a = {
    id,
    name: fm.name || id,
    enabled: /^(true|yes|on|1)$/i.test(String(fm.enabled || '')),
    everyMessages: num('every_messages'),
    atContextPct: num('at_context_pct'),
    everyMinutes: num('every_minutes'),
    input: (fm.input || 'since_last_run').toLowerCase(),
    sink: (fm.sink || 'note').toLowerCase(),
    model: fm.model || '',
    keepTail: num('keep_tail'),
    prompt: body,
    raw: text,
    errors,
  };
  if (!parseFrontmatter(text)) errors.push('no frontmatter (need a "---" block with config at the top)');
  if (!a.prompt) errors.push('no prompt (the body below the frontmatter is empty)');
  if (a.everyMessages == null && a.atContextPct == null && a.everyMinutes == null) {
    errors.push('no trigger (set every_messages, at_context_pct, or every_minutes)');
  }
  if (!(a.sink === 'memory' || a.sink === 'note' || a.sink === 'compact' || a.sink.startsWith('append:'))) {
    errors.push(`unknown sink "${a.sink}" — use memory, note, compact, or append:<path>`);
  }
  return a;
}

function triggerSummary(a) {
  const t = [];
  if (a.everyMessages != null) t.push(`every ${a.everyMessages} msgs`);
  if (a.atContextPct != null) t.push(`at ${a.atContextPct}% context`);
  if (a.everyMinutes != null) t.push(`every ${a.everyMinutes} min`);
  return t.length ? t.join(' or ') : 'no trigger';
}

// ---- registry (loaded from OPFS) ------------------------------------------
let agents = [];
async function loadAgents() {
  let entries = [];
  try { entries = await opfs.listDir(AGENTS_DIR); } catch { agents = []; return agents; }
  const out = [];
  for (const e of entries) {
    if (e.kind !== 'file' || !/\.md$/i.test(e.name)) continue;
    const id = e.name.replace(/\.md$/i, '');
    let text = '';
    try { text = await opfs.read(`${AGENTS_DIR}/${e.name}`); } catch { continue; }
    const a = parseAgent(id, text);
    if (!ID_RE.test(id)) a.errors.unshift(`invalid filename "${e.name}" — use lowercase a-z, 0-9, _ or -`);
    out.push(a);
  }
  out.sort((x, y) => x.id.localeCompare(y.id));
  agents = out;
  return agents;
}

const DISTILLER_PROMPT = [
  "You are sandpie's memory distiller. You read an excerpt of a chat conversation and extract DURABLE takeaways worth remembering in FUTURE, separate conversations — decisions reached, conclusions, stable facts about a project/system/person, and explicit user preferences.",
  "",
  "Rules:",
  "- Save only what stays true and useful later. Ignore greetings, transient chatter, and anything tied only to this moment.",
  "- Each note must be SELF-CONTAINED: understandable months from now with no access to this conversation.",
  "- File it under a short topic (its subject/domain). Reuse an existing topic when one fits.",
  "- If nothing durable is worth saving, skip.",
  "",
  "Output ONLY one JSON object, nothing else:",
  '  {"skip": true}',
  '  {"topic": "<kebab-case-subject>", "note": "<1-4 sentence durable takeaway>"}',
].join('\n');

const DEFAULT_DISTILLER = `---
name: Memory distiller
enabled: false
every_messages: 10
input: since_last_run
sink: memory
---
${DISTILLER_PROMPT}
`;

const COMPACTOR_PROMPT = [
  "You are sandpie's conversation compactor. You receive the EARLIER part of an ongoing chat — the most recent turns are kept verbatim and are NOT shown to you. Produce a dense briefing that REPLACES those earlier turns in the live context, so the conversation can continue indefinitely without losing the thread.",
  "",
  "Preserve, compactly:",
  "- The original goal/task and any stated constraints or requirements.",
  "- Decisions made and why; conclusions reached.",
  "- Key facts, names, file paths, commands, IDs, and values referenced.",
  "- Open threads — what is still in progress or unresolved.",
  "- The user's stated preferences and any corrections they gave.",
  "",
  "Drop greetings, small talk, and anything already superseded. Write a tight briefing (headings or bullets are fine) for a future reader with NO access to the omitted turns. Do not invent anything. Output ONLY the summary text — no preamble, no JSON.",
].join('\n');

const DEFAULT_COMPACTOR = `---
name: Conversation compactor
enabled: false
at_context_pct: 70
keep_tail: 10
sink: compact
---
${COMPACTOR_PROMPT}
`;

const NEW_AGENT_TEMPLATE = `---
name: New agent
enabled: false
every_messages: 20
input: since_last_run
sink: note
---
Describe the job here. You receive a slice of the conversation as input and
produce text output. With sink "note" the output is shown in the sidebar; use
sink "append:<path>" to append it to a file, or "memory" with a JSON
{"topic","note"} result to write memory/<topic>.md.
`;

async function ensureDefaults() {
  let entries = [];
  try { entries = await opfs.listDir(AGENTS_DIR); } catch {}
  const mdNames = new Set(entries.filter(e => /\.md$/i.test(e.name)).map(e => e.name.toLowerCase()));
  if (mdNames.size === 0) {
    await writeAgentFile('distiller', DEFAULT_DISTILLER);
    mdNames.add('distiller.md');
  }
  // Seed the compactor once (disabled). One-time flag so a user's delete sticks.
  if (!mdNames.has('compactor.md') && !localStorage.getItem('sandpie-agent-seed-compactor')) {
    await writeAgentFile('compactor', DEFAULT_COMPACTOR);
    localStorage.setItem('sandpie-agent-seed-compactor', '1');
  }
}

// ---- direct (non-streaming) completion — never the SW conversation stream --
async function runPrompt(system, user, { model, signal, maxTokens = 1024 } = {}) {
  const active = (typeof SandpieProviders !== 'undefined' && SandpieProviders.getActive) ? SandpieProviders.getActive() : null;
  // Local (WebGPU Qwen3.5) provider: run the completion IN-BROWSER. Its "endpoint"
  // is a model-variant id, not an OpenAI server — never POST <variant>/chat/completions.
  // runConversation is the only entry point; drive it with no tools and collect the
  // streamed content deltas into a single string.
  if (active && active.type === 'webgpu') {
    // Route to the SAME engine the chat uses (dense Qwen3 vs hybrid Qwen3.5) so a utility
    // prompt doesn't load the other model. Match the active model id against the dense set.
    const isDense = typeof SandpieQwen3 !== 'undefined' && SandpieQwen3.DEFAULT_MODELS
      && SandpieQwen3.DEFAULT_MODELS.some(m => m.modelId === active.endpoint);
    const eng = isDense ? SandpieQwen3 : (typeof SandpieQwen35 !== 'undefined' ? SandpieQwen35 : null);
    if (!eng || !eng.runConversation) throw new Error('WebGPU engine not loaded');
    let out = '';
    await eng.runConversation({
      provider: { endpoint: active.endpoint, maxTokens },
      messages: [{ role: 'user', content: user }],
      systemPrompt: system,
      tools: [], convId: null, signal,
    }, (ev) => { if (ev && ev.type === 'delta' && ev.delta && typeof ev.delta.content === 'string') out += ev.delta.content; });
    return out;
  }
  const endpoint = (document.getElementById('endpoint')?.value || '').replace(/\/$/, '');
  const apiKey = document.getElementById('apiKey')?.value || '';
  const mdl = model || document.getElementById('model')?.value || '';
  if (!endpoint || !mdl) throw new Error('no provider configured');
  const route = (typeof Sandpie !== 'undefined' && Sandpie.api) ? Sandpie.api(endpoint + '/chat/completions') : (endpoint + '/chat/completions');
  const url = new URL(route, location.href).href;
  const body = { model: mdl, messages: [{ role: 'system', content: system }, { role: 'user', content: user }], stream: false, max_tokens: maxTokens };
  if (active && active.temperature != null) body.temperature = active.temperature;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) { const t = await res.text().catch(() => ''); throw new Error('HTTP ' + res.status + (t ? ': ' + t.slice(0, 200) : '')); }
  const data = await res.json();
  return data?.choices?.[0]?.message?.content || '';
}

// ---- per-(agent,conversation) cursor + per-agent last-run -----------------
const cursorKey = (id, convId) => `sandpie-agent-cur-${id}-${convId}`;
const lastRunKey = (id) => `sandpie-agent-last-${id}`;
const cursorOf = (id, convId) => parseInt(localStorage.getItem(cursorKey(id, convId)) || '0', 10) || 0;

function emitChanged(path) {
  if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', path);
  try { Sandpie.refreshFiles && Sandpie.refreshFiles(); } catch {}
}

// ---- triggers --------------------------------------------------------------
// Estimate the live conversation size in tokens (chars/4 — the same heuristic
// SandpieTokens uses). Counts the CURRENT messages array, so it already includes
// a turn the user just typed but hasn't sent yet.
function estimateConvTokens(msgs) {
  let chars = 0;
  for (const m of msgs || []) {
    chars += textOf(m.content).length;
    if (Array.isArray(m.tool_calls)) for (const tc of m.tool_calls) {
      chars += ((tc.function && tc.function.arguments) || '').length + ((tc.function && tc.function.name) || '').length;
    }
  }
  return Math.ceil(chars / 4);
}

// Current context usage as a % of the active provider's window, or null when the
// window is unknown (no way to compute a %, so the at_context_pct trigger can't
// fire — the provider needs a context window set). Takes the LARGER of the
// authoritative last-turn usage and a fresh estimate of the live array: the
// estimate catches a big turn before it is sent (last usage only reflects the
// PREVIOUS turn, and is stale after a compaction), while the authoritative figure
// accounts for the system prompt + tools the estimate can't see.
async function contextPct() {
  if (typeof SandpieTokens === 'undefined') return null;
  let w; try { w = SandpieTokens.contextWindow(); } catch { w = null; }
  if (!w) return null;
  const msgs = (typeof messages !== 'undefined' && Array.isArray(messages)) ? messages : [];
  // Measure what's actually SENT: with non-destructive compaction the live array
  // holds the full history but only [summary + in-context tail] goes to the model.
  let sent = msgs;
  try {
    const comp = (typeof SandpieConversations !== 'undefined' && SandpieConversations.getCompaction)
      ? SandpieConversations.getCompaction(activeConv()) : null;
    if (comp && comp.boundary > 0 && comp.boundary < msgs.length) {
      sent = [{ role: 'user', content: comp.summary || '' }, ...msgs.slice(comp.boundary)];
    }
  } catch {}
  let used = estimateConvTokens(sent);
  try { const t = await SandpieTokens.conversationTokens(); if (t > used) used = t; } catch {}
  return (used / w) * 100;
}

async function shouldRun(a, convId) {
  if (a.errors.length) return false;
  const msgs = (typeof messages !== 'undefined' && Array.isArray(messages)) ? messages : [];
  if (a.everyMessages != null && (msgs.length - cursorOf(a.id, convId)) >= a.everyMessages) return true;
  if (a.atContextPct != null) {
    try { const p = await contextPct(); if (p != null && p >= a.atContextPct) return true; } catch {}
  }
  if (a.everyMinutes != null) {
    const last = parseInt(localStorage.getItem(lastRunKey(a.id)) || '0', 10) || 0;
    if (Date.now() - last >= a.everyMinutes * 60000) return true;
  }
  return false;
}

// ---- run + sinks -----------------------------------------------------------
async function applySink(a, out, convId) {
  if (a.sink === 'compact') {
    if (typeof SandpieConversations === 'undefined' || !SandpieConversations.compact) {
      return { status: 'compaction unavailable (conversations module not ready)' };
    }
    const r = await SandpieConversations.compact(convId, { keepTail: a.keepTail || 10, summary: out });
    return { status: r.ok ? `compacted ${r.removed} → kept ${r.kept}` : 'skipped: ' + (r.reason || '') };
  }
  if (a.sink === 'note') return { status: 'note: ' + out.trim().replace(/\s+/g, ' ').slice(0, 120) };
  if (a.sink.startsWith('append:')) {
    const path = a.sink.slice(7).trim().replace(/^\/+/, '');
    if (!path) return { status: 'bad sink path' };
    let body = ''; try { body = await opfs.read(path); } catch {}
    body += `${body ? '\n\n' : ''}[${nowStamp()}] (conv: ${convId})\n${out.trim()}`;
    await opfs.write(path, body); emitChanged(path);
    return { status: 'saved', file: path };
  }
  // memory
  let obj = null;
  try { const i = out.indexOf('{'), j = out.lastIndexOf('}'); if (i >= 0 && j > i) obj = JSON.parse(out.slice(i, j + 1)); } catch {}
  if (!obj || obj.skip || !obj.topic || !obj.note) return { status: 'nothing durable' };
  const topic = slugTopic(obj.topic); if (!topic) return { status: 'bad topic' };
  const note = String(obj.note).trim().replace(/\s+/g, ' '); if (!note) return { status: 'empty note' };
  const file = 'memory/' + topic + '.md';
  let body; try { body = await opfs.read(file); }
  catch { body = `# ${topic}\n\n> Distilled notes from past conversations (auto-written by an agent).\n`; }
  body += `\n- [${nowDate()}] ${note} _(conv: ${convId})_`;
  await opfs.write(file, body); emitChanged(file);
  return { status: 'saved', file };
}

async function runAgent(a, convId, signal) {
  const msgs = (typeof messages !== 'undefined' && Array.isArray(messages)) ? messages : [];
  let from = 0, to = msgs.length;
  let priorSummary = '';
  if (a.sink === 'compact') {
    // Summarize the span between the current compaction boundary and the new one
    // (everything except the protected tail). Build on the prior summary so old
    // context isn't lost re-summarizing only the newly-aged turns.
    const keepTail = a.keepTail || 10;
    to = (typeof SandpieConversations !== 'undefined' && SandpieConversations.safeSplitIndex)
      ? SandpieConversations.safeSplitIndex(msgs, keepTail)
      : Math.max(0, msgs.length - keepTail);
    const comp = (typeof SandpieConversations !== 'undefined' && SandpieConversations.getCompaction)
      ? SandpieConversations.getCompaction(convId) : null;
    from = (comp && comp.boundary) || 0;
    priorSummary = (comp && comp.summary) || '';
  } else if (a.input === 'since_last_run') {
    from = cursorOf(a.id, convId);
  } else if (/^last_\d+$/.test(a.input)) {
    from = Math.max(0, msgs.length - parseInt(a.input.slice(5), 10));
  }
  let transcript = buildTranscript(msgs, from, to);
  if (a.sink === 'compact' && priorSummary) {
    transcript = '[Summary of the conversation so far]\n' + priorSummary + '\n\n[New turns to fold into the summary]\n' + transcript;
  }
  if (!transcript.trim()) return { status: 'nothing to process' };
  const out = await runPrompt(a.prompt, transcript, { model: a.model || undefined, signal, maxTokens: a.sink === 'compact' ? 2048 : 1024 });
  localStorage.setItem(cursorKey(a.id, convId), String(msgs.length));
  localStorage.setItem(lastRunKey(a.id), String(Date.now()));
  return await applySink(a, out, convId);
}

// ---- runtime state + guardrails -------------------------------------------
let busy = false;
let currentAbort = null;
const status = {};
const activeConv = () => (typeof activeConvId !== 'undefined' && activeConvId) ? activeConvId : null;
const statusLine = (r) => !r ? 'idle' : (r.status === 'saved' ? `saved → ${r.file}` : r.status);

async function execAgent(a, convId) {
  busy = true; currentAbort = new AbortController();
  status[a.id] = 'running…'; renderAgents();
  try {
    status[a.id] = statusLine(await runAgent(a, convId, currentAbort.signal));
  } catch (e) {
    if (e && e.name === 'AbortError') status[a.id] = 'stopped';
    else { console.warn('[agents] ' + a.id + ' failed:', e); status[a.id] = 'error: ' + String((e && e.message) || e).slice(0, 80); }
  } finally {
    busy = false; currentAbort = null; renderAgents();
  }
}

async function onTurnComplete(payload) {
  if (busy) return;
  if (payload && payload.aborted) return;
  if (typeof Sandpie !== 'undefined' && Sandpie.isGenerating && Sandpie.isGenerating()) return;
  const convId = (payload && payload.convId) || activeConv();
  if (!convId) return;
  await loadAgents(); // pick up edits the user or the LLM made
  for (const a of agents) {
    if (!a.enabled) continue;
    let fire = false;
    try { fire = await shouldRun(a, convId); } catch {}
    if (!fire) continue;
    await execAgent(a, convId);
    break; // single-flight
  }
}

// Proactive, pre-send compaction. The composer calls this right BEFORE a turn is
// sent: if an enabled compact-sink agent's context threshold is already met, run
// it now so the outgoing request stays under the limit. This is what makes the
// compactor reliable — the reactive generation:complete path only fires AFTER a
// turn (so it cannot save a turn that itself overflows), and a request that
// fails on overflow records no usage, so the reactive %-check then reads
// stale-low and never fires. Awaited by the caller, so the now-smaller context
// is what gets built into the request.
async function maybeCompactBeforeSend(convId) {
  if (busy || !convId || convId !== activeConv()) return;   // compaction mutates the active conversation only
  if (!agents.length) { try { await loadAgents(); } catch {} }
  for (const a of agents) {
    if (!a.enabled || a.errors.length) continue;
    if (a.sink !== 'compact' || a.atContextPct == null) continue;
    let p = null;
    try { p = await contextPct(); } catch {}
    if (p == null || p < a.atContextPct) continue;
    await execAgent(a, convId);
    break; // one compaction per send
  }
}

async function runNow(id) {
  if (busy) { status[id] = 'busy — another run in progress'; renderAgents(); return; }
  await loadAgents();
  const a = agents.find(x => x.id === id);
  if (!a) return;
  if (a.errors.length) { status[id] = 'fix config first: ' + a.errors[0]; renderAgents(); return; }
  const convId = activeConv();
  if (!convId) { status[id] = 'no active conversation'; renderAgents(); return; }
  await execAgent(a, convId);
}

function stopAll() { if (currentAbort) try { currentAbort.abort(); } catch {} }

// ---- file ops --------------------------------------------------------------
async function writeAgentFile(id, text) {
  await opfs.write(`${AGENTS_DIR}/${id}.md`, text);
  emitChanged(`${AGENTS_DIR}/${id}.md`);
}
async function deleteAgent(id) {
  try { await opfs.remove(`${AGENTS_DIR}/${id}.md`); } catch {}
  if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:deleted', `${AGENTS_DIR}/${id}.md`);
  try { Sandpie.refreshFiles && Sandpie.refreshFiles(); } catch {}
}
function withEnabled(raw, on) {
  if (/^enabled[ \t]*:.*$/m.test(raw)) return raw.replace(/^enabled[ \t]*:.*$/m, 'enabled: ' + on);
  if (FM_RE.test(raw)) return raw.replace(/^(﻿?---[ \t]*\r?\n)/, `$1enabled: ${on}\n`);
  return raw;
}
function newAgentId() {
  let n = 1, id = 'new_agent';
  const taken = new Set(agents.map(a => a.id));
  while (taken.has(id)) id = 'new_agent_' + (++n);
  return id;
}

// ---- sidebar UI ------------------------------------------------------------
let editingId = null;

function renderAgents() {
  const host = document.getElementById('agentsBody');
  if (!host) return;
  let html = `<div style="margin-bottom:0.5rem;"><button id="agentNew" style="font-size:0.72rem; padding:0.2rem 0.55rem; background:transparent; color:var(--sp-text-dim); border:1px solid var(--sp-border); border-radius:4px; cursor:pointer;">+ New agent</button></div>`;
  if (!agents.length) {
    html += `<p style="color:var(--sp-text-dim);">No agents yet. Each is a file at <code>agents/&lt;id&gt;.md</code> (frontmatter config + prompt body).</p>`;
  }
  for (const a of agents) {
    const editing = editingId === a.id;
    const st = status[a.id] || 'idle';
    html += `
      <div style="border-bottom:1px solid var(--sp-border); padding:0.45rem 0;">
        <label style="display:flex; align-items:center; gap:0.4rem; cursor:pointer;">
          <input type="checkbox" data-en="${a.id}" ${a.enabled ? 'checked' : ''} ${a.errors.length ? 'disabled' : ''}>
          <span>${escHtml(a.name)}</span>
          <span style="color:var(--sp-text-dim); font-size:0.92em;">· ${escHtml(a.id)}</span>
        </label>
        <div style="color:var(--sp-text-dim); margin-left:1.4rem;">Trigger: ${escHtml(triggerSummary(a))} · sink: ${escHtml(a.sink)}</div>
        ${a.errors.length ? `<div style="color:var(--sp-accent-neg, #e06c75); margin-left:1.4rem;">⚠ ${a.errors.map(escHtml).join('; ')}</div>` : ''}
        <div style="margin:0.25rem 0 0 1.4rem; display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap;">
          <button data-edit="${a.id}" style="font-size:0.7rem; padding:0.12rem 0.45rem; background:transparent; color:var(--sp-text-dim); border:1px solid var(--sp-border); border-radius:4px; cursor:pointer;">${editing ? 'Close' : 'Edit'}</button>
          <button data-run="${a.id}" ${busy ? 'disabled' : ''} style="font-size:0.7rem; padding:0.12rem 0.45rem; background:transparent; color:var(--sp-text-dim); border:1px solid var(--sp-border); border-radius:4px; cursor:pointer;">Run now</button>
          <button data-del="${a.id}" style="font-size:0.7rem; padding:0.12rem 0.45rem; background:transparent; color:var(--sp-text-dim); border:1px solid var(--sp-border); border-radius:4px; cursor:pointer;">Delete</button>
          <span style="color:var(--sp-text-dim);">${escHtml(st)}</span>
        </div>
        ${editing ? `
          <textarea data-ta="${a.id}" spellcheck="false" style="width:100%; box-sizing:border-box; margin-top:0.4rem; min-height:200px; font-family:monospace; font-size:0.7rem; background:var(--sp-bg, #1e1e1e); color:var(--sp-text, #ddd); border:1px solid var(--sp-border); border-radius:4px; padding:0.4rem;">${escHtml(a.raw)}</textarea>
          <div style="margin-top:0.3rem; display:flex; gap:0.4rem; align-items:center;">
            <button data-save="${a.id}" style="font-size:0.7rem; padding:0.15rem 0.6rem; background:var(--sp-accent); color:#000; border:none; border-radius:4px; cursor:pointer;">Save</button>
            <span style="color:var(--sp-text-dim); font-size:0.68rem;">writes agents/${escHtml(a.id)}.md</span>
          </div>` : ''}
      </div>`;
  }
  html += `<p style="font-size:0.68rem; color:var(--sp-text-dim); margin:0.5rem 0 0;">Agents run their own model calls when enabled. Off by default. Editable here or via the file tools by the assistant.</p>`;
  host.innerHTML = html;

  const $ = (sel) => host.querySelectorAll(sel);
  $('input[data-en]').forEach(cb => cb.onchange = async () => {
    const a = agents.find(x => x.id === cb.dataset.en); if (!a) return;
    await writeAgentFile(a.id, withEnabled(a.raw, cb.checked));
    await loadAgents(); renderAgents();
  });
  $('button[data-edit]').forEach(b => b.onclick = () => { editingId = (editingId === b.dataset.edit) ? null : b.dataset.edit; renderAgents(); });
  $('button[data-run]').forEach(b => b.onclick = () => runNow(b.dataset.run));
  $('button[data-del]').forEach(b => b.onclick = async () => {
    if (!confirm(`Delete agent "${b.dataset.del}"? This removes agents/${b.dataset.del}.md.`)) return;
    if (editingId === b.dataset.del) editingId = null;
    await deleteAgent(b.dataset.del); await loadAgents(); renderAgents();
  });
  $('button[data-save]').forEach(b => b.onclick = async () => {
    const ta = host.querySelector(`textarea[data-ta="${b.dataset.save}"]`); if (!ta) return;
    await writeAgentFile(b.dataset.save, ta.value);
    editingId = null; await loadAgents(); renderAgents();
  });
  const nb = document.getElementById('agentNew');
  if (nb) nb.onclick = async () => {
    const id = newAgentId();
    await writeAgentFile(id, NEW_AGENT_TEMPLATE);
    await loadAgents(); editingId = id; renderAgents();
  };

  if (typeof SandpieMenu !== 'undefined') {
    SandpieMenu.updateBadge('agentsSection', String(agents.filter(a => a.enabled && !a.errors.length).length));
  }
}

// ---- init ------------------------------------------------------------------
async function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Agents module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  SandpieMenu.add('agentsSection', {
    title: 'Agents',
    badge: '0',
    open: false,
    html: `<div id="agentsBody" style="font-size:0.75rem; line-height:1.4;"></div>`,
    onRender() { renderAgents(); },
  });

  try { await ensureDefaults(); } catch (e) { console.warn('[agents] ensureDefaults failed:', e); }
  try { await loadAgents(); } catch (e) { console.warn('[agents] loadAgents failed:', e); }
  renderAgents();

  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('generation:complete', onTurnComplete);
    // Reflect external edits (e.g. the assistant tuning an agent) in the UI,
    // unless the user is mid-edit (don't clobber the textarea).
    Sandpie.events.on('file:changed', (p) => {
      if (typeof p === 'string' && p.startsWith(AGENTS_DIR + '/') && editingId === null) {
        loadAgents().then(renderAgents);
      }
    });
  }

  console.log('Agents module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

window.SandpieAgents = {
  loadAgents,
  runNow,
  maybeCompactBeforeSend,
  stopAll,
  get agents() { return agents; },
  _internals: { parseAgent, parseFrontmatter, parseTriggerSummary: triggerSummary, buildTranscript, slugTopic, shouldRun, contextPct, estimateConvTokens, applySink, runAgent, withEnabled, newAgentId },
};
