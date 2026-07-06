/**
 * Compactor module for Sandpie — first-class, harness-native conversation compaction.
 *
 * The compaction ENGINE lives in conversations.js (non-destructive {boundary,
 * summary} state, collapse-behind-a-toggle rendering, buildAgentConfig shipping
 * [summary, …tail] at send time). THIS module owns only the policy around it:
 *   - config (enabled / threshold / keep-tail / model / prompt), in localStorage,
 *   - the built-in summarization prompt,
 *   - a Settings-modal section to edit all of the above,
 *   - one-time migration off the old opt-in `sandpie/agents/compactor.md` agent.
 *
 * conversations.js reads SandpieCompactor.config() and drives the actual
 * summarize-then-compact on the pre-send path (maybeAutoCompact). Enabled by
 * default so long chats "just work" without setup.
 */
const SandpieCompactor = (function () {
  'use strict';

  const K_ENABLED  = 'sandpie-compactor-enabled';    // '0' | '1' (unset = default ON)
  const K_PCT      = 'sandpie-compactor-pct';         // integer %
  const K_KEEPTAIL = 'sandpie-compactor-keeptail';    // integer messages
  const K_PROMPT   = 'sandpie-compactor-prompt';       // '' = built-in
  const MIGRATED   = 'sandpie-compactor-migrated';     // one-time flag

  const DEFAULTS = { enabled: true, pct: 80, keepTail: 10 };

  const BUILT_IN_PROMPT = [
    "You are sandpie's conversation compactor. You receive the EARLIER part of an ongoing chat — the most recent turns are kept verbatim and are NOT shown to you. Produce a dense briefing that REPLACES those earlier turns in the live context, so the conversation can continue indefinitely without losing the thread.",
    "",
    "Preserve, compactly:",
    "- The original goal/task and any stated constraints or requirements.",
    "- Decisions made and why; conclusions reached.",
    "- Key facts, names, file paths, commands, IDs, and values referenced.",
    "- Open threads — what is still in progress or unresolved.",
    "- The user's stated preferences and any corrections they gave.",
    "",
    "Drop greetings, small talk, and anything already superseded. Write a tight briefing (headings or bullets are fine) for a future reader with NO access to the omitted turns. Do not invent anything. Output ONLY the summary text — no preamble, no JSON.",
  ].join('\n');

  const _int = (key, fallback) => { const v = parseInt(localStorage.getItem(key) || '', 10); return Number.isFinite(v) ? v : fallback; };

  function isEnabled() { const v = localStorage.getItem(K_ENABLED); return v == null ? DEFAULTS.enabled : v === '1'; }
  function getPrompt() { const v = localStorage.getItem(K_PROMPT); return (v == null || v === '') ? BUILT_IN_PROMPT : v; }
  function config() {
    return {
      enabled: isEnabled(),
      pct: Math.min(99, Math.max(1, _int(K_PCT, DEFAULTS.pct))),
      keepTail: Math.max(2, _int(K_KEEPTAIL, DEFAULTS.keepTail)),
      model: '',
      prompt: getPrompt(),
    };
  }

  // ---- one-time migration off the old agents/compactor.md -------------------
  // Preserve anyone who had customized or enabled the old agent: pull its config
  // + prompt into localStorage, then delete the file locally AND from Dropbox.
  const FM_RE = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/;
  async function migrate() {
    if (localStorage.getItem(MIGRATED) === '1') return;
    if (typeof opfs === 'undefined') return;
    const path = 'sandpie/agents/compactor.md';
    try {
      let text = null;
      try { text = await opfs.read(path); } catch (_) {}
      if (text) {
        const m = FM_RE.exec(text);
        if (m) {
          const fm = {};
          for (const line of m[1].split(/\r?\n/)) {
            const kv = /^([A-Za-z][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*)$/.exec(line);
            if (kv) { let v = kv[2].trim(); if ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'"))) v = v.slice(1, -1); fm[kv[1].toLowerCase()] = v; }
          }
          // Only seed a key the user hasn't already set natively.
          if (localStorage.getItem(K_ENABLED) == null && fm.enabled != null)
            localStorage.setItem(K_ENABLED, /^(true|yes|on|1)$/i.test(fm.enabled) ? '1' : '0');
          if (localStorage.getItem(K_PCT) == null && fm.at_context_pct != null)
            localStorage.setItem(K_PCT, String(parseInt(fm.at_context_pct, 10) || DEFAULTS.pct));
          if (localStorage.getItem(K_KEEPTAIL) == null && fm.keep_tail != null)
            localStorage.setItem(K_KEEPTAIL, String(parseInt(fm.keep_tail, 10) || DEFAULTS.keepTail));
          const body = text.replace(FM_RE, '').trim();
          if (localStorage.getItem(K_PROMPT) == null && body && body !== BUILT_IN_PROMPT) localStorage.setItem(K_PROMPT, body);
        }
        let existed = false; try { existed = await opfs.exists(path); } catch (_) {}
        try { await opfs.remove(path); } catch (_) {}
        if (existed && window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', path);
      }
      localStorage.setItem(MIGRATED, '1');
    } catch (_) { /* leave flag unset → retry next load */ }
  }

  // ---- Settings section -----------------------------------------------------
  const HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">When a conversation grows past the threshold, the earlier turns are auto-summarized into a briefing that replaces them in the model's context — the full history stays visible in the chat. Stored locally in this browser only.</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.6rem;">
      <input type="checkbox" id="cmpEnabled" style="width:auto;"> Enable automatic compaction
    </label>
    <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:0.6rem;">
      <label style="font-size:0.78rem; color:var(--sp-text-dim);">Trigger at
        <input type="number" id="cmpPct" min="1" max="99" style="width:4rem; margin-left:0.3rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.15rem 0.3rem;"> % of context
      </label>
      <label style="font-size:0.78rem; color:var(--sp-text-dim);">Keep last
        <input type="number" id="cmpKeep" min="2" max="100" style="width:4rem; margin-left:0.3rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.15rem 0.3rem;"> messages
      </label>
    </div>

    <div class="sp-block">
      <div class="sp-block-head">Compaction prompt</div>
      <p class="sp-block-hint">The instruction sent to the model to produce each briefing.</p>
      <textarea id="cmpPrompt" rows="10" spellcheck="false" style="width:100%; resize:vertical; padding:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font:0.8rem 'JetBrains Mono', Consolas, monospace; line-height:1.45;"></textarea>
      <div style="display:flex; align-items:center; gap:0.6rem; margin-top:0.4rem;">
        <span id="cmpStatus" style="font-size:0.7rem; color:var(--sp-text-dim); flex:1;"></span>
        <button type="button" class="ghost" id="cmpPromptReset" style="font-size:0.72rem; padding:0.2rem 0.55rem;">Reset prompt to default</button>
      </div>
    </div>`;

  let _flashT = null;
  function flash(msg) { const el = document.getElementById('cmpStatus'); if (!el) return; el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500); }

  function wire(panel) {
    const cfg = config();
    const en = panel.querySelector('#cmpEnabled');
    const pct = panel.querySelector('#cmpPct');
    const keep = panel.querySelector('#cmpKeep');

    const prompt = panel.querySelector('#cmpPrompt');
    const reset = panel.querySelector('#cmpPromptReset');
    if (en) { en.checked = cfg.enabled; en.addEventListener('change', () => { localStorage.setItem(K_ENABLED, en.checked ? '1' : '0'); flash('Saved'); }); }
    if (pct) { pct.value = cfg.pct; pct.addEventListener('change', () => { const v = Math.min(99, Math.max(1, parseInt(pct.value, 10) || DEFAULTS.pct)); pct.value = v; localStorage.setItem(K_PCT, String(v)); flash('Saved'); }); }
    if (keep) { keep.value = cfg.keepTail; keep.addEventListener('change', () => { const v = Math.max(2, parseInt(keep.value, 10) || DEFAULTS.keepTail); keep.value = v; localStorage.setItem(K_KEEPTAIL, String(v)); flash('Saved'); }); }

    if (prompt) { prompt.value = getPrompt(); prompt.addEventListener('input', () => { const v = prompt.value; if (v.trim() === '' || v === BUILT_IN_PROMPT) localStorage.removeItem(K_PROMPT); else localStorage.setItem(K_PROMPT, v); flash('Saved'); }); }
    if (reset) reset.addEventListener('click', () => { localStorage.removeItem(K_PROMPT); if (prompt) prompt.value = BUILT_IN_PROMPT; flash('Reset to default'); });
  }

  let _retry = 0;
  function init() {
    migrate();
    if (window.SandpieSettings) { SandpieSettings.register({ id: 'compaction', title: 'Compaction', order: 16, render(panel) { panel.innerHTML = HTML; wire(panel); } }); return; }
    if (typeof SandpieMenu !== 'undefined') { SandpieMenu.add('compactionSection', { title: 'Compaction', badge: null, open: false, html: HTML, onRender: wire }); return; }
    if (_retry++ < 40) setTimeout(init, 500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { config, isEnabled, getPrompt, BUILT_IN_PROMPT, migrate, init };
})();
window.SandpieCompactor = SandpieCompactor;
