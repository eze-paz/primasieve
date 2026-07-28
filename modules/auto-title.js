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

  // Token budgets. A title is ~8 tokens, but an in-browser reasoning model
  // (Qwen3, Bonsai) opens with a <think> block and would spend the whole cloud
  // budget in there and return nothing usable — local gets more room, plus a
  // /no_think hint appended to the prompt (honoured by the Qwen3 family, inert
  // text elsewhere).
  const MAXTOK_CLOUD = 24;
  const MAXTOK_LOCAL = 96;
  const CHARS_PER_MSG = 800;   // how much of each opening message the model sees

  const BUILT_IN_PROMPT = [
    'You name chat conversations. You receive the opening of one; reply with a title for it.',
    '',
    'Rules:',
    '- 3 to 6 words. Name the specific topic or task, not the genre ("Centering a div in CSS", never "Coding question" or "User asks about CSS").',
    '- Reply with the title ALONE: no quotes, no trailing period, no markdown, no "Title:" prefix, no explanation.',
    '- Write it in the same language the user wrote in.',
  ].join('\n');

  function isEnabled() { const v = localStorage.getItem(K_ENABLED); return v == null ? DEFAULTS.enabled : v === '1'; }
  function getPrompt() { const v = localStorage.getItem(K_PROMPT); return (v == null || v === '') ? BUILT_IN_PROMPT : v; }
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
  async function generate({ userText = '', assistantText = '', signal } = {}) {
    if (!isEnabled()) return '';
    if (typeof SandpieProviders === 'undefined' || !SandpieProviders.complete) return '';
    const u = String(userText || '').trim().slice(0, CHARS_PER_MSG);
    if (!u) return '';
    const a = String(assistantText || '').trim().slice(0, CHARS_PER_MSG);

    const active = SandpieProviders.getActive ? SandpieProviders.getActive() : null;
    const isLocal = !!active && (active.type === 'litertlm' || active.type === 'webgpu');
    let user = 'User: ' + u + (a ? '\n\nAssistant: ' + a : '');
    if (isLocal) user += '\n\n/no_think';

    const out = await SandpieProviders.complete({
      system: getPrompt(),
      user,
      maxTokens: isLocal ? MAXTOK_LOCAL : MAXTOK_CLOUD,
      signal,
    });
    return clean(out);
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
    if (window.SandpieSettings) { SandpieSettings.register({ id: 'titles', title: 'Conversation titles', order: 18, render(panel) { panel.innerHTML = HTML; wire(panel); } }); return; }
    if (typeof SandpieMenu !== 'undefined') { SandpieMenu.add('autoTitleSection', { title: 'Conversation titles', badge: null, open: false, html: HTML, onRender: wire }); return; }
    if (_retry++ < 40) setTimeout(init, 500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { config, isEnabled, getPrompt, generate, clean, BUILT_IN_PROMPT, init };
})();
window.SandpieAutoTitle = SandpieAutoTitle;
