/**
 * Notifications Module for Sandpie
 *
 * Usage: <script type="module" src="modules/notifications.js"></script>
 */

const SandpieNotifications = (function() {
  'use strict';

  const NOTIF_PREF_KEY = 'sandpie-notify-enabled';

  // DOM references — populated by onRender
  let btnEl = null;
  let statusEl = null;
  let _cfgWired = false;

  // ============================================================
  // PREFERENCE LAYER
  // ============================================================

  function prefEnabled() {
    const c = window.SandpieConfig;
    if (c) { const n = c.get('notifications'); if (n && typeof n.enabled === 'boolean') return n.enabled; }
    return localStorage.getItem(NOTIF_PREF_KEY) !== '0';
  }
  function setPrefEnabled(on) {
    const c = window.SandpieConfig;
    if (c) c.set('notifications', Object.assign({}, c.get('notifications', {}) || {}, { enabled: !!on }));
    else if (on) localStorage.removeItem(NOTIF_PREF_KEY);
    else localStorage.setItem(NOTIF_PREF_KEY, '0');
  }
  // One-time import: preserve an explicit legacy "muted" choice into config.
  // (Default is enabled, so only a stored '0' needs migrating.)
  function importLegacyNotif() {
    const c = window.SandpieConfig; if (!c) return;
    if (c.get('notifications') !== undefined) return;
    if (localStorage.getItem(NOTIF_PREF_KEY) === '0') c.set('notifications', { enabled: false });
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
      setPrefEnabled(!prefEnabled());
    } else if (p === 'default') {
      try { await Notification.requestPermission(); } catch (_) {}
      setPrefEnabled(true);
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
   * Title comes from the generation:complete payload when the emitter knows it
   * (it has just saved the conv, so it's canonical — including a title generated
   * by auto-title.js on this very turn). Otherwise ask conversations.js, which
   * knows both on-disk formats; the direct read of the legacy monolithic conv
   * JSON is the last resort, for pages without that module.
   *
   * @param {string} convId
   * @param {string} [knownTitle]
   */
  async function notifyComplete(convId, knownTitle) {
    if (!effectivelyOn()) return;
    if (!document.hidden) return;
    let title = 'Conversation complete';
    if (knownTitle && String(knownTitle).trim()) title = String(knownTitle).trim();
    else try {
      const getTitle = window.SandpieConversations && SandpieConversations.getTitle;
      const t = getTitle ? await getTitle(convId) : (JSON.parse(await opfs.read(convPath(convId))) || {}).title;
      if (t) title = t;
    } catch (e) {
      console.warn('[sandpie] notify: title read failed:', e);
    }
    const opts = {
      body: title,
      icon: 'icon-192.png',
      tag: 'sandpie-conv-' + convId,
    };
    try {
      const notif = new Notification('sandpie', opts);
      notif.onclick = () => { window.focus(); notif.close(); };
    } catch (e) {
      console.error('[sandpie] notify: Notification constructor threw:', e);
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
      if (p && !p.aborted) notifyComplete(p.convId, p.title);
    });
  }

  const NOTIF_HTML = `
        <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.5rem;">Get a system notification when a conversation finishes.</p>
        <button type="button" class="ghost" id="notifEnableBtn">Enable notifications</button>
        <p id="notifStatus" style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.5rem 0 0;"></p>
      `;
  function wireNotifPanel(bodyEl) {
    btnEl = bodyEl.querySelector('#notifEnableBtn');
    statusEl = bodyEl.querySelector('#notifStatus');
    if (btnEl) btnEl.addEventListener('click', toggle);
    refreshStatus();
  }

  // Prefer the gear modal (SandpieSettings); fall back to the sidebar
  function init() {
    wireEvents();
    if (!_cfgWired && window.SandpieConfig) {
      _cfgWired = true;
      SandpieConfig.ready().then(importLegacyNotif);
      SandpieConfig.subscribe('notifications', refreshStatus);
    }

    if (window.SandpieSettings) {
      SandpieSettings.register({
        id: 'notifications', title: 'Notifications', order: 30,
        render(panel) { panel.innerHTML = NOTIF_HTML; wireNotifPanel(panel); },
      });
      return;
    }
    setTimeout(init, 500);   // neither host ready yet — retry
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
