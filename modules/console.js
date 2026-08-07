/* =============================================================================
   Console Module — capture all console output for `>>> console`.
   Redirects console.log/warn/error/info/debug (plus window errors, unhandled
   rejections and service-worker logs) into a capped in-memory buffer. The
   `>>> console` command dumps that buffer as plain text into the command
   output panel (cmd-body). No UI of its own — the settings tab, sidebar
   section and Clear/Copy panel were removed (2026-08-07); the console lives
   entirely behind the command.
   ============================================================================= */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Line buffer
  // ---------------------------------------------------------------------------
  const MAX_LINES = 500;           // tail buffer

  let _lines = [];

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

  /* Record a line: append to the capped tail buffer. */
  function record(level, text) {
    _lines.push({ level, text, t: Date.now() });
    if (_lines.length > MAX_LINES) _lines.splice(0, _lines.length - MAX_LINES);
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
  // `>>> console` command — dump the buffer as plain text
  // ---------------------------------------------------------------------------
  let _retry = 0;
  function registerConsoleCommand() {
    if (typeof SandpieCommands === 'undefined') return false;
    SandpieCommands.register({
      name: 'console',
      module: 'core',
      help: 'Dump the captured console output as plain text',
      usage: '>>> console',
      run() {
        if (!_lines.length) return '(console buffer is empty)';
        return _lines.map(l => l.text).join('\n');
      },
    });
    return true;
  }

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
