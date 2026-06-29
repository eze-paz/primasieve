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
SCOPE — by default lists your WORKSPACE (the synced working folder); "path" is then relative. To browse the wider connected Dropbox set scope:"dropbox" — then "path" is an ABSOLUTE Dropbox folder (e.g. "/R+D+I/reports"), default = root. (A bare "/" is the workspace root, not all of Dropbox — use scope:"dropbox".) For a Dropbox listing, list shallowly and drill into a subfolder: recursive:true on a large/unknown tree is capped (~1500 entries, not the whole tree).`,
    parameters: {
      type: 'object',
      properties: {
        scope:     { type: 'string', enum: ['workspace', 'dropbox'], description: '"workspace" (default) = list your synced working folder; "dropbox" = list the wider connected Dropbox ("path" = an absolute folder, default = root).' },
        path:      { type: 'string', description: 'With scope "workspace" (default): directory relative to /files/ (default: root). With scope "dropbox": an absolute Dropbox folder to list (e.g. "/R+D+I/reports"), default = Dropbox root.' },
        pattern:   { type: 'string', description: 'Glob to filter names/paths: * (within a segment), ** (across folders), ? (one char). E.g. "**/*.json".' },
        recursive: { type: 'boolean', description: 'Walk subfolders (default false). Use only on a small, specific folder; recursing a large/unknown Dropbox subtree is capped — list shallowly and drill down instead.' },
      },
      required: [],
    },
  },
  search: {
    description: `Find files by CONTENT or NAME. PREFER THIS over run_python for grep-style search.
