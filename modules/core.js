/* =============================================================================
   sandpie core — host contract + foundational globals.
   Loaded first (classic <script>, NOT a module) so $, SandpieMenu, the shared
   conversation state, and window.Sandpie exist as bare globals before any
   module runs. Dependencies flow ONE way: modules depend on these; this file
   names no specific module.
   ============================================================================= */
const $ = id => document.getElementById(id);
window.$ = $;

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
   SandpieCommands - Text Command Registry
   ============================================================================= */
const SandpieCommands = (() => {
  const commands = new Map();
  return {
    register(cmd = {}) {
      if (!cmd.name) { console.warn('SandpieCommands: missing name'); return false; }
      commands.set(cmd.name, cmd);
      return true;
    },
    unregister(name) { return commands.delete(name); },
    get(name) { return commands.get(name) || null; },
    list() { return Array.from(commands.values()); },
    async dispatch(text) {
      const trimmed = text.slice(3).trim(); // strip '>>>'
      if (!trimmed) return false;
      const parts = trimmed.split(/\s+/);
      const cmd = commands.get(parts[0]);
      if (!cmd) return false;
      if (cmd.run) {
        try {
          const result = await cmd.run(text, parts);
          if (SandpieCommandView) SandpieCommandView.show(result, cmd.name);
        } catch (err) {
          if (SandpieCommandView) SandpieCommandView.show('Error: ' + err.message, cmd.name);
        }
      } else {
        if (SandpieCommandView) SandpieCommandView.show('(command not yet implemented)', cmd.name);
      }
      return true;
    },
    hintFor(text) {
      // Return placeholder hint for matching commands
      const t = text.slice(3).trimStart();
      if (t === '') return null;
      const matches = [];
      for (const c of commands.values()) {
        if (c.name.startsWith(t)) matches.push(c);
      }
      if (matches.length === 0) return null;
      return matches.slice(0, 6).map(c => c.usage || c.name).join(' \u00B7 ');
    },
    complete(text) {
      const t = text.slice(3).trimStart();
      const matches = [];
      for (const c of commands.values()) {
        if (c.name.startsWith(t)) matches.push(c.name);
      }
      if (matches.length === 0) return null;
      matches.sort();
      let prefix = matches[0];
      for (let i = 1; i < matches.length; i++) {
        let j = 0;
        while (j < prefix.length && j < matches[i].length && prefix[j] === matches[i][j]) j++;
        prefix = prefix.slice(0, j);
      }
      return { matches, prefix, single: matches.length === 1 };
    }
  };
})();
window.SandpieCommands = SandpieCommands;

/* ---- built-in commands: help, clear ------------------------------------ */
(function() {
  function helpTable() {
    const cmds = SandpieCommands.list().sort((a, b) => {
      if (a.module !== b.module) return a.module.localeCompare(b.module);
      return a.name.localeCompare(b.name);
    });
    const maxName = cmds.reduce((m, c) => Math.max(m, (c.usage || c.name).length), 0);
    let out = '';
    let lastModule = '';
    for (const c of cmds) {
      if (c.module !== lastModule) {
        if (lastModule) out += '\n';
        out += '[' + c.module + ']\n';
        lastModule = c.module;
      }
      const name = (c.usage || c.name).padEnd(maxName);
      out += '  ' + name + '  ' + c.help + '\n';
    }
    return out || '(no commands registered)';
  }
  function helpDetail(cmdName) {
    const c = SandpieCommands.get(cmdName);
    if (!c) return 'Unknown command: ' + cmdName;
    let out = '';
    out += 'Command:  ' + c.name + '\n';
    out += 'Module:   ' + c.module + '\n';
    out += 'Usage:    ' + (c.usage || c.name) + '\n';
    out += 'Help:     ' + c.help + '\n';
    return out;
  }
  SandpieCommands.register({
    name: 'help',
    module: 'core',
    help: 'List commands or get help for one',
    usage: '>>> help [command]',
    run(text, parts) {
      if (parts.length > 1) return helpDetail(parts[1]);
      return helpTable();
    }
  });
  SandpieCommands.register({
    name: 'clear',
    module: 'core',
    help: 'Close the inline output panel',
    usage: '>>> clear',
    run() {
      if (SandpieCommandView) SandpieCommandView.hide();
      return '';
    }
  });

  SandpieCommands.register({
    name: 'copy',
    module: 'core',
    help: 'Copy the entire conversation object to clipboard',
    usage: '>>> copy',
    async run() {
      const s = (typeof activeStream === 'function') ? activeStream() : (convStreams ? convStreams.get(activeConvId) : null);
      const convMessages = s ? s.messages : messages;
      if (!convMessages || !convMessages.length) return 'No active conversation to copy.';
      const firstUser = convMessages.find(m => m.role === 'user');
      let derived = 'Untitled';
      if (firstUser && firstUser.content) {
        const text = typeof firstUser.content === 'string'
          ? firstUser.content
          : firstUser.content.filter(p => p.type === 'text').map(p => p.text).join('');
        derived = text.slice(0, 60);
      }
      let sysContent = (typeof SandpieSystemPrompt !== 'undefined' && SandpieSystemPrompt.get)
        ? SandpieSystemPrompt.get()
        : (localStorage.getItem('sandpie-system-prompt') || 'You are a helpful assistant that reasons through the users requests step-by-step.');
      if (typeof SandpieMindframe !== 'undefined' && SandpieMindframe.systemBlock) {
        try { sysContent += SandpieMindframe.systemBlock(convMessages); } catch (_) {}
      }
      const payload = {
        id: activeConvId,
        title: derived,
        updated: new Date().toISOString(),
        messages: convMessages,
        systemPrompt: { role: 'system', content: sysContent },
        compaction: s ? s.compaction : null,
      };
      const json = JSON.stringify(payload, null, 2);
      try {
        await navigator.clipboard.writeText(json);
        return 'Copied ' + convMessages.length + ' message(s) to clipboard (' + json.length + ' chars).';
      } catch (e) {
        return 'Clipboard error: ' + e.message;
      }
    }
  });
})();

