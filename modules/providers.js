/**
 * Providers Module for Sandpie
 *
 * Model catalog + per-conversation provider selection. There is NO global
 * "active" provider: every conversation carries its own providerId (persisted
 * in the conversation's .meta.json by conversations.js), and the composer's
 * model picker (mp-trigger) sets it for THAT pane's conversation. The settings
 * modal lists the available models (plain, non-selectable) and offers + Add.
 *
 * Storage stays in localStorage: a provider definition includes its API key (a
 * secret), so providers are NOT synced to the SandpieConfig blob.
 *
 * account.js may inject "managed" providers at runtime (on company sign-in) via
 * setManaged(): they show as read-only entries, are never persisted, and are
 * removed on sign-out.
 */

const PROVIDERS_KEY = 'sandpie-providers';

let _providers = [];
let _managed = [];              // company providers injected by account.js (one read-only chip per managed model); in-memory only, never persisted
const MANAGED_ID = '__managed'; // id prefix — each managed provider's id is `__managed:<model>`
function isManagedId(id) { return typeof id === 'string' && id.indexOf(MANAGED_ID + ':') === 0; }
// Managed models the user can actively pick. INTERNAL models (models.json
// internal:true) stay in _managed so a visible model's visionFallback can resolve
// to them (getProviderById searches _managed), but they never show in the picker
// or get auto-selected — e.g. an image-only model used solely as a fallback.
function selectableManaged() { return _managed.filter(p => !p.internal); }

const AI_HTML = `
      <div id="providerChips"></div>
      <div id="providerManagedNote" style="display:none; margin-top:1rem; padding-top:0.85rem; border-top:1px solid var(--sp-border); font-size:0.78rem; color:var(--sp-text-dim);">Company models are provided by your sign-in and are managed for you.</div>
      <div id="routingHint" style="margin-top:0.5rem; font-size:0.7rem; color:var(--sp-text-dim);"></div>

    `;

// clearLocalModelCaches removed (local LLM engines removed)

// AI provider lives in the gear modal (SandpieSettings).
function init() {
  if (window.SandpieSettings) {
    SandpieSettings.register({
      id: 'aiProvider', title: 'AI provider', order: 10,
      render(panel) { panel.innerHTML = AI_HTML; _wireProviderPanel(); },
    });
    return;
  }
  setTimeout(init, 500);   // neither host ready yet — retry
}

function _wireProviderPanel() {
  loadProviders();
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
      saveProviders();
    }
  }

  refreshProvidersUI();
}

function saveProviders() {
  localStorage.setItem(PROVIDERS_KEY, JSON.stringify(_providers));
}

// Resolve any id, including the in-memory managed provider.
function getProviderById(id) {
  return _managed.find(p => p.id === id) || _providers.find(p => p.id === id) || null;
}

// DEFAULT provider: what background utility calls (auto-title, compaction
// summaries, memory agents) use when the caller doesn't pass a model. This is
// NOT a chat default — conversations always use their own provider.
function defaultProvider() {
  return selectableManaged()[0] || _providers[0] || null;
}
// Legacy alias — external modules (auto-title, context, images, compactor log)
// still call SandpieProviders.getActive(); it now means the default provider.
const getActiveProvider = defaultProvider;

