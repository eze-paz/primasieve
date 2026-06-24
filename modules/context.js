
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
      skills.push({ name: folder, desc, path, file });
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
    for (const s of idx.skills) {
      const mark = loaded.has(s.name) ? ' _(already loaded above)_' : '';
      lines.push(`| ${s.name} | ${clip(s.desc)}${mark} |`);
    }
    if (!idx.skills.length) lines.push('| _none yet_ | — |');
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
let _unsubscribeSkills = null;

function fmtTokens(n) {
  n = Math.max(0, Math.round(n || 0));
  if (n < 1000) return String(n);
  if (n < 1000000) return (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k';
  return (n / 1000000).toFixed(1) + 'M';
}

const escHtml = s => String(s).replace(/[&<>"']/g, c => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

async function renderSkills() {
  const countEl = document.getElementById('ctxSkillCount');
  const listEl = document.getElementById('ctxSkillList');
  const errEl = document.getElementById('ctxSkillErrors');
  const createBtn = document.getElementById('ctxSkillCreate');
  if (!countEl || typeof SandpieContext === 'undefined') return;

  const msgs = (typeof messages !== 'undefined') ? messages : [];
  let st;
  try { st = await SandpieContext.inspect(msgs); }
  catch (e) { console.warn('skills inspect failed:', e); return; }

  if (!st.exists) {
    countEl.textContent = '—';
    listEl.innerHTML = `<span style="color:var(--sp-text-dim);">No ${escHtml(SandpieContext.SKILLS_DIR)}/ folder yet.</span>`;
    errEl.innerHTML = '';
    createBtn.style.display = '';
    return;
  }
  createBtn.style.display = 'none';
  countEl.textContent = String(st.skills.length) + (st.errors.length ? ` · ${st.errors.length}⚠` : '');

  const loaded = new Set(st.loaded || []);
  listEl.innerHTML = st.skills.length
    ? st.skills.map(s => {
        const mark = loaded.has(s.name)
          ? ' <span style="color:var(--sp-accent);" title="The model loaded this skill in this conversation">● loaded</span>'
          : '';
        return `<div title="${escHtml(s.desc)}">${escHtml(s.name)}${mark}<div style="color:var(--sp-text-dim); font-size:0.95em; padding-left:0.4rem;">${escHtml(s.desc.length > 70 ? s.desc.slice(0, 70) + '…' : s.desc)}</div></div>`;
      }).join('')
    : `<span style="color:var(--sp-text-dim);">No valid skills — add ${escHtml(SandpieContext.SKILLS_DIR)}/&lt;name&gt;/SKILL.md with frontmatter.</span>`;
  errEl.innerHTML = st.errors.map(e => `<div title="Flagged automatically — not loadable until fixed">⚠ ${escHtml(e)}</div>`).join('');
}

async function render() {
  const T = SandpieTokens;
  if (typeof T === 'undefined') return;

  const convEl = document.getElementById('ctxConvTokens');
  const barEl = document.getElementById('ctxConvBar');
  const pctEl = document.getElementById('ctxConvPct');
  const weekEl = document.getElementById('ctxWeekTokens');
  if (!convEl) return;

  const convTokens = await T.conversationTokens();
  const window_ = T.contextWindow();
  const estimated = T.isEstimated();

  convEl.textContent = fmtTokens(convTokens) + (estimated ? ' ~' : '');
  convEl.title = estimated
    ? 'Estimated (provider did not report usage)'
    : 'Reported by the provider';

  let badge = fmtTokens(convTokens);
  if (window_) {
    const pct = Math.min(100, (convTokens / window_) * 100);
    barEl.style.width = pct.toFixed(1) + '%';
    barEl.style.background = pct > 90 ? 'var(--sp-accent-neg, #e06c75)' : 'var(--sp-accent)';
    barEl.parentElement.style.visibility = 'visible';
    pctEl.textContent = `${pct.toFixed(pct < 10 ? 1 : 0)}% used · ${fmtTokens(window_ - convTokens)} left of ${fmtTokens(window_)}`;
    badge = `${pct.toFixed(0)}%`;
  } else {
    barEl.parentElement.style.visibility = 'hidden';
    pctEl.textContent = 'Context window unknown for this model';
  }

  if (weekEl) weekEl.textContent = fmtTokens(T.weeklyTotal());

  if (typeof SandpieMenu !== 'undefined') SandpieMenu.updateBadge('contextSection', badge);
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
      <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.25rem;">
        <span style="color:var(--sp-text-dim);">Conversation</span>
        <span id="ctxConvTokens" style="font-variant-numeric:tabular-nums;">–</span>
      </div>
      <div style="height:6px; border-radius:3px; background:var(--sp-border); overflow:hidden; visibility:hidden;">
        <div id="ctxConvBar" style="height:100%; width:0%; background:var(--sp-accent); transition:width 0.3s;"></div>
      </div>
      <p id="ctxConvPct" style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.3rem 0 0;"></p>
      <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-top:0.7rem;">
        <span style="color:var(--sp-text-dim);">This week (7d)</span>
        <span id="ctxWeekTokens" style="font-variant-numeric:tabular-nums;">–</span>
      </div>
      <div style="border-top:1px solid var(--sp-border); margin-top:0.8rem; padding-top:0.6rem;">
        <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
          <span style="color:var(--sp-text-dim);">Skills</span>
          <span id="ctxSkillCount" style="font-variant-numeric:tabular-nums;">–</span>
        </div>
        <div id="ctxSkillList" style="font-size:0.72rem; line-height:1.6; margin-top:0.25rem;"></div>
        <div id="ctxSkillErrors" style="font-size:0.7rem; color:var(--sp-accent-neg, #e06c75); margin-top:0.25rem;"></div>
        <button id="ctxSkillCreate" style="display:none; margin-top:0.4rem; font-size:0.7rem; padding:0.2rem 0.5rem; background:transparent; color:var(--sp-text-dim); border:1px solid var(--sp-border); border-radius:4px; cursor:pointer;">Create example skill
      </div>
    `,
    onRender(bodyEl) {
      if (!_unsubscribe) _unsubscribe = SandpieTokens.subscribe(render);
      if (!_unsubscribeSkills) {
        _unsubscribeSkills = SandpieContext.subscribe(renderSkills);
        const btn = document.getElementById('ctxSkillCreate');
        if (btn) btn.onclick = async () => { await SandpieContext.scaffold(); renderSkills(); };
      }
      render();
      renderSkills();
    }
  });

  console.log('Context module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
