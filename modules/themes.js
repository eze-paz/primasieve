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
    accent: '#ff3b5c', text: '#fafafa', textDim: '#888',
    border: '#2a2a2a', borderBright: '#444',
    success: '#00e676', danger: '#ff1744', warn: '#ffc400'
  }
};
const _paletteLabels = {
  bg: 'Background', surface: 'Surface', panel: 'Panel',
  accent: 'Accent', text: 'Text', textDim: 'Muted text',
  border: 'Border', borderBright: 'Bright border',
  success: 'Success', danger: 'Danger', warn: 'Warning'
};

function setTheme(name) {
  var map = { 'midnight': 'classic-dark', 'light': 'classic-light' };
  name = map[name] || name;
  if (!_themePalettes[name]) name = 'classic-dark';
  if (name === 'classic-dark') document.documentElement.removeAttribute('data-theme');
  else if (name === 'classic-light') document.documentElement.setAttribute('data-theme', 'light');
  else document.documentElement.setAttribute('data-theme', name);
  localStorage.setItem('sandpie-theme', name);
  applyThemePalette(name);
  buildPaletteUI(name);
  $('themeCustomize').style.display = 'flex';
  updateThemeButtons();
  computeAccentNeg();
}

function applyThemePalette(name) {
  var palette = Object.assign({}, _themePalettes[name]);
  var saved = localStorage.getItem('sandpie-theme-palette-' + name);
  if (saved) { try { Object.assign(palette, JSON.parse(saved)); } catch (e) {} }
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
  var saved = localStorage.getItem('sandpie-theme-palette-' + name);
  if (saved) { try { Object.assign(palette, JSON.parse(saved)); } catch (e) {} }
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
  var name = localStorage.getItem('sandpie-theme') || 'classic-dark';
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
  localStorage.setItem('sandpie-theme-palette-' + name, JSON.stringify(palette));
  var hint = $('themeHint');
  if (hint) { hint.textContent = 'Colors saved!'; hint.style.opacity = '1'; setTimeout(function () { hint.style.opacity = '0'; }, 1200); }
}

function resetThemeColors() {
  var name = localStorage.getItem('sandpie-theme') || 'classic-dark';
  localStorage.removeItem('sandpie-theme-palette-' + name);
  applyThemePalette(name);
  buildPaletteUI(name);
  var defaultAccent = _themePalettes[name].accent;
  if (defaultAccent && defaultAccent.startsWith('#')) {
    updateDerivedColors(defaultAccent);
  }
}

function updateThemeButtons() {
  var name = localStorage.getItem('sandpie-theme') || 'classic-dark';
  document.querySelectorAll('.theme-btn[data-t]').forEach(function (b) {
    b.classList.toggle('active', b.dataset.t === name);
  });
}

function applySavedCustom() {
  var saved = localStorage.getItem('sandpie-theme') || 'classic-dark';
  if (saved && _themePalettes[saved]) {
    setTheme(saved);
    var pal = localStorage.getItem('sandpie-theme-palette-' + saved);
    if (pal) { try { Object.assign(_themePalettes[saved], JSON.parse(pal)); applyThemePalette(saved); } catch (e) {} }
  } else {
    setTheme('classic-dark');
  }
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


/* ─── SandpieMenu registration for Appearance section ─── */
function injectAppearanceMenu() {
  if (typeof SandpieMenu === 'undefined') {
    // Retry after scripts load
    if (typeof window !== 'undefined') {
      setTimeout(injectAppearanceMenu, 50);
    }
    return;
  }
  if (SandpieMenu.get('themeSection')) return;
  SandpieMenu.add('themeSection', {
    title: 'Appearance',
    html: '<div style="display:flex;gap:0.35rem;flex-wrap:wrap;">' +
      '<button class="ghost theme-btn" data-t="classic-dark" onclick="setTheme('classic-dark')" title="Classic dark">Dark</button>' +
      '<button class="ghost theme-btn" data-t="classic-light" onclick="setTheme('classic-light')" title="Classic light">Light</button>' +
      '<button class="ghost theme-btn" data-t="cyberpunk" onclick="setTheme('cyberpunk')" title="Neon cyberpunk">Cybr</button>' +
      '<button class="ghost theme-btn" data-t="aurora" onclick="setTheme('aurora')" title="Aurora glass">Aurora</button>' +
      '<button class="ghost theme-btn" data-t="electric" onclick="setTheme('electric')" title="Electric bold">Bold</button>' +
      '</div>' +
      '<div id="themeCustomize" style="display:none;flex-direction:column;gap:0.5rem;margin-top:0.5rem;padding-top:0.5rem;border-top:1px solid var(--sp-border);">' +
        '<div id="themePaletteRows" style="display:flex;flex-direction:column;gap:0.4rem;"></div>' +
        '<div style="display:flex;gap:0.35rem;margin-top:0.25rem;">' +
          '<button class="ghost" onclick="resetThemeColors()" style="font-size:0.72rem;">Reset defaults</button>' +
          '<button class="ghost" onclick="saveThemeColors()" style="font-size:0.72rem;">Save colors</button>' +
        '</div>' +
      '</div>' +
      '<div id="themeHint" style="font-size:0.65rem;color:var(--sp-text-dim);padding:0.5rem;margin-top:auto;text-align:center;transition:opacity 0.3s;opacity:0;">Pick a look. Saved locally.</div>',
    onRender: function(body) {
      var saved = localStorage.getItem('sandpie-theme') || 'classic-dark';
      if (_themePalettes[saved]) {
        updateThemeButtons();
        buildPaletteUI(saved);
      }
    }
  });
}

// Auto-init: wait for DOM + SandpieMenu availability
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() {
    injectAppearanceMenu();
    applySavedCustom();
  });
} else {
  injectAppearanceMenu();
  applySavedCustom();
}
