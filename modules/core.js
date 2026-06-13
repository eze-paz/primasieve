/* =============================================================================
   sandpie core — host contract + foundational globals.
   Loaded first (classic <script>, NOT a module) so $, SandpieMenu, the shared
   conversation state, and window.Sandpie exist as bare globals before any
   module runs. Dependencies flow ONE way: modules depend on these; this file
   names no specific module.
   ============================================================================= */
const $ = id => document.getElementById(id);

/* =============================================================================
   SandpieMenu — Sidebar Section Registry
   ============================================================================= */
const SandpieMenu = (() => {
  const sections = new Map();
  let sidebarEl = null;
  function ensureSidebar() {
    if (!sidebarEl) sidebarEl = document.querySelector('aside');
    return sidebarEl;
  }
  function createSectionEl(id, config) {
    const details = document.createElement('details');
    details.className = 'service';
    details.id = id;
    if (config.open) details.open = true;
    const summary = document.createElement('summary');
    let summaryHtml = config.title;
    if (config.dot) {
      summaryHtml += ` <span class="status-dot" id="${config.dot}"></span>`;
    }
    if (config.badge) {
      summaryHtml += ` <span style="margin-left:auto; font-size:0.7rem; color:var(--sp-text-dim);">${config.badge}</span>`;
    }
    summary.innerHTML = summaryHtml;
    details.appendChild(summary);
    const body = document.createElement('div');
    body.className = 'service-body';
    if (typeof config.html === 'string') {
      body.innerHTML = config.html;
    } else if (config.html instanceof HTMLElement) {
      body.appendChild(config.html);
    }
    details.appendChild(body);
    return details;
  }
  function insertBeforeFooter(el) {
    const sidebar = ensureSidebar();
    if (!sidebar) return;
    // The footer is the bottom block (margin-top:auto) holding the Settings button.
    const footer = sidebar.querySelector('div[style*="margin-top:auto"]');
    if (footer && sidebar.contains(footer)) {
      sidebar.insertBefore(el, footer);
    } else {
      sidebar.appendChild(el);
    }
  }
  return {
    add(id, config = {}) {
      if (sections.has(id)) {
        console.warn(`SandpieMenu: section "${id}" already exists`);
        return false;
      }
      const el = createSectionEl(id, config);
      insertBeforeFooter(el);
      sections.set(id, { el, config });
      if (config.onRender) config.onRender(el.querySelector('.service-body'));
      return true;
    },
    remove(id) {
      const section = sections.get(id);
      if (!section) return false;
      section.el.remove();
      sections.delete(id);
      return true;
    },
    get(id) {
      return sections.get(id)?.el || null;
    },
    updateBadge(id, text) {
      const section = sections.get(id);
      if (!section) return false;
      const badge = section.el.querySelector('summary span');
      if (badge) badge.textContent = text;
      return true;
    },
    list() {
      return Array.from(sections.keys());
    }
  };
})();
window.SandpieMenu = SandpieMenu;

/* =============================================================================
   Shared conversation state — host-global because several modules
   (conversations, artifacts, context, augmentations, mobile) read it as bare
   globals and conversations.js reassigns activeConvId / messages.
   ============================================================================= */
let messages = [];
const convStreams = new Map();
const convLastViewed = new Map();
let activeConvId = localStorage.getItem('sandpie-active-conv') || null;

/* --- API URL routing: remote proxy, local /proxy/, or direct --- */
const isLocalhost = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
function api(url) {
  const stripped = url.replace(/^https?:\/\//, '');
  const remote = ($('proxyUrl').value || '').trim().replace(/\/$/, '');
  if (remote) return remote + '/proxy/' + stripped;
  if (isLocalhost) return '/proxy/' + stripped;
  return url;
}

/* =============================================================================
   Sandpie — core contract / host API.
   The single integration surface a module may touch. Dependencies flow ONE way:
   modules depend on Sandpie; Sandpie never names a specific module. Optional
   capabilities (e.g. cloud sync) are plugged in through a registry, so when a
   module is absent its slot is simply empty and the calls degrade to no-ops —
   the page boots and core chat works with any module removed.
   ============================================================================= */
const Sandpie = (() => {
  // --- event bus -------------------------------------------------------------
  const _bus = new Map(); // event name -> Set<callback>
  const events = {
    on(evt, cb) {
      let s = _bus.get(evt);
      if (!s) _bus.set(evt, s = new Set());
      s.add(cb);
      return () => events.off(evt, cb);
    },
    off(evt, cb) { _bus.get(evt)?.delete(cb); },
    emit(evt, payload) {
      for (const cb of (_bus.get(evt) || [])) {
        try { cb(payload); } catch (e) { console.warn('[Sandpie] listener error for', evt, e); }
      }
    },
  };

  // --- sync provider registry (cloud sync is an optional capability) ---------
  // A provider implements: { sync(), fileStatus(path, opfsMtime), getState(),
  // initialSyncDone }. With no provider registered every call below is a no-op
  // and the file browser falls back to a local-only view.
  let _sync = null;
  function registerSyncProvider(impl) {
    _sync = impl;
    events.emit('sync:provider-changed', impl);
    return () => { if (_sync === impl) { _sync = null; events.emit('sync:provider-changed', null); } };
  }

  return {
    events,

    // primitives the page owns and modules are allowed to use
    $,
    api,
    get addMsg() { return window.addMsg; },   // defined in modules/conversations.js
    get opfs()   { return opfs; },
    get menu()   { return SandpieMenu; },
    get tokens() { return (typeof SandpieTokens !== 'undefined') ? SandpieTokens : null; },
    opfsMtime(path)        { return opfs.lastModified(path); },
    isGenerating()         { return anyStreamGenerating(); },
    openFilePath()         { return window._openFilePath; },
    refreshFiles()         { return refreshFileList(); },
    refreshConversations() { return refreshConversationList(); },

    // sync capability
    registerSyncProvider,
    syncProvider() { return _sync; },
    sync()         { return _sync?.sync?.(); },
    fileSyncStatus(path, opfsMtime) { return _sync?.fileStatus?.(path, opfsMtime) ?? null; },
    initialSyncDone()               { return _sync ? !!_sync.initialSyncDone : window._sandpieBootDone; },
  };
})();
window.Sandpie = Sandpie;

window._sandpieBootDone = true;

/* =============================================================================
   Page-chrome glue
   ============================================================================= */
// Suppress the browser's default PWA install prompt (saved for a future in-app trigger).
let _deferredInstallPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  _deferredInstallPrompt = e;
  console.log('[sandpie] PWA install prompt suppressed (available via menu)');
});

