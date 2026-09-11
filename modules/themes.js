/* ========== Theme Palette System ========== */
const _themePalettes = {
  'classic-dark': {
    bg: '#0d1117', surface: '#161b22', panel: '#21262d',
    accent: '#58a6ff', text: '#e6edf3', textDim: '#9ab0c8',
    border: '#30363d', borderBright: '#484f58',
    success: '#3fb950', danger: '#f85149', warn: '#d29922'
  },
  'classic-light': {
    bg: '#ffffff', surface: '#f6f8fa', panel: '#eaeef2',
    accent: '#85c4f0', text: '#1f2328', textDim: '#656d76',
    border: '#d0d7de', borderBright: '#b0b7be',
    success: '#1f883d', danger: '#cf222e', warn: '#9a6700'
  },
  'cyberpunk': {
    bg: '#050505', surface: '#0a0a0f', panel: '#11111a',
    accent: '#00f0ff', text: '#e8f4f8', textDim: '#7a8a9a',
    border: '#1a1a2e', borderBright: '#2d2d44',
    success: '#00ff88', danger: '#ff3366', warn: '#ffaa00'
  },
  'aurora': {
    bg: '#070b14', surface: 'rgba(15,23,42,0.6)', panel: 'rgba(30,41,59,0.5)',
    accent: '#38bdf8', text: '#f1f5f9', textDim: '#94a3b8',
    border: 'rgba(148,163,184,0.12)', borderBright: 'rgba(148,163,184,0.2)',
    success: '#34d399', danger: '#f87171', warn: '#fbbf24'
  },
  'electric': {
    bg: '#0a0a0a', surface: '#141414', panel: '#1e1e1e',
    accent: '#77C078', text: '#fafafa', textDim: '#888',
    border: '#2a2a2a', borderBright: '#444',
    success: '#00e676', danger: '#ff1744', warn: '#ffc400'
  },
  'clear': {
    bg: '#ffffff', surface: '#ffffff', panel: '#ffffff',
    accent: '#000000', text: '#000000', textDim: '#666666',
    border: '#000000', borderBright: '#000000',
    success: '#000000', danger: '#000000', warn: '#000000'
  }
};
const _paletteLabels = {
  bg: 'Background', surface: 'Surface', panel: 'Panel',
  accent: 'Accent', text: 'Text', textDim: 'Muted text',
  border: 'Border', borderBright: 'Bright border',
  success: 'Success', danger: 'Danger', warn: 'Warning'
};

/* ─── persistence: route theme settings through SandpieConfig's 'appearance'
   namespace when it's loaded (so they sync across a user's devices via OPFS),
   falling back to the original localStorage keys otherwise. Secret-free — just
   the chosen theme + any customized palettes. ─── */
function _cfg() { return window.SandpieConfig || null; }
function getThemeName() {
  var c = _cfg();
  if (c) { var a = c.get('appearance'); if (a && a.theme) return a.theme; }
  return localStorage.getItem('sandpie-theme') || null;
}
function setThemeName(name) {
  var c = _cfg();
  if (c) c.set('appearance', Object.assign({}, c.get('appearance', {}) || {}, { theme: name }));
  else localStorage.setItem('sandpie-theme', name);
}
function getPalette(name) {
  var c = _cfg();
  if (c) { var a = c.get('appearance'); return (a && a.palettes && a.palettes[name]) || null; }
  try { return JSON.parse(localStorage.getItem('sandpie-theme-palette-' + name) || 'null'); } catch (e) { return null; }
}
function setPalette(name, pal) {
  var c = _cfg();
  if (c) {
    var a = Object.assign({}, c.get('appearance', {}) || {});
    a.palettes = Object.assign({}, a.palettes || {}); a.palettes[name] = pal;
    c.set('appearance', a);
  } else localStorage.setItem('sandpie-theme-palette-' + name, JSON.stringify(pal));
}
function clearPalette(name) {
  var c = _cfg();
  if (c) {
    var a = Object.assign({}, c.get('appearance', {}) || {});
    if (a.palettes) { a.palettes = Object.assign({}, a.palettes); delete a.palettes[name]; }
    c.set('appearance', a);
  } else localStorage.removeItem('sandpie-theme-palette-' + name);
}
// One-time import of legacy localStorage theme settings into config. Call only
// after SandpieConfig.ready() so it can't clobber a copy synced from elsewhere.
function _importLegacyAppearance() {
  var c = _cfg(); if (!c) return;
  var cur = c.get('appearance');
  if (cur && typeof cur === 'object') return;   // already present — nothing to import
  var appearance = {};
  var t = localStorage.getItem('sandpie-theme'); if (t) appearance.theme = t;
  var palettes = {};
  try {
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (k && k.indexOf('sandpie-theme-palette-') === 0) {
        try { palettes[k.slice('sandpie-theme-palette-'.length)] = JSON.parse(localStorage.getItem(k)); } catch (e) {}
      }
    }
  } catch (e) {}
  if (Object.keys(palettes).length) appearance.palettes = palettes;
  if (Object.keys(appearance).length) c.set('appearance', appearance);
}

