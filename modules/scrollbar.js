/* sandpie — rail scrollbar (v=2)
   Hides the browser's scrollbar on a host and draws a custom "rail": a
   hairline track, a square thumb, and (optionally) one accent tick where each
   of the user's turns begins, so the bar doubles as a turn index.
   Scope is deliberately narrow — two hosts:
     • every mounted .conv-host (main + side pane), WITH ticks;
     • the <aside> sidebar, WITHOUT ticks, desktop only.
   Settings, home, file viewer, and artifact iframes keep the native bar (see
   sandpie.css "Scrollbars — quiet native style").

   Ghost behaviour: the rail is invisible while the conversation is at rest and
   fades in on hover, focus-within, drag, or for 900ms after any scroll.

   The rail is appended to a MOUNT element (an ancestor with position:relative)
   and placed with getBoundingClientRect deltas, so it never lives inside the
   scroller: a child of the scroller would scroll away, or lag a frame behind
   compositor-thread scrolling. Conversation rails mount in their pane
   (#messages / #messagesSide); the sidebar rail mounts in <body>.

   Attachment is by observation, not by id: .conv-host elements are created in
   ensureStream() and mounted / unmounted / moved between #messages and
   #messagesSide as conversations open, close, and swap panes. A MutationObserver
   on #messagesWrap attaches a rail to any host that enters the DOM and detaches
   it when the host leaves. The rail lives in the PANE (the host's parent), not
   inside the host, so it never touches the host's flex gap, scroll anchoring,
   or first-child home plumbing. The side pane in artifact/viewer mode hides its
   host via display:none; the ResizeObserver sees the 0×0 box and hides the rail.

   Cost while streaming: a MutationObserver on the host coalesces every token
   into one requestAnimationFrame that reads scrollHeight/scrollTop and writes
   one transform. Ticks are only re-measured when the user-turn count changes or
   the host resizes — never per token. */
