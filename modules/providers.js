/**
 * Providers Module for Sandpie
 *
 * "AI provider" settings: chips to pick the active provider, with the selected
 * provider's fields shown inline right below — no separate popup modal. The
 * panel lives in the gear Settings modal (SandpieSettings); falls back to the
 * sidebar (SandpieMenu) when settings.js isn't loaded (e.g. the stable page).
 *
 * Storage stays in localStorage: a provider definition includes its API key (a
 * secret), so providers are NOT synced to the SandpieConfig blob.
 *
 * account.js may inject a "managed" provider at runtime (on company sign-in) via
 * setManaged(): it shows as a read-only chip, is never persisted, and is removed
 * on sign-out.
 */

const PROVIDERS_KEY = 'sandpie-providers';
const ACTIVE_PROVIDER_KEY = 'sandpie-active-provider';

let _providers = [];
let _activeProviderId = null;
let _managed = [];              // company providers injected by account.js (one read-only chip per managed model); in-memory only, never persisted
const MANAGED_ID = '__managed'; // id prefix — each managed provider's id is `__managed:<model>`
function isManagedId(id) { return typeof id === 'string' && id.indexOf(MANAGED_ID + ':') === 0; }

const AI_HTML = `
      <div id="providerChips"></div>
      <div id="providerManagedNote" style="display:none; margin-top:1rem; padding-top:0.85rem; border-top:1px solid var(--sp-border); font-size:0.78rem; color:var(--sp-text-dim);">This provider is provided by your company sign-in — its settings are managed for you.</div>
      <div id="providerForm" style="display:none; flex-direction:column; gap:0.4rem; margin-top:1rem; padding-top:0.85rem; border-top:1px solid var(--sp-border);">
        <div style="font-size:0.7rem; color:var(--sp-text-dim); text-transform:uppercase; letter-spacing:0.04em;">Selected provider</div>
        <select id="spType">
          <option value="openai">API (OpenAI-compatible)</option>
          <option value="wllama">Local model (wllama, in-browser)</option>
          <option value="transformersjs">Local model (Transformers.js, in-browser)</option>
          <option value="litertlm">Local model (LiteRT-LM / Gemma, in-browser)</option>
        </select>
        <select id="spWllamaModel" style="display:none;"></select>
        <select id="spTransformersJSModel" style="display:none;"></select>
        <select id="spLiteRTLMModel" style="display:none;"></select>
        <input id="spName" autocomplete="off" placeholder="Name (e.g. Main, Backup)">
        <input id="spEndpoint" autocomplete="off" placeholder="Base URL (e.g. https://api.openai.com/v1)">
        <input id="spModel" autocomplete="off" placeholder="Model (e.g. gpt-4o)">
        <input id="spApiKey" type="text" autocomplete="off" style="-webkit-text-security:disc; text-security:disc;" placeholder="API key">
        <input id="spProxyUrl" autocomplete="off" placeholder="Proxy URL (optional)">
        <input id="spContextWindow" type="number" min="1" autocomplete="off" placeholder="Context window (e.g. 128000)">
        <input id="spMaxTokens" type="number" min="1" autocomplete="off" placeholder="Max output tokens (optional)">
        <input id="spTemperature" type="number" min="0" max="2" step="0.1" autocomplete="off" placeholder="Temperature (optional, 0–2)">
        <input id="spReasoningEffort" list="spReasoningEffortList" autocomplete="off" placeholder="Reasoning effort (reasoning models only: minimal/low/medium/high)">
        <datalist id="spReasoningEffortList"><option value="minimal"></option><option value="low"></option><option value="medium"></option><option value="high"></option><option value="none"></option></datalist>
        <div id="spWllamaParams" style="display:none; flex-direction:column; gap:0.4rem;">
          <div style="font-size:0.7rem; color:var(--sp-text-dim); text-transform:uppercase; letter-spacing:0.04em;">Local sampling &amp; reasoning</div>
          <input id="spTopP" type="number" min="0" max="1" step="0.01" autocomplete="off" placeholder="top_p (e.g. 0.8)">
          <input id="spTopK" type="number" min="0" step="1" autocomplete="off" placeholder="top_k (e.g. 20)">
          <input id="spMinP" type="number" min="0" max="1" step="0.01" autocomplete="off" placeholder="min_p (e.g. 0)">
          <input id="spFreqPenalty" type="number" min="-2" max="2" step="0.1" autocomplete="off" placeholder="frequency_penalty (−2 to 2)">
          <input id="spPresencePenalty" type="number" min="-2" max="2" step="0.1" autocomplete="off" placeholder="presence_penalty (−2 to 2)">
          <input id="spSeed" type="number" step="1" autocomplete="off" placeholder="seed (optional — fixed = reproducible)">
          <select id="spReasoning">
            <option value="auto">Thinking: auto (model default)</option>
            <option value="think">Thinking: on (/think)</option>
            <option value="no_think">Thinking: off (/no_think)</option>
          </select>
          <select id="spFlashAttn">
            <option value="false">Flash attention: off (safer)</option>
            <option value="true">Flash attention: on (faster, may crash)</option>
          </select>
          <input id="spGpuLayers" type="number" min="0" step="1" autocomplete="off" placeholder="GPU layers (blank/0 = CPU, 999 = all, may crash)">
        </div>
        <div style="display:flex; gap:0.35rem;">
          <button class="ghost" type="button" id="spDuplicate" style="flex:1;">Duplicate</button>
          <button class="ghost" type="button" id="spDelete" style="flex:1;">Delete</button>
        </div>
      </div>
      <div id="routingHint" style="margin-top:0.5rem; font-size:0.7rem; color:var(--sp-text-dim);"></div>
    `;

