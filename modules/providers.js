/**
 * Providers Module for Sandpie
 *
 * Registers an "AI provider" section in the sidebar via SandpieMenu.
 * Usage: <script type="module" src="modules/providers.js"></script>
 */

const PROVIDERS_KEY = 'sandpie-providers';
const ACTIVE_PROVIDER_KEY = 'sandpie-active-provider';

let _providers = [];
let _activeProviderId = null;
let _editingProviderId = null;
let _chipMenuTarget = null;

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Providers module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  SandpieMenu.add('aiSection', {
    title: 'AI provider',
    dot: 'aiDot',
    badge: null,
    open: false,
    html: `
      <div class="chip-row" id="providerChips"></div>
      <div class="hint" id="routingHint" style="margin-top:0.5rem;"></div>
    `,
    onRender(bodyEl) {
      loadProviders();
      _bindProviderListeners();
      renderChips();
      updateRoutingHint();
      refreshAiDot();
      // Auto-open if credentials are missing
      const ep = document.getElementById('endpoint');
      const ak = document.getElementById('apiKey');
      if ((!ep || !ep.value.trim()) || (!ak || !ak.value.trim())) {
        const details = document.getElementById('aiSection');
        if (details) details.open = true;
      }
    }
  });

  console.log('Providers module registered');
}

// ============================================================
// PROVIDER MANAGEMENT
// ============================================================

function loadProviders() {
  const raw = localStorage.getItem(PROVIDERS_KEY);
  try {
    const parsed = raw ? JSON.parse(raw) : [];
    _providers = Array.isArray(parsed) ? parsed.filter(p => p && typeof p === 'object' && p.id) : [];
  } catch (e) {
    console.warn('loadProviders: corrupt provider list in localStorage, resetting:', e);
    _providers = [];
  }
  _activeProviderId = localStorage.getItem(ACTIVE_PROVIDER_KEY);

  if (_providers.length === 0) {
    const old = JSON.parse(localStorage.getItem('opencode-config') || '{}');
    if (old.endpoint || old.model || old.apiKey) {
      const migrated = {
        id: 'provider_' + Date.now(),
        name: old.model || 'Provider',
        endpoint: old.endpoint || '',
        model: old.model || '',
        apiKey: old.apiKey || '',
        proxyUrl: old.proxyUrl || ''
      };
      _providers = [migrated];
      _activeProviderId = migrated.id;
      saveProviders();
    }
  }

  if (_activeProviderId && !_providers.find(p => p.id === _activeProviderId)) {
    _activeProviderId = _providers.length ? _providers[0].id : null;
  }
  if (!_activeProviderId && _providers.length) {
    _activeProviderId = _providers[0].id;
  }

  applyActiveProvider();
}

function saveProviders() {
  localStorage.setItem(PROVIDERS_KEY, JSON.stringify(_providers));
  localStorage.setItem(ACTIVE_PROVIDER_KEY, _activeProviderId || '');
}

function getActiveProvider() {
  return _providers.find(p => p.id === _activeProviderId) || null;
}

function applyActiveProvider() {
  const p = getActiveProvider();
  const ep = document.getElementById('endpoint');
  const mo = document.getElementById('model');
  const ak = document.getElementById('apiKey');
  const pu = document.getElementById('proxyUrl');
  if (ep) ep.value = p ? p.endpoint : '';
  if (mo) mo.value = p ? p.model : '';
  if (ak) ak.value = p ? p.apiKey : '';
  if (pu) pu.value = p ? p.proxyUrl : '';
  updateRoutingHint();
  refreshAiDot();
}

function _bindProviderListeners() {
  const pu = document.getElementById('proxyUrl');
  if (pu && !pu._spBound) {
    pu.addEventListener('input', updateRoutingHint);
    pu._spBound = true;
  }
  ['endpoint', 'apiKey'].forEach(id => {
    const el = document.getElementById(id);
    if (el && !el._spBound) {
      el.addEventListener('input', refreshAiDot);
      el._spBound = true;
    }
  });
}

