// augmentations.js — Tool-call logger, recent-paths tracker, and project-lesson distiller.
// Loaded before conversations.js so SandpieAugmentations is available during dispatchAgentEvent().

(function (global) {
  'use strict';

  const MEMORY_DIR = 'sandpie/memory';
  const META_NS = '_sp_augment';

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
  function getProjectId(paths) {
    if (!paths || !paths.length) {
      try { return localStorage.getItem('sandpie-active-folder') || 'global'; } catch (_) { return 'global'; }
    }
    const ps = paths.filter(Boolean).map(p => p.replace(/\\/g, '/'));
    if (!ps.length) return 'global';
    const parts = ps[0].split('/');
    let prefix = '';
    for (let i = 0; i < parts.length; i++) {
      const cand = prefix + parts[i];
      if (ps.every(p => p.startsWith(cand + '/') || p === cand)) { prefix = cand + '/'; }
      else break;
    }
    return prefix.replace(/\/$/, '') || 'global';
  }

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
    // meta.files via getProjectId([...]) returned the full file path (incl. name)
    // and wrote to a garbage nested dir that the reader never looked in.
    const project = getProjectId();
    const storePath = MEMORY_DIR + '/' + project + '.recent-paths.json';
    let list = [];
    try { const raw = await opfs.read(storePath); if (raw) list = JSON.parse(raw); } catch (_) {}
    list = list.filter(p => p !== path);
    list.unshift(path);
    const max = Number(localStorage.getItem('sandpie-recent-paths-count') || '20');
    if (list.length > max) list = list.slice(0, max);
    await opfs.write(storePath, JSON.stringify(list, null, 2));
    // Mark dirty so it uploads and survives the Dropbox sync orphan-cleanup.
    try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', storePath); } catch (_) {}
  }

  async function getRecentPaths(projectHint) {
    const project = projectHint || 'global';
    try { const raw = await opfs.read(MEMORY_DIR + '/' + project + '.recent-paths.json'); if (raw) return JSON.parse(raw); } catch (_) {}
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
    // Same no-arg project id the reader (lessonSystemBlock) uses — deriving it
    // from meta.files wrote lessons to a path the reader never looked in.
    const project = getProjectId();
    const files = [...meta.files];
    // Only the tool calls SINCE the last distill (fromIdx) — the "what just
    // happened" the distiller reasons over. total is returned so the caller can
    // advance its cursor.
    const tools = meta.toolCalls.slice(fromIdx).map(tc => {
      const p = tc.args?.path || tc.args?.src || tc.args?.cwd || '';
      return '- ' + tc.name + (p ? ' "' + p + '"' : '');
    });
    return { project, files, tools, total: meta.toolCalls.length };
  }

  // Called at each TURN END (conversations.js gates on touchUpdated). Distills
  // lessons from the tool calls accrued since the last run, deduped against both
  // existing lessons AND saved memory facts, and advances the cursor so the same
  // turns are never re-examined. Silent + guarded — never breaks the turn.
  async function distillLessons(convId) {
    const meta = convMeta.get(convId);
    if (!meta) return;
    const total = meta.toolCalls.length;
    const cursor = _distillCursor.get(convId) || 0;
    if (total - cursor < MIN_NEW_TOOLCALLS) return;   // not enough new activity this turn
    if (localStorage.getItem('sandpie-lessons-enabled') === 'false') return;
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return;

    const summary = summarizeSession(convId, cursor);
    if (!summary || !summary.tools.length) return;
    const project = summary.project;
    const lessonPath = MEMORY_DIR + '/' + project + '.lessons.md';
    let existing = '';
    try { existing = await opfs.read(lessonPath) || ''; } catch (_) {}

    // Dedup against saved memory facts too, so a lesson never restates something
    // the remember tool already captured.
    let memHint = '';
    try {
      if (typeof window !== 'undefined' && window.SandpieMemory && SandpieMemory.list) {
        const facts = await SandpieMemory.list();
        if (facts.length) memHint = '\nAlready in memory (do NOT restate these):\n' + facts.map(f => '- ' + f.description).join('\n');
      }
    } catch (_) {}

    const prompt = [
      'You are a lesson distiller. From the RECENT actions below, extract 0-3 NEW lessons not already covered by the existing lessons or memory.',
      '',
      'A lesson is:',
      '- SPECIFIC to this project (not generic coding advice)',
      '- AVOID something that failed, or WHEN to do something that worked',
      '- 1 sentence, actionable',
      '- Do NOT state the obvious, and do NOT repeat anything already listed below',
      '',
      'Project: ' + project,
      'Files: ' + (summary.files.join(', ') || 'none'),
      'Recent actions:',
      summary.tools.join('\n'),
      existing ? '\nExisting lessons:\n' + existing : '',
      memHint,
      '',
      'Output ONLY markdown bullets (max 3 new ones), or nothing if there is no genuinely new lesson. No prose, no fences.',
    ].join('\n');

    const emit = (t) => { try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit(t, { convId }); } catch (_) {} };
    emit('lessons:start');
    try {
      const out = await SandpieProviders.complete({ system: 'You extract lessons from coding sessions.', user: prompt, maxTokens: 512 });
      // Advance the cursor on a SUCCESSFUL call even if it yielded no bullets —
      // those turns simply had nothing to learn; don't re-examine them. On an
      // exception we leave the cursor put so the next turn retries.
      _distillCursor.set(convId, total);
      if (!out || !out.trim()) return;
      const bullets = out.trim().split('\n').filter(l => l.trim().startsWith('- '));
      if (!bullets.length) return;
      const block = bullets.join('\n') + '\n';
      const updated = existing + (existing ? '\n' : '') + block;
      const maxLessons = Number(localStorage.getItem('sandpie-lessons-max') || '20');
      const all = updated.trim().split('\n').filter(l => l.trim().startsWith('- '));
      const trimmed = all.slice(-maxLessons).join('\n') + '\n';
      await opfs.write(lessonPath, trimmed);
      try { if (typeof Sandpie !== 'undefined' && Sandpie.events) Sandpie.events.emit('file:changed', lessonPath); } catch (_) {}
      console.log('[Aug] Distilled', bullets.length, 'lessons for', project, '(tools', cursor, '→', total + ')');
    } catch (e) {
      console.warn('[Aug] Lesson distillation failed:', e);
    } finally {
      emit('lessons:end');
    }
  }

  async function lessonSystemBlock(projectHint) {
    const project = projectHint || 'global';
    try {
      const raw = await opfs.read(MEMORY_DIR + '/' + project + '.lessons.md');
      if (!raw) return '';
      const maxLessons = Number(localStorage.getItem('sandpie-lessons-max') || '20');
      const bullets = raw.trim().split('\n').filter(l => l.trim().startsWith('- ')).slice(0, maxLessons);
      if (!bullets.length) return '';
      return '\n\n## Project lessons\n\n' + bullets.join('\n') + '\n\nThese are verified patterns specific to this project. Trust them.\n';
    } catch (_) { return ''; }
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
    console.log(`[Aug] start ${name}`, args.path || args.src || args.cwd || '');
  }

  function logToolResult(convId, result) {
    const meta = getMeta(convId);
    const last = meta.toolCalls[meta.toolCalls.length - 1];
    if (last) last.phase = 'done';
    // Scan for artifact/file creation patterns
    const text = String(result || '');
    const created = text.match(/Created:\s*([^\s]+)/);
    if (created) meta.files.add(created[1]);
    const written = text.match(/written to\s+([^\s]+)/i);
    if (written) meta.files.add(written[1]);
    const artifact = text.match(/artifact["']?\s*[:=]\s*["']?([^\s"']+)/i);
    if (artifact) meta.files.add(artifact[1]);
    console.log(`[Aug] done  ${last ? last.name : '?'}`, `files=${meta.files.size}`);
  }

  /* ── (removed) file co-occurrence fingerprint + preload advisor.
     Was write-only: the fingerprint was rebuilt each conversation but its only
     reader (getPreloadFiles) was never wired in. Co-occurrence is a weak signal
     and mispredicted preloads pollute context, so the feature was dropped.
     Recent-paths + lessons below remain the live augmentations. ── */


  
  /* ── system prompt injection block ─────────────────────────────────── */
  async function systemBlock() {
    let block = '';
    const project = getProjectId();
    // Recent paths
    if (localStorage.getItem('sandpie-recent-paths-enabled') !== 'false') {
      // Path-shape filter: cleans any pre-existing junk entries (21, len, panic!,
      // {, {:#x}) written before the _shellFileTargets fix, so they never reach the
      // prompt. The stored file self-heals via its 20-cap as real paths push them out.
      const paths = (await getRecentPaths(project)).filter(p => typeof p === 'string' && (p.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(p)));
      if (paths.length) {
        block += '\n\n## Recent paths\n\nFiles touched recently in this project:\n' + paths.map(p => '- ' + p).join('\n') + '\n';
      }
    }
    // Lessons
    if (localStorage.getItem('sandpie-lessons-enabled') !== 'false') {
      const lessons = await lessonSystemBlock(project);
      if (lessons) block += lessons;
    }
    return block;
  }
/* ── public API ───────────────────────────────────────────────────── */
  global.SandpieAugmentations = {
    getProjectId,
    trackRecentPath,
    getRecentPaths,
    distillLessons,
    lessonSystemBlock,
    getConvMeta: getMeta,
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
      console.log('[Aug] stats:', out);
      return out;
    },
    _rawMeta: convMeta,
  };
})(window);
