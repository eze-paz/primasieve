// sandpie/modules/notifications.js — User-completion notifications
//
// Two-layer state: (1) the browser permission (granted/denied/default —
// sandpie can only REQUEST, never revoke; revoking lives in browser
// settings), and (2) a sandpie-local on/off preference stored in
// localStorage so the user can mute completion pings without yanking
// the underlying permission. notifyComplete() is the call site for
// the page's per-conversation completion hook.
//
// Notifications are routed through Service Worker registration's
// showNotification() rather than `new Notification()` because:
//   - Android Chrome silently no-ops `new Notification()` from a page.
//   - iOS Safari only displays notifications when the app is added
//     to the home screen, and only via SW notifications (16.4+).
//   - Desktop also accepts the SW path, so one branch covers all.
// The page-side `new Notification()` fallback stays for environments
// where no SW registration is available (registration in flight,
// blocked by policy, etc).
//
// Click handling lives in the SW's `notificationclick` listener
// (sandpie.js) since SW.showNotification doesn't return a JS object
// the page can attach onclick to.

const SandpieNotifications = (function() {
  'use strict';

  const $ = id => document.getElementById(id);
  const NOTIF_PREF_KEY = 'sandpie-notify-enabled';

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
   * setDot is a global helper defined in sandpie.html; calling it
   * with a missing element id is a safe no-op.
   */
  function refreshStatus() {
    const btn = $('notifEnableBtn');
    const status = $('notifStatus');
    // Status dot mirrors effectivelyOn — lit only when notifications will
    // actually fire (browser permission granted AND local pref on).
    if (typeof setDot === 'function') setDot('notifDot', effectivelyOn() ? 'ok' : null);
    if (!btn || !status) return;
    if (!('Notification' in self)) {
      btn.disabled = true;
      btn.textContent = 'Not supported';
      status.textContent = 'This browser does not support notifications.';
      return;
    }
    const p = Notification.permission;
    if (p === 'denied') {
      btn.disabled = true;
      btn.textContent = 'Blocked by browser';
      status.textContent = 'Notifications are blocked. Re-enable in your browser settings, then come back here.';
      return;
    }
    btn.disabled = false;
    if (p === 'granted' && prefEnabled()) {
      btn.textContent = 'Disable notifications';
      status.textContent = 'You will be notified when conversations finish.';
    } else if (p === 'granted') {
      btn.textContent = 'Enable notifications';
      status.textContent = 'Muted in sandpie. Click to turn back on (no browser prompt needed).';
    } else {
      btn.textContent = 'Enable notifications';
      status.textContent = '';
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

  function init() {
    refreshStatus();
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
