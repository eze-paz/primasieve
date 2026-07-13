/**
 * Second Brain — sidebar visualization of the memory store.
 *
 * Renders the facts in sandpie/memory/ (via SandpieMemory.list) as a living
 * constellation: one node per fact, clustered by type, edges from [[name]]
 * links in fact bodies (nearest same-type neighbor as fallback so nothing
 * floats orphaned). Above it a running count with a "+N today" badge; below
 * it a 30-day cumulative sparkline of the store growing.
 *
 * Registered as a collapsible SandpieMenu section. The requestAnimationFrame
 * loop runs ONLY while the <details> is open AND the tab is visible — a
 * collapsed section costs nothing. Re-renders on the memory:changed event
 * (lazily when collapsed: marked dirty, rebuilt on next open).
 *
 * All colors come from the --sp-* theme variables (SVG fills via CSS classes),
 * so every theme — including aurora — restyles it for free.
 */
const SandpieSecondBrain = (function () {
  'use strict';

  const SECTION_ID = 'secondBrainSection';
  const TYPE_CLASS = { user: 'sb-user', feedback: 'sb-feedback', project: 'sb-project', reference: 'sb-reference' };
  const TYPE_LABEL = { user: 'you', feedback: 'feedback', project: 'projects', reference: 'reference' };
  const W = 240, H = 170;   // viewBox; scales to sidebar width

  const CSS = `
    #${SECTION_ID} .sb-count { font-size:1.5rem; font-weight:600; color:var(--sp-text); line-height:1; }
    #${SECTION_ID} .sb-count-row { display:flex; align-items:baseline; gap:0.4rem; margin-bottom:0.3rem; }
    #${SECTION_ID} .sb-count-lbl { font-size:0.7rem; color:var(--sp-text-dim); }
    #${SECTION_ID} .sb-today { font-size:0.65rem; color:var(--sp-success); border:1px solid var(--sp-success); border-radius:8px; padding:0 0.35rem; }
    #${SECTION_ID} svg.sb-net { width:100%; height:auto; display:block; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:8px; }
    #${SECTION_ID} .sb-node { cursor:pointer; }
    #${SECTION_ID} .sb-user      { fill:var(--sp-success); }
    #${SECTION_ID} .sb-feedback  { fill:var(--sp-warn); }
    #${SECTION_ID} .sb-project   { fill:var(--sp-accent); }
    #${SECTION_ID} .sb-reference { fill:var(--sp-text-dim); }
    #${SECTION_ID} .sb-edge { stroke:var(--sp-border-bright); stroke-width:0.7; opacity:0.6; }
    #${SECTION_ID} .sb-edge.sb-link { stroke:var(--sp-accent); opacity:0.5; }
    #${SECTION_ID} .sb-new { stroke:var(--sp-accent); stroke-width:1.2; }
    #${SECTION_ID} .sb-legend { display:flex; flex-wrap:wrap; gap:0.15rem 0.6rem; margin:0.3rem 0 0.1rem; }
    #${SECTION_ID} .sb-legend span { font-size:0.62rem; color:var(--sp-text-dim); display:flex; align-items:center; gap:0.25rem; }
    #${SECTION_ID} .sb-legend i { width:7px; height:7px; border-radius:50%; display:inline-block; }
    #${SECTION_ID} .sb-hover { font-size:0.66rem; color:var(--sp-text-dim); min-height:2em; line-height:1.3; margin-top:0.25rem;
      overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
    #${SECTION_ID} .sb-hover b { color:var(--sp-text); font-weight:600; }
    #${SECTION_ID} svg.sb-spark { width:100%; height:26px; display:block; margin-top:0.3rem; }
    #${SECTION_ID} .sb-spark-line { fill:none; stroke:var(--sp-accent); stroke-width:1.2; }
    #${SECTION_ID} .sb-spark-fill { fill:var(--sp-accent-dim); stroke:none; }
    #${SECTION_ID} .sb-spark-lbl { font-size:0.6rem; color:var(--sp-text-dim); margin-top:0.1rem; }
    #${SECTION_ID} .sb-empty { font-size:0.72rem; color:var(--sp-text-dim); padding:0.4rem 0; }
  `;

  // Deterministic per-fact jitter so the constellation is stable across renders.
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rand01(seed, n) { const x = Math.sin(seed * 12.9898 + n * 78.233) * 43758.5453; return x - Math.floor(x); }

  const CLUSTERS = {   // anchor per type inside the viewBox
    user:      { x: W * 0.24, y: H * 0.32 },
    feedback:  { x: W * 0.72, y: H * 0.26 },
    project:   { x: W * 0.34, y: H * 0.70 },
    reference: { x: W * 0.76, y: H * 0.68 },
  };

  let _body = null;        // .service-body we render into
  let _detailsEl = null;   // the <details> section
  let _nodes = [];         // { el, x, y, r, phase, isNew }
  let _raf = 0;
  let _t = 0;
  let _dirty = true;       // needs rebuild on next open

  function running() { return !!(_detailsEl && _detailsEl.open && document.visibilityState === 'visible' && _nodes.length); }

  function tick() {
    _raf = 0;
    if (!running()) return;
    _t += 0.025;
    for (const n of _nodes) {
      n.el.setAttribute('cy', (n.y + Math.sin(_t + n.phase) * 1.5).toFixed(2));
      if (n.isNew) n.el.setAttribute('fill-opacity', (0.55 + 0.45 * (Math.sin(_t * 2 + n.phase) + 1) / 2).toFixed(2));
    }
    _raf = requestAnimationFrame(tick);
  }
  function startAnim() { if (!_raf && running()) _raf = requestAnimationFrame(tick); }
  function stopAnim() { if (_raf) { cancelAnimationFrame(_raf); _raf = 0; } }

  function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
  const dayMs = 86400000;
  const today = () => new Date().toISOString().slice(0, 10);

  async function render() {
    if (!_body) return;
    _dirty = false;
    stopAnim();
    _nodes = [];
    let facts = [];
    try { facts = await SandpieMemory.list(); } catch (_) {}

    if (typeof SandpieMenu !== 'undefined') SandpieMenu.updateBadge(SECTION_ID, String(facts.length || ''));

    if (!facts.length) {
      _body.innerHTML = `<div class="sb-empty">No memories yet — sandpie saves durable facts as you work, and they'll appear here as a growing constellation.</div>`;
      return;
    }

    const td = today();
    const newToday = facts.filter(f => (f.created || '').slice(0, 10) === td).length;

    // --- layout: cluster by type, deterministic jitter by name hash ---------
    const pos = facts.map(f => {
      const c = CLUSTERS[f.type] || CLUSTERS.reference;
      const h = hash(f.name);
      const a = rand01(h, 1) * Math.PI * 2;
      const r = 8 + rand01(h, 2) * 34;
      return {
        f,
        x: Math.min(W - 6, Math.max(6, c.x + Math.cos(a) * r)),
        y: Math.min(H - 6, Math.max(6, c.y + Math.sin(a) * r * 0.75)),
        s: 1.8 + rand01(h, 3) * 1.8,
      };
    });
    const byName = new Map(pos.map((p, i) => [p.f.name, i]));

    // --- edges: real [[links]] first, nearest same-type neighbor as fallback -
    const edges = [];
    const linked = new Set();
    pos.forEach((p, i) => {
      const re = /\[\[([a-z0-9-]+)\]\]/g; let m;
      while ((m = re.exec(p.f.body || '')) !== null) {
        const j = byName.get(m[1]);
        if (j !== undefined && j !== i) { edges.push([i, j, true]); linked.add(i); linked.add(j); }
      }
    });
    pos.forEach((p, i) => {
      if (linked.has(i)) return;
      let best = -1, bd = Infinity;
      pos.forEach((q, j) => {
        if (i === j || q.f.type !== p.f.type) return;
        const d = (p.x - q.x) ** 2 + (p.y - q.y) ** 2;
        if (d < bd) { bd = d; best = j; }
      });
      if (best >= 0 && bd < 2200) edges.push([i, best, false]);
    });

    const edgeSvg = edges.map(([i, j, isLink]) =>
      `<line class="sb-edge${isLink ? ' sb-link' : ''}" x1="${pos[i].x.toFixed(1)}" y1="${pos[i].y.toFixed(1)}" x2="${pos[j].x.toFixed(1)}" y2="${pos[j].y.toFixed(1)}"/>`).join('');
    const nodeSvg = pos.map((p, i) => {
      const isNew = (p.f.created || '').slice(0, 10) === td;
      return `<circle class="sb-node ${TYPE_CLASS[p.f.type] || 'sb-reference'}${isNew ? ' sb-new' : ''}" data-i="${i}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${p.s.toFixed(1)}"/>`;
    }).join('');

    // --- sparkline: cumulative store size over the last 30 days --------------
    const now = Date.now();
    const counts = new Array(30).fill(0);
    let before = 0;
    for (const f of facts) {
      const t = Date.parse(f.created || '');
      if (!Number.isFinite(t)) { before++; continue; }
      const age = Math.floor((now - t) / dayMs);
      if (age >= 30) before++; else counts[29 - Math.min(29, Math.max(0, age))]++;
    }
    let acc = before;
    const cum = counts.map(c => (acc += c));
    const max = Math.max(1, cum[29]), min = Math.min(before, cum[0]);
    const span = Math.max(1, max - min);
    const sx = i => (i * (W / 29)).toFixed(1);
    const sy = v => (22 - ((v - min) / span) * 18).toFixed(1);
    const linePts = cum.map((v, i) => `${sx(i)},${sy(v)}`).join(' ');

    _body.innerHTML = `
      <div class="sb-count-row">
        <span class="sb-count" id="sbCount">${facts.length}</span>
        <span class="sb-count-lbl">memories</span>
        ${newToday ? `<span class="sb-today">+${newToday} today</span>` : ''}
      </div>
      <svg class="sb-net" viewBox="0 0 ${W} ${H}" role="img" aria-label="Constellation of ${facts.length} memories">${edgeSvg}${nodeSvg}</svg>
      <div class="sb-legend">${Object.keys(TYPE_CLASS).map(t =>
        `<span><i class="${TYPE_CLASS[t]}" style="background:var(${t === 'user' ? '--sp-success' : t === 'feedback' ? '--sp-warn' : t === 'project' ? '--sp-accent' : '--sp-text-dim'})"></i>${TYPE_LABEL[t]}</span>`).join('')}</div>
      <div class="sb-hover" id="sbHover">hover a memory</div>
      <svg class="sb-spark" viewBox="0 0 ${W} 26" role="img" aria-label="Memory growth over the last 30 days">
        <polygon class="sb-spark-fill" points="0,24 ${linePts} ${W},24"/>
        <polyline class="sb-spark-line" points="${linePts}"/>
      </svg>
      <div class="sb-spark-lbl">last 30 days</div>
    `;

    const hover = _body.querySelector('#sbHover');
    const svg = _body.querySelector('svg.sb-net');
    svg.querySelectorAll('circle.sb-node').forEach(el => {
      const i = +el.dataset.i, p = pos[i];
      _nodes.push({ el, x: p.x, y: p.y, phase: rand01(hash(p.f.name), 4) * Math.PI * 2, isNew: el.classList.contains('sb-new') });
      el.addEventListener('mouseenter', () => { el.setAttribute('r', (p.s * 1.9).toFixed(1)); hover.innerHTML = `<b>${esc(p.f.name)}</b> · ${esc(p.f.description)}`; });
      el.addEventListener('mouseleave', () => { el.setAttribute('r', p.s.toFixed(1)); hover.textContent = 'hover a memory'; });
      el.addEventListener('click', () => {
        if (typeof SandpieCommands !== 'undefined' && SandpieCommands.dispatch) SandpieCommands.dispatch('>>> memory show ' + p.f.name);
      });
    });

    startAnim();
  }

  function onSectionToggle() {
    if (_detailsEl && _detailsEl.open) { if (_dirty) render(); else startAnim(); }
    else stopAnim();
  }

  let _retry = 0;
  function init() {
    if (typeof SandpieMenu === 'undefined' || typeof SandpieMemory === 'undefined') {
      if (_retry++ < 40) setTimeout(init, 500);
      return;
    }
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    SandpieMenu.add(SECTION_ID, {
      title: 'Second brain', badge: '…', open: false,
      onRender(body) { _body = body; },
    });
    _detailsEl = SandpieMenu.get(SECTION_ID);
    if (_detailsEl) _detailsEl.addEventListener('toggle', onSectionToggle);
    document.addEventListener('visibilitychange', () => { document.visibilityState === 'visible' ? startAnim() : stopAnim(); });

    if (typeof Sandpie !== 'undefined' && Sandpie.events) {
      Sandpie.events.on('memory:changed', () => {
        if (_detailsEl && _detailsEl.open) render();
        else { _dirty = true; SandpieMemory.list().then(f => SandpieMenu.updateBadge(SECTION_ID, String(f.length || ''))).catch(() => {}); }
      });
    }

    // First render happens lazily on open; but populate the badge right away.
    render().then(() => { if (!_detailsEl.open) stopAnim(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return { render };
})();
window.SandpieSecondBrain = SandpieSecondBrain;
