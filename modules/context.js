
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

  // Reported-only conversation size. Returns the provider's authoritative token
  // usage for a conversation (its last-turn prompt+completion), or 0 when the
  // provider has not reported any usage yet. There is NO client-side estimate:
  // every backend that has a real tokenizer (the API providers AND the local
  // WebGPU engine) emits a `usage` event, which recordUsage() persists here.
  // convId defaults to the active conversation so existing call sites keep working;
  // pass an explicit id to measure a BACKGROUND conversation (compaction runs per
  // conversation regardless of which one is on screen).
  async function conversationTokens(convId) {
    convId = convId || localStorage.getItem('sandpie-active-conv');
    if (!convId) return 0;
    try {
      const stored = localStorage.getItem(USAGE_PREFIX + convId);
      if (stored) return usageTotal(JSON.parse(stored));
    } catch {}
    try {
      const text = await window.opfs.read('sandpie/conversations/' + convId + '.json');
      const data = JSON.parse(text);
      if (data.usage) return usageTotal(data.usage);
    } catch {}
    return 0;
  }

  // The single source of truth for "how full is the context window" — reported
  // tokens ÷ the active provider's window, as a percentage. null when the window
  // is unknown or nothing has been reported. The compaction trigger, the live ctx
  // counter, and the context popup all read this so they can never disagree.
  async function contextPct(convId) {
    const w = contextWindow();
    if (!w) return null;
    const used = await conversationTokens(convId);
    if (!used) return null;
    return (used / w) * 100;
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
    recordUsage, forget, conversationTokens, contextPct,
    weeklyTotal, contextWindow, subscribe, notify,
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
 * Wires provider-reported token usage into SandpieTokens (via the tokens:record
 * event). There is no sidebar section: per-conversation context size lives in a
 * click popup on each chat's own ctx counter (conversations.js openContextPopup),
 * driven by SandpieTokens.conversationTokens — real reported usage, never an
 * estimate.
 *
 * Usage: <script type="module" src="modules/context.js"></script>
 */

function init() {
  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('tokens:record', ({ convId, usage }) => {
      SandpieTokens.recordUsage(convId, usage);
    });
    return;
  }
  setTimeout(init, 500);   // Sandpie.events not ready yet
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
