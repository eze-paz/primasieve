// sandpie /modules/tools.js — Tool schema definitions

const tools = {
  run_python: {
    description: `Execute a Python script from OPFS via Pyodide. Working dir is /files/ (persistent).
REQUIRED: path must point to a script already saved in OPFS (typically under sandpie/scripts/). Use write_file to create a script first, then call run_python with its path.
ONLY path: + args: are accepted. Scripts must be saved to OPFS before execution.
ASYNC: your code runs ON an already-running event loop, so TOP-LEVEL await works — call coroutines directly (end the script with await main(), which works even inside an if __name__ == '__main__': block). Do NOT use asyncio.run(), loop.run_until_complete(), or asyncio.new_event_loop() — they raise "event loop is already running". Do NOT use time.sleep() (it freezes the whole app) — use await asyncio.sleep(n).
PACKAGES: ~100 prebuilt (numpy, pandas, scipy, matplotlib, bs4, lxml, micropip…) — just import. Others: await micropip.install('name') then import. No compiled C extensions, no subprocess.
HTTP: no sockets, so requests/urllib don't work. Use pyodide.http.pyfetch (async): r = await pyfetch(url); data = await r.json() (also await r.bytes() / await r.string()). Non-CORS hosts: pyfetch('/proxy/host/path').
OUTPUT: write to sandpie/artifacts/, then call show_artifact({"path":"sandpie/artifacts/file.html"}).
Examples:
  run      → {path: "sandpie/scripts/random_numbers.py", args: ["5"]}
  with arg → {path: "sandpie/scripts/analyze_machine.py", args: ["2026-05-03.csv"]}
  async    → script ends with await main()  (NOT asyncio.run(main()))
  pypi     → script runs: import micropip; await micropip.install('feedparser')
  html out → script writes sandpie/artifacts/out.html, then show_artifact({"path":"sandpie/artifacts/out.html"})`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Path under /files/ to a saved Python script (e.g. "sandpie/scripts/foo.py"). When set, sandpie reads that file and execs it with sys.argv = [path, *args].' },
        args: { type: 'array', items: { type: 'string' }, description: 'CLI args passed via sys.argv when path is used.' },
      },
      required: ['path'],
    },
  },
  write_file: {
  description: `Create a NEW file in OPFS under /files/. If the file already exists it is NOT overwritten — its current content is returned instead, so you can edit_file it in place (don't rewrite it or save a renamed copy). Path is relative to /files/ (e.g. "sandpie/scripts/analyze.py", "sandpie/artifacts/chart.html"). Use this to create scripts before running them with run_python.`,
  parameters: {
    type: 'object',
    properties: {
      path:    { type: 'string', description: 'OPFS path relative to /files/' },
      content: { type: 'string', description: 'Full file content' },
    },
    required: ['path', 'content'],
  },
},
edit_file: {
  description: `Replace a string in an existing OPFS file — the PREFERRED way to change a file. Matching is forgiving: exact first, then ignoring line-ending and trailing-whitespace differences, so a small whitespace drift won't fail. old_str must still resolve to ONE place (otherwise it returns the match count + line numbers, or the closest lines, so you can retry precisely). Read the file first to copy exact content (do NOT include read_file's line-number prefixes in old_str). To FIX a script that errored, edit_file the offending lines — NEVER rewrite the whole file or save a renamed copy.`,
  parameters: {
    type: 'object',
    properties: {
      path:    { type: 'string', description: 'OPFS path relative to /files/' },
      old_str: { type: 'string', description: 'Exact string to replace. Must match exactly once.' },
      new_str: { type: 'string', description: 'Replacement string. Omit to delete old_str.' },
    },
    required: ['path', 'old_str'],
  },
},
  read_file: {
    description: `Read a UTF-8 text file from OPFS (/files/). PREFER THIS over run_python for reading — it's instant and can't crash the runtime. Output is line-numbered as "<n>\\t<line>"; the numbers are for reference only — never include them when calling write_file/edit_file. Reports total lines + byte size. For large files or head/tail, page with offset (1-based start line) + limit. For images use load_image instead.`,
    parameters: {
      type: 'object',
      properties: {
        path:   { type: 'string', description: 'OPFS path relative to /files/ (e.g. "sandpie/scripts/foo.py").' },
        offset: { type: 'integer', description: '1-based line to start at (default 1). Use for paging / tail.' },
        limit:  { type: 'integer', description: 'Max lines to return (default 2000).' },
      },
      required: ['path'],
    },
  },
  list_files: {
    description: `List files and folders with size + modified time. PREFER THIS over run_python for browsing. Default lists the immediate contents of "path" (like ls). Find files BY NAME with a glob "pattern" (e.g. "**/*.md"); find files BY CONTENT with search.

"path" can be relative (your workspace, default) OR an absolute Dropbox path (e.g. "/R+D+I/reports") to browse elsewhere in Dropbox. For a Dropbox path, list shallowly and drill into a subfolder — recursive:true on a large/unknown Dropbox tree is capped (~1500 entries, not the whole tree) and is the wrong tool for broad discovery.`,
    parameters: {
      type: 'object',
      properties: {
        path:      { type: 'string', description: 'Directory relative to /files/ (default: root), or an absolute Dropbox path (e.g. "/R+D+I/reports").' },
        pattern:   { type: 'string', description: 'Glob to filter names/paths: * (within a segment), ** (across folders), ? (one char). E.g. "**/*.json".' },
        recursive: { type: 'boolean', description: 'Walk subfolders (default false). Use only on a small, specific folder; recursing a large/unknown Dropbox subtree is capped — list shallowly and drill down instead.' },
      },
      required: [],
    },
  },
  search: {
    description: `Search file CONTENTS by regular expression, returning matches as "path:line: text". PREFER THIS over run_python for grep-style search. Scope with "path": a subtree relative to your workspace (default: everything), OR an absolute Dropbox path (e.g. "/R+D+I/reports") to search elsewhere in the user's Dropbox. Also "include" (a name glob like "*.js"). files_only:true returns just the matching files. Case-insensitive unless ignore_case:false. When some files aren't downloaded locally, it also lists matching cloud files (open them with read_file). (To find files by NAME, use list_files.) Skips /sandpie/conversations unless "path" points inside it.`,
    parameters: {
      type: 'object',
      properties: {
        pattern:     { type: 'string', description: 'JavaScript regular expression matched per line (e.g. "function\\\\s+\\\\w+", "TODO").' },
        path:        { type: 'string', description: 'Subtree relative to your workspace (default: everything), or an absolute Dropbox path (e.g. "/Shared/reports") to search elsewhere in Dropbox.' },
        include:     { type: 'string', description: 'Only search files whose name/path matches this glob (e.g. "*.py").' },
        files_only:  { type: 'boolean', description: 'Return just matching file paths instead of per-line matches.' },
        ignore_case: { type: 'boolean', description: 'Case-insensitive (default true).' },
      },
      required: ['pattern'],
    },
  },
  show_artifact: {
    description: `Render a file from OPFS as a live artifact injected directly into the chat.
Use this whenever:
- The user says "show this", "artifact", "add into chat", "inject", "put in the DOM", or similar
- You have written any visual output (HTML page, plot, SVG, chart, dataframe, image) to OPFS
The file must already exist in OPFS — write it first with run_python, then call this.
Supported types: .html (full page, CDN JS works), .svg, .png, .jpg, .gif, .csv, .txt.
Path is OPFS-relative — do NOT include a leading slash (e.g. "sandpie/artifacts/chart.html").
Default output folder is sandpie/artifacts/ — use it unless the user specifies a different path.
Typical flow:
  run_python: open('sandpie/artifacts/chart.html', 'w').write(html)
  show_artifact: { "path": "sandpie/artifacts/chart.html" }`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'OPFS path to the file (e.g. "sandpie/artifacts/chart.html"). No leading slash. Default folder: sandpie/artifacts/.' },
      },
      required: ['path'],
    },
  },
    load_skill: {
      description: `Load a skill's full instructions by name (the available skills and when to use each are listed in the "# Skills" section). Don't re-load one already marked "(already loaded above)".`,
      parameters: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'The skill name from the Skills section (e.g. "sandpie_deploy").' },
        },
        required: ['name'],
      },
    },
        load_image: {
      description: `Load an image file from OPFS so you can see its pixel content. The image is returned as part of this tool call — you will see it immediately on the next step, no further action needed.
WHEN TO USE: Only when the user asks about an image stored in /files/ AND that image is NOT already attached to their current message. Example: user says "look at images/cat.png" with no inline attachment — call this with path="images/cat.png".
WHEN NOT TO USE: If the user's current message already contains an image (an image_url content block, an inline image, a photo they just attached/pasted/dropped), DO NOT call this tool. The image is already visible to you — describe it directly. Calling load_image in that case wastes a turn and ignores what the user actually sent. Never call this on a guessed filename from a directory listing.
Supports JPEG, PNG, GIF, WEBP. Path is relative to /files/.
Large images are refused: if a file's base64 form would exceed ~5 MB it is NOT loaded and you get an error instead — downscale it first with run_python + Pillow (e.g. img.thumbnail((1568,1568))) and load the smaller copy.`,
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to image file relative to /files/ (e.g. "beach.jpg" or "images/photo.png")' },
        },
        required: ['path'],
      },
    },
    copy_to_workspace: {
      description: `Copy a file from ELSEWHERE in the user's Dropbox INTO their workspace so you can use it. Use this after the search tool returns a file OUTSIDE the workspace (an absolute Dropbox path like "/R+D+I/reports/q1.pdf") that you need to read or process — read_file/run_python/load_image cannot reach paths outside the workspace directly. The copy is server-side and READ-ONLY on the source (the original is never modified, moved, or deleted). Returns the new workspace-relative path; then use read_file / run_python / load_image on it as normal.`,
      parameters: {
        type: 'object',
        properties: {
          src:  { type: 'string', description: 'Absolute Dropbox path of the file to copy in (as returned by search), e.g. "/R+D+I/reports/q1.pdf".' },
          dest: { type: 'string', description: 'Optional destination within the workspace (default: the source filename), e.g. "imported/q1.pdf".' },
        },
        required: ['src'],
      },
    },
};
// ── Enable/disable + description overrides (global, localStorage) ─────────────
// Lets the user (Settings → System prompt) turn tools off and rewrite their
// descriptions. Stored globally so it applies to every conversation. toolDefs()
// — what's actually sent to the model — is the single choke point that honors it.
const TOOLS_DISABLED_KEY = 'sandpie-tools-disabled';   // JSON array of disabled names
const TOOLS_DESC_KEY     = 'sandpie-tools-desc';       // JSON map { name: customDescription }
function _toolsReadJson(key, fallback) {
  try { const v = JSON.parse(localStorage.getItem(key) || 'null'); return v == null ? fallback : v; }
  catch { return fallback; }
}
function _toolsDisabledSet() { const a = _toolsReadJson(TOOLS_DISABLED_KEY, []); return new Set(Array.isArray(a) ? a : []); }
function _toolsDescMap() { const m = _toolsReadJson(TOOLS_DESC_KEY, {}); return (m && typeof m === 'object') ? m : {}; }
// A tool may be present but unavailable (e.g. copy_to_workspace needs Dropbox).
function _toolAvailable(name) {
  if (name === 'copy_to_workspace') {
    try { const p = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider(); return !!(p && p.isConnected && p.isConnected()); }
    catch (_) { return false; }
  }
  return true;
}

