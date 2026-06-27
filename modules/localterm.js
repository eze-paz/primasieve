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
 * Usage: <script type="module" src="modules/localterm.js?v=1"></script>
 */

const PORT = 8771;
const BASE = `http://127.0.0.1:${PORT}`;
const TOKEN_KEY = 'sandpie:localterm:token';
// Where the helper binaries are hosted (drop the Desktop\localterm\* files here on deploy).
const DOWNLOAD_BASE = '/localterm';
const FILES = [
  ['Windows (x64)',  'localterm-windows-amd64.exe'],
  ['Windows (ARM)',  'localterm-windows-arm64.exe'],
  ['macOS (Apple Silicon)', 'localterm-macos-arm64'],
  ['macOS (Intel)',  'localterm-macos-amd64'],
  ['Linux (x64)',    'localterm-linux-amd64'],
  ['Linux (ARM)',    'localterm-linux-arm64'],
];

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
  const archName = arm ? 'arm64' : 'amd64';
  const ext = os === 'windows' ? '.exe' : '';
  const file = `localterm-${os}-${archName}${ext}`;
  const label = { windows: 'Windows', macos: 'macOS', linux: 'Linux' }[os] + (arm ? ' (ARM)' : ' (x64)');
  return { os, file, label };
}

/* ---- presence probe (does NOT spawn a shell) ---- */
async function helperUp() {
  try {
    const r = await fetch(`${BASE}/ping`, { mode: 'cors', cache: 'no-store' });
    return r.ok;
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
let term = null, ws = null, connected = false, pollTimer = null;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

async function renderInstall(body, msg) {
  connected = false;
  const { file, label } = await detectBinary();
  const others = FILES.filter(f => f[1] !== file)
    .map(f => `<a href="${DOWNLOAD_BASE}/${f[1]}" download style="color:var(--sp-text-dim);font-size:0.68rem;text-decoration:none;border-bottom:1px dotted var(--sp-border);">${f[0]}</a>`)
    .join(' · ');
  body.innerHTML = `
    <div style="font-size:0.75rem;line-height:1.5;">
      ${msg ? `<p style="color:var(--sp-text-dim);margin:0 0 0.5rem;">${esc(msg)}</p>` : ''}
      <p style="margin:0 0 0.5rem;">Run a tiny one-time helper to use your machine's terminal here.</p>
      <a id="ltDownload" href="${DOWNLOAD_BASE}/${file}" download
         style="display:inline-block;background:var(--sp-accent,#2563eb);color:#fff;padding:0.45rem 0.9rem;border-radius:6px;font-weight:600;text-decoration:none;">
         ⬇ Download for ${label}
      </a>
      <ol style="margin:0.7rem 0 0.4rem;padding-left:1.1rem;color:var(--sp-text-dim);">
        <li>Run the downloaded file (approve your OS prompt once).</li>
        <li>It re-opens sandpie already paired — this turns into a terminal.</li>
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

function terminalShell(body) {
  stopPoll();
  body.innerHTML = `
    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;">
      <span id="ltStatus" style="font-family:ui-monospace,monospace;font-size:0.7rem;color:var(--sp-text-dim);">connecting…</span>
      <button id="ltDisconnect" style="margin-left:auto;font-size:0.68rem;padding:0.1rem 0.45rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-text-dim);cursor:pointer;">Disconnect</button>
    </div>
    <div id="ltTerm" style="height:320px;background:#1a1a1a;border:1px solid var(--sp-border);border-radius:6px;overflow:hidden;"></div>`;
  body.querySelector('#ltDisconnect').onclick = () => { try { ws && ws.close(); } catch {} term && term.dispose(); term = null; connected = false; renderInstall(body, 'Disconnected.'); };
}
function setStatus(body, text, color) { const s = body.querySelector('#ltStatus'); if (s) { s.textContent = text; s.style.color = color || 'var(--sp-text-dim)'; } }

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
    opened = true; connected = true; setStatus(body, 'connected', '#3fb950');
    term.onData(d => ws.send(enc.encode(d)));
    const size = () => { try { fit.fit(); ws.send('R ' + term.cols + ' ' + term.rows); } catch {} };
    size(); new ResizeObserver(size).observe(host); term.focus();
  };
  ws.onmessage = e => term.write(new Uint8Array(e.data));
  ws.onclose = () => { connected = false; if (!opened) renderInstall(body, 'Helper not reachable — is localterm running?'); else setStatus(body, 'closed', '#e06c75'); };
  ws.onerror = () => { if (!opened) renderInstall(body, `Could not reach the helper on 127.0.0.1:${PORT}.`); };
}

async function renderSection(body) {
  if (connected) return;
  if (getToken() && await helperUp()) connect(body);
  else renderInstall(body, '');
}

/* ---- init ---- */
function init() {
  if (typeof SandpieMenu === 'undefined') { setTimeout(init, 500); return; }
  const paired = readTokenFromHash();
  SandpieMenu.add('localtermSection', {
    title: 'Terminal',
    open: !!paired,            // auto-open when the helper just paired us
    html: '<div id="localtermBody" style="font-size:0.75rem;line-height:1.4;"></div>',
    onRender() { renderSection(document.getElementById('localtermBody')); },
  });
  console.log('[localterm] module registered' + (paired ? ' (paired via #lt)' : ''));
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
