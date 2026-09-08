// sandpie /modules/tools.js — Tool schema definitions

const tools = {
  run_python: {
    description: `Execute a Python script from OPFS via Pyodide. The script runs with its OWN folder as the working directory (like \`python script.py\`), so a relative save — doc.save("out.docx"), open("out.csv","w") — lands NEXT TO the script (e.g. projects/<project>/out.docx), not at the /files root. Use a path relative to the script, or an absolute /files/… path. The file is surfaced to the user automatically at the end of the turn.
REQUIRED: path must point to a script already saved in OPFS. Save task scripts in the MOST RELEVANT folder for the job — e.g. projects/<project>/… or the folder whose data the task acts on — so scripts sit next to what they operate on. (Reusable system instruments may live in sandpie/scripts/; the sandbox sandpie/ is otherwise system-only.) Use write_file to create a script first, then call run_python with its path.
ONLY path: + args: are accepted. Scripts must be saved to OPFS before execution.
ASYNC: your code runs ON an already-running event loop, so TOP-LEVEL await works — call coroutines directly (end the script with await main(), which works even inside an if __name__ == '__main__': block). Do NOT use asyncio.run(), loop.run_until_complete(), or asyncio.new_event_loop() — they raise "event loop is already running". Do NOT use time.sleep() (it blocks this run's interpreter and burns the timeout) — use await asyncio.sleep(n).
PACKAGES: ~100 prebuilt (numpy, pandas, scipy, matplotlib, bs4, lxml, micropip…) — just import. Others: await micropip.install('name') then import. No compiled C extensions, no subprocess.
HTTP: no sockets, so requests/urllib don't work. Use pyodide.http.pyfetch (async): r = await pyfetch(url); data = await r.json() (also await r.bytes() / await r.string()). Non-CORS hosts: pyfetch('/proxy/host/path'). pyfetch does NOT raise on HTTP 4xx/5xx — check r.ok / r.status (or r.raise_for_status()) before using the body; a bad status is also auto-logged to stderr so you'll see it even if you forget.
OUTPUT: write to the most relevant folder (e.g. projects/<project>/out.html) — every file you write is shown to the user automatically at the end of the turn.
Examples:
  run      → {path: "projects/<project>/random_numbers.py", args: ["5"]}
  with arg → {path: "projects/<project>/analyze_machine.py", args: ["2026-05-03.csv"]}
  async    → script ends with await main()  (NOT asyncio.run(main()))
  pypi     → script runs: import micropip; await micropip.install('feedparser')
  html out → script writes projects/<project>/out.html (shown to the user automatically at turn end)`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Path under /files/ to a saved Python script (e.g. "projects/<project>/foo.py" — the most relevant folder for the task). When set, sandpie reads that file and execs it with sys.argv = [path, *args].' },
        args: { type: 'array', items: { type: 'string' }, description: 'CLI args passed via sys.argv when path is used.' },
        timeout: { type: 'number', description: 'Max seconds the script may run before it is killed (default 120, max 600). On timeout the run is aborted and its interpreter discarded, so it can never hang the conversation — raise this only for genuinely long computations.' },
      },
      required: ['path'],
    },
  },
  write_file: {
  description: `Write a file in OPFS under /files/. By default it only CREATES: if the file already exists nothing is written and its current state is returned. Then pick the right follow-up: for a small or targeted change, edit_file it in place; to REPLACE the content wholesale (wrong or corrupted beyond editing), call write_file again with overwrite:true. NEVER save a renamed copy (foo_v2.html) to work around an existing file. Path is relative to /files/ — put files in the MOST RELEVANT folder for the task (e.g. "projects/<project>/analyze.py", "projects/<project>/chart.html"), never in the sandbox (sandpie/ is system-only). Use this to create scripts before running them with run_python.

For large or multi-line content, you MAY skip JSON and emit the body as a raw block in your reply instead (no escaping of newlines/quotes needed); append |overwrite inside the header to replace an existing file:
<|write_file:PATH|>
<file content, verbatim>
<|end_write_file|>`,
  parameters: {
    type: 'object',
    properties: {
      path:    { type: 'string', description: 'OPFS path relative to /files/' },
      content: { type: 'string', description: 'Full file content' },
      overwrite: { type: 'boolean', description: 'Set true to replace an existing file with `content` — only once you know what it holds (from a previous write_file refusal or a read_file). Default false: existing files are never touched.' },
    },
    required: ['path', 'content'],
  },
},
edit_file: {
  description: `Replace a string in an existing OPFS file — the PREFERRED way to change a file. Matching is forgiving: exact first, then ignoring line-ending and trailing-whitespace differences, so a small whitespace drift won't fail. old_str must still resolve to ONE place (otherwise it returns the match count + line numbers, or the closest lines, so you can retry precisely). Read the file first to copy exact content (do NOT include read_file's line-number prefixes in old_str). To FIX a script that errored, edit_file the offending lines — NEVER rewrite the whole file or save a renamed copy.

For multi-line edits, you MAY skip JSON and emit a raw SEARCH/REPLACE block in your reply instead (no escaping needed). One block per edit; emit multiple for multiple edits:
<|edit_file:PATH|>
<<<<<<< SEARCH
<exact old text>
=======
<new text>
>>>>>>> REPLACE
<|end_edit_file|>`,
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
  delete_file: {
    description: `Delete a file (or directory) from OPFS under /files/. Use it to clean up after yourself — scratch scripts, failed drafts, superseded intermediates — and whenever the user asks for a file to be removed. It also unblocks the "start over" case: if a file is corrupted beyond editing you may either delete_file it and write_file fresh, or simply write_file with overwrite:true. NEVER work around an unwanted file by saving a renamed copy. The deletion propagates to the user's cloud sync, so it removes the file everywhere, not just locally — it is immediate and unrecoverable. Delete only files you created in this conversation, or files the user explicitly named; if you are unsure, ask first. Refuses anything under sandpie/ (system data: memories, skills, conversations).`,
    parameters: {
      type: 'object',
      properties: {
        path:      { type: 'string',  description: 'OPFS path relative to /files/ of the file or directory to delete.' },
        recursive: { type: 'boolean', description: 'Set true to delete a directory AND everything inside it. Default false: non-empty directories are refused.' },
      },
      required: ['path'],
    },
  },
  read_file: {
    description: `Read a UTF-8 text file from OPFS (/files/). PREFER THIS over run_python for reading — it's instant and can't crash the runtime. Output is line-numbered as "<n>\\t<line>"; the numbers are for reference only — never include them when calling write_file/edit_file. Reports total lines + byte size. For large files or head/tail, page with offset (1-based start line) + limit. Re-reading a file that has NOT changed since you last saw it returns a short "unchanged" note instead of the content — the copy already in your context is authoritative; work from it rather than re-reading. For images use load_image instead.`,
    parameters: {
      type: 'object',
      properties: {
        path:   { type: 'string', description: 'OPFS path relative to /files/ (e.g. "sandpie/scripts/foo.py").' },
        offset: { type: 'integer', description: '1-based line to start at (default 1). Use for paging / tail.' },
        limit:  { type: 'integer', description: 'Max lines to return (default 2000).' },
        force:  { type: 'boolean', description: 'Re-emit the content even if unchanged since your last read of this exact range. Use only when the copy in your context is unusable (e.g. after a context summarization).' },
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
  web_search: {
    description: `Search the WEB and get back a ranked list of results (title, URL, snippet). Use whenever the user asks to search the web / look something up online / find current or recent information, or when you need facts beyond your knowledge or a source to cite.
Give plain keywords (not a regex). Robust by design: results come from a real search backend (OpenRouter web search / Exa) when available, and it transparently falls back to scraping several public engines (DuckDuckGo, Brave, Bing, Mojeek) otherwise — the backend actually used is reported.
This searches the public web — it is NOT for the user's files (use search / list_files for those). To read a result's full page text, follow up with read_url on its URL.`,
    parameters: {
      type: 'object',
      properties: {
        query:       { type: 'string', description: 'Plain-keyword search query, e.g. "python asyncio tutorial" or "Reixach compressor datasheet".' },
        num_results: { type: 'integer', description: 'Max results to return (default 8, max 20).' },
      },
      required: ['query'],
    },
  },
  read_url: {
    description: `Fetch a web page and return its main readable text (nav/scripts/ads/boilerplate stripped) plus the page title. Use it to READ a result from web_search, or any URL the user gives you, when you need the actual content rather than just the snippet.
Returns up to max_chars characters and reports the total length; if the page is longer than you got, call again with a larger max_chars.`,
    parameters: {
      type: 'object',
      properties: {
        url:       { type: 'string', description: 'Full URL to fetch, e.g. "https://example.com/article".' },
        max_chars: { type: 'integer', description: 'Max characters of text to return (default 8000, max 40000).' },
      },
      required: ['url'],
    },
  },
  // show_artifact REMOVED (2026-08-28): every file a turn touches is surfaced to
  // the user automatically at turn end (worker 'files_touched' event → one card
  // per file, .html/images expanded, the rest collapsed clickable cards), and
  // deliverable localization triggers there too. The worker keeps a transitional
  // shim for stale sessions that still call it.
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
HOW LONG YOU CAN SEE IT: only for the turn in which you load it. Afterwards the image is replaced in the conversation by a short note naming its path, so it no longer takes up context. If a LATER turn needs you to check something in that image again — a detail you did not describe, or a new question about it — call load_image on the same path again. Do not answer from memory of an image you loaded in an earlier turn, and do not claim you can still see it.
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
      description: `Copy a file INTO the user's editable workspace so you can modify it. Two uses: (1) FORK a workspace file — e.g. a shared package under "sandpie/shared-installed/" — into a standalone copy (shared-installed files are now editable in place via editor write-back, but forking is still handy for a detached copy): pass its workspace path as src (no leading slash). (2) IMPORT a file from ELSEWHERE in the user's Dropbox that read_file/run_python/load_image can't reach: pass an absolute Dropbox path like "/R+D+I/reports/q1.pdf" (as returned by search). The source is never modified in either case. Returns the new editable workspace-relative path; then use read_file / edit_file / run_python on it.`,
      parameters: {
        type: 'object',
        properties: {
          src:  { type: 'string', description: 'Either a workspace path to fork (e.g. "sandpie/shared-installed/impagados/dashboard.html") or an absolute Dropbox path to import (e.g. "/R+D+I/reports/q1.pdf").' },
          dest: { type: 'string', description: 'Optional destination within the workspace (default: the source filename at the workspace root — visible; never the sandbox), e.g. "imported/q1.pdf".' },
        },
        required: ['src'],
      },
    },
    share: {
      description: `Share a file or folder in OPFS with a team department.
The share is performed by the page (Dropbox), so this tool returns once it is published.
- type "team" (the only type): recipients are TEAM/DEPARTMENT FOLDER names (e.g. ["IT"]) — the item is copied into IA/<department>/<name>/; only that department can read it (Dropbox folder membership is the boundary). A SKILL.md in the folder makes it a shared skill.
path is OPFS-relative (e.g. "projects/<project>/report.html").`,
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'OPFS path of the file or folder to share (e.g. "projects/<project>/x.html").' },
          type: { type: 'string', enum: ['team'], description: '"team" = publish to a department folder.' },
          recipients: { type: 'array', items: { type: 'string' }, description: 'Department folder name(s), e.g. ["IT"].' },
        },
        required: ['path', 'type', 'recipients'],
      },
    },
    share: {
      description: `Share a file or folder in OPFS with the team or with specific people (1:1).
The share is performed by the page (Dropbox), so this tool returns once it is published.
- type "team": recipients are TEAM/DEPARTMENT FOLDER names (e.g. ["R+D+I"]) — the item is copied into that department's shared hub; only that department can read it (Dropbox folder membership is the boundary).
- type "p2p": recipients are EMAIL addresses — a folder is shared live in place, a single file is wrapped into an outbox folder, and each recipient is invited as a folder member.
permissions: "viewer" (default, read-only) or "editor" (may write back); "read"/"write" aliases accepted. Permissions apply to p2p invites; team shares are bounded by the department folder membership.
path is OPFS-relative (e.g. "projects/<project>/report.html").`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'OPFS path of the file or folder to share (e.g. "projects/<project>/x.html").' },
        type: { type: 'string', enum: ['team', 'p2p'], description: '"team" = publish to department hub(s); "p2p" = share 1:1 with email recipients.' },
        recipients: { type: 'array', items: { type: 'string' }, description: 'team: department folder names (e.g. ["R+D+I"]); p2p: recipient email addresses.' },
        pinFile: { type: 'string', description: 'Which file in the folder to set as the main/pinned file (e.g. "Impagats.html"). Only used when sharing a folder. Defaults to SKILL.md if present, else index.html, else the first file.' },
      },
      required: ['path', 'type', 'recipients'],
    },
  },
  html_console: {
    description: `Read the browser console output of an HTML artifact that is shown in the conversation, so you can see console.log/warn/error output, uncaught errors, and unhandled promise rejections from the artifact's own JavaScript.
WHEN TO USE: after showing an HTML artifact, when the user reports something looks broken (blank areas, missing elements, wrong layout) or you want to verify the page's JS ran without errors. The console is captured from load time (the capture script is injected before the artifact's own scripts), so load-time errors are included.
WHEN NOT TO USE: for non-HTML artifacts (images, PDFs, office docs have no console). If the artifact is not currently open in the conversation it is rendered automatically first — the console is read from the live preview frame.
path: optional — omit to read the most recently shown artifact, or pass the exact path (e.g. "projects/<project>/report.html").`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Optional OPFS path of the artifact (e.g. "projects/<project>/report.html"). Omit to target the most recently shown artifact.' },
      },
      required: [],
    },
  },
  screenshot: {
    description: `Render an artifact and SEE it as an image — the screenshot comes back as part of this tool call, visible to you on the next step, no further action needed.
WHEN TO USE: after writing or editing an HTML artifact, to check what it actually looks like before telling the user it's done. Layout bugs — overlapping elements, clipped text, broken alignment, a chart that rendered empty, invisible low-contrast text — do NOT throw errors, so html_console cannot find them and reading your own source cannot either. Looking is the only way.
Also use it to check responsive behaviour (pass width), and to verify a fix really landed rather than assuming it did.
WHEN NOT TO USE: on files that are not HTML or images (a .docx/.pdf/.csv cannot be rasterized). Don't screenshot the same unchanged file twice.
The artifact does NOT need to be shown in the conversation first: by default it is rendered offscreen at exact dimensions, which neither disturbs the user's view nor depends on what is currently on screen.
The result lists FIDELITY CAVEATS when parts of the page could not be captured faithfully (e.g. cross-origin images, backdrop-filter, shadow DOM). Trust the rest of the image; treat flagged areas as unverified.
Typical flow:
  run_python: write projects/<project>/report.html
  screenshot: { "path": "projects/<project>/report.html" }
  -> see a clipped header -> edit_file to fix -> screenshot again to confirm`,
    parameters: {
      type: 'object',
      properties: {
        path:      { type: 'string', description: 'OPFS path of the artifact to capture (e.g. "projects/<project>/report.html"). HTML or an image file. No leading slash.' },
        width:     { type: 'integer', description: 'Viewport width in CSS pixels (default 1280). Use e.g. 375 to check the mobile layout. If the content turns out to be wider than this, the capture is automatically re-rendered wide enough to fit rather than handing you a clipped image — the result says so when that happens.' },
        exact_width: { type: 'boolean', description: 'Disable the auto-fit above and capture at exactly "width", clipped, as a real viewport of that size would show it. Use when the width itself is what you are testing (e.g. proving a page overflows at 375px).' },
        height:    { type: 'integer', description: 'Viewport height in CSS pixels (default 800). Ignored when full_page is true.' },
        full_page: { type: 'boolean', description: 'Capture the entire scrollable height instead of just the viewport (default false).' },
        wait_ms:   { type: 'integer', description: 'Extra settle time in ms before capturing, for pages that render asynchronously (default 400, max 10000).' },
        live:      { type: 'boolean', description: 'Capture the artifact frame already shown in the conversation, preserving its current interacted state, instead of rendering a fresh copy. Falls back to a fresh render if it is not on screen.' },
      },
      required: ['path'],
    },
  },
  write_todos: {
      description: `Create and manage a structured task list for the current session. This helps you track progress, organize complex work, and demonstrate to the user that you understand the scope.
Use it for: complex multi-step tasks (3+ distinct steps); non-trivial work that needs planning; when the user gives you multiple tasks or explicitly asks for a todo list; when you start a task (mark it in_progress) and when you finish one (mark it completed and add any follow-ups).
Do NOT use it for: a single straightforward task; trivial work; anything doable in under 3 steps; purely conversational requests — it only adds overhead there.
The harness holds the list as a FLAT set of tasks with IDs. Two call forms:
1. DELTA (preferred for status changes): {"todos":[{"id":"3","status":"completed"}]} — items with an "id" and NO "content" flip statuses only; nothing is added, dropped, or re-typed. This is the cheapest call: use it every time you finish or start a task.
2. FULL LIST: {"todos":[{"content":…,"status":…},…]} — for the initial plan or restructuring. It is reconciled to the existing checklist (matched by id, then content — reworded content still matches, so resending finished tasks can NOT duplicate them; open tasks you omit are dropped and reported).
Batch transitions: when you finish a task, mark it completed AND (if you know the next step differs from list order) start the next one in the SAME call. If a call leaves nothing in_progress, the harness AUTO-STARTS the first unblocked pending task and tells you which — you never need a second call just to start work.
When every task is completed the checklist is DONE: do not call write_todos again — deliver your answer with respond().
Each task MAY carry "est": your honest estimate of how many TOOL CALLS it will take (not time). The user sees it as live progress ("14/~20" plus a time projection from the run's own pace), so estimate what you actually expect — including reads and checks — and skip it when you genuinely can't tell.
At most ONE task may be in_progress at a time. The checklist and your scratchpad are injected into your context every round, so you always see your plan and working notes without re-reading.
PLAN-FIRST GATE: while NO task is in_progress, the harness offers only write_todos, scratch, and respond — every other tool (python, shell, files, search, …) is HIDDEN, not missing. Creating a plan and starting a task (in_progress) unlocks the full toolset immediately. Never tell the user a tool is unavailable or ask them to enable it: plan, start the task, then call the tool.
LANGUAGE: author every "content"/"activeForm"/"reason" in ENGLISH — the system automatically translates the checklist into the user's language for display. Do NOT write them in the user's language yourself; you generate correct text only in English.`,
      parameters: {
        type: 'object',
        properties: {
          todos: {
            type: 'array',
            description: 'DELTA form: items {"id","status"} with no content flip statuses only (cheapest — use for every finish/start). FULL-LIST form: items with "content" are reconciled to the existing checklist (reworded content still matches; open tasks you omit are dropped and reported). At most ONE task may be in_progress.',
            items: {
              type: 'object',
              properties: {
                id:        { type: 'string', description: 'Existing task id (from the checklist). With "status" and NO "content" this is a delta: flips that task\'s status only.' },
                content:   { type: 'string', description: 'The task, as a brief imperative title (e.g. \'Run tests\'), in English (the system localizes it for display). Omit when sending a delta ({id,status}).' },
                status:    { type: 'string', enum: ['pending', 'in_progress', 'completed', 'blocked'], description: 'Task state. At most ONE may be in_progress.' },
                blockedBy: { type: 'array', items: { type: 'string' }, description: 'Mark tasks (from this same list) that must complete before this one can start.' },
                activeForm:{ type: 'string', description: 'The present continuous form shown while the task is in progress (e.g. \'Running tests\').' },
                est:       { type: 'integer', description: 'Your honest estimate of how many TOOL CALLS this task will take (not time). Shown to the user as live progress (\'14/~20\') — skip it when you have no idea rather than guessing wildly.' },
                reason:    { type: 'string', description: 'For \'blocked\': why the task is stalled (shown in the checklist).' },
              },
              required: [],
            },
          },
        },
        required: ['todos'],
      },
    },
    scratch: {
      description: `Set your working notes for this conversation — plan hypotheses, blockers, next steps, state that must survive compaction. Overwrites previous content. Re-injected into your context every round (ephemeral, not in messages) so you always see your working state without re-reading. NOT shown to the user.
Use it for: recording what you tried and what happened, tracking blockers, noting next steps, keeping state across compaction. Distinct from remember() (permanent, cross-conversation) — scratch is session-scoped working memory.
Cap ~4KB. The result echoes the byte count stored.`,
      parameters: {
        type: 'object',
        properties: {
          text: { type: 'string', description: 'The full new content of the scratchpad (overwrites previous).' },
        },
        required: ['text', 'language'],
      },
    },
        spawn_subagent: {
      description: `Delegate a well-scoped subtask to a fresh subagent that runs its OWN short agent loop in an ISOLATED context (it does NOT see this conversation) and returns only its final result. Use this to keep your own context clean on a big task: hand off focused exploration, research, verification, or a self-contained piece of work, and get back a bounded summary you can act on.
HOW: pick an agent by name — each is defined in sandpie/agents/<name>.md, whose file sets that subagent's system prompt, which tools it may use, its model, and its round budget. Then write a SELF-CONTAINED prompt: state the goal and include EVERY path, id, and constraint it needs, because it starts from a blank context and cannot ask you follow-up questions. It works independently and hands back a distilled result.
WHEN: a subtask is bounded and describable in one brief — "audit this claim against the code", "find where X is implemented and how it's wired", "research Y and report". Skip it for trivial one-step things you can just do yourself. A subagent cannot spawn further subagents.`,
      parameters: {
        type: 'object',
        properties: {
          agent:  { type: 'string', description: 'Name of the agent to run, matching a file sandpie/agents/<name>.md (e.g. "adversarial").' },
          prompt: { type: 'string', description: 'The self-contained task brief. Include all context (paths, ids, goal, constraints) — the subagent sees nothing else.' },
        },
        required: ['agent', 'prompt'],
      },
    },
    shell: {
      description: `Run a command on the REMOTE relay host and get back its stdout, stderr, and exit code.

⚠️ THE RELAY IS A SEPARATE MACHINE WITH ITS OWN, DIFFERENT FILESYSTEM — it is NOT your workspace. Your workspace is /files: the persistent store that write_file, edit_file, read_file, delete_file, list_files, run_python and show_artifact all act on. A file you create in your workspace does NOT exist on the relay, and the relay's paths (/tmp, /root, ~, /home, and any projects/… there) are NOT your workspace files. The two never share a path, so shell can't see your files and you can't reach the relay's files with the file tools.

Do NOT use shell for workspace file operations — creating, reading, editing, listing, verifying, moving, or deleting files under /files. Use the file tools instead: list_files to see what exists, read_file / show_artifact to read, write_file / edit_file to change, delete_file to remove, run_python to process. In particular, after write_file or run_python, VERIFY with list_files / read_file — never with \`ls\`/\`cat\`/\`test -f\` in shell, which run on the other machine and will report your files missing.

Use shell ONLY when the task is genuinely about the relay machine itself: run a program or build that lives there ("cargo test"), reach another host ("ssh myserver 'systemctl restart app'"), or move data between the relay and elsewhere ("scp myserver:/var/log/x.log /tmp/"). ssh/scp use the relay host's own ~/.ssh — no key setup here.
WRITE A FILE ON THE RELAY (not your workspace) WITH ZERO ESCAPING: pipe content through stdin — {"command":"cat > /path/on/relay.rs", "stdin":"<the entire file content>"} — quotes, $, backticks, (parens), newlines survive verbatim; read it back with {"command":"cat /path/on/relay.rs"}. Never build cat<<EOF / sed one-liners for file content.
LONG JOBS (>~120s: full builds, kernel boots): a call is killed at ~120s, so launch detached and poll a log — {"command":"nohup cargo build --release >/tmp/b.log 2>&1 & echo $!"} then {"command":"tail -40 /tmp/b.log"}.
Requires the relay running on that machine; on a connection error, tell the user to start it and do NOT retry in a loop.`,
      parameters: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'The command / script to run (bash). May contain &&, |, $, quotes, multiple lines.' },
          stdin:   { type: 'string', description: 'Optional data piped to the command\'s stdin (use with "cat > file" to write a file verbatim — no escaping).' },
          cwd:     { type: 'string', description: 'Optional working directory to run in.' },
          timeout: { type: 'number', description: 'Max seconds before the command is killed (default 30, max 300).' },
        },
        required: ['command'],
      },
    },
    remember: {
      description: `Save something you've learned that should persist across conversations. Facts for the project you're CURRENTLY working in are auto-injected in full every turn; the rest appear as a one-line index you can expand with recall(). So saving is usually enough — but if you need a fact that's only in the index, call recall().
WRITE ONE AS SOON AS you learn any of these (capture it the moment it's clear — don't wait for the task to end):
  - a stable user preference or fact about the user  → type "user"
  - a correction or instruction on HOW to work, with the reason why  → type "feedback"
  - durable project context, a constraint, or a decision that will matter later  → type "project"
  - a pointer to an external resource, or a gotcha worth not rediscovering  → type "reference"
TWO GATES, BOTH REQUIRED (to keep memory signal-dense):
  (1) durable — true beyond this conversation, and
  (2) non-derivable — not already recoverable from the code, files, git history, or a loaded skill.
Skip task-local details, anything the repo/files already record, and low-confidence guesses.
If a related fact may already exist, reuse its exact name to UPDATE it instead of creating a near-duplicate. Keep the body to the durable essence (1-3 sentences); include the WHY for feedback/project.
LINK related memories: reference other facts inside the body as [[their-name]] (the name slug, not the description). Link liberally — a [[name]] that doesn't exist yet marks something worth writing later, not an error.`,
      parameters: {
        type: 'object',
        properties: {
          name:        { type: 'string', description: 'Short kebab-case identifier / title (e.g. "user-prefers-terse"). Reuse an existing name to update that fact.' },
          description: { type: 'string', description: 'One-line summary of the fact — the header shown for it in context.' },
          type:        { type: 'string', enum: ['user', 'feedback', 'project', 'reference'], description: 'user = who they are/preferences; feedback = how to work + why; project = ongoing context; reference = pointer to a resource.' },
          body:        { type: 'string', description: 'The fact itself, in full. For feedback/project include the reasoning ("why") so it stays actionable.' },
          links:       { type: 'array', items: { type: 'string' }, description: 'Optional names of related memories to cross-link.' },
          project:     { type: 'string', description: 'Optional: the project/topic this fact belongs to (e.g. "riscv-vm", "sandpie"). Omit to let it be derived from the files you touched. Facts sharing a project are grouped and recalled together.' },
          supersedes:  { type: 'array', items: { type: 'string' }, description: 'Optional names of older memories this one REPLACES (superseded snapshots, outdated status). They are archived (recoverable), not shown anymore. Use when you are updating a moving fact rather than adding a distinct one.' },
        },
        required: ['name', 'body'],
      },
    },

    recall: {
      description: `Load memories that aren't currently shown in full. Your context shows the CURRENT project's memories in full plus a one-line index of the rest; call recall to pull any indexed fact (or a whole other project) into view by keyword or name. Use it when the task touches something outside your current project — a past decision, a gotcha, another project's setup.`,
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Keywords or a memory name to search for across all saved memories.' },
          limit: { type: 'number', description: 'Max memories to return (default 3, max 6).' },
        },
        required: ['query'],
      },
    },

    ask: {
      description: `Ask the user to choose between concrete options to resolve genuine ambiguity — a multiple-choice clarification the user answers with one click.

USE THIS when the user's prompt has an INTERPRETABLE AMBIGUITY: a fork where guessing wrong would waste significant work or produce a result they did not want, and the conversation context does not already make the intent clear. Ask EARLY, before doing the work, not after.

TRIGGERS (ask when any of these is genuinely ambiguous):
- Scope: "make a report on the ACS200" when several ACS200 variants/sites exist.
- Target/format: "send it to the team" when the recipient or channel is unclear.
- Direction: "reduce the cost" when several diverging cost levers exist.
- Constraints: a deadline, priority, budget, or language that changes the approach.
- Conflicting requirements where you must settle on one reading.

DO NOT USE when:
- The choice is trivial and you can safely assume a sensible default (pick it and state it).
- Prior context or earlier turns already disambiguate the intent.
- The user can simply answer in their next message without wasted work.
- It is a matter of taste you can decide yourself.

ALWAYS BATCH: if several ambiguities exist, ask them ALL in ONE call (multiple questions), never one question at a time. Keep to at most 4 questions per call.
Each question must be phrased as a clear choice with 2-5 mutually exclusive, non-overlapping options, and you MUST set a default (the option you would pick if the user skips) so a single click resolves it. Prefer short, concrete option labels.
LANGUAGE: author the questions and options in ENGLISH — the system automatically translates them into the user's language for display. Do NOT write them in the user's language yourself; you generate correct text only in English.`,
      parameters: {
        type: 'object',
        properties: {
          questions: {
            type: 'array',
            minItems: 1,
            maxItems: 4,
            description: 'The clarification questions to ask, batched together. All are shown at once.',
            items: {
              type: 'object',
              properties: {
                question: { type: 'string', description: 'The clarification, phrased as a choice. Concise and specific, in English (the system localizes it for display).' },
                options: { type: 'array', minItems: 2, maxItems: 5, items: { type: 'string' }, description: '2-5 mutually exclusive, concrete options. No overlap. In English (the system localizes them for display).' },
                allow_freeform: { type: 'boolean', description: 'If true, ALSO offer a free-text "Other" input so the user can type a custom answer (default false).' },
                default: { type: 'string', description: 'The option that is pre-selected if the user skips. Must exactly match one of options.' },
              },
              required: ['question', 'options'],
            },
          },
        },
        required: ['questions'],
      },
    },

    walios: {
      description: `Run a shell script inside walios — the WALI wasm-OS (a real Linux userland: busybox ash + coreutils, python3, ssh, make — compiled to native wasm) hosted at /walios/. Headless: no terminal UI; you get stdout/stderr plus the exit code.
Pass the script in the "script" argument (a normal string; multi-line is fine). For long or heavily-quoted scripts where JSON escaping is error-prone, you MAY instead OMIT "script" and put it in the raw blob form in your reply:
<|walios|>
echo hello
uname -a
<|end_walios|>
Everything between the sentinels IS the script — no escaping needed. Either channel works; the blob form is just an escaping-free alternative. Optional per-call timeout on the blob opener: <|walios:90|> (seconds; default 120, max 300).
ENVIRONMENT: busybox ash (full coreutils), persistent home at /root (files written there survive across calls), real TCP/UDP via the WISP relay (wget, nc, ssh, ping), python3 (stdlib lazy-loads on first use).
⚠️ /root IS the app's OPFS workspace root (same namespace the file tools see) — rm there deletes REAL files. Use it deliberately.
COMMANDS: awk basename cat chmod chown cksum clear cmp comm cp curl cut date df diff dirname du echo env expand expr find flock fold getopt grep head hexdump hostname id install kill less ln ls mkdir mkfifo mktemp mv nc nl nslookup od paste ping printf pwd readlink realpath rev rm rmdir sed sh sleep soffice sort split stat tac tail telnet test timeout touch tr tree uname uniq vi wc wget which xargs yes. There is NO tar, gzip, zip, base64, md5sum/sha256sum or jq — do that work in run_python instead. seq exists as an applet but SEGFAULTS (exit 139) - use awk or a while loop instead. curl works over http:// and https://, but its -w/--write-out prints NOTHING in this build - use -o FILE plus wc -c for the size, and -D FILE or -I for the status line.
GIT: git 2.45.3 is installed; clone/fetch/push over HTTPS work (real TLS through the relay). Example: git clone https://github.com/owner/repo /root/repo — for a private repo put the token in the URL. Clones land in /root, which IS the user's workspace, so say where you put it and clean up scratch clones.
OFFICE→PDF: soffice --headless --convert-to pdf [--outdir DIR] FILE...  converts docx/doc/odt/rtf/txt, xlsx/xls/ods/csv, pptx/ppt/odp and odg under /root to PDF with the app's in-browser LibreOffice (same engine and fonts as the file viewer). PDF is the ONLY target; files and --outdir must be under /root. Without --outdir the PDF is written to the CURRENT directory (real soffice behaviour), which for this tool is /root. First conversion boots the engine (30-90s); the run's timeout is paused while it does.
USE FOR: quick POSIX shell computation, text processing (grep/sed/awk/sort/uniq/cut/wc over files in /root), and sandboxed shell logic — including the shelling-out that run_python cannot do, since this platform has no fork. Its python3 DOES have numpy, pandas, matplotlib, Pillow, lxml, python-docx, openpyxl and more — but prefer run_python for Python work (it keeps a warm interpreter, so imports and globals persist between calls). NOT the shell tool: that runs on the user's real machine, walios is an isolated in-browser OS.`,
      parameters: {
        type: 'object',
        properties: {
          script: { type: 'string', description: 'The shell script to run (busybox ash -c). Multi-line is fine. Omit ONLY when you are supplying the script via the <|walios|>…<|end_walios|> blob form in your reply instead.' },
          timeout: { type: 'number', description: 'Max seconds the run may take before it is terminated (default 120, max 300). Can also be set via the <|walios:90|> blob opener.' },
        },
        required: ['script'],
      },
    },

    respond: {
      description: `Deliver your FINAL, user-facing answer. Whatever you pass as "text" is shown to the user as your reply, rendered as Markdown.
WHY THIS EXISTS: the chat must contain ONLY your finished answer — never your thinking, planning, or scratch narration, and never a mix of languages. Keep reasoning in your reasoning channel (or a scratch file); when you are ready to answer, put ONLY the finished reply here.
LANGUAGE: "language" is REQUIRED — set it to this reply's language code (e.g. "ca", "es", "en"). Author "text" per the system language directive: directly in the reply language when the directive says you author it yourself (a language you generate fluently), in ENGLISH when the directive says the system translates delivery (a language you don't generate reliably). Never write a language the directive tells you not to author.
WHEN: your FINAL action — every turn must END on a respond(), so the last thing the user sees is your conclusion. Finish all work and side effects FIRST (files, remember, final write_todos), THEN respond() once at the end. You MAY respond and then keep working, but you must respond() AGAIN afterward so the turn still ends on a respond() reflecting the latest work. If the user asked for replies in multiple languages, emit those respond() calls together (each = one language) as that closing step. Do NOT emit any other prose in the same turn; this tool's argument is your entire visible reply.`,
      parameters: {
        type: 'object',
        properties: {
          text: { type: 'string', description: 'Your complete user-facing reply (Markdown supported), authored per the system language directive — English when an author-in-English directive is active (the system translates delivery), otherwise the reply language itself.' },
          language: { type: 'string', description: 'REQUIRED. The language code for this reply (e.g. "ca", "es", "en").' },
        },
        required: ['text', 'language'],
      },
    },

};
//// Tool enable/disable + description editing were REMOVED 2026-08-07 (product
// decision): every tool is always ON with its shipped description — isEnabled()
// returns true and description() returns the default. The storage below is inert
// legacy (kept for API compatibility); toolDefs() no longer reads it.
const TOOLS_DISABLED_KEY = 'sandpie-tools-disabled';   // JSON array of disabled names
const TOOLS_DESC_KEY     = 'sandpie-tools-desc';       // JSON map { name: customDescription }
const TOOLS_ENABLED_KEY  = 'sandpie-tools-enabled';    // JSON array of explicitly-ON names (for default-off tools)
// Tools that stay OFF until the user explicitly turns them on. They NEVER auto-enable:
// isEnabled returns false unless the name is in TOOLS_ENABLED_KEY (set only by setEnabled).
const TOOLS_DEFAULT_OFF  = new Set(['shell']);   // relay-backed shell; off until the user opts in
const SHELL_RELAY_URL_KEY = 'sandpie-shell-relay-url';
const SHELL_RELAY_DEFAULT = 'http://localhost:8765';
function shellRelayUrl() {
  try { const v = (localStorage.getItem(SHELL_RELAY_URL_KEY) || '').trim(); return v || SHELL_RELAY_DEFAULT; }
  catch (_) { return SHELL_RELAY_DEFAULT; }
}
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
  // remember/recall are only offered when the memory feature is enabled (Settings → Memory).
  if (name === 'remember' || name === 'recall') {
    try { return !!(window.SandpieMemory && SandpieMemory.isEnabled()); }
    catch (_) { return false; }
  }
  return true;
}