// Prefer the gear modal (SandpieSettings); fall back to the sidebar (SandpieMenu).
function init() {
  if (window.SandpieSettings) {
    SandpieSettings.register({
      id: 'aiProvider', title: 'AI provider', order: 10,
      render(panel) { panel.innerHTML = AI_HTML; _wireProviderPanel(); },
    });
    return;
  }
  if (typeof SandpieMenu !== 'undefined') {
    SandpieMenu.add('aiSection', { title: 'AI provider', dot: 'aiDot', badge: null, open: false, html: AI_HTML, onRender: _wireProviderPanel });
    return;
  }
  setTimeout(init, 500);   // neither host ready yet — retry
}

function _wireProviderPanel() {
  loadProviders();
  renderChips();
  for (const id of ['spName','spEndpoint','spModel','spApiKey','spProxyUrl','spContextWindow','spMaxTokens','spTemperature','spReasoningEffort','spTopP','spTopK','spMinP','spFreqPenalty','spPresencePenalty','spSeed','spReasoning','spFlashAttn','spGpuLayers']) {
    const el = document.getElementById(id);
    if (el && !el._spBound) { el.addEventListener('change', commitForm); el._spBound = true; }
  }
  const typeSel = document.getElementById('spType');
  if (typeSel && !typeSel._spBound) { typeSel.addEventListener('change', () => { commitForm(); applyTypeUI(); }); typeSel._spBound = true; }
  const wmSel = document.getElementById('spWllamaModel');
  if (wmSel && !wmSel._spBound) {
    if (typeof SandpieWllama !== 'undefined' && !wmSel.options.length) {
      wmSel.innerHTML = '<option value="">— pick a model —</option>'
        + SandpieWllama.DEFAULT_MODELS.map(m => `<option value="${m.url}">${m.label}</option>`).join('')
        + '<option value="__custom">Custom GGUF URL…</option>';
    }
    wmSel.addEventListener('change', () => {
      const v = wmSel.value;
      if (!v || v === '__custom') return;   // leave the Base URL field for manual entry
      const m = (typeof SandpieWllama !== 'undefined') ? SandpieWllama.DEFAULT_MODELS.find(x => x.url === v) : null;
      const ep = document.getElementById('spEndpoint'); if (ep) ep.value = v;
      const mo = document.getElementById('spModel'); if (mo && m) mo.value = m.label;
      commitForm();
    });
    wmSel._spBound = true;
  }
  const tjSel = document.getElementById('spTransformersJSModel');
  if (tjSel && !tjSel._spBound) {
    if (typeof SandpieTransformersJS !== 'undefined' && !tjSel.options.length) {
      tjSel.innerHTML = '<option value="">— pick a model —</option>'
        + SandpieTransformersJS.DEFAULT_MODELS.map(m => `<option value="${m.modelId}">${m.label}</option>`).join('')
        + '<option value="__custom">Custom HF model ID…</option>';
    }
    tjSel.addEventListener('change', () => {
      const v = tjSel.value;
      if (!v || v === '__custom') return;
      const m = (typeof SandpieTransformersJS !== 'undefined') ? SandpieTransformersJS.DEFAULT_MODELS.find(x => x.modelId === v) : null;
      const ep = document.getElementById('spEndpoint'); if (ep) ep.value = v;
      const mo = document.getElementById('spModel'); if (mo && m) mo.value = m.id;
      commitForm();
    });
    tjSel._spBound = true;
  }
  const lrSel = document.getElementById('spLiteRTLMModel');
  if (lrSel && !lrSel._spBound) {
    if (typeof SandpieLiteRTLM !== 'undefined' && !lrSel.options.length) {
      lrSel.innerHTML = '<option value="">— pick a model —</option>'
        + SandpieLiteRTLM.DEFAULT_MODELS.map(m => `<option value="${m.modelId}">${m.label}</option>`).join('')
        + '<option value="__custom">Custom .litertlm URL…</option>';
    }
    lrSel.addEventListener('change', () => {
      const v = lrSel.value;
      if (!v || v === '__custom') return;
      const m = (typeof SandpieLiteRTLM !== 'undefined') ? SandpieLiteRTLM.DEFAULT_MODELS.find(x => x.modelId === v) : null;
      const ep = document.getElementById('spEndpoint'); if (ep) ep.value = v;
      const mo = document.getElementById('spModel'); if (mo && m) mo.value = m.id;
      commitForm();
    });
    lrSel._spBound = true;
  }
  document.getElementById('spDuplicate')?.addEventListener('click', duplicateSelected);
  document.getElementById('spDelete')?.addEventListener('click', deleteSelected);
  if (_activeProviderId) loadFormFor(_activeProviderId);
  applyTypeUI();
  updateRoutingHint();
  refreshAiDot();
}