// One-shot, NON-streaming completion — the shared utility path for background
// summarization (native compactor + memory/note agents). Never touches the
// conversation stream, so it emits no generation:complete. Routes to whatever
// provider is active. Returns the assistant text (may be ''). Returns the assistant text (may be '').
// maxTokens: null (default) sends NO max_tokens on the wire for cloud providers
// (OpenAI-spec default — the model's own cap). In-browser engines still need a
// concrete generation budget, so the local paths below fall back to 1024.
async function completeOnce({ system = '', user = '', model = '', maxTokens = null, signal, noReasoning = false, sessionId = null } = {}) {
  const active = defaultProvider();
  const localMax = maxTokens != null ? maxTokens : 1024;
  // local-LM inference paths removed
  const endpoint = ((active && active.endpoint) || '').replace(/\/$/, '');
  const apiKey = (active && active.apiKey) || '';
  const mdl = model || (active && active.model) || '';
  if (!endpoint || !mdl) throw new Error('no provider configured');
  const route = (typeof Sandpie !== 'undefined' && Sandpie.api) ? Sandpie.api(endpoint + '/chat/completions', active && active.proxyUrl) : (endpoint + '/chat/completions');
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

// Refresh every UI surface that mirrors the provider catalog (settings list,
// composer pickers, status dot). Called after any catalog change.
function refreshProvidersUI() {
  renderChips();
  renderModelPicker();
  refreshAiDot();
}

// Ensure the conversation being sent into has a usable provider. With no global
// active provider, this only VALIDATES: it resolves the conversation's provider
// (via conversations.js) and reports whether it can actually serve a request.
// Returns true when a turn can go out.
function ensureUsable(convId) {
  const p = resolveProvider(convId);
  return !!(p && (p.model || '').trim() && (p.endpoint || '').trim());
}

// ============================================================
// CHIPS  (pick the active provider; "+ Add" creates a new one)
// ============================================================

function renderChips() {
  renderModelPicker();   // composer picker tracks list changes even when the gear modal is closed
  const row = document.getElementById('providerChips');
  if (!row) return;
  row.innerHTML = '';
  // Plain NON-SELECTABLE list of models: chips are informational only (no active
  // highlight, no click-to-activate). Which model a conversation uses is picked
  // in that pane's composer model picker; + Add below extends the catalog.
  const makeChip = (p) => {
    const chip = document.createElement('div');
    chip.className = 'chip plain' + (p.managed ? ' managed' : '');
    chip.textContent = p.name || p.model || 'Unnamed';
    chip.dataset.id = p.id;
    if (p.managed) chip.title = 'Provided by your company sign-in';
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
  const shownManaged = selectableManaged();   // hide internal (fallback-only) models
  if (shownManaged.length) {
    row.appendChild(label('Company', false));
    row.appendChild(groupOf(shownManaged.map(makeChip)));
    row.appendChild(label('Your providers', true));
    row.appendChild(groupOf(_providers.map(makeChip).concat(addChip)));
  } else {
    row.appendChild(groupOf(_providers.map(makeChip).concat(addChip)));
  }
}

// Compact model selector for the composer — a "dropup" chip. Mirrors renderChips'
// Company / Your-models split (a clean separator line between them, only when there
// ARE company models, i.e. not anonymous). Lives in the input bar so the model is
// switchable without opening Settings. Painted into EVERY .model-picker host
// (main pane + side pane); no-op when none exist on the page.
//
// PER-CONVERSATION: each host carries data-conv-id (set by conversations.js when
// the pane mounts a conversation). The chip shows THAT conversation's provider and
// selecting an item sets it for that conversation only — there is no global model.
function renderModelPicker() {
  // Paint the picker into EVERY composer host (main pane + side pane). Each host
  // gets its own trigger; the dropup panel is per-host too (moved to <body> only
  // while open, so position:fixed can escape overflow/backdrop-filter clipping).
  const hosts = Array.from(document.querySelectorAll('.model-picker'));
  if (!hosts.length) return;
  // Clean up any panel previously moved to <body> (per-host panels are wiped by innerHTML below).
  document.querySelectorAll('body > .mp-panel').forEach(p => p.remove());
  for (const host of hosts) {
    const wasOpen = host.classList.contains('open');
    host.innerHTML = '';
    host.classList.toggle('open', wasOpen);   // preserve open state across a re-render
    buildModelPickerInto(host, resolveProvider(host.dataset.convId || null));
  }
}

// Build one picker (trigger + dropup panel) inside `host`.
function buildModelPickerInto(host, active) {

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
  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    if (host.classList.contains('open')) hideModelPickerPanel(host);
    else { host.classList.add('open'); positionModelPickerPanel(host); }
  });

  const panel = document.createElement('div');
  panel.className = 'mp-panel';
  const item = (p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'mp-item' + (active && p.id === active.id ? ' active' : '');
    b.textContent = p.name || p.model || 'Unnamed';
    if (p.model) b.title = p.model;
    b.addEventListener('click', () => { hideModelPickerPanel(host); setConvProvider(host.dataset.convId || null, p.id); });
    return b;
  };
  const hdr = (t) => { const d = document.createElement('div'); d.className = 'mp-hdr'; d.textContent = t; return d; };
  const empty = (t) => { const d = document.createElement('div'); d.className = 'mp-empty'; d.textContent = t; return d; };

  const shownManaged = selectableManaged();   // hide internal (fallback-only) models
  if (shownManaged.length) {
    panel.appendChild(hdr('Company'));
    shownManaged.forEach(p => panel.appendChild(item(p)));
    // 'Your models' section only exists when the user actually HAS models —
    // with none, no header, no separator, no empty note (nothing to show).
    if (_providers.length) {
      panel.appendChild(Object.assign(document.createElement('div'), { className: 'mp-sep' }));
      panel.appendChild(hdr('Your models'));
      _providers.forEach(p => panel.appendChild(item(p)));
    }
  } else if (_providers.length) {
    _providers.forEach(p => panel.appendChild(item(p)));
  } else {
    panel.appendChild(empty('No models — add one in Settings → AI provider'));
  }

  // ---- Reasoning effort slider (mockup D) --------------------------------
  // One shared setting per conversation: 'off'|'low'|'medium'|'high' (null =
  // app default). Persisted via the SandpieConv bridge (stream + meta, same
  // contract as the provider id). The slider is a real <input type=range>
  // (0..3) styled by sandpie.css (.rs-*), so keyboard/touch work for free.
  const RSN_LV = ['off', 'low', 'medium', 'high'];
  const RSN_SHORT = { off: 'Off', low: 'Low', medium: 'Med', high: 'High' };
  const curLevel = (() => {
    try {
      const lv = (window.SandpieConv && SandpieConv.getReasoningLevel)
        ? SandpieConv.getReasoningLevel(host.dataset.convId || null) : null;
      if (lv && RSN_LV.includes(lv)) return lv;
      try { return (localStorage.getItem('sandpie-default-reasoning') || '').trim() || 'medium'; }
      catch (_) { return 'medium'; }
    } catch (_) { return 'medium'; }
  })();

  panel.appendChild(Object.assign(document.createElement('div'), { className: 'mp-sep' }));
  panel.appendChild(hdr('Reasoning'));
  const rsBlock = document.createElement('div');
  rsBlock.className = 'rs-block';
  const rsHead = document.createElement('div');
  rsHead.className = 'rs-head';
  const rsName = document.createElement('span');
  rsName.className = 'rs-name';
  rsName.textContent = 'Effort';
  const rsVal = document.createElement('span');
  rsVal.className = 'rs-val';
  rsVal.textContent = RSN_SHORT[curLevel];
  rsHead.append(rsName, rsVal);
  const rsSlider = document.createElement('input');
  rsSlider.type = 'range';
  rsSlider.min = '0'; rsSlider.max = '3'; rsSlider.step = '1';
  rsSlider.value = String(RSN_LV.indexOf(curLevel));
  rsSlider.className = 'rs-slider';
  rsSlider.setAttribute('aria-label', 'Reasoning effort');
  const rsTicks = document.createElement('div');
  rsTicks.className = 'rs-ticks';
  RSN_LV.forEach(lv => {
    const t = document.createElement('span');
    t.textContent = RSN_SHORT[lv];
    if (lv === curLevel) t.classList.add('on');
    rsTicks.appendChild(t);
  });
  const paintLevel = (lv) => {
    rsVal.textContent = RSN_SHORT[lv];
    [...rsTicks.children].forEach((t, i) => t.classList.toggle('on', RSN_LV[i] === lv));
    // Mirror the level on the trigger pill: "Model · Med"
    const lblEl = trigger.querySelector('.mp-label');
    if (lblEl) {
      const base = active ? (active.name || active.model || 'Model') : 'Select model';
      lblEl.textContent = (lv === 'medium') ? base : (base + ' · ' + RSN_SHORT[lv]);
    }
  };
  rsSlider.addEventListener('input', () => paintLevel(RSN_LV[Number(rsSlider.value)]));   // live label while dragging
  rsSlider.addEventListener('change', () => {
    const lv = RSN_LV[Number(rsSlider.value)];
    try {
      if (window.SandpieConv && SandpieConv.setReasoningLevel) SandpieConv.setReasoningLevel(host.dataset.convId || null, lv);
    } catch (_) {}
  });
  rsBlock.append(rsHead, rsSlider, rsTicks);
  panel.appendChild(rsBlock);

  host.append(trigger, panel);
  paintLevel(curLevel);   // initial pill suffix
  if (host.classList.contains('open')) positionModelPickerPanel(host);
}