// applyTheme — apply a theme to the DOM WITHOUT persisting. Used at boot and
// when reacting to a config change (e.g. one synced from another device), so it
// must NEVER write back to SandpieConfig — that would re-fire the 'appearance'
// subscriber and loop.
function applyTheme(name) {
  var map = { 'midnight': 'classic-dark', 'light': 'classic-light' };
  name = map[name] || name;
  if (!_themePalettes[name]) name = 'electric';
  if (name === 'classic-dark') document.documentElement.removeAttribute('data-theme');
  else if (name === 'classic-light') document.documentElement.setAttribute('data-theme', 'light');
  else document.documentElement.setAttribute('data-theme', name);
  applyThemePalette(name);
  buildPaletteUI(name);
  var _tc = $('themeCustomize'); if (_tc) _tc.style.display = 'flex';
  updateThemeButtons();
  computeAccentNeg();
}
// setTheme — user action: persist the choice, then apply it.
function setTheme(name) {
  var map = { 'midnight': 'classic-dark', 'light': 'classic-light' };
  var resolved = map[name] || name;
  if (!_themePalettes[resolved]) resolved = 'electric';
  setThemeName(resolved);
  applyTheme(resolved);
  _reportTheme(resolved);
}

// _reportTheme — fire-and-forget push of the chosen theme to the server's
// per-user prefs (PATCH /prefs), so /admin "Others" can show which appearance
// each user runs. Never blocks or breaks the theme change.
function _reportTheme(name) {
  try {
    fetch('/prefs', {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appearance: { theme: name, updated_at: Math.floor(Date.now() / 1000) } })
    }).catch(function () {});
  } catch (e) {}
}

function applyThemePalette(name) {
  var palette = Object.assign({}, _themePalettes[name]);
  var saved = getPalette(name);
  if (saved) { try { Object.assign(palette, saved); } catch (e) {} }
  var css = ':root{ ';
  for (var key in palette) {
    if (key === 'accent-dim') continue; // derived, handled separately
    var prop = key === 'bg' ? '--sp-bg' : '--sp-' + key;
    css += prop + ':' + palette[key] + '!important; ';
  }
  // Inject accent-dim if present in saved palette
  if (palette['accent-dim']) {
    css += '--sp-accent-dim:' + palette['accent-dim'] + '!important; ';
  }
  css += '}';
  var style = document.getElementById('themeOverride');
  if (!style) { style = document.createElement('style'); style.id = 'themeOverride'; document.head.appendChild(style); }
  style.textContent = css;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', palette.accent);
  // Sync derived colors from current accent
  if (palette.accent && palette.accent.startsWith('#')) {
    updateDerivedColors(palette.accent);
  }
}

