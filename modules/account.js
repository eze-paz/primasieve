// sandpie /modules/account.js — optional company sign-in (progressive enhancement).
//
// Anonymous-first: sandpie is fully usable signed-out. When a sandpie-server
// backend is present, this adds an "Account" panel (Sign in / Sign out) to the
// gear modal and, once signed in, surfaces the company SSO **as a read-only AI
// provider** — a server-side wrapper that holds the real LLM key. Nothing here
// is persisted: the managed provider is injected into SandpieProviders in memory
// and removed on sign-out, so the user's own settings/config file are never
// touched.
//
// No backend (static / Dropbox / file:// deploy, or /auth/* missing) → this
// module is a silent no-op: no panel, no chip, no behaviour change.
//
// CLASSIC script (global window.SandpieAccount). Load after settings.js + providers.js.

const SandpieAccount = (() => {
  let _user = null;
  let _panel = null;
  let _registered = false;
  let _refreshTimer = null;

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c])); }
  function initials(s) {
    const parts = String(s || '').trim().split(/[\s.@_-]+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return String(s || '?').slice(0, 2).toUpperCase();
  }

  async function getJSON(url) {
    const r = await fetch(url, { credentials: 'same-origin' });
    let data = null;
    if (r.ok) { try { data = await r.json(); } catch (_) {} }
    return { ok: r.ok, status: r.status, data };
  }

  // Probe the backend. Only a real auth response (200 signed-in / 401 signed-out)
  // lights up the Account UI; anything else (404, error) means no backend → no-op.
  async function init() {
    let me;
    try { me = await getJSON('/auth/me'); }
    catch (_) { return; }                  // server unreachable → stay anonymous, no UI
    if (me.ok && me.data) {                // signed in
      _user = me.data;
      registerPanel();
      onSignedIn();
    } else if (me.status === 401) {        // backend present, signed out
      registerPanel();
      paint();
    }
    // 404 / other → no auth backend → no-op
  }

  async function onSignedIn() {
    paint();
    await refreshManagedProvider();
    clearInterval(_refreshTimer);
    _refreshTimer = setInterval(refreshManagedProvider, 30 * 60 * 1000);   // keep the session token fresh
  }

  // Pull the session token and surface the company SSO as a read-only provider.
  // Re-callable: SandpieProviders.setManaged re-applies the (refreshed) token.
  async function refreshManagedProvider() {
    let tok;
    try { tok = await getJSON('/auth/token'); } catch (_) { return; }
    if (!tok.ok || !tok.data || !tok.data.token) return;
    if (window.SandpieProviders && SandpieProviders.setManaged) {
      SandpieProviders.setManaged({
        name: 'Company AI',
        endpoint: location.origin,   // → the server's /chat/completions (it injects the real key + model)
        model: '(managed)',
        apiKey: tok.data.token,      // the session token is the "key" — server-verified
        proxyUrl: '',
      });
    }
  }

  function login()  { window.location.href = '/auth/login'; }
  function logout() {
    try { if (window.SandpieProviders && SandpieProviders.clearManaged) SandpieProviders.clearManaged(); } catch (_) {}
    window.location.href = '/auth/logout';
  }

  // ---- Account panel (gear modal) ----
  function registerPanel() {
    if (_registered || !window.SandpieSettings) return;
    _registered = true;
    SandpieSettings.register({ id: 'account', title: 'Account', order: 5, render(panel) { _panel = panel; paint(); } });
  }

  function paint() {
    if (!_panel) return;
    if (_user) {
      const name = _user.name || _user.email || 'Signed in';
      _panel.innerHTML =
        '<div style="display:flex; align-items:center; gap:0.6rem;">' +
          '<div style="width:38px;height:38px;border-radius:50%;background:var(--sp-accent-dim);display:flex;align-items:center;justify-content:center;font-weight:600;font-size:0.85rem;">' + esc(initials(name)) + '</div>' +
          '<div style="display:flex;flex-direction:column;min-width:0;">' +
            '<span style="font-size:0.9rem;">' + esc(name) + '</span>' +
            '<span style="font-size:0.72rem;color:var(--sp-text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(_user.email || '') + '</span>' +
          '</div>' +
        '</div>' +
        '<button class="ghost" id="spLogoutBtn" style="margin-top:0.9rem;">Sign out</button>';
      _panel.querySelector('#spLogoutBtn')?.addEventListener('click', logout);
    } else {
      _panel.innerHTML =
        '<p style="font-size:0.8rem;color:var(--sp-text-dim);margin:0 0 0.7rem;">Sign in with your company account to use the managed AI provider. Signing in is optional — sandpie works anonymously with your own providers.</p>' +
        '<button class="ghost" id="spLoginBtn">Sign in</button>';
      _panel.querySelector('#spLoginBtn')?.addEventListener('click', login);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { login, logout, isActive: () => !!_user, current: () => _user };
})();
window.SandpieAccount = SandpieAccount;