// The dropup panel is appended to <body> and position:fixed so it escapes both
// .input-wrap's overflow:hidden AND any backdrop-filter containing block on the
// form (aurora theme). Anchor it just above the trigger, in viewport coordinates,
// clamped so a wide panel never spills off the screen edge.
function positionModelPickerPanel(host) {
  const trig = host.querySelector('.mp-trigger');
  const panel = host.querySelector('.mp-panel');
  if (!trig || !panel) return;
  // Move panel to <body> so it's not trapped in a backdrop-filter containing block.
  // Tag it with its host id so hideModelPickerPanel can find the RIGHT panel even
  // when another host's idle panel also exists in the document.
  document.body.appendChild(panel);
  if (host.id) panel.dataset.mpHost = host.id;
  const r = trig.getBoundingClientRect();
  panel.style.bottom = (window.innerHeight - r.top + 6) + 'px';
  const pw = panel.offsetWidth || 220;
  panel.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pw - 8)) + 'px';
  panel.classList.add('visible');
}

// Close one host's picker: drop 'open' and hide/return THAT host's panel (which
// may currently live in <body> while shown). Never touches the other host's panel.
function hideModelPickerPanel(host) {
  host.classList.remove('open');
  let panel = host.querySelector('.mp-panel');
  if (!panel && host.id) panel = document.querySelector('.mp-panel[data-mp-host="' + host.id + '"]');
  if (!panel) panel = document.querySelector('body > .mp-panel');
  if (panel) {
    panel.classList.remove('visible');
    host.appendChild(panel);   // return it so host.querySelector('.mp-panel') works next time
  }
}

