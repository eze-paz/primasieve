// augmentations.js — Tool-call logger, recent-paths tracker, and tool-outcome capture.
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
      // Keep an OUTCOME snippet (head+tail) so the RAM meta records what
      // actually happened, not just the action shape. Errors and test verdicts
      // usually live at one of the two ends.
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
     Recent-paths below remains the live augmentation. ── */


  
  /* ── system prompt injection block ─────────────────────────────────── */
  async function systemBlock() {
    let block = '';
    // Recent paths: always on when memory is enabled — the separate enable lever
    // was removed 2026-08-07; the single "Enable automatic memory" checkbox gates
    // both the memory facts (memory.js systemBlock) and this recent-paths block.
    if (typeof SandpieMemory === 'undefined' || !SandpieMemory.isEnabled()) return block;
    // Path-shape filter: cleans any pre-existing junk entries (21, len, panic!,
    // {, {:#x}) written before the _shellFileTargets fix, so they never reach the
    // prompt. The stored file self-heals via its 50-cap as real paths push them out.
    const shaped = (await getRecentPaths())
      .filter(p => typeof p === 'string' && (p.includes('/') || /\.[A-Za-z0-9]{1,8}$/.test(p)))
      .map(p => p.replace(/^\/+/, '').replace(/^files\//, ''))
      .slice(0, 40);
    // EXISTENCE filter: only inject paths that STILL resolve in OPFS. Recorded
    // paths include the model's own typos (a hyphen/underscore variant, a slash
    // that became a hyphen) and since-deleted files; feeding those back makes the
    // model chase a path that never existed. Checked in parallel; on a transient
    // lookup error keep the path rather than lose real data.
    const checked = await Promise.all(shaped.map(async p => {
      try { return (await opfs.exists(p)) ? p : null; } catch (_) { return p; }
    }));
    const paths = checked.filter(Boolean);
    if (paths.length) {
      block += '\n\n## Recent paths\n\nFiles touched recently:\n' + paths.map(p => '- ' + p).join('\n') + '\n';
    }
    // (Lessons/harvest injection removed: the auto-harvester (distillLessons) was
    // eliminated 2026-08-07 — the remember tool is the only capture channel. Old
    // *.lessons.md files are inert; memory.js already skips them.)
    return block;
  }
/* ── public API ───────────────────────────────────────────────────── */
  global.SandpieAugmentations = {
    
    trackRecentPath,
    getRecentPaths,
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
