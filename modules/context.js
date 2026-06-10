
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

  async function conversationTokens() {
    const convId = localStorage.getItem('sandpie-active-conv');
    if (!convId) return 0;
    try {
      const stored = localStorage.getItem(USAGE_PREFIX + convId);
      if (stored) return usageTotal(JSON.parse(stored));
    } catch {}
    try {
      const text = await window.opfs.read('_conversations/' + convId + '.json');
      const data = JSON.parse(text);
      if (data.usage) return usageTotal(data.usage);
      if (data.messages) return estimateTokens(data.messages);
    } catch {}
    return 0;
  }

  function isEstimated() {
    const convId = localStorage.getItem('sandpie-active-conv');
    return !convId || !localStorage.getItem(USAGE_PREFIX + convId);
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

  function subscribe(cb) { listeners.add(cb); return () => listeners.delete(cb); }
  function notify() { for (const cb of listeners) { try { cb(); } catch (e) { console.warn(e); } } }

  return {
    recordUsage, conversationTokens, isEstimated, weeklyTotal,
    contextWindow, subscribe, notify,
  };
})();
window.SandpieTokens = SandpieTokens;

/* =============================================================================
   SandpieContext — skills: enforced index + model-driven loading

   OPFS layout:
     skills/index.md          enforced index: one table | Skill | When to use | Path |
     skills/<name>/SKILL.md   the skill's instructions (folder may hold support files)

   Selection is the MODEL's decision, not a keyword match. Every send injects the
   index (skill name + a "when to use" description + path) into the system prompt;
   when a request matches a description — by intent, not exact words — the model
   calls the `load_skill` tool, which returns that skill's SKILL.md as a tool
   result. This routes relevance through comprehension, so synonyms ("ship it to
   prod") and intent expressed in an assistant turn both work, which literal tag
   matching could never cover reliably.

   The index is read from OPFS fresh on every send (no cache to invalidate). The
   tool runs in the service worker (sandpie.js → tool_load_skill); this module
   owns the index format, the system-prompt block, and the sidebar view.
   ============================================================================= */
