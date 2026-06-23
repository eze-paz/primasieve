/**
 * Tunnels Module for Sandpie — lightweight remote device bridge.
 *
 * Usage: <script type="module" src="modules/tunnels.js?v=1"></script>
 */

/* -------------------------------------------------------------------------- */
/*  config                                                                     */
/* -------------------------------------------------------------------------- */
const STORAGE_KEY = 'sandpie:tunnels:devices';
const DEFAULT_RELAY = (location.hostname === 'localhost') ? 'http://localhost:8080' : 'https://sandpie.gasn2cloud.com';
const DEVICE_POLL_MS = 4000;
const MAX_HISTORY = 200;

function loadDevs() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
  catch { return []; }
}
function saveDevs(devs) { localStorage.setItem(STORAGE_KEY, JSON.stringify(devs)); }

/* -------------------------------------------------------------------------- */
/*  network primitives                                                        */
/* -------------------------------------------------------------------------- */
async function relayPOST(relay, pubkey, path, body) {
  const url = `${relay}/tunnel/${pubkey}/default${path}`;
  try {
    const r = await fetch(url, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Content-Type': 'application/json' },
      credentials: 'omit',
    });
    const text = await r.text();
    try { return { ok: r.ok, status: r.status, json: JSON.parse(text), raw: text }; }
    catch { return { ok: r.ok, status: r.status, raw: text }; }
  } catch (e) { return { ok: false, status: 0, error: e.message }; }
}

/* -------------------------------------------------------------------------- */
/*  device status (one-shot poll at init)                                     */
/* -------------------------------------------------------------------------- */
async function checkDev(dev) {
  // A connected agent responds 200 to any tunnel GET, 502 if offline
  try {
    const r = await fetch(`${dev.relay}/tunnel/${dev.pubkey}/default/`, {
      method: 'GET', credentials: 'omit'
    });
    if (r.ok || r.status === 405) return { online: true, ts: Date.now() };
    if (r.status === 502) return { online: false, ts: Date.now() };
  } catch {}
  return { online: false, ts: Date.now() };
}

/* -------------------------------------------------------------------------- */
/*  deployer discovery                                                        */
/* -------------------------------------------------------------------------- */
async function discover(deployer) {
  try {
    const r = await fetch(`${DEFAULT_RELAY}/machines?deployer=${encodeURIComponent(deployer)}`, { credentials: 'omit' });
    if (!r.ok) return [];
    const data = await r.json();
    return (data.machines || []).map(m => ({
      id: m.pubkey.slice(0, 12),
      pubkey: m.pubkey,
      relay: DEFAULT_RELAY,
      label: `device-${m.pubkey.slice(0, 8)}`,
      source: 'deployer',
    }));
  } catch { return []; }
}

/* -------------------------------------------------------------------------- */
/*  terminal session                                                          */
/* -------------------------------------------------------------------------- */
const sessions = new Map();
function getSession(pubkey) {
  if (!sessions.has(pubkey)) sessions.set(pubkey, { history: [], busy: false });
  return sessions.get(pubkey);
}
function logSession(pubkey, text) {
  const s = getSession(pubkey);
  s.history.push(text);
  if (s.history.length > MAX_HISTORY) s.history.shift();
  renderTerminal(pubkey);
}
function renderTerminal(pubkey) {
  const out = document.getElementById(`tunnel-out-${pubkey}`);
  if (!out) return;
  out.textContent = getSession(pubkey).history.join('\n');
  out.scrollTop = out.scrollHeight;
}

/* -------------------------------------------------------------------------- */
/*  exec (shell)                                                              */
/* -------------------------------------------------------------------------- */
async function shellExec(dev, command) {
  const s = getSession(dev.pubkey);
  if (s.busy) return;
  s.busy = true;
  logSession(dev.pubkey, `$ ${command}`);
  try {
    const r = await relayPOST(dev.relay, dev.pubkey, '/__exec__', {
      script: command, lang: 'shell', timeout: 60,
    });
    if (r.json) {
      const d = r.json;
      if (d.stdout) logSession(dev.pubkey, d.stdout);
      if (d.stderr) logSession(dev.pubkey, 'ERR: ' + d.stderr);
      if (d.timeout) logSession(dev.pubkey, '[timed out]');
    } else {
      logSession(dev.pubkey, `[error] HTTP ${r.status} ${r.raw.slice(0,200)}`);
    }
  } catch (e) {
    logSession(dev.pubkey, `[net error] ${e.message}`);
  } finally {
    s.busy = false;
  }
}

