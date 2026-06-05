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
  description: `Create a new file in OPFS under /files/. Fails if the file already exists — use edit_file to modify existing files. Path is relative to /files/ (e.g. "scripts/analyze.py", "artifacts/chart.html"). Use this to create scripts before running them with run_python.`,
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
  description: `Replace an exact string in an existing OPFS file. old_str must appear exactly once — fails if zero or 2+ matches. Always read the file with run_python first to verify exact content before editing.`,
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
        load_image: {
      description: `Load an image file from OPFS into the conversation so you can see its pixel content.
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

