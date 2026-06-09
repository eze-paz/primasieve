/**
 * Notifications Module for Sandpie
 *
 * Registers a "Notifications" section in the sidebar via SandpieMenu.
 * Usage: <script type="module" src="modules/notifications.js"></script>
 */

const SandpieNotifications = (function() {
  'use strict';

  const NOTIF_PREF_KEY = 'sandpie-notify-enabled';

  // DOM references — populated by onRender
  let btnEl = null;
  let statusEl = null;

  // ============================================================
  // PREFERENCE LAYER
  // ============================================================

  function prefEnabled() {
    return localStorage.getItem(NOTIF_PREF_KEY) !== '0';
  }

  /**
   * Effective on/off — both the browser permission and the local
   * preference must be on for notifications to fire.
   */
  function effectivelyOn() {
    return 'Notification' in self
      && Notification.permission === 'granted'
      && prefEnabled();
  }

  // ============================================================
  // SIDEBAR UI
  // ============================================================

  /**
   * Reflect the current permission + preference into the sidebar
   * button label, disabled state, helper text, and summary status dot.
   */
  function refreshStatus() {
    // Status dot mirrors effectivelyOn — lit only when notifications will
    // actually fire (browser permission granted AND local pref on).
    const _notifDot = document.getElementById('notifDot');
    if (_notifDot) { _notifDot.classList.remove('ok', 'warn', 'err'); if (effectivelyOn()) _notifDot.classList.add('ok'); }
    if (!btnEl || !statusEl) return;
    if (!('Notification' in self)) {
      btnEl.disabled = true;
      btnEl.textContent = 'Not supported';
      statusEl.textContent = 'This browser does not support notifications.';
      return;
    }
    const p = Notification.permission;
    if (p === 'denied') {
      btnEl.disabled = true;
      btnEl.textContent = 'Blocked by browser';
      statusEl.textContent = 'Notifications are blocked. Re-enable in your browser settings, then come back here.';
      return;
    }
    btnEl.disabled = false;
    if (p === 'granted' && prefEnabled()) {
      btnEl.textContent = 'Disable notifications';
      statusEl.textContent = 'You will be notified when conversations finish.';
    } else if (p === 'granted') {
      btnEl.textContent = 'Enable notifications';
      statusEl.textContent = 'Muted in sandpie. Click to turn back on (no browser prompt needed).';
    } else {
      btnEl.textContent = 'Enable notifications';
      statusEl.textContent = '';
    }
  }

  /**
   * Sidebar button click handler. On first click (permission === default)
   * the browser prompt is shown; on subsequent clicks with a granted
   * permission, the local pref is flipped — no re-prompt.
   */
  async function toggle() {
    if (!('Notification' in self)) return;
    const p = Notification.permission;
    if (p === 'granted') {
      // Already authorised by the browser — just flip the sandpie-local pref.
      if (prefEnabled()) localStorage.setItem(NOTIF_PREF_KEY, '0');
      else localStorage.removeItem(NOTIF_PREF_KEY);
    } else if (p === 'default') {
      try { await Notification.requestPermission(); } catch (_) {}
      localStorage.removeItem(NOTIF_PREF_KEY);
    }
    // 'denied' is unreachable — the button is disabled in that branch.
    refreshStatus();
  }

  // ============================================================
  // FIRING
  // ============================================================

  /**
   * Fire a completion notification for the given conversation.
   * No-op if notifications are disabled (either layer off), if the API
   * isn't available, or if the page is currently visible (the user is
   * already looking at sandpie — they don't need a system toast for
   * something happening on screen in front of them).
   *
   * Reads the canonical title from the conv JSON (so renames are
   * reflected) — the caller must have just saved the conv.
   *
   * @param {string} convId
   */
  async function notifyComplete(convId) {
    if (!effectivelyOn()) return;
    if (!document.hidden) return;
    let title = 'Conversation complete';
    try {
      // Pull canonical title from the just-saved conv JSON.
      const data = JSON.parse(await opfs.read(convPath(convId)));
      if (data && data.title) title = data.title;
    } catch (e) {
      console.warn('[sandpie] notify: title read failed:', e);
    }
    const opts = {
      body: title,
      icon: 'icon-192.png',
      tag: 'sandpie-conv-' + convId,
    };
    // Prefer SW.showNotification — only path that works on mobile.
    let shown = false;
    try {
      const reg = navigator.serviceWorker
        && await navigator.serviceWorker.getRegistration();
      if (reg && reg.showNotification) {
        await reg.showNotification('sandpie', opts);
        shown = true;
      }
    } catch (e) {
      console.error('[sandpie] notify: SW showNotification threw:', e);
    }
    // Desktop fallback for environments without an SW registration.
    if (!shown) {
      try {
        const notif = new Notification('sandpie', opts);
        notif.onclick = () => { window.focus(); notif.close(); };
      } catch (e) {
        console.error('[sandpie] notify: Notification constructor threw:', e);
      }
    }
  }

  // ============================================================
  // INIT
  // ============================================================

  // Decoupling: the page announces completion via the Sandpie event bus instead
  // of calling us directly, so this module is an optional LISTENER — absent
  // module ⇒ no subscriber ⇒ the page's emit is a silent no-op. Idempotent and
  // guarded so it's safe on pages without a Sandpie host. notifyComplete stays
  // exported for sandpie.html / variants that still invoke it directly.
  let _wired = false;
  function wireEvents() {
    if (_wired || !(window.Sandpie && window.Sandpie.events)) return;
    _wired = true;
    Sandpie.events.on('generation:complete', (p) => {
      if (p && !p.aborted) notifyComplete(p.convId);
    });
  }

  function init() {
    wireEvents();
    if (typeof SandpieMenu === 'undefined') {
      console.warn('Notifications module: SandpieMenu not found, retrying in 500ms...');
      setTimeout(init, 500);
      return;
    }

    SandpieMenu.add('notificationsSection', {
      title: 'Notifications',
      dot: 'notifDot',
      badge: null,
      open: false,
      html: `
        <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.5rem;">Get a system notification when a conversation finishes.</p>
        <button type="button" class="ghost" id="notifEnableBtn">Enable notifications</button>
        <p id="notifStatus" style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.5rem 0 0;"></p>
      `,
      onRender(bodyEl) {
        btnEl = bodyEl.querySelector('#notifEnableBtn');
        statusEl = bodyEl.querySelector('#notifStatus');
        if (btnEl) btnEl.addEventListener('click', toggle);
        refreshStatus();
      }
    });

    console.log('Notifications module registered');
  }

  return {
    effectivelyOn,
    refreshStatus,
    toggle,
    notifyComplete,
    init,
  };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', SandpieNotifications.init);
} else {
  SandpieNotifications.init();
}