// ============================================================
// PROVIDER STORAGE (localStorage — secrets stay local)
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

  if (_activeProviderId && !getProviderById(_activeProviderId)) {
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

// Resolve any id, including the in-memory managed provider.
function getProviderById(id) {
  return _managed.find(p => p.id === id) || _providers.find(p => p.id === id) || null;
}

function getActiveProvider() {
  return getProviderById(_activeProviderId);
}

// Push the active provider's connection details into the hidden inputs that
// conversations.js reads (endpoint/model/apiKey/proxyUrl).
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
  renderModelPicker();   // keep the composer model-picker label/selection in sync
}

// Ensure a model is selected before a send. If the hidden #model input is empty
// but a configured provider has one, activate it instead of forcing the user to
// pick (a better default than erroring). Returns true once a model is set.
function ensureUsable() {
  const modelSet = () => !!(document.getElementById('model')?.value || '').trim();
  if (modelSet()) return true;
  // The active provider may have a model that simply wasn't synced to the inputs.
  const active = getActiveProvider();
  if (active && (active.model || '').trim() && (active.endpoint || '').trim()) {
    applyActiveProvider();
    if (modelSet()) return true;
  }
  // Otherwise pick the first configured provider that actually has a model.
  const candidate = [..._managed, ..._providers].find(p => (p.model || '').trim() && (p.endpoint || '').trim());
  if (candidate) selectProvider(candidate.id);
  return modelSet();
}

// ============================================================
// CHIPS  (pick the active provider; "+ Add" creates a new one)
// ============================================================