// ---------------------------------------------------------------------------
// run_python has TWO backends and they do not have the same rules. The shipped
// description above is Pyodide's, and it is FALSE for walios on the two points a
// model acts on most: it says there are no sockets and no compiled C extensions,
// when walios has real sockets + TLS and its numpy/pandas ARE C extensions. Handing
// the model the wrong backend's rules is a measured cost -- in the A/B logs the
// model burned turns probing for requests / urllib / a system python.
//
// Built by replacement, and then CHECKED. An identical construction in the A/B
// harness silently produced a byte-identical copy for months (the anchors did not
// match), so if any part of this fails to apply we keep the base text rather than
// ship something subtly wrong.
const RUN_PYTHON_WALIOS = (() => {
  const base = tools.run_python.description;
  const PACKAGES = "PACKAGES: numpy, pandas, matplotlib, Pillow, lxml, python-docx, openpyxl, python-pptx, reportlab, pypdf, bs4, xlsxwriter, requests, sqlite3 and more are BUILT IN as real compiled C extensions — just import. Others: await micropip.install('name') installs pure-Python wheels from PyPI with their dependencies; a package needing compiled C code cannot be installed at runtime and micropip tells you so, naming an installed alternative where one exists.";
  const HTTP = "HTTP: real sockets, TLS and CA certificates are present, so requests and urllib work normally (import requests; r = requests.get(url); r.json()). pyodide.http.pyfetch also works (async) and is cheaper for a simple GET: r = await pyfetch(url); data = await r.json(). pyfetch does NOT raise on HTTP 4xx/5xx — check r.ok / r.status before using the body.";
  // Measured through the real warm-REPL path in a browser: asyncio.run() 4.2s on the
  // first call then 69ms, run_until_complete 4ms, top-level await 16ms. Pyodide's
  // "they raise event loop is already running" is simply untrue here. subprocess and
  // os.popen, by contrast, HANG to the timeout because fork cannot start a child.
  const ASYNC_WALIOS = "ASYNC: top-level await works, and so does the normal asyncio API — asyncio.run(main()), loop.run_until_complete() and asyncio.new_event_loop() all work here (unlike the Pyodide backend). Use whichever reads best. Do NOT use time.sleep() — it blocks this run's interpreter and burns the timeout; use await asyncio.sleep(n).";
  const SHELL_WALIOS = "SHELL: there is no subprocess. subprocess.run(), subprocess.Popen and os.popen() raise OSError [Errno 38] Function not implemented immediately (this platform cannot fork), and os.system() returns -1. Do not shell out from Python — use the walios tool for shell work, or do the job in Python directly.\nOFFICE→PDF: never subprocess soffice; instead `import soffice; pdf = soffice.convert('/root/report.docx')` (or outdir='/root/out') converts docx/doc/odt/rtf/txt, xlsx/xls/ods/csv, pptx/ppt/odp, odg to PDF with the app's in-browser LibreOffice and returns the PDF path. PDF is the only target; the source and outdir must be under /root.";
  let out = base
    .replace('Execute a Python script from OPFS via Pyodide.',
             'Execute a Python script from OPFS via walios (wasm CPython 3.14 on a real Linux userland).')
    .replace(/^PACKAGES:.*$/m, PACKAGES)
    .replace(/^HTTP:.*$/m, HTTP)
    .replace(/^ASYNC:.*$/m, ASYNC_WALIOS + '\n' + SHELL_WALIOS);
  const applied = out !== base
    && out.indexOf(PACKAGES) !== -1
    && out.indexOf(HTTP) !== -1
    && out.indexOf(ASYNC_WALIOS) !== -1
    && out.indexOf(SHELL_WALIOS) !== -1
    && out.indexOf('no sockets') === -1
    && out.indexOf('No compiled C extensions') === -1
    && out.indexOf('event loop is already running') === -1;
  if (!applied) {
    try { console.warn('[tools] walios run_python description did NOT build; using the Pyodide text'); } catch (_) {}
    return base;
  }
  return out;
})();

