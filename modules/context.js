
const SandpieTokens = (() => {
  const WEEK_LOG_KEY = 'sandpie-token-weeklog';
  const USAGE_PREFIX = 'sandpie-usage-';
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
  const listeners = new Set();

  function usageTotal(u) {
    if (!u) return 0;
    return u.total_tokens || ((u.prompt_tokens || 0) + (u.completion_tokens || 0));
  }

  function loadLog() {
    try { const v = JSON.parse(localStorage.getItem(WEEK_LOG_KEY) || '[]'); return Array.isArray(v) ? v : []; }
    catch { return []; }
  }
  function prune(log) {
    const cutoff = Date.now() - WEEK_MS;
    return log.filter(e => e && typeof e.t === 'number' && e.t >= cutoff);
  }
  function weeklyTotal() {
    return prune(loadLog()).reduce((a, e) => a + (e.tokens || 0), 0);
  }

  function textOf(content) {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) return content.map(p => p && p.type === 'text' ? (p.text || '') : '').join(' ');
    return '';
  }
  function estimateTokens(msgs) {
    let chars = 0;
    for (const m of (msgs || [])) {
      chars += textOf(m.content).length;
      if (m.tool_calls) for (const tc of m.tool_calls) chars += (tc.function?.arguments || '').length + (tc.function?.name || '').length;
    }
    return Math.ceil(chars / 4);
  }

  // Live override pushed by the streaming loop during generation, so the panel
  // climbs in real time (baseline + generated-so-far) instead of only updating
  // when the turn ends. Cleared when the turn finishes → authoritative wins.
  let _liveTotal = null, _liveConvId = null, _liveNotifyT = null;

  async function conversationTokens() {
    const convId = localStorage.getItem('sandpie-active-conv');
    if (!convId) return 0;
    if (_liveTotal != null && _liveConvId === convId) return _liveTotal;
    try {
      const stored = localStorage.getItem(USAGE_PREFIX + convId);
      if (stored) return usageTotal(JSON.parse(stored));
    } catch {}
    try {
      const text = await window.opfs.read('sandpie/conversations/' + convId + '.json');
      const data = JSON.parse(text);
      if (data.usage) return usageTotal(data.usage);
      if (data.messages) return estimateTokens(data.messages);
    } catch {}
    return 0;
  }

  function isEstimated() {
    const convId = localStorage.getItem('sandpie-active-conv');
    if (_liveTotal != null && _liveConvId === convId) return true;   // live = estimate
    return !convId || !localStorage.getItem(USAGE_PREFIX + convId);
  }

  // Streaming loop calls this (throttled internally) with the live running total.
  function setLiveTokens(convId, total) {
    _liveConvId = convId;
    _liveTotal = (typeof total === 'number' && total >= 0) ? total : null;
    if (_liveNotifyT) return;   // coalesce re-renders to ~5/s
    _liveNotifyT = setTimeout(() => { _liveNotifyT = null; notify(); }, 200);
  }
  function clearLiveTokens(convId) {
    if (convId != null && convId !== _liveConvId) return;
    _liveTotal = null; _liveConvId = null;
    if (_liveNotifyT) { clearTimeout(_liveNotifyT); _liveNotifyT = null; }
    notify();
  }

  function contextWindow() {
    const ap = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    return (ap && ap.contextWindow > 0) ? ap.contextWindow : null;
  }

  function recordUsage(convId, usage) {
    if (!usage) return;
    localStorage.setItem(USAGE_PREFIX + convId, JSON.stringify(usage));
    const log = prune(loadLog());
    log.push({ t: Date.now(), tokens: usageTotal(usage) });
    localStorage.setItem(WEEK_LOG_KEY, JSON.stringify(log));
    notify();
  }

  // Drop a conversation's recorded usage so its size is re-derived from the live
  // messages (used after compaction, whose summary makes the old usage stale-high).
  function forget(convId) {
    if (!convId) return;
    try { localStorage.removeItem(USAGE_PREFIX + convId); } catch {}
    notify();
  }

  function subscribe(cb) { listeners.add(cb); return () => listeners.delete(cb); }
  function notify() { for (const cb of listeners) { try { cb(); } catch (e) { console.warn(e); } } }

  return {
    recordUsage, forget, conversationTokens, isEstimated, weeklyTotal,
    contextWindow, subscribe, notify, setLiveTokens, clearLiveTokens,
  };
})();
window.SandpieTokens = SandpieTokens;

