// sandpie /modules/tools.js — Tool schema definitions

const tools = {
  run_python: {
    description: `Execute a Python script from OPFS via Pyodide. Working dir is /files/ (persistent).
REQUIRED: path must point to a script already saved in OPFS (typically under sandpie/scripts/). Use write_file to create a script first, then call run_python with its path.
ONLY path: + args: are accepted. Scripts must be saved to OPFS before execution.
ASYNC: your code runs ON an already-running event loop, so TOP-LEVEL await works — call coroutines directly (end the script with await main(), which works even inside an if __name__ == '__main__': block). Do NOT use asyncio.run(), loop.run_until_complete(), or asyncio.new_event_loop() — they raise "event loop is already running". Do NOT use time.sleep() (it blocks this run's interpreter and burns the timeout) — use await asyncio.sleep(n).
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
        timeout: { type: 'number', description: 'Max seconds the script may run before it is killed (default 120, max 600). On timeout the run is aborted and its interpreter discarded, so it can never hang the conversation — raise this only for genuinely long computations.' },
      },
      required: ['path'],
    },
  },
  write_file: {
  description: `Create a NEW file in OPFS under /files/. If the file already exists it is NOT overwritten — its current content is returned instead, so you can edit_file it in place (don't rewrite it or save a renamed copy). Path is relative to /files/ (e.g. "sandpie/scripts/analyze.py", "sandpie/artifacts/chart.html"). Use this to create scripts before running them with run_python.

For large or multi-line content, you MAY skip JSON and emit the body as a raw block in your reply instead (no escaping of newlines/quotes needed):
<|write_file:PATH|>
<file content, verbatim>
<|end_write_file|>`,
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
    description: `Inject a file from OPFS into the chat as an artifact card.
File type never blocks this — show any file the user might want:
- HTML (full page, CDN JS works), SVG, PNG/JPG/GIF/WebP, PDF, CSV, TXT, JSON, and
  Office docs (docx/xlsx/pptx, rendered in-app via LibreOffice) preview INLINE.
- Any OTHER type shows a clickable card that opens/downloads the file — still useful.
Use whenever the user says "show this", "artifact", "add into chat", "inject", or
after you've written an output file worth surfacing.
The file must already exist in OPFS — write it first (e.g. with run_python).
Path is OPFS-relative — no leading slash (e.g. "sandpie/artifacts/chart.html").
Default output folder is sandpie/artifacts/ — use it unless the user says otherwise.
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
      description: `Copy a file INTO the user's editable workspace so you can modify it. Two uses: (1) FORK a workspace file — e.g. a shared package under "sandpie/shared-installed/" — into a standalone copy (shared-installed files are now editable in place via editor write-back, but forking is still handy for a detached copy): pass its workspace path as src (no leading slash). (2) IMPORT a file from ELSEWHERE in the user's Dropbox that read_file/run_python/load_image can't reach: pass an absolute Dropbox path like "/R+D+I/reports/q1.pdf" (as returned by search). The source is never modified in either case. Returns the new editable workspace-relative path; then use read_file / edit_file / run_python on it.`,
      parameters: {
        type: 'object',
        properties: {
          src:  { type: 'string', description: 'Either a workspace path to fork (e.g. "sandpie/shared-installed/impagados/dashboard.html") or an absolute Dropbox path to import (e.g. "/R+D+I/reports/q1.pdf").' },
          dest: { type: 'string', description: 'Optional destination within the workspace (default: the source filename, lifted out of sandpie/shared-installed/), e.g. "imported/q1.pdf".' },
        },
        required: ['src'],
      },
    },
    share: {
      description: `Share a file or folder in OPFS with the team or with specific people (1:1).
The share is performed by the page (Dropbox), so this tool returns once it is published.
- type "team": recipients are TEAM/DEPARTMENT FOLDER names (e.g. ["R+D+I"]) — the item is copied into that department's shared hub; only that department can read it (Dropbox folder membership is the boundary).
- type "p2p": recipients are EMAIL addresses — a folder is shared live in place, a single file is wrapped into an outbox folder, and each recipient is invited as a folder member.
permissions: "viewer" (default, read-only) or "editor" (may write back); "read"/"write" aliases accepted. Permissions apply to p2p invites; team shares are bounded by the department folder membership.
path is OPFS-relative (e.g. "sandpie/artifacts/report.html").`,
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'OPFS path of the file or folder to share (e.g. "sandpie/artifacts/x.html").' },
          type: { type: 'string', enum: ['team', 'p2p'], description: '"team" = publish to department hub(s); "p2p" = share 1:1 with email recipients.' },
          recipients: { type: 'array', items: { type: 'string' }, description: 'team: department folder names (e.g. ["R+D+I"]); p2p: recipient email addresses.' },
          permissions: { type: 'string', enum: ['viewer', 'editor'], description: '"viewer" (default) read-only, or "editor" (recipient may write back).' },
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
path is OPFS-relative (e.g. "sandpie/artifacts/report.html").`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'OPFS path of the file or folder to share (e.g. "sandpie/artifacts/x.html").' },
        type: { type: 'string', enum: ['team', 'p2p'], description: '"team" = publish to department hub(s); "p2p" = share 1:1 with email recipients.' },
        recipients: { type: 'array', items: { type: 'string' }, description: 'team: department folder names (e.g. ["R+D+I"]); p2p: recipient email addresses.' },
        permissions: { type: 'string', enum: ['viewer', 'editor'], description: '"viewer" (default) read-only, or "editor" (recipient may write back).' },
      },
      required: ['path', 'type', 'recipients'],
    },
  },
  html_console: {
    description: `Read the browser console output of an HTML artifact that is shown in the conversation (rendered via show_artifact), so you can see console.log/warn/error output, uncaught errors, and unhandled promise rejections from the artifact's own JavaScript.
WHEN TO USE: after showing an HTML artifact, when the user reports something looks broken (blank areas, missing elements, wrong layout) or you want to verify the page's JS ran without errors. The console is captured from load time (the capture script is injected before the artifact's own scripts), so load-time errors are included.
WHEN NOT TO USE: for non-HTML artifacts (images, PDFs, office docs have no console). If the artifact is not currently open in the conversation, call show_artifact first — the console is read from the live preview frame.
path: optional — omit to read the most recently shown artifact, or pass the exact path (e.g. "sandpie/artifacts/report.html").`,
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Optional OPFS path of the artifact (e.g. "sandpie/artifacts/report.html"). Omit to target the most recently shown artifact.' },
      },
      required: [],
    },
  },
  write_todos: {
      description: `Create and manage a structured task list for the current session. This helps you track progress, organize complex work, and demonstrate to the user that you understand the scope.
Use it for: complex multi-step tasks (3+ distinct steps); non-trivial work that needs planning; when the user gives you multiple tasks or explicitly asks for a todo list; when you start a task (mark it in_progress) and when you finish one (mark it completed and add any follow-ups).
Do NOT use it for: a single straightforward task; trivial work; anything doable in under 3 steps; purely conversational requests — it only adds overhead there.
The harness holds the list as a FLAT set of tasks with IDs; you send deterministic OPS and it returns the current state. You do NOT resend or rewrite the whole list (that silently erased work in the past).
FIRST plan: send a full list once — {"todos":[{"content":"…"}, …]} — accepted only when there is no checklist yet.
THEN update with ops: {"ops":[ … ]}. Each op:
  {"op":"add","text":"Run tests","activeForm":"Running tests"?,"blockedBy":["2"]?}   add a task. text = imperative title; activeForm = present-continuous form shown while it runs; blockedBy = ids of tasks that must complete before this one can start.
  {"op":"block","id":"3","by":["1"]}  /  {"op":"unblock","id":"3","by":["1"]}   add/remove blockers (tasks that must complete before this one can start) after creation.
  {"op":"start","id":"3"}   mark in_progress before you begin it. Refused while the task still has an open blocker; several tasks may be in progress at once if nothing blocks them.
  {"op":"complete","id":"3"}   mark done — ONLY when you have FULLY accomplished it. Never complete a task if tests fail, the implementation is partial, or errors are unresolved: keep it in_progress. If you hit a blocker you can't clear, keep the task in_progress and add a new task describing what must be resolved.
  {"op":"delete","id":"3"}   remove a task you're no longer doing (also removed from any other task's blockedBy).
