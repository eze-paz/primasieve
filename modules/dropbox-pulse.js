/**
 * Dropbox Pulse — ambient awareness of what the user is working on.
 *
 * Opt-in (default OFF). When enabled, does ONE full recursive metadata scan of
 * the user's Dropbox (names + timestamps only, via dropbox-full's exported
 * listFolder — file CONTENT is never read), keeps the entries modified within
 * the horizon (default 14 days), and persists the delta cursor. Every later
 * session is a cheap /list_folder/continue delta pull, same pattern as the
 * sync provider's cursor.
 *
 * From those recent entries it derives the user's ACTIVE PROJECTS (top-level
 * path clusters weighted by recency) and:
 *   - shows them in a collapsible "Pulse" sidebar section (SandpieMenu), and
 *   - injects a compact "what the user is working on" block into every system
 *     prompt (systemBlock, wired into buildSystemPrompt) so the model has
 *     standing context about the user's real work without being told.
 *
 * Privacy: enabling this sends file NAMES from the scanned area to whatever
 * model provider is configured — hence opt-in, with the scan root narrowable.
 * The sandpie working folder itself is excluded (echoing app files is noise).
 */
const SandpiePulse = (function () {
  'use strict';

  const K_ENABLED = 'pulse-enabled';      // '1' | unset (default OFF — see privacy note)
  const K_ROOT    = 'pulse-root';         // scan root, '' = whole Dropbox
  const K_DAYS    = 'pulse-days';         // horizon in days
  const K_CURSOR  = 'pulse-cursor';       // list_folder delta cursor
  const K_RECENT  = 'pulse-recent';       // JSON [{p, m}] — path + mtime(ms), horizon-trimmed
  const SECTION_ID = 'pulseSection';
  const DEF_DAYS = 14;
  const MAX_KEEP = 3000;                  // hard cap on stored entries
  const MAX_PROJECTS = 6;

  const enabled = () => localStorage.getItem(K_ENABLED) === '1';
  const root = () => localStorage.getItem(K_ROOT) || '';
  const days = () => { const v = parseInt(localStorage.getItem(K_DAYS) || '', 10); return Number.isFinite(v) && v >= 1 ? Math.min(90, v) : DEF_DAYS; };
  const horizonMs = () => days() * 86400000;

  function recent() { try { return JSON.parse(localStorage.getItem(K_RECENT) || '[]'); } catch { return []; } }
  function saveRecent(list) {
    const cut = Date.now() - horizonMs();
    const kept = list.filter(e => e.m >= cut).sort((a, b) => b.m - a.m).slice(0, MAX_KEEP);
    localStorage.setItem(K_RECENT, JSON.stringify(kept));
    return kept;
  }

  function excluded(pathLower) {
    let parent = '/r+d+i/sandpie';
    try { if (window.SandpieDbxFull) parent = SandpieDbxFull.workingParent().toLowerCase(); } catch (_) {}
    return pathLower.startsWith(parent + '/') || pathLower === parent;
  }

  // ---- scan / delta ----------------------------------------------------------
  let _busy = false;
  function _merge(entries, base) {
    const map = new Map(base.map(e => [e.p.toLowerCase(), e]));
    for (const e of entries) {
      if (!e.path) continue;
      const pl = e.path.toLowerCase();
      if (e.kind === 'deleted') { map.delete(pl); continue; }
      if (e.kind !== 'file' || excluded(pl)) continue;
      const m = Date.parse(e.cloudMtime || '');
      if (Number.isFinite(m)) map.set(pl, { p: e.path, m });
    }
    return [...map.values()];
  }

  async function fullScan(status) {
    if (_busy) return { ok: false, reason: 'busy' };
    if (!window.SandpieDbxFull || !SandpieDbxFull.isConnected()) return { ok: false, reason: 'Dropbox not connected' };
    _busy = true;
    try {
      status && status('Scanning Dropbox metadata… (one-time; large accounts take a while)');
      const r = await SandpieDbxFull.listFolder(root() || '/', { recursive: true });
      const kept = saveRecent(_merge(r.entries, []));
      localStorage.setItem(K_CURSOR, r.cursor);
      status && status('');
      return { ok: true, scanned: r.entries.length, kept: kept.length };
    } catch (e) {
      status && status('Scan failed: ' + (e && e.message));
      return { ok: false, reason: (e && e.message) || String(e) };
    } finally { _busy = false; }
  }

  async function refresh(status) {
    if (_busy || !enabled()) return { ok: false, reason: 'busy or disabled' };
    const cursor = localStorage.getItem(K_CURSOR);
    if (!cursor) return fullScan(status);
    if (!window.SandpieDbxFull || !SandpieDbxFull.isConnected()) return { ok: false, reason: 'Dropbox not connected' };
    _busy = true;
    try {
      const r = await SandpieDbxFull.listContinue(cursor);
      const kept = saveRecent(_merge(r.entries, recent()));
      localStorage.setItem(K_CURSOR, r.cursor);
      return { ok: true, delta: r.entries.length, kept: kept.length };
    } catch (e) {
      // Expired/invalid cursor (409) ⇒ full rescan rebuilds it.
      if (/409|reset/.test(String(e && e.message))) { _busy = false; localStorage.removeItem(K_CURSOR); return fullScan(status); }
      return { ok: false, reason: (e && e.message) || String(e) };
    } finally { _busy = false; }
  }

  // ---- projects --------------------------------------------------------------
  function projects() {
    const now = Date.now();
    const groups = new Map();
    for (const e of recent()) {
      const seg = e.p.split('/').filter(Boolean);
      const key = seg.length <= 1 ? '(top level)' : seg.slice(0, Math.min(2, seg.length - 1)).join('/');
      let g = groups.get(key);
      if (!g) { g = { key, score: 0, files: [] }; groups.set(key, g); }
      g.score += Math.exp(-((now - e.m) / 86400000) / 7);   // recency-weighted activity
      g.files.push(e);
    }
    const out = [...groups.values()].sort((a, b) => b.score - a.score).slice(0, MAX_PROJECTS);
    for (const g of out) { g.files.sort((a, b) => b.m - a.m); g.latest = g.files[0]; }
    return out;
  }

  const ago = (m) => {
    const d = Math.floor((Date.now() - m) / 86400000);
    return d <= 0 ? 'today' : d === 1 ? '1d ago' : d + 'd ago';
  };

  // ---- system prompt injection ------------------------------------------------
  async function systemBlock() {
    if (!enabled()) return '';
    const projs = projects();
    if (!projs.length) return '';
    const lines = ['', '', '# Dropbox pulse',
      `What the user has actually been working on — their Dropbox files modified in the last ${days()} days, clustered into projects, most active first. Use this as standing context about the user's current work; when a request is ambiguous, it likely relates to one of these.`];
    for (const g of projs) {
      const names = g.files.slice(0, 3).map(f => f.p.split('/').pop() + ' (' + ago(f.m) + ')').join(', ');
      lines.push(`- ${g.key} — ${g.files.length} file(s) active; latest: ${names}`);
    }
    return lines.join('\n');
  }

  // ---- sidebar section ---------------------------------------------------------
  let _body = null;
  function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

  function renderSection() {
    if (!_body) return;
    const connected = !!(window.SandpieDbxFull && SandpieDbxFull.isConnected());
    const on = enabled();
    const projs = on ? projects() : [];
    if (typeof SandpieMenu !== 'undefined') SandpieMenu.updateBadge(SECTION_ID, on && projs.length ? String(projs.length) : '');
    let listHtml = '';
    if (on) {
      listHtml = projs.length ? projs.map(g => `
        <div style="padding:0.3rem 0; border-top:1px solid var(--sp-border);">
          <div style="font-size:0.74rem; color:var(--sp-text); display:flex; justify-content:space-between;">
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(g.key)}</span>
            <span style="color:var(--sp-text-dim); flex-shrink:0; margin-left:0.4rem;">${g.files.length}</span>
          </div>
          <div style="font-size:0.66rem; color:var(--sp-text-dim); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(g.latest.p.split('/').pop())} · ${ago(g.latest.m)}</div>
        </div>`).join('')
        : `<div style="font-size:0.7rem; color:var(--sp-text-dim); padding:0.3rem 0;">${localStorage.getItem(K_CURSOR) ? 'No activity in the last ' + days() + ' days.' : 'Not scanned yet.'}</div>`;
    }
    _body.innerHTML = `
      <p style="font-size:0.68rem; color:var(--sp-text-dim); margin:0 0 0.45rem;">Watches your Dropbox activity (file names + dates only, never content) to learn what you're working on, and tells the model. <b>File names from the scanned area are sent to your configured model provider.</b></p>
      <label style="display:flex; align-items:center; gap:0.45rem; font-size:0.78rem; margin-bottom:0.4rem;">
        <input type="checkbox" id="pulseEnabled" style="width:auto;" ${on ? 'checked' : ''} ${connected ? '' : 'disabled'}> Enable pulse${connected ? '' : ' <span style="font-size:0.65rem; color:var(--sp-text-dim);">(connect Dropbox first)</span>'}
      </label>
      <div style="display:flex; gap:0.5rem; align-items:center; margin-bottom:0.3rem; flex-wrap:wrap;">
        <label style="font-size:0.68rem; color:var(--sp-text-dim);">Root <input type="text" id="pulseRoot" value="${esc(root())}" placeholder="/ (all)" style="width:7rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.1rem 0.3rem; font-size:0.68rem;"></label>
        <label style="font-size:0.68rem; color:var(--sp-text-dim);">Days <input type="number" id="pulseDays" value="${days()}" min="1" max="90" style="width:3rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:4px; color:var(--sp-text); padding:0.1rem 0.3rem; font-size:0.68rem;"></label>
        <button class="ghost" id="pulseRescan" style="font-size:0.68rem; padding:0.15rem 0.45rem;" ${on && connected ? '' : 'disabled'}>Rescan</button>
      </div>
      <div id="pulseStatus" style="font-size:0.66rem; color:var(--sp-warn); min-height:1em;"></div>
      <div id="pulseList">${listHtml}</div>
    `;
    const status = (msg) => { const el = _body.querySelector('#pulseStatus'); if (el) el.textContent = msg || ''; };
    _body.querySelector('#pulseEnabled').addEventListener('change', async (ev) => {
      if (ev.target.checked) {
        localStorage.setItem(K_ENABLED, '1');
        renderSection();
        if (!localStorage.getItem(K_CURSOR)) { await fullScan(status); renderSection(); }
      } else {
        // Full off-switch: drop the data too, not just the flag.
        localStorage.removeItem(K_ENABLED); localStorage.removeItem(K_CURSOR); localStorage.removeItem(K_RECENT);
        renderSection();
      }
    });
    _body.querySelector('#pulseRoot').addEventListener('change', (ev) => { localStorage.setItem(K_ROOT, ev.target.value.trim()); localStorage.removeItem(K_CURSOR); localStorage.removeItem(K_RECENT); });
    _body.querySelector('#pulseDays').addEventListener('change', (ev) => { const v = Math.min(90, Math.max(1, parseInt(ev.target.value, 10) || DEF_DAYS)); ev.target.value = v; localStorage.setItem(K_DAYS, String(v)); renderSection(); });
    const rescan = _body.querySelector('#pulseRescan');
    if (rescan) rescan.addEventListener('click', async () => { localStorage.removeItem(K_CURSOR); await fullScan(status); renderSection(); });
  }

  let _retry = 0;
  function init() {
    if (typeof SandpieMenu === 'undefined') { if (_retry++ < 40) setTimeout(init, 500); return; }
    SandpieMenu.add(SECTION_ID, { title: 'Pulse', badge: '', open: false, onRender(body) { _body = body; } });
    renderSection();
    // Session-start delta pull (cheap cursor continue), delayed so it never
    // competes with app boot / initial sync for the network.
    setTimeout(async () => { if (enabled()) { await refresh(); renderSection(); } }, 8000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { systemBlock, refresh, fullScan, projects, enabled };
})();
window.SandpiePulse = SandpiePulse;
