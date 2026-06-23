// sandpie /modules/tools.js — Tool schema definitions

const tools = {
  run_python: {
    description: `Execute a Python script from OPFS via Pyodide. Working dir is /files/ (persistent).
REQUIRED: path must point to a script already saved in OPFS (typically under scripts/). Use write_file to create a script first, then call run_python with its path.
ONLY path: + args: are accepted. Scripts must be saved to OPFS before execution.
ASYNC: your code runs ON an already-running event loop, so TOP-LEVEL await works — call coroutines directly (end the script with await main(), which works even inside an if __name__ == '__main__': block). Do NOT use asyncio.run(), loop.run_until_complete(), or asyncio.new_event_loop() — they raise "event loop is already running". Do NOT use time.sleep() (it freezes the whole app) — use await asyncio.sleep(n).
PACKAGES: ~100 prebuilt (numpy, pandas, scipy, matplotlib, bs4, lxml, micropip…) — just import. Others: await micropip.install('name') then import. No compiled C extensions, no subprocess.
HTTP: no sockets, so requests/urllib don't work. Use pyodide.http.pyfetch (async): r = await pyfetch(url); data = await r.json() (also await r.bytes() / await r.string()). Non-CORS hosts: pyfetch('/proxy/host/path').
OUTPUT: write to artifacts/, then call show_artifact({"path":"artifacts/file.html"}).
Examples:
  run      → {path: "scripts/random_numbers.py", args: ["5"]}
  with arg → {path: "scripts/analyze_machine.py", args: ["2026-05-03.csv"]}
  async    → script ends with await main()  (NOT asyncio.run(main()))
  pypi     → script runs: import micropip; await micropip.install('feedparser')
  html out → script writes artifacts/out.html, then show_artifact({"path":"artifacts/out.html"})`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Path under /files/ to a saved Python script (e.g. "scripts/foo.py"). When set, sandpie reads that file and execs it with sys.argv = [path, *args].' },
        args: { type: 'array', items: { type: 'string' }, description: 'CLI args passed via sys.argv when path is used.' },
      },
      required: ['path'],
    },
  },
  write_file: {
  description: `Create a NEW file in OPFS under /files/. If the file already exists it is NOT overwritten — its current content is returned instead, so you can edit_file it in place (don't rewrite it or save a renamed copy). Path is relative to /files/ (e.g. "scripts/analyze.py", "artifacts/chart.html"). Use this to create scripts before running them with run_python.`,
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
        path:   { type: 'string', description: 'OPFS path relative to /files/ (e.g. "scripts/foo.py").' },
        offset: { type: 'integer', description: '1-based line to start at (default 1). Use for paging / tail.' },
        limit:  { type: 'integer', description: 'Max lines to return (default 2000).' },
      },
      required: ['path'],
    },
  },
  list_files: {
    description: `List files and folders in OPFS (/files/) with size + modified time. PREFER THIS over run_python for browsing. Default lists the immediate contents of "path" (like ls). To find files BY NAME, set a glob "pattern" (e.g. "*.py", "**/*.md") and usually recursive:true. To find files BY CONTENT, use search instead.`,
    parameters: {
      type: 'object',
      properties: {
        path:      { type: 'string', description: 'Directory relative to /files/ (default: root).' },
        pattern:   { type: 'string', description: 'Glob to filter names/paths: * (within a segment), ** (across folders), ? (one char). E.g. "**/*.json".' },
        recursive: { type: 'boolean', description: 'Walk subfolders (default false). Set true when using a "**" pattern.' },
      },
      required: [],
    },
  },
  search: {
    description: `Search file CONTENTS by regular expression across OPFS (/files/), returning matches as "path:line: text". PREFER THIS over run_python for grep-style search. Scope with "path" (a subtree) and/or "include" (a name glob like "*.js"). Set files_only:true to get just the list of matching files. Case-insensitive unless ignore_case:false. (To find files by NAME, use list_files.) Skips /_conversations unless "path" points inside it.`,
    parameters: {
      type: 'object',
      properties: {
        pattern:     { type: 'string', description: 'JavaScript regular expression matched per line (e.g. "function\\\\s+\\\\w+", "TODO").' },
        path:        { type: 'string', description: 'Subtree to search, relative to /files/ (default: everything).' },
        include:     { type: 'string', description: 'Only search files whose name/path matches this glob (e.g. "*.py").' },
        files_only:  { type: 'boolean', description: 'Return just matching file paths instead of per-line matches.' },
        ignore_case: { type: 'boolean', description: 'Case-insensitive (default true).' },
      },
      required: ['pattern'],
    },
  },
  search_dropbox: {
    description: `Search for files in the user's Dropbox by keyword using Dropbox search_v2 (full-text content search).
Rules:
- If the result count is >100, you MUST refine the query (more specific terms or a narrower path) before proceeding — do NOT try to read all matches.
- If ≤100 results, list the matching paths; use read_file on whichever files are relevant.
- Dropbox search is token/prefix-based, NOT substring or regex — use whole words for best recall.
- Results are eventually consistent: newly created or edited files may not appear immediately.
- Set filename_only:true to match only file names (faster, less noise); omit it (default false) to also match file content.`,
    parameters: {
      type: 'object',
      properties: {
        query:         { type: 'string',  description: 'Search query. Use whole words; Dropbox does prefix-token matching.' },
        path:          { type: 'string',  description: 'Optional Dropbox folder path to restrict the search (e.g. "/R+D+I/reports"). Defaults to the user\'s working sync folder.' },
        filename_only: { type: 'boolean', description: 'Search file names only (default false = also search file content).' },
      },
      required: ['query'],
    },
  },
  show_artifact: {
    description: `Render a file from OPFS as a live artifact injected directly into the chat.
Use this whenever:
- The user says "show this", "artifact", "add into chat", "inject", "put in the DOM", or similar
- You have written any visual output (HTML page, plot, SVG, chart, dataframe, image) to OPFS
The file must already exist in OPFS — write it first with run_python, then call this.
Supported types: .html (full page, CDN JS works), .svg, .png, .jpg, .gif, .csv, .txt.
Path is OPFS-relative — do NOT include a leading slash (e.g. "artifacts/chart.html").
Default output folder is artifacts/ — use it unless the user specifies a different path.
Typical flow:
  run_python: open('artifacts/chart.html', 'w').write(html)
  show_artifact: { "path": "artifacts/chart.html" }`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'OPFS path to the file (e.g. "artifacts/chart.html"). No leading slash. Default folder: artifacts/.' },
      },
      required: ['path'],
    },
  },
    load_skill: {
      description: `Load a skill's full instructions. Skills are saved playbooks for specific tasks, listed in the "# Skills" section of the system prompt with their name and a "when to use" description.
WHEN TO USE: As soon as the user's request matches a skill's description — judged by intent, not exact wording (e.g. "ship it to prod" matches a deploy skill). Call this BEFORE you start the task, then follow the returned instructions for the rest of the turn.
Pass the skill's name exactly as listed. Returns the skill's instructions (or an error if there's no such skill). Don't reload a skill already marked "(already loaded above)" — its instructions are already in this conversation. If no skill fits the request, don't call this.`,
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
Supports JPEG, PNG, GIF, WEBP. Path is relative to /files/.`,
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to image file relative to /files/ (e.g. "beach.jpg" or "images/photo.png")' },
        },
        required: ['path'],
      },
    },
};
const toolDefs = () => Object.entries(tools)
  .filter(([name]) => {
    return true;
  })
  .map(([name, t]) => ({
    type: 'function',
    function: { name, description: t.description, parameters: t.parameters },
  }));