/* =============================================================================
   SandpieCommandView - Inline output panel controller
   ============================================================================= */
const SandpieCommandView = (() => {
  let panel = null, body = null, promptEl = null;
  function ensure() {
    if (panel) return;
    panel = $('commandOutput');
    if (!panel) return;
    body = panel.querySelector('.cmd-body');
    promptEl = panel.querySelector('.cmd-prompt');
  }
  return {
    show(output, cmdName) {
      ensure();
      if (!panel || !body) return;
      if (output instanceof HTMLElement) {
        body.innerHTML = '';
        body.appendChild(output);
      } else {
        body.textContent = typeof output === 'string' ? output : JSON.stringify(output, null, 2);
      }
      if (promptEl) promptEl.textContent = '>>> ' + (cmdName || '');
      panel.style.display = '';
    },
    hide() { if (panel) panel.style.display = 'none'; },
    clear() { if (body) body.textContent = ''; }
  };
})();
window.SandpieCommandView = SandpieCommandView;



/* =============================================================================
   Shared conversation state — host-global because several modules
   (conversations, artifacts, context, augmentations, mobile) read it as bare
   globals and conversations.js reassigns activeConvId / messages.
   ============================================================================= */
let messages = [];
const convStreams = new Map();
const convLastViewed = new Map();
let activeConvId = null; // always start on homescreen (was: localStorage read)

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

  // --- refresh interception --------------------------------------------------
  // A refresh reloads BEFORE the sync provider has pushed anything still marked
  // dirty, and before Dropbox's cursor has been read past our own uploads — the
  // second one is why the boot splash used to appear with nothing to download.
  // So: flush first, then reload for real.
  //
  // HARD LIMIT, worth knowing: only key-driven refreshes can be intercepted.
  // The browser's reload button, the address bar and closing the tab cannot be
  // delayed by a page — `beforeunload` may only raise a native dialog, it cannot
  // await async work, and requests started during unload are cut off. There is no
  // API that makes those paths wait for a sync.
  let _reloading = false;
  const RELOAD_PROGRESS_KEY = 'reload-flush';
  async function reloadWithSync() {
    if (_reloading) return;               // second F5 while flushing: ignore, one reload is coming
    _reloading = true;
    // Reuse the app's one progress affordance (the compaction spinner pill), and only
    // if the flush is slow enough to be worth explaining — a clean refresh is
    // instant, so normally nothing appears at all.
    const notice = setTimeout(() => {
      try { window.showAppProgress?.(RELOAD_PROGRESS_KEY, 'Finishing sync before reload…'); } catch (_) {}
    }, 250);
    try {
      if (_sync?.flushBeforeReload) await _sync.flushBeforeReload();
      else if (_sync?.sync) await _sync.sync();
    } catch (e) {
      console.warn('[reload] pre-reload flush failed, reloading anyway:', e);
    } finally {
      clearTimeout(notice);
      // The reload wipes the DOM anyway; this only matters if something blocks it.
      try { window.hideAppProgress?.(RELOAD_PROGRESS_KEY); } catch (_) {}
      location.reload();
    }
  }
  // Capture phase so this wins over any per-element handler.
  window.addEventListener('keydown', (e) => {
    const isF5 = e.key === 'F5';
    const isCmdR = (e.ctrlKey || e.metaKey) && (e.key === 'r' || e.key === 'R');
    if (!isF5 && !isCmdR) return;
    // Shift = hard reload (cache bypass). Never intercept it: that is the escape
    // hatch for a wedged page, and it must stay instant.
    if (e.shiftKey || e.altKey) return;
    if (!_sync?.isConnected?.()) return;  // nothing to flush → let the browser reload
    e.preventDefault();
    reloadWithSync();
  }, true);

  return {
    events,

    // primitives the page owns and modules are allowed to use
    $,
    api,
    get addMsg() { return window.addMsg; },   // defined in modules/conversations.js
    // Pane → content container (.conv-host when mounted), and a composer-safe
    // append. Both from modules/conversations.js. Modules that render into a pane
    // MUST use them: a bare appendChild on a pane lands below the sticky composer.
    get paneScrollEl()  { return window.paneScrollEl; },
    get appendContent() { return window.appendContent; },
    get opfs()   { return opfs; },
    get menu()   { return SandpieMenu; },
    get tokens() { return (typeof SandpieTokens !== 'undefined') ? SandpieTokens : null; },
    opfsMtime(path)        { return opfs.lastModified(path); },
    isGenerating()         { return (typeof anyStreamGenerating === 'function' && anyStreamGenerating()) || (typeof window !== 'undefined' && typeof window.anyStreamGenerating === 'function' && window.anyStreamGenerating()) || false; },
    openFilePath()         { return window._openFilePath; },
    refreshFiles()         { return refreshFileList(); },
    refreshConversations() { return refreshConversationList(); },

    // sync capability
    registerSyncProvider,
    syncProvider() { return _sync; },
    sync()         { return _sync?.sync?.(); },
    reload()       { return reloadWithSync(); },
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

