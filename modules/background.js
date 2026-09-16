/* background.js — the empty-chat home screen background: a slow pixel
   animation behind the pane, chosen in Settings → Appearance → Background.

   This module GENERALIZES the original home-sky.js (pixel clouds) into a small
   registry of animations that all share the same engine: a low-resolution
   buffer (4px cells) ordered-dithered (4×4 Bayer) into a FIVE-STEP RAMP
   DERIVED FROM THE THEME — --sp-bg toward --sp-text-dim (dark themes) or
   --sp-text (light themes) — so every animation recolours itself with any
   built-in or custom palette.

   Modes:
     clouds      — the original homeSky pixel-cloud field (default)
     water-open  — 'Selune': moonlit open water — ripple bands compress toward
                   the horizon, glints shimmer, glare moon with a randomized
                   phase (crescent) spawned once per page load
     none        — plain background, no animation

   The choice is persisted in SandpieConfig under the 'background' namespace
   ({ mode }) with a localStorage fallback, and applied live. Lifecycle is the
   home-sky one: the canvas lives behind #messages and only renders while
   #homeCenter is on screen; it stops when the pane is hidden or the tab is in
   the background. prefers-reduced-motion slows every mode to a crawl rather
   than removing it.

   CLASSIC script (global window.SandpieBackground + window.SandpieHomeSky).
   Replaces modules/home-sky.js in sandpie.html. */