function buildPaletteUI(name) {
  var container = $('themePaletteRows');
  if (!container) return;
  container.innerHTML = '';
  var palette = Object.assign({}, _themePalettes[name]);
  var saved = getPalette(name);
  if (saved) { try { Object.assign(palette, saved); } catch (e) {} }
  for (var key in palette) {
    var label = _paletteLabels[key] || key;
    var val = palette[key];
    var hexVal = (!val.startsWith('#') || val.length !== 7) ? rgbaToHex(val) : val;
    if (!hexVal) continue;
    var row = document.createElement('div');
    row.className = 'palette-row';
    row.style.cssText = 'display:flex;align-items:center;gap:0.5rem;';
    var picker = document.createElement('input');
    picker.type = 'color';
    picker.value = hexVal.toUpperCase();
    picker.dataset.key = key;
    picker.dataset.origVal = val;
    picker.style.cssText = 'padding:0;width:28px;height:28px;border:none;background:transparent;cursor:pointer;';
    picker.addEventListener('input', onPaletteInput);
    var lab = document.createElement('span');
    lab.textContent = label;
    lab.style.cssText = 'font-size:0.75rem;color:var(--sp-text-dim);flex:1;';
    var hexDisp = document.createElement('span');
    hexDisp.className = 'hex';
    hexDisp.textContent = hexVal.toUpperCase();
    hexDisp.style.cssText = 'font-size:0.72rem;color:var(--sp-text-dim);font-family:"JetBrains Mono",monospace;min-width:5em;text-align:right;';
    hexDisp.dataset.hexFor = key;
    row.appendChild(picker);
    row.appendChild(lab);
    row.appendChild(hexDisp);
    container.appendChild(row);
  }
}

function onPaletteInput(e) {
  var picker = e.target;
  var key = picker.dataset.key;
  var color = picker.value;
  var hexDisp = picker.parentNode.querySelector('[data-hex-for="' + key + '"]');
  if (hexDisp) hexDisp.textContent = color.toUpperCase();
  var style = document.getElementById('themeOverride');
  if (style) {
    var css = style.textContent;
    var prop = key === 'bg' ? '--sp-bg' : '--sp-' + key;
    var re = new RegExp(prop + ':[^!;]+');
    if (re.test(css)) {
      css = css.replace(re, prop + ':' + color);
    } else {
      css = css.replace('}', ' ' + prop + ':' + color + '}');
    }
    style.textContent = css;
  }
  if (key === 'accent') {
    updateDerivedColors(color);
  }
}

function saveThemeColors() {
  var name = getThemeName() || 'classic-dark';
  var palette = {};
  var rows = $('themePaletteRows').querySelectorAll('.palette-row');
  for (var i = 0; i < rows.length; i++) {
    var picker = rows[i].querySelector('input[type="color"]');
    if (picker) palette[picker.dataset.key] = picker.value;
  }
  // Also save derived accent-dim so applyThemePalette can restore it
  var style = document.getElementById('themeOverride');
  if (style) {
    var m = style.textContent.match(/--sp-accent-dim:([^!;]+)/);
    if (m) palette['accent-dim'] = m[1].trim();
  }
  setPalette(name, palette);
  var hint = $('themeHint');
  if (hint) { hint.textContent = 'Colors saved!'; hint.style.opacity = '1'; setTimeout(function () { hint.style.opacity = '0'; }, 1200); }
}

function resetThemeColors() {
  var name = getThemeName() || 'classic-dark';
  clearPalette(name);
  applyThemePalette(name);
  buildPaletteUI(name);
  var defaultAccent = _themePalettes[name].accent;
  if (defaultAccent && defaultAccent.startsWith('#')) {
    updateDerivedColors(defaultAccent);
  }
}

function updateThemeButtons() {
  var name = getThemeName() || 'classic-dark';
  document.querySelectorAll('.theme-btn[data-t]').forEach(function (b) {
    b.classList.toggle('active', b.dataset.t === name);
  });
}

function applySavedCustom() {
  var saved = getThemeName() || 'electric';
  if (saved && _themePalettes[saved]) {
    applyTheme(saved);
    var pal = getPalette(saved);
    if (pal) { try { Object.assign(_themePalettes[saved], pal); applyThemePalette(saved); } catch (e) {} }
  } else {
    applyTheme('electric');
  }
  _reportTheme(getThemeName() || 'electric');   // also report users who never change theme
}

function rgbaToHex(rgba) {
  var m = rgba.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (!m) return null;
  return '#' + [+m[1], +m[2], +m[3]].map(function (x) { return x.toString(16).padStart(2, '0'); }).join('');
}

