/**
 * Screenshot Module for Sandpie
 *
 * Client-side capture of artifacts as raster images, so the model can SEE what it
 * built instead of inferring layout from source. No server, no headless browser.
 *
 * HOW IT WORKS (and why this shape)
 * ---------------------------------
 * HTML artifacts are rasterized through SVG <foreignObject>: the document is
 * serialized into an <svg><foreignObject>, loaded as an <img>, and drawn to a
 * canvas. The BROWSER'S OWN layout+paint engine renders the foreignObject, so
 * typography, flexbox/grid, borders, shadows, gradients and inline SVG come out
 * pixel-identical. This is not a JS reimplementation of CSS (that's html2canvas,
 * which is both slower and less faithful).
 *
 * The capture runs INSIDE the artifact frame, via a bootstrap injected by
 * opfs.toUrl (the same injection point as the console capture). That placement is
 * what makes this accurate:
 *   - live <canvas> bitmaps are readable (a serialized <canvas> carries no pixels)
 *   - getContext is patched to force preserveDrawingBuffer, so WebGL artifacts
 *     capture instead of coming out blank — this MUST run before the artifact's
 *     own scripts, hence the head injection
 *   - form state (value/checked/selected) is a property, not an attribute, so it
 *     only survives if read live
 *   - the artifact IS the captured document, so there is no nested-iframe blind
 *     spot (the usual blocker when rasterizing from a parent page)
 * Because the whole document is serialized — <style> blocks included — CSS rules,
 * pseudo-elements and @font-face all apply natively. No style inlining, no
 * computed-style flattening, no library.
 *
 * Known unfixable gaps are REPORTED rather than hidden (see collectWarnings):
 * backdrop-filter, cross-origin images without CORS, scrolled containers, shadow
 * DOM. A model told its screenshot is suspect reasons correctly; one silently
 * handed a wrong image does not.
 *
 * iOS/WebKit workarounds are baked in, not bolted on later:
 *   - foreignObject is given explicit width/height (Safari renders nothing without)
 *   - img.decode() instead of onload (onload fires before pixels exist)
 *   - the rasterize pass runs TWICE (Safari's first attempt silently no-ops)
 *
 * Usage:
 *   await SandpieScreenshot.capture('sandpie/artifacts/x.html', { width: 1280 })
 *     -> { dataUrl, width, height, warnings: [] }
 */

