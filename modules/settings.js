// sandpie /modules/settings.js — SandpieSettings: the gear/settings surface.
//
// A registry + modal for set-once-and-forget configuration, so modules stop
// crowding the sidebar (SandpieMenu) with things the user touches rarely. A
// module calls SandpieSettings.register({ id, title, order, render }) and gets a
// panel in the gear modal. The sidebar stays for runtime, per-conversation
// things (conversations, files, agents, context, console).
//
// Mirrors the SandpieMenu contract: render(panel) receives a `.service-body`
// element — the same shape as SandpieMenu's onRender(body) — so a module's
// existing panel code works unchanged. Panels render lazily, the first time
// they're shown.
//
// Pure UI: it knows nothing about storage. Panels read/write via SandpieConfig.
// Optional, like every sandpie module: if settings.js isn't loaded, modules fall
// back to registering in the sidebar instead.
//
// CLASSIC script (global window.SandpieSettings). Load after core.js.

const SandpieSettings = (() => {
  const items = new Map();   // id -> { id, title, order, render, panel, navBtn, rendered }
  let _active = null;

  const modalEl  = () => document.getElementById('settingsModal');
  const navEl    = () => document.getElementById('settingsNav');
  const panelsEl = () => document.getElementById('settingsPanels');

  function byOrder(a, b) { return (a.order - b.order) || a.title.localeCompare(b.title); }
  function firstId() { const s = [...items.values()].sort(byOrder)[0]; return s ? s.id : null; }

  // register({ id, title, order=100, render }) — render(panelEl) populates the
  // panel (called once, lazily, when first shown).
  function register(opts) {
    const o = opts || {};
    if (!o.id || items.has(o.id)) return false;
    items.set(o.id, {
      id: o.id, title: o.title || o.id,
      order: (o.order == null ? 100 : o.order),
      render: o.render, onShow: o.onShow, panel: null, navBtn: null, rendered: false,
    });
    if (navEl()) buildNav();   // modal already in the DOM — refresh nav
    return true;
  }

  function buildNav() {
    const nav = navEl(), panels = panelsEl();
    if (!nav || !panels) return;
    nav.innerHTML = ''; panels.innerHTML = '';
    for (const it of [...items.values()].sort(byOrder)) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ghost';
      btn.textContent = it.title;
      btn.style.cssText = 'text-align:left; font-size:0.85rem; padding:0.4rem 0.55rem; border-radius:6px; background:transparent;';
      btn.onclick = () => activate(it.id);
      nav.appendChild(btn);
      it.navBtn = btn;

      const panel = document.createElement('div');
      panel.className = 'service-body';
      panel.style.display = 'none';
      panels.appendChild(panel);
      it.panel = panel;
      it.rendered = false;
    }
    if (!items.has(_active)) _active = firstId();
  }

  function activate(id) {
    const it = items.get(id);
    if (!it) return;
    _active = id;
    for (const other of items.values()) {
      const on = (other === it);
      if (other.panel)  other.panel.style.display = on ? '' : 'none';
      if (other.navBtn) other.navBtn.style.background = on ? 'var(--sp-panel)' : 'transparent';
    }
    if (!it.rendered && typeof it.render === 'function') {
      it.rendered = true;
      try { it.render(it.panel); } catch (e) { console.warn('[SandpieSettings] render failed:', id, e); }
    }
    // onShow runs on EVERY activation (not just first render) so panels with
    // file-derived content (e.g. the skills list) refresh when re-opened.
    if (typeof it.onShow === 'function') {
      try { it.onShow(it.panel); } catch (e) { console.warn('[SandpieSettings] onShow failed:', id, e); }
    }
  }

  function open(id) {
    const m = modalEl(); if (!m) return;
    const nav = navEl();
    if (nav && !nav.childElementCount) buildNav();
    const target = id || _active || firstId();
    if (target) activate(target);
    m.style.display = 'flex';
  }
  function close() { const m = modalEl(); if (m) m.style.display = 'none'; }
  function isOpen() { const m = modalEl(); return !!m && m.style.display !== 'none'; }

  function boot() {
    buildNav();
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen()) close(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  return { register, open, close, activate, isOpen, list: () => [...items.keys()] };
})();
window.SandpieSettings = SandpieSettings;
