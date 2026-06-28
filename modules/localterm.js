/**
 * localterm Module for Sandpie — terminal to the user's OWN local machine.
 *
 * A tiny local helper (downloaded once) listens on 127.0.0.1 and pipes a PTY
 * over a loopback WebSocket. This module:
 *   - shows a "Terminal" sidebar section,
 *   - detects whether the helper is running (GET /ping),
 *   - if not: shows an OS-detected one-click download + run instructions,
 *   - if yes: opens an xterm.js terminal connected over ws://127.0.0.1:PORT/pty,
 *   - auto-pairs via a token the helper passes in the URL fragment (#lt=...).
 *
 * NEW: Also supports the Sandpie Local Terminal Chrome Extension for
 * seamless PTY access without downloading a binary.
 *
 * Usage: <script type="module" src="modules/localterm.js"></script>
 */

const PORT = 8771;
const BASE = `http://127.0.0.1:${PORT}`;
const TOKEN_KEY = 'sandpie:localterm:token';
// Where the helper binaries are hosted (drop the Desktop\localterm\* files here on deploy).
const DOWNLOAD_BASE = '/modules';
const FILES = [
  ['Windows (x64)',  'localterm-windows-amd64.exe'],
  ['Windows (ARM)',  'localterm-windows-arm64.exe'],
  ['macOS (Apple Silicon)', 'localterm-macos-arm64'],
  ['macOS (Intel)',  'localterm-macos-amd64'],
  ['Linux (x64)',    'localterm-linux-amd64'],
  ['Linux (ARM)',    'localterm-linux-arm64'],
];

/* ---- Chrome Extension bridge detection ---- */
let extensionBridge = null;
let extensionAvailable = false;

function detectExtension() {
  // The content script injects window.SandpieExtensionBridge
  if (window.SandpieExtensionBridge) {
    extensionBridge = window.SandpieExtensionBridge;
    extensionAvailable = true;
    return true;
  }
  // Check for the marker injected by content script
  if (window.__sandpieExtensionAvailable) {
    extensionAvailable = true;
  }
  return extensionAvailable;
}

// Poll for extension becoming available (it may load after sandpie)
function waitForExtension(timeout = 5000) {
  return new Promise((resolve) => {
    if (detectExtension()) { resolve(true); return; }
    const interval = setInterval(() => {
      if (detectExtension()) {
        clearInterval(interval);
        resolve(true);
      }
    }, 200);
    setTimeout(() => {
      clearInterval(interval);
      resolve(false);
    }, timeout);
  });
}

/* ---- token pairing (helper opens us with #lt=<token>) ---- */
function readTokenFromHash() {
  const m = (location.hash || '').match(/[#&]lt=([a-f0-9]+)/i);
  if (m) {
    localStorage.setItem(TOKEN_KEY, m[1]);
    try { history.replaceState(null, '', location.pathname + location.search); } catch {}
    return m[1];
  }
  return localStorage.getItem(TOKEN_KEY) || '';
}
function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }

/* ---- OS / arch detection -> recommended binary ---- */
async function detectBinary() {
  let os = '', arm = false;
  const uad = navigator.userAgentData;
  const ua = navigator.userAgent || '';
  if (uad && uad.platform) os = uad.platform.toLowerCase();
  if (uad && uad.getHighEntropyValues) {
    try { const h = await uad.getHighEntropyValues(['architecture']); arm = /arm/i.test(h.architecture || ''); } catch {}
  }
  if (!os) os = /win/i.test(ua) ? 'windows' : /mac/i.test(ua) ? 'macos' : 'linux';
  else os = os.includes('win') ? 'windows' : os.includes('mac') ? 'macos' : 'linux';
  if (/aarch64|arm64/i.test(ua)) arm = true;
  // Apple Silicon usually reports Intel in UA; default modern Macs to arm64.
  const android = /android/i.test(ua);
  if (android) { os = 'linux'; if (!/x86_64|i686|x86;/i.test(ua)) arm = true; } // Android = Linux kernel, ~always arm64
  const archName = arm ? 'arm64' : 'amd64';
  const ext = os === 'windows' ? '.exe' : '';
  const file = `localterm-${os}-${archName}${ext}`;
  const label = android
    ? `Android · Linux ${arm ? 'ARM64' : 'x64'}`
    : { windows: 'Windows', macos: 'macOS', linux: 'Linux' }[os] + (arm ? ' (ARM)' : ' (x64)');
  return { os, file, label, android };
}

/* ---- presence probe (does NOT spawn a shell) ---- */
async function helperUp() {
  try {
    const r = await fetch(`${BASE}/ping`, { mode: 'cors', cache: 'no-store' });
    return r.ok;
  } catch { return false; }
}

async function extensionUp() {
  if (!extensionBridge) return false;
  try {
    const result = await extensionBridge.send('ping');
    return !!result.version;
  } catch { return false; }
}

/* ---- dynamic xterm.js load ---- */
let xtermLoaded = false;
function loadScript(src) { return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('load ' + src)); document.head.appendChild(s); }); }
function loadCss(href) { return new Promise((res) => { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href; l.onload = res; l.onerror = res; document.head.appendChild(l); }); }
async function loadXterm() {
  if (xtermLoaded) return;
  await loadCss('https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css');
  await loadScript('https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.js');
  await loadScript('https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js');
  xtermLoaded = true;
}

