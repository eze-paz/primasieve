/* =============================================================================
   Console Sidebar Module — Redirect all console output into a collapsible
   sidebar panel so it's visible on mobile (and desktop) without the
   DevTools panel.
   ============================================================================= */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------
  const $ = id => document.getElementById(id);

  // ---------------------------------------------------------------------------
  // Settings
  // ---------------------------------------------------------------------------
  const MAX_LINES    = 500;           // tail buffer
  const BATCH_MS     = 50;            // render coalescing
  const STORAGE_KEY  = 'sandpie-console-open';

  // ---------------------------------------------------------------------------
  // Line buffer + rendering
  // ---------------------------------------------------------------------------
  let _lines = [];
  let _flushTimer = null;
  let _scrolledToBottom = true;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function colorFor(level) {
    switch (level) {
      case 'error': return 'var(--sp-danger)';
      case 'warn':  return 'var(--sp-warn)';
      case 'info':  return 'var(--sp-accent)';
      case 'debug': return 'var(--sp-text-dim)';
      default:      return 'var(--sp-text)';
    }
  }

  function iconFor(level) {
    switch (level) {
      case 'error': return '✕';
      case 'warn':  return '‼';
      case 'info':  return 'ℹ';
      case 'debug': return '◦';
      default:      return '›';
    }
  }

  /* Turn any logged arguments into a single string (like DevTools does) */
  function serialize(args) {
    return args.map(a => {
      if (a === null) return 'null';
      if (a === undefined) return 'undefined';
      if (typeof a === 'object') {
        try { return JSON.stringify(a); } catch (_) { return String(a); }
      }
      return String(a);
    }).join(' ');
  }

  /* Record a line: append to the capped tail buffer, then schedule a render. */
  function record(level, text) {
    _lines.push({ level, text, t: Date.now() });
    if (_lines.length > MAX_LINES) _lines.splice(0, _lines.length - MAX_LINES);
    scheduleFlush();
  }

  /* Schedule flush of buffered lines to DOM */
  function scheduleFlush() {
    if (_flushTimer) return;
    _flushTimer = setTimeout(flushLines, BATCH_MS);
  }

  function flushLines() {
    _flushTimer = null;
    const panel = $('consoleLines');
    if (!panel) return;

    const frag = document.createDocumentFragment();
    for (const entry of _lines) {
      const row = document.createElement('div');
      row.className = 'console-line';
      row.style.cssText = `
        font: 0.72rem/1.4 'JetBrains Mono', 'SF Mono', Consolas, monospace;
        padding: 0.15rem 0.3rem;
        border-left: 2px solid transparent;
        white-space: pre-wrap;
        word-break: break-word;
        color: ${colorFor(entry.level)};
      `;
      row.textContent = `${iconFor(entry.level)} ${entry.text}`;
      frag.appendChild(row);
    }
    // replaceChildren — NOT append — so repeated flushes never duplicate lines
    // (the buffer is the source of truth, capped in record()), and a freshly
    // mounted panel paints the full history on open.
    panel.replaceChildren(frag);

    if (_scrolledToBottom) {
      panel.scrollTop = panel.scrollHeight;
    }
  }

  // ---------------------------------------------------------------------------
  // Intercept native console
  // ---------------------------------------------------------------------------
  const _orig = {
    log:   console.log,
    warn:  console.warn,
    error: console.error,
    info:  console.info,
    debug: console.debug,
  };

  function hijack(level) {
    return function (...args) {
      _orig[level].apply(console, args);
      record(level, serialize(args));
    };
  }

  console.log   = hijack('log');
  console.warn  = hijack('warn');
  console.error = hijack('error');
  console.info  = hijack('info');
  console.debug = hijack('debug');

  // Also catch window.onerror (uncaught exceptions)
  window.addEventListener('error', (e) => {
    const msg = e.error ? `${e.message}\n${e.error.stack || ''}` : e.message;
    record('error', msg);
  });
  window.addEventListener('unhandledrejection', (e) => {
    const reason = e.reason;
    const text = reason instanceof Error ? `${reason.message}\n${reason.stack || ''}` : String(reason);
    record('error', `Unhandled rejection: ${text}`);
  });

  // ---------------------------------------------------------------------------
  // Relay service-worker logs into the (hijacked) console so [sw] output is
  // captured here too. OPFS-change SW messages are handled separately in
  // modules/dropbox.js.
  // ---------------------------------------------------------------------------
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', (ev) => {
      const d = ev.data;
      if (!d || d.type !== 'sandpie-sw-log') return;
      const fn = console[d.level] || console.log;
      fn.call(console, '[sw]', d.text);
    });
    const flushSwLogs = () => {
      const c = navigator.serviceWorker.controller;
      if (c) try { c.postMessage({ type: 'sandpie-sw-flush-logs' }); } catch (_) {}
    };
    flushSwLogs();
    navigator.serviceWorker.addEventListener('controllerchange', flushSwLogs);
  }

  // ---------------------------------------------------------------------------
  // Build sidebar panel HTML
  // ---------------------------------------------------------------------------
  const panelHtml = `
    <div style="display:flex; gap:0.25rem; margin-bottom:0.35rem;">
      <button class="ghost" id="consoleClear" style="flex:1; font-size:0.7rem;">Clear</button>
      <button class="ghost" id="consoleCopy"  style="flex:1; font-size:0.7rem;">Copy</button>
    </div>
    <div id="consoleLines" style="
      max-height: 220px;
      overflow-y: auto;
      background: var(--sp-bg);
      border: 1px solid var(--sp-border);
      border-radius: 4px;
      padding: 0.25rem 0;
    "></div>
  `;

  // ---------------------------------------------------------------------------
  // Register with sidebar via SandpieMenu (fails silently if API unavailable)
  // ---------------------------------------------------------------------------
  /* Wire a freshly-mounted console panel (its body already contains panelHtml):
     scroll tracking + Clear/Copy, then paint the existing history. */
  function wireConsolePanel(body) {
    const linesEl = body.querySelector('#consoleLines');
    if (!linesEl) return;

    linesEl.addEventListener('scroll', () => {
      _scrolledToBottom =
        linesEl.scrollHeight - linesEl.scrollTop - linesEl.clientHeight <= 4;
    });

    const btnClear = body.querySelector('#consoleClear');
    if (btnClear) btnClear.addEventListener('click', () => { _lines.length = 0; linesEl.replaceChildren(); });

    const btnCopy = body.querySelector('#consoleCopy');
    if (btnCopy) btnCopy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(_lines.map(l => l.text).join('\n')); } catch (_) { /* ignore */ }
    });

    _scrolledToBottom = true;
    flushLines();   // paint the buffered history into the just-mounted panel
  }

  /* Console access moved to the command registry (2026-08-07): `>>> console`
     toggles a floating panel. The old surfaces — the gear-modal tab and the
     sidebar section — are commented out below; uncomment them to restore:

  function init() {
    if (window.SandpieSettings) {
      SandpieSettings.register({
        id: 'console', title: 'Console', order: 90,
        render(panel) { panel.innerHTML = panelHtml; wireConsolePanel(panel); },
      });
      return;
    }
    if (typeof SandpieMenu !== 'undefined') {
      const wasOpen = localStorage.getItem(STORAGE_KEY) === '1';
      SandpieMenu.add('console', { title: 'Console', open: wasOpen, html: panelHtml, onRender: wireConsolePanel });
      const details = document.getElementById('console');
      if (details) details.addEventListener('toggle', () => {
        localStorage.setItem(STORAGE_KEY, details.open ? '1' : '');
      });
      return;
    }
    setTimeout(init, 100);   // neither host ready yet — retry
  }
  */

  let _overlay = null;
  let _retry = 0;

  function ensureOverlay() {
    if (_overlay && document.body.contains(_overlay)) return _overlay;
    const ov = document.createElement('div');
    ov.id = 'sandpieConsoleOverlay';
    ov.style.cssText = [
      'position:fixed; right:0.75rem; bottom:0.75rem; z-index:9999;',
      'width:min(560px, calc(100vw - 1.5rem)); max-height:42vh;',
      'display:flex; flex-direction:column;',
      'background:var(--sp-panel); border:1px solid var(--sp-border-bright); border-radius:8px;',
      'box-shadow:0 0 30px var(--sp-accent-dim);',
      'font:0.8rem inherit; color:var(--sp-text);',
    ].join(' ');
    ov.innerHTML =
      '<div style="display:flex; align-items:center; gap:0.4rem; padding:0.4rem 0.6rem; border-bottom:1px solid var(--sp-border); flex:0 0 auto;">' +
        '<span style="font-weight:600; font-size:0.72rem; letter-spacing:0.08em; color:var(--sp-text-dim); flex:1;">CONSOLE</span>' +
        '<button type="button" class="ghost" id="consoleClear" style="font-size:0.7rem; padding:0.15rem 0.5rem;">Clear</button>' +
        '<button type="button" class="ghost" id="consoleCopy" style="font-size:0.7rem; padding:0.15rem 0.5rem;">Copy</button>' +
        '<button type="button" class="ghost" id="consoleClose" title="Close (or >>> console)" style="font-size:0.7rem; padding:0.15rem 0.45rem;">✕</button>' +
      '</div>' +
      '<div id="consoleLines" style="overflow-y:auto; min-height:4rem; padding:0.25rem 0; background:var(--sp-bg);"></div>';
    document.body.appendChild(ov);
    _overlay = ov;
    wireConsolePanel(ov);                       // scroll tracking + Clear/Copy
    const closeBtn = ov.querySelector('#consoleClose');
    if (closeBtn) closeBtn.addEventListener('click', closeConsole);
    return ov;
  }

  function openConsole() {
    const ov = ensureOverlay();
    ov.style.display = 'flex';
    flushLines();                               // paint lines logged while closed
  }
  function closeConsole() { if (_overlay) _overlay.style.display = 'none'; }
  function toggleConsole() {
    const visible = !!(_overlay && _overlay.style.display !== 'none');
    if (visible) closeConsole(); else openConsole();
    return !visible;
  }

  function registerConsoleCommand() {
    if (typeof SandpieCommands === 'undefined') return false;
    SandpieCommands.register({
      name: 'console',
      module: 'core',
      help: 'Open/close the live console panel (toggle)',
      usage: '>>> console',
      run() { return toggleConsole() ? 'Console panel opened.' : 'Console panel closed.'; },
    });
    return true;
  }

  /* Boot: the console is command-driven now — `>>> console` toggles the panel.
     (core.js loads before console.js, so SandpieCommands exists on first try;
     retry is just belt-and-braces.) */
  function init() {
    if (!registerConsoleCommand() && _retry++ < 50) setTimeout(init, 100);
  }

  // Boot when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