// ============================================================
// PER-CONVERSATION PROVIDER RESOLUTION
// ============================================================

// Resolve the provider a conversation will use. Reads the conversation's own
// providerId via conversations.js (window.SandpieConv.getProviderId); falls back
// to the default provider when the conv has none (or isn't known yet). Returns
// null only when the catalog itself is empty.
function resolveProvider(convId) {
  let pid = null;
  try { pid = (window.SandpieConv && SandpieConv.getProviderId) ? SandpieConv.getProviderId(convId) : null; } catch (_) {}
  if (!pid) {
    // No conversation-bound choice (home screen / brand-new chat, or a conv that
    // never picked): fall back to the LAST-USED provider (the picker writes it
    // here even before any conversation exists), then the catalog default.
    try { pid = localStorage.getItem('sandpie-default-provider') || null; } catch (_) {}
  }
  return getProviderById(pid) || defaultProvider();
}

// Set a conversation's provider (composer picker click). Delegates persistence to
// conversations.js (stream + .meta.json); then repaints the pickers.
function setConvProvider(convId, providerId) {
  try {
    if (window.SandpieConv && SandpieConv.setProviderId) SandpieConv.setProviderId(convId, providerId);
  } catch (_) {}
  renderModelPicker();
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

function addProvider() {
  const np = { id: 'provider_' + Date.now(), name: '', endpoint: '', model: '', apiKey: '', proxyUrl: '', type: 'openai' };
  _providers.push(np);
  saveProviders();
  refreshProvidersUI();   // the new (empty) model appears in the list + pickers
}

// ============================================================
// MANAGED PROVIDER  (injected by account.js on company sign-in; in-memory only)
// ============================================================

// Surface read-only company providers as chips (one per managed model). NOT
// persisted. With no global active provider, conversations that point at a
// managed id keep it while it exists; conversations.js falls back to the
// default provider for ids that no longer resolve. Accepts a single def or a
// list; `defaultModel` = catalog id (kept for API compat, unused here).
function setManaged(defs, defaultModel) {
  const list = Array.isArray(defs) ? defs : (defs ? [defs] : []);
  _managed = list.map(d => Object.assign({}, d, { id: MANAGED_ID + ':' + (d.model || d.name), managed: true }));
  refreshProvidersUI();
}

// Remove the managed providers (on sign-out). Conversations pointing at a
// managed id fall back to the default provider on their next send.
function clearManaged() {
  _managed = [];
  refreshProvidersUI();
}

// ============================================================
// HINT / STATUS
// ============================================================

function updateRoutingHint() {
  const hint = document.getElementById('routingHint');
  if (!hint) return;
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    hint.textContent = 'Routing via local /proxy/';
  } else {
    hint.textContent = 'Direct calls (CORS required, e.g. OpenRouter)';
  }
}