const SandpieTools = {
  names() { return Object.keys(tools); },
  defaultDescription(name) { return tools[name] ? tools[name].description : ''; },
  description(name) { const o = _toolsDescMap(); return (o[name] != null) ? o[name] : SandpieTools.defaultDescription(name); },
  isCustom(name) { const o = _toolsDescMap(); return o[name] != null && o[name] !== SandpieTools.defaultDescription(name); },
  isEnabled(name) { return !_toolsDisabledSet().has(name); },
  isAvailable(name) { return _toolAvailable(name); },
  setEnabled(name, on) {
    const s = _toolsDisabledSet();
    if (on) s.delete(name); else s.add(name);
    localStorage.setItem(TOOLS_DISABLED_KEY, JSON.stringify([...s]));
  },
  setDescription(name, text) {
    const o = _toolsDescMap();
    if (text == null || String(text).trim() === '' || text === SandpieTools.defaultDescription(name)) delete o[name];
    else o[name] = String(text);
    localStorage.setItem(TOOLS_DESC_KEY, JSON.stringify(o));
  },
  resetDescription(name) { const o = _toolsDescMap(); delete o[name]; localStorage.setItem(TOOLS_DESC_KEY, JSON.stringify(o)); },
  // Everything the settings UI needs to render a row, in catalog order.
  list() {
    return Object.keys(tools).map(name => ({
      name,
      description: SandpieTools.description(name),
      defaultDescription: SandpieTools.defaultDescription(name),
      custom: SandpieTools.isCustom(name),
      enabled: SandpieTools.isEnabled(name),
      available: _toolAvailable(name),
    }));
  },
};
window.SandpieTools = SandpieTools;

const toolDefs = () => Object.entries(tools)
  .filter(([name]) => SandpieTools.isEnabled(name) && _toolAvailable(name))
  .map(([name]) => ({
    type: 'function',
    function: { name, description: SandpieTools.description(name), parameters: tools[name].parameters },
  }));

