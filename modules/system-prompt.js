/**
 * System Prompt module for Sandpie
 *
 * The chat system prompt is a FIXED base prompt (the DEFAULT literal below)
 * plus an optional user suffix APPENDED after it. The suffix is stored in the
 * synced OPFS file sandpie/config/system-prompt.json — visible in the file
 * browser and synced via Dropbox — mirrored in a synchronous in-memory cache.
 *
 * - SandpieSystemPrompt.get() is read by conversations.js buildSystemPrompt().
 * - Registers a "System" section in the Settings modal (gear), with a
 * - One-time migrations: pull any existing sandpie_memory.md into the suffix
 *   then delete that file locally AND from Dropbox; move any localStorage
 *   suffix into sandpie/config/system-prompt.json (the synced source of truth).
 */
const SandpieSystemPrompt = (function () {
  'use strict';

  const KEY = 'sandpie-system-prompt';              // legacy localStorage suffix (migrated → FILE)
  const FILE = 'sandpie/config/system-prompt.json'; // synced source of truth
  const MIGRATED_KEY = 'sandpie-sysprompt-migrated';      // sandpie_memory.md → KEY (legacy)
  const FILE_MIGRATED_KEY = 'sandpie-sysprompt-file-v1';  // KEY → FILE (one-time)
  const DEFAULT = `You are an agent that gets real work done with tools. You are judged by whether
the task is actually done and verified — not by how much you explain.

## LANGUAGE: follow the per-request language directive exactly
Every request carries a "## Deliver in …" directive naming the conversation's
language and which of two regimes applies. It is the sole authority on language;
follow it exactly, and re-check it rather than assuming.
- AUTHOR-IN-ENGLISH regime ("author in English"): the target is a language you do
  NOT generate reliably - writing it yourself produces garbled, lossy, broken text.
  Author EVERYTHING in English - reasoning, every tool call and its arguments, every
  file/document/script body, code, comments, todo items, questions, scratch notes,
  and your respond() text - and set the delivery "language" argument; the system
  translates your English downstream. Under this directive the rule is HARD: no user
  instruction overrides it, and any non-English output you produce in any channel is
  rejected and re-prompted. A request to "write it in <that language>" is satisfied
  by authoring English + setting the delivery "language", never by writing it directly.
- NATIVE regime ("author it directly"): the target is a language you generate
  fluently. Author user-facing text (respond() reply, todo items, ask() questions,
  document bodies written for the user) directly in it; there is no translation
  layer, so never leave English in user-facing text. Code, identifiers, and internal
  reasoning stay in English.
In both regimes, a one-off deliverable in some OTHER language follows the same split:
fluent languages you may author directly; anything else is authored in English with
that language code set on the delivery.

## Act, don't speculate
If a claim is checkable with a tool, check it. Never assert a value, output, or
behavior you could have verified. The moment you think "it should be X", "I think",
"probably", or "let me check" — stop and run the check. That sentence is a
hypothesis; one tool call settles it. Prefer running a probe over reasoning about
what something "should" be.

## Use the real thing, not your head
Never eyeball raw data — bytes, hex, logs, output — and interpret it in prose. Run
the actual decoder, parser, or command and read its result. A probe that prints
interpreted state beats a paragraph of hand-analysis every time.

## One step, then verify
Don't chain guesses. Make at most one inference, then ground it with a tool. If a
result contradicts your expectation, say so plainly and change your hypothesis —
do not reshape the story to fit the result.

## Tools are cheap; being wrong is expensive
Bias toward action. A failed or empty tool result is information, not a reason to
fall back on speculation — adjust and try again.

## Match effort to the task
When the user is simply asking a question or wants your judgment, answer directly
and concisely — don't force tools where none are needed.

## Plan before you act
Before using ANY tool other than write_todos (and the respond() reply), you must
have a plan with one task marked in_progress. So your FIRST action on real work is
write_todos: lay out the steps and mark the task you're starting as in_progress.
Then do that task; mark it completed and start the next. Tools stay blocked until a
task is active — and once every task is done, a fresh request needs a fresh plan.
(A trivial reply that needs no tools can just go straight to respond().)

## Answer ONLY through respond()
respond() is the only channel the user can see. Anything you write as plain text is
hidden from them — it does not reach the chat. So you MUST deliver every reply by
calling respond(). Never try to answer in plain prose; never narrate between tool
calls. Put reasoning in your reasoning channel and the finished answer in respond()'s
"text", authored per the language directive above (English when the author-in-English
regime is active — the system translates delivery — otherwise the reply language
itself), and always set the "language" argument.

Every turn ENDS on a respond() — the harness never lets a turn finish on any other
tool, so make respond() your FINAL action. The clean pattern: do all the work and
side effects first (files, remember, final write_todos), then call
respond() once at the very end. You MAY respond earlier and keep working, but then
you MUST respond() again at the end, so the last thing the user sees is your final
conclusion reflecting everything you did — never leave the turn ending on a
remember/write_todos/work call. If you must reply in more than one language, emit
those respond() calls together (one per language) as that final step.`;
  // The default prompt shipped before 2026-08-07. Browsers that stored exactly
  // this (i.e. never really customized) are re-enrolled onto the new DEFAULT;
  // genuinely custom prompts are untouched.
  const LEGACY_DEFAULT = 'You are a helpful assistant that reasons through the users requests step-by-step.';
  function forgetLegacyDefault() { try { if (localStorage.getItem(KEY) === LEGACY_DEFAULT) localStorage.removeItem(KEY); } catch (_) {} }

  // The user-editable part is an APPEND-ONLY suffix: the base prompt is a hard
  // default and can never be replaced from the Settings modal. get() composes
  // DEFAULT + suffix. A stored value equal to DEFAULT (an old explicit copy)
  // counts as no suffix so the default is never duplicated.
  // Storage: OPFS file sandpie/config/system-prompt.json {"text": "…"} — synced
  // via Dropbox and visible in the file browser — mirrored into the sync
  // _suffix cache. get()/getAppend() are async; set() writes debounced and
  // emits file:changed so the sync provider uploads it.
  let _suffix = '';
  let _ready = null;   // Promise of the initial file read (null → not started / retry)
  let _ver = 0;        // bumped on set(); guards stale reads from clobbering a newer value
  function clean(s) { const t = String(s || '').trim(); return (t && t !== DEFAULT) ? t : ''; }
  function readFile() {
    return (async () => {
      try {
        if (!(window.opfs && opfs.readBytes)) return '';
        const buf = await opfs.readBytes(FILE);
        const obj = JSON.parse(new TextDecoder().decode(buf));
        return (obj && typeof obj.text === 'string') ? obj.text : '';
      } catch (_) { return ''; }   // missing/unparseable → no suffix
    })();
  }
  function writeFile(text) {
    return (async () => {
      if (!(window.opfs && opfs.write)) return false;
      await opfs.write(FILE, new Blob([JSON.stringify({ text })], { type: 'application/json' }));
      if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', FILE);
      return true;
    })();
  }
  function ensureLoaded() {
    if (!_ready) {
      _ready = (async () => {
        const v = _ver;
        const s = await readFile();
        if (v === _ver) _suffix = s;          // skip if a set() landed during the read
        if (!(window.opfs && opfs.readBytes)) { _ready = null; return ''; }  // opfs not mounted yet — retry next call
        return s;
      })();
    }
    return _ready;
  }
  async function get() { await ensureLoaded(); const s = clean(_suffix); return s ? DEFAULT + '\n\n' + s : DEFAULT; }
  // Raw stored text exactly as the user typed it ('' when unset or a duplicate
  // of DEFAULT) — what the Settings textarea shows and edits.
  async function getAppend() { await ensureLoaded(); return clean(_suffix) ? _suffix : ''; }
  function isCustom() { return clean(_suffix) !== ''; }
  // Debounced write: the modal fires on every keystroke; persist ~350ms after
  // the last one and flash 'Saved' only when the file write actually lands.
  let _writeTimer = null;
  function set(v) {
    const text = (v == null) ? '' : String(v);
    _ver++;
    _suffix = text;
    _ready = Promise.resolve(text);
    if (_writeTimer) clearTimeout(_writeTimer);
    _writeTimer = setTimeout(() => {
      _writeTimer = null;
      writeFile(text).then(() => flashMsg('Saved')).catch(() => {});
    }, 350);
  }

  // One-time migration off the old OPFS sandpie_memory.md. Seed the local prompt
  // from it (hydrating first if it's a dehydrated placeholder), then remove the
  // file locally AND from Dropbox (file:deleted → the sync provider's delete).
  // Best-effort: retries next load if OPFS isn't ready yet.
  async function migrate() {
    if (localStorage.getItem(MIGRATED_KEY) === '1') return;
    if (typeof opfs === 'undefined') return;
    try {
      if (localStorage.getItem(KEY) == null) {
        let old = null;
        try { old = await opfs.read('sandpie_memory.md'); } catch (_) {}
        if (old == null) {   // maybe a dehydrated placeholder — hydrate then read
          try {
            const sp = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
            if (sp && sp.hydrate) { await sp.hydrate('sandpie_memory.md'); old = await opfs.read('sandpie_memory.md'); }
          } catch (_) {}
        }
        if (old != null && old.trim() && old.trim() !== DEFAULT) localStorage.setItem(KEY, old);
      }
      let existed = false;
      try { existed = await opfs.exists('sandpie_memory.md'); } catch (_) {}
      try { await opfs.remove('sandpie_memory.md'); } catch (_) {}
      // Remove the Dropbox copy too — standard delete path; no-op if not connected.
      if (existed && window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', 'sandpie_memory.md');
      localStorage.setItem(MIGRATED_KEY, '1');
    } catch (_) { /* leave MIGRATED_KEY unset → retry next load */ }
  }

  // One-time migration: localStorage KEY (previous storage) → OPFS FILE. The
  // file is now the source of truth; a legacy per-device suffix seeds it on
  // first run, then the key is dropped. No-op once FILE_MIGRATED_KEY is set.
  async function migrateFile() {
    if (localStorage.getItem(FILE_MIGRATED_KEY) === '1') return;
    try {
      if (!(window.opfs && opfs.write)) return;   // retry next init
      const existing = await readFile();
      if (!existing) {
        const stored = localStorage.getItem(KEY);
        if (stored != null) await writeFile(stored);
      }
      localStorage.removeItem(KEY);
      localStorage.setItem(FILE_MIGRATED_KEY, '1');
    } catch (_) { /* leave FILE_MIGRATED_KEY unset → retry next load */ }
  }

  const HTML = `
        <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.5rem;">Use this box to add your own <b>rules or persona</b> for the AI — anything you type here is <b>appended</b> to the base prompt and sent to the AI in <b>every conversation</b>.</p>
        <textarea id="sysPromptText" rows="6" spellcheck="false" placeholder="Append to the base prompt (optional)…" style="width:100%; resize:vertical; padding:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font:0.82rem 'JetBrains Mono', Consolas, monospace; line-height:1.45;"></textarea>
        <div style="display:flex; align-items:center; gap:0.6rem; margin-top:0.4rem;">
          <span id="sysPromptStatus" style="font-size:0.7rem; color:var(--sp-text-dim); flex:1; min-width:0;"></span>
          <button type="button" class="ghost" id="sysPromptReset" style="font-size:0.72rem; padding:0.2rem 0.55rem;">Reset to default</button>
        </div>

        <div class="sp-block">
          <div class="sp-block-head">Skills <span class="sp-count" id="spSkillsCount"></span></div>
          <div id="spSkillsErrors"></div>
          <div id="spSkillsList"></div>
          <button type="button" class="ghost" id="spSkillCreate" style="font-size:0.72rem; padding:0.2rem 0.55rem; margin-top:0.4rem;">Create example skill</button>
        </div>

        <div class="sp-block">
          <div class="sp-block-head">Tools <span class="sp-count" id="spToolsCount"></span></div>
          <div id="spToolsList"></div>
        </div>
      `;

  let _flashT = null;
  function flashMsg(msg) {
    const el = document.getElementById('sysPromptStatus');
    if (!el) return;
    el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500);
  }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // A collapsible row: [checkbox] name  …preview…  meta  ▸ ; clicking anywhere
  // but the checkbox toggles the body open/closed.
  function makeRow(checkbox, nameText, metaText, descPreview) {
    const row = document.createElement('div'); row.className = 'sp-item';
    const head = document.createElement('div'); head.className = 'sp-item-head';
    if (checkbox) head.appendChild(checkbox);
    const name = document.createElement('span'); name.className = 'sp-item-name'; name.textContent = nameText;
    if (checkbox && !checkbox.checked) name.style.opacity = '0.5';
    head.appendChild(name);
    if (descPreview) {
      const desc = document.createElement('span'); desc.className = 'sp-item-desc'; desc.textContent = descPreview;
      head.appendChild(desc);
    }
    const meta = document.createElement('span'); meta.className = 'sp-item-meta'; meta.textContent = metaText || '';
    head.appendChild(meta);
    const caret = document.createElement('span'); caret.className = 'sp-caret'; caret.textContent = '▸';
    head.appendChild(caret);
    const body = document.createElement('div'); body.className = 'sp-item-body'; body.style.display = 'none';
    row.append(head, body);
    head.addEventListener('click', (e) => {
      if (e.target === checkbox) return;
      const open = body.style.display === 'none';
      body.style.display = open ? '' : 'none'; caret.textContent = open ? '▾' : '▸';
      if (open && body._onOpen) { const f = body._onOpen; body._onOpen = null; f(); }
    });
    return { row, head, body };
  }

  function renderTools(panel) {
    const listEl = panel.querySelector('#spToolsList');
    const countEl = panel.querySelector('#spToolsCount');
    if (!listEl || typeof SandpieTools === 'undefined') return;
    // Show the EFFECTIVE definitions the model receives (pyodide, trimmed
    // descriptions) rather than the raw source catalog — the panel is an inspector
    // of what's actually sent. Falls back to list() on an older tools.js.
    const items = (typeof SandpieTools.effectiveList === 'function') ? SandpieTools.effectiveList() : SandpieTools.list();
    if (countEl) countEl.textContent = String(items.length);
    listEl.innerHTML = '';
    for (const t of items) {
      // All tools are always ON (toggle removed 2026-08-07); the description is
      // read-only — expand a row to inspect the exact text sent to the model.
      const meta = t.available ? '' : 'needs Dropbox';
      const { row, body } = makeRow(null, t.name, meta, null);
      const pre = document.createElement('pre');
      pre.className = 'sp-edit';
      pre.style.cssText = 'margin:0; white-space:pre-wrap; word-break:break-word;';
      pre.textContent = t.description;
      body.appendChild(pre);
      listEl.appendChild(row);
    }
  }

  async function renderSkills(panel) {
    const listEl = panel.querySelector('#spSkillsList');
    const errEl = panel.querySelector('#spSkillsErrors');
    const countEl = panel.querySelector('#spSkillsCount');
    if (!listEl || typeof SandpieContext === 'undefined' || !SandpieContext.inspect) return;
    let idx;
    try { idx = await SandpieContext.inspect([]); } catch (_) { return; }
    if (!idx || !idx.exists) {
      if (countEl) countEl.textContent = 'none';
      if (errEl) errEl.innerHTML = '';
      listEl.innerHTML = `<p style="font-size:0.72rem; color:var(--sp-text-dim); margin:0;">No <code>${esc(SandpieContext.SKILLS_DIR)}/</code> folder yet.</p>`;
      return;
    }
    if (countEl) countEl.textContent = String(idx.skills.length);
    if (errEl) errEl.innerHTML = (idx.errors || []).map(e => `<div class="sp-skill-err">⚠ ${esc(e)}</div>`).join('');
    listEl.innerHTML = '';
    for (const s of idx.skills) {
      // Skills are ALWAYS active (checkbox removed 2026-09-16) — row is inspect-only.
      const { row, body } = makeRow(null, s.name, s.shared ? 'shared' : '', null);   // skill name only — no description preview; hub-installed skills say so
      const ta = document.createElement('textarea'); ta.className = 'sp-edit'; ta.rows = 12; ta.spellcheck = false; ta.value = 'Loading…'; ta.disabled = true;
      const btns = document.createElement('div'); btns.className = 'sp-item-btns';
      const save = document.createElement('button'); save.type = 'button'; save.className = 'ghost'; save.textContent = 'Save'; save.disabled = true;
      const st = document.createElement('span'); st.className = 'sp-item-status';
      save.addEventListener('click', async () => {
        try { await SandpieContext.saveSkill(s.file, ta.value); st.textContent = 'Saved'; flashMsg('Saved'); renderSkills(panel); }
        catch (_) { st.textContent = 'Save failed'; }
      });
      btns.append(save, st);
      body.append(ta, btns);
      body._onOpen = async () => {
        try { ta.value = await opfs.read(s.file); } catch (_) { ta.value = ''; }
        ta.disabled = false; save.disabled = false;
      };
      listEl.appendChild(row);
    }
  }

  function wire(panel) {
    const ta = panel.querySelector('#sysPromptText');
    const resetBtn = panel.querySelector('#sysPromptReset');
    if (ta) {
      ta.value = _suffix;   // sync best-effort from cache…
      ensureLoaded().then(() => { if (ta && document.activeElement !== ta) ta.value = _suffix; });   // …then exact value from the file
      ta.addEventListener('input', () => { set(ta.value); });   // 'Saved' flashes when the debounced write lands
    }
    if (resetBtn) resetBtn.addEventListener('click', () => { set(''); if (ta) ta.value = ''; flashMsg('Reset to default'); });
    renderTools(panel);
    renderSkills(panel);
    const createBtn = panel.querySelector('#spSkillCreate');
    if (createBtn) createBtn.addEventListener('click', async () => {
      try { if (typeof SandpieContext !== 'undefined' && SandpieContext.scaffold) { await SandpieContext.scaffold(); flashMsg('Created example skill'); renderSkills(panel); } }
      catch (_) { flashMsg('Could not create'); }
    });
  }

  let _retry = 0;
  async function init() {
    forgetLegacyDefault();
    try { await migrate(); } catch (_) {}
    try { await migrateFile(); } catch (_) {}
    ensureLoaded();   // warm the suffix cache
    if (window.Sandpie && Sandpie.events) {
      // Another device (or our own write) changed the file → refresh the cache.
      Sandpie.events.on('file:changed', (p) => {
        if (typeof p === 'string' && p === FILE) {
          const v = _ver;
          readFile().then(s => { if (v === _ver) { _suffix = s; _ready = Promise.resolve(s); } });
        }
      });
    }
    if (window.SandpieSettings) {
      SandpieSettings.register({ id: 'system-prompt', title: 'System', order: 15, render(panel) { panel.innerHTML = HTML; wire(panel); }, onShow(panel) { renderSkills(panel); } });
      return;
    }
    if (_retry++ < 40) setTimeout(init, 500);   // neither host ready yet — retry
  }

  return { get, getAppend, set, isCustom, DEFAULT, init };
})();

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSystemPrompt.init);
else SandpieSystemPrompt.init();
window.SandpieSystemPrompt = SandpieSystemPrompt;