/* ---- UI ---- */
let term = null, ws = null, connected = false, pollTimer = null, userQuit = false;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

// ON/OFF indicator in the "Terminal" section header.
function setStatusBadge(on) {
  try {
    const el = SandpieMenu.get && SandpieMenu.get('localtermSection');
    const span = el && el.querySelector('summary span');
    if (span) { span.textContent = on ? 'ON' : 'OFF'; span.style.color = on ? '#3fb950' : 'var(--sp-text-dim)'; }
  } catch (_) {}
}

async function renderInstall(body, msg) {
  connected = false;
  setStatusBadge(false);

  // Check if Chrome extension is available
  const hasExt = await waitForExtension(1000);
  if (hasExt) {
    renderExtensionUI(body);
    return;
  }

  const { file, label, android } = await detectBinary();
  const mobile = isMobile();
  const others = FILES.filter(f => f[1] !== file)
    .map(f => `<a href="${DOWNLOAD_BASE}/${f[1]}" download style="color:var(--sp-text-dim);font-size:0.68rem;text-decoration:none;border-bottom:1px dotted var(--sp-border);">${f[0]}</a>`)
    .join(' · ');
  const intro = mobile
    ? `Use your phone's shell here — on Android via <a href="https://termux.dev" target="_blank" style="color:var(--sp-accent,#2563eb);">Termux</a> (any app that runs a Linux binary).`
    : `Run a tiny one-time helper to use your machine's terminal here.`;
  const steps = mobile
    ? `<li>In Termux: <code style="color:var(--sp-text);">chmod +x ${file} &amp;&amp; ./${file}</code></li>
        <li>Open the link it prints (or it opens sandpie) — now paired.</li>`
    : `<li>Run the downloaded file (approve your OS prompt once).</li>
        <li>It re-opens sandpie already paired — this turns into a terminal.</li>`;
  body.innerHTML = `
    <div style="font-size:0.75rem;line-height:1.5;">
      ${msg ? `<p style="color:var(--sp-text-dim);margin:0 0 0.5rem;">${esc(msg)}</p>` : ''}
      <p style="margin:0 0 0.5rem;">${intro}</p>
      <a id="ltDownload" href="${DOWNLOAD_BASE}/${file}" download
         style="display:inline-block;background:var(--sp-accent,#2563eb);color:#fff;padding:0.45rem 0.9rem;border-radius:6px;font-weight:600;text-decoration:none;">
         ⬇ Download for ${label}
      </a>
      <ol style="margin:0.7rem 0 0.4rem;padding-left:1.1rem;color:var(--sp-text-dim);">
        ${steps}
      </ol>
      <details style="margin-top:0.3rem;"><summary style="cursor:pointer;color:var(--sp-text-dim);font-size:0.7rem;">other platforms</summary>
        <div style="margin-top:0.35rem;display:flex;gap:0.5rem;flex-wrap:wrap;">${others}</div>
      </details>
      <p id="ltWait" style="margin:0.6rem 0 0;color:var(--sp-text-dim);font-size:0.7rem;">○ waiting for the helper…</p>
    </div>`;
  // poll for the helper coming up
  stopPoll();
  pollTimer = setInterval(async () => {
    if (connected) return;
    if (await helperUp()) {
      stopPoll();
      const w = body.querySelector('#ltWait'); if (w) w.innerHTML = '● helper found — connecting…';
      if (getToken()) connect(body);
      else if (w) w.innerHTML = '● helper running, but not paired. Re-run it, or open ' + BASE + ' directly.';
    }
  }, 2000);
}

