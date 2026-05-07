# Publish Plan

Roadmap for turning this into a public GitHub repo. Polish first, ship after.

## Phase 0 — Decisions to lock before any work

- [ ] **Project name.** "OpenCode" collides with sst/opencode. Candidates: `countained`, `opfs-chat`, `localagent`, `sandshell`. Pick one — it gates README, repo URL, and the title in `index.html`.
- [ ] **License.** MIT (most permissive, best for adoption) or Apache-2.0 (explicit patent grant). Recommend MIT for a small pet project.
- [ ] **Target audience for the README.** Two valid pitches: (a) "privacy-conscious AI workspace", (b) "hackable single-file LLM playground." They aim at different readers. Pick one as the lead.

## Phase 1 — Pre-publish polish (must-do)

### 1.1 Repo hygiene
- [ ] Add `LICENSE` (text matching chosen license)
- [ ] Add `.gitignore`: `__pycache__/`, `*.pyc`, `.env`, `.DS_Store`, `node_modules/` (in case anyone tools it later), `*.swp`
- [ ] Rename `index.html` `<title>` and any "OpenCode" references to chosen project name
- [ ] Verify no secrets, API keys, or personal paths in any file before first commit

### 1.2 README (the load-bearing document)
Structure (top → bottom):
1. **One-line pitch** — what it is, why it's different, in <20 words.
2. **Animated demo GIF** — 10–15s screencap: upload file → ask AI to grep → answer. Hosted in repo as `docs/demo.gif`. Sells the pitch faster than prose.
3. **Why this exists** — 2–3 sentences on the containment thesis. Sandboxed OPFS, Pyodide for compute, explicit sync to your own cloud storage. No backend, no telemetry, BYO LLM key.
4. **Quick start** (target: 60 seconds from clone to first message)
   - `git clone …`
   - `python serve.py`
   - Open localhost:8080, paste OpenAI key + model + base URL, hit Save, type a message
5. **Dropbox setup** — annotated screenshots of the dev console flow:
   - Create app at dropbox.com/developers/apps (Scoped access, App folder or Full Dropbox)
   - Permissions: `files.content.read`, `files.content.write`, `files.metadata.read`
   - Settings → Redirect URIs → add `http://localhost:8080/` exactly (note the trailing slash, click Add)
   - Copy App key into the sidebar slot
6. **What the AI can do** — list the three tools with one-line examples each (`read_file`, `edit_file`, `run_python`). Show a sample chat: "grep for TODO in all files" → Pyodide script → output.
7. **Architecture** — one-paragraph mental model. OPFS = working set. Pyodide = compute. Dropbox = optional canonical store. `serve.py` = thin CORS-bypass proxy, no business logic.
8. **Browser support** — table:
   | Browser | Status |
   |---|---|
   | Chrome/Edge ≥ 110 | ✅ |
   | Firefox ≥ 111 | ✅ |
   | Safari ≥ 17 | ✅ (OPFS), ⚠️ untested with Dropbox redirect |