function renderChips() {
  renderModelPicker();   // composer picker tracks list changes even when the gear modal is closed
  const row = document.getElementById('providerChips');
  if (!row) return;
  row.innerHTML = '';
  const makeChip = (p) => {
    const chip = document.createElement('div');
    chip.className = 'chip' + (p.id === _activeProviderId ? ' active' : '') + (p.managed ? ' managed' : '');
    chip.textContent = p.name || p.model || 'Unnamed';
    chip.dataset.id = p.id;
    if (p.managed) chip.title = 'Provided by your company sign-in';
    chip.onclick = () => selectProvider(p.id);
    return chip;
  };
  const groupOf = (chips) => {
    const g = document.createElement('div');
    g.className = 'chip-row';
    chips.forEach(c => g.appendChild(c));
    return g;
  };
  const label = (text, top) => {
    const d = document.createElement('div');
    d.textContent = text;
    d.style.cssText = 'font-size:0.65rem; color:var(--sp-text-dim); text-transform:uppercase; letter-spacing:0.05em; margin:' + (top ? '0.7rem' : '0') + ' 0 0.35rem;';
    return d;
  };
  const addChip = document.createElement('div');
  addChip.className = 'chip add';
  addChip.textContent = '+ Add';
  addChip.onclick = () => addProvider();
  // Two labeled sections only when there are company-managed providers to
  // separate; otherwise a single flat row (unchanged for anonymous users).
  if (_managed.length) {
    row.appendChild(label('Company', false));
    row.appendChild(groupOf(_managed.map(makeChip)));
    row.appendChild(label('Your providers', true));
    row.appendChild(groupOf(_providers.map(makeChip).concat(addChip)));
  } else {
    row.appendChild(groupOf(_providers.map(makeChip).concat(addChip)));
  }
}

// Compact model selector for the composer — a "dropup" chip. Mirrors renderChips'
// Company / Your-models split (a clean separator line between them, only when there
// ARE company models, i.e. not anonymous). Lives in the input bar so the model is
// switchable without opening Settings. No-op if #modelPicker isn't on the page.
function renderModelPicker() {
  const host = document.getElementById('modelPicker');
  if (!host) return;
  const wasOpen = host.classList.contains('open');
  const active = getActiveProvider();
  host.innerHTML = '';
  host.classList.toggle('open', wasOpen);   // preserve open state across a re-render

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'mp-trigger';
  trigger.title = active ? ('Model: ' + (active.model || active.name || '')) : 'Pick a model';
  const lbl = document.createElement('span');
  lbl.className = 'mp-label';
  lbl.textContent = active ? (active.name || active.model || 'Model') : 'Select model';
  const caret = document.createElement('span');
  caret.className = 'mp-caret';
  caret.textContent = '▴';
  trigger.append(lbl, caret);
  trigger.addEventListener('click', (e) => { e.stopPropagation(); host.classList.toggle('open'); if (host.classList.contains('open')) positionModelPickerPanel(host); });

  const panel = document.createElement('div');
  panel.className = 'mp-panel';
  const item = (p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'mp-item' + (p.id === _activeProviderId ? ' active' : '');
    b.textContent = p.name || p.model || 'Unnamed';
    if (p.model) b.title = p.model;
    b.addEventListener('click', () => { host.classList.remove('open'); selectProvider(p.id); });
    return b;
  };
  const hdr = (t) => { const d = document.createElement('div'); d.className = 'mp-hdr'; d.textContent = t; return d; };
  const empty = (t) => { const d = document.createElement('div'); d.className = 'mp-empty'; d.textContent = t; return d; };

  if (_managed.length) {
    panel.appendChild(hdr('Company'));
    _managed.forEach(p => panel.appendChild(item(p)));
    panel.appendChild(Object.assign(document.createElement('div'), { className: 'mp-sep' }));
    panel.appendChild(hdr('Your models'));
    if (_providers.length) _providers.forEach(p => panel.appendChild(item(p)));
    else panel.appendChild(empty('None yet — add one in Settings'));
  } else if (_providers.length) {
    _providers.forEach(p => panel.appendChild(item(p)));
  } else {
    panel.appendChild(empty('No models — add one in Settings → AI provider'));
  }

  host.append(trigger, panel);
  if (wasOpen) positionModelPickerPanel(host);
}

// The dropup panel is position:fixed so it escapes the composer's overflow:hidden
// (.input-wrap clips to its rounded corners). Anchor it just above the trigger, in
// viewport coordinates, clamped so a wide panel never spills off the screen edge.
function positionModelPickerPanel(host) {
  const trig = host.querySelector('.mp-trigger');
  const panel = host.querySelector('.mp-panel');
  if (!trig || !panel) return;
  const r = trig.getBoundingClientRect();
  panel.style.bottom = (window.innerHeight - r.top + 6) + 'px';
  const pw = panel.offsetWidth || 220;
  panel.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pw - 8)) + 'px';
}

