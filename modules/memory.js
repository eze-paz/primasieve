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
 * Config (enabled) lives in localStorage; a "Memory" section
 * in the Settings modal edits it.
 */
const SandpieMemory = (function () {
  'use strict';

  const K_ENABLED   = 'sandpie-memory-enabled';     // '0' | '1' (unset = default ON)

  const DEFAULTS = { enabled: true };

  const DIR = 'sandpie/memory';
  const PRUNED = DIR + '/.pruned';
  const VALID_TYPES = ['user', 'feedback', 'project', 'reference'];

  function isEnabled() { const v = localStorage.getItem(K_ENABLED); return v == null ? DEFAULTS.enabled : v === '1'; }
  function config() { return { enabled: isEnabled() }; }

  // ---- store ----------------------------------------------------------------
  const estTokens = (s) => Math.ceil((s || '').length / 4);
  const _today = () => new Date().toISOString().slice(0, 10);
  function _slug(s) { return String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'note'; }

  // ---- clustering (shared by injection + graph) -----------------------------
  // Canonical path identity via SUFFIX-UNION with a bare-basename guard (see the
  // graph section for the rationale). Facts are grouped into components by shared
  // canonical path (present in >=2 facts) OR identical stored `project` label.
  function _parsePaths(f) { return String(f.paths || '').split(',').map(s => s.trim()).filter(Boolean); }
  function _canonMap(all) {
    const uniq = [...new Set(all)]; const nseg = p => p.split('/').filter(Boolean).length; const map = {};
    for (const p of uniq) { let best = p, bl = nseg(p); if (nseg(p) >= 2) for (const q of uniq) if (q !== p && q.endsWith('/' + p) && nseg(q) > bl) { best = q; bl = nseg(q); } map[p] = best; }
    return map;
  }
  // Deterministic project label from a canonical path → one of the real repos.
  // STRONG = explicit repo roots; WEAK = generic files that tend to belong to a repo.
  // (The stored `project` frontmatter always wins over this; it's only the fallback
  // for a cluster with no stored label. Keep in sync with the worker's _projFromPath.)
  function _pathRepoStrong(p) {
    if (/(^|\/)(crates|riscv-core|riscv-supervisor|riscv-harness|riscv-devices|riscv-test-harness)(\/|$)|(^|\/)riscv-vm(\/|$)|vmlinuz|oneshot_alpine|(^|\/)kernels\/|gen_dtb/i.test(p)) return 'riscv-vm';
    if (/(^|\/)(opt\/)?sandpie-server(\/|$)/.test(p)) return 'sandpie-server';
    let m = /(^|\/)skills\/([^/]+)/.exec(p); if (m) return m[2];
    m = /(^|\/)files\/projects\/([^/]+)/.exec(p); if (m) return /impag/i.test(m[2]) ? 'impagados' : m[2];
    return '';
  }
  function _pathRepoWeak(p) {
    if (/(^|\/)modules\//.test(p) || /^[^/]+\.(js|css|wasm)$/.test(p) || /coiserver|(^|\/)sandpie\.(html|css)|(^|\/)sw\.js|(^|\/)opfs\.js|univer\.js|file-viewer\.js/.test(p)) return 'sandpie';
    if (/aging_|dashboard_live|slartran|IONAPI/i.test(p)) return 'impagados';
    return '';
  }
  function _projLabel(path) { return _pathRepoStrong(path) || _pathRepoWeak(path) || (String(path).split('/').filter(Boolean)[0] || ''); }
  function _clusterFacts(facts) {
    const canon = _canonMap(facts.flatMap(_parsePaths));
    const canByFact = facts.map(f => [...new Set(_parsePaths(f).map(p => canon[p]))]);
    const freq = {}; for (const cs of canByFact) for (const c of cs) freq[c] = (freq[c] || 0) + 1;
    const par = facts.map((_, i) => i); const find = x => { while (par[x] !== x) { par[x] = par[par[x]]; x = par[x]; } return x; };
    const edges = [];
    for (let i = 0; i < facts.length; i++) for (let j = i + 1; j < facts.length; j++) {
      const shared = canByFact[i].filter(c => freq[c] >= 2 && canByFact[j].includes(c));
      if (shared.length) { edges.push([i, j, shared.length]); par[find(i)] = find(j); }
    }
    // stored `project` is a first-class grouping key: union facts sharing one
    const seenProj = {};
    facts.forEach((f, i) => { const p = (f.project || '').trim(); if (p) { if (seenProj[p] !== undefined) par[find(i)] = find(seenProj[p]); else seenProj[p] = i; } });
    const comp = {}; for (let i = 0; i < facts.length; i++) { const r = find(i); (comp[r] = comp[r] || []).push(i); }
    const comps = Object.values(comp).sort((a, b) => b.length - a.length);
    const compOf = [], labelOf = [];
    comps.forEach((g, ci) => {
      const cf = {}; const pf = {};
      for (const i of g) { compOf[i] = ci; const sp = (facts[i].project || '').trim(); if (sp) pf[sp] = (pf[sp] || 0) + 1; for (const c of canByFact[i]) if (freq[c] >= 2) cf[c] = (cf[c] || 0) + 1; }
      const topProj = Object.entries(pf).sort((a, b) => b[1] - a[1])[0];
      const topPath = Object.entries(cf).sort((a, b) => b[1] - a[1])[0];
      labelOf[ci] = topProj ? topProj[0] : (topPath ? _projLabel(topPath[0]) : '');
    });
    const projectOf = facts.map((f, i) => (f.project && f.project.trim()) ? f.project.trim() : (labelOf[compOf[i]] || ''));
    return { canon, canByFact, freq, edges, comps, compOf, labelOf, projectOf };
  }
  // Which project(s) the current turn is "in". SCORE every project by relevance —
  // recency-weighted recent-path hits + keyword hits — then activate only the TOP
  // one or two (leader + anything within 60% of it, hard cap 2). Binary "any match →
  // active" over-fired: a global recent-path list spanning scattered work, plus a big
  // message, lit up every project at once. Ranking keeps it to the project(s) actually
  // in focus; the rest stay in the one-line index (recall() pulls them on demand).
  function _activeProjects(facts, cl, ctx) {
    const base = p => String(p).split('/').filter(Boolean).pop() || p;
    const score = {};
    const bump = (i, w) => { const p = cl.projectOf[i]; if (p) score[p] = (score[p] || 0) + w; };
    // Recent paths: freshest first; weight newest higher; only the freshest ~12 (the
    // list is a long global accumulator — stale cross-project paths shouldn't activate).
    const recent = ((ctx && ctx.paths) || []).slice(0, 12);
    recent.forEach((rp, idx) => {
      const w = 2 - idx / 12;
      for (let i = 0; i < facts.length; i++)
        if (cl.canByFact[i].some(c => c === rp || c.endsWith('/' + rp) || rp.endsWith('/' + c) || base(c) === base(rp))) bump(i, w);
    });
    // Keyword match on the current user message (cap the term set so a pasted wall of
    // text can't match everything); a fact needs ≥2 distinct term hits to count.
    const terms = [...new Set((String((ctx && ctx.message) || '').toLowerCase().match(/[a-z0-9][a-z0-9_-]{3,}/g) || []))].slice(0, 40);
    for (let i = 0; i < facts.length; i++) {
      const hay = (facts[i].name + ' ' + facts[i].description + ' ' + facts[i].paths).toLowerCase();
      let hits = 0; for (const t of terms) if (hay.includes(t)) hits++;
      if (hits >= 2) bump(i, 1);
    }
    delete score[''];
    const ranked = Object.entries(score).sort((a, b) => b[1] - a[1]);
    if (!ranked.length) return new Set();
    const max = ranked[0][1];
    return new Set(ranked.filter(([, s]) => s >= max * 0.6).slice(0, 2).map(([p]) => p));
  }
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
    return { name, description, type, created: fm.created || '', last_verified: fm.last_verified || '', body, file: file || (name + '.md'), conversation: fm.conversation || '', tool_calls: fm.tool_calls || '', paths: fm.paths || '', project: fm.project || '', supersedes: fm.supersedes || '' };
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
  // Names of the facts injected IN FULL on the last systemBlock() call = "activated"
  // this turn (Tier-0 standing user/feedback + Tier-2 promoted active-project facts).
  // The sidebar graph reads this to colour nodes (accent = activated, dim = not).
  // Changing the set emits memory:active so an open graph re-colours live.
  let _lastActiveNames = new Set();
  function activeNames() { return _lastActiveNames; }
  function _setActive(names) {
    const next = names instanceof Set ? names : new Set(names);
    let changed = next.size !== _lastActiveNames.size;
    if (!changed) for (const n of next) if (!_lastActiveNames.has(n)) { changed = true; break; }
    _lastActiveNames = next;
    if (changed) { try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('memory:active', {}); } catch (_) {} }
  }
  // Char budget for Tier-2 promoted bodies (~5K tokens). Beyond this, active-project
  // memories that don't fit drop to the index and the cluster is flagged to consolidate.
  const TIER2_BUDGET = 20000;
  const _INSTRUCTION = "Durable facts you've saved with the remember tool. Treat them as true unless the current conversation contradicts them. Each fact shows its verification age (verified Nd ago) — judge staleness yourself; when a tool observation CONFIRMS an aging fact, re-save it (same name) to bump the date; when one CONTRADICTS it, update or forget it. As soon as you learn something durable and non-derivable — a user preference, standing feedback on how to work, or lasting project context — SAVE IT with remember right then. Memories for your CURRENT work are shown in full below; the rest are listed in the index by name — call recall(\"keywords\") to pull any of them in full. [[name]] links a related fact.";
  function _badge(f, now) {
    const ref = Date.parse(f.last_verified || f.created || '');
    if (!Number.isFinite(ref)) return ' · unverified';
    const days = Math.max(0, Math.floor((now - ref) / 86400000));
    return days === 0 ? ' · verified today' : ` · verified ${days}d ago`;
  }
  // ctx (optional): { message: <latest user text>, paths: [recent file paths] } — drives
  // which project's memories are promoted to full this turn. Absent ctx (cold) = index only.
  async function systemBlock(ctx) {
    if (!isEnabled()) { _lastBlockChars = 0; _setActive([]); return ''; }
    const facts = await list();
    const lines = ['', '', '# Memory', _INSTRUCTION];
    if (!facts.length) {
      lines.push('', '_(No memories saved yet. Save the first durable, non-derivable fact you learn this session.)_');
      const b = lines.join('\n'); _lastBlockChars = b.length; _setActive([]); return b;
    }
    const now = Date.now();
    const full = f => `\n## ${f.description} _(${f.type}${_badge(f, now)})_\n${f.body}`;
    // Legacy path (flag off): inject every body in full, as before.
    if (localStorage.getItem('sandpie-memory-tiered') === '0') {
      for (const f of facts) lines.push('', `## ${f.description} _(${f.type}${_badge(f, now)})_`, f.body);
      const b = lines.join('\n'); _lastBlockChars = b.length; _setActive(facts.map(f => f.name)); return b;
    }
    // TIERED. Tier 0: user/feedback always full (identity + how-to-work).
    const cl = _clusterFacts(facts);
    const always = [], contextual = [];
    facts.forEach((f, i) => { (f.type === 'user' || f.type === 'feedback') ? always.push(f) : contextual.push({ f, i }); });
    if (always.length) { lines.push('', '## Standing — always applies'); for (const f of always) lines.push(full(f)); }
    // Tier 2: promote contextual memories whose project is active this turn, newest first, until budget.
    const active = _activeProjects(facts, cl, ctx);
    const activeFacts = contextual.filter(x => active.has(cl.projectOf[x.i]))
      .sort((a, b) => (Date.parse(b.f.last_verified || b.f.created || 0) || 0) - (Date.parse(a.f.last_verified || a.f.created || 0) || 0));
    const promoted = new Set(); let used = 0, overflow = 0;
    const promotedLines = [];
    for (const x of activeFacts) { const t = full(x.f); if (used + t.length <= TIER2_BUDGET) { promotedLines.push(t); promoted.add(x.i); used += t.length; } else overflow++; }
    if (promotedLines.length) { lines.push('', `## Active project${active.size > 1 ? 's' : ''}: ${[...active].join(', ')}`); for (const t of promotedLines) lines.push(t); }
    // Tier 1: everything else as a 1-line index, grouped by project.
    const idx = contextual.filter(x => !promoted.has(x.i));
    if (idx.length) {
      lines.push('', '## Index — other memories (recall("keywords") to load in full)');
      const byProj = {};
      for (const x of idx) { const p = cl.projectOf[x.i] || 'misc'; (byProj[p] = byProj[p] || []).push(x.f); }
      for (const p of Object.keys(byProj).sort()) { lines.push('', `### ${p}`); for (const f of byProj[p]) lines.push(`- ${f.name}: ${f.description}`); }
      if (overflow) lines.push('', `_(+${overflow} active-project memories over budget — recall() to load; consider consolidating this project)_`);
    }
    // Record what got injected in full = "activated" this turn (standing + promoted).
    const activated = new Set(always.map(f => f.name));
    for (const i of promoted) activated.add(facts[i].name);
    _setActive(activated);
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


  // ---- path clustering ------------------------------------------------------
  function _parsePaths(fact) {
    if (!fact.paths) return [];
    return String(fact.paths).split(',').map(p => p.trim()).filter(Boolean);
  }
  function clusterByPaths(facts, minShared) {
    minShared = minShared || 2;
    const clusters = [];
    const used = new Set();
    for (let i = 0; i < facts.length; i++) {
      if (used.has(i)) continue;
      const fi = facts[i];
      const pi = _parsePaths(fi);
      if (!pi.length) continue;
      const cluster = { id: fi.name, memories: [fi], sharedPaths: pi.slice(), types: new Set([fi.type]) };
      used.add(i);
      for (let j = i + 1; j < facts.length; j++) {
        if (used.has(j)) continue;
        const fj = facts[j];
        const pj = _parsePaths(fj);
        if (!pj.length) continue;
        const shared = pi.filter(p => pj.some(q => q === p || p.startsWith(q + '/') || q.startsWith(p + '/')));
        if (shared.length >= minShared) {
          cluster.memories.push(fj);
          shared.forEach(p => { if (!cluster.sharedPaths.includes(p)) cluster.sharedPaths.push(p); });
          cluster.types.add(fj.type);
          used.add(j);
        }
      }
      if (cluster.memories.length >= 3) clusters.push(cluster);
    }
    return clusters;
  }

  // ---- deterministic consolidation (supersede near-duplicates) --------------
  // NO LLM rewrite (the model can't be trusted to prune memory automatically).
  // Reduction is by SUPERSESSION: within one project, if two memories are near-identical
  // (Jaccard token overlap), the older is archived to .pruned/ (recoverable). The AUTO
  // threshold is deliberately HIGH — a dry-run over the real store showed lower thresholds
  // archive DISTINCT facts (similarity ≠ supersession). Pairs in the mid band are only
  // REPORTED as candidates, never auto-archived. user/feedback are never superseded.
  const AUTO_TH = 0.65;   // >= this → auto-archive the older (zero false positives measured)
  const CAND_TH = 0.4;    // [CAND_TH, AUTO_TH) → surface as a review candidate only
  const LAST_KEY = 'sandpie-memory-consolidate-ts';
  const _MEM_STOP = new Set('the a an of to in on for and or is are was be it this that with at by from as into not no you your can will has have not are'.split(' '));
  function _memTokens(f) { return new Set((`${f.name} ${f.description} ${f.body}`.toLowerCase().match(/[a-z0-9][a-z0-9_-]{2,}/g) || []).filter(w => !_MEM_STOP.has(w))); }
  function _jaccard(a, b) { let inter = 0; for (const x of a) if (b.has(x)) inter++; const uni = a.size + b.size - inter; return uni ? inter / uni : 0; }
  let _lastReport = null;
  function lastConsolidateReport() { return _lastReport; }

  // Run the deterministic pass. opts.dryRun => detect only, archive nothing.
  async function consolidate(facts, opts) {
    opts = opts || {};
    facts = facts || await list();
    if (facts.length < 2) return { ok: false, reason: 'nothing to consolidate', archived: [], candidates: [] };
    const cl = _clusterFacts(facts);
    const proj = cl.projectOf;
    const tok = facts.map(_memTokens);
    const dateOf = f => Date.parse(f.last_verified || f.created || '') || 0;
    const archived = [], candidates = [], gone = new Set();
    // (1) EXPLICIT supersession the model declared via remember(supersedes: [...]).
    // Any confidence — the model understood the semantics; we just execute it.
    for (let i = 0; i < facts.length; i++) {
      if (!facts[i].supersedes) continue;
      for (const on of String(facts[i].supersedes).split(',').map(s => s.trim()).filter(Boolean)) {
        const oi = facts.findIndex((x, k) => k !== i && !gone.has(k) && x.name === on);
        if (oi < 0) continue;
        archived.push({ name: facts[oi].name, by: facts[i].name, sim: 'explicit' });
        gone.add(oi);
        if (!opts.dryRun) { try { await _tombstone(facts[oi]); } catch (_) {} }
      }
    }
    // (2) AUTOMATIC supersession of near-identical same-project pairs.
    const pairs = [];
    for (let i = 0; i < facts.length; i++) for (let j = i + 1; j < facts.length; j++) {
      if (gone.has(i) || gone.has(j)) continue;
      if (!proj[i] || proj[i] !== proj[j]) continue;                       // same project only
      if (/^(user|feedback)$/.test(facts[i].type) || /^(user|feedback)$/.test(facts[j].type)) continue;
      const s = _jaccard(tok[i], tok[j]);
      if (s >= CAND_TH) pairs.push({ i, j, s });
    }
    pairs.sort((a, b) => b.s - a.s);
    for (const p of pairs) {
      if (gone.has(p.i) || gone.has(p.j)) continue;
      const older = dateOf(facts[p.i]) <= dateOf(facts[p.j]) ? p.i : p.j;
      const newer = older === p.i ? p.j : p.i;
      if (p.s >= AUTO_TH) {
        archived.push({ name: facts[older].name, by: facts[newer].name, sim: +p.s.toFixed(2) });
        gone.add(older);
        if (!opts.dryRun) { try { await _tombstone(facts[older]); } catch (_) {} }
      } else {
        candidates.push({ older: facts[older].name, newer: facts[newer].name, sim: +p.s.toFixed(2) });
      }
    }
    if (archived.length && !opts.dryRun) notify();
    _lastReport = { at: Date.now(), archived, candidates, before: facts.length, after: facts.length - archived.length };
    return { ok: true, ...(_lastReport) };
  }

  // Restore an auto-archived memory from .pruned/ back into the live store.
  async function restore(name) {
    const slug = _slug(name);
    const src = PRUNED + '/' + slug + '.md';
    let text; try { text = await opfs.read(src); } catch (_) { return { ok: false, reason: 'no archived memory "' + slug + '"' }; }
    const dst = DIR + '/' + slug + '.md';
    await opfs.write(dst, text);
    try { await opfs.remove(src); } catch (_) {}
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', dst); } catch (_) {}
    notify();
    return { ok: true, name: slug };
  }

  // EVENT-DRIVEN: consolidation runs a few seconds after a memory is WRITTEN — the
  // only moment a new near-duplicate / supersession can appear — coalescing bursts.
  // No clock, no per-turn cost. A run that archives something re-emits memory:changed,
  // which schedules one more pass that finds nothing new and stops (self-terminating).
  let _consTimer = null, _consolidating = false;
  function scheduleConsolidate() {
    if (!isEnabled()) return;
    clearTimeout(_consTimer);
    _consTimer = setTimeout(runAutoConsolidate, 4000);
  }
  async function runAutoConsolidate() {
    if (_consolidating || !isEnabled()) return;
    _consolidating = true;
    try { const r = await consolidate(); if (r.archived && r.archived.length) console.log('[sandpie memory] auto-superseded:', r.archived); }
    catch (e) { console.warn('[sandpie] consolidate failed', e); }
    finally { _consolidating = false; }
  }
  // Subscribe once to every memory-write signal (save/forget/restore/consolidate emit
  // memory:changed via notify(); the harvester's save() emits file:changed; a worker
  // remember() surfaces as memory:changed via the conversations.js relay).
  function _wireAutoConsolidate() {
    if (typeof Sandpie === 'undefined' || !Sandpie.events) return;
    Sandpie.events.on('memory:changed', scheduleConsolidate);
    Sandpie.events.on('file:changed', (p) => { if (typeof p === 'string' && /(^|\/)sandpie\/memory\/[^/]+\.md$/.test(p) && !p.includes('/.pruned/')) scheduleConsolidate(); });
  }
  // Back-compat: any remaining caller just nudges a (debounced) pass.
  function maybeConsolidate() { scheduleConsolidate(); return Promise.resolve(); }

  // ---- commands -------------------------------------------------------------
  function registerCommands() {
    if (typeof SandpieCommands === 'undefined') return;
    SandpieCommands.register({
      name: 'memory', module: 'core',
      help: 'List memories; "show <name>", "consolidate" (supersede near-dupes), "restore <name>"',
      usage: '>>> memory [show <name> | consolidate | restore <name>]',
      async run(text, parts) {
        if (parts[1] === 'consolidate' || parts[1] === 'cluster' || parts[1] === 'dedup') {
          const dry = parts[2] === 'dry' || parts[2] === '--dry';
          const r = await consolidate(null, { dryRun: dry });
          if (!r.ok) return 'Consolidate: ' + (r.reason || 'failed') + '.';
          const a = (r.archived || []).map(x => `  • ${x.name} → superseded by ${x.by} (${x.sim})`).join('\n');
          const c = (r.candidates || []).map(x => `  • ${x.older} ~ ${x.newer} (${x.sim})`).join('\n');
          return `${dry ? 'DRY RUN — ' : ''}${r.before}→${r.after} memories.\n`
            + (a ? `Archived (recoverable via >>> memory restore <name>):\n${a}\n` : 'Nothing auto-archived.\n')
            + (c ? `Review candidates (not archived; supersede manually if right):\n${c}` : 'No review candidates.');
        }
        if (parts[1] === 'restore') { const r = await restore(parts[2] || ''); return r.ok ? `Restored "${r.name}".` : (r.reason || 'restore failed') + '.'; }
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
          `  ·  ${facts.length} parsed  ·  ~${used} tokens`;
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
        // INERT — the auto-harvester that replaced them was eliminated 2026-08-07
        // (the remember tool is the only capture channel); flag leftovers as removable.
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
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">Durable facts are remembered across conversations and injected into the model's context automatically. Auto-consolidation keeps the store small by merging, pruning and de-duplicating near-identical facts. Stored locally in this browser only.</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.6rem;">
      <input type="checkbox" id="memEnabled" style="width:auto;"> Enable automatic memory
    </label>
    <span id="memStatus" style="font-size:0.7rem; color:var(--sp-text-dim); display:block; margin-bottom:0.6rem;"></span>
    <hr style="border:none; border-top:1px solid var(--sp-border); margin:0.8rem 0;">
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.4rem;"><strong>Recent paths</strong> &mdash; files touched in this project, injected into every prompt while memory is on (always the most recent 50).</p>
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0.6rem 0 0.4rem;"><strong>Auto-consolidation</strong> &mdash; always on, deterministic: archives near-identical memories within a project.</p>
    `;

  let _flashT = null;
  function flash(msg) { const el = document.getElementById('memStatus'); if (!el) return; el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500); }

  function wire(panel) {
    const cfg = config();
    const en = panel.querySelector('#memEnabled');
    if (en) { en.checked = cfg.enabled; en.addEventListener('change', () => { localStorage.setItem(K_ENABLED, en.checked ? '1' : '0'); flash('Saved'); setMemoryDot(); }); }
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
    if (window.SandpieSettings) { SandpieSettings.register({ id: 'memory', title: 'Memory', order: 17, dot: 'memoryDot', render(panel) { panel.innerHTML = HTML; wire(panel); } }); }
    else if (typeof SandpieMenu !== 'undefined') { SandpieMenu.add('memorySection', { title: 'Memory', dot: 'memoryDot', badge: null, open: false, html: HTML, onRender: wire }); }
    else if (_retry++ < 40) { setTimeout(init, 500); return; }
    initSecondBrain();
    _wireAutoConsolidate();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  /* ============ Second Brain visualization (folded from second-brain.js) ============ */
  const SB_SECTION_ID = 'secondBrainSection';
  const SB_W = 240, SB_H = 170;

  const SB_CSS = `
    #${SB_SECTION_ID} svg.sb-net { width:100%; height:auto; display:block; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:8px; }
    #${SB_SECTION_ID} .sb-cell { cursor:pointer; }
    #${SB_SECTION_ID} .sb-active   { fill:var(--sp-accent); }
    #${SB_SECTION_ID} .sb-inactive { fill:var(--sp-text-dim); opacity:0.35; }
    #${SB_SECTION_ID} .sb-c-lbl { fill:var(--sp-text-dim); font-size:8.5px; font-weight:600; letter-spacing:.05em; }
    #${SB_SECTION_ID} .sb-c-lbl-act { fill:var(--sp-accent); }
    #${SB_SECTION_ID} .sb-legend { display:flex; flex-wrap:wrap; gap:0.15rem 0.6rem; margin:0.3rem 0.3rem 0.1rem; }
    #${SB_SECTION_ID} .sb-legend span { font-size:0.62rem; color:var(--sp-text-dim); display:flex; align-items:center; gap:0.25rem; }
    #${SB_SECTION_ID} .sb-legend i { width:7px; height:7px; border-radius:50%; display:inline-block; }
    #${SB_SECTION_ID} .sb-empty { font-size:0.72rem; color:var(--sp-text-dim); padding:0.4rem 0; }
    @keyframes sb-latch { 0%{opacity:0;filter:brightness(2.2)} 40%{opacity:1;filter:brightness(1.6)} 100%{opacity:1;filter:none} }
    #${SB_SECTION_ID} .sb-cell { animation:sb-latch .3s ease-out backwards; }
    @media (prefers-reduced-motion:reduce) { #${SB_SECTION_ID} .sb-cell { animation:none !important; } }
  `;

  function _sbHash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function _sbRand01(seed, n) { const x = Math.sin(seed * 12.9898 + n * 78.233) * 43758.5453; return x - Math.floor(x); }

  const SB_CLUSTERS = {
    user:      { x: SB_W * 0.24, y: SB_H * 0.32 },
    feedback:  { x: SB_W * 0.72, y: SB_H * 0.26 },
    project:   { x: SB_W * 0.34, y: SB_H * 0.70 },
    reference: { x: SB_W * 0.76, y: SB_H * 0.68 },
  };

  let _sbBody = null, _sbDetails = null, _sbNodes = [], _sbRaf = 0, _sbT = 0, _sbDirty = true;

  function _sbRunning() { return !!(_sbDetails && _sbDetails.open && document.visibilityState === 'visible' && _sbNodes.length); }
  function _sbTick() {
    // flat 2D databank — no float/bob animation (it made the graph read as 3D)
    _sbRaf = 0;
  }
  function _sbStartAnim() { if (!_sbRaf && _sbRunning()) _sbRaf = requestAnimationFrame(_sbTick); }
  function _sbStopAnim() { if (_sbRaf) { cancelAnimationFrame(_sbRaf); _sbRaf = 0; } }
  function _sbEsc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

  // Label fitting: measure with a hidden span (inherits the app font) and ellipsize.
  let _sbLblMeter = null;
  function _sbLblWidth(s) {
    if (!_sbLblMeter) {
      _sbLblMeter = document.createElement('span');
      _sbLblMeter.setAttribute('aria-hidden', 'true');
      _sbLblMeter.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none;white-space:nowrap;font-size:8.5px;font-weight:600;letter-spacing:.05em;';
      document.body.appendChild(_sbLblMeter);
    }
    _sbLblMeter.textContent = s;
    return _sbLblMeter.getBoundingClientRect().width;
  }
  function _sbEllipsize(s, maxW) {
    if (_sbLblWidth(s) <= maxW) return s;
    let t = String(s);
    while (t.length > 1 && _sbLblWidth(t + '\u2026') > maxW) t = t.slice(0, -1);
    return t + '\u2026';
  }

  // ---- path-based graph -----------------------------------------------------
  // The graph shares ONE clustering with injection (_clusterFacts, module scope):
  // components = memories linked by a shared canonical file path (suffix-union, with
  // the bare-basename guard) OR an identical stored `project` label. Layout positions
  // by component ("sections": riscv, sandpie, tecnec, …); colour still encodes type.
  const _memGraph = _clusterFacts;

  function _sbAgeOp(f) {
    const ref = Date.parse(f.last_verified || f.created || '');
    if (!Number.isFinite(ref)) return 0.4;
    const d = Math.floor((Date.now() - ref) / 86400000);
    if (d <= 1) return 1; if (d <= 7) return 0.88; if (d <= 30) return 0.72; if (d <= 90) return 0.58; return 0.42;
  }

  // LANES databank: one row per project (active projects first, highlighted); the
  // newest MAX blocks per lane are right-aligned; '+N' badges the overflow. Flat 2D,
  // no edges, no time axis. Block colour = state, opacity = verification age.
  async function _sbRender() {
    if (!_sbBody) return;
    _sbDirty = false;
    _sbStopAnim();
    _sbNodes = [];
    let facts = [];
    try { facts = await list(); } catch (_) {}
    if (typeof SandpieMenu !== 'undefined') SandpieMenu.updateBadge(SB_SECTION_ID, String(facts.length || ''));
    if (!facts.length) {
      _sbBody.innerHTML = `<div class="sb-empty">No memories yet — sandpie saves durable facts as you work, and they'll appear here as a databank.</div>`;
      return 0;
    }
    _memGraph(facts);
    const SB_BUCKETS = ['scripts', 'skills', 'artifacts', 'modules', 'memory', 'fonts', 'conversations', 'secrets', 'config'];
    const laneOf = (f) => {
      const proj = (f.project || '').trim();
      if (proj === 'sandpie') {
        const p = _parsePaths(f)[0] || '';
        const seg = p.split('/').filter(Boolean)[1] || '';
        return SB_BUCKETS.includes(seg) ? 'sandpie/' + seg : 'sandpie';
      }
      return proj;
    };
    // single catch-all: facts with NO project go straight to the rest bucket
    // (they are not a lane — merging them with the overflow lanes avoids the
    // one catch-all group).
    const lanes = {}, unassigned = [];
    facts.forEach((f, i) => {
      const proj = (f.project || '').trim();
      if (!proj) { unassigned.push(i); return; }
      const k = laneOf(f); (lanes[k] = lanes[k] || []).push(i);
    });
    const laneAct = k => (lanes[k] || []).filter(i => _lastActiveNames.has(facts[i].name)).length;
    const laneOrder = Object.keys(lanes).sort((a, b) => (laneAct(b) ? 1 : 0) - (laneAct(a) ? 1 : 0) || lanes[b].length - lanes[a].length);
    const maxNamed = unassigned.length ? 6 : 7;
    const named = laneOrder.slice(0, maxNamed);
    const overflow = laneOrder.slice(maxNamed);
    const restMembers = unassigned.concat(overflow.reduce((a, r) => a.concat(lanes[r]), []));
    const top = named.slice();
    if (restMembers.length) top.push('other');

    // chip-rack geometry — chips fill the width (6..SB_W-6), height grows with content
    const CHIP_X = 6, CHIP_W = SB_W - 12, LABEL_W = 84;
    const CELL = 4.5, GAP = 2.5, PITCH = CELL + GAP;
    // label zone: text starts at CHIP_X+10, must stop LBL_PAD_R before the cells
    const LBL_PAD_R = 8, MAX_LBL_W = LABEL_W - 10 - LBL_PAD_R;
    const rows_per_chip = Math.max(1, Math.floor((CHIP_W - LABEL_W - 8) / PITCH));
    let y = 8, chip_i = 0, totalH = 8;
    const chips = [], gridCs = [];
    top.forEach((k) => {
      const members = (k === 'other' ? restMembers : lanes[k])
        .slice().sort((a, b) => ((facts[b].last_verified || facts[b].created || '') < (facts[a].last_verified || facts[a].created || '') ? -1 : 1));
      const n = members.length;
      const nr = Math.ceil(n / rows_per_chip);
      const chip_h = 2 + nr * PITCH + 4;
      // vertical center of the cell block (rows span y+2 .. y+2+(nr-1)*PITCH+CELL)
      const gridC = y + 2 + ((nr - 1) * PITCH) / 2 + CELL / 2;
      gridCs.push(gridC);
      const act = k === 'other' ? restMembers.filter(i => _lastActiveNames.has(facts[i].name)).length : laneAct(k);
      const lbl = _sbEsc(_sbEllipsize(k === 'other' ? 'other' : k.replace('sandpie/', ''), MAX_LBL_W));
      chips.push(`<text class="sb-c-lbl${act ? ' sb-c-lbl-act' : ''}" x="${(CHIP_X + 10).toFixed(1)}" y="${(gridC + 2.3).toFixed(1)}">${lbl}</text>`);
      members.forEach((i, kk) => {
        const c = kk % rows_per_chip, r = Math.floor(kk / rows_per_chip);
        const cx = CHIP_X + LABEL_W + 4 + c * PITCH, ey = y + 2 + r * PITCH;
        const cls = _lastActiveNames.has(facts[i].name) ? 'sb-active' : 'sb-inactive';
        const op = _sbAgeOp(facts[i]);
        const d = chip_i * 220 + kk * 6;
        chips.push(`<rect class="sb-cell ${cls}" data-i="${i}" x="${cx.toFixed(1)}" y="${ey.toFixed(1)}" width="${CELL.toFixed(1)}" height="${CELL.toFixed(1)}" rx="1" opacity="${op.toFixed(2)}" style="animation-delay:${d}ms"/>`);
      });
      y += chip_h + 2;
      chip_i++;
      totalH = y;
    });
    totalH += 6;

    const nOn = facts.filter(f => _lastActiveNames.has(f.name)).length;
    const nOff = facts.length - nOn;

    _sbBody.innerHTML = `
      <svg class="sb-net" viewBox="0 0 ${SB_W} ${totalH.toFixed(1)}" role="img" aria-label="Memory databank of ${facts.length}">${chips.join('')}</svg>
      <div class="sb-legend"><span><i style="background:var(--sp-accent)"></i>active ${nOn}</span><span><i style="background:var(--sp-text-dim)"></i>standby ${nOff}</span></div>`;

    const svg = _sbBody.querySelector('svg.sb-net');
    // Vertically center each label on its cell block: SVG <text> y is the baseline,
    // so measure the rendered glyph box and shift y until its center hits gridC.
    svg.querySelectorAll('text.sb-c-lbl').forEach((el, i) => {
      const bb = el.getBBox();
      el.setAttribute('y', (+el.getAttribute('y') - (bb.y + bb.height / 2) + gridCs[i] - 1.2).toFixed(1));
    });
    svg.querySelectorAll('rect.sb-cell').forEach(el => {
      const i = +el.dataset.i, f = facts[i];
      _sbNodes.push({ el, x: +el.getAttribute('x'), y: +el.getAttribute('y') });
      el.setAttribute('title', _sbEsc(f.name) + ' — ' + _sbEsc(f.description));
      el.addEventListener('mouseenter', () => { el.setAttribute('stroke', 'var(--sp-text)'); el.setAttribute('stroke-width', '0.9'); });
      el.addEventListener('mouseleave', () => { el.removeAttribute('stroke'); });
      el.addEventListener('click', () => {
        if (window.SandpieFileViewer && SandpieFileViewer.open) SandpieFileViewer.open(DIR + '/' + f.file, f.file);
        else if (typeof SandpieCommands !== 'undefined' && SandpieCommands.dispatch) SandpieCommands.dispatch('>>> memory show ' + f.name);
      });
    });
    _sbStartAnim();
    return facts.length;
  }

  function _sbOnToggle() {
    if (_sbDetails && _sbDetails.open) { if (_sbDirty) _sbRender(); else _sbStartAnim(); }
    else _sbStopAnim();
  }

  function _sbPlaceAboveFiles() {
    // Sidebar order is conversations, memory, files. SandpieMenu appends new
    // sections above the footer (below the static #filesSection), so lift the
    // memory section to sit directly above Files.
    try {
      const filesEl = document.getElementById('filesSection');
      const el = SandpieMenu.get(SB_SECTION_ID);
      if (filesEl && el) filesEl.before(el);
    } catch (_) {}
  }
  function initSecondBrain() {
    if (typeof SandpieMenu === 'undefined') return;
    const style = document.createElement('style');
    style.textContent = SB_CSS;
    document.head.appendChild(style);
    // Add SYNCHRONOUSLY so the header is in the DOM on first paint — an async
    // add made the whole section (header included) pop in ~1s after load.
    // Always open by default; the real badge arrives when _sbRender finishes.
    SandpieMenu.add(SB_SECTION_ID, { title: 'MEMORY', badge: '…', open: true, onRender(body) { _sbBody = body; } });
    _sbPlaceAboveFiles();
    _sbDetails = SandpieMenu.get(SB_SECTION_ID);
    if (_sbDetails) _sbDetails.addEventListener('toggle', _sbOnToggle);
    document.addEventListener('visibilitychange', () => { document.visibilityState === 'visible' ? _sbStartAnim() : _sbStopAnim(); });
    if (typeof Sandpie !== 'undefined' && Sandpie.events) {
      Sandpie.events.on('memory:changed', () => {
        if (_sbDetails && _sbDetails.open) _sbRender();
        else { _sbDirty = true; list().then(f => SandpieMenu.updateBadge(SB_SECTION_ID, String(f.length || ''))).catch(() => {}); }
      });
      // Activation changed (a new turn promoted a different project) → re-colour.
      Sandpie.events.on('memory:active', () => { if (_sbDetails && _sbDetails.open) _sbRender(); else _sbDirty = true; });
    }
    _sbRender().then(() => { if (!_sbDetails.open) _sbStopAnim(); });
  }

  // Recompute the activated set from a conversation's context WITHOUT building
  // the prompt block — called on conversation switch so the sidebar re-colours
  // immediately (send-time systemBlock() would be too late). Mirrors the tiered
  // semantics: standing user/feedback always active, plus contextual memories of
  // the projects active for this conversation's ctx.
  async function refreshActive(ctx, stillActive) {
    if (!isEnabled()) { _setActive([]); return; }
    const facts = await list();
    if (stillActive && !stillActive()) return;   // superseded mid-flight — a newer conversation switch won; drop without re-colouring
    if (!facts.length) { _setActive([]); return; }
    const cl = _clusterFacts(facts);
    const active = _activeProjects(facts, cl, ctx || {});
    const activated = new Set();
    facts.forEach((f, i) => {
      if (f.type === 'user' || f.type === 'feedback') activated.add(f.name);
      else if (active.has(cl.projectOf[i])) activated.add(f.name);
    });
    _setActive(activated);
  }

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

  return { config, isEnabled, list, systemBlock, refreshActive, blockChars, activeNames, maybeConsolidate, consolidate, restore, lastConsolidateReport, notify, init, save };
})();
window.SandpieMemory = SandpieMemory;