9. **Security & limitations** — be honest:
   - Refresh tokens in `localStorage` are XSS-fragile. Don't deploy this on a public origin you don't control.
   - OPFS quota varies by browser; under storage pressure data can be evicted.
   - The proxy disables TLS verification (see Phase 1.4) — fix in this version.
   - Pyodide is single-threaded; long scripts block the UI.
   - Sync is push-only, additive (doesn't delete Dropbox files missing from OPFS).
   - Tools operate on flat OPFS; Dropbox subfolders aren't recursed.
10. **License** line + link to LICENSE.

### 1.3 Demo asset
- [ ] Record 10–15s GIF: upload 2–3 small text files → ask "grep for the word X" → see Pyodide tool call → see result. Tools to record: ScreenToGif (Win), Kap (Mac), peek (Linux). Optimize ≤ 3 MB.
- [ ] Save as `docs/demo.gif`. Reference in README.

### 1.4 Tighten `serve.py` for public release
- [ ] **Remove `ssl.CERT_NONE`** — default to verified TLS. Currently bypasses cert validation, which is a footgun in a published tool.
- [ ] **Bind to `127.0.0.1`** explicitly (already does, but document it). Add a comment that this proxy is localhost-only by design.
- [ ] **Add a Content-Length-aware upload path.** Right now we read the full body into memory before forwarding — fine for chat completions, fine for typical Dropbox uploads, but worth a comment noting the 100 MB-ish ceiling.
- [ ] **Document why the proxy exists** — header forwarding for Dropbox, CORS bypass — so a security-minded reader doesn't assume malice.

## Phase 2 — Strongly recommended polish

### 2.1 UX nits
- [ ] Show the redirect URI in the sidebar Dropbox section (`location.origin + '/'`) with a tiny "copy" button so users don't have to guess what to register.
- [ ] Visible "Pyodide: ready / loading / not loaded" indicator in the sidebar — currently only shown in chat on first load.
- [ ] Better error display for fetch failures — right now "Failed to fetch" is opaque; expose the underlying status & body if available.
- [ ] Empty-state hint in the chat panel explaining: "Configure endpoint and API key on the left, then say hi."

### 2.2 Code hygiene
- [ ] Inline section banners (`// ===== ... =====`) are good; keep them. Don't fragment into modules — single-file is part of the pitch.
- [ ] Add a `// @ts-check` JSDoc comment block for the more involved functions (`streamRound`, `dbxApi`, `syncOpfsToPy`) — costs nothing, helps readers and editors.
- [ ] Extract magic strings (`'/proxy/'`, `'opencode-config'`, `'dbx-tokens'`) into a constants block at the top.

### 2.3 Footguns to defuse
- [ ] On `dbxConnect()`, show a confirmation dialog if there are unsynced OPFS edits — currently a fresh OAuth round-trip can wipe in-flight work if combined with a Pull.
- [ ] On `dbxDisconnect()`, call `/2/auth/token/revoke` *before* clearing localStorage — currently we just orphan the token at Dropbox.
- [ ] On `clearChat()`, confirm if there are messages — accidental click loses history.
- [ ] On OPFS `×` delete button, confirm — accidental click loses a file.

## Phase 3 — Nice-to-have (not blockers)

- [ ] "Why not LangChain / Cursor / Code Interpreter / etc." paragraph in README — helps people self-select.
- [ ] Export OPFS as zip (download all files in one click). One library or 30 lines with `JSZip`.
- [ ] Import zip → write all entries to OPFS.
- [ ] Audit log: append every tool call (name, args hash, timestamp) to `_audit.jsonl` in OPFS. Toggleable.
- [ ] System prompt as a special `_system.md` file in OPFS, auto-loaded each turn if present.
- [ ] Recursive Dropbox pull/sync + nested OPFS (this is the obvious next architectural extension; defer until v2).

## Phase 4 — Things to explicitly skip for v1

- ❌ Tests / CI — overhead exceeds value at this size. Add when contributors arrive.
- ❌ Docker — `python serve.py` is already simpler than a `docker run` command.
- ❌ Dedicated docs site (mkdocs, docusaurus, etc.) — README until it's not enough.
- ❌ Issue/PR templates — empty templates feel desperate. Add when there are real issues.
- ❌ `CONTRIBUTING.md` — same logic. Wait for the second contributor.
- ❌ Multi-LLM provider abstraction — the OpenAI-compatible base URL field already covers OpenAI, Anthropic via proxies, OpenRouter, local Ollama, etc. Don't add SDK adapters.

## Phase 5 — Launch

- [ ] Cut a `v0.1.0` tag once Phases 1 + 2 are done.
- [ ] Post to: HN ("Show HN: A browser-sandboxed AI workspace…"), Reddit r/LocalLLaMA, Lobste.rs.
- [ ] Pin the Dropbox-setup section as a discussion or wiki page if questions repeat.

## Open questions to resolve later

- Should `run_python` reset Pyodide state between turns? (Pro: deterministic. Con: can't build up state.)
- Recursive Dropbox: flatten paths in OPFS or mirror the tree as nested OPFS dirs? Mirror is right but more work.
- GitHub adapter as a third backend? Pulls and commits a repo. Powerful, fits the same shape, but auth + diff semantics get hairy.
- Self-hosted deployment story (Cloudflare Worker proxy + GitHub Pages static)? Tempting; punt to v2.