/* =============================================================================
   SandpieContext — skills: filesystem-derived index + model-driven loading

   OPFS layout (the filesystem IS the index — nothing to hand-maintain):
     skills/<name>/SKILL.md   a skill. <name> (the folder) is the skill's name.
                              The folder may also hold support files.

   Each SKILL.md self-describes via YAML-style frontmatter at the very top:
     ---
     name: sandpie_deploy            (optional; defaults to the folder name)
     description: When to use this…  (REQUIRED — how the model decides to load it)
     ---
     # instructions…

   Every send, scanSkills() walks each skills/<name>/SKILL.md, parses frontmatter,
   and builds the index in memory. Malformed skills (no SKILL.md, no frontmatter, no
   description) are flagged deterministically — surfaced in the sidebar and the
   prompt — and are NOT offered to the model (without a description it can't know
   when to use them). No registry to keep in sync; drop a folder and it appears.

   Selection stays the MODEL's decision: the prompt lists each valid skill's name
   + description and instructs the model to call `load_skill` (executed in the SW,
   sandpie.js → tool_load_skill) when a request matches — by intent, not keywords.
   ============================================================================= */
const SandpieContext = (() => {
  const SKILLS_DIR = 'sandpie/skills';
  const SKILL_FILE = 'SKILL.md';
  const DESC_CAP = 400;           // chars of description shown per skill in the prompt
  const NAME_RE = /^[a-z0-9][a-z0-9_-]*$/;
  const listeners = new Set();

  // Enable/disable (global, localStorage). A disabled skill is omitted from the
  // prompt's skill table so the model can't see or load it; the file stays on disk.
  const SKILLS_DISABLED_KEY = 'sandpie-skills-disabled';
  function disabledSkills() { try { const a = JSON.parse(localStorage.getItem(SKILLS_DISABLED_KEY) || '[]'); return new Set(Array.isArray(a) ? a : []); } catch { return new Set(); } }
  function isSkillEnabled(name) { return !disabledSkills().has(name); }
  function setSkillEnabled(name, on) {
    const s = disabledSkills();
    if (on) s.delete(name); else s.add(name);
    localStorage.setItem(SKILLS_DISABLED_KEY, JSON.stringify([...s]));
    notify();
  }
  // Save an edited SKILL.md back to OPFS (the settings inline editor uses this).
  async function saveSkill(file, text) {
    await opfs.write(file, text);
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', file); } catch (_) {}
    notify();
  }

  // Last computed state, for the sidebar: {exists, skills, errors, loaded}
  let last = { exists: false, skills: [], errors: [], loaded: [] };

  // Parse leading YAML-ish frontmatter (--- … ---). Deterministic and
  // dependency-free: only scalar `key: value` lines (name, description). Returns
  // null when there's no frontmatter block at all.
  function parseFrontmatter(text) {
    const m = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(text);
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

  // Walk skills/*/ and derive the index from each folder's SKILL.md frontmatter.
  // Every problem is reported in `errors`; only fully-valid skills reach `skills`.
  async function scanSkills() {
    let entries;
    try { entries = await opfs.listDir(SKILLS_DIR); }
    catch { return { exists: false, skills: [], errors: [] }; } // no skills/ dir yet
    const skills = [], errors = [];
    for (const e of entries) {
      if (e.kind !== 'directory') continue; // stray files under skills/ are ignored
      const folder = e.name;                // the folder name IS the skill name
      const path = `${SKILLS_DIR}/${folder}`;
      const file = `${path}/${SKILL_FILE}`;
      let text;
      try { text = await opfs.read(file); }
      catch { errors.push(`${path}/ — no ${SKILL_FILE} (add one, or remove the folder)`); continue; }
      // load_skill resolves skills/<folder>/SKILL.md, so the folder must be a
      // valid (lowercase) name; otherwise it could be advertised but not loadable.
      if (!NAME_RE.test(folder)) { errors.push(`${path}/ — folder name "${folder}" isn't a valid skill name (lowercase a-z, 0-9, _ or -); rename it`); continue; }
      const fm = parseFrontmatter(text);
      if (!fm) { errors.push(`${file} — no frontmatter; add a "---" block with name + description at the very top`); continue; }
      if (fm.name && fm.name.toLowerCase() !== folder) {
        errors.push(`${file} — frontmatter name "${fm.name}" ≠ folder "${folder}"; load_skill uses the folder name "${folder}"`);
      }
      const desc = (fm.description || '').replace(/\s+/g, ' ').trim();
      if (!desc) { errors.push(`${file} — missing "description"; the model needs it to decide when to load this skill`); continue; }
      skills.push({ name: folder, desc, path, file, enabled: isSkillEnabled(folder) });
    }
    skills.sort((a, b) => a.name.localeCompare(b.name));
    return { exists: true, skills, errors };
  }

  // Names of skills the model already pulled in this conversation — so the index
  // can mark them "loaded" and the model won't waste a round-trip reloading.
  function loadedSkillNames(msgs) {
    const out = new Set();
    for (const m of msgs || []) {
      if (m && m.role === 'assistant' && Array.isArray(m.tool_calls)) {
        for (const tc of m.tool_calls) {
          if (tc.function?.name !== 'load_skill') continue;
          try { const a = JSON.parse(tc.function.arguments || '{}'); if (a.name) out.add(String(a.name).toLowerCase()); }
          catch {}
        }
      }
    }
    return out;
  }

  const clip = s => s.length > DESC_CAP ? s.slice(0, DESC_CAP) + '…' : s;

  // The block conversations.js appends to the system prompt on every send.
  // Returns '' (zero tokens) when there's no skills/ directory.
  async function skillBlock(convMessages) {
    const idx = await scanSkills();
    const loaded = idx.exists ? loadedSkillNames(convMessages) : new Set();
    last = { ...idx, loaded: [...loaded] };
    notify();
    if (!idx.exists) return '';

    const lines = ['', '', '# Skills'];
    lines.push(
      `Skills are saved playbooks for specific tasks, auto-discovered from \`${SKILLS_DIR}/*/${SKILL_FILE}\`. ` +
      `**When the user's request matches a skill's description — by intent, not exact wording — call the \`load_skill\` tool with that skill's name BEFORE you start, then follow the instructions it returns.** ` +
      `If several could apply, load the best match; if none clearly fit, just proceed. ` +
      `To add a skill, create \`${SKILLS_DIR}/<name>/${SKILL_FILE}\` with frontmatter (a "---" block holding name + description) — it's discovered automatically, no registry to update.`,
    );
    lines.push('', '| Skill | When to use |', '|---|---|');
    const activeSkills = idx.skills.filter(s => s.enabled);   // disabled skills are hidden from the model
    for (const s of activeSkills) {
      const mark = loaded.has(s.name) ? ' _(already loaded above)_' : '';
      lines.push(`| ${s.name} | ${clip(s.desc)}${mark} |`);
    }
    if (!activeSkills.length) lines.push('| _none yet_ | — |');
    if (idx.errors.length) {
      lines.push('', `Skill problems (${idx.errors.length}) — these folders are NOT loadable until fixed:`);
      for (const e of idx.errors.slice(0, 5)) lines.push(`- ${e}`);
    }
    return lines.join('\n');
  }

  // Sidebar view: same scan + which skills the active conversation has loaded.
  async function inspect(convMessages) {
    const idx = await scanSkills();
    last = { ...idx, loaded: idx.exists ? [...loadedSkillNames(convMessages)] : [] };
    return last;
  }

  // Scaffold one well-formed example skill so the frontmatter format is obvious.
  const EXAMPLE_NAME = 'example_skill';
  const EXAMPLE = `---
name: ${EXAMPLE_NAME}
description: Describe in plain language when this skill applies — the task it handles. The model reads this to decide when to load the skill, so write it the way you'd brief a teammate (e.g. "Deploying the app to production: bump version, commit, push, verify CI").
---

# ${EXAMPLE_NAME}

Replace this with the step-by-step instructions for the task. The whole file is
returned to the model when it calls load_skill on this skill.
`;

  async function scaffold() {
    const file = `${SKILLS_DIR}/${EXAMPLE_NAME}/${SKILL_FILE}`;
    if (await opfs.exists(file)) return;
    await opfs.write(file, EXAMPLE);
    if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', file);
    try { Sandpie.refreshFiles(); } catch {}
  }

  function subscribe(cb) { listeners.add(cb); return () => listeners.delete(cb); }
  function notify() { for (const cb of listeners) { try { cb(); } catch (e) { console.warn(e); } } }

  return {
    SKILLS_DIR, skillBlock, inspect, scaffold, subscribe,
    isSkillEnabled, setSkillEnabled, saveSkill,
    lastState: () => last,
  };
})();
window.SandpieContext = SandpieContext;

/**
 * Context Module for Sandpie
 *
 * Registers a "Context" section in the sidebar via SandpieMenu and renders the
 * conversation's token usage (with a context-window percentage when the model's
 * window is known) plus a rolling 7-day token total. The numbers come from
 * SandpieTokens, which the page populates from real provider usage.
 * Below the usage block it renders the skill index (SandpieContext): every
 * indexed skill, validation errors, and which skills the active conversation
 * has loaded.
 *
 * Usage: <script type="module" src="modules/context.js"></script>
 */

let _unsubscribe = null;

function fmtTokens(n) {
  n = Math.max(0, Math.round(n || 0));
  if (n < 1000) return String(n);
  if (n < 1000000) return (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k';
  return (n / 1000000).toFixed(1) + 'M';
}

const escHtml = s => String(s).replace(/[&<>"']/g, c => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

// Estimate the conversation's token usage split by TYPE (a client-side estimate
// at ~4 chars/token, like SandpieTokens.estimateTokens). The provider only gives
// a single total, so the per-type split is necessarily approximate.
//  - system prompt   : the editable base prompt (SandpieSystemPrompt)
//  - tool descriptions: the serialized tool defs sent every request (toolDefs)
//  - skills          : the skills block appended to the system prompt (from the
//                      cached scan, so we don't re-read OPFS on every tick)
//  - messages        : user + assistant text
//  - tool calls      : assistant tool_calls (name + arguments)
//  - tool results    : tool-role message content
//  - images          : counted (their token cost is provider/size-specific)
const CTX_CATS = [
  ['system',      'System prompt',     '#58a6ff'],
  ['tools',       'Tool descriptions', '#a371f7'],
  ['skills',      'Skills',            '#3fb950'],
  ['messages',    'Messages',          '#d29922'],
  ['toolCalls',   'Tool calls',        '#f778ba'],
  ['toolResults', 'Tool results',      '#ff7b72'],
];

async function computeBreakdown() {
  const toTok = c => Math.ceil((c || 0) / 4);
  const b = { system: 0, tools: 0, skills: 0, messages: 0, toolCalls: 0, toolResults: 0, images: 0 };
  try { if (typeof SandpieSystemPrompt !== 'undefined' && SandpieSystemPrompt.get) b.system = toTok((SandpieSystemPrompt.get() || '').length); } catch {}
  try { if (typeof toolDefs === 'function') b.tools = toTok(JSON.stringify(toolDefs() || []).length); } catch {}
  try {
    if (typeof SandpieContext !== 'undefined' && SandpieContext.lastState) {
      const st = SandpieContext.lastState();
      if (st && st.exists) {
        let chars = 620;  // the fixed instruction/header in the skills block
        for (const s of (st.skills || [])) { if (s.enabled === false) continue; chars += (s.name || '').length + Math.min((s.desc || '').length, 400) + 12; }
        b.skills = toTok(chars);
      }
    }
  } catch {}
  let msgs = [];
  try {
    const convId = localStorage.getItem('sandpie-active-conv');
    if (convId && window.opfs) {
      const data = JSON.parse(await opfs.read('sandpie/conversations/' + convId + '.json'));
      if (Array.isArray(data.messages)) msgs = data.messages;
    }
  } catch {}
  for (const m of msgs) {
    if (!m) continue;
    let textLen = 0;
    const c = m.content;
    if (typeof c === 'string') textLen += c.length;
    else if (Array.isArray(c)) for (const p of c) {
      if (p && p.type === 'text') textLen += (p.text || '').length;
      else if (p && /image/.test(String(p.type || ''))) b.images++;
    }
    if (m.role === 'tool') b.toolResults += toTok(textLen); else b.messages += toTok(textLen);
    if (Array.isArray(m.tool_calls)) {
      let t = 0;
      for (const tc of m.tool_calls) { const f = tc.function || {}; t += (f.name || '').length + (f.arguments || '').length; }
      b.toolCalls += toTok(t);
    }
  }
  return b;
}

async function render() {
  const T = SandpieTokens;
  if (typeof T === 'undefined') return;

  const convEl = document.getElementById('ctxConvTokens');
  if (!convEl) return;
  const pctEl = document.getElementById('ctxConvPct');
  const weekEl = document.getElementById('ctxWeekTokens');
  const barEl = document.getElementById('ctxStackBar');
  const legEl = document.getElementById('ctxBreakdown');
  const section = document.getElementById('contextSection');
  const open = !section || section.open;

  const reportedTotal = await T.conversationTokens();
  const window_ = T.contextWindow();
  const estimated = T.isEstimated();

  // The per-type breakdown is also a fuller estimate: it counts the system prompt,
  // tool defs, and skills that the message-only estimate misses.
  const b = await computeBreakdown();
  const sum = CTX_CATS.reduce((a, [k]) => a + (b[k] || 0), 0);
  // When estimating, show whichever is larger — the live/running figure or the
  // breakdown sum — so the headline never reads smaller than its own breakdown.
  const total = estimated ? Math.max(reportedTotal, sum) : reportedTotal;

  convEl.textContent = fmtTokens(total) + (estimated ? ' ~' : '');
  convEl.title = estimated ? 'Estimated client-side (provider did not report usage)' : 'Reported by the provider';

  let badge = fmtTokens(total);
  if (window_) {
    const pct = Math.min(100, (total / window_) * 100);
    badge = `${pct.toFixed(0)}%`;
    if (pctEl) pctEl.textContent = `${pct.toFixed(pct < 10 ? 1 : 0)}% of ${fmtTokens(window_)} window · ${fmtTokens(Math.max(0, window_ - total))} left`;
  } else if (pctEl) {
    pctEl.textContent = 'Context window unknown for this model';
  }
  if (weekEl) weekEl.textContent = fmtTokens(T.weeklyTotal());
  if (typeof SandpieMenu !== 'undefined') SandpieMenu.updateBadge('contextSection', badge);

  // Only the bar/legend DOM is skipped when collapsed (the totals above stay live);
  // the toggle handler re-runs render() when the section is expanded.
  if (!open || (!barEl && !legEl)) return;

  const present = CTX_CATS.filter(([k]) => b[k] > 0);

  if (barEl) {
    barEl.innerHTML = sum > 0
      ? present.map(([k, label, color]) => `<div title="${label}: ${fmtTokens(b[k])} (${Math.round(b[k] / sum * 100)}%)" style="width:${(b[k] / sum * 100).toFixed(2)}%;background:${color};height:100%;"></div>`).join('')
      : '';
  }
  if (legEl) {
    const rows = present.map(([k, label, color]) =>
      `<div style="display:flex;align-items:center;gap:0.4rem;font-size:0.72rem;line-height:1.55;">
        <span style="width:9px;height:9px;border-radius:2px;background:${color};flex:0 0 auto;"></span>
        <span style="color:var(--sp-text-dim);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${label}</span>
        <span style="font-variant-numeric:tabular-nums;color:var(--sp-text);">${fmtTokens(b[k])}</span>
        <span style="color:var(--sp-text-dim);min-width:2.6em;text-align:right;">${Math.round(b[k] / sum * 100)}%</span>
      </div>`).join('');
    const imgNote = b.images ? `<div style="font-size:0.68rem;color:var(--sp-text-dim);margin-top:0.2rem;">+ ${b.images} image${b.images > 1 ? 's' : ''} (size not estimated)</div>` : '';
    legEl.innerHTML = sum > 0 ? rows + imgNote : '<div style="font-size:0.72rem;color:var(--sp-text-dim);">No messages yet.</div>';
  }
}

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Context module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('tokens:record', ({convId, usage}) => {
      SandpieTokens.recordUsage(convId, usage);
    });
  }

  SandpieMenu.add('contextSection', {
    title: 'Context',
    badge: '—',
    open: false,
    html: `
      <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.3rem;">
        <span style="color:var(--sp-text-dim);">Conversation</span>
        <span id="ctxConvTokens" style="font-variant-numeric:tabular-nums;">–</span>
      </div>
      <div id="ctxStackBar" title="Estimated breakdown by type" style="display:flex; height:8px; border-radius:4px; overflow:hidden; background:var(--sp-border);"></div>
      <p id="ctxConvPct" style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.35rem 0 0.55rem;"></p>
      <div id="ctxBreakdown" style="display:flex; flex-direction:column; gap:0.1rem;"></div>
      <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-top:0.7rem;">
        <span style="color:var(--sp-text-dim);">This week (7d)</span>
        <span id="ctxWeekTokens" style="font-variant-numeric:tabular-nums;">–</span>
      </div>
    `,
    onRender(bodyEl) {
      if (!_unsubscribe) _unsubscribe = SandpieTokens.subscribe(render);
      // Recompute the breakdown when the user expands the (collapsed-by-default)
      // section, since render() skips the heavy part while it's closed.
      const section = document.getElementById('contextSection');
      if (section && !section._ctxToggleWired) {
        section._ctxToggleWired = true;
        section.addEventListener('toggle', () => { if (section.open) render(); });
      }
      render();
    }
  });

  console.log('Context module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
