/**
 * Themes Module for Sandpie
 *
 * Registers a "Theme" section in the sidebar via SandpieMenu.
 * Usage: <script type="module" src="modules/themes.js"></script>
 */

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Themes module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  SandpieMenu.add('themesSection', {
    title: 'Theme',
    badge: null,
    open: false,
    html: `
      <div class="chip-row" id="themePresets">
        <span class="chip active" data-preset="midnight">Midnight</span>
        <span class="chip" data-preset="light">Light</span>
        <span class="chip" data-preset="custom">Custom</span>
      </div>
      <div id="customColors" style="display:none; flex-direction:column; gap:0.375rem; margin-top:0.5rem;">
        <label style="font-size:0.7rem; color:var(--sp-text-dim); text-transform:uppercase;">Accent</label>
        <input type="color" id="customAccent" value="#58a6ff">
        <label style="font-size:0.7rem; color:var(--sp-text-dim); text-transform:uppercase;">Background</label>
        <input type="color" id="customBg" value="#0d1117">
        <label style="font-size:0.7rem; color:var(--sp-text-dim); text-transform:uppercase;">Surface</label>
        <input type="color" id="customSurface" value="#161b22">
        <label style="font-size:0.7rem; color:var(--sp-text-dim); text-transform:uppercase;">Text</label>
        <input type="color" id="customText" value="#e6edf3">
        <button class="ghost" id="resetThemeBtn" style="margin-top:0.25rem; font-size:0.75rem;">Reset to midnight</button>
      </div>
    `,
    onRender(bodyEl) {
      bodyEl.querySelectorAll('#themePresets .chip').forEach(chip => {
        chip.addEventListener('click', () => setTheme(chip.dataset.preset));
      });
      ['customAccent', 'customBg', 'customSurface', 'customText'].forEach(id => {
        const el = bodyEl.querySelector('#' + id);
        if (el) el.addEventListener('input', applyCustomTheme);
      });
      const resetBtn = bodyEl.querySelector('#resetThemeBtn');
      if (resetBtn) resetBtn.addEventListener('click', resetCustomTheme);

      const saved = localStorage.getItem('sandpie-theme') || 'midnight';
      setTheme(saved);
      const custom = localStorage.getItem('sandpie-custom');
      if (custom) {
        try {
          const c = JSON.parse(custom);
          const accentEl = bodyEl.querySelector('#customAccent');
          const bgEl = bodyEl.querySelector('#customBg');
          const surfaceEl = bodyEl.querySelector('#customSurface');
          const textEl = bodyEl.querySelector('#customText');
          if (accentEl) accentEl.value = c.accent;
          if (bgEl) bgEl.value = c.bg;
          if (surfaceEl) surfaceEl.value = c.surface;
          if (textEl) textEl.value = c.text;
        } catch (e) {}
      }
    }
  });
  console.log('Themes module registered');
}

function setTheme(name) {
  document.querySelectorAll('#themePresets .chip').forEach(c => {
    c.classList.toggle('active', c.dataset.preset === name);
  });
  const customPanel = document.getElementById('customColors');
  if (name === 'custom') {
    customPanel.style.display = 'flex';
    applyCustomTheme();
  } else {
    customPanel.style.display = 'none';
    if (name === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }
  localStorage.setItem('sandpie-theme', name);
  computeAccentNeg();
}

function applyCustomTheme() {
  const accent = document.getElementById('customAccent').value;
  const bg = document.getElementById('customBg').value;
  const surface = document.getElementById('customSurface').value;
  const text = document.getElementById('customText').value;
  const r = parseInt(accent.slice(1, 3), 16);
  const g = parseInt(accent.slice(3, 5), 16);
  const b = parseInt(accent.slice(5, 7), 16);
  document.documentElement.style.setProperty('--sp-bg', bg);
  document.documentElement.style.setProperty('--sp-surface', surface);
  document.documentElement.style.setProperty('--sp-accent', accent);
  document.documentElement.style.setProperty('--sp-accent-dim', `rgba(${r},${g},${b},0.35)`);
  document.documentElement.style.setProperty('--sp-text', text);
  document.documentElement.style.setProperty('--sp-text-dim', text);
  localStorage.setItem('sandpie-custom', JSON.stringify({ accent, bg, surface, text }));
  computeAccentNeg();
}

function resetCustomTheme() {
  document.getElementById('customAccent').value = '#58a6ff';
  document.getElementById('customBg').value = '#0d1117';
  document.getElementById('customSurface').value = '#161b22';
  document.getElementById('customText').value = '#e6edf3';
  localStorage.removeItem('sandpie-custom');
  setTheme('midnight');
}
function computeAccentNeg() {
  const root = document.documentElement;
  const accent = getComputedStyle(root).getPropertyValue('--sp-accent').trim();
  if (!accent) return;
  // Parse hex → RGB
  const hex = accent.replace('#', '');
  const r = parseInt(hex.slice(0, 2), 16) / 255;
  const g = parseInt(hex.slice(2, 4), 16) / 255;
  const b = parseInt(hex.slice(4, 6), 16) / 255;
  // RGB → HSL
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  h = (h + 0.5) % 1;
  const hue2rgb = (p, q, t) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const rr = Math.round(hue2rgb(p, q, h + 1/3) * 255);
  const gg = Math.round(hue2rgb(p, q, h) * 255);
  const bb = Math.round(hue2rgb(p, q, h - 1/3) * 255);
  const neg = '#' + [rr, gg, bb].map(x => x.toString(16).padStart(2, '0')).join('');
  root.style.setProperty('--sp-accent-neg', neg);
}

window.computeAccentNeg = computeAccentNeg;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
