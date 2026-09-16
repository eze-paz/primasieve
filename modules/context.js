
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
    const u = await _readUsage(convId);
    return u ? usageTotal(u) : 0;
  }
  // The raw stored usage object for a conversation (or null). Kept separate from
  // conversationTokens so contextPct can also read the window the usage was
  // recorded against (_window, stamped by recordUsage).
  async function _readUsage(convId) {
    convId = convId || localStorage.getItem('sandpie-active-conv');
    if (!convId) return null;
    try {
      const stored = localStorage.getItem(USAGE_PREFIX + convId);
      if (stored) { const u = JSON.parse(stored); if (u) return u; }
    } catch {}
    // Disk fallback: new format stores usage in the meta sidecar; legacy convs in
    // the monolithic .json. Try both (archived paths included).
    const base = 'sandpie/conversations/';
    for (const rel of [convId + '.meta.json', 'archived/' + convId + '.meta.json', convId + '.json', 'archived/' + convId + '.json']) {
      try {
        const data = JSON.parse(await window.opfs.read(base + rel));
        if (data && data.usage) return data.usage;
      } catch {}
    }
    return null;
  }

  // The single source of truth for "how full is the context window" — reported
  // tokens ÷ the window, as a percentage. null when the window is unknown or
  // nothing has been reported. The compaction trigger, the live ctx counter, and
  // the context popup all read this so they can never disagree.
  //
  // Window choice: the usage was measured under whatever provider the turn ran
  // on, so its stamped _window is the honest denominator — NOT whatever provider
  // happens to be selected right now. We take min(recorded, active): switching
  // DOWN to a smaller-window model must still trigger compaction (the next send
  // really will hit the smaller window), but switching UP to a bigger one must
  // not keep reporting the old model's inflated %. Legacy usage without a stamp
  // falls back to the active window (old behavior).
  async function contextPct(convId) {
    const u = await _readUsage(convId);
    if (!u) return null;
    const used = usageTotal(u);
    if (!used) return null;
    const rec = (u._window > 0) ? u._window : null;
    const act = contextWindow(convId);
    const w = (rec && act) ? Math.min(rec, act) : (rec || act);
    if (!w) return null;
    return (used / w) * 100;
  }

  function contextWindow(convId) {
    // Per-conversation: resolve THIS conversation's provider (falls back to the
    // default provider when the conv has no bound id). getActive() is a legacy
    // alias for defaultProvider() and would report the wrong model's window.
    let ap = null;
    try { ap = (typeof SandpieProviders !== 'undefined' && SandpieProviders.resolve) ? SandpieProviders.resolve(convId) : null; }
    catch (_) { ap = null; }
    if (!ap) { try { ap = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null; } catch (_) {} }
    return (ap && ap.contextWindow > 0) ? ap.contextWindow : null;
  }

  function recordUsage(convId, usage) {
    if (!usage) return;
    // Stamp the context window the usage was measured against, so contextPct
    // keeps an honest denominator after the user switches the active provider.
    try { const w = contextWindow(convId); if (w) usage = { ...usage, _window: w }; } catch {}
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

  // Skills are ALWAYS active (toggle removed 2026-09-16): an installed skill is
  // always listed in the prompt's skill table. The old per-skill enable/disable
  // flag lived in localStorage under 'sandpie-skills-disabled' — that key is now
  // inert; clear it so stale disabled lists can't linger on any device.
  const SKILLS_DISABLED_KEY = 'sandpie-skills-disabled';
  function isSkillEnabled() { return true; }
  try { localStorage.removeItem(SKILLS_DISABLED_KEY); } catch (_) {}
  // Save an edited SKILL.md back to OPFS (the settings inline editor uses this).
  async function saveSkill(file, text) {
    await opfs.write(file, text);
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', file); } catch (_) {}
    notify();
  }

  // Last computed state, for the sidebar: {exists, skills, errors, loaded}
  let last = { exists: false, skills: [], errors: [], loaded: [] };

  // Parse leading YAML-ish frontmatter (--- … ---). Deterministic and
  // dependency-free: single-line `key: value` scalars plus YAML BLOCK scalars —
  // `key: >` (folded), `key: |` (literal) and bare `key:` followed by indented
  // lines — because skill descriptions commonly span several lines that way.
  // Returns null when there's no frontmatter block at all.
  function parseFrontmatter(text) {
    const m = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(text);
    if (!m) return null;
    const fm = {};
    const lines = m[1].split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const kv = /^([A-Za-z][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*)$/.exec(lines[i]);
      if (!kv) continue;
      let v = kv[2].trim();
      // Block scalar ('>' folded, '|' literal, bare 'key:' with indented body):
      // the value is the run of indented lines that follows. Folded joins with
      // spaces, literal with newlines (the -/+ chomping hints are ignored — the
      // result is trimmed anyway).
      if (v === '' || /^[>|][-+]?$/.test(v)) {
        const parts = [];
        while (i + 1 < lines.length) {
          const next = lines[i + 1];
          if (!/^[ \t]/.test(next) || next.trim() === '') break;
          parts.push(next.trim());
          i++;
        }
        v = v[0] === '|' ? parts.join('\n') : parts.join(' ');
      }
      if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
      fm[kv[1].toLowerCase()] = v;
    }
    return fm;
  }

  // Clean a frontmatter description into model-ready text: drop everything up to
  // and including the leading run of whitespace/symbols before the first
  // alphanumeric character (a leftover block-scalar indicator like '>', a stray
  // quote, a '---' fragment), then collapse internal whitespace. A value with no
  // alphanumeric content at all ('>', '---') becomes '' and trips the
  // missing-description guard — junk can never be advertised as a description.
  // Unicode-aware ([\p{L}\p{N}]) so accented first letters survive.
  function cleanDescription(s) {
    const flat = String(s || '').replace(/\s+/g, ' ');
    const first = flat.search(/[\p{L}\p{N}]/u);
    return first >= 0 ? flat.slice(first).trim() : '';
  }

  // Minimum usable description length: fewer alphanumeric characters than this is
  // junk ('>', '--', 'Short.'), not guidance the model can decide on — such skills
  // are flagged (never advertised) exactly like missing descriptions.
  const MIN_DESC_ALNUM = 10;
  function descAlnum(s) { const m = String(s || '').match(/[\p{L}\p{N}]/gu); return m ? m.length : 0; }

  // Walk skills/*/ and derive the index from each folder's SKILL.md frontmatter.
  // Every problem is reported in `errors`; only fully-valid skills reach `skills`.
  async function scanSkills() {
    const skills = [], errors = [];
    let entries = null;
    try { entries = await opfs.listDir(SKILLS_DIR); } catch (_) {} // no skills/ dir yet
    for (const e of (entries || [])) {
      if (e.kind !== 'directory') continue; // stray files under skills/ are ignored
      const folder = e.name;                // the folder name IS the skill name
      // web_search was promoted from a skill to a built-in worker TOOL
      // (2026-09-01: OpenRouter/Exa primary + multi-engine scrape fallback). A
      // leftover skill by that name would only shadow the tool with the old
      // flaky instructions, so it is retired on sight — deleted locally and in
      // the workspace cloud (same 'file:deleted' handshake sharing.js uses).
      if (/^(web[-_]?search)$/i.test(folder)) {
        const dir = `${SKILLS_DIR}/${folder}`;
        try {
          await opfs.remove(dir);
          try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:deleted', dir); } catch (_) {}
          console.info('[skills] "' + folder + '" skill removed — web_search is now a built-in tool');
        } catch (_) {}
        continue;
      }
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
      const desc = cleanDescription(fm.description);
      if (!desc) {
        const hint = fm.description
          ? ' — description resolves to empty text; if it uses a YAML `>`/`|` block scalar, the text must sit on indented lines under the indicator'
          : '';
        errors.push(`${file} — missing "description"${hint}; the model needs it to decide when to load this skill`);
        continue;
      }
      const dn = descAlnum(desc);
      if (dn < MIN_DESC_ALNUM) {
        errors.push(`${file} — description is only ${dn} characters of real text (need ≥ ${MIN_DESC_ALNUM}); the model can't decide when to load this skill`);
        continue;
      }
      skills.push({ name: folder, desc, path, file, enabled: isSkillEnabled(folder) });
    }
    // Shared skills: installed packages under sandpie/shared-installed/<id>/ that
    // carry a SKILL.md. Discovered + advertised like local skills; load_skill
    // resolves the shared path first. The HUB WINS a name collision (compared
    // with '-'/'_' folded — legacy shares slugged web_search → web-search): the
    // sharing sync deletes the local twin outright, and this replacement covers
    // the window before that pass runs, so a doomed local copy is never
    // advertised alongside its hub replacement.
    const foldName = (n) => String(n).replace(/_/g, '-');
    try {
      for (const e of await opfs.listDir('sandpie/shared-installed')) {
        if (e.kind !== 'directory' || !NAME_RE.test(e.name)) continue;
        const path = 'sandpie/shared-installed/' + e.name, file = path + '/' + SKILL_FILE;
        let text; try { text = await opfs.read(file); } catch { continue; }   // not a skill package
        const fm = parseFrontmatter(text);
        const desc = cleanDescription(fm && fm.description);
        if (!desc || descAlnum(desc) < MIN_DESC_ALNUM) continue;
        const dup = skills.findIndex(s => foldName(s.name) === foldName(e.name));
        if (dup >= 0) skills.splice(dup, 1);
        skills.push({ name: e.name, desc, path, file, enabled: isSkillEnabled(e.name), shared: true });
      }
    } catch (_) {}
    skills.sort((a, b) => a.name.localeCompare(b.name));
    return { exists: !!(entries || skills.length), skills, errors };
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
    const activeSkills = idx.skills;   // all installed skills are always active (toggle removed 2026-09-16)
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
    isSkillEnabled, saveSkill,
    parseFrontmatter, cleanDescription, descAlnum,
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
