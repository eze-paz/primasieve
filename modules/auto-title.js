/**
 * Auto-title module for Sandpie — a real name for every conversation.
 *
 * Without this, a conversation's title is its first user message truncated to 60
 * chars (_deriveTitle in conversations.js), so the sidebar reads as a column of
 * half-sentences. This module turns the opening exchange into a 3-6 word title.
 *
 * Split mirrors the compactor: THIS module owns only the policy —
 *   - config (enabled / prompt), in localStorage,
 *   - the built-in title prompt,
 *   - a Settings-modal section to edit both,
 *   - the single one-shot model call + output sanitizing.
 * conversations.js owns eligibility and persistence (maybeAutoTitle → a
 * `titleLocked` flag in the conversation's .meta.json). It calls
 * SandpieAutoTitle.generate() defensively, so an absent module = no titling.
 * Enabled by default.
 */
const SandpieAutoTitle = (function () {
  'use strict';

  const K_ENABLED = 'sandpie-autotitle-enabled';   // '0' | '1' (unset = default ON)
  const K_PROMPT  = 'sandpie-autotitle-prompt';    // '' = built-in

  const DEFAULTS = { enabled: true };

  // Token budgets. A title is ~8 tokens, but a REASONING model spends tokens
  // thinking first and they are billed against max_tokens — a hybrid cloud model
  // (DeepSeek V4, Qwen3, GLM…) burned a 24-token budget mid-thought and returned
  // a response with no content at all. The primary fix is asking the provider to
  // turn thinking OFF (noReasoning below); these budgets are the backstop for a
  // provider that ignores the request, so they must fit a short think block.
  // In-browser engines also get a /no_think hint, honoured by the Qwen3 family
  // that all of them descend from.
  const MAXTOK_CLOUD = 256;
  const MAXTOK_LOCAL = 192;
  const CHARS_PER_MSG = 800;   // how much of each opening message the model sees

  const BUILT_IN_PROMPT = [
    'You name chat conversations. You receive the opening of one; reply with a title for it.',
    '',
    'Rules:',
    '- 3 to 6 words. Name the specific topic or task, not the genre ("Centering a div in CSS", never "Coding question" or "User asks about CSS").',
    '- Reply with the title ALONE: no quotes, no trailing period, no markdown, no "Title:" prefix, no explanation.',
  ].join('\n');
  // Language line, appended per call: when the user's reply language is one the
  // active model does NOT generate fluently (models.json `fluent` on the managed
  // provider def), the title is authored in English and machine-translated after
  // (a directly-authored title in a non-fluent language comes out garbled —
  // same regime split as the chat itself). Fluent/unknown-language => the old
  // behavior, title in the user's language.
  function _titleLang() {
    try {
      const SL = window.SandpieLanguage;
      const code = String((SL && SL.effective && SL.effective()) || 'en').split(/[-_]/)[0].toLowerCase();
      if (!code || code === 'en') return { line: '- Write it in the same language the user wrote in.', tx: null };
      const p = SandpieProviders.getActive ? SandpieProviders.getActive() : null;
      const fl = (p && Array.isArray(p.fluent)) ? p.fluent.map(c => String(c).split(/[-_]/)[0].toLowerCase()) : null;
      if (fl && fl.includes(code)) return { line: '- Write it in the same language the user wrote in.', tx: null };
      const name = (SL && SL.name && SL.name(code)) || code;
      return { line: '- Write it in English.', tx: { code, name } };
    } catch (_) { return { line: '- Write it in the same language the user wrote in.', tx: null }; }
  }

  // Hardcoded 2026-08-07 (product decision): the Titles settings tab is removed
  // from the UI and the config is fixed for every user — auto-titling is always
  // ON with the built-in prompt. The old localStorage keys (K_ENABLED/K_PROMPT)
  // are deliberately IGNORED: a browser that previously disabled it or saved a
  // custom prompt is re-enrolled onto the default too. Uncommenting the
  // register() call in init() restores the levers.
  function isEnabled() { return DEFAULTS.enabled; }    // always true
  function getPrompt() { return BUILT_IN_PROMPT; }     // always the built-in default
  function config() { return { enabled: isEnabled(), prompt: getPrompt() }; }

  // ---- output sanitizing ----------------------------------------------------
  // Everything a small (or chatty) model does to a one-line answer: thinking
  // blocks, quotes, a "Title:" label, a trailing period, a preamble line. Take
  // the LAST non-empty line — models that ignore "title alone" tend to put the
  // title last. '' means "unusable, keep the derived title".
  const REFUSAL = /^(i (can'?t|cannot|am unable|do not|don'?t)|as an ai|sure[,!]|here('s| is))/i;

  function clean(raw) {
    let t = String(raw || '');
    t = t.replace(/<think>[\s\S]*?<\/think>/gi, '');   // closed reasoning block
    t = t.replace(/<\/?think>[\s\S]*$/i, '');          // budget ran out mid-think
    const lines = t.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (!lines.length) return '';
    t = lines[lines.length - 1];
    t = t.replace(/^(?:title|título|titulo)\s*[:\-—]\s*/i, '');
    t = t.replace(/^["'`“”‘’*_#\s]+|["'`“”‘’*_\s]+$/g, '');
    t = t.replace(/\s+/g, ' ').replace(/[.,;:]+$/, '').trim();
    if (t.length < 2 || REFUSAL.test(t)) return '';
    if (t.length > 60) {                                // clip on a word boundary
      const cut = t.slice(0, 60);
      const sp = cut.lastIndexOf(' ');
      t = (sp > 24 ? cut.slice(0, sp) : cut).trim();
    }
    return t;
  }

  // ---- the model call -------------------------------------------------------
  // One short, non-streaming completion on whatever provider is active (cloud or
  // in-browser) via the shared SandpieProviders.complete(). Returns a clean title
  // or '' — it never throws for a bad/empty answer, only for a transport failure,
  // which the caller treats as "leave the title alone and try again next turn".
  async function generate({ userText = '', assistantText = '', signal, sessionId = null } = {}) {
    if (!isEnabled()) return '';
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return '';
    const u = String(userText || '').trim().slice(0, CHARS_PER_MSG);
    if (!u) return '';
    const a = String(assistantText || '').trim().slice(0, CHARS_PER_MSG);

    const active = SandpieProviders.getActive ? SandpieProviders.getActive() : null;
    const isLocal = false;  // local-LLM engines removed
    let user = 'User: ' + u + (a ? '\n\nAssistant: ' + a : '');
    if (isLocal) user += '\n\n/no_think';

    const lang = _titleLang();
    const out = await SandpieProviders.complete({
      system: getPrompt() + '\n' + lang.line,
      user,
      maxTokens: isLocal ? MAXTOK_LOCAL : MAXTOK_CLOUD,
      noReasoning: true,
      signal,
      sessionId,   // inherit parent session so /admin/transcripts groups the retitle op
    });
    let title = clean(out);
    // Don't fail silently: a model that answered but whose answer was unusable is
    // indistinguishable from "no provider" at the call site otherwise.
    if (!title && out && out.trim()) console.warn('[sandpie] auto-title: unusable answer, keeping the derived title:', JSON.stringify(out.slice(0, 200)));
    // Non-fluent reply language: the title was authored in English — translate it
    // through the shared localizer (display-cached). Fail-open to the English title.
    if (title && lang.tx && window.__locCache && window.__locCache.localize) {
      try {
        const [tr] = await window.__locCache.localize([title], lang.tx.code, lang.tx.name);
        if (typeof tr === 'string' && tr.trim()) title = tr.trim();
      } catch (_) {}
    }
    return title;
  }

  // ---- landing animation ----------------------------------------------------
  // The row pulses accent (CSS: li.conv-retitled) while the new name types itself
  // in. Called by conversations.js from buildConvLi, on the freshly rebuilt <li>
  // — refreshConversationList() replaces the whole list, so there is no old row
  // left to animate. Pure presentation: it owns no state and is safe to no-op.
  //
  // Typing writes textContent on the existing .name span, so nowrap/ellipsis
  // behave exactly as they do normally. Fire-and-forget; the row already carries
  // the final title before this runs, so any interruption (another list rebuild
  // mid-typing) just leaves the correct text on screen.
  const MS_PER_CHAR = 20;      // ~25-char title ≈ 500ms, inside the 900ms pulse
  const CARET_HOLD  = 90;      // caret lingers a beat after the last character
  const PULSE_MS    = 900;     // must match conv-retitle-pulse in sandpie.css

  function animateRetitle(li, nameEl, newTitle) {
    if (!li || !nameEl) return;
    const text = String(newTitle == null ? nameEl.textContent : newTitle);
    const snap = () => { nameEl.textContent = text; nameEl.classList.remove('conv-typing'); li.classList.remove('conv-retitled'); };

    let reduced = false;
    try { reduced = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) {}
    // A hidden tab is the common case here (titles land as a turn finishes, which
    // is exactly when the user has switched away) and it must NOT animate: a
    // background tab clamps setTimeout to ~1s, so the title would type at one
    // character per second, and CSS animations don't advance at all, so the pulse
    // class would never see its animationend. Skip straight to the final title.
    if (reduced || document.hidden) { snap(); return; }

    li.classList.add('conv-retitled');
    // animationend is the normal cleanup, but it only fires if the animation
    // actually ran — a row left with .conv-retitled keeps an accent tint forever,
    // so back it with a timer sized to the keyframes (900ms) plus slack.
    const kill = setTimeout(() => li.classList.remove('conv-retitled'), PULSE_MS + 300);
    li.addEventListener('animationend', function done(e) {
      if (e.target !== li) return;                  // ignore the .name/caret animations
      clearTimeout(kill);
      li.classList.remove('conv-retitled');
      li.removeEventListener('animationend', done);
    });

    nameEl.classList.add('conv-typing');
    nameEl.textContent = '';
    let i = 0;
    const onHide = () => { if (document.hidden) { document.removeEventListener('visibilitychange', onHide); i = text.length; snap(); } };
    document.addEventListener('visibilitychange', onHide);
    const tick = () => {
      // Stop if the list was rebuilt under us — the new row already has the full
      // title, so there is nothing to finish. Same for a tab hidden mid-typing
      // (onHide already snapped the text): drop the timer chain.
      if (!nameEl.isConnected || i >= text.length) { document.removeEventListener('visibilitychange', onHide); return; }
      nameEl.textContent = text.slice(0, ++i);
      if (i < text.length) { setTimeout(tick, MS_PER_CHAR); return; }
      document.removeEventListener('visibilitychange', onHide);
      setTimeout(() => nameEl.classList.remove('conv-typing'), CARET_HOLD);
    };
    setTimeout(tick, MS_PER_CHAR);
  }

  // ---- Settings section -----------------------------------------------------
  const HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">After a conversation's first exchange, the model is asked for a short title for it — so the sidebar lists topics instead of truncated first messages. One tiny extra request per conversation, never repeated. A title you set yourself is never overwritten. Stored locally in this browser only.</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.6rem;">
      <input type="checkbox" id="atEnabled" style="width:auto;"> Name new conversations automatically
    </label>

    <div class="sp-block">
      <div class="sp-block-head">Title prompt</div>
      <p class="sp-block-hint">The instruction sent to the model. It sees only the first user message and the first reply.</p>
      <textarea id="atPrompt" rows="7" spellcheck="false" style="width:100%; resize:vertical; padding:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font:0.8rem 'JetBrains Mono', Consolas, monospace; line-height:1.45;"></textarea>
      <div style="display:flex; align-items:center; gap:0.6rem; margin-top:0.4rem;">
        <span id="atStatus" style="font-size:0.7rem; color:var(--sp-text-dim); flex:1;"></span>
        <button type="button" class="ghost" id="atPromptReset" style="font-size:0.72rem; padding:0.2rem 0.55rem;">Reset prompt to default</button>
      </div>
      <p style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.5rem 0 0;">Retitle a conversation on demand with <code>&gt;&gt;&gt; retitle</code>.</p>
    </div>`;

  let _flashT = null;
  function flash(msg) { const el = document.getElementById('atStatus'); if (!el) return; el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500); }

  function wire(panel) {
    const en = panel.querySelector('#atEnabled');
    const prompt = panel.querySelector('#atPrompt');
    const reset = panel.querySelector('#atPromptReset');
    if (en) { en.checked = isEnabled(); en.addEventListener('change', () => { localStorage.setItem(K_ENABLED, en.checked ? '1' : '0'); flash('Saved'); }); }
    if (prompt) { prompt.value = getPrompt(); prompt.addEventListener('input', () => { const v = prompt.value; if (v.trim() === '' || v === BUILT_IN_PROMPT) localStorage.removeItem(K_PROMPT); else localStorage.setItem(K_PROMPT, v); flash('Saved'); }); }
    if (reset) reset.addEventListener('click', () => { localStorage.removeItem(K_PROMPT); if (prompt) prompt.value = BUILT_IN_PROMPT; flash('Reset to default'); });
  }

  let _retry = 0;
  function init() {
    // Titles settings tab commented out 2026-08-07 (product decision): the
    // enabled/prompt levers are removed from the UI and the config is hardcoded
    // (see isEnabled/getPrompt above). HTML/wire are kept intact below so this
    // tab can be restored by uncommenting the register() line.
    // if (window.SandpieSettings) { SandpieSettings.register({ id: 'titles', title: 'Titles', order: 18, render(panel) { panel.innerHTML = HTML; wire(panel); } }); return; }
    // if (typeof SandpieMenu !== 'undefined') { SandpieMenu.add('autoTitleSection', { title: 'Titles', badge: null, open: false, html: HTML, onRender: wire }); return; }
    // if (_retry++ < 40) setTimeout(init, 500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { config, isEnabled, getPrompt, generate, clean, animateRetitle, BUILT_IN_PROMPT, init };
})();
window.SandpieAutoTitle = SandpieAutoTitle;
