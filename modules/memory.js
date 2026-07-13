/**
 * Memory module for Sandpie — durable, cross-conversation facts.
 *
 * Modeled on Claude Code's own memory: one fact per `.md` file under
 * sandpie/memory/, each with YAML-ish frontmatter (name, description, type,
 * created, last_verified). There is NO lazy fetch and NO recall tool — the
 * facts are small, so ALL of them are injected into the system prompt every
 * turn (systemBlock, wired into buildSystemPrompt). The store is kept bounded
 * by an automatic consolidation/prune pass that fires when the injected block
 * grows past the token budget.
 *
 *   - Capture: the `remember` tool (worker) writes a fact file (gated by its own
 *     description: durable + non-derivable). Enabled by default.
 *   - Injection: systemBlock() concatenates every fact into the prompt.
 *   - Prune: maybeConsolidate() runs an LLM merge/dedupe/prune pass over budget,
 *     tombstoning removed facts to sandpie/memory/.pruned/ (recoverable).
 *   - Commands: >>> memory [show <name> | consolidate], >>> forget <name>.
 *
 * Config (enabled, budget threshold) lives in localStorage; a "Memory" section
 * in the Settings modal edits it.
 */
const SandpieMemory = (function () {
  'use strict';

  const K_ENABLED   = 'sandpie-memory-enabled';     // '0' | '1' (unset = default ON)
  const K_THRESHOLD = 'sandpie-memory-threshold';    // integer tokens

  const DEFAULTS = { enabled: true, threshold: 5000 };
  const MIN_THRESHOLD = 500;

  const DIR = 'sandpie/memory';
  const PRUNED = DIR + '/.pruned';
  const VALID_TYPES = ['user', 'feedback', 'project', 'reference'];

  const _int = (key, fallback) => { const v = parseInt(localStorage.getItem(key) || '', 10); return Number.isFinite(v) ? v : fallback; };

  function isEnabled() { const v = localStorage.getItem(K_ENABLED); return v == null ? DEFAULTS.enabled : v === '1'; }
  function threshold() { return Math.max(MIN_THRESHOLD, _int(K_THRESHOLD, DEFAULTS.threshold)); }
  function config() { return { enabled: isEnabled(), threshold: threshold() }; }

  // ---- store ----------------------------------------------------------------
  const estTokens = (s) => Math.ceil((s || '').length / 4);
  const _today = () => new Date().toISOString().slice(0, 10);
  function _slug(s) { return String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'note'; }
  const FM_RE = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/;

  function _parse(text, file) {
    const fm = {}; let body = text;
    const m = FM_RE.exec(text);
    if (m) {
      for (const line of m[1].split(/\r?\n/)) {
        const kv = /^([A-Za-z][\w-]*)[ \t]*:[ \t]*(.*)$/.exec(line);
        if (kv) { let v = kv[2].trim(); if ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'"))) v = v.slice(1, -1); fm[kv[1].toLowerCase()] = v; }
      }
      body = text.slice(m[0].length);
    }
    body = body.trim();
    const name = fm.name || (file ? file.replace(/\.md$/, '') : 'note');
    const description = fm.description || (body.split(/\r?\n/)[0] || '').slice(0, 120);
    const type = VALID_TYPES.includes(fm.type) ? fm.type : 'reference';
    return { name, description, type, created: fm.created || '', last_verified: fm.last_verified || '', body, file: file || (name + '.md') };
  }

  async function list() {
    if (typeof opfs === 'undefined') return [];
    let entries = [];
    try { entries = await opfs.listDir(DIR); } catch (_) { return []; }   // dir absent ⇒ empty
    const out = [];
    for (const e of entries) {
      // memory facts only: skip MEMORY.md and the augmentations lessons files
      // (<project>.lessons.md) that also live in this folder and end in .md.
      if (e.kind !== 'file' || !e.name.endsWith('.md') || e.name === 'MEMORY.md' || e.name.endsWith('.lessons.md')) continue;
      try { out.push(_parse(await opfs.read(DIR + '/' + e.name), e.name)); } catch (_) {}
    }
    out.sort((a, b) => a.name.localeCompare(b.name));
    return out;
  }

  function _usedTokens(facts) { return facts.reduce((s, f) => s + estTokens(f.body) + estTokens(f.description), 0); }

  function notify() { try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('memory:changed', {}); } catch (_) {} }

  async function _tombstone(f) {
    const src = DIR + '/' + f.file;
    try { await opfs.write(PRUNED + '/' + f.file, await opfs.read(src)); } catch (_) {}   // local-only recovery copy
    try { await opfs.remove(src); } catch (_) {}
    // Propagate the delete to Dropbox — opfs.remove is OPFS-only, so without this
    // the file stays in the cloud and re-downloads on the next sync (prunes and
    // >>> forget would silently un-delete). file:deleted → onFileDeleted → del().
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:deleted', src); } catch (_) {}
  }

  // ---- injection ------------------------------------------------------------
  // Char length of the block last produced by systemBlock(), so the (synchronous)
  // context-token estimator in context.js can attribute memory's context cost
  // without re-reading OPFS. buildSystemPrompt calls systemBlock() every send, so
  // this stays fresh; 0 when memory is off/empty.
  let _lastBlockChars = 0;
  function blockChars() { return _lastBlockChars; }
  async function systemBlock() {
    if (!isEnabled()) { _lastBlockChars = 0; return ''; }
    const facts = await list();
    // Inject the instruction ALWAYS — even with an empty store. Gating it behind
    // "facts already exist" was a cold-start dead zone: no facts → no instruction
    // → the model never saved the first one → memory stayed empty forever. The
    // capability + expectation must be visible from turn one.
    const lines = ['', '', '# Memory',
      "Durable facts you've saved across conversations with the remember tool. Treat them as true unless the current conversation contradicts them. Memory reflects what was true WHEN it was written — every fact shows its verification age (verified Nd ago); judge staleness yourself: the older, the more you should re-check before relying on it. When a tool observation CONFIRMS an aging fact still holds, re-save it with remember (same name, same content) to bump its verification date; when an observation CONTRADICTS one, update or forget it immediately. [[name]] inside a body is a link to the fact with that name slug (dangling links mark facts worth writing). As soon as you learn something durable and non-derivable — a stable user preference, standing feedback on how to work, or lasting project context (e.g. where a project's real source tree lives, a key decision, a gotcha) — SAVE IT with the remember tool right then, without waiting for the task to end."];
    if (!facts.length) {
      lines.push('', '_(No memories saved yet. Save the first durable, non-derivable fact you learn this session.)_');
    } else {
      // Verification age on EVERY fact — raw signal, no threshold: the model (which
      // knows "now" from the prompt header) judges staleness itself. Falls back to
      // created when last_verified is absent; no date at all → "unverified".
      const now = Date.now();
      for (const f of facts) {
        let badge = ' · unverified';
        const ref = Date.parse(f.last_verified || f.created || '');
        if (Number.isFinite(ref)) {
          const days = Math.max(0, Math.floor((now - ref) / 86400000));
          badge = days === 0 ? ' · verified today' : ` · verified ${days}d ago`;
        }
        lines.push('', `## ${f.description} _(${f.type}${badge})_`, f.body);
      }
    }
    const block = lines.join('\n');
    _lastBlockChars = block.length;
    return block;
  }

  // ---- consolidation / prune ------------------------------------------------
  const CONSOLIDATE_PROMPT = [
    "You are sandpie's memory consolidator. You receive the current memory store as one JSON object per line, each: {name, description, type, created, last_verified, body}. Rewrite it into a CLEANER set and return the desired end-state.",
    "",
    "Rules:",
    "- MERGE duplicates and near-duplicates into one fact (union the detail, keep the clearest description).",
    "- RESOLVE contradictions: keep the newer / more-recently-verified fact, drop the loser. Never keep both sides of a contradiction.",
    "- DELETE obsolete facts: superseded, or that point at a file/function/flag/project that has clearly ended.",
    "- DROP derivable facts: anything recoverable from source code or git history does not belong in memory.",
    "- PROTECT by type: NEVER drop a user or feedback fact merely to save space — they capture who the user is and how they want you to work. This pass may be running because the store exceeded its size budget; when you must shrink it, prune in THIS order: obsolete/stale first, then reference, then project. Drop a user or feedback fact ONLY when it is directly contradicted or clearly obsolete, never just to fit.",
    "- TIGHTEN: compress each body to the durable essence.",
    "- LINKS: [[name]] in a body references another fact by its name slug. Preserve links whose target you keep; when you MERGE facts, retarget links that pointed at the absorbed name to the surviving name; add [[links]] between clearly related facts you keep. A dangling link (no fact with that name) is allowed — it marks a fact worth writing — but do not invent new dangling links.",
    "- Keep type one of: user, feedback, project, reference. Preserve created. PRESERVE last_verified — surviving this pass is NOT verification; only a real-world re-check bumps it. When merging facts, the merged fact takes the NEWEST last_verified among its sources.",
    "",
    "Output ONLY a JSON array of the kept/merged facts: [{name, description, type, created, last_verified, body}, ...]. No prose, no markdown fences.",
  ].join('\n');

  function _extractJsonArray(s) {
    if (!s) return null;
    try { return JSON.parse(s); } catch (_) {}
    const a = s.indexOf('['), b = s.lastIndexOf(']');
    if (a >= 0 && b > a) { try { return JSON.parse(s.slice(a, b + 1)); } catch (_) {} }
    return null;
  }

  let _consolidating = false;
  async function consolidate(facts) {
    if (_consolidating) return { ok: false, reason: 'already running' };
    facts = facts || await list();
    if (facts.length < 2) return { ok: false, reason: 'nothing to consolidate' };
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return { ok: false, reason: 'no completion provider' };
    _consolidating = true;
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('memory:consolidate-start', {}); } catch (_) {}
    try {
      const input = facts.map(f => JSON.stringify({ name: f.name, description: f.description, type: f.type, created: f.created, last_verified: f.last_verified, body: f.body })).join('\n');
      const out = await SandpieProviders.complete({ system: CONSOLIDATE_PROMPT, user: input, maxTokens: 4096 });
      const arr = _extractJsonArray(out);
      if (!Array.isArray(arr) || !arr.length) return { ok: false, reason: 'consolidator returned unusable output' };
      const today = _today();
      const keep = new Set();
      for (const f of arr) {
        if (!f || !f.body || !String(f.body).trim()) continue;
        const slug = _slug(f.name || f.description || 'note');
        keep.add(slug);
        const t = VALID_TYPES.includes(f.type) ? f.type : 'reference';
        const desc = String(f.description || '').replace(/\s*\n\s*/g, ' ').trim();
        // last_verified comes from the consolidator (told to preserve / take newest
        // on merge) — NOT stamped to today: surviving consolidation isn't verification.
        const lv = String(f.last_verified || f.created || today).slice(0, 10);
        const text = `---\nname: ${slug}\ndescription: ${desc}\ntype: ${t}\ncreated: ${f.created || today}\nlast_verified: ${lv}\n---\n` + String(f.body).trim() + '\n';
        const fpath = DIR + '/' + slug + '.md';
        try {
          await opfs.write(fpath, text);
          // Mark dirty so the merged/rewritten fact uploads and survives the sync
          // orphan-cleanup — same reason tool_remember posts sw-opfs-changed.
          if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', fpath);
        } catch (_) {}
      }
      // Deletions now propagate to Dropbox (see _tombstone), so an over-aggressive
      // LLM that drops facts it shouldn't would lose them permanently. Safety guard:
      // if a single pass wants to remove more than 60% of the store (beyond ~3),
      // treat the output as untrustworthy — keep the merged improvements we just
      // wrote, but do NOT delete the originals this pass.
      const removeList = facts.filter(f => !keep.has(_slug(f.name)));
      let removed = 0, guarded = false;
      if (removeList.length > Math.max(3, facts.length * 0.6)) {
        guarded = true;
        console.warn('[sandpie] memory consolidation would remove', removeList.length, 'of', facts.length, 'facts — skipping deletion as a safety guard');
      } else {
        for (const f of removeList) { await _tombstone(f); removed++; }
      }
      notify();
      return { ok: true, before: facts.length, after: keep.size, removed, guarded };
    } catch (e) {
      return { ok: false, reason: (e && e.message) || String(e) };
    } finally {
      _consolidating = false;
      try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('memory:consolidate-end', {}); } catch (_) {}
    }
  }

  // Called on the pre-send path (from buildSystemPrompt). Consolidation now runs
  // whenever the store GREW since the last pass (a new fact is the moment dupes
  // and contradictions appear — refine immediately, don't wait for the budget),
  // and still as a backstop when over the token budget. First sighting of the
  // store only records the baseline (no consolidate-on-app-start churn).
  let _lastCount = -1;   // fact count after the last consolidation (or first sight)
  async function maybeConsolidate() {
    if (_consolidating || !isEnabled()) return;
    const facts = await list();
    if (facts.length < 2) { _lastCount = facts.length; return; }
    if (_lastCount < 0) { _lastCount = facts.length; if (_usedTokens(facts) <= threshold()) return; }
    const grew = facts.length > _lastCount;
    const over = _usedTokens(facts) > threshold();
    if (!grew && !over) return;
    try {
      const r = await consolidate(facts);
      _lastCount = (r && r.ok) ? r.after : facts.length;   // on failure: don't re-hammer every send
    } catch (e) { _lastCount = facts.length; console.warn('[sandpie] memory consolidation failed:', e); }
  }

  // ---- commands -------------------------------------------------------------
  function registerCommands() {
    if (typeof SandpieCommands === 'undefined') return;
    SandpieCommands.register({
      name: 'memory', module: 'core',
      help: 'List remembered facts; "show <name>" for one, "consolidate" to prune now',
      usage: '>>> memory [show <name> | consolidate]',
      async run(text, parts) {
        if (parts[1] === 'consolidate') { const r = await consolidate(); return r.ok ? `Consolidated: ${r.before} → ${r.after} fact(s), ${r.removed} pruned.${r.guarded ? ' (deletion skipped by safety guard — pass looked over-aggressive)' : ''}` : 'Consolidation: ' + (r.reason || 'failed') + '.'; }
        if (parts[1] === 'show') { const f = (await list()).find(x => x.name === parts[2]); return f ? f.body : 'No memory named "' + (parts[2] || '') + '".'; }
        // Default: DIAGNOSE + simulate the real system-prompt injection, so what you
        // see here is exactly what the model gets (systemBlock) — and when it's empty
        // you can tell WHY (disabled / no local files / parse failure).
        const enabled = isEnabled();
        let entries = null;                       // null = folder not present locally
        try { if (typeof opfs !== 'undefined') entries = await opfs.listDir(DIR); } catch (_) { entries = null; }
        const mdFiles = Array.isArray(entries) ? entries.filter(e => e.kind === 'file' && e.name.endsWith('.md') && e.name !== 'MEMORY.md' && !e.name.endsWith('.lessons.md')) : [];
        const facts = await list();
        const used = _usedTokens(facts);
        const header =
          `Memory: ${enabled ? 'ENABLED' : 'DISABLED'}  ·  dir "${DIR}": ` +
          (entries === null ? 'not present locally' : `${mdFiles.length} fact file(s)`) +
          `  ·  ${facts.length} parsed  ·  ~${used}/${threshold()} tokens`;
        const block = await systemBlock();        // the ACTUAL injected text (respects enabled + facts)
        let injected;
        if (!enabled) injected = '\n\n(memory is DISABLED → nothing is injected, even if files exist)';
        else if (!facts.length) injected = entries === null
          ? `\n\n(nothing injected — "${DIR}" has no local files. If Dropbox is connected they re-download on sync; otherwise none saved yet.)`
          : '\n\n(nothing injected — files present but none parsed as facts)';
        else injected = '\n\n──────── injected into system prompt ────────' + block;
        // Also surface the augmentations content that lives in this folder and is
        // injected via a SEPARATE path (augmentations.systemBlock): recent-paths
        // (*.recent-paths.json). Old *.lessons.md files may still exist but are
        // INERT — the lessons injection was replaced by the memory harvester,
        // which writes normal facts (listed above); flag leftovers as removable.
        let aux = '';
        if (Array.isArray(entries)) {
          for (const e of entries) {
            if (e.kind !== 'file') continue;
            try {
              if (e.name.endsWith('.recent-paths.json')) {
                const arr = JSON.parse(await opfs.read(DIR + '/' + e.name) || '[]');
                if (arr.length) aux += `\n\nRecent paths (${e.name}, injected via augmentations):\n` + arr.slice(0, 20).map(p => '  • ' + p).join('\n');
              } else if (e.name.endsWith('.lessons.md')) {
                aux += `\n\n(${e.name}: legacy lessons file — NO LONGER injected; safe to delete)`;
              }
            } catch (_) {}
          }
        }
        return header + injected + aux;
      },
    });
    SandpieCommands.register({
      name: 'forget', module: 'core',
      help: 'Delete a remembered fact by name',
      usage: '>>> forget <name>',
      async run(text, parts) {
        const name = parts[1];
        if (!name) return 'Usage: >>> forget <name> — see names with >>> memory.';
        const f = (await list()).find(x => x.name === name);
        if (!f) return 'No memory named "' + name + '".';
        if (typeof confirm === 'function' && !confirm('Delete memory "' + name + '"?')) return '(cancelled)';
        await _tombstone(f); notify();
        return 'Forgot "' + name + '".';
      },
    });
  }

  // ---- Settings section -----------------------------------------------------
  const HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">Durable facts are remembered across conversations and injected into the model's context automatically. When the remembered facts grow past the budget below, they're auto-consolidated (merged, pruned, de-duplicated) to stay small. Stored locally in this browser only.</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.6rem;">
      <input type="checkbox" id="memEnabled" style="width:auto;"> Enable automatic memory
    </label>
    <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:0.2rem;">
      <label style="font-size:0.78rem; color:var(--sp-text-dim);">Memory budget
        <input type="number" id="memThreshold" min="500" step="500" style="width:6rem; margin-left:0.3rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.15rem 0.3rem;"> tokens
      </label>
      <span id="memStatus" style="font-size:0.7rem; color:var(--sp-text-dim); align-self:center;"></span>
    </div>
    <hr style="border:none; border-top:1px solid var(--sp-border); margin:0.8rem 0;">
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.4rem;"><strong>Recent paths</strong> &mdash; files touched in this project, injected into every prompt.</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.4rem;">
      <input type="checkbox" id="rpEnabled" style="width:auto;"> Enable recent-paths memory
    </label>
    <label style="font-size:0.78rem; color:var(--sp-text-dim); margin-bottom:0.6rem;">Max paths (5–100):
      <input type="number" id="rpCount" min="5" max="100" step="5" style="width:4rem; margin-left:0.3rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.15rem 0.3rem;">
    </label>
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.4rem;"><strong>Auto-harvest</strong> &mdash; automatically saves durable, evidence-backed facts from sessions into memory (shares the memory budget above; refined by consolidation).</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.4rem;">
      <input type="checkbox" id="lessonsEnabled" style="width:auto;"> Enable automatic memory harvest
    </label>
    `;

  let _flashT = null;
  function flash(msg) { const el = document.getElementById('memStatus'); if (!el) return; el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500); }

  function wire(panel) {
    const cfg = config();
    const en = panel.querySelector('#memEnabled');
    const th = panel.querySelector('#memThreshold');
    const rpEn = panel.querySelector('#rpEnabled');
    const rpCnt = panel.querySelector('#rpCount');
    const lsEn = panel.querySelector('#lessonsEnabled');
    if (en) { en.checked = cfg.enabled; en.addEventListener('change', () => { localStorage.setItem(K_ENABLED, en.checked ? '1' : '0'); flash('Saved'); setMemoryDot(); }); }
    if (th) { th.value = cfg.threshold; th.addEventListener('change', () => { const v = Math.max(MIN_THRESHOLD, parseInt(th.value || '', 10) || DEFAULTS.threshold); th.value = v; localStorage.setItem(K_THRESHOLD, String(v)); flash('Saved'); }); }
    if (rpEn) {
      rpEn.checked = localStorage.getItem('sandpie-recent-paths-enabled') !== 'false';
      rpCnt.value = localStorage.getItem('sandpie-recent-paths-count') || '20';
      rpEn.addEventListener('change', () => localStorage.setItem('sandpie-recent-paths-enabled', rpEn.checked ? 'true' : 'false'));
      rpCnt.addEventListener('change', () => { let v = parseInt(rpCnt.value, 10); if (!Number.isFinite(v) || v < 5) v = 5; if (v > 100) v = 100; rpCnt.value = v; localStorage.setItem('sandpie-recent-paths-count', String(v)); });
    }
    if (lsEn) {
      // Same localStorage key as the old lessons toggle, so an existing OFF choice
      // carries over — but it now gates the memory HARVESTER (augmentations
      // distillLessons), whose output lives in the normal memory store/budget.
      lsEn.checked = localStorage.getItem('sandpie-lessons-enabled') !== 'false';
      lsEn.addEventListener('change', () => localStorage.setItem('sandpie-lessons-enabled', lsEn.checked ? 'true' : 'false'));
    }
  }

  let _retry = 0;
  function setMemoryDot() {
    const dot = document.getElementById('memoryDot');
    if (!dot) return;
    const hasMem = isEnabled();
    dot.classList.remove('ok', 'warn', 'err', 'busy');
    dot.classList.add(hasMem ? 'mem' : '');
  }

  function init() {
    registerCommands();
    if (window.SandpieSettings) { SandpieSettings.register({ id: 'memory', title: 'Memory', order: 17, dot: 'memoryDot', render(panel) { panel.innerHTML = HTML; wire(panel); } }); return; }
    if (typeof SandpieMenu !== 'undefined') { SandpieMenu.add('memorySection', { title: 'Memory', dot: 'memoryDot', badge: null, open: false, html: HTML, onRender: wire }); return; }
    if (_retry++ < 40) setTimeout(init, 500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  // Page-side fact writer for automatic capture (the harvester, Loop Lab's
  // run-end [MEMORY] harvest). Same file format + dirty-sync as tool_remember;
  // same-name save = update (bumps last_verified — saving IS verifying).
  async function save({ name, description, type, body }) {
    if (!isEnabled() || !body || !String(body).trim()) return { ok: false, reason: 'disabled or empty' };
    const slug = _slug(name || description || 'note');
    const t = VALID_TYPES.includes(type) ? type : 'reference';
    const today = _today();
    let created = today;
    try { const old = (await list()).find(f => f.name === slug); if (old && old.created) created = old.created; } catch (_) {}
    const desc = String(description || String(body).split(/\r?\n/)[0]).replace(/\s*\n\s*/g, ' ').trim().slice(0, 160);
    const text = `---\nname: ${slug}\ndescription: ${desc}\ntype: ${t}\ncreated: ${created}\nlast_verified: ${today}\n---\n` + String(body).trim() + '\n';
    const fpath = DIR + '/' + slug + '.md';
    await opfs.write(fpath, text);
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', fpath); } catch (_) {}
    return { ok: true, name: slug };
  }

  return { config, isEnabled, threshold, list, systemBlock, blockChars, maybeConsolidate, consolidate, notify, init, save };
})();
window.SandpieMemory = SandpieMemory;