WORKSPACE (default scope) — greps file CONTENTS in your synced working folder by regex; "path" scopes to a subtree; matches return as "path:line: text" (on-demand files not downloaded locally are also listed as cloud matches to open with read_file).
DROPBOX (scope:"dropbox") — a Dropbox KEYWORD search over file NAMES + text contents: give plain keywords, NOT regex (only the literal words ≥3 chars in "pattern" are used — "Reixach.*compressor" just searches "Reixach compressor"). "path" = an absolute folder to narrow (e.g. "/R+D+I"), default = all of Dropbox. A bare "/" is the workspace root, not Dropbox; up to 100 matches/page (use "offset" to page).
"include" filters results by file type / name glob (e.g. "*.jpg", "*.{pdf,docx}") — works in BOTH scopes. files_only:true returns just paths. Case-insensitive unless ignore_case:false. Skips /sandpie/conversations unless "path" points inside it.
IMAGES, PDFs and other binaries: their CONTENTS aren't searchable — find them by NAME keywords + the extension (e.g. pattern:"compressor reixach", include:"*.jpg"), or browse the folder with list_files(scope:"dropbox").`,
    parameters: {
      type: 'object',
      properties: {
        pattern:     { type: 'string', description: 'WORKSPACE scope: a JS regex matched per line (e.g. "function\\\\s+\\\\w+"). DROPBOX scope: its literal words become the keyword query (regex/wildcards ignored — just give keywords, e.g. "compressor reixach").' },
        scope:       { type: 'string', enum: ['workspace', 'dropbox'], description: '"workspace" (default) = search your synced working folder; "dropbox" = search the wider connected Dropbox (use "path" to narrow to an absolute folder).' },
        path:        { type: 'string', description: 'With scope "workspace" (default): a subtree relative to your workspace (default: everything). With scope "dropbox": an absolute Dropbox folder to narrow it (e.g. "/R+D+I"), default = all of Dropbox.' },
        include:     { type: 'string', description: 'Filter results by file type / name glob (e.g. "*.jpg", "*.{pdf,docx}"). Works in both scopes; in dropbox scope it narrows to those file types.' },
        files_only:  { type: 'boolean', description: 'Return just matching file paths instead of per-line matches.' },
        ignore_case: { type: 'boolean', description: 'Case-insensitive (default true).' },
        offset:      { type: 'integer', description: 'For a scope:"dropbox" search with many matches: skip this many results to page through them, 100 per page (e.g. offset:100 for the next page). Default 0.' },
      },
      required: ['pattern'],
    }
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
    local_shell: {
      description: `Run a command on the USER'S OWN computer — the real machine running this browser (PowerShell on Windows, bash/zsh on macOS/Linux) — via the locally-installed "localterm" helper, and get back stdout, stderr and the exit code.

This is the user's ACTUAL operating system, not a sandbox. Use it only when the user wants something done on their own machine: inspect or edit their files, run a build/test, git, check versions, system info, install a package, etc. This tool is OFF by default; if you can call it, the user deliberately enabled it — but still avoid destructive commands (rm -rf, format, mass deletes, overwrites) unless they clearly asked.
DON'T confuse with the sandbox: for Python data work in the in-browser sandbox use run_python; for the OPFS workspace files use read_file/write_file/list_files. local_shell is for the user's real OS.
Each call is a fresh, independent run: there is NO persistent state between calls (cwd, env, and variables reset every time) — chain steps in ONE call with ; or && (e.g. "cd path; ls", "cd path && cmd"). Multi-line commands are fine — the whole block is parsed and run. You get clean stdout, stderr, and an exit code. There is NO interactive TTY, so don't launch full-screen/interactive programs (vim, top, REPLs, an ssh login prompt); use non-interactive flags. Long output is truncated.
If it says the helper isn't running, tell the user to start localterm (sandpie Terminal panel → Download) and STOP — do not retry in a loop.`,
      parameters: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'The command to run in the user default shell (e.g. "git -C ~/proj status", "node -v", "ls -la"). Chain multiple steps with ; or &&.' },
          timeout: { type: 'integer', description: 'Max seconds before the command is killed (default 60, max 300).' },
        },
        required: ['command'],
      },
    },
};
// ── Enable/disable + description overrides (global, localStorage) ─────────────
// Lets the user (Settings → System prompt) turn tools off and rewrite their
// descriptions. Stored globally so it applies to every conversation. toolDefs()
// — what's actually sent to the model — is the single choke point that honors it.
const TOOLS_DISABLED_KEY = 'sandpie-tools-disabled';   // JSON array of disabled names
const TOOLS_DESC_KEY     = 'sandpie-tools-desc';       // JSON map { name: customDescription }
const TOOLS_ENABLED_KEY  = 'sandpie-tools-enabled';    // JSON array of explicitly-ON names (for default-off tools)
// Tools that stay OFF until the user explicitly turns them on. They NEVER auto-enable:
// isEnabled returns false unless the name is in TOOLS_ENABLED_KEY (set only by setEnabled).
const TOOLS_DEFAULT_OFF  = new Set(['local_shell']);
function _toolsReadJson(key, fallback) {
  try { const v = JSON.parse(localStorage.getItem(key) || 'null'); return v == null ? fallback : v; }
  catch { return fallback; }
}
function _toolsDisabledSet() { const a = _toolsReadJson(TOOLS_DISABLED_KEY, []); return new Set(Array.isArray(a) ? a : []); }
function _toolsEnabledSet() { const a = _toolsReadJson(TOOLS_ENABLED_KEY, []); return new Set(Array.isArray(a) ? a : []); }
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
  isEnabled(name) {
    if (TOOLS_DEFAULT_OFF.has(name)) return _toolsEnabledSet().has(name);   // off until explicitly enabled
    return !_toolsDisabledSet().has(name);
  },
  isAvailable(name) { return _toolAvailable(name); },
  setEnabled(name, on) {
    if (TOOLS_DEFAULT_OFF.has(name)) {       // default-off tools track explicit ON, not OFF
      const e = _toolsEnabledSet();
      if (on) e.add(name); else e.delete(name);
      localStorage.setItem(TOOLS_ENABLED_KEY, JSON.stringify([...e]));
      return;
    }
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
  schemas() { return toolDefs(); },
  schemaFor(name) { const s = toolDefs(); return s.find(t => t.function && t.function.name === name); },
};
window.SandpieTools = SandpieTools;

const toolDefs = () => Object.entries(tools)
  .filter(([name]) => SandpieTools.isEnabled(name) && _toolAvailable(name))
  .map(([name]) => {
    let description = SandpieTools.description(name);
    // Tell the model WHERE its workspace sits in Dropbox so a scope:"dropbox"
    // search can target the parent shared folder precisely (e.g. /R+D+I) instead
    // of guessing. Only when Dropbox is connected + the working root is resolved.
    if (name === 'search') {
      try {
        const p = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
        const wr = p && p.workingRoot && p.workingRoot();
        if (wr) {
          const parent = wr.replace(/\/[^/]+$/, '') || '/';
          description += `\nYour workspace is the Dropbox folder "${wr}"; its parent shared folder is "${parent}". To search the wider shared area, use scope:"dropbox" with path:"${parent}" (or another absolute folder).`;
        }
      } catch (_) {}
    }
    return { type: 'function', function: { name, description, parameters: tools[name].parameters } };
  });

