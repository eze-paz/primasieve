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
          <option value="hermes">API (Hermes local llama.cpp)</option>
        </select>

        <input id="spName" autocomplete="off" placeholder="Name (e.g. Main, Backup)">
        <input id="spEndpoint" autocomplete="off" placeholder="Base URL (e.g. https://api.openai.com/v1)">
        <input id="spModel" autocomplete="off" placeholder="Model (e.g. gpt-4o)">
        <input id="spApiKey" type="text" autocomplete="off" style="-webkit-text-security:disc; text-security:disc;" placeholder="API key">
        <input id="spProxyUrl" autocomplete="off" placeholder="Proxy URL (optional)">
        <input id="spContextWindow" type="number" min="1" autocomplete="off" placeholder="Context window (e.g. 128000)">
        <input id="spMaxTokens" type="number" min="1" autocomplete="off" placeholder="Max output tokens (optional)">
        <input id="spTemperature" type="number" min="0" max="2" step="0.1" autocomplete="off" placeholder="Temperature (optional, 0–2)">
        <input id="spTopP" type="number" min="0" max="1" step="0.05" autocomplete="off" placeholder="top_p (optional, 0–1)">
        <input id="spReasoningEffort" list="spReasoningEffortList" autocomplete="off" placeholder="Reasoning effort (reasoning models only: minimal/low/medium/high)">
        <datalist id="spReasoningEffortList"><option value="minimal"></option><option value="low"></option><option value="medium"></option><option value="high"></option><option value="none"></option></datalist>
        <input id="spProviderOrder" autocomplete="off" placeholder="Upstream routing (OpenRouter provider.order: e.g. deepseek — comma-separated, tried in order)">
        <select id="spAllowFallbacks" style="display:none;">
          <option value="yes">If preferred upstreams fail: fall back to others</option>
          <option value="no">If preferred upstreams fail: error (no fallback)</option>
        </select>
        <select id="spVision">
          <option value="yes">Vision: yes (this model accepts images)</option>
          <option value="no">Vision: no (text only)</option>
        </select>
        <select id="spVisionFallback" style="display:none;">
          <option value="">— no vision fallback —</option>
        </select>
        <div style="display:flex; gap:0.35rem;">
          <button class="ghost" type="button" id="spDuplicate" style="flex:1;">Duplicate</button>
          <button class="ghost" type="button" id="spDelete" style="flex:1;">Delete</button>
        </div>
      </div>
      <div id="routingHint" style="margin-top:0.5rem; font-size:0.7rem; color:var(--sp-text-dim);"></div>

    `;

// clearLocalModelCaches removed (local LLM engines removed)

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
  for (const id of ['spName','spEndpoint','spModel','spApiKey','spProxyUrl','spContextWindow','spMaxTokens','spTemperature','spTopP','spReasoningEffort','spProviderOrder','spAllowFallbacks','spVisionFallback']) {
    const el = document.getElementById(id);
    if (el && !el._spBound) { el.addEventListener('change', commitForm); el._spBound = true; }
  }
  const visionSel = document.getElementById('spVision');
  if (visionSel && !visionSel._spBound) { visionSel.addEventListener('change', () => { commitForm(); applyTypeUI(); }); visionSel._spBound = true; }
  const typeSel = document.getElementById('spType');
  if (typeSel && !typeSel._spBound) { typeSel.addEventListener('change', () => { commitForm(); applyTypeUI(); }); typeSel._spBound = true; }
  // spLiteRTLMModel wiring removed (local LLM engines removed)
  // spWebGPUModel wiring removed (local LLM engines removed)
  document.getElementById('spDuplicate')?.addEventListener('click', duplicateSelected);
  document.getElementById('spDelete')?.addEventListener('click', deleteSelected);
  // spClearModelCache wiring removed (local LLM engines removed)
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

// One-shot, NON-streaming completion — the shared utility path for background
// summarization (native compactor + memory/note agents). Never touches the
// conversation stream, so it emits no generation:complete. Routes to whatever
// provider is active. Returns the assistant text (may be ''). Returns the assistant text (may be '').
// maxTokens: null (default) sends NO max_tokens on the wire for cloud providers
// (OpenAI-spec default — the model's own cap). In-browser engines still need a
// concrete generation budget, so the local paths below fall back to 1024.
async function completeOnce({ system = '', user = '', model = '', maxTokens = null, signal, noReasoning = false, sessionId = null } = {}) {
  const active = getActiveProvider();
  const localMax = maxTokens != null ? maxTokens : 1024;
  // local-LM inference paths removed
  const endpoint = (document.getElementById('endpoint')?.value || '').replace(/\/$/, '');
  const apiKey = document.getElementById('apiKey')?.value || '';
  const mdl = model || document.getElementById('model')?.value || '';
  if (!endpoint || !mdl) throw new Error('no provider configured');
  const route = (typeof Sandpie !== 'undefined' && Sandpie.api) ? Sandpie.api(endpoint + '/chat/completions') : (endpoint + '/chat/completions');
  const url = new URL(route, location.href).href;
  // STREAM the response: with stream:false the socket sits idle for the whole (often
  // multi-minute) generation and an intermediary proxy/CDN kills it with a 504 — the
  // exact failure that blocked memory consolidation. SSE keeps tokens flowing so the
  // idle-timeout never fires; we just assemble the text and return it.
  const body = { model: mdl, messages: [{ role: 'system', content: system }, { role: 'user', content: user }], stream: true, stream_options: { include_usage: true } };
  if (sessionId) body.session_id = sessionId;   // parent-session marker e.g. "Retitle:<sid>"
  if (maxTokens != null) body.max_tokens = maxTokens;
  if (active && active.temperature != null) body.temperature = active.temperature;
  // noReasoning: for a short utility call (a conversation title), thinking is pure
  // cost — and on a hybrid model it's fatal, because reasoning tokens are billed
  // against max_tokens, so a small budget is spent thinking and the response
  // carries no content at all. There is no standard switch, so send the two that
  // cover the field and let _REASONING_KEYS below undo them if the server is
  // strict about unknown parameters:
  //   reasoning.enabled          — OpenRouter (any hybrid model behind it)
  //   chat_template_kwargs       — the DeepSeek/Qwen chat-template flag, as used
  //                                by vLLM / SGLang / DeepSeek's own API
  if (noReasoning) {
    body.reasoning = { enabled: false };
    body.chat_template_kwargs = { thinking: false, enable_thinking: false };
  }
  // A reasoning model streams its chain-of-thought in delta.reasoning (OpenRouter)
  // or delta.reasoning_content (DeepSeek) and leaves delta.content EMPTY until it
  // has finished thinking — and reasoning tokens are billed against max_tokens. So
  // a budget too small for the thinking yields a stream where every content delta
  // is '' and finish_reason is 'length': the call "succeeds" with an empty string,
  // which every caller then has to guess about. Count the reasoning and turn that
  // case into a diagnosis instead of silence. Reasoning text is never RETURNED —
  // it isn't an answer, and passing it off as one produces convincing garbage.
  const _emptyErr = (think, finish) => new Error(
    'model produced only reasoning tokens (' + think.length + ' chars' +
    (finish ? ', finish_reason=' + finish : '') + ') and no content — max_tokens was spent thinking, raise it');

  async function readStreamText(res) {
    if (!res.body || !res.body.getReader) {   // buffering proxy: whole JSON despite stream:true
      const data = await res.json();
      if (data.error) throw new Error(String(data.error.message || JSON.stringify(data.error)));
      const m = data?.choices?.[0]?.message || {};
      const think = String(m.reasoning || m.reasoning_content || '');
      if (!m.content && think) throw _emptyErr(think, data?.choices?.[0]?.finish_reason);
      return m.content || '';
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '', out = '', think = '', finish = '';
    for (;;) {
      if (signal && signal.aborted) { try { reader.cancel(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (payload === '[DONE]') continue;
        let j; try { j = JSON.parse(payload); } catch (_) { continue; }
        if (j.error) throw new Error(String(j.error.message || JSON.stringify(j.error)));
        const ch = j.choices?.[0] || {};
        const d = ch.delta || {};
        if (d.content) out += d.content;
        if (typeof d.reasoning === 'string') think += d.reasoning;
        else if (typeof d.reasoning_content === 'string') think += d.reasoning_content;
        if (ch.finish_reason) finish = ch.finish_reason;
      }
    }
    if (!out && think) throw _emptyErr(think, finish);
    return out;
  }
  // Retry transient/5xx/network failures with backoff, like a standard completion,
  // so a 504 doesn't fail a background summarization (compaction / memory distiller)
  // outright. Bounded (unlike the foreground turn) since these are best-effort and
  // fire again on their next trigger; a non-retryable error (4xx) surfaces at once.
  const RETRYABLE = new Set([408, 425, 429, 500, 502, 503, 504, 520, 522, 524]);
  const BACKOFF_MS = [1000, 2000, 5000, 10000];
  // The reasoning switches above are non-standard: OpenAI-spec servers reject an
  // unrecognized body parameter with a 400 rather than ignoring it. Rather than
  // maintain a per-provider allowlist, drop them and retry ONCE on the first 4xx —
  // worst case the model thinks and the (generous) budget absorbs it.
  const _REASONING_KEYS = ['reasoning', 'chat_template_kwargs'];
  let strippedReasoning = false;
  let lastErr = null;
  for (let attempt = 0; attempt <= BACKOFF_MS.length; attempt++) {
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey },
        body: JSON.stringify(body), signal,
      });
      if (!res.ok) { const t = await res.text().catch(() => ''); const e = new Error('HTTP ' + res.status + (t ? ': ' + t.slice(0, 200) : '')); e.status = res.status; throw e; }
      return await readStreamText(res);
    } catch (e) {
      if (signal && signal.aborted) throw e;
      lastErr = e;
      if (noReasoning && !strippedReasoning && e && e.status >= 400 && e.status < 500) {
        strippedReasoning = true;
        for (const k of _REASONING_KEYS) delete body[k];
        console.warn('[sandpie] provider rejected the disable-reasoning parameters — retrying without them:', e.message);
        attempt--;                               // this retry is the fallback, not one of the backoff attempts
        continue;
      }
      const retryable = (e && RETRYABLE.has(e.status)) || (e instanceof TypeError);   // TypeError = network failure
      if (!retryable || attempt === BACKOFF_MS.length) throw e;
      await new Promise(r => setTimeout(r, BACKOFF_MS[attempt]));
    }
  }
  throw lastErr || new Error('completion failed');
}

// Push the active provider's connection details into the hidden inputs that
// conversations.js reads (endpoint/model/apiKey/proxyUrl).
function applyActiveProvider() {
  const p = getActiveProvider();
  // local-LLM engine unload removed
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
  // Clean up any panel previously moved to <body>.
  const oldPanel = document.querySelector('.mp-panel');
  if (oldPanel) oldPanel.remove();
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
  trigger.addEventListener('click', (e) => { e.stopPropagation(); host.classList.toggle('open'); if (host.classList.contains('open')) positionModelPickerPanel(host); else { const p = document.querySelector('.mp-panel'); if (p) p.classList.remove('visible'); } });

  const panel = document.createElement('div');
  panel.className = 'mp-panel';
  const item = (p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'mp-item' + (p.id === _activeProviderId ? ' active' : '');
    b.textContent = p.name || p.model || 'Unnamed';
    if (p.model) b.title = p.model;
    b.addEventListener('click', () => { host.classList.remove('open'); const mp = document.querySelector('.mp-panel'); if (mp) mp.classList.remove('visible'); selectProvider(p.id); });
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

// The dropup panel is appended to <body> and position:fixed so it escapes both
// .input-wrap's overflow:hidden AND any backdrop-filter containing block on the
// form (aurora theme). Anchor it just above the trigger, in viewport coordinates,
// clamped so a wide panel never spills off the screen edge.
function positionModelPickerPanel(host) {
  const trig = host.querySelector('.mp-trigger');
  let panel = host.querySelector('.mp-panel') || document.querySelector('.mp-panel');
  if (!trig || !panel) return;
  // Move panel to <body> so it's not trapped in a backdrop-filter containing block.
  if (panel.parentNode !== document.body) document.body.appendChild(panel);
  const r = trig.getBoundingClientRect();
  panel.style.bottom = (window.innerHeight - r.top + 6) + 'px';
  const pw = panel.offsetWidth || 220;
  panel.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pw - 8)) + 'px';
  panel.classList.add('visible');
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
  set('spTopP', p.topP);
  set('spReasoningEffort', p.reasoningEffort);
  set('spProviderOrder', Array.isArray(p.providerOrder) ? p.providerOrder.join(', ') : '');
  set('spAllowFallbacks', p.allowFallbacks === false ? 'no' : 'yes');
  set('spVision', p.vision === 'no' ? 'no' : 'yes');
  renderVisionFallbackOptions(p.id);
  set('spVisionFallback', p.visionFallbackId || '');
  set('spType', p.type || 'openai');
  // spLiteRTLMModel/spWebGPUModel value setting removed (local LLM engines removed)
  applyTypeUI();
}

// Show/hide provider fields based on the selected backend type.
function applyTypeUI() {
  const type = (document.getElementById('spType')?.value) || 'openai';
  const hermes = type === 'hermes';
  const show = (id, on) => { const el = document.getElementById(id); if (el) el.style.display = on ? '' : 'none'; };
  show('spApiKey', !hermes);
  show('spProxyUrl', !hermes);
  show('spReasoningEffort', !hermes);
  show('spProviderOrder', !hermes);
  // Fallback choice only matters once a preferred-provider order is set.
  const hasOrder = !!(document.getElementById('spProviderOrder')?.value || '').trim();
  show('spAllowFallbacks', !hermes && hasOrder);
  // Vision capability (yes/no) + vision-fallback picker.
  show('spVision', true);
  const vision = (document.getElementById('spVision')?.value) || 'yes';
  show('spVisionFallback', vision === 'no');
  show('spContextWindow', true);
  show('spTemperature', !hermes);
  show('spTopP', !hermes);
  const ep = document.getElementById('spEndpoint');
  if (ep) ep.placeholder = 'Base URL (e.g. https://api.openai.com/v1)';
  const cw = document.getElementById('spContextWindow');
  if (cw) cw.placeholder = 'Context window (e.g. 128000)';
}

// Populate the vision-fallback dropdown with every vision-CAPABLE provider except
// the one being edited (a model can't fall back to itself). Includes company-managed
// providers — a company MiMo model is a valid vision fallback for a personal
// text-only model. Rebuilt on every loadFormFor, so add/delete/duplicate stays in sync.
function renderVisionFallbackOptions(activeId) {
  const sel = document.getElementById('spVisionFallback');
  if (!sel) return;
  const prev = sel.value;
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  // Only vision-capable providers make sense as a fallback (a text-only model
  // can't see the rerouted images either).
  const opts = [..._managed, ..._providers].filter(p => p.id !== activeId && providerCanSee(p));
  sel.innerHTML = '<option value="">— no vision fallback —</option>'
    + opts.map(p => {
      const name = (p.name && p.name !== p.model) ? p.name + ' (' + p.model + ')' : (p.name || p.model || 'Unnamed');
      return '<option value="' + esc(p.id) + '">' + esc(name) + '</option>';
    }).join('');
  sel.value = prev;
}

// Cloud providers can see images unless explicitly marked vision:no.
function providerCanSee(p) {
  if (!p) return false;
  return p.vision !== 'no';
}

// Resolve a provider's configured vision fallback — the model that receives image
// turns when THIS model can't see. Returns null when unset or when the target
// can't see either.
function resolveVisionFallback(p) {
  if (!p || !p.visionFallbackId) return null;
  const fb = getProviderById(p.visionFallbackId);
  return (fb && providerCanSee(fb)) ? fb : null;
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
  const cw = num('spContextWindow'); if (cw && cw > 0) p.contextWindow = cw; else delete p.contextWindow;
  const mt = num('spMaxTokens');     if (mt && mt > 0) p.maxTokens = mt;     else delete p.maxTokens;
  const tp = num('spTemperature');   if (tp != null && tp >= 0) p.temperature = tp; else delete p.temperature;
  const pp = num('spTopP');          if (pp != null && pp >= 0) p.topP = pp;        else delete p.topP;
  const re = val('spReasoningEffort').toLowerCase(); if (re) p.reasoningEffort = re; else delete p.reasoningEffort;
  // OpenRouter upstream routing: providerOrder is stored as an ARRAY (maps to the
  // request's provider.order), allowFallbacks as a bool (provider.allow_fallbacks).
  const po = val('spProviderOrder').split(',').map(s => s.trim()).filter(Boolean);
  if (po.length) p.providerOrder = po; else delete p.providerOrder;
  const af = (document.getElementById('spAllowFallbacks')?.value) || 'yes';
  if (po.length && af === 'no') p.allowFallbacks = false; else delete p.allowFallbacks;
  p.vision = (val('spVision') === 'no') ? 'no' : 'yes';
  const vf = val('spVisionFallback');
  if (vf && vf !== p.id) p.visionFallbackId = vf; else delete p.visionFallbackId;
  applyTypeUI();   // reflect fallback-select visibility as the order field changes
  const rsn = (document.getElementById('spReasoning')?.value) || 'auto'; if (rsn !== 'auto') p.reasoning = rsn; else delete p.reasoning;
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
  if (active?.type === 'hermes') {
    hint.textContent = 'Hermes local llama.cpp via ' + (active.endpoint || '(no endpoint set)');
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
  const local = (active?.type === 'hermes');
  const ok = ep && (local || document.getElementById('apiKey')?.value.trim());
  const dot = document.getElementById('aiDot');
  if (dot) { dot.classList.remove('ok', 'warn', 'err'); if (ok) dot.classList.add('ok'); }
}

// ============================================================
// GLOBAL API
// ============================================================

window.SandpieProviders = {
  getActive: getActiveProvider,
  complete: completeOnce,
  load: loadProviders,
  apply: applyActiveProvider,
  ensureUsable,
  list: () => _providers.slice(),
  get activeId() { return _activeProviderId; },
  updateHint: updateRoutingHint,
  refreshDot: refreshAiDot,
  setManaged,
  clearManaged,
  providerCanSee,
  resolveVisionFallback,
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
    if (h && h.classList.contains('open') && !h.contains(e.target)) {
      const p = document.querySelector('.mp-panel');
      if (p && p.contains(e.target)) return;
      h.classList.remove('open');
      if (p) p.classList.remove('visible');
    }
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
