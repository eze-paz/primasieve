/**
 * Memory module for Sandpie — durable, cross-conversation facts.
 *
 * Modeled on Claude Code's own memory: one fact per `.md` file under
 * sandpie/memory/, fully injected into the system prompt each turn (no lazy
 * fetch, no separate recall tool), kept bounded by an automatic prune/merge
 * pass. This file currently owns only the POLICY surface:
 *   - config (enabled / budget threshold), in localStorage,
 *   - a Settings-modal section to edit it.
 * The store, injection, gated capture, and consolidation land in later passes;
 * they read SandpieMemory.config().
 *
 * Enabled by default — automatic accumulation is the whole value. The threshold
 * is the token budget the injected memory block is kept under; crossing it is
 * what triggers the consolidation/prune pass.
 */
const SandpieMemory = (function () {
  'use strict';

  const K_ENABLED   = 'sandpie-memory-enabled';     // '0' | '1' (unset = default ON)
  const K_THRESHOLD = 'sandpie-memory-threshold';    // integer tokens

  const DEFAULTS = { enabled: true, threshold: 5000 };
  const MIN_THRESHOLD = 500;

  const _int = (key, fallback) => { const v = parseInt(localStorage.getItem(key) || '', 10); return Number.isFinite(v) ? v : fallback; };

  function isEnabled() { const v = localStorage.getItem(K_ENABLED); return v == null ? DEFAULTS.enabled : v === '1'; }
  function threshold() { return Math.max(MIN_THRESHOLD, _int(K_THRESHOLD, DEFAULTS.threshold)); }
  function config() { return { enabled: isEnabled(), threshold: threshold() }; }

  // ---- Settings section -----------------------------------------------------
  const HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">Durable facts are remembered across conversations and injected into the model's context automatically. When the remembered facts grow past the budget below, they're auto-consolidated (merged, pruned, de-duplicated) to stay small. Stored locally in this browser only.</p>
    <label style="display:flex; align-items:center; gap:0.5rem; font-size:0.82rem; margin-bottom:0.6rem;">
      <input type="checkbox" id="memEnabled" style="width:auto;"> Enable automatic memory
    </label>
    <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:0.2rem;">
      <label style="font-size:0.78rem; color:var(--sp-text-dim);">Memory budget
        <input type="number" id="memThreshold" min="500" step="500" style="width:6rem; margin-left:0.3rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.15rem 0.3rem;"> tokens
      </label>
      <span id="memStatus" style="font-size:0.7rem; color:var(--sp-text-dim); align-self:center;"></span>
    </div>`;

  let _flashT = null;
  function flash(msg) { const el = document.getElementById('memStatus'); if (!el) return; el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500); }

  function wire(panel) {
    const cfg = config();
    const en = panel.querySelector('#memEnabled');
    const th = panel.querySelector('#memThreshold');
    if (en) { en.checked = cfg.enabled; en.addEventListener('change', () => { localStorage.setItem(K_ENABLED, en.checked ? '1' : '0'); flash('Saved'); }); }
    if (th) { th.value = cfg.threshold; th.addEventListener('change', () => { const v = Math.max(MIN_THRESHOLD, parseInt(th.value, 10) || DEFAULTS.threshold); th.value = v; localStorage.setItem(K_THRESHOLD, String(v)); flash('Saved'); }); }
  }

  let _retry = 0;
  function init() {
    if (window.SandpieSettings) { SandpieSettings.register({ id: 'memory', title: 'Memory', order: 17, render(panel) { panel.innerHTML = HTML; wire(panel); } }); return; }
    if (typeof SandpieMenu !== 'undefined') { SandpieMenu.add('memorySection', { title: 'Memory', badge: null, open: false, html: HTML, onRender: wire }); return; }
    if (_retry++ < 40) setTimeout(init, 500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { config, isEnabled, threshold, init };
})();
window.SandpieMemory = SandpieMemory;