(function () {
  'use strict';
  // Cell size follows the pane width: 4px on desktop, 3 on tablets, 2 on phones —
  // a 4px cell on a 390px-wide pane reads as blocks, not pixels. Cloud scale and drift
  // are expressed in CSS px and converted to cells, so the picture keeps its
  // size and slows down rather than shrinking and speeding up on a phone.
  let cell = 4;
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map(v => (v + .5) / 16);
  const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { return false; } };
  const clamp = (v, a, b) => v < a ? a : v > b ? b : v;

  /* ── mode registry: which animation fills the home screen ──
     'clouds' is the original homeSky field; the two water modes are the
     round-3 monochrome mockups (W1 open water, W3 river current) ported to
     the same theme-derived ramp; 'none' disables the animation entirely. */
  let mode = 'clouds';
  const MODES = {
    'clouds':      { label: 'Clouds' },
    'water-open':  { label: 'Selune' },
    'none':        { label: 'None' },
  };
  const isWater = () => mode === 'water-open';

  /* ── per-theme tuning (from the round-13 studies). `reach` is how far along the
     bg→tint ramp the top step sits; light themes need far less because the eye
     is more sensitive on a bright ground. Unknown themes fall back by luminance. */
  const TUNE = {
    'classic-dark': { mode: 'clouds', tint: 'dim',  reach: .28, size: 1.0,  cover: .53, tempo: 3, speed: .06 },
    'aurora':       { mode: 'clouds', tint: 'dim',  reach: .2576, size: 1.0,  cover: .53, tempo: 3, speed: .06 },
    'electric':     { mode: 'clouds', tint: 'dim',  reach: .2464, size: 1.0,  cover: .53, tempo: 3, speed: .06 },
    'classic-light':{ mode: 'sky',    tint: 'text', reach: .204, size: 1.15, cover: .51, tempo: 3, speed: .06 },
    'clear':        { mode: 'sky',    tint: 'text', reach: .144, size: 1.2,  cover: .53, tempo: 4, speed: .05 },
  };
  const FALLBACK_DARK  = TUNE['classic-dark'];
  const FALLBACK_LIGHT = TUNE['classic-light'];
  const CAP = .62, DETAIL = 4, FALL = .85;

  /* ── colour helpers: resolve a CSS token to [r,g,b] via a probe element ── */
  let _probe = null;
  function rgbOf(cssValue, fallback) {
    try {
      if (!_probe) { _probe = document.createElement('i'); _probe.style.display = 'none'; document.body.appendChild(_probe); }
      _probe.style.color = ''; _probe.style.color = cssValue;
      const m = /rgba?\(([^)]+)\)/.exec(getComputedStyle(_probe).color);
      if (m) { const p = m[1].split(',').map(s => parseFloat(s)); if (p.length >= 3) return [p[0], p[1], p[2]]; }
    } catch (_) {}
    return fallback;
  }
  const token = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const lum = c => (.2126 * c[0] + .7152 * c[1] + .0722 * c[2]) / 255;
  const mix = (a, b, t) => [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)];

  function themeName() {
    const t = document.documentElement.getAttribute('data-theme');
    return !t ? 'classic-dark' : t === 'light' ? 'classic-light' : t;
  }
  function buildPalette() {
    const bg = rgbOf(token('--sp-bg') || '#0d1117', [13, 17, 23]);
    const name = themeName();
    const tune = TUNE[name] || (lum(bg) > .5 ? FALLBACK_LIGHT : FALLBACK_DARK);
    const tintTok = tune.tint === 'text' ? '--sp-text' : '--sp-text-dim';
    const tint = rgbOf(token(tintTok) || (lum(bg) > .5 ? '#1f2328' : '#9ab0c8'), lum(bg) > .5 ? [31, 35, 40] : [154, 176, 200]);
    // Water reads best with a slightly wider ramp than clouds (same theme
    // colours, more reach) — capped so it never leaves the monochrome family.
    const reach = Math.min(.55, tune.reach * (isWater() ? 1.7 : 1));
    const pal = [0, 1, 2, 3, 4].map(i => mix(bg, tint, (i / 4) * reach));
    return { pal, tune, tint };
  }

  /* ── noise: one fixed lattice, smooth value noise, 4 octaves ── */
  const N = 64, lat = new Float32Array(N * N);
  { let seed = 1234567; for (let i = 0; i < lat.length; i++) { seed = (seed * 1664525 + 1013904223) >>> 0; lat[i] = seed / 4294967296; } }
  const at = (x, y) => lat[((y & (N - 1)) * N) + (x & (N - 1))];
  function noise(x, y) {
    const x0 = Math.floor(x), y0 = Math.floor(y), tx = x - x0, ty = y - y0;
    const sx = tx * tx * (3 - 2 * tx), sy = ty * ty * (3 - 2 * ty);
    return (at(x0, y0) * (1 - sx) + at(x0 + 1, y0) * sx) * (1 - sy) + (at(x0, y0 + 1) * (1 - sx) + at(x0 + 1, y0 + 1) * sx) * sy;
  }
  function fbm(x, y) { let v = 0, a = .5, f = 1, n = 0; for (let o = 0; o < DETAIL; o++) { v += a * noise(x * f, y * f); n += a; a *= .5; f *= 2.1; } return v / n; }
  const dither = (v, x, y) => { const l = clamp(v, 0, .9999) * 4, i = l | 0, f = l - i; return f > BAYER[(y & 3) * 4 + (x & 3)] ? i + 1 : i; };

  /* ── canvas ── */
  let canvas, ctx, off, octx, img, gw = 0, gh = 0, drift = 0, tick = 0, pal = null, tune = null, dirty = true, running = false, raf = 0;

  function ensureCanvas() {
    if (canvas) return canvas;
    const pane = document.getElementById('messages');
    if (!pane) return null;
    canvas = document.createElement('canvas');
    canvas.id = 'homeSky';
    canvas.setAttribute('aria-hidden', 'true');
    pane.insertBefore(canvas, pane.firstChild);
    ctx = canvas.getContext('2d');
    off = document.createElement('canvas'); octx = off.getContext('2d');
    new ResizeObserver(size).observe(canvas);
    size();
    return canvas;
  }
  function size() {
    if (!canvas) return;
    const r = canvas.getBoundingClientRect();
    const W = Math.max(1, r.width | 0), H = Math.max(1, r.height | 0);
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    // pixel density 1.5: 1.5× the shipped pixels per area (finer dither)
    cell = Math.max(1, Math.round((W < 500 ? 2 : W < 900 ? 3 : 4) / 1.5));
    gw = Math.ceil(W / cell); gh = Math.ceil(H / cell);
    off.width = gw; off.height = gh; img = octx.createImageData(gw, gh);
    ctx.imageSmoothingEnabled = false;
    dirty = true;
  }
  /* ── water fields (round-3 mockups W1/W3, monochrome via the shared ramp) ── */
  /* ── open water: tuned field (mockup round 4) + moon with reflection ──
     The moon position is drawn ONCE per page load (boot) and kept for the
     whole session — resizes, pane remounts and focus changes never move it.
     It is constrained to the sky band and never overlaps the greeting. */
  const MOON = { x: .7, y: .06, r: .04, soft: .4, glintW: .11, glintAmp: 1, glareR: .9, glareAmp: 1.05 };
  let moon = null;                       // { x, y, ph } in pane fractions, spawned per redraw
  // Phase params (mockup C, user-tuned): terminator softness 1, phase randomized
  // per page load into the crescent bands 0.20-0.30 (waxing) or 0.70-0.80 (waning).
  function greetingRect() {
    // bounding box of the greeting text in canvas cell coords (or null)
    const g = document.querySelector('#messages .home-greeting');
    if (!g || !canvas) return null;
    const gr = g.getBoundingClientRect(), cr = canvas.getBoundingClientRect();
    if (gr.bottom < cr.top || gr.top > cr.bottom) return null;
    return {
      x0: (gr.left - cr.left) / cell, x1: (gr.right - cr.left) / cell,
      y0: (gr.top - cr.top) / cell,  y1: (gr.bottom - cr.top) / cell,
    };
  }
  function spawnMoon() {
    const horizon = gh * .5;
    const r = Math.min(gw, gh) * MOON.r;
    const m = 6;                                    // clearance around the greeting, cells
    const g = greetingRect();
    const pad = r * 2 + m;
    for (let tries = 0; tries < 40; tries++) {
      const x = pad / gw + Math.random() * Math.max(0, 1 - 2 * pad / gw);
      const yMin = (r + 2) / gh, yMax = Math.max(yMin, (horizon - r - 2) / gh);
      const y = yMin + Math.random() * Math.max(0, yMax - yMin);
      const cx = x * gw, cy = y * gh;
      if (g && cx > g.x0 - pad && cx < g.x1 + pad && cy > g.y0 - pad && cy < g.y1 + pad) continue;
      moon = { x, y, ph: spawnPhase() };
      return;
    }
    const ph = Math.random() < .5 ? .2 + Math.random() * .1 : .7 + Math.random() * .1;
    moon = { x, y, ph };                            // fallback: the tuned spot
  }
  function spawnPhase() {
    // crescent band: 0.20-0.30 waxing or 0.70-0.80 waning, rolled once per page load
    return Math.random() < .5 ? .2 + Math.random() * .1 : .7 + Math.random() * .1;
  }
  function paintWaterOpen() {
    if (!img || !pal) return;
    if (!moon) spawnMoon();          // lazily on first paint; position + phase fixed for the session
    const d = img.data, T = tick / 60, horizon = gh * .5;
    const mx = moon.x * gw, my = moon.y * gh, mr = Math.min(gw, gh) * MOON.r;
    const gx = moon.x * gw, halfw = gw * MOON.glintW;
    for (let y = 0; y < gh; y++) {
      for (let x = 0; x < gw; x++) {
        let c, moonCore = false;
        if (y < horizon) {
          // EMPTY sky — no pattern, just the moon disc
          const dist = Math.hypot(x - mx, y - my);
          const edge = clamp((mr - dist) / Math.max(1, mr * MOON.soft), 0, 1);
          const ss = edge * edge * (3 - 2 * edge);
          // GLARE: hot bloom at the moon's centre (mockup A, user-tuned)
          const glare = Math.exp(-(dist * dist) / (2 * mr * mr * MOON.glareR * MOON.glareR)) * MOON.glareAmp;
          // PHASE (mockup C, user-tuned): a shadow disc of the same radius slides
          // across the moon — 0 new, .25 first quarter, .5 full, .75 last quarter.
          // Softness 1 → the terminator fades across the whole disc. The glare
          // follows the lit part; the halo/atmosphere stays full.
          const ph = moon.ph == null ? .5 : moon.ph;
          const waxing = ph < .5;
          const ph2 = waxing ? ph : 1 - ph;          // 0 new .. .5 full
          const dx = 4 * mr * ph2;                   // 0..2mr shadow offset
          const sx = mx + (waxing ? -dx : dx);       // shadow slides from the lit side
          const dSh = Math.hypot(x - sx, y - my);
          const mask = clamp((dSh - mr) / (mr * 1) + .5, 0, 1);   // phaseSoft = 1
          c = ss * mask + glare * mask;
          moonCore = edge > .55 && mask > .6;        // core only on the lit part
        } else {
          const dn = (y - horizon) / (gh - horizon);
          const persp = .12 + Math.pow(dn, .5) * 5;
          const rip = fbm(x * .06, dn * 32 * persp - T * .10 * persp);
          const slope = fbm(x * .06 + .35, dn * 32 * persp - T * .10 * persp) - rip;
          const glint = Math.pow(Math.max(0, rip - .47) * 2.2, 3.2) * (1 + Math.max(0, slope) * 3.5);
          c = rip * .3 * (.4 + dn * .8) + glint;
          const sp = fbm(x * .3, dn * 40 * persp + T * .3);
          if (sp > .93) c += (sp - .93) * 8 * (1.2 - dn);
          // moon reflection: shimmer column under the moon — gaussian across x,
          // fading with depth, flickering with the ripple field
          const across = Math.exp(-((x - gx) * (x - gx)) / (2 * halfw * halfw));
          const depth = clamp(1 - dn * 1.15, 0, 1);
          const flicker = .55 + .45 * fbm(x * .12 + T * .05, dn * 26 * persp - T * .12);
          c += across * depth * flicker * MOON.glintAmp;
          c = clamp(c, 0, 1);
        }
        const p = moonCore ? (tintCol || pal[4]) : pal[dither(c, x, y)], q = (y * gw + x) * 4;
        d[q] = p[0]; d[q + 1] = p[1]; d[q + 2] = p[2]; d[q + 3] = 255;
      }
    }
    blit();
  }
  function blit() {
    octx.putImageData(img, 0, 0);
    ctx.drawImage(off, 0, 0, gw * cell, gh * cell);
  }
  function paint() {
    if (!img || !pal) return;
    if (mode === 'water-open') return paintWaterOpen();
    paintClouds();
  }
  function paintClouds() {
    if (!img || !pal) return;
    // Keep the clouds' size in CSS px constant across cell sizes (finer cells →
    // more cells per cloud), slightly smaller on phones so a few whole shapes fit.
    const narrow = gw * cell < 700, sf = (cell / 4) * (narrow ? 1.15 : 1);
    const d = img.data, k1 = .035 / tune.size * sf, k2 = .045 / tune.size * sf, thr = tune.cover, sky = tune.mode === 'sky';
    for (let y = 0; y < gh; y++) {
      const band = 1 - Math.pow(y / gh, 2.2) * FALL;
      for (let x = 0; x < gw; x++) {
        const far = fbm((x + drift * .5) * k1, y * k1 * 1.7 + 7.3), near = fbm((x + drift) * k2 + 3.1, y * k2 * 1.66);
        let c = Math.min(CAP, Math.max(0, far - thr) * 1.14 + Math.max(0, near - (thr + .03)) * 2.2) * band;
        if (sky) c = CAP * band - c;
        const p = pal[dither(c, x, y)], q = (y * gw + x) * 4;
        d[q] = p[0]; d[q + 1] = p[1]; d[q + 2] = p[2]; d[q + 3] = 255;
      }
    }
    blit();
  }
  function frame() {
    raf = 0;
    if (!running) return;
    tick++;
    // Drift is set in CSS px per frame (desktop ≈ 0.08px/frame ≈ 5px/s) and
    // converted to cells, so phones — finer cells, narrower pane — get the same
    // or slower motion, never faster. Phones run at 40% of desktop speed.
    const narrow = gw * cell < 700;
    const every = (tune.tempo + (narrow ? 1 : 0)) * (reduced() ? 4 : 1);
    if (tick % every === 0) {
      // Clouds only repaint when the drift advances; the water fields are
      // time-driven (t in the field), so they repaint on every tempo tick.
      if (isWater()) dirty = true;
      else drift += (tune.speed * 4 / tune.tempo) * (narrow ? .4 : 1) * every / cell;
      if (!isWater()) dirty = true;
    }
    if (dirty && !document.hidden) { paint(); dirty = false; }
    raf = requestAnimationFrame(frame);
  }
  function start() { if (running) return; running = true; if (!raf) raf = requestAnimationFrame(frame); }
  function stop() { running = false; if (raf) { cancelAnimationFrame(raf); raf = 0; } }
  let tintCol = null;
  function retheme() { let r; ({ pal, tune, tint: tintCol } = buildPalette()); dirty = true; }

  /* ── show only on the welcome state: #homeCenter connected in the LEFT pane
     and not retired by .home-leave (conversations.js flips that on the first
     live message and on loading a conversation). Polled cheaply on a
     MutationObserver rather than wired into conversations.js internals. */
  function homeVisible() {
    const hc = document.getElementById('homeCenter'), pane = document.getElementById('messages');
    return !!(hc && pane && pane.contains(hc) && !hc.classList.contains('home-leave'));
  }
  function sync() {
    const c = ensureCanvas(); if (!c) return;
    const on = homeVisible();
    c.classList.toggle('sky-on', on);
    if (on) { size(); start(); } else stop();
    updateGreeting();
  }

  /* ── greeting: time of day, in the language chosen in Settings (Language
     setting → SandpieLanguage.effective(); 'auto' resolves to the browser's).
     Four slots: morning · afternoon · evening · night. Languages whose custom
     is to greet the same way across two slots repeat the word (es/ca/pt
     "tardes" covers afternoon AND evening; fr "bonjour" all day). Anything not
     listed falls back to English rather than to a wrong language. ── */
  const GREETINGS = {
    en: ['Good morning', 'Good afternoon', 'Good evening', 'Good night'],
    es: ['Buenos días', 'Buenas tardes', 'Buenas tardes', 'Buenas noches'],
    ca: ['Bon dia', 'Bona tarda', 'Bona tarda', 'Bona nit'],
    gl: ['Bos días', 'Boas tardes', 'Boas tardes', 'Boas noites'],
    eu: ['Egun on', 'Arratsalde on', 'Arratsalde on', 'Gabon'],
    pt: ['Bom dia', 'Boa tarde', 'Boa noite', 'Boa noite'],
    fr: ['Bonjour', 'Bonjour', 'Bonsoir', 'Bonne nuit'],
    it: ['Buongiorno', 'Buon pomeriggio', 'Buonasera', 'Buonanotte'],
    de: ['Guten Morgen', 'Guten Tag', 'Guten Abend', 'Gute Nacht'],
    nl: ['Goedemorgen', 'Goedemiddag', 'Goedenavond', 'Goedenacht'],
    sv: ['God morgon', 'God eftermiddag', 'God kväll', 'God natt'],
    da: ['Godmorgen', 'God eftermiddag', 'Godaften', 'Godnat'],
    nb: ['God morgen', 'God ettermiddag', 'God kveld', 'God natt'],
    no: ['God morgen', 'God ettermiddag', 'God kveld', 'God natt'],
    fi: ['Hyvää huomenta', 'Hyvää päivää', 'Hyvää iltaa', 'Hyvää yötä'],
    pl: ['Dobry ranek', 'Dobry wieczór', 'Dobry wieczór', 'Dobranoc'],
    cs: ['Dobré ráno', 'Dobré odpoledne', 'Dobrý večer', 'Dobrou noc'],
    sk: ['Dobré ráno', 'Dobré popoludnie', 'Dobrý večer', 'Dobrú noc'],
    hu: ['Jó reggelt', 'Jó napot', 'Jó estét', 'Jó éjszakát'],
    ro: ['Bună dimineața', 'Bună ziua', 'Bună seara', 'Noapte bună'],
    el: ['Καλημέρα', 'Καλό απόγευμα', 'Καλησπέρα', 'Καληνύχτα'],
    tr: ['Günaydın', 'İyi günler', 'İyi akşamlar', 'İyi geceler'],
    ru: ['Доброе утро', 'Добрый день', 'Добрый вечер', 'Доброй ночи'],
    uk: ['Доброго ранку', 'Доброго дня', 'Доброго вечора', 'Доброї ночі'],
    bg: ['Добро утро', 'Добър ден', 'Добър вечер', 'Лека нощ'],
    sr: ['Добро јутро', 'Добар дан', 'Добро вече', 'Добро ноћ'],
    hr: ['Dobro jutro', 'Dobar dan', 'Dobra večer', 'Dobra noć'],
    sl: ['Dobro jutro', 'Dober dan', 'Dober večer', 'Lahko noč'],
    ar: ['صباح الخير', 'مساء الخير', 'مساء الخير', 'تصبح على خير'],
    he: ['בוקר טוב', 'צהריים טובים', 'ערב טוב', 'לילה טוב'],
    fa: ['صبح بخیر', 'ظهر بخیر', 'عصر بخیر', 'شب بخیر'],
    hi: ['सुप्रभात।', 'नमस्ते।', 'शुभ संध्या।', 'शुभ रात्रि।'],
    bn: ['সুপ্রভাত।', 'শুভ অপরাহ্ন।', 'শুভ সন্ধ্যা।', 'শুভ রাত্রি।'],
    id: ['Selamat pagi', 'Selamat siang', 'Selamat malam', 'Selamat malam'],
    ms: ['Selamat pagi', 'Selamat petang', 'Selamat malam', 'Selamat malam'],
    vi: ['Chào buổi sáng', 'Chào buổi chiều', 'Chào buổi tối', 'Chúc ngủ ngon'],
    th: ['อรุณสวัสดิ์', 'สวัสดีตอนบ่าย', 'สวัสดีตอนเย็น', 'ราตรีสวัสดิ์'],
    zh: ['早上好。', '下午好。', '晚上好。', '晚安。'],
    ja: ['おはようございます。', 'こんにちは。', 'こんばんは。', 'おやすみなさい。'],
    ko: ['좋은 아침입니다', '좋은 오후입니다', '좋은 저녁입니다', '안녕히 주무세요'],
    sw: ['Habari za asubuhi', 'Habari za mchana', 'Habari za jioni', 'Usiku mwema'],
    af: ['Goeie more', 'Goeie middag', 'Goeie naand', 'Goeie nag'],
    ga: ['Maidin mhaith', 'Tráthnóna maith', 'Tráthnóna maith', 'Oíche mhaith'],
    cy: ['Bore da', 'Prynhawn da', 'Noswaith dda', 'Nos da'],
    is: ['Góðan daginn', 'Góðan daginn', 'Gott kvöld', 'Góða nótt'],
    et: ['Tere hommikust', 'Tere päevast', 'Tere õhtust', 'Head ööd'],
    lv: ['Labrīt', 'Labdien', 'Labvakar', 'Ar labu nakti'],
    lt: ['Labas rytas', 'Laba diena', 'Labas vakaras', 'Labos nakties'],
    eo: ['Bonan matenon', 'Bonan posttagmezon', 'Bonan vesperon', 'Bonan nokton'],
    la: ['Bonum mane', 'Bonum meridiem', 'Bonum vesperum', 'Bonam noctem'],
  };
  function lang() {
    let code = '';
    try { code = (window.SandpieLanguage && SandpieLanguage.effective && SandpieLanguage.effective()) || ''; } catch (_) {}
    if (!code) { try { code = navigator.language || 'en'; } catch (_) { code = 'en'; } }
    return String(code).toLowerCase().split(/[-_]/)[0];
  }
  // 5–11 morning · 12–17 afternoon · 18–21 evening · 22–4 night
  function slot(h) { return h >= 5 && h < 12 ? 0 : h < 18 ? 1 : h < 22 ? 2 : 3; }
  function greetingText() { const g = GREETINGS[lang()] || GREETINGS.en; return g[slot(new Date().getHours())]; }
  function updateGreeting() {
    const hc = document.getElementById('homeCenter'); if (!hc) return;
    let el = hc.querySelector('.home-greeting');
    if (!el) { el = document.createElement('div'); el.className = 'home-greeting'; hc.insertBefore(el, hc.firstChild); }
    const t = greetingText();
    if (el.textContent !== t) el.textContent = t;
  }

  /* ── mode persistence: SandpieConfig 'background' namespace, localStorage
     fallback so the choice survives even without config.js ── */
  const LS_BG = 'sandpie-background-mode';
  function loadMode() {
    try { if (window.SandpieConfig && SandpieConfig.get) { const v = SandpieConfig.get('background'); if (v && v.mode && MODES[v.mode]) return v.mode; } } catch (_) {}
    try { const v = localStorage.getItem(LS_BG); if (v && MODES[v]) return v; } catch (_) {}
    return 'clouds';
  }
  function saveMode(m) {
    try { localStorage.setItem(LS_BG, m); } catch (_) {}
    try { if (window.SandpieConfig && SandpieConfig.set) SandpieConfig.set('background', { mode: m }); } catch (_) {}
  }
  function applyMode(m) {
    if (!MODES[m]) m = 'clouds';
    if (m === mode) return mode;
    mode = m;
    retheme();          // re-derive the ramp (water uses a wider reach)
    dirty = true;
    if (window.SandpieSettings && typeof window.SandpieSettings.refreshPanel === 'function') {
      try { window.SandpieSettings.refreshPanel('appearance'); } catch (_) {}
    }
    return mode;
  }

  /* ── wiring ── */
  function boot() {
    mode = loadMode();
    retheme(); sync();
    spawnMoon();                     // one random moon per page load
    // Settings → Appearance → Background (another device/tab or this module's
    // own save) — re-apply live.
    try { if (window.SandpieConfig && SandpieConfig.subscribe) SandpieConfig.subscribe('background', () => { const m = loadMode(); if (m !== mode) applyMode(m); }); } catch (_) {}
    // theme switch (data-theme) and custom palettes (#themeOverride <style>) both
    // land in <head>/<html>; re-derive the ramp on either.
    new MutationObserver(() => { retheme(); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    new MutationObserver(() => { retheme(); }).observe(document.head, { childList: true, subtree: true, characterData: true });
    // home screen comes and goes as conversations mount/unmount: watch the pane.
    const pane = document.getElementById('messages');
    if (pane) new MutationObserver(() => { sync(); }).observe(pane, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    document.addEventListener('visibilitychange', () => { dirty = true; });
    setInterval(updateGreeting, 60 * 1000);        // crosses a time-of-day boundary
    // Settings → Language writes SandpieConfig['language']; re-greet at once.
    try { if (window.SandpieConfig && SandpieConfig.subscribe) SandpieConfig.subscribe('language', updateGreeting); } catch (_) {}
    try { if (window.SandpieConfig && SandpieConfig.ready) SandpieConfig.ready.then(updateGreeting); } catch (_) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();

  window.SandpieHomeSky = { refresh: () => { retheme(); sync(); }, greeting: greetingText };
  window.SandpieBackground = {
    modes: () => Object.keys(MODES).map(k => ({ id: k, label: MODES[k].label })),
    get: () => mode,
    set: (m) => { applyMode(m); saveMode(mode); sync(); },
    refresh: () => { retheme(); sync(); },
  };
})();