// ============================================================
// INLINE FORM  (settings of the selected/active provider)
// ============================================================

// Selecting a chip activates that provider AND loads it into the form below.
function selectProvider(id) {
  _activeProviderId = id;
  saveProviders();
  applyActiveProvider();
  loadFormFor(id);
  renderChips();
}

function loadFormFor(id) {
  const form = document.getElementById('providerForm');
  const note = document.getElementById('providerManagedNote');
  if (!form) return;
  const p = getProviderById(id);
  // Managed (company) providers are read-only: hide the editable form, show a note.
  if (p && p.managed) { form.style.display = 'none'; if (note) note.style.display = 'block'; return; }
  if (note) note.style.display = 'none';
  if (!p) { form.style.display = 'none'; return; }
  form.style.display = 'flex';
  const set = (fid, v) => { const el = document.getElementById(fid); if (el) el.value = (v != null ? v : ''); };
  set('spName', p.name); set('spEndpoint', p.endpoint); set('spModel', p.model);
  set('spApiKey', p.apiKey); set('spProxyUrl', p.proxyUrl);
  set('spContextWindow', p.contextWindow); set('spMaxTokens', p.maxTokens); set('spTemperature', p.temperature);
  set('spReasoningEffort', p.reasoningEffort);
  set('spType', p.type || 'openai');
  set('spTopP', p.topP); set('spTopK', p.topK); set('spMinP', p.minP);
  set('spFreqPenalty', p.frequencyPenalty); set('spPresencePenalty', p.presencePenalty); set('spSeed', p.seed);
  const rs = document.getElementById('spReasoning'); if (rs) rs.value = p.reasoning || 'auto';
  const fa = document.getElementById('spFlashAttn'); if (fa) fa.value = p.flashAttn ? 'true' : 'false';
  set('spGpuLayers', p.nGpuLayers);
  const wm = document.getElementById('spWllamaModel');
  if (wm) wm.value = (p.type === 'wllama' && p.endpoint) ? p.endpoint : '';
  const tj = document.getElementById('spTransformersJSModel');
  if (tj) tj.value = (p.type === 'transformersjs' && p.endpoint) ? p.endpoint : '';
  const lr = document.getElementById('spLiteRTLMModel');
  if (lr) lr.value = (p.type === 'litertlm' && p.endpoint) ? p.endpoint : '';
  applyTypeUI();
}

// Show/hide provider fields based on the selected backend type.
function applyTypeUI() {
  const type = (document.getElementById('spType')?.value) || 'openai';
  const wllama = type === 'wllama';
  const transformersjs = type === 'transformersjs';
  const litertlm = type === 'litertlm';
  const local = wllama || transformersjs || litertlm;
  const show = (id, on) => { const el = document.getElementById(id); if (el) el.style.display = on ? '' : 'none'; };
  show('spWllamaModel', wllama);
  show('spTransformersJSModel', transformersjs);
  show('spLiteRTLMModel', litertlm);
  show('spApiKey', !local);
  show('spProxyUrl', !local);
  show('spReasoningEffort', !local);
  const wp = document.getElementById('spWllamaParams');
  if (wp) wp.style.display = local ? 'flex' : 'none';
  const ep = document.getElementById('spEndpoint');
  if (ep) ep.placeholder = local ? 'Model ID (picker above; gated models need HF token)' : 'Base URL (e.g. https://api.openai.com/v1)';
  const cw = document.getElementById('spContextWindow');
  if (cw) cw.placeholder = local ? 'Context window (n_ctx, default 8192)' : 'Context window (e.g. 128000)';
}