/* ---- Extension UI (when Chrome extension is available) ---- */
function renderExtensionUI(body) {
  stopPoll();
  body.innerHTML = `
    <div style="font-size:0.75rem;line-height:1.5;">
      <p style="margin:0 0 0.5rem;color:var(--sp-text-dim);">Sandpie Local Terminal extension detected.</p>
      <p style="margin:0 0 0.5rem;">Connect to your local machine via the extension bridge.</p>
      <button id="ltExtConnect" style="display:inline-block;background:var(--sp-accent,#2563eb);color:#fff;padding:0.45rem 0.9rem;border-radius:6px;font-weight:600;border:0;cursor:pointer;">
        Connect to 127.0.0.1:22
      </button>
      <p id="ltExtStatus" style="margin:0.6rem 0 0;color:var(--sp-text-dim);font-size:0.7rem;">○ click to connect</p>
    </div>`;
  const btn = body.querySelector('#ltExtConnect');
  if (btn) btn.onclick = () => connectExtension(body);
}

async function connectExtension(body) {
  const statusEl = body.querySelector('#ltExtStatus');
  if (statusEl) statusEl.textContent = '● connecting…';

  try {
    const result = await extensionBridge.send('connect', {
      host: '127.0.0.1',
      port: 22
    });
    if (result.connected) {
      connected = true;
      if (statusEl) statusEl.innerHTML = '<span style="color:#3fb950;">● connected</span>';
      // Switch to terminal view
      await loadXterm();
      terminalShell(body);
      setupExtensionTerminal(body);
    } else {
      if (statusEl) statusEl.innerHTML = '<span style="color:#e06c75;">● failed: ' + esc(result.error || 'unknown error') + '</span>';
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = '<span style="color:#e06c75;">● error: ' + esc(e.message) + '</span>';
  }
}

function setupExtensionTerminal(body) {
  const host = body.querySelector('#ltTerm');
  if (!host) return;

  term = new Terminal({ fontSize: 13, cursorBlink: true, theme: { background: '#1a1a1a' } });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(host);
  fit.fit();

  // Send keystrokes to extension
  term.onData(d => {
    if (extensionBridge) {
      extensionBridge.send('data', { data: d });
    }
  });

  // Receive data from extension
  const unsubscribe = extensionBridge.onData(data => {
    if (typeof data === 'string') {
      term.write(data);
    } else if (Array.isArray(data)) {
      term.write(new Uint8Array(data));
    }
  });

  // Handle resize
  const size = () => {
    try {
      fit.fit();
      if (extensionBridge) {
        extensionBridge.send('resize', { cols: term.cols, rows: term.rows });
      }
    } catch {}
  };
  size();
  const ro = new ResizeObserver(size);
  ro.observe(host);
  term.focus();

  // Handle disconnect
  const origDisconnect = body.querySelector('#ltDisconnect');
  if (origDisconnect) {
    origDisconnect.onclick = () => {
      userQuit = true; stopPoll();
      try { unsubscribe(); } catch {}
      try { ro.disconnect(); } catch {}
      try { term && term.dispose(); } catch {}
      term = null; connected = false;
      if (extensionBridge) {
        extensionBridge.send('disconnect');
      }
      renderDisconnected(body);
    };
  }
}

function terminalShell(body) {
  stopPoll();
  body.innerHTML = `
    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;">
      <span id="ltStatus" style="font-family:ui-monospace,monospace;font-size:0.7rem;color:var(--sp-text-dim);">connecting…</span>
      <button id="ltDisconnect" style="margin-left:auto;font-size:0.68rem;padding:0.1rem 0.45rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-text-dim);cursor:pointer;">Disconnect</button>
    </div>
    <div id="ltTerm" style="height:320px;background:#1a1a1a;border:1px solid var(--sp-border);border-radius:6px;overflow:hidden;"></div>`;
  body.querySelector('#ltDisconnect').onclick = () => {
    userQuit = true; stopPoll();
    try { ws && ws.close(); } catch {}
    try { term && term.dispose(); } catch {}
    term = null; connected = false;
    renderDisconnected(body);
  };
}
function setStatus(body, text, color) { const s = body.querySelector('#ltStatus'); if (s) { s.textContent = text; s.style.color = color || 'var(--sp-text-dim)'; } }

// Shown after the user clicks Disconnect: stays disconnected (no auto-reconnect poll)
// until they explicitly click Reconnect. Closing the socket also ends the shell
// session on the helper; the helper process itself keeps running in the background.
function renderDisconnected(body) {
  stopPoll();
  setStatusBadge(false);
  body.innerHTML = `<div style="font-size:0.78rem;line-height:1.5;color:var(--sp-text-dim);">
    <p style="margin:0 0 0.5rem;">Disconnected. The localterm helper is still running in the background.</p>
    <button id="ltReconnect" style="background:var(--sp-accent,#2563eb);color:#fff;border:0;border-radius:6px;padding:0.4rem 0.85rem;font-weight:600;cursor:pointer;">Reconnect</button>
    <p style="margin:0.6rem 0 0;font-size:0.68rem;">To stop the helper entirely (it has no window): on Windows run <code style="color:var(--sp-text);">Get-Process localterm* | Stop-Process -Force</code>; mac/Linux: kill the localterm process.</p>
  </div>`;
  const b = body.querySelector('#ltReconnect');
  if (b) b.onclick = () => { userQuit = false; renderSection(body); };
}

async function connect(body) {
  const token = getToken();
  if (!token) { renderInstall(body, 'No helper paired yet.'); return; }
  await loadXterm();
  terminalShell(body);
  const host = body.querySelector('#ltTerm');
  term = new Terminal({ fontSize: 13, cursorBlink: true, theme: { background: '#1a1a1a' } });
  const fit = new FitAddon.FitAddon(); term.loadAddon(fit); term.open(host); fit.fit();
  const enc = new TextEncoder();
  let opened = false;
  ws = new WebSocket(`ws://127.0.0.1:${PORT}/pty?token=${token}`);
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => {
    opened = true; connected = true; setStatus(body, 'connected', '#3fb950'); setStatusBadge(true);
    term.onData(d => ws.send(enc.encode(d)));
    const size = () => { try { fit.fit(); ws.send('R ' + term.cols + ' ' + term.rows); } catch {} };
    size(); new ResizeObserver(size).observe(host); term.focus();
  };
  ws.onmessage = e => term.write(new Uint8Array(e.data));
  ws.onclose = () => { connected = false; setStatusBadge(false); if (userQuit) return; if (!opened) renderInstall(body, 'Helper not reachable — is localterm running?'); else setStatus(body, 'closed', '#e06c75'); };
  ws.onerror = () => { if (userQuit) return; if (!opened) renderInstall(body, `Could not reach the helper on 127.0.0.1:${PORT}.`); };
}

function isMobile() {
  return (navigator.userAgentData && navigator.userAgentData.mobile) || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
}
async function renderSection(body) {
  if (connected) return;
  if (userQuit) { renderDisconnected(body); return; }   // stay disconnected until Reconnect

  // Try extension first
  const hasExt = await waitForExtension(500);
  if (hasExt && await extensionUp()) {
    connectExtension(body);
    return;
  }

  // Fall back to localterm helper
  if (getToken() && await helperUp()) connect(body);
  else renderInstall(body, '');
}

/* ---- init ---- */
function init() {
  if (typeof SandpieMenu === 'undefined') { setTimeout(init, 500); return; }
  const paired = readTokenFromHash();
  SandpieMenu.add('localtermSection', {
    title: 'Terminal',
    open: false,               // collapsed by default
    badge: 'OFF',              // ON/OFF status shown in the section header
    html: '<div id="localtermBody" style="font-size:0.75rem;line-height:1.4;"></div>',
    onRender() { renderSection(document.getElementById('localtermBody')); },
  });
  console.log('[localterm] module registered' + (paired ? ' (paired via #lt)' : '') +
    (extensionAvailable ? ' (extension bridge available)' : ''));
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