function updateDerivedColors(accent) {
  // Derive accent-dim from accent at 15% opacity
  var hex = accent.replace('#','');
  var r = parseInt(hex.slice(0,2),16);
  var g = parseInt(hex.slice(2,4),16);
  var b = parseInt(hex.slice(4,6),16);
  var dim = 'rgba(' + r + ',' + g + ',' + b + ',0.15)';

  // Inject into override style
  var style = document.getElementById('themeOverride');
  if (style) {
    var css = style.textContent;
    // Replace or add --sp-accent-dim
    if (css.indexOf('--sp-accent-dim:') >= 0) {
      css = css.replace(/--sp-accent-dim:[^!;]+/, '--sp-accent-dim:' + dim);
    } else {
      css = css.replace('}', ' --sp-accent-dim:' + dim + '}');
    }
    style.textContent = css;
  }

  // Also re-run accent-neg computation
  computeAccentNeg();
}

function computeAccentNeg() {
  var root = document.documentElement;
  var accent = getComputedStyle(root).getPropertyValue('--sp-accent').trim();
  if (!accent) return;
  var hex = accent.replace('#','');
  var r = parseInt(hex.slice(0,2),16)/255;
  var g = parseInt(hex.slice(2,4),16)/255;
  var b = parseInt(hex.slice(4,6),16)/255;
  var max = Math.max(r,g,b), min = Math.min(r,g,b);
  var h = 0, s = 0, l = (max+min)/2;
  if (max !== min) {
    var d = max-min;
    s = l > 0.5 ? d/(2-max-min) : d/(max+min);
    switch(max) {
      case r: h = ((g-b)/d + (g < b ? 6 : 0))/6; break;
      case g: h = ((b-r)/d + 2)/6; break;
      case b: h = ((r-g)/d + 4)/6; break;
    }
  }
  h = (h + 0.5) % 1;
  var hue2rgb = function(p,q,t) {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q-p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q-p) * (2/3 - t) * 6;
    return p;
  };
  var q = l < 0.5 ? l*(1+s) : l+s-l*s;
  var p = 2*l-q;
  var rr = Math.round(hue2rgb(p,q,h+1/3)*255);
  var gg = Math.round(hue2rgb(p,q,h)*255);
  var bb = Math.round(hue2rgb(p,q,h-1/3)*255);
  var neg = '#' + [rr,gg,bb].map(function(x){return x.toString(16).padStart(2,'0');}).join('');
  root.style.setProperty('--sp-accent-neg', neg);
}




/* ─── Chat column width ──────────────────────────────────────────────────────
   Deliberately NOT routed through SandpieConfig: a phone, a laptop and a 4K
   monitor want different widths, so this stays a per-device localStorage pref.
   0 / missing = fill the pane (the historical behaviour). */
var _CHAT_WIDTH_KEY = 'sandpie-chat-max-w';
var _CHAT_W_MIN = 560, _CHAT_W_MAX = 1600, _CHAT_W_STEP = 20;   // slider range; at MAX = fill the pane
function getChatWidth() {
  try { var v = parseInt(localStorage.getItem(_CHAT_WIDTH_KEY), 10); return v > 0 ? v : 0; } catch (e) { return 0; }
}
function _chatWidthLabel(w) { return w ? w + 'px' : 'Full'; }
function applyChatWidth() {
  var w = getChatWidth();
  document.documentElement.style.setProperty('--sp-chat-max-w', w ? w + 'px' : '100%');
  var r = document.getElementById('chatWidthRange'); if (r) r.value = w || _CHAT_W_MAX;
  var v = document.getElementById('chatWidthVal'); if (v) v.textContent = _chatWidthLabel(w);
}
function setChatWidth(px) {
  px = parseInt(px, 10) || 0;
  if (px >= _CHAT_W_MAX) px = 0;   // slider parked at the right end = no cap
  try { px ? localStorage.setItem(_CHAT_WIDTH_KEY, String(px)) : localStorage.removeItem(_CHAT_WIDTH_KEY); } catch (e) {}
  applyChatWidth();
}
window.setChatWidth = setChatWidth;

