/**
 * System Prompt module for Sandpie
 *
 * The chat system prompt is an editable value cached in localStorage — NOT a
 * synced or browsable OPFS file. This replaces the old OPFS `sandpie_memory.md`
 * (which showed in the file browser and synced to Dropbox).
 *
 * - SandpieSystemPrompt.get() is read by conversations.js buildSystemPrompt().
 * - Registers a "System prompt" section in the Settings modal (gear), with a
 *   sidebar (SandpieMenu) fallback.
 * - One-time migration: pull any existing sandpie_memory.md into the local
 *   prompt, then delete that file locally AND from Dropbox.
 */
const SandpieSystemPrompt = (function () {
  'use strict';

  const KEY = 'sandpie-system-prompt';
  const MIGRATED_KEY = 'sandpie-sysprompt-migrated';
  const DEFAULT = 'You are a helpful assistant that reasons through the users requests step-by-step.';

  function get() { const v = localStorage.getItem(KEY); return (v == null || v === '') ? DEFAULT : v; }
  function set(v) { if (v == null || String(v).trim() === '') localStorage.removeItem(KEY); else localStorage.setItem(KEY, String(v)); }
  function isCustom() { const v = localStorage.getItem(KEY); return v != null && v !== '' && v !== DEFAULT; }

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

  const HTML = `
        <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.5rem;">Sets the assistant's behavior for every conversation. Stored locally in this browser only — not synced and not saved as a file.</p>
        <textarea id="sysPromptText" rows="10" spellcheck="false" placeholder="You are a helpful assistant…" style="width:100%; resize:vertical; padding:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font:0.82rem 'JetBrains Mono', Consolas, monospace; line-height:1.45;"></textarea>
        <div style="display:flex; align-items:center; gap:0.6rem; margin-top:0.4rem;">
          <span id="sysPromptStatus" style="font-size:0.7rem; color:var(--sp-text-dim); flex:1; min-width:0;"></span>
          <button type="button" class="ghost" id="sysPromptReset" style="font-size:0.72rem; padding:0.2rem 0.55rem;">Reset to default</button>
        </div>
      `;

  function wire(panel) {
    const ta = panel.querySelector('#sysPromptText');
    const statusEl = panel.querySelector('#sysPromptStatus');
    const resetBtn = panel.querySelector('#sysPromptReset');
    if (!ta) return;
    ta.value = get();
    let t = null;
    const flash = (msg) => { if (!statusEl) return; statusEl.textContent = msg; clearTimeout(t); t = setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 1500); };
    ta.addEventListener('input', () => { set(ta.value); flash('Saved'); });
    if (resetBtn) resetBtn.addEventListener('click', () => { set(''); ta.value = get(); flash('Reset to default'); });
  }

  let _retry = 0;
  function init() {
    migrate();
    if (window.SandpieSettings) {
      SandpieSettings.register({ id: 'system-prompt', title: 'System prompt', order: 15, render(panel) { panel.innerHTML = HTML; wire(panel); } });
      return;
    }
    if (typeof SandpieMenu !== 'undefined') {
      SandpieMenu.add('systemPromptSection', { title: 'System prompt', badge: null, open: false, html: HTML, onRender: wire });
      return;
    }
    if (_retry++ < 40) setTimeout(init, 500);   // neither host ready yet — retry
  }

  return { get, set, isCustom, init };
})();

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSystemPrompt.init);
else SandpieSystemPrompt.init();
window.SandpieSystemPrompt = SandpieSystemPrompt;