// walios is a real Linux userland: every blocking syscall suspends through JSPI, so
// without it the guest does not degrade, it TRAPS — measured, a bare `echo ok` exits 139
// and python cannot start at all. JSPI is Chromium-only, so on Safari/Firefox a user with
// the walios preference set would get a dead Python tool. Fall back to Pyodide instead.
//
// THE SAME predicate must decide the tool DESCRIPTION and the tool's actual BACKEND, or
// the model is told walios's rules while running on Pyodide — that exact mismatch was a
// real bug once already. conversations.js calls SandpieTools.waliosPython() for the
// worker's config so there is one answer, not two.
function _waliosCapable() {
  return typeof WebAssembly !== 'undefined'
      && typeof WebAssembly.Suspending === 'function'
      && typeof WebAssembly.promising === 'function';
}
let _waliosWarned = false;
function _waliosPython() {
  let want = false;
  try { want = (localStorage.getItem('sandpie-python-backend') || '').trim() === 'walios'; }
  catch (_) { return false; }
  if (!want) return false;
  if (_waliosCapable()) return true;
  if (!_waliosWarned) {
    _waliosWarned = true;
    console.warn('[sandpie] python backend "walios" requested but this browser has no JSPI '
                 + '(WebAssembly.Suspending/promising) — falling back to Pyodide.');
  }
  return false;
}

