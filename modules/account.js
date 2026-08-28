// sandpie /modules/account.js — optional company sign-in (progressive enhancement).
//
// Anonymous-first: sandpie is fully usable signed-out. The "Account" panel in
// the gear modal is ALWAYS present: signed-in users see their company identity
// (and Sign out), everyone else sees an "Anonymous" placeholder. The panel also
// hosts the reply-language picker (see SandpieLanguage) — the language sandpie
// answers in. When a sandpie-server backend is present, signing in surfaces the
// company SSO **as a read-only AI provider** — a server-side wrapper that holds
// the real LLM key. Nothing here is persisted: the managed provider is injected
// into SandpieProviders in memory and removed on sign-out, so the user's own
// settings/config file are never touched.
//
// No backend (static / Dropbox / file:// deploy, or /auth/* missing) → this
// module is a silent no-op: no panel, no chip, no behaviour change.
//
// CLASSIC script (global window.SandpieAccount). Load after settings.js + providers.js.

const SandpieAccount = (() => {
  let _user = null;
  let _backend = false;       // a sandpie-server auth backend was detected
  let _langFlashT = null;     // "Applied" feedback timer for the language picker
  let _panel = null;
  let _registered = false;
  let _refreshTimer = null;
  let _managedCache = null;       // last { token, cat } fetched — lets a late-booting picker catch up

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
    // The Account panel (identity + reply language) is always available — no
    // backend needed. The /auth/me probe only fills in the real identity and
    // the Sign in / Sign out UI when a sandpie-server backend is present.
    registerPanel();
    let me;
    try { me = await getJSON('/auth/me'); }
    catch (_) { _backend = false; paint(); return; }   // unreachable → anonymous
    if (me.ok && me.data) {                // signed in
      _backend = true;
      _user = me.data;
      onSignedIn();
    } else if (me.status === 401) {        // backend present, signed out
      _backend = true;
      paint();
    } else {                               // 404 / other → no auth backend
      _backend = false;
      paint();
    }
  }

  async function onSignedIn() {
    paint();
    // Announce sign-in on the shared bus so optional modules can react (e.g.
    // dropbox.js auto-connects cloud sync). Loose coupling — no hard dep.
    try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('account:signedin', _user); } catch (_) {}
    await refreshManagedProvider();
    clearInterval(_refreshTimer);
    _refreshTimer = setInterval(refreshManagedProvider, 30 * 60 * 1000);   // keep the session token fresh
  }

  // Pull the session token + model catalog and surface them as read-only providers.
  // Re-callable (the 30-min token refresh re-runs it). The fetched catalog is
  // cached (_managedCache) so a picker that booted *after* this ran can still
  // catch up via ensureManaged() — otherwise company models silently never show
  // when providers.js wasn't ready at fetch time.
  async function refreshManagedProvider() {
    let tok;
    try { tok = await getJSON('/auth/token'); } catch (_) { return; }
    if (!tok.ok || !tok.data || !tok.data.token) return;
    const token = tok.data.token;   // the session token is the "key" — server-verified
    // Managed model catalog (GET /models) → one read-only chip per model. The
    // server injects the real LLM key and enforces model/temperature/max-output.
    // Older server with no catalog (/models 404 or empty) → one "(managed)" chip.
    let cat = null;
    try { const r = await getJSON('/models'); if (r.ok && r.data && Array.isArray(r.data.models) && r.data.models.length) cat = r.data; } catch (_) {}
    _managedCache = { token, cat };
    applyManaged();
  }

  // Inject the cached catalog into SandpieProviders. No-op until providers.js is
  // ready, so it is safe to call before the picker exists; bootProviders re-calls
  // it (via ensureManaged) once the picker is up.
  function applyManaged() {
    if (!_managedCache) return;
    if (!(window.SandpieProviders && SandpieProviders.setManaged)) return;
    const { token, cat } = _managedCache;
    if (cat) {
      SandpieProviders.setManaged(cat.models.map(m => ({
        name: m.label || m.id,
        endpoint: location.origin,   // → the server's /chat/completions
        model: m.id,
        apiKey: token,
        proxyUrl: '',
        contextWindow: m.contextWindow,
        maxTokens: m.maxOutput,
        temperature: m.temperature,
        reasoningEffort: m.reasoningEffort,
        // Vision config pre-set by the company admin in models.json (yes/no only).
        vision: (m.vision === 'yes') ? 'yes' : 'no',
        // Languages this model GENERATES reliably (models.json `fluent`). Drives
        // the localization gate: a Reply language in this set is authored directly
        // by the model; one outside it is authored in English and machine-
        // translated. Omitted => undefined => localize everything non-English.
        fluent: Array.isArray(m.fluent) ? m.fluent : undefined,
        visionFallbackId: m.visionFallback ? '__managed:' + m.visionFallback : undefined,
      })), cat.defaultModel);
    } else {
      SandpieProviders.setManaged({ name: 'Company AI', endpoint: location.origin, model: '(managed)', apiKey: token, proxyUrl: '' });
    }
  }

  // Re-apply the company catalog if it was fetched before the picker was ready.
  // Called by providers.js bootProviders so the picker never misses the catalog.
  function ensureManaged() { applyManaged(); }

  // The worker re-minted the managed session token after a 401 (the short-lived
  // JWT lapsed while the SSO cookie is still valid). Apply it page-side so future
  // requests use the fresh token too — no second /auth/token round-trip and no
  // user prompt. setManaged() preserves the active pick (not a first injection)
  // and re-syncs the hidden #apiKey input via applyActiveProvider().
  function applyRefreshedToken(token) {
    if (!token) return;
    if (_managedCache) { _managedCache.token = token; applyManaged(); }
    else { refreshManagedProvider(); }   // catalog not loaded yet → do a full refresh
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
    let html = '';
    // Identity row: the real account, or an "Anonymous" placeholder.
    if (_user) {
      const name = _user.name || _user.email || 'Signed in';
      html +=
        '<div style="display:flex; align-items:center; gap:0.6rem;">' +
          '<div style="flex:none;aspect-ratio:1;width:38px;height:38px;border-radius:50%;background:var(--sp-accent-dim);display:flex;align-items:center;justify-content:center;font-weight:600;font-size:0.85rem;">' + esc(initials(name)) + '</div>' +
          '<div style="display:flex;flex-direction:column;min-width:0;">' +
            '<span style="font-size:0.9rem;">' + esc(name) + '</span>' +
            '<span style="font-size:0.72rem;color:var(--sp-text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(_user.email || '') + '</span>' +
          '</div>' +
        '</div>' +
        '<button class="ghost" id="spLogoutBtn" style="margin-top:0.9rem;">Sign out</button>';
    } else {
      html +=
        '<div style="display:flex; align-items:center; gap:0.6rem;">' +
          '<div style="flex:none;aspect-ratio:1;width:38px;height:38px;border-radius:50%;background:var(--sp-panel);border:1px solid var(--sp-border);display:flex;align-items:center;justify-content:center;font-weight:600;font-size:0.85rem;color:var(--sp-text-dim);">?</div>' +
          '<div style="display:flex;flex-direction:column;min-width:0;">' +
            '<span style="font-size:0.9rem;">Anonymous</span>' +
            '<span style="font-size:0.72rem;color:var(--sp-text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">not signed in</span>' +
          '</div>' +
        '</div>';
      if (_backend) html += '<button class="ghost" id="spLoginBtn" style="margin-top:0.9rem;">Sign in</button>';
    }
    // Reply-language picker — always present, backend or not.
    html += languageBlockHtml();
    _panel.innerHTML = html;
    _panel.querySelector('#spLogoutBtn')?.addEventListener('click', logout);
    _panel.querySelector('#spLoginBtn')?.addEventListener('click', login);
    wireLanguage();
  }

  // ---- Reply-language picker (drives the LLM reply language; see SandpieLanguage) ----
  function languageBlockHtml() {
    let select;
    try {
      const L = (typeof SandpieLanguage !== 'undefined') ? SandpieLanguage : null;
      if (!L || !L.options || !L.stored) throw new Error('SandpieLanguage missing');
      const o = L.options();
      const stored = L.stored();
      const current = (stored && stored !== 'auto') ? stored : 'auto';
      select = '<select id="spLanguage" style="width:100%;margin-top:0.35rem;padding:0.4rem 0.5rem;background:var(--sp-panel);border:1px solid var(--sp-border);border-radius:6px;color:var(--sp-text);font-size:0.82rem;">' +
        '<option value="auto">' + esc(o.auto.label) + '</option>' +
        o.items.map(l => '<option value="' + esc(l.code) + '" title="' + esc(l.name) + '"' + (l.code === current ? ' selected' : '') + '>' + esc(l.native || l.name) + '</option>').join('') +
        '</select>';
    } catch (_) {
      select = '<p style="font-size:0.75rem;color:var(--sp-text-dim);margin:0.35rem 0 0;">Language picker unavailable.</p>';
    }
    return '<div style="margin-top:1rem;border-top:1px solid var(--sp-border);padding-top:0.8rem;">' +
      '<label for="spLanguage" style="font-size:0.8rem;font-weight:600;display:block;">Reply language</label>' +
      select +
      '<p id="spLangHint" style="font-size:0.72rem;color:var(--sp-text-dim);margin:0.35rem 0 0;">Sandpie answers in this language unless you explicitly ask otherwise (e.g. a translation task).</p>' +
      '</div>';
  }

  function wireLanguage() {
    if (!_panel) return;
    const sel = _panel.querySelector('#spLanguage');
    const hint = _panel.querySelector('#spLangHint');
    if (!sel || !hint) return;
    sel.addEventListener('change', () => {
      try { if (typeof SandpieLanguage !== 'undefined' && SandpieLanguage.set) SandpieLanguage.set(sel.value); } catch (_) {}
      let shown = sel.selectedOptions && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : sel.value;
      try {
        if (sel.value === 'auto' && typeof SandpieLanguage !== 'undefined' && SandpieLanguage.nativeName) {
          shown = SandpieLanguage.nativeName(SandpieLanguage.effective());
        }
      } catch (_) {}
      hint.textContent = 'Applied — sandpie will now reply in ' + shown + '.';
      clearTimeout(_langFlashT);
      _langFlashT = setTimeout(() => {
        hint.textContent = 'Sandpie answers in this language unless you explicitly ask otherwise (e.g. a translation task).';
      }, 2000);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { login, logout, isActive: () => !!_user, current: () => _user, ensureManaged, applyRefreshedToken };
})();
window.SandpieAccount = SandpieAccount;