(function () {
  'use strict';

  const INSET = 6;        // px the rail stops short of the host's top/bottom edges
  const MIN_THUMB = 24;   // px
  const MAX_THUMB = 0.30; // of the track — a proportional thumb on a barely-scrolling host is a full-height slab; cap it
  const IDLE_MS = 900;    // fade-out delay after the last scroll
  const HOST_SEL = '.conv-host';
  const TICK_SEL = ':scope > .msg.user';
  const RAIL_W = 10;      // px, matches .osb-rail width in sandpie.css
  const RIGHT_GAP = 4;    // px between the rail and the host's right edge
  const rails = new WeakMap();   // host → Rail
  const reduced = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  class Rail {
    constructor(host, opts) {
      this.host = host;
      this.opts = Object.assign({ mount: host.parentElement, ticks: true, cls: '' }, opts);
      const pane = this.pane = this.opts.mount;
      pane.classList.add('osb-pane');
      host.classList.add('osb-host');

      const rail = this.rail = document.createElement('div');
      rail.className = 'osb-rail' + (this.opts.cls ? ' ' + this.opts.cls : '');
      rail.setAttribute('aria-hidden', 'true');   // keyboard + wheel scrolling of the host is untouched
      const thumb = this.thumb = document.createElement('div');
      thumb.className = 'osb-thumb';
      rail.appendChild(thumb);
      const ticks = this.ticks = document.createElement('div');
      ticks.className = 'osb-ticks';
      rail.appendChild(ticks);
      pane.appendChild(rail);

      this._raf = 0; this._idleT = 0; this._tickCount = -1; this._tickMeasured = 0; this._tickTops = []; this._hover = false; this._focus = false; this._drag = false;

      // ---- sync triggers ------------------------------------------------
      this._onScroll = () => { this.request(); this.activity(); };
      host.addEventListener('scroll', this._onScroll, { passive: true });
      this._ro = new ResizeObserver(() => { this._tickCount = -1; this.request(); });   // size change ⇒ ticks move
      this._ro.observe(host);
      this._mo = new MutationObserver(() => this.request());
      this._mo.observe(host, { childList: true, subtree: true, characterData: true });

      // ---- ghost visibility --------------------------------------------
      this._enter = () => { this._hover = true; this.show(); };
      this._leave = () => { this._hover = false; this.show(); };
      host.addEventListener('pointerenter', this._enter);
      host.addEventListener('pointerleave', this._leave);
      rail.addEventListener('pointerenter', this._enter);
      rail.addEventListener('pointerleave', this._leave);
      this._focusIn = () => { this._focus = true; this.show(); };
      this._focusOut = () => { this._focus = host.contains(document.activeElement); this.show(); };
      host.addEventListener('focusin', this._focusIn);
      host.addEventListener('focusout', this._focusOut);

      // ---- drag ---------------------------------------------------------
      let startY = 0, startTop = 0;
      thumb.addEventListener('pointerdown', e => {
        e.preventDefault();
        startY = e.clientY; startTop = host.scrollTop;
        this._drag = true; rail.classList.add('osb-dragging'); this.show();
        try { thumb.setPointerCapture(e.pointerId); } catch (_) {}
      });
      thumb.addEventListener('pointermove', e => {
        if (!this._drag) return;
        const g = this.geom(); if (!g) return;
        host.scrollTop = startTop + (e.clientY - startY) * (g.max / (g.trackH - g.thumbH));
      });
      const end = () => { if (!this._drag) return; this._drag = false; rail.classList.remove('osb-dragging'); this.activity(); };
      thumb.addEventListener('pointerup', end);
      thumb.addEventListener('pointercancel', end);

      // ---- click on the track: jump a viewport toward the click ----------
      rail.addEventListener('pointerdown', e => {
        if (e.target === thumb) return;
        const g = this.geom(); if (!g) return;
        const y = e.clientY - rail.getBoundingClientRect().top;
        host.scrollTo({ top: (y / g.trackH) * g.sh - g.ch / 2, behavior: reduced() ? 'auto' : 'smooth' });
      });

      this.request();
    }

    geom() {
      const h = this.host, sh = h.scrollHeight, ch = h.clientHeight, max = sh - ch;
      if (ch === 0 || max <= 1) return null;   // hidden host (side pane in artifact mode) or nothing to scroll
      const trackH = Math.max(0, ch - INSET * 2);
      // Proportional thumb, floored at MIN_THUMB and capped at MAX_THUMB of the
      // track. Position is still frac * (trackH - thumbH), so a capped thumb just
      // travels a longer path — top and bottom of the content stay reachable.
      const thumbH = Math.min(Math.max(MIN_THUMB, Math.round(trackH * MAX_THUMB)), Math.max(MIN_THUMB, Math.round(ch / sh * trackH)));
      return { sh, ch, max, trackH, thumbH };
    }

    request() { if (!this._raf) this._raf = requestAnimationFrame(() => { this._raf = 0; this.sync(); }); }

    sync() {
      const h = this.host, g = this.geom();
      this.rail.hidden = !g;
      if (!g) return;
      // Rail geometry in mount coordinates (mount is position:relative).
      const hr = h.getBoundingClientRect(), mr = this.pane.getBoundingClientRect();
      this.rail.style.top = Math.round(hr.top - mr.top + this.pane.scrollTop + INSET) + 'px';
      this.rail.style.left = Math.round(hr.right - mr.left + this.pane.scrollLeft - RIGHT_GAP - RAIL_W) + 'px';
      this.rail.style.height = g.trackH + 'px';
      const frac = h.scrollTop / g.max;
      const y = Math.round(frac * (g.trackH - g.thumbH));
      this.thumb.style.height = g.thumbH + 'px';
      this.thumb.style.transform = 'translateY(' + y + 'px)';
      // Ticks: measure (N getBoundingClientRect) only when a user turn is added,
      // the host resizes, or at most every 500ms while content is changing;
      // otherwise just re-place the cached content offsets against the new
      // scrollHeight, which is what moves them as a reply streams in.
      if (!this.opts.ticks) return;
      const userTurns = h.querySelectorAll(TICK_SEL);
      const now = performance.now();
      if (userTurns.length !== this._tickCount || now - this._tickMeasured > 500) this.measureTicks(userTurns, now);
      this.placeTicks(g);
    }

    measureTicks(els, now) {
      this._tickCount = els.length; this._tickMeasured = now;
      const hostTop = this.host.getBoundingClientRect().top - this.host.scrollTop;   // content origin in viewport px
      this._tickTops = Array.from(els, el => el.getBoundingClientRect().top - hostTop);
      if (this.ticks.childElementCount !== els.length) {
        const frag = document.createDocumentFragment();
        for (let i = 0; i < els.length; i++) frag.appendChild(document.createElement('i'));
        this.ticks.replaceChildren(frag);
      }
    }
    placeTicks(g) {
      const tops = this._tickTops || [], kids = this.ticks.children;
      for (let i = 0; i < kids.length; i++) kids[i].style.top = Math.round(tops[i] / g.sh * g.trackH) + 'px';
    }

    activity() {
      this.rail.classList.add('osb-scrolling');
      clearTimeout(this._idleT);
      this._idleT = setTimeout(() => { this.rail.classList.remove('osb-scrolling'); this.show(); }, IDLE_MS);
    }
    show() { this.rail.classList.toggle('osb-show', this._hover || this._focus || this._drag); }

    detach() {
      const h = this.host;
      h.removeEventListener('scroll', this._onScroll);
      h.removeEventListener('pointerenter', this._enter); h.removeEventListener('pointerleave', this._leave);
      h.removeEventListener('focusin', this._focusIn); h.removeEventListener('focusout', this._focusOut);
      this._ro.disconnect(); this._mo.disconnect();
      cancelAnimationFrame(this._raf); clearTimeout(this._idleT);
      this.rail.remove();
      h.classList.remove('osb-host');
    }
  }

  function attach(host, opts) {
    if (rails.has(host) || !host.parentElement) return;
    rails.set(host, new Rail(host, opts));
  }
  function detach(host) {
    const r = rails.get(host); if (!r) return;
    r.detach(); rails.delete(host);
  }

  function boot() {
    if (window.__spOff && window.__spOff('rail')) return;   // ?off=rail bisect switch
    // Sidebar: the <aside> is its own scroll container; mount in <body> (made
    // position:relative in sandpie.css) so the rail sits outside the scroller.
    // No ticks — a list of chats has no "turns". Hidden on mobile by CSS: the
    // drawer there is position:fixed with an animated left, and the phone's own
    // overlay indicator is the right behaviour under touch anyway.
    const aside = document.querySelector('body > aside');
    if (aside) attach(aside, { mount: document.body, ticks: false, cls: 'osb-aside' });

    const wrap = document.getElementById('messagesWrap');
    if (!wrap) return;
    wrap.querySelectorAll(HOST_SEL).forEach(h => attach(h));
    // Hosts mount/unmount as conversations open, close, and move between panes.
    // A host moved from one pane to the other is a removal + an addition in the
    // same batch, so process removals first and let the addition re-attach it
    // to its new parent.
    new MutationObserver(records => {
      const removed = new Set(), added = new Set();
      for (const rec of records) {
        rec.removedNodes.forEach(n => { if (n.nodeType !== 1) return; if (n.matches(HOST_SEL)) removed.add(n); n.querySelectorAll && n.querySelectorAll(HOST_SEL).forEach(h => removed.add(h)); });
        rec.addedNodes.forEach(n => { if (n.nodeType !== 1) return; if (n.matches(HOST_SEL)) added.add(n); n.querySelectorAll && n.querySelectorAll(HOST_SEL).forEach(h => added.add(h)); });
      }
      removed.forEach(detach);
      added.forEach(h => { if (h.isConnected) attach(h); });   // default opts: mount = pane, ticks on
    }).observe(wrap, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  window.SandpieScrollbar = { attach, detach, _rails: rails };
})();
