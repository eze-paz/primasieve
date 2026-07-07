// augmentations.js — Tool-call logger, co-occurrence fingerprint builder, and preload advisor.
// Loaded before conversations.js so SandpieAugmentations is available during dispatchAgentEvent().

(function (global) {
  'use strict';

  const FINGERPRINT_DIR = '.sandpie';
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

  async function trackRecentPath(convId, path) {
    if (!path) return;
    const meta = convMeta.get(convId);
    const project = meta ? getProjectId([...meta.files]) : 'global';
    const storePath = MEMORY_DIR + '/' + project + '.recent-paths.json';
    let list = [];
    try { const raw = await opfs.read(storePath); if (raw) list = JSON.parse(raw); } catch (_) {}
    list = list.filter(p => p !== path);
    list.unshift(path);
    const max = Number(localStorage.getItem('sandpie-recent-paths-count') || '20');
    if (list.length > max) list = list.slice(0, max);
    await opfs.write(storePath, JSON.stringify(list, null, 2));
  }

  async function getRecentPaths(projectHint) {
    const project = projectHint || 'global';
    try { const raw = await opfs.read(MEMORY_DIR + '/' + project + '.recent-paths.json'); if (raw) return JSON.parse(raw); } catch (_) {}
    return [];
  }

  /* ── lessons (distilled project-specific patterns) ─────────────────── */
  const _distilled = new Set(); // convId -> guard against duplicate distillation

  function summarizeSession(convId) {
    const meta = convMeta.get(convId);
    if (!meta || meta.toolCalls.length === 0) return null;
    const project = getProjectId([...meta.files]);
    const files = [...meta.files];
    const tools = meta.toolCalls.map(tc => {
      const p = tc.args?.path || tc.args?.src || '';
      return '- ' + tc.name + (p ? ' "' + p + '"' : '');
    });
    return { project, files, tools };
  }

  async function distillLessons(convId) {
    if (_distilled.has(convId)) return;
    const summary = summarizeSession(convId);
    if (!summary || summary.tools.length < 2) return;
    const project = summary.project;
    const lessonPath = MEMORY_DIR + '/' + project + '.lessons.md';
    let existing = '';
    try { existing = await opfs.read(lessonPath) || ''; } catch (_) {}

    const prompt = [
      'You are a lesson distiller. Given a session summary, extract 0-3 NEW lessons not already covered below.',
      '',
      'A lesson is:',
      '- SPECIFIC to this project (not generic coding advice)',
      '- AVOID something that failed, or WHEN to do something that worked',
      '- 1 sentence, actionable',
      '- Do NOT state the obvious',
      '',
      'Session:',
      'Project: ' + project,
      'Files: ' + (summary.files.join(', ') || 'none'),
      'Tools:',
      summary.tools.join('\n'),
      existing ? '\nExisting lessons:\n' + existing : '',
      '',
      'Output ONLY markdown bullets (max 3 new ones). No prose, no markdown fences.',
    ].join('\n');

    try { if (localStorage.getItem('sandpie-lessons-enabled') === 'false') return; } catch (_) {}
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return;
    try {
      const out = await SandpieProviders.complete({ system: 'You extract lessons from coding sessions.', user: prompt, maxTokens: 512 });
      if (!out || !out.trim()) return;
      const bullets = out.trim().split('\n').filter(l => l.trim().startsWith('- '));
      if (!bullets.length) return;
      const block = bullets.join('\n') + '\n';
      const updated = existing + (existing ? '\n' : '') + block;
      const maxLessons = Number(localStorage.getItem('sandpie-lessons-max') || '20');
      const all = updated.trim().split('\n').filter(l => l.trim().startsWith('- '));
      const trimmed = all.slice(-maxLessons).join('\n') + '\n';
      await opfs.write(lessonPath, trimmed);
      _distilled.add(convId);
      console.log('[Aug] Distilled', bullets.length, 'lessons for', project);
    } catch (e) {
      console.warn('[Aug] Lesson distillation failed:', e);
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
  function logToolStarted(convId, tc) {
    const meta = getMeta(convId);
    const name = tc?.function?.name || 'unknown';
    let args = {};
    try { args = JSON.parse(tc?.function?.arguments || '{}'); } catch (_) {}
    meta.toolCalls.push({ name, args, phase: 'started', turn: meta.toolCalls.length + 1, ts: Date.now() });
    // Track file args
    if (args.path) { meta.files.add(args.path); trackRecentPath(convId, args.path); }
    if (args.src) { meta.files.add(args.src); trackRecentPath(convId, args.src); }
    // Track script references from run_python
    if (name === 'run_python' && args.path) meta.scripts.add(args.path);
    console.log(`[Aug] start ${name}`, args.path || args.src || '');
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

  /* ── post-conversation: rebuild fingerprint from chat log + meta ───── */
  async function rebuildFingerprint(convId) {
    const meta = convMeta.get(convId);
    if (!meta || meta.toolCalls.length === 0) return;

    const folder = meta.folder || 'global';
    const fpPath = `${FINGERPRINT_DIR}/fingerprint.json`;
    console.log(`[Aug] Rebuilding fingerprint for ${folder}: ${meta.toolCalls.length} tool calls, ${meta.files.size} files`);

    // 1. Build turn-grouped file touches from logged tool calls
    const turns = new Map(); // turnIndex -> Set(file_paths)
    meta.toolCalls.forEach((tc, idx) => {
      const turnIdx = Math.floor(idx / 2); // each user turn ≈ pair of assistant events
      if (!turns.has(turnIdx)) turns.set(turnIdx, new Set());
      const s = turns.get(turnIdx);
      // Files mentioned in tool args
      const path = tc.args?.path || tc.args?.src;
      if (path) s.add(cleanPath(path));
      // If this tool_result completed successfully, try to infer output files
      if (tc.phase === 'done' && tc.name === 'run_python' && tc.args?.path) {
        s.add(cleanPath(tc.args.path));
      }
      if (tc.args?.code && typeof tc.args.code === 'string') {
        const paths = extractFilePathsFromCode(tc.args.code);
        paths.forEach(p => s.add(cleanPath(p)));
      }
    });
    // Also inject explicitly tracked files from meta.files
    meta.files.forEach(f => {
      const p = cleanPath(f);
      // Bucket into the last turn
      const lastTurn = Math.max(0, turns.size - 1);
      if (!turns.has(lastTurn)) turns.set(lastTurn, new Set());
      turns.get(lastTurn).add(p);
    });

    // 2. Count co-occurrences
    const cooccur = new Map(); // "a\t\tb" -> count
    for (const [, files] of turns) {
      const arr = [...files].filter(Boolean).sort();
      for (let i = 0; i < arr.length; i++) {
        for (let j = i + 1; j < arr.length; j++) {
          const key = arr[i] + '\t' + arr[j];
          cooccur.set(key, (cooccur.get(key) || 0) + 1);
        }
      }
    }
    if (cooccur.size === 0) return;

    // 3. Normalize to weights
    const totals = new Map();
    for (const [key, count] of cooccur) {
      const [a, b] = key.split('\t');
      totals.set(a, (totals.get(a) || 0) + count);
      totals.set(b, (totals.get(b) || 0) + count);
    }

    const newAssoc = {}; // file -> { file: weight }
    for (const [key, count] of cooccur) {
      const [a, b] = key.split('\t');
      const maxTot = Math.max(totals.get(a) || 1, totals.get(b) || 1);
      const w = Math.round((count / maxTot) * 100) / 100;
      if (w >= 0.15) {
        if (!newAssoc[a]) newAssoc[a] = {};
        if (!newAssoc[b]) newAssoc[b] = {};
        newAssoc[a][b] = Math.max(newAssoc[a][b] || 0, w);
        newAssoc[b][a] = Math.max(newAssoc[b][a] || 0, w);
      }
    }

    // 4. Merge with existing fingerprint
    let existing = { last_folder: folder, conversations: 0, turns: 0, associations: {} };
    try {
      const raw = await opfs.read(fpPath);
      if (raw) existing = JSON.parse(raw);
    } catch (_) {}

    existing.last_updated = new Date().toISOString();
    existing.last_folder  = folder;
    existing.conversations = (existing.conversations || 0) + 1;
    existing.turns = (existing.turns || 0) + turns.size;

    // Merge associations (boost existing, add new)
    for (const [a, peers] of Object.entries(newAssoc)) {
      if (!existing.associations[a]) existing.associations[a] = {};
      for (const [b, w] of Object.entries(peers)) {
        const old = existing.associations[a][b] || 0;
        // Exponential moving average
        existing.associations[a][b] = Math.round((0.7 * old + 0.3 * w) * 100) / 100;
      }
    }

    // Trim stale (<0.20 after decay)
    for (const a of Object.keys(existing.associations || {})) {
      for (const b of Object.keys(existing.associations[a])) {
        existing.associations[a][b] = Math.round(existing.associations[a][b] * 0.95 * 100) / 100;
        if (existing.associations[a][b] < 0.15) delete existing.associations[a][b];
      }
      if (Object.keys(existing.associations[a]).length === 0) delete existing.associations[a];
    }

    await opfs.write(fpPath, JSON.stringify(existing, null, 2));
    console.log(`[Aug] Fingerprint saved: ${fpPath} (${Object.keys(existing.associations).length} associations)`);
  }

  /* ── preload advisor: called at turn 0 of a new conversation ───────── */
  async function getPreloadFiles(targetPathOrFolder, topN = 5) {
    const fpPath = `${FINGERPRINT_DIR}/fingerprint.json`;
    let fp;
    try { fp = JSON.parse(await opfs.read(fpPath) || '{}'); } catch (_) { return []; }
    const assoc = fp.associations || {};
    const candidates = new Map();

    // If targetPathOrFolder is an existing file, boost its associates
    if (targetPathOrFolder && assoc[targetPathOrFolder]) {
      for (const [b, w] of Object.entries(assoc[targetPathOrFolder])) {
        candidates.set(b, (candidates.get(b) || 0) + w);
      }
    }
    // Also boost any files in a similar path prefix
    if (targetPathOrFolder) {
      const prefix = targetPathOrFolder.includes('/') ? targetPathOrFolder.split('/').slice(0, -1).join('/') + '/' : '';
      for (const [a, peers] of Object.entries(assoc)) {
        if (a.startsWith(prefix)) {
          for (const [b, w] of Object.entries(peers)) {
            candidates.set(b, (candidates.get(b) || 0) + w * 0.5);
          }
        }
      }
    }

    return [...candidates.entries()]
      .sort((x, y) => y[1] - x[1])
      .slice(0, topN)
      .map(([p]) => p);
  }

  /* ── helpers ──────────────────────────────────────────────────────── */
  function cleanPath(p) {
    if (!p) return '';
    // Normalize leading slashes, collapse ./ and ../ simply
    return p.replace(/^\//, '').replace(/\/+/g, '/').replace(/^\.\/+/g, '');
  }

  function extractFilePathsFromCode(code) {
    const paths = [];
    // Naïve but deterministic: match strings that look like file paths
    const re = /['"]([^'"]*\.(?:js|mjs|cjs|ts|py|rs|md|txt|csv|json|html|css|scss|docx|xlsx|pptx|pdf|tex|png|jpg|jpeg|svg))['"]/gi;
    let m;
    while ((m = re.exec(code)) !== null) paths.push(m[1]);
    return paths;
  }


  /* ── settings panel ──────────────────────────────────────────────── */
  const RP_HTML = [
    '<div class="settings-group">',
    '  <label class="settings-row"><input type="checkbox" id="sp-rp-enabled"> Enable recent-paths memory</label>',
    '  <div class="settings-row">',
    '    <label for="sp-rp-count">Paths to remember (5-100):</label>',
    '    <input type="number" id="sp-rp-count" min="5" max="100" style="width:4em;margin-left:0.5em">',
    '  </div>',
    '  <p class="settings-hint">Tracks files you recently read or edited, per project. Injected into the system prompt.</p>',
    '</div>',
  ].join("\n");

  const LESSONS_HTML = [
    '<div class="settings-group">',
    '  <label class="settings-row"><input type="checkbox" id="sp-rp-enabled"> Enable recent-paths memory</label>',
    '  <div class="settings-row">',
    '    <label for="sp-rp-count">Paths to remember (5–100):</label>',
    '    <input type="number" id="sp-rp-count" min="5" max="100" style="width:4em;margin-left:0.5em">',
    '  </div>',
    '  <p class="settings-hint">Tracks files you recently read or edited, per project. Injected into the system prompt.</p>',
    '</div>',
    '<div class="settings-group">',
    '  <label class="settings-row"><input type="checkbox" id="sp-lessons-enabled"> Enable lesson distillation</label>',
    '  <div class="settings-row">',
    '    <label for="sp-lessons-max">Max lessons per project (5–30):</label>',
    '    <input type="number" id="sp-lessons-max" min="5" max="30" style="width:4em;margin-left:0.5em">',
    '  </div>',
    '  <p class="settings-hint">After each session, the AI extracts 0–3 project-specific lessons. Injected into future prompts.</p>',
    '</div>',
  ].join('\n');

  function wireRPSettings(panel) {
    const cb = panel.querySelector('#sp-rp-enabled');
    const num = panel.querySelector('#sp-rp-count');
    if (!cb) return;
    cb.checked = localStorage.getItem('sandpie-recent-paths-enabled') !== 'false';
    num.value = localStorage.getItem('sandpie-recent-paths-count') || '20';
    cb.addEventListener('change', () => localStorage.setItem('sandpie-recent-paths-enabled', cb.checked ? 'true' : 'false'));
    num.addEventListener('change', () => {
      let v = parseInt(num.value, 10);
      if (!Number.isFinite(v) || v < 5) v = 5;
      if (v > 100) v = 100;
      num.value = v;
      localStorage.setItem('sandpie-recent-paths-count', String(v));
    });
  }

  function wireLessonsSettings(panel) {
    const cb = panel.querySelector('#sp-lessons-enabled');
    const num = panel.querySelector('#sp-lessons-max');
    if (!cb) return;
    cb.checked = localStorage.getItem('sandpie-lessons-enabled') !== 'false';
    num.value = localStorage.getItem('sandpie-lessons-max') || '20';
    cb.addEventListener('change', () => localStorage.setItem('sandpie-lessons-enabled', cb.checked ? 'true' : 'false'));
    num.addEventListener('change', () => {
      let v = parseInt(num.value, 10);
      if (!Number.isFinite(v) || v < 5) v = 5;
      if (v > 30) v = 30;
      num.value = v;
      localStorage.setItem('sandpie-lessons-max', String(v));
    });
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
    rebuildFingerprint,
    getPreloadFiles,
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