function refreshAiDot() {
  const ok = [...selectableManaged(), ..._providers].some(p => (p.model || '').trim() && (p.endpoint || '').trim());
  const dot = document.getElementById('aiDot');
  if (dot) { dot.classList.remove('ok', 'warn', 'err'); if (ok) dot.classList.add('ok'); }
}

// ============================================================
// GLOBAL API
// ============================================================

window.SandpieProviders = {
  getActive: defaultProvider,          // legacy alias = DEFAULT provider (utility calls)
  resolve: resolveProvider,            // per-conversation resolution
  setConvProvider,
  refreshPickers: renderModelPicker,   // repaint all composer pickers (conv switch)
  complete: completeOnce,
  load: loadProviders,
  ensureUsable,
  list: () => _providers.slice(),
  updateHint: updateRoutingHint,
  refreshDot: refreshAiDot,
  setManaged,
  clearManaged,
  providerCanSee,
  resolveVisionFallback,
};

function bootProviders() {
  init();
  // Load the provider catalog + render the composer model-pickers at app start
  // (the panel's lazy render re-loads later — idempotent).
  try { loadProviders(); } catch (_) {}
  // If the user signed in before this module evaluated, the company catalog may
  // have been fetched before the picker existed — inject it now (no-op otherwise).
  try { if (window.SandpieAccount && SandpieAccount.ensureManaged) SandpieAccount.ensureManaged(); } catch (_) {}
  // Close the dropup on any click outside it.
  document.addEventListener('click', (e) => {
    for (const h of document.querySelectorAll('.model-picker.open')) {
      if (h.contains(e.target)) continue;
      const p = h.querySelector('.mp-panel') || document.querySelector('body > .mp-panel[data-mp-host="' + (h.id || '') + '"]');
      if (p && p.contains(e.target)) continue;   // click on the open dropup itself
      hideModelPickerPanel(h);
    }
  });
  // Re-anchor the fixed-positioned dropup to its trigger when the viewport changes.
  window.addEventListener('resize', () => {
    for (const h of document.querySelectorAll('.model-picker')) {
      if (h.classList.contains('open')) positionModelPickerPanel(h);
    }
  });
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootProviders);
} else {
  bootProviders();
}