const SandpieTools = {
  // The single answer to "is run_python actually running on walios right now?" —
  // the preference AND the browser capability. conversations.js feeds the worker from
  // this so the backend and the tool description can never disagree.
  waliosPython() { return _waliosPython(); },
  names() { return Object.keys(tools); },
  defaultDescription(name) { return tools[name] ? tools[name].description : ''; },
  description(name) {
    // the shipped description (editing removed 2026-08-07), except that run_python
    // describes whichever backend is actually selected
    if (name === 'run_python' && _waliosPython()) return RUN_PYTHON_WALIOS;
    return SandpieTools.defaultDescription(name);
  },
  isCustom(name) { return false; },                                          // custom-description storage is inert
  isEnabled(name) {
    // Hardcoded 2026-08-07: every tool is always ON. The disabled/enabled
    // localStorage sets are ignored — a browser that previously toggled tools
    // is re-enrolled onto all-on.
    return true;
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
  // Raw catalog rows (source name + shipped description), in catalog order.
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
  // What the model ACTUALLY receives — effective name + trimmed description per the
  // current mode. The Settings → Tools inspector renders this so it matches the wire
  // schema (pyodide, short descriptions), not the raw source catalog.
  effectiveList() {
    return Object.keys(tools).filter(name => SandpieTools.isEnabled(name)).map(name => {
      const e = _effectiveTool(name);
      return { name: e.name, description: e.description, available: _toolAvailable(name) };
    });
  },
  shellRelayUrl() { return shellRelayUrl(); },
  setShellRelayUrl(url) { try { localStorage.setItem(SHELL_RELAY_URL_KEY, String(url || '').trim()); } catch (_) {} },
  schemas() { return toolDefs(); },
  schemaFor(name) { const s = toolDefs(); return s.find(t => t.function && t.function.name === name); },
};
window.SandpieTools = SandpieTools;

// ---- Trimmed tool descriptions -------------------------------------------
// The A/Bs (synthetic tie; real multi-turn 7/12=7/12; single-prompt empty 2/8 <
// first-sentence 4/8) showed the description's FIRST SENTENCE carries tool
// selection and the ~90% beyond it is situational execution nuance. So we keep a
// one/two-line "what it does" plus ONLY the few nudges that prevent expensive,
// non-self-correcting mistakes (asyncio.run raises, shell-is-a-different-machine,
// image-already-attached, the plan-first gate). Everything else — repetition,
// when/when-not trees, examples, schema restatement — is cut.
//
// SHORT_DESC is the /app (OPFS workspace) wording; BETA_DESC layers the Dropbox-
// project overrides on top for the fork. run_python→pyodide and the inline-`code`
// param graduated to BOTH modes (NAME / PARAMS); copy_to_workspace→copy stays
// beta-only (BETA_NAME / BETA_PARAMS).
const SHORT_DESC = {
  run_python: 'Run Python and get stdout/stderr. Pass `code` to run a snippet directly (preferred — no throwaway script), or `path` to run a saved .py file under /files. Async: top-level `await` works — end with `await main()`, never asyncio.run() or time.sleep() (use `await asyncio.sleep`). No sockets — for HTTP use `pyodide.http.pyfetch` and check `r.ok`. ~100 packages prebuilt (numpy, pandas, matplotlib, bs4…); others via `await micropip.install(...)`. A relative save lands next to the script; inline `code` runs in /files.',
  write_file: 'Create or overwrite a text file under /files. Creates by default; if it already exists nothing is written unless you pass overwrite:true. For a small change to an existing file, use edit_file instead of rewriting it — never save a renamed copy (foo_v2).',
  edit_file: 'Replace an exact string in an existing file — the preferred way to change one. Fails if old_str is missing or not unique; include enough surrounding text to make it unique.',
  read_file: 'Read a UTF-8 text file under /files (use offset/limit for a line range).',
  delete_file: 'Delete a file or folder under /files.',
  list_files: 'List files and folders (with size + modified time) under /files. Use it to see what exists and to verify a write. scope:"dropbox" lists the connected Dropbox by absolute path.',
  search: 'Find files by content or name (regex) in your workspace. scope:"dropbox" runs a keyword search over file names + contents across the connected Dropbox; an absolute `path` scopes it.',
  web_search: 'Search the web; returns a ranked list of {title, url, snippet}.',
  read_url: 'Fetch a web page and return its main readable text plus the title.',
  load_skill: 'Load a skill\'s full instructions by name (skills and when to use each are listed in the Skills section).',
  load_image: 'Load an image under /files so you can see its pixels — it\'s visible on your next step. Do NOT call it if the image is already attached to the user\'s message (you already see it). You can only see it during this turn; reload the same path in a later turn if you need it again. JPEG/PNG/GIF/WEBP; images over ~5 MB are refused — downscale first (pyodide + Pillow).',
  copy_to_workspace: 'Copy a file from elsewhere in the user\'s Dropbox INTO your editable workspace (/files) so you can read or run it — pass an absolute Dropbox path (from search). The source is never modified.',
  share: 'Share a file or folder with a team department or specific people — published to Dropbox; returns once done.',
  html_console: 'Read the browser console output (log/warn/error, uncaught errors) of an HTML artifact shown in the conversation, to debug it.',
  screenshot: 'Render an HTML artifact and see it as an image — check the layout actually looks right (overlaps, clipping, empty charts, low-contrast text) before telling the user it\'s done.',
  write_todos: 'Track a multi-step task as a flat checklist (skip it for trivial work). Delta form {"todos":[{"id","status"}]} flips status; full list to plan or restructure. At most one task in_progress. While nothing is in_progress the harness offers only planning tools — start a task to unlock the rest; never tell the user a tool is unavailable. Author content in English.',
  scratch: 'Set your working notes for this conversation (plan, hypotheses, blockers, next steps). Survives compaction and is shown to you each round.',
  spawn_subagent: 'Delegate a well-scoped subtask to a fresh subagent that runs its own loop in an isolated context (it does NOT see this conversation) and returns only its final result. Use it to keep your own context clean.',
  shell: 'Run a command on the REMOTE relay host (stdout/stderr/exit code). The relay is a SEPARATE machine — NOT your /files workspace: verify workspace files with list_files, never `ls`/`cat` here. Use it only for the relay itself (builds, ssh/scp to other hosts). Write a relay file by piping content through stdin. Long jobs (>~120s) are killed — launch detached (nohup … & echo $!) and poll a log.',
  walios: 'Run a shell script inside walios — a wasm Linux userland (busybox ash: grep, sed, awk, sort, uniq, cut, wc, find, xargs, diff, wget, nc, plus python3, ssh, make; no tar/gzip/zip). Headless: returns stdout/stderr + exit code. Pass the script in "script".',
  remember: 'Save a durable, non-obvious fact across conversations: a user preference → "user"; a correction on how to work, with the why → "feedback"; lasting project context/decision → "project"; an external pointer or gotcha → "reference". Skip task-local details and anything recoverable from the code/files/git.',
  recall: 'Load memories not currently shown in full, by name or topic.',
  ask: 'Ask the user to choose between options to resolve a genuine ambiguity that would waste real work if guessed wrong — ask early, before doing the work. Batch all questions in ONE call (≤4), each with 2-5 mutually exclusive options and a default. Author in English.',
  respond: 'Deliver your final, user-facing answer (rendered as Markdown). Put ONLY the finished reply here — never thinking, planning, or scratch narration.',
};
// Beta (Dropbox-project) overrides: only the tools whose path model differs from
// /app. Everything else is inherited from SHORT_DESC.
const BETA_DESC = { ...SHORT_DESC,
  run_python: 'Run Python and get stdout/stderr. Pass `code` to run a snippet directly (preferred — no throwaway script), or `path` to run a saved .py script in the project. Async: top-level `await` works — end with `await main()`, never asyncio.run() or time.sleep() (use `await asyncio.sleep`). No sockets — for HTTP use `pyodide.http.pyfetch` and check `r.ok`. ~100 packages prebuilt (numpy, pandas, matplotlib, bs4…); others via `await micropip.install(...)`. Files resolve in the project folder.',
  write_file: 'Create or overwrite a text file in the project. Creates by default; if it already exists nothing is written unless you pass overwrite:true. For a small change to an existing file, use edit_file instead of rewriting it — never save a renamed copy (foo_v2).',
  read_file: 'Read a UTF-8 text file (use offset/limit for a line range). You can read ANY file in the user\'s Dropbox by absolute path, not just the project.',
  delete_file: 'Delete a file or folder in the project.',
  list_files: 'List files and folders (with size + modified time). Use it to see what exists and to verify a write. An absolute path lists anywhere in Dropbox.',
  search: 'Find files by content or name (regex) in the project. scope:"dropbox" runs a keyword search over file names + contents across all of the user\'s Dropbox; an absolute `path` scopes it.',
  load_image: 'Load an image so you can see its pixels — it\'s visible on your next step. Do NOT call it if the image is already attached to the user\'s message (you already see it). You can only see it during this turn; reload the same path in a later turn if you need it again. JPEG/PNG/GIF/WEBP; images over ~5 MB are refused — downscale first (pyodide + Pillow).',
  copy_to_workspace: 'Copy a file or folder from anywhere in the user\'s Dropbox INTO this conversation\'s project folder so you can edit or run it. The source is never modified.',
  shell: 'Run a command on the REMOTE relay host (stdout/stderr/exit code). The relay is a SEPARATE machine — NOT your project files: verify project files with list_files, never `ls`/`cat` here. Use it only for the relay itself (builds, ssh/scp to other hosts). Write a relay file by piping content through stdin. Long jobs (>~120s) are killed — launch detached (nohup … & echo $!) and poll a log.',
};

// The WIRE path is _effectiveTool(), and it prefers SHORT_DESC/BETA_DESC over
// SandpieTools.description() — so the backend-aware text on the accessor never reached
// the model. Caught only by dumping the tools array the app actually POSTed: while
// running WALIOS the model was being told "never asyncio.run()", "No sockets — use
// pyodide.http.pyfetch" and "~100 packages prebuilt", every one of which is false here.
// Same content as RUN_PYTHON_WALIOS, in the short form these maps use.
const SHORT_DESC_WALIOS = "Run Python and get stdout/stderr. Pass `code` to run a snippet directly (preferred — no throwaway script), or `path` to run a saved .py file. Runs on walios (wasm CPython 3.14 on a real Linux userland), NOT Pyodide. Async: top-level `await` works, and asyncio.run(main()) / loop.run_until_complete() work too. Do not use time.sleep() — use await asyncio.sleep(n). REAL SOCKETS: requests and urllib work normally (import requests; r = requests.get(url)); pyodide.http.pyfetch also works and is cheaper for a simple GET — check r.ok / r.status. PACKAGES: numpy, pandas, matplotlib, Pillow, lxml, python-docx, openpyxl, python-pptx, reportlab, pypdf, bs4, xlsxwriter, requests, sqlite3 and more are BUILT IN as real compiled C extensions — just import; others via `await micropip.install(...)` (pure-Python wheels only). NO subprocess: subprocess.run/Popen and os.popen raise OSError [Errno 38] immediately (no fork) — use the walios tool for shell work. OFFICE→PDF: import soffice; soffice.convert('/root/x.docx') → '/root/x.pdf' (in-browser LibreOffice; PDF only). A relative save lands next to the script.";

// BOTH modes: run_python is renamed pyodide() and takes `code` directly (REPL).
const NAME = { run_python: 'pyodide' };
const PARAMS = {
  run_python: { type: 'object', properties: {
    code: { type: 'string', description: 'Python code to run directly (preferred for one-off work).' },
    path: { type: 'string', description: 'Path to an existing .py script to run instead of code.' },
    args: { type: 'array', items: { type: 'string' }, description: 'sys.argv[1:].' },
    timeout: { type: 'number', description: 'Seconds before the run is killed.' },
  }, required: [] },
};
// Beta-only: copy_to_workspace is exposed as copy() with a project-shaped schema.
const BETA_NAME = { copy_to_workspace: 'copy' };
const BETA_PARAMS = {
  copy_to_workspace: { type: 'object', properties: {
    src:  { type: 'string', description: 'Source path — absolute (anywhere in Dropbox) or relative to the project.' },
    dest: { type: 'string', description: 'Optional destination inside the project (default: the source filename).' },
  }, required: ['src'] },
};

// Resolve one tool to the EFFECTIVE {name, description, parameters} actually sent
// to the model — applying the mode's rename, param, and trimmed-description maps.
// Shared by toolDefs() (the wire schema) and SandpieTools.effectiveList() (the
// Settings → Tools inspector), so the panel always shows exactly what's sent.
function _effectiveTool(name) {
  const beta = !!window.SANDPIE_BETA;
  const descMap = beta ? BETA_DESC : SHORT_DESC;
  let description = (descMap[name] != null) ? descMap[name] : SandpieTools.description(name);
  // run_python describes whichever backend is actually selected, on the wire path too.
  if (name === 'run_python' && _waliosPython()) description = SHORT_DESC_WALIOS;
  const outName = (beta && BETA_NAME[name]) || NAME[name] || name;
  const params = (beta && BETA_PARAMS[name]) || PARAMS[name] || tools[name].parameters;
  // /app search: append WHERE the workspace + team shared area sit in Dropbox, so
  // a scope:"dropbox" search can target the shared folder precisely. (Beta carries
  // its per-conversation project path in the system prompt instead.)
  if (!beta && name === 'search') {
    try {
      const p = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
      const wr = p && p.workingRoot && p.workingRoot();
      if (wr) {
        const team = (p.teamParent && p.teamParent()) || '';
        description += `\nYour workspace is the Dropbox folder "${wr}", in the user's own Dropbox.`
          + (team ? ` The team's shared area is "${team}" — to search it, use scope:"dropbox" with path:"${team}" (or another absolute folder).`
                  : ` To search elsewhere in Dropbox, use scope:"dropbox" with an absolute folder path.`);
      }
    } catch (_) {}
  }
  return { name: outName, description, parameters: params };
}

const toolDefs = () => Object.entries(tools)
  .filter(([name]) => SandpieTools.isEnabled(name) && _toolAvailable(name))
  .map(([name]) => ({ type: 'function', function: _effectiveTool(name) }));