// ============================================================
// UI RENDERING
// ============================================================

function renderChips() {
  const row = document.getElementById('providerChips');
  if (!row) return;
  row.innerHTML = '';

  for (const p of _providers) {
    try {
      if (!p || !p.id) continue;
      const chip = document.createElement('div');
      chip.className = 'chip' + (p.id === _activeProviderId ? ' active' : '');
      chip.textContent = p.name || p.model || 'Unnamed';
      chip.dataset.id = p.id;
      chip.onclick = () => activateProvider(p.id);
      chip.oncontextmenu = (e) => showChipMenu(e, p.id);
      row.appendChild(chip);
    } catch (e) {
      console.warn('renderChips: skipping malformed provider:', p, e);
    }
  }

  const addChip = document.createElement('div');
  addChip.className = 'chip add';
  addChip.textContent = '+ Add';
  addChip.onclick = () => openProviderModal();
  row.appendChild(addChip);
}

function activateProvider(id) {
  _activeProviderId = id;
  saveProviders();
  applyActiveProvider();
  renderChips();
}

// ============================================================
// MODAL
// ============================================================

function openProviderModal(providerId = null) {
  _editingProviderId = providerId;
  const p = providerId ? _providers.find(x => x.id === providerId) : null;
  document.getElementById('modalName').value = p ? (p.name || p.model || '') : '';
  document.getElementById('modalEndpoint').value = p ? p.endpoint : '';
  document.getElementById('modalModel').value = p ? p.model : '';
  document.getElementById('modalApiKey').value = p ? p.apiKey : '';
  document.getElementById('modalProxyUrl').value = p ? p.proxyUrl : '';
  const mt = document.getElementById('modalMaxTokens');
  if (mt) mt.value = (p && p.maxTokens != null) ? p.maxTokens : '';
  const tp = document.getElementById('modalTemperature');
  if (tp) tp.value = (p && p.temperature != null) ? p.temperature : '';
  const cw = document.getElementById('modalContextWindow');
  if (cw) cw.value = (p && p.contextWindow != null) ? p.contextWindow : '';
  document.getElementById('providerModal').style.display = '';
}

function closeProviderModal() {
  document.getElementById('providerModal').style.display = 'none';
  _editingProviderId = null;
}

function saveProviderModal() {
  const name = document.getElementById('modalName').value.trim();
  const endpoint = document.getElementById('modalEndpoint').value.trim();
  const model = document.getElementById('modalModel').value.trim();
  const apiKey = document.getElementById('modalApiKey').value.trim();
  const proxyUrl = document.getElementById('modalProxyUrl').value.trim();

  if (!endpoint || !model || !apiKey) {
    alert('Endpoint, model, and API key are required.');
    return;
  }

  // Optional per-provider tuning. The inputs only exist on pages that expose
  // them; where absent, leave any stored values untouched (don't clobber).
  const mtEl = document.getElementById('modalMaxTokens');
  const tpEl = document.getElementById('modalTemperature');
  const cwEl = document.getElementById('modalContextWindow');
  function applyTuning(p) {
    if (mtEl) {
      const v = parseInt(mtEl.value, 10);
      if (Number.isFinite(v) && v > 0) p.maxTokens = v; else delete p.maxTokens;
    }
    if (tpEl) {
      const t = parseFloat(tpEl.value);
      if (Number.isFinite(t) && t >= 0) p.temperature = t; else delete p.temperature;
    }
    if (cwEl) {
      const c = parseInt(cwEl.value, 10);
      if (Number.isFinite(c) && c > 0) p.contextWindow = c; else delete p.contextWindow;
    }
  }

  if (_editingProviderId) {
    const p = _providers.find(x => x.id === _editingProviderId);
    if (p) {
      p.name = name || model;
      p.endpoint = endpoint;
      p.model = model;
      p.apiKey = apiKey;
      p.proxyUrl = proxyUrl;
      applyTuning(p);
    }
  } else {
    const newP = {
      id: 'provider_' + Date.now(),
      name: name || model,
      endpoint, model, apiKey, proxyUrl
    };
    applyTuning(newP);
    _providers.push(newP);
    _activeProviderId = newP.id;
  }

  saveProviders();
  applyActiveProvider();
  renderChips();
  closeProviderModal();
}