/* -------------------------------------------------------------------------- */
/*  UI                                                                        */
/* -------------------------------------------------------------------------- */
let activePubkey = null;
let pollDone = false;

function htmlEsc(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function renderTunnels() {
  const host = document.getElementById('tunnelsBody');
  if (!host) return;
  const devs = loadDevs();

  let html = '<div style="margin-bottom:0.5rem;display:flex;gap:0.35rem;flex-wrap:wrap;">';
  if (!pollDone) {
    html += '<button id="tunnelsPollBtn" style="font-size:0.72rem;padding:0.2rem 0.5rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-text-dim);cursor:pointer;">Check status</button>';
  }
  html += '<button id="tunnelsAddBtn" style="font-size:0.72rem;padding:0.2rem 0.5rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-text-dim);cursor:pointer;">+ Device</button>';
  html += '<button id="tunnelsDeployerBtn" style="font-size:0.72rem;padding:0.2rem 0.5rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-text-dim);cursor:pointer;">+ Deployer</button>';
  html += '</div>';

  if (!devs.length) {
    html += '<p style="color:var(--sp-text-dim);font-size:0.75rem;">No devices. Add one or use deployer discovery.</p>';
  }

  for (const d of devs) {
    const dot = d.online ? '<span style="color:#3fb950;">●</span> Online' : '<span style="color:var(--sp-text-dim);">○</span> Offline';
    const active = activePubkey === d.pubkey;
    html += `
      <div style="border-bottom:1px solid var(--sp-border);padding:0.35rem 0;">
        <div style="display:flex;align-items:center;gap:0.4rem;">
          <span style="font-size:0.7rem;">${dot}</span>
          <strong style="font-size:0.78rem;">${htmlEsc(d.label || d.id)}</strong>
          <span style="margin-left:auto;color:var(--sp-text-dim);font-size:0.65rem;">${htmlEsc(d.pubkey.slice(0,16))}…</span>
        </div>
        <div style="display:flex;gap:0.3rem;margin-top:0.25rem;align-items:center;">
          <button data-term="${d.pubkey}" style="font-size:0.68rem;padding:0.1rem 0.4rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-text-dim);cursor:pointer;">${active ? 'Close' : 'Terminal'}</button>
          <button data-del="${d.pubkey}" style="font-size:0.68rem;padding:0.1rem 0.4rem;border:1px solid var(--sp-border);border-radius:4px;background:transparent;color:var(--sp-accent-neg,#e06c75);cursor:pointer;">Remove</button>
        </div>
        ${active ? terminalHTML(d.pubkey) : ''}
      </div>`;
  }
  host.innerHTML = html;

  host.querySelectorAll('button[data-term]').forEach(b => {
    b.onclick = () => {
      activePubkey = (activePubkey === b.dataset.term) ? null : b.dataset.term;
      if (activePubkey) setTimeout(() => renderTerminal(activePubkey), 50);
      renderTunnels();
    };
  });
  host.querySelectorAll('button[data-del]').forEach(b => {
    b.onclick = () => {
      if (!confirm('Remove this device?')) return;
      saveDevs(loadDevs().filter(d => d.pubkey !== b.dataset.del));
      if (activePubkey === b.dataset.del) activePubkey = null;
      renderTunnels();
    };
  });

  const pollBtn = document.getElementById('tunnelsPollBtn');
  if (pollBtn) pollBtn.onclick = runPoll;

  const addBtn = document.getElementById('tunnelsAddBtn');
  if (addBtn) addBtn.onclick = () => addDeviceDialog();

  const depBtn = document.getElementById('tunnelsDeployerBtn');
  if (depBtn) depBtn.onclick = () => addDeployerDialog();

  if (activePubkey) {
    const inp = document.getElementById(`tunnel-in-${activePubkey}`);
    if (inp) inp.focus();
  }
}

function terminalHTML(pubkey) {
  return `
    <div style="margin-top:0.4rem;">
      <pre id="tunnel-out-${pubkey}" style="background:var(--sp-bg,#1a1a1a);border:1px solid var(--sp-border);border-radius:4px;padding:0.4rem;font-size:0.72rem;height:200px;overflow:auto;white-space:pre-wrap;word-break:break-word;margin:0;color:var(--sp-text,#ccc);"></pre>
      <div style="display:flex;gap:0.3rem;margin-top:0.3rem;">
        <input id="tunnel-in-${pubkey}" placeholder="type $ cmd and hit Enter…" autocomplete="off" spellcheck="false"
          style="flex:1;padding:0.35rem;font-size:0.73rem;background:var(--sp-panel);color:var(--sp-text);border:1px solid var(--sp-border);border-radius:4px;"
          onkeydown="if(event.key==='Enter')TunnelShell.submit('${pubkey}')">
      </div>
    </div>`;
}

function addDeviceDialog() {
  const label = prompt('Device label (e.g. work-laptop):')?.trim();
  if (!label) return;
  const pubkey = prompt('Paste device pubkey (43 chars):')?.trim();
  if (!pubkey || pubkey.length < 20) { alert('Invalid pubkey'); return; }
  const relay = prompt('Relay URL:', DEFAULT_RELAY)?.trim() || DEFAULT_RELAY;
  const devs = loadDevs();
  if (devs.find(d => d.pubkey === pubkey)) { alert('Device already exists'); return; }
  devs.push({ id: pubkey.slice(0, 12), pubkey, relay, label, source: 'manual' });
  saveDevs(devs);
  renderTunnels();
  runPoll();
}

async function addDeployerDialog() {
  const key = prompt('Paste deployer pubkey:')?.trim();
  if (!key) return;
  const found = await discover(key);
  if (!found.length) { alert('No machines found for that deployer key.'); return; }
  const devs = loadDevs();
  for (const f of found) {
    if (!devs.find(d => d.pubkey === f.pubkey)) devs.push(f);
  }
  saveDevs(devs);
  renderTunnels();
  runPoll();
}

/* -------------------------------------------------------------------------- */
/*  global shell submit                                                       */
/* -------------------------------------------------------------------------- */
window.TunnelShell = {
  submit(pubkey) {
    const inp = document.getElementById(`tunnel-in-${pubkey}`);
    if (!inp) return;
    const cmd = inp.value.trim();
    if (!cmd) return;
    inp.value = '';
    const dev = loadDevs().find(d => d.pubkey === pubkey);
    if (!dev) return;
    shellExec(dev, cmd);
  }
};

/* -------------------------------------------------------------------------- */
/*  one-shot poll                                                             */
/* -------------------------------------------------------------------------- */
async function runPoll() {
  pollDone = true;
  const devs = loadDevs();
  for (const d of devs) {
    const st = await checkDev(d);
    d.online = st.online;
    await new Promise(r => setTimeout(r, 300));
  }
  saveDevs(devs);
  renderTunnels();
  if (typeof SandpieMenu !== 'undefined') {
    SandpieMenu.updateBadge('tunnelsSection', String(devs.filter(d => d.online).length));
  }
}

/* -------------------------------------------------------------------------- */
/*  init                                                                       */
/* -------------------------------------------------------------------------- */
function init() {
  if (typeof SandpieMenu === 'undefined') { setTimeout(init, 500); return; }
  SandpieMenu.add('tunnelsSection', {
    title: 'Devices',
    badge: '0',
    open: false,
    html: '<div id="tunnelsBody" style="font-size:0.75rem;line-height:1.4;"></div>',
    onRender() { renderTunnels(); },
  });
  setTimeout(runPoll, 600);
  console.log('[tunnels] module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
