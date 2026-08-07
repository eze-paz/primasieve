// augmentations.js — Tool-call logger, recent-paths tracker, and project-lesson distiller.
// Loaded before conversations.js so SandpieAugmentations is available during dispatchAgentEvent().

(function (global) {
  'use strict';

  const MEMORY_DIR = 'sandpie/memory';
  const META_NS = '_sp_augment';

  // Per-tool-call [Aug] logging is chatty (two lines per tool call); off by
  // default. Re-enable with localStorage 'sandpie-aug-log' = '1'. Errors
  // (console.warn) always show.
  function _augLog(...args) { try { if (localStorage.getItem('sandpie-aug-log') === '1') console.log(...args); } catch (_) {} }

  /* ── per-conversation scratchpad (ephemeral, lives in RAM) ────────── */
  const convMeta = new Map(); // convId -> { scripts:Set, files:Set, toolCalls:[], folder }

  function getMeta(convId) {
    if (!convMeta.has(convId)) {
      convMeta.set(convId, { scripts: new Set(), files: new Set(), toolCalls: [], folder: inferFolder() });
    }
    return convMeta.get(convId);
  }

  function inferFolder() {
    // Derive from current page state when possible; fallback to null
    try {
      const f = localStorage.getItem('sandpie-active-folder');
      if (f) return f;
    } catch (_) {}
    return null;
  }


  /* ── project ID from paths ────────────────────────────────────────── */

  // Serialize the read-modify-write: a turn fires many trackRecentPath calls
  // concurrently, and without a queue they race on the same file and clobber
  // each other (only the last write survives → paths get lost).
  let _rpChain = Promise.resolve();
  function trackRecentPath(convId, path) {
    if (!path) return _rpChain;
    _rpChain = _rpChain.then(() => _trackRecentPathInner(path)).catch(() => {});
    return _rpChain;
  }
  async function _trackRecentPathInner(path) {
    // Use the SAME project id the read side (systemBlock) uses. Deriving it from
    // and wrote to a garbage nested dir that the reader never looked in.
    // Recent paths: single global list (was per-project)
    const storePath = MEMORY_DIR + '/global.recent-paths.json';
    let list = [];
    try { const raw = await opfs.read(storePath); if (raw) list = JSON.parse(raw); } catch (_) {}
    list = list.filter(p => p !== path);
    list.unshift(path);
    const max = 50;   // hardcoded 2026-08-07: recent-paths count is fixed (lever removed from Settings → Memory)
    if (list.length > max) list = list.slice(0, max);
    await opfs.write(storePath, JSON.stringify(list, null, 2));
    // Mark dirty so it uploads and survives the Dropbox sync orphan-cleanup.
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', storePath); } catch (_) {}
  }

  async function getRecentPaths() {
    try { const raw = await opfs.read(MEMORY_DIR + '/global.recent-paths.json'); if (raw) return JSON.parse(raw); } catch (_) {}
    return [];
  }

  /* ── lessons (distilled project-specific patterns) ─────────────────── */
  // convId -> number of tool calls already examined. Cursor, NOT a boolean: the
  // distiller re-runs at each turn end over only the tool calls accrued since,
  // so a long session keeps learning (the old boolean ran once, early, forever).
  const _distillCursor = new Map();
  const MIN_NEW_TOOLCALLS = 2;   // don't bother distilling a turn with <2 new actions

  function summarizeSession(convId, fromIdx = 0) {
    const meta = convMeta.get(convId);
    if (!meta || meta.toolCalls.length === 0) return null;
    // from meta.files wrote lessons to a path the reader never looked in.
    // Recent paths: single global list (was per-project)
    const files = [...meta.files];
    // Only the tool calls SINCE the last distill (fromIdx) — the "what just
    // happened" the distiller reasons over. total is returned so the caller can
    // advance its cursor.
    const tools = meta.toolCalls.slice(fromIdx).map(tc => {
      const p = tc.args?.path || tc.args?.src || tc.args?.cwd || '';
      // Include the OUTCOME snippet: without it a distiller can only pattern-match
      // action shapes (the root cause of the old formulaic/hallucinated lessons).
      return '- ' + tc.name + (p ? ' "' + p + '"' : '') + (tc.result ? '  → ' + tc.result : '');
    });
    return { project, files, tools, total: meta.toolCalls.length };
  }

  // Called at each TURN END (conversations.js gates on touchUpdated). Distills
  // lessons from the tool calls accrued since the last run, deduped against both
  // saved memory facts, and advances the cursor so the same turns are never
  // re-examined. This is the AUTOMATIC capture channel: the old lesson distiller's
  // reliable trigger, retargeted to write memory-grade facts (remember's gates +
  // an evidence rule) into the ONE store via SandpieMemory.save — consolidation
  // (which runs on every add) then refines them. Silent + guarded.
  async function distillLessons(convId) {
    const meta = convMeta.get(convId);
    if (!meta) return;
    const total = meta.toolCalls.length;
    const cursor = _distillCursor.get(convId) || 0;
    if (total - cursor < MIN_NEW_TOOLCALLS) return;   // not enough new activity this turn
    if (localStorage.getItem('sandpie-lessons-enabled') === 'false') return;
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return;
    if (typeof window === 'undefined' || !window.SandpieMemory || !SandpieMemory.save || !SandpieMemory.isEnabled()) return;

    const summary = summarizeSession(convId, cursor);
    if (!summary || !summary.tools.length) return;
    const project = summary.project;

    // Dedup against saved memory facts, so a harvest never restates something
    // the remember tool already captured.
    let memHint = '';
    try {
      if (typeof window !== 'undefined' && window.SandpieMemory && SandpieMemory.list) {
        const facts = await SandpieMemory.list();
        if (facts.length) memHint = '\nAlready in memory (do NOT restate these):\n' + facts.map(f => '- ' + f.description).join('\n');
      }
    } catch (_) {}

    const prompt = [
      "You are sandpie's memory harvester. From the RECENT actions + their outcomes below, extract 0-2 facts worth saving to durable memory. Usually the answer is ZERO — output [] unless something clearly passes ALL gates:",
      '',
      '  (1) DURABLE — true beyond this session (an environment gotcha, a tool quirk, where something lives, a verified diagnosis), not task progress or one-off state.',
      '  (2) NON-DERIVABLE — not recoverable from the code, files, or git history.',
      '  (3) EVIDENCED — the fact must be directly visible in an action OUTCOME below (the text after "→"). Never infer process rules from action sequences alone; never invent context that is not in the evidence.',
      '',
      'Project: ' + project,
      'Recent actions (→ outcome):',
      summary.tools.join('\n'),
      memHint,
      '',
      'Each fact: {"name":"<short-kebab-slug>","description":"<one line>","type":"user|feedback|project|reference","body":"<1-3 sentences, the durable essence; cite the key evidence; link related memories as [[their-name]]>"}',
      'Output ONLY a JSON array (usually []). No prose, no fences.',
    ].join('\n');

    const emit = (t) => { try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit(t, { convId }); } catch (_) {} };
    emit('lessons:start');
    try {
      const out = await SandpieProviders.complete({ system: 'You extract durable memory facts from coding-session evidence. Precision over recall: an empty array beats a speculative fact.', user: prompt, maxTokens: 1024 });
      // Advance the cursor on a SUCCESSFUL call even when nothing was harvested —
      // those turns simply had nothing durable; don't re-examine them. On an
      // exception we leave the cursor put so the next turn retries.
      _distillCursor.set(convId, total);
      let arr = null;
      try { arr = JSON.parse(out); } catch (_) { const a = out.indexOf('['), b = out.lastIndexOf(']'); if (a >= 0 && b > a) { try { arr = JSON.parse(out.slice(a, b + 1)); } catch (_) {} } }
      if (!Array.isArray(arr) || !arr.length) return;
      let saved = 0;
      for (const f of arr.slice(0, 2)) {
        if (!f || !f.body) continue;
        try { const r = await SandpieMemory.save(f); if (r && r.ok) saved++; } catch (_) {}
      }
      if (saved) _augLog('[Aug] Harvested', saved, 'memory fact(s) for', project, '(tools', cursor, '→', total + ')');
    } catch (e) {
      console.warn('[Aug] Memory harvest failed:', e);
    } finally {
      emit('lessons:end');
    }
  }

  /* ── tool-call logging (called from conversations.js dispatch loop) ── */
  // Pull the files a `shell` command WRITES (output redirects + tee) plus its
  // cwd. shell args are {command, cwd, …} with no `path`, so without this every
  // shell-driven edit is invisible to the file/recent-path trackers. We only
  // extract unambiguous WRITE targets (not every path-looking token) to stay
  // robust — matching whole bash commands for filenames is a fragile game.
  function _shellFileTargets(cmd) {
    const out = new Set();
    if (typeof cmd !== 'string' || !cmd) return [];
    // Strip heredoc BODIES first: `cat > f << 'EOF' … EOF` embeds FILE CONTENT
    // (code full of >, =>, generics, comparisons) that must NOT be scanned for
    // redirects — otherwise `=> {`, `x > 21`, `=> panic!` get captured as targets.
    let scan = cmd.replace(/<<-?\s*(['"]?)(\w+)\1[\s\S]*?^[ \t]*\2[ \t]*$/gm, ' <<HEREDOC ');
    scan = scan.replace(/<<-?\s*(['"]?)\w+\1[\s\S]*$/g, ' <<HEREDOC ');   // unterminated heredoc
    // Only keep PATH-SHAPED tokens (contain "/" or end in a file extension) — this
    // rejects the junk (21, len, panic!, {, =, {:#x}) that a bare `>` before a code
    // token would otherwise yield.
    const keep = t => t && !t.startsWith('&') && !/^\/dev\//.test(t)
      && (t.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(t));
    for (const m of scan.matchAll(/\d*>>?\s*("[^"]+"|'[^']+'|[^\s|&;<>()]+)/g)) {
      const t = m[1].replace(/^['"]|['"]$/g, '');
      if (keep(t)) out.add(t);
    }
    for (const m of scan.matchAll(/\btee\s+(?:-a\s+)?("[^"]+"|'[^']+'|[^\s|&;<>()]+)/g)) {
      const t = m[1].replace(/^['"]|['"]$/g, '');
      if (keep(t)) out.add(t);
    }
    return [...out].slice(0, 8);
  }

  function logToolStarted(convId, tc) {
    const meta = getMeta(convId);
    const name = tc?.function?.name || 'unknown';
    let args = {};
    try { args = JSON.parse(tc?.function?.arguments || '{}'); } catch (_) {}
    meta.toolCalls.push({ name, args, phase: 'started', turn: meta.toolCalls.length + 1, ts: Date.now() });
    // Track file args
    if (args.path) { meta.files.add(args.path); trackRecentPath(convId, args.path); }
    if (args.src) { meta.files.add(args.src); trackRecentPath(convId, args.src); }
    // shell() has no path arg — capture its cwd + the files it writes so shell
    // work isn't invisible to recent-paths / lessons.
    if (name === 'shell') {
      if (args.cwd) { meta.files.add(args.cwd); trackRecentPath(convId, args.cwd); }
      for (const p of _shellFileTargets(args.command)) { meta.files.add(p); trackRecentPath(convId, p); }
    }
    // Track script references from run_python
    if (name === 'run_python' && args.path) meta.scripts.add(args.path);
    _augLog(`[Aug] start ${name}`, args.path || args.src || args.cwd || '');
  }

  function logToolResult(convId, result) {
    const meta = getMeta(convId);
    const last = meta.toolCalls[meta.toolCalls.length - 1];
    if (last) {
      last.phase = 'done';
      // Keep an OUTCOME snippet — the memory harvester needs evidence (what
      // actually happened), not just action shapes. Head+tail: errors and test
      // verdicts usually live at one of the two ends.
      const s = String(result || '').replace(/\s+/g, ' ').trim();
      last.result = s.length > 300 ? s.slice(0, 200) + ' … ' + s.slice(-80) : s;
    }
    // Scan for artifact/file creation patterns
    const text = String(result || '');
    const created = text.match(/Created:\s*([^\s]+)/);
    if (created) meta.files.add(created[1]);
    const written = text.match(/written to\s+([^\s]+)/i);
    if (written) meta.files.add(written[1]);
    const artifact = text.match(/artifact["']?\s*[:=]\s*["']?([^\s"']+)/i);
    if (artifact) meta.files.add(artifact[1]);
    _augLog(`[Aug] done  ${last ? last.name : '?'}`, `files=${meta.files.size}`);
  }

  /* ── (removed) file co-occurrence fingerprint + preload advisor.
     Was write-only: the fingerprint was rebuilt each conversation but its only
     reader (getPreloadFiles) was never wired in. Co-occurrence is a weak signal
     and mispredicted preloads pollute context, so the feature was dropped.
     Recent-paths + lessons below remain the live augmentations. ── */


  
  /* ── system prompt injection block ─────────────────────────────────── */
  async function systemBlock() {
    let block = '';
    // Recent paths: single global list (was per-project)
    // Recent paths
    if (localStorage.getItem('sandpie-recent-paths-enabled') !== 'false') {
      // Path-shape filter: cleans any pre-existing junk entries (21, len, panic!,
      // {, {:#x}) written before the _shellFileTargets fix, so they never reach the
      // prompt. The stored file self-heals via its 20-cap as real paths push them out.
      const paths = (await getRecentPaths()).filter(p => typeof p === 'string' && (p.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(p)));
      if (paths.length) {
        block += '\n\n## Recent paths\n\nFiles touched recently:\n' + paths.map(p => '- ' + p).join('\n') + '\n';
      }
    }
    // (Project-lessons injection removed: the distiller now harvests memory facts
    // into the ONE store — memory.js systemBlock injects them. Old *.lessons.md
    // files are inert; memory.js already skips them.)
    return block;
  }
/* ── public API ───────────────────────────────────────────────────── */
  global.SandpieAugmentations = {
    
    trackRecentPath,
    getRecentPaths,
    distillLessons,
    getConvMeta: getMeta,
    getConvPaths(convId) {
      const meta = convMeta.get(convId);
      if (!meta) return [];
      return [...meta.files].filter(p => typeof p === 'string' && (p.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(p)));
    },
    logToolStarted,
    logToolResult,
    systemBlock,
    stats() {
      const out = { conversations: convMeta.size, files: new Set(), toolCalls: 0 };
      for (const m of convMeta.values()) {
        out.toolCalls += m.toolCalls.length;
        m.files.forEach(f => out.files.add(f));
      }
      out.fileCount = out.files.size;
      _augLog('[Aug] stats:', out);
      return out;
    },
    _rawMeta: convMeta,
  };
})(window);