// Commit form edits to the active provider (auto-save on field change/blur).
function commitForm() {
  const p = getActiveProvider();
  if (!p || p.managed) return;   // managed providers are read-only
  const val = id => (document.getElementById(id)?.value || '').trim();
  const num = id => { const n = parseFloat(document.getElementById(id)?.value); return Number.isFinite(n) ? n : null; };
  p.type = (document.getElementById('spType')?.value) || 'openai';
  p.endpoint = val('spEndpoint');
  p.model = val('spModel');
  p.apiKey = val('spApiKey');
  p.proxyUrl = val('spProxyUrl');
  p.name = val('spName') || p.model || 'Unnamed';
  const cw = num('spContextWindow'); if (cw && cw > 0) p.contextWindow = cw; else if (p.type === 'wllama' || p.type === 'transformersjs') p.contextWindow = 8192; else delete p.contextWindow;
  const mt = num('spMaxTokens');     if (mt && mt > 0) p.maxTokens = mt;     else delete p.maxTokens;
  const tp = num('spTemperature');   if (tp != null && tp >= 0) p.temperature = tp; else delete p.temperature;
  const re = val('spReasoningEffort').toLowerCase(); if (re) p.reasoningEffort = re; else delete p.reasoningEffort;
  // wllama-only sampling / reasoning params
  const tpp = num('spTopP');              if (tpp != null) p.topP = tpp; else delete p.topP;
  const tpk = num('spTopK');              if (tpk != null) p.topK = tpk; else delete p.topK;
  const mnp = num('spMinP');              if (mnp != null) p.minP = mnp; else delete p.minP;
  const fpen = num('spFreqPenalty');      if (fpen != null) p.frequencyPenalty = fpen; else delete p.frequencyPenalty;
  const ppen = num('spPresencePenalty');  if (ppen != null) p.presencePenalty = ppen; else delete p.presencePenalty;
  const sd = num('spSeed');               if (sd != null) p.seed = sd; else delete p.seed;
  const rsn = (document.getElementById('spReasoning')?.value) || 'auto'; if (rsn !== 'auto') p.reasoning = rsn; else delete p.reasoning;
  const fa = (document.getElementById('spFlashAttn')?.value) || 'false'; p.flashAttn = fa === 'true';
  const gl = num('spGpuLayers');          if (gl != null && gl >= 0) p.nGpuLayers = Math.round(gl); else delete p.nGpuLayers;
  saveProviders();
  applyActiveProvider();
  renderChips();   // reflect a renamed chip / active highlight
}

function addProvider() {
  const np = { id: 'provider_' + Date.now(), name: '', endpoint: '', model: '', apiKey: '', proxyUrl: '', type: 'openai' };
  _providers.push(np);
  selectProvider(np.id);   // activate + show an empty form to fill in
}

function duplicateSelected() {
  const p = getActiveProvider();
  if (!p || p.managed) return;
  const copy = { ...p, id: 'provider_' + Date.now(), name: (p.name || p.model || 'Provider') + ' (copy)' };
  _providers.push(copy);
  selectProvider(copy.id);
}

function deleteSelected() {
  const p = getActiveProvider();
  if (!p || p.managed) return;
  if (!confirm('Delete "' + (p.name || p.model || 'this provider') + '"?')) return;
  _providers = _providers.filter(x => x.id !== p.id);
  _activeProviderId = _providers.length ? _providers[0].id : null;
  saveProviders();
  applyActiveProvider();
  if (_activeProviderId) loadFormFor(_activeProviderId);
  else { const f = document.getElementById('providerForm'); if (f) f.style.display = 'none'; }
  renderChips();
}

// ============================================================
// MANAGED PROVIDER  (injected by account.js on company sign-in; in-memory only)
// ============================================================

// Resolve the catalog's default model to a managed provider. Match by model id
// (the canonical case), else by model/name trimmed + case-insensitively; if
// nothing matches (usually a defaultModel typo in models.json) warn and fall back
// to the first chip.
function managedDefault(defaultModel) {
  if (defaultModel != null && String(defaultModel).trim() !== '') {
    const want = String(defaultModel).trim();
    const byId = getProviderById(MANAGED_ID + ':' + want);
    if (byId) return byId;
    const lc = want.toLowerCase();
    const byField = _managed.find(p => String(p.model).toLowerCase() === lc || String(p.name).toLowerCase() === lc);
    if (byField) return byField;
    console.warn('[SandpieProviders] managed defaultModel ' + JSON.stringify(defaultModel) + ' matched no model — using the first. Available models:', _managed.map(p => p.model));
  }
  return _managed[0];
}

