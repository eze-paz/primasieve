/* =============================================================================
   apps-modal.js — Apps launcher modal
   Opens from the rail's "apps" button (and the mobile header's twin).
   pins.js renderHome() paints the pinned-app grid (#pinnedHome) into this
   modal's body instead of the home screen, so #homeCenter stays empty and a
   fresh chat is just an empty chat. Same shell as the Files modal (.files-modal)
   so the two read as one family.
   ============================================================================= */
(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }

  function ensureDom() {
    if (el('appsModal')) return;
    const wrap = document.createElement('div');
    wrap.className = 'files-modal apps-modal';
    wrap.id = 'appsModal';
    wrap.style.display = 'none';
    wrap.innerHTML =
      '<div class="fm-panel">' +
        '<div class="fm-title">' +
          '<span class="material-symbols-outlined" style="font-size:18px; color:var(--sp-text-dim);">apps</span>' +
          '<span class="fm-name">Apps</span>' +
          '<button class="fm-close" title="Close (Esc)">✕</button>' +
        '</div>' +
        '<div class="fm-body" id="appsModalBody"></div>' +
      '</div>';
    document.body.appendChild(wrap);

    wrap.querySelector('.fm-close').onclick = close;
    wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(); });
    // Opening a pinned app (or the +Add tile → Settings) dismisses the launcher.
    // Reorder drags suppress their own click (pins.js), so a drag never closes it.
    wrap.addEventListener('click', (e) => {
      if (e.target.closest && e.target.closest('.pin-tile-btn, .add-tile')) close();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && el('appsModal').style.display !== 'none') close();
    });
  }

  // Host element for pins.js renderHome(). Lazily builds the modal so the grid
  // exists (and stays wired for reorder) before the launcher is first opened.
  function host() { ensureDom(); return el('appsModalBody'); }

  function open() {
    ensureDom();
    el('appsModal').style.display = '';
    try { if (window.SandpiePins && SandpiePins.refreshFromDisk) SandpiePins.refreshFromDisk(); } catch (_) {}
  }
  function close() { const m = el('appsModal'); if (m) m.style.display = 'none'; }

  window.SandpieAppsModal = { open, close, host };
})();