/* ─── Settings UI: Appearance lives in the gear modal (SandpieSettings). ─── */
var _CHAT_WIDTH_HTML = '<div style="margin-top:0.75rem;padding-top:0.5rem;border-top:1px solid var(--sp-border);">' +
  '<div style="font-size:0.72rem;color:var(--sp-text-dim);margin-bottom:0.35rem;">Chat width <span style="opacity:0.7">(this device only)</span></div>' +
  '<div class="chat-width-row">' +
  '<input type="range" id="chatWidthRange" min="' + _CHAT_W_MIN + '" max="' + _CHAT_W_MAX + '" step="' + _CHAT_W_STEP + '" ' +
  'oninput="setChatWidth(this.value)" title="Drag right to the end for full width">' +
  '<span class="chat-width-val" id="chatWidthVal"></span>' +
  '</div></div>';
var _APPEARANCE_HTML = `<div style="display:flex;gap:0.35rem;flex-wrap:wrap;">
      <button class="ghost theme-btn" data-t="classic-dark" onclick="setTheme('classic-dark')" title="Classic dark">Dark</button>
      <button class="ghost theme-btn" data-t="classic-light" onclick="setTheme('classic-light')" title="Classic light">Light</button>
      <button class="ghost theme-btn" data-t="cyberpunk" onclick="setTheme('cyberpunk')" title="Neon cyberpunk">Cybr</button>
      <button class="ghost theme-btn" data-t="aurora" onclick="setTheme('aurora')" title="Aurora glass">Aurora</button>
      <button class="ghost theme-btn" data-t="electric" onclick="setTheme('electric')" title="Electric bold">Bold</button>
      <button class="ghost theme-btn" data-t="clear" onclick="setTheme('clear')" title="Clear minimal">Clear</button>
    </div>
    <div id="themeCustomize" style="display:none;flex-direction:column;gap:0.5rem;margin-top:0.5rem;padding-top:0.5rem;border-top:1px solid var(--sp-border);">
      <div id="themePaletteRows" style="display:flex;flex-direction:column;gap:0.4rem;"></div>
      <div style="display:flex;gap:0.35rem;margin-top:0.25rem;">
        <button class="ghost" onclick="resetThemeColors()" style="font-size:0.72rem;">Reset defaults</button>
        <button class="ghost" onclick="saveThemeColors()" style="font-size:0.72rem;">Save colors</button>
      </div>
    </div>
    <div id="themeHint" style="font-size:0.65rem;color:var(--sp-text-dim);padding:0.5rem;margin-top:auto;text-align:center;transition:opacity 0.3s;opacity:0;">Pick a look.</div>` + _CHAT_WIDTH_HTML;
function _setupAppearancePanel() {
  applyChatWidth();   // highlight the active width button
  var saved = getThemeName() || 'classic-dark';
  if (_themePalettes[saved]) {
    updateThemeButtons();
    buildPaletteUI(saved);
    // The palette pickers live inside #themeCustomize, which is hidden until a
    // theme is applied. When this panel mounts the theme is already applied, so
    // reveal them now instead of waiting for the user to click a theme button.
    var tc = $('themeCustomize'); if (tc) tc.style.display = 'flex';
  }
}
function injectAppearanceUI() {
  if (window.SandpieSettings) {
    SandpieSettings.register({
      id: 'appearance', title: 'Appearance', order: 20,
      render: function(panel) { panel.innerHTML = _APPEARANCE_HTML; _setupAppearancePanel(); },
    });
    return;
  }
  setTimeout(injectAppearanceUI, 50);   // neither host ready yet — retry
}

function _refreshAppearancePanel() {
  var s = getThemeName();
  if (s && _themePalettes[s]) { updateThemeButtons(); if ($('themePaletteRows')) buildPaletteUI(s); }
}
function _bootThemes() {
  applySavedCustom();            // apply the theme immediately from the local mirror
  applyChatWidth();              // per-device chat column width (localStorage)
  injectAppearanceUI();          // register the gear panel (or sidebar fallback)
  var c = window.SandpieConfig;
  if (c) {
    // Once the durable/synced config has been reconciled, migrate any legacy
    // localStorage theme settings (once), then re-apply — a theme synced from
    // another device wins. Also re-apply on any later 'appearance' change.
    c.ready().then(function() { _importLegacyAppearance(); applySavedCustom(); _refreshAppearancePanel(); });
    c.subscribe('appearance', function() { applySavedCustom(); _refreshAppearancePanel(); });
  }
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _bootThemes);
} else {
  _bootThemes();
}
