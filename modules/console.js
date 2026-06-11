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

  /* Prefer the gear modal (SandpieSettings); fall back to the sidebar
     (SandpieMenu) so the console still appears when settings.js isn't loaded
     (e.g. the stable page). No debug toggle — the console is always available. */
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

  // Boot when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