IDs are shown in the returned checklist. You can batch several ops in one call. A full {"todos":[…]} replacement is refused while any task is still open — complete or delete them first.`,
      parameters: {
        type: 'object',
        properties: {
          ops: {
            type: 'array',
            description: 'Operations to apply, in order. Use this to update an existing checklist.',
            items: {
              type: 'object',
              properties: {
                op:        { type: 'string', enum: ['add', 'start', 'complete', 'delete', 'block', 'unblock'], description: 'The operation.' },
                text:      { type: 'string', description: 'For "add": the task, as a brief imperative title (e.g. "Run tests").' },
                blockedBy: { type: 'array', items: { type: 'string' }, description: 'For "add": mark tasks that must complete before this one can start (e.g. ["2"]).' },
                activeForm:{ type: 'string', description: 'For "add": the present continuous form shown while the task is in progress (e.g. "Running tests").' },
                id:        { type: 'string', description: 'For start/complete/delete/block/unblock: the target task id.' },
                by:        { type: 'array', items: { type: 'string' }, description: 'For block: mark tasks that must complete before this one can start. For unblock: the blocker ids to remove.' },
              },
              required: ['op'],
            },
          },
          todos: {
            type: 'array',
            description: 'Full list — ONLY for the initial plan, or a reset when every task is completed/deleted. Refused while any task is open.',
            items: {
              type: 'object',
              properties: {
                content:   { type: 'string', description: 'The task, as a brief imperative title (e.g. "Run tests").' },
                status:    { type: 'string', enum: ['pending', 'in_progress', 'completed'], description: 'Initial state (usually "pending").' },
                blockedBy: { type: 'array', items: { type: 'string' }, description: 'Mark tasks (from this same list) that must complete before this one can start.' },
                activeForm:{ type: 'string', description: 'The present continuous form shown while the task is in progress (e.g. "Running tests").' },
              },
              required: ['content'],
            },
          },
        },
        required: [],
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
      description: `Run a shell command and get back its stdout, stderr, and exit code. This is a real terminal on the machine hosting the sandpie relay — run the relay INSIDE your target environment (e.g. WSL) so commands land where your project lives.
