// augmentations.js — Tool-call logger, co-occurrence fingerprint builder, and preload advisor.
// Loaded before conversations.js so SandpieAugmentations is available during dispatchAgentEvent().

(function (global) {
  'use strict';

  const FINGERPRINT_DIR = '.sandpie';
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

  /* ── tool-call logging (called from conversations.js dispatch loop) ── */
  function logToolStarted(convId, tc) {
    const meta = getMeta(convId);
    const name = tc?.function?.name || 'unknown';
    let args = {};
    try { args = JSON.parse(tc?.function?.arguments || '{}'); } catch (_) {}
    meta.toolCalls.push({ name, args, phase: 'started', turn: meta.toolCalls.length + 1, ts: Date.now() });
    // Track file args
    if (args.path) meta.files.add(args.path);
    if (args.src) meta.files.add(args.src);
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

  /* ── public API ───────────────────────────────────────────────────── */
  global.SandpieAugmentations = {
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