// Surface read-only company providers as chips (one per managed model). NOT
// persisted. On sign-in (the first time managed providers are injected) the
// company *default* model is selected — even over a leftover personal/stale pick,
// since a signed-in user should land on the company default. On later calls (e.g.
// the 30-min token refresh) the active provider is left as-is so the user isn't
// yanked mid-chat. Accepts a single def or a list; `defaultModel` = catalog id.
function setManaged(defs, defaultModel) {
  const firstInjection = _managed.length === 0;
  const list = Array.isArray(defs) ? defs : (defs ? [defs] : []);
  _managed = list.map(d => Object.assign({}, d, { id: MANAGED_ID + ':' + (d.model || d.name), managed: true }));
  if (_managed.length) {
    if (firstInjection || !getProviderById(_activeProviderId)) _activeProviderId = managedDefault(defaultModel).id;
  } else if (!getProviderById(_activeProviderId)) {
    _activeProviderId = _providers[0] ? _providers[0].id : null;
  }
  applyActiveProvider();
  renderChips();
  if (isManagedId(_activeProviderId)) loadFormFor(_activeProviderId);
}

// Remove the managed provider (on sign-out); fall back to a real provider/none.
function clearManaged() {
  const wasActive = isManagedId(_activeProviderId);
  _managed = [];
  if (wasActive) {
    _activeProviderId = _providers.length ? _providers[0].id : null;
    saveProviders();
    applyActiveProvider();
  }
  renderChips();
  if (_activeProviderId) loadFormFor(_activeProviderId);
  else { const f = document.getElementById('providerForm'); if (f) f.style.display = 'none'; }
}

// ============================================================
// HINT / STATUS
// ============================================================

function updateRoutingHint() {
  const active = getActiveProvider();
  const remote = (document.getElementById('proxyUrl')?.value || '').trim();
  const hint = document.getElementById('routingHint');
  if (!hint) return;
  if (active?.type === 'wllama') {
    hint.textContent = 'In-browser wllama · ' + (active.model || 'local model');
  } else if (active?.type === 'transformersjs') {
    hint.textContent = 'In-browser Transformers.js · ' + (active.model || 'local model');
  } else if (remote) {
    hint.textContent = 'Routing via ' + remote.replace(/^https?:\/\//, '');
  } else if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    hint.textContent = 'Routing via local /proxy/';
  } else {
    hint.textContent = 'Direct calls (CORS required, e.g. OpenRouter)';
  }
}

function refreshAiDot() {
  const ep = document.getElementById('endpoint')?.value.trim();
  const active = getActiveProvider();
  const local = (active?.type === 'wllama' || active?.type === 'transformersjs');
  const ok = ep && (local || document.getElementById('apiKey')?.value.trim());
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
  ensureUsable,
  list: () => _providers.slice(),
  get activeId() { return _activeProviderId; },
  updateHint: updateRoutingHint,
  refreshDot: refreshAiDot,
  setManaged,
  clearManaged,
};

function bootProviders() {
  init();
  // Load personal providers + render the composer model-picker at app start, so it
  // shows the user's models without first opening the gear panel (the panel's lazy
  // render re-loads later — idempotent). loadProviders → applyActiveProvider →
  // renderModelPicker does the initial paint.
  try { loadProviders(); } catch (_) {}
  // If the user signed in before this module evaluated, the company catalog may
  // have been fetched before the picker existed — inject it now (no-op otherwise).
  try { if (window.SandpieAccount && SandpieAccount.ensureManaged) SandpieAccount.ensureManaged(); } catch (_) {}
  // Close the dropup on any click outside it.
  document.addEventListener('click', (e) => {
    const h = document.getElementById('modelPicker');
    if (h && h.classList.contains('open') && !h.contains(e.target)) h.classList.remove('open');
  });
  // Re-anchor the fixed-positioned dropup to its trigger when the viewport changes.
  window.addEventListener('resize', () => {
    const h = document.getElementById('modelPicker');
    if (h && h.classList.contains('open')) positionModelPickerPanel(h);
  });
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootProviders);
} else {
  bootProviders();
}