(function () {
  'use strict';

  const SHOT_TIMEOUT = 25000;
  const DEFAULT_W = 1280;
  const DEFAULT_H = 800;
  const MAX_PX = 16384;          // Chrome's canvas dimension ceiling
  const MAX_FIT_W = 4096;        // ceiling for auto-widening to fit overflowing content

  /* ---------------------------------------------------------------------- */
  /*  In-frame engine (stringified into the artifact via opfs.toUrl)         */
  /* ---------------------------------------------------------------------- */

  // Runs FIRST, before the artifact's own scripts. Forcing preserveDrawingBuffer
  // is the single highest-value line in this file: three.js and friends default it
  // to false, which leaves the framebuffer cleared by the time toDataURL runs, so
  // every WebGL artifact would otherwise capture as an empty rectangle.
  function __sandpieShotPatch() {
    if (window.__sandpieShotPatched) return;
    window.__sandpieShotPatched = 1;
    try {
      const orig = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (type, attrs) {
        if (/webgl/i.test(String(type))) {
          attrs = attrs || {};
          if (attrs.preserveDrawingBuffer === undefined) attrs.preserveDrawingBuffer = true;
        }
        return orig.call(this, type, attrs);
      };
    } catch (_) {}
  }

  // Runs at end of body. Answers 'sandpie-shot-request' from the parent.
  function __sandpieShotEngine() {
    if (window.__sandpieShotReady) return;
    window.__sandpieShotReady = 1;

    const XHTML_NS = 'http://www.w3.org/1999/xhtml';

    const isInlineUrl = (u) => /^(data:|blob:)/i.test(String(u || ''));

    function isSameOrigin(u) {
      try { return new URL(u, location.href).origin === location.origin; }
      catch (_) { return false; }
    }

    // The SVG-in-<img> rasterization context cannot fetch ANY subresource, so
    // every external image must be turned into a data: URI up front or it renders
    // blank. Cross-origin fetches need CORS; failures are reported, not silent.
    function toDataUri(src) {
      return fetch(src, { mode: 'cors', credentials: 'omit' })
        .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); })
        .then((b) => new Promise((res, rej) => {
          const fr = new FileReader();
          fr.onload = () => res(fr.result);
          fr.onerror = () => rej(new Error('read failed'));
          fr.readAsDataURL(b);
        }));
    }

    // Walk the live tree and its clone in lockstep, recording what needs fixing.
    // Nothing is mutated during the walk — a structural edit mid-walk would
    // desynchronise the two trees.
    function pairUp(live, clone, out) {
      out.push([live, clone]);
      const a = live.children, b = clone.children;
      const n = Math.min(a.length, b.length);
      for (let i = 0; i < n; i++) pairUp(a[i], b[i], out);
      return out;
    }

    function collect(pairs, warnings) {
      const canvasFixes = [];
      const imgFixes = [];
      let scrolled = 0, shadow = 0, backdrop = 0;

      for (const [live, clone] of pairs) {
        const tag = live.tagName ? live.tagName.toLowerCase() : '';

        if (tag === 'canvas') {
          let url = null;
          try { url = live.toDataURL('image/png'); } catch (_) { /* tainted */ }
          // A cleared WebGL buffer serialises to a ~120-byte blank PNG; treat a
          // suspiciously tiny payload as a failed capture rather than pretend.
          if (url && url.length > 200) canvasFixes.push([clone, url, live.width, live.height]);
          else warnings.push('A <canvas> could not be captured (tainted by cross-origin content, or its WebGL buffer was already cleared) — it appears blank in the image.');
        }

        if (tag === 'img') {
          const src = live.currentSrc || live.getAttribute('src') || '';
          if (src && !isInlineUrl(src)) imgFixes.push([clone, src]);
        }

        // Live form state lives in properties, not attributes — without this the
        // capture shows the pristine markup, not what was typed or clicked.
        if (tag === 'input') {
          if (live.type === 'checkbox' || live.type === 'radio') {
            if (live.checked) clone.setAttribute('checked', 'checked');
            else clone.removeAttribute('checked');
          } else if (live.value != null) {
            clone.setAttribute('value', live.value);
          }
        } else if (tag === 'textarea') {
          clone.textContent = live.value || '';
        } else if (tag === 'option') {
          if (live.selected) clone.setAttribute('selected', 'selected');
          else clone.removeAttribute('selected');
        }

        if (live.shadowRoot) shadow++;
        if (live.scrollTop > 2 || live.scrollLeft > 2) scrolled++;

        try {
          const cs = getComputedStyle(live);
          const bf = cs.backdropFilter || cs.webkitBackdropFilter;
          if (bf && bf !== 'none') backdrop++;
        } catch (_) {}
      }

      if (scrolled) warnings.push(scrolled + ' scrolled container(s) capture from the top — their scroll position is not reproduced.');
      if (shadow) warnings.push(shadow + ' element(s) use shadow DOM; shadow content is not serialisable and is missing from the image.');
      if (backdrop) warnings.push(backdrop + ' element(s) use backdrop-filter, which has nothing to sample in an isolated render — those areas appear flat rather than frosted.');

      return { canvasFixes, imgFixes };
    }

    // A screenshot is ONE state of a page that may have many. Enumerating them is
    // hopeless (a page driven by an API has unbounded states), so this only
    // DISCLOSES that other views exist — enough that the model doesn't declare a
    // tabbed dashboard fine having seen a third of it. It is a disclosure, not an
    // invitation to go exploring.
    function disclose(warnings) {
      const q = (sel) => { try { return document.querySelectorAll(sel).length; } catch (_) { return 0; } };
      const bits = [];
      const tabs = q('[role="tab"]');
      if (tabs > 1) bits.push(tabs + ' tabs (one shown)');
      const collapsed = q('details:not([open])');
      if (collapsed) bits.push(collapsed + ' collapsed <details>');
      const expandable = q('[aria-expanded="false"]');
      if (expandable) bits.push(expandable + ' collapsed section(s)');
      const dialogs = q('dialog:not([open])');
      if (dialogs) bits.push(dialogs + ' unopened dialog(s)');
      const hidden = q('[hidden]');
      if (hidden) bits.push(hidden + ' [hidden] element(s)');
      if (bits.length) {
        warnings.push('OTHER VIEWS EXIST — this is one state of an interactive page: '
          + bits.join(', ') + '. What is not shown is not verified.');
      }
    }

    async function build(opts, warnings) {
      const doc = document;
      const root = doc.documentElement;
      const W = Math.max(1, opts.width | 0 || root.clientWidth || 1280);
      const H = Math.max(1, opts.height | 0 || (opts.full_page
        ? Math.max(root.scrollHeight, doc.body ? doc.body.scrollHeight : 0)
        : root.clientHeight) || 800);

      // Horizontal overflow is the failure mode most likely to be mistaken for a
      // faithful capture: the page renders fine, it is just wider than the frame,
      // so the right edge is cut with nothing to indicate it. Report the width
      // that would actually fit rather than leaving the model to guess.
      // Measured here, acted on by the caller: only the parent can widen the frame
      // (layout follows the iframe's width, not the SVG's), so captureOffscreen
      // re-renders at contentWidth rather than shipping a knowingly clipped image.
      // The warning is the FALLBACK for surfaces that can't be resized — the side
      // panel is the user's real window and must not be reflowed underneath them.
      const overflow = root.scrollWidth - root.clientWidth;
      if (overflow > 1) {
        warnings.push('Content is ' + root.scrollWidth + 'px wide but this capture is ' + root.clientWidth
          + 'px, so the right ' + overflow + 'px is CUT OFF (text near the right edge may be missing characters).'
          + (opts.liveSurface
              ? ' This is the user\'s actual window, so it is a real horizontal-overflow problem in the page, not a capture artifact.'
              : ' exact_width was set, so it was captured clipped as requested — drop exact_width to get a complete image.'));
      }

      disclose(warnings);

      const clone = root.cloneNode(true);
      const pairs = pairUp(root, clone, []);
      const { canvasFixes, imgFixes } = collect(pairs, warnings);

      // Scripts never execute inside an <img>-loaded SVG; dropping them keeps the
      // payload small and the XML clean.
      clone.querySelectorAll('script').forEach((s) => s.remove());

      for (const [node, url, w, h] of canvasFixes) {
        const img = doc.createElementNS(XHTML_NS, 'img');
        img.setAttribute('src', url);
        img.setAttribute('width', String(w));
        img.setAttribute('height', String(h));
        img.setAttribute('style', (node.getAttribute('style') || '') + ';display:block;');
        if (node.parentNode) node.parentNode.replaceChild(img, node);
      }

      let failedImgs = 0;
      await Promise.all(imgFixes.map(([node, src]) =>
        toDataUri(src)
          .then((d) => node.setAttribute('src', d))
          .catch(() => {
            failedImgs++;
            node.removeAttribute('src');
          })
      ));
      if (failedImgs) {
        warnings.push(failedImgs + ' image(s) could not be inlined (cross-origin without CORS headers) and are blank in the capture.');
      }

      // Any remaining url() reference in CSS has the same problem as an <img>, but
      // rewriting stylesheet text is a different order of complexity — flag it.
      try {
        const cssUrls = Array.from(doc.styleSheets).some((sh) => {
          try {
            return Array.from(sh.cssRules || []).some((r) =>
              r.cssText && /url\((?!['"]?(data:|#))/i.test(r.cssText));
          } catch (_) { return false; }
        });
        if (cssUrls) warnings.push('Stylesheet url() references (background images, external fonts) are not inlined — they may be missing, and a substituted font changes text metrics.');
      } catch (_) {}

      clone.setAttribute('xmlns', XHTML_NS);
      const html = new XMLSerializer().serializeToString(clone);

      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">' +
        // Explicit width/height on foreignObject is REQUIRED by Safari — without
        // it, iOS renders nothing at all.
        '<foreignObject x="0" y="0" width="' + W + '" height="' + H + '">' + html + '</foreignObject></svg>';

      return { url: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg), W, H };
    }

    function backdropColor() {
      try {
        for (const el of [document.body, document.documentElement]) {
          if (!el) continue;
          const c = getComputedStyle(el).backgroundColor;
          if (c && !/transparent|rgba\(0,\s*0,\s*0,\s*0\)/i.test(c)) return c;
        }
      } catch (_) {}
      return '#ffffff';
    }

    async function draw(url, W, H, scale, bg) {
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(W * scale);
      canvas.height = Math.round(H * scale);
      const cx = canvas.getContext('2d');
      cx.fillStyle = bg;
      cx.fillRect(0, 0, canvas.width, canvas.height);

      const img = new Image();
      img.src = url;
      // decode() rather than onload: on WebKit, onload fires before the SVG has
      // actually produced pixels, and drawImage then paints nothing.
      if (img.decode) { try { await img.decode(); } catch (_) { await new Promise((r) => { img.onload = r; img.onerror = r; }); } }
      else await new Promise((r) => { img.onload = r; img.onerror = r; });

      cx.drawImage(img, 0, 0, canvas.width, canvas.height);
      return canvas;
    }

    // A vertical scrollbar steals ~15 CSS px of the width the caller asked for,
    // which silently clips fixed-width documents (an A4 page is 793.7px — at a
    // 794px request it lost its right edge). Suppress it for the capture only.
    function suppressScrollbars() {
      const st = document.createElement('style');
      st.textContent = 'html{overflow:hidden !important;scrollbar-width:none !important}'
        + 'html::-webkit-scrollbar{display:none !important}';
      document.head.appendChild(st);
      return () => st.remove();
    }

    async function shoot(opts) {
      const warnings = [];
      const restore = suppressScrollbars();
      let built;
      try { built = await build(opts || {}, warnings); }
      finally { restore(); }
      const { url, W, H } = built;

      // Never rasterize below 1:1 — devicePixelRatio is < 1 at browser zoom under
      // 100%, which would silently soften every capture (a 794px request came back
      // 715px at 90% zoom, blurring small text enough to be misread).
      let scale = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
      if (W * scale > 16384 || H * scale > 16384) scale = 1;
      let h = H;
      if (h > 16384) {
        warnings.push('Content is ' + H + 'px tall; truncated to 16384px (canvas limit).');
        h = 16384;
      }

      const bg = backdropColor();
      // Safari's first rasterization of a foreignObject SVG silently produces
      // nothing. Drawing twice is the standard workaround; the second pass hits
      // the image cache, so it costs almost nothing on browsers that don't need it.
      await draw(url, W, h, scale, bg);
      const canvas = await draw(url, W, h, scale, bg);

      return {
        dataUrl: canvas.toDataURL('image/jpeg', 0.92),
        width: canvas.width,
        height: canvas.height,
        warnings,
        // What the document actually needs vs what it got. captureOffscreen uses
        // this to re-render at a width that fits.
        contentWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
      };
    }

    window.addEventListener('message', (e) => {
      const d = e.data;
      if (!d || d.type !== 'sandpie-shot-request') return;
      const reply = (payload) => {
        try { (e.source || parent).postMessage(Object.assign({ type: 'sandpie-shot-result', id: d.id }, payload), '*'); }
        catch (_) {}
      };
      shoot(d.opts || {})
        .then((out) => reply(Object.assign({ ok: true }, out)))
        .catch((err) => reply({ ok: false, error: (err && err.message) || String(err) }));
    });
  }

  const ENGINE_SRC = __sandpieShotEngine.toString();
  const HEAD_BOOTSTRAP = '<script>(' + __sandpieShotPatch.toString() + ')();<\/script>';
  const BODY_BOOTSTRAP = '<script>(' + ENGINE_SRC + ')();<\/script>';

  /* ---------------------------------------------------------------------- */
  /*  Page side                                                             */
  /* ---------------------------------------------------------------------- */

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function askFrame(win, opts) {
    return new Promise((resolve, reject) => {
      const id = 'shot_' + Math.random().toString(36).slice(2);
      const timer = setTimeout(() => {
        window.removeEventListener('message', onMsg);
        reject(new Error('the artifact did not answer the capture request in time (it may predate the screenshot bootstrap — re-show it to reinstrument)'));
      }, SHOT_TIMEOUT);
      function onMsg(e) {
        const d = e.data;
        if (!d || d.type !== 'sandpie-shot-result' || d.id !== id) return;
        clearTimeout(timer);
        window.removeEventListener('message', onMsg);
        if (d.ok) resolve(d); else reject(new Error(d.error || 'capture failed inside the artifact'));
      }
      window.addEventListener('message', onMsg);
      try { win.postMessage({ type: 'sandpie-shot-request', id, opts }, '*'); }
      catch (e) { clearTimeout(timer); window.removeEventListener('message', onMsg); reject(e); }
    });
  }

  // Non-HTML artifacts (png/jpg/svg/…) need no DOM work — decode and re-encode.
  async function captureImageFile(path, opts) {
    const url = await opfs.toUrl(path);
    try {
      const img = new Image();
      img.src = url;
      if (img.decode) { try { await img.decode(); } catch (_) { await new Promise((r) => { img.onload = r; img.onerror = r; }); } }
      else await new Promise((r) => { img.onload = r; img.onerror = r; });

      let w = img.naturalWidth || opts.width || DEFAULT_W;
      let h = img.naturalHeight || opts.height || DEFAULT_H;
      if (w > MAX_PX || h > MAX_PX) {
        const k = MAX_PX / Math.max(w, h);
        w = Math.round(w * k); h = Math.round(h * k);
      }
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const cx = canvas.getContext('2d');
      cx.fillStyle = '#ffffff';
      cx.fillRect(0, 0, w, h);
      cx.drawImage(img, 0, 0, w, h);
      return { dataUrl: canvas.toDataURL('image/jpeg', 0.92), width: w, height: h, warnings: [] };
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }
  }

  const _norm = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '');

  // The side-panel viewer loads files through the service worker at their real
  // /files/ URL (file-viewer.js showRendered), NOT through opfs.toUrl — so the
  // capture bootstrap was never injected. The frame is same-origin, so install the
  // engine on demand. NOTE: the getContext patch cannot be retrofitted (the
  // artifact's scripts already ran), so a WebGL canvas may capture blank here —
  // collect() reports that when it happens.
  function ensureEngine(win) {
    try {
      if (win.__sandpieShotReady) return true;
      const s = win.document.createElement('script');
      s.textContent = '(' + ENGINE_SRC + ')();';
      (win.document.body || win.document.documentElement).appendChild(s);
      s.remove();
      return !!win.__sandpieShotReady;
    } catch (_) { return false; }
  }

  // Capture what the user is CURRENTLY LOOKING AT in the side panel. This is the
  // privileged state: it holds fetched data, the open tab, scroll position and
  // typed input — none of which a fresh render could reproduce, and all of which
  // is what "it looks broken" actually refers to.
  async function captureSidePanel(path, opts) {
    const want = _norm(path);
    if (want && _norm(window._openFilePath) !== want) return null;   // panel shows a different file
    for (const frame of document.querySelectorAll('.file-viewer iframe')) {
      const src = frame.getAttribute('src') || '';
      if (!src.startsWith('/files/')) continue;                      // pdf/latex frames aren't captureable
      if (!frame.contentWindow || !ensureEngine(frame.contentWindow)) continue;
      // This is the user's real window — never reflow it to make a tidier picture.
      // Overflow here is a genuine layout problem they are looking at, so report it.
      const out = await askFrame(frame.contentWindow, Object.assign({}, opts, { liveSurface: true }));
      out.mode = 'side-panel';
      return out;
    }
    return null;
  }

  // Capture the artifact frame already visible in the conversation. Preserves
  // whatever state the page is in (post-interaction), at the cost of depending on
  // that frame being mounted and expanded.
  async function captureLiveFrame(path, opts) {
    const norm = _norm;
    const want = norm(path);
    for (const wrap of document.querySelectorAll('.artifact-wrap')) {
      if (want && norm(wrap.dataset.artifactPath) !== want) continue;
      const frame = wrap.querySelector('.artifact-frame');
      if (!frame || !frame.contentWindow) continue;
      // The conversation no longer shows inline frames — the only .artifact-frame
      // is the hidden 1px console frame (consoleOnly). It has no real layout, so
      // skip it and let capture() fall through to the deterministic offscreen render.
      if (frame.dataset.consoleOnly === '1') continue;
      // A collapsed frame is display:none — no layout, nothing to serialise. Expand
      // for the duration, then put it back exactly as the user left it.
      const wasCollapsed = wrap.dataset.artifactCollapsed === '1';
      if (wasCollapsed && typeof window.expandArtifact === 'function') {
        window.expandArtifact(wrap);
        await sleep(120);
      }
      try {
        const out = await askFrame(frame.contentWindow, Object.assign({}, opts, { liveSurface: true }));
        out.mode = 'conversation-frame';
        return out;
      } finally {
        if (wasCollapsed && typeof window.collapseArtifact === 'function') window.collapseArtifact(wrap);
      }
    }
    return null;
  }

  // Default path: render the artifact into an offscreen iframe at exact
  // dimensions. Deterministic size (so responsive checks mean something), works
  // regardless of which conversation is mounted, and never disturbs the user's view.
  async function captureOffscreen(path, opts) {
    const W = Math.max(120, opts.width | 0 || DEFAULT_W);
    const H = Math.max(120, opts.height | 0 || DEFAULT_H);
    const host = document.createElement('iframe');
    host.setAttribute('aria-hidden', 'true');
    host.setAttribute('tabindex', '-1');
    // Positioned offscreen rather than display:none — the document still needs
    // layout, and display:none gives it none.
    host.style.cssText =
      'position:fixed;left:-30000px;top:0;width:' + W + 'px;height:' + H + 'px;' +
      'border:0;background:#fff;z-index:-1;pointer-events:none;opacity:0;';
    document.body.appendChild(host);

    let url = null;
    try {
      url = await opfs.toUrl(path);
      await new Promise((resolve, reject) => {
        const t = setTimeout(() => reject(new Error('artifact did not load in time')), SHOT_TIMEOUT);
        host.onload = () => { clearTimeout(t); resolve(); };
        host.onerror = () => { clearTimeout(t); reject(new Error('artifact failed to load')); };
        host.src = url;
      });
      // Settle window: async rendering (fetches, chart libraries, load handlers)
      // has not necessarily finished when load fires.
      await sleep(Math.min(Math.max(opts.wait_ms | 0 || 400, 0), 10000));
      let out = await askFrame(host.contentWindow, Object.assign({}, opts, { width: W, height: opts.full_page ? 0 : H }));

      // The capture knows exactly how wide the content needed to be, so shipping a
      // clipped image and a note telling someone else to fix it is indefensible —
      // one more render costs ~400ms and produces a correct picture. Opt out with
      // exact_width when the requested width IS the thing being tested.
      const need = out.contentWidth | 0;
      if (!opts.exact_width && need > W + 1 && need <= MAX_FIT_W) {
        host.style.width = need + 'px';
        await sleep(250);                     // let the reflow settle before re-asking
        const wide = await askFrame(host.contentWindow, Object.assign({}, opts, { width: need, height: opts.full_page ? 0 : H }));
        wide.warnings = wide.warnings || [];
        // Don't hide what happened: a page that overflows the width it was asked
        // for may still have a real layout bug, and only the caller knows whether
        // that width mattered.
        wide.warnings.unshift('AUTO-FITTED: the requested ' + W + 'px was too narrow (content needs '
          + need + 'px), so this was re-rendered at ' + need + 'px and nothing is cut off. '
          + 'If you were specifically testing the ' + W + 'px layout, note that at that width the right '
          + (need - W) + 'px overflows — pass exact_width: true to capture it clipped as-is.');
        wide.autoFitted = true;
        out = wide;
      }
      out.mode = 'fresh-render';
      return out;
    } finally {
      host.remove();
      if (url) setTimeout(() => URL.revokeObjectURL(url), 5000);
    }
  }

  /**
   * Capture an OPFS artifact as a JPEG data URL.
   * @param {string} path  OPFS path (e.g. "sandpie/artifacts/report.html")
   * @param {object} opts  { width, height, full_page, wait_ms, live }
   * @returns {Promise<{dataUrl:string,width:number,height:number,warnings:string[]}>}
   */
  async function capture(path, opts) {
    opts = opts || {};
    let clean = String(path || '').replace(/^\/+/, '');
    if (!clean) throw new Error('a path is required');
    if (typeof window.resolveArtifactPath === 'function') {
      try { clean = await window.resolveArtifactPath(clean); } catch (_) {}
    }

    const ext = (clean.split('.').pop() || '').toLowerCase();
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) {
      return await captureImageFile(clean, opts);
    }
    if (ext !== 'html' && ext !== 'htm') {
      throw new Error('cannot screenshot a .' + ext + ' file — only HTML artifacts and image files can be rasterized.');
    }

    // live: the user's ACTUAL view, in preference order — side panel (where files
    // are really viewed and interacted with), then the inline conversation card.
    // Falls back to a fresh render when the file is on screen nowhere.
    if (opts.live) {
      const panel = await captureSidePanel(clean, opts);
      if (panel) return panel;
      const inline = await captureLiveFrame(clean, opts);
      if (inline) return inline;
    }
    return await captureOffscreen(clean, opts);
  }

  window.SandpieScreenshot = {
    capture,
    HEAD_BOOTSTRAP,
    BODY_BOOTSTRAP,
  };
})();