EVERYTHING IS JUST A COMMAND: local work ("cargo test"), a different machine over SSH ("ssh myserver 'systemctl restart app'"), file transfer ("scp myserver:/var/log/x.log /tmp/"). ssh/scp use the relay host's own ~/.ssh — there is no key setup or target switch here.
WRITE A FILE WITH ZERO ESCAPING: pipe the content through stdin instead of a heredoc — {"command":"cat > /path/file.rs", "stdin":"<the entire file content>"}. The content never touches the command line, so quotes, $, backticks, (parens) and newlines survive verbatim. Read it back with {"command":"cat /path/file.rs"}. NEVER build cat<<EOF / sed one-liners for file content — use stdin.
LONG JOBS (>~120s: full builds, kernel boots): a call is killed at ~120s, so launch detached and poll a log — {"command":"nohup cargo build --release >/tmp/b.log 2>&1 & echo $!"} then {"command":"tail -40 /tmp/b.log"}.
Requires the local relay running; on a connection error, tell the user to start it and do NOT retry in a loop.`,
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

};
//// Lets the user (Settings → System prompt) turn tools off and rewrite their
// descriptions. Stored globally so it applies to every conversation. toolDefs()
// — what's actually sent to the model — is the single choke point that honors it.
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
  shellRelayUrl() { return shellRelayUrl(); },
  setShellRelayUrl(url) { try { localStorage.setItem(SHELL_RELAY_URL_KEY, String(url || '').trim()); } catch (_) {} },
  schemas() { return toolDefs(); },
  schemaFor(name) { const s = toolDefs(); return s.find(t => t.function && t.function.name === name); },
};
window.SandpieTools = SandpieTools;

const toolDefs = () => Object.entries(tools)
  .filter(([name]) => SandpieTools.isEnabled(name) && _toolAvailable(name))
  .map(([name]) => {
    let description = SandpieTools.description(name);
    // Tell the model WHERE its workspace sits in Dropbox, and where the team's
    // shared area is, so a scope:"dropbox" search can target the shared folder
    // precisely (e.g. /R+D+I) instead of guessing. The workspace is in the user's
    // OWN Dropbox and the shared area is in the team space — two different places,
    // so the shared path is asked for directly rather than derived from the
    // workspace path. Only when Dropbox is connected + the working root resolved.
    if (name === 'search') {
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
    return { type: 'function', function: { name, description, parameters: tools[name].parameters } };
  });