const SandpieContext = (() => {
  const INDEX_PATH = 'skills/index.md';
  const SKILL_FILE = 'SKILL.md';
  const DESC_CAP = 300;           // chars of description shown in the index row
  const NAME_RE = /^[a-z0-9][a-z0-9_-]*$/;
  const listeners = new Set();

  // Last computed state, for the sidebar: {exists, skills, errors, loaded}
  let last = { exists: false, skills: [], errors: [], loaded: [] };

  const stripCell = c => String(c).replace(/^[\s`*\[]+|[\s`*\]]+$/g, '');

  function normSkillPath(p) {
    let s = stripCell(p).replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
    if (/^files\//i.test(s)) s = s.slice(6); // tolerate the model-visible /files/ prefix
    return s;
  }

  // Enforced parse: rows are ignored until the | Skill | When to use | Path |
  // header; every malformed row is skipped and reported, never silently accepted.
  function parseIndex(text) {
    const skills = [], errors = [];
    const seen = new Set();
    let headerSeen = false;
    const lines = String(text).split('\n');
    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i].trim();
      if (!raw.startsWith('|')) continue;
      const cells = raw.replace(/^\|/, '').replace(/\|+$/, '').split('|').map(s => s.trim());
      if (cells.every(c => /^:?-+:?$/.test(c))) continue; // table separator row
      if (!headerSeen) {
        const h = cells.map(c => c.toLowerCase());
        if (cells.length === 3 && h[0].includes('skill') && (h[1].includes('use') || h[1].includes('desc')) && h[2].includes('path')) {
          headerSeen = true;
        } else {
          errors.push(`line ${i + 1}: ignored — rows only count after the header | Skill | When to use | Path |`);
        }
        continue;
      }
      if (cells.length !== 3) { errors.push(`line ${i + 1}: expected 3 columns, got ${cells.length}`); continue; }
      const name = stripCell(cells[0]).toLowerCase();
      if (!NAME_RE.test(name)) { errors.push(`line ${i + 1}: invalid skill name "${stripCell(cells[0])}" (use a-z 0-9 _ -)`); continue; }
      if (seen.has(name)) { errors.push(`line ${i + 1}: duplicate skill "${name}"`); continue; }
      const desc = stripCell(cells[1]).replace(/\s+/g, ' ');
      if (!desc) { errors.push(`line ${i + 1}: skill "${name}" has no "when to use" description — the model needs it to decide when to load`); continue; }
      const path = normSkillPath(cells[2]);
      if (!path) { errors.push(`line ${i + 1}: skill "${name}" has no path`); continue; }
      seen.add(name);
      skills.push({ name, desc, path, line: i + 1 });
    }
    if (!headerSeen) errors.push(`no header row | Skill | When to use | Path | found in ${INDEX_PATH}`);
    return { skills, errors };
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

  async function readIndex() {
    let text;
    try { text = await opfs.read(INDEX_PATH); }
    catch { return { exists: false, skills: [], errors: [] }; }
    return { exists: true, ...parseIndex(text) };
  }

  const clip = s => s.length > DESC_CAP ? s.slice(0, DESC_CAP) + '…' : s;

  // The block conversations.js appends to the system prompt on every send.
  // Returns '' (zero tokens) when skills/index.md doesn't exist.
  async function skillBlock(convMessages) {
    const idx = await readIndex();
    const loaded = idx.exists ? loadedSkillNames(convMessages) : new Set();
    last = { ...idx, loaded: [...loaded] };
    notify();
    if (!idx.exists) return '';

    const lines = ['', '', '# Skills'];
    lines.push(
      `\`${INDEX_PATH}\` lists saved playbooks for specific tasks. Each row is a skill, ` +
      `when to use it, and where its full instructions live. ` +
      `**When the user's request matches a skill's "when to use" — by intent, not exact wording — call the \`load_skill\` tool with that skill's name BEFORE you start, then follow the instructions it returns.** ` +
      `If several could apply, load the best match; if none clearly fit, just proceed. ` +
      `To add a skill: create \`<path>/${SKILL_FILE}\` and append a row to ${INDEX_PATH} (name = [a-z0-9_-], unique; a "when to use" description; a folder path).`,
    );
    lines.push('', '| Skill | When to use | Path |', '|---|---|---|');
    for (const s of idx.skills) {
      const mark = loaded.has(s.name) ? ' _(already loaded above)_' : '';
      lines.push(`| ${s.name} | ${clip(s.desc)}${mark} | ${s.path} |`);
    }
    if (!idx.skills.length) lines.push('| _none yet_ | — | — |');
    if (idx.errors.length) {
      lines.push('', `Index problems (${idx.errors.length}) — fix ${INDEX_PATH} if the user asks about skills:`);
      for (const e of idx.errors.slice(0, 3)) lines.push(`- ${e}`);
    }
    return lines.join('\n');
  }

  // Sidebar view: fresh read + SKILL.md existence checks + which skills the
  // active conversation has already loaded.
  async function inspect(convMessages) {
    const idx = await readIndex();
    for (const s of idx.skills) {
      s.missing = !(await opfs.exists(s.path + '/' + SKILL_FILE));
      if (s.missing) idx.errors.push(`skill "${s.name}": ${s.path}/${SKILL_FILE} not found`);
    }
    last = { ...idx, loaded: idx.exists ? [...loadedSkillNames(convMessages)] : [] };
    return last;
  }

  const SCAFFOLD = `# Sandpie skills index

Enforced format: one markdown table, header exactly | Skill | When to use | Path |.
- Skill: lowercase identifier (a-z, 0-9, _ or -), unique.
- When to use: a plain-language description of the tasks this skill covers. The
  model reads this to decide when to call load_skill — write it the way you'd
  describe the job to a teammate ("Deploying the app to production: bump the
  version, commit, push, verify the CI run").
- Path: folder relative to /files/ that contains SKILL.md, e.g. skills/my_skill

| Skill | When to use | Path |
|---|---|---|
`;

  async function scaffold() {
    if (await opfs.exists(INDEX_PATH)) return;
    await opfs.write(INDEX_PATH, SCAFFOLD);
    if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', INDEX_PATH);
    try { Sandpie.refreshFiles(); } catch {}
  }

  function subscribe(cb) { listeners.add(cb); return () => listeners.delete(cb); }
  function notify() { for (const cb of listeners) { try { cb(); } catch (e) { console.warn(e); } } }

  return {
    INDEX_PATH, skillBlock, inspect, scaffold, subscribe,
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
    listEl.innerHTML = `<span style="color:var(--sp-text-dim);">No ${escHtml(SandpieContext.INDEX_PATH)} yet.</span>`;
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
        const miss = s.missing
          ? ' <span style="color:var(--sp-accent-neg, #e06c75);" title="SKILL.md not found at this path">missing</span>'
          : '';
        return `<div title="${escHtml(s.desc)}">${escHtml(s.name)}${mark}${miss}<div style="color:var(--sp-text-dim); font-size:0.95em; padding-left:0.4rem;">${escHtml(s.desc.length > 70 ? s.desc.slice(0, 70) + '…' : s.desc)}</div></div>`;
      }).join('')
    : `<span style="color:var(--sp-text-dim);">Index is empty — add rows to ${escHtml(SandpieContext.INDEX_PATH)}.</span>`;
  errEl.innerHTML = st.errors.map(e => `<div>⚠ ${escHtml(e)}</div>`).join('');
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
        <button id="ctxSkillCreate" style="display:none; margin-top:0.4rem; font-size:0.7rem; padding:0.2rem 0.5rem; background:transparent; color:var(--sp-text-dim); border:1px solid var(--sp-border); border-radius:4px; cursor:pointer;">Create skills/index.md</button>
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