// ============================================================
// CONTEXT MENU
// ============================================================

function showChipMenu(e, providerId) {
  e.preventDefault();
  _chipMenuTarget = providerId;
  const menu = document.getElementById('chipContextMenu');
  menu.style.display = '';
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
}

function hideChipMenu() {
  document.getElementById('chipContextMenu').style.display = 'none';
  _chipMenuTarget = null;
}

function editProviderFromMenu() {
  if (_chipMenuTarget) openProviderModal(_chipMenuTarget);
  hideChipMenu();
}

function duplicateProviderFromMenu() {
  if (!_chipMenuTarget) return;
  const p = _providers.find(x => x.id === _chipMenuTarget);
  if (!p) { hideChipMenu(); return; }
  const copy = {
    id: 'provider_' + Date.now(),
    name: (p.name || p.model) + ' (copy)',
    endpoint: p.endpoint, model: p.model, apiKey: p.apiKey, proxyUrl: p.proxyUrl
  };
  if (p.maxTokens != null) copy.maxTokens = p.maxTokens;
  if (p.temperature != null) copy.temperature = p.temperature;
  if (p.contextWindow != null) copy.contextWindow = p.contextWindow;
  _providers.push(copy);
  saveProviders();
  renderChips();
  hideChipMenu();
}

function deleteProviderFromMenu() {
  if (!_chipMenuTarget) return;
  const p = _providers.find(x => x.id === _chipMenuTarget);
  if (p && confirm('Delete "' + (p.name || p.model) + '"?')) {
    _providers = _providers.filter(x => x.id !== _chipMenuTarget);
    if (_activeProviderId === _chipMenuTarget) {
      _activeProviderId = _providers.length ? _providers[0].id : null;
    }
    saveProviders();
    applyActiveProvider();
    renderChips();
  }
  hideChipMenu();
}

// ============================================================
// HINT / STATUS
// ============================================================

function updateRoutingHint() {
  const remote = (document.getElementById('proxyUrl')?.value || '').trim();
  const hint = document.getElementById('routingHint');
  if (!hint) return;
  if (remote) hint.textContent = 'Routing via ' + remote.replace(/^https?:\/\//, '');
  else if (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
    hint.textContent = 'Routing via local /proxy/';
  else
    hint.textContent = 'Direct calls (CORS required, e.g. OpenRouter)';
}

function refreshAiDot() {
  const ok = document.getElementById('endpoint')?.value.trim() && document.getElementById('apiKey')?.value.trim();
  const dot = document.getElementById('aiDot');
  if (dot) { dot.classList.remove('ok', 'warn', 'err'); if (ok) dot.classList.add('ok'); }
}

// ============================================================
// GLOBAL API
// ============================================================

window.SandpieProviders = {
  getActive: getActiveProvider,
  load: loadProviders,
  apply: applyActiveProvider,
  list: () => _providers.slice(),
  get activeId() { return _activeProviderId; },
  openModal: openProviderModal,
  closeModal: closeProviderModal,
  saveModal: saveProviderModal,
  showMenu: showChipMenu,
  hideMenu: hideChipMenu,
  editFromMenu: editProviderFromMenu,
  duplicateFromMenu: duplicateProviderFromMenu,
  deleteFromMenu: deleteProviderFromMenu,
  updateHint: updateRoutingHint,
  refreshDot: refreshAiDot,
};

// Global click handler to hide chip menu
document.addEventListener('click', hideChipMenu);

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
