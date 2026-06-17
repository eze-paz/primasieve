// sandpie/modules/speech-to-text.js — SandpieSpeech: on-device voice input.
//
// Adds a mic button to the composer. Click → record from the microphone; click
// again → stop, transcribe locally with Whisper, and INSERT the text into the
// chat input (never auto-sends — the user reviews then sends). The transcription
// runs in a dedicated Web Worker (modules/stt-worker.js) using Transformers.js,
// so the audio NEVER leaves the tab — true to sandpie's "nothing escapes the tab"
// promise. The only network traffic is the one-time model download (cached after).
//
// Optional + self-wiring, like every sandpie module: this script injects its own
// button and registers its own settings panel, so removing the <script> tag
// removes the feature cleanly with no orphaned markup. It needs only the static
// .input-bar (always present) and degrades to no-op on browsers without
// getUserMedia / AudioContext / Workers (the button simply isn't shown).
//
// Prefs (model + language) ride SandpieConfig under the 'speech' namespace
// (synced, no secrets); falls back to localStorage when config.js isn't loaded.
//
// CLASSIC script (global window.SandpieSpeech). Load after core.js / config.js /
// settings.js.

const SandpieSpeech = (function () {
  'use strict';

  // ── Curated Whisper catalog (all PUBLIC onnx-community repos, no HF token) ──
  // Multilingual checkpoints only, so the worker can pass a language / auto-detect.
  // Sizes are the rough on-disk download (fp32 encoder + q4 decoder on WebGPU).
  const MODELS = [
    { id: 'onnx-community/whisper-tiny',  label: 'Whisper Tiny — fastest (~80 MB)' },
    { id: 'onnx-community/whisper-base',  label: 'Whisper Base — balanced (~150 MB)' },
    { id: 'onnx-community/whisper-small', label: 'Whisper Small — most accurate (~480 MB)' },
  ];
  const LANGS = [
    ['auto', 'Auto-detect'], ['en', 'English'], ['es', 'Spanish'], ['fr', 'French'],
    ['de', 'German'], ['it', 'Italian'], ['pt', 'Portuguese'], ['nl', 'Dutch'],
    ['ru', 'Russian'], ['zh', 'Chinese'], ['ja', 'Japanese'], ['ko', 'Korean'],
    ['ar', 'Arabic'], ['hi', 'Hindi'],
  ];
  const NS = 'speech';
  const LS_KEY = 'sandpie-speech';
  const DEFAULTS = { model: 'onnx-community/whisper-base', lang: 'auto' };
  const TARGET_SR = 16000;   // Whisper expects 16 kHz mono

  // ── Prefs (SandpieConfig namespace, localStorage fallback — no secrets) ──
  function cfgAll() {
    const c = window.SandpieConfig;
    if (c) return Object.assign({}, DEFAULTS, c.get(NS, {}) || {});
    try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(LS_KEY) || '{}')); }
    catch (_) { return Object.assign({}, DEFAULTS); }
  }
  function setCfg(partial) {
    const c = window.SandpieConfig;
    if (c) { c.update(NS, partial); return; }
    const next = Object.assign(cfgAll(), partial);
    try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch (_) {}
  }
  const cfgModel = () => cfgAll().model;
  const cfgLang  = () => cfgAll().lang;

  // ── Capability gate — Whisper itself runs on WASM if there's no WebGPU, so the
  // only hard requirements are mic capture, audio decode, and Workers. ──
  function supported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)
      && !!(window.AudioContext || window.webkitAudioContext)
      && typeof Worker !== 'undefined';
  }

  // ============================================================
  // Worker — model load + transcription run OFF the main thread.
  // (Bump ?v when editing stt-worker.js: it isn't a <script> in the HTML, so the
  // page cache-buster doesn't cover it.)
  // ============================================================
  const WORKER_URL = 'modules/stt-worker.js?v=1';
  let _worker = null, _seq = 0;
  function getWorker() {
    if (!_worker) {
      _worker = new Worker(WORKER_URL, { type: 'module' });
      _worker.addEventListener('error', (ev) => console.warn('[stt] worker error:', (ev && ev.message) || ev));
    }
    return _worker;
  }

  // Resolve { onProgress, onReady } so callers (transcribe, panel preload) can
  // surface download progress without each re-attaching listeners.
  let _progressCb = null;
  function transcribeAudio(audio) {
    const worker = getWorker();
    const id = ++_seq;
    return new Promise((resolve, reject) => {
      function cleanup() { worker.removeEventListener('message', onMsg); }
      const onMsg = (e) => {
        const m = e.data || {};
        if (m.type === 'progress') { try { _progressCb && _progressCb(m.data); } catch (_) {} return; }
        if (m.type === 'ready')    { try { _progressCb && _progressCb({ progress: 1, ready: true }); } catch (_) {} return; }
        if (m.type === 'result' && m.id === id) { cleanup(); resolve(m.text || ''); return; }
        if (m.type === 'error') { cleanup(); reject(new Error(m.message || 'stt worker error')); return; }
      };
      worker.addEventListener('message', onMsg);
      // Transfer the audio buffer (no copy).
      try {
        worker.postMessage({ type: 'transcribe', id, modelId: cfgModel(), lang: cfgLang(), audio }, [audio.buffer]);
      } catch (e) { cleanup(); reject(e); }
    });
  }

  // ============================================================
  // Audio capture → 16 kHz mono Float32 (record, then transcribe).
  // ============================================================
  let _media = null, _rec = null, _chunks = [];

  async function decodeToMono16k(blob) {
    const buf = await blob.arrayBuffer();
    const AC = window.AudioContext || window.webkitAudioContext;
    const tmp = new AC();
    let decoded;
    try { decoded = await tmp.decodeAudioData(buf); }
    finally { try { tmp.close(); } catch (_) {} }
    const frames = Math.ceil(decoded.duration * TARGET_SR);
    if (!frames) return new Float32Array(0);
    const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    const off = new OAC(1, frames, TARGET_SR);   // 1 channel → mono downmix + resample
    const src = off.createBufferSource();
    src.buffer = decoded;
    src.connect(off.destination);
    src.start(0);
    const rendered = await off.startRendering();
    return rendered.getChannelData(0);
  }

  async function startRecording() {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) {
      flashError(e && e.name === 'NotAllowedError' ? 'Microphone permission denied' : 'No microphone available');
      return;
    }
    _media = stream;
    _chunks = [];
    try { _rec = new MediaRecorder(stream); }
    catch (_) { try { _rec = new MediaRecorder(stream, { mimeType: 'audio/webm' }); } catch (e2) { flashError('Recording not supported'); releaseMic(); return; } }
    _rec.ondataavailable = (ev) => { if (ev.data && ev.data.size) _chunks.push(ev.data); };
    _rec.onstop = onRecordingStop;
    _rec.start();
    setState('recording');
  }

  function stopRecording() {
    try { if (_rec && _rec.state !== 'inactive') _rec.stop(); } catch (_) {}
  }

  function releaseMic() {
    try { if (_media) _media.getTracks().forEach(t => t.stop()); } catch (_) {}   // clears the browser's recording indicator
    _media = null;
  }

  async function onRecordingStop() {
    releaseMic();
    const type = (_rec && _rec.mimeType) || 'audio/webm';
    const blob = new Blob(_chunks, { type });
    _chunks = []; _rec = null;
    if (!blob.size) { setState('idle'); return; }
    setState('transcribing');
    try {
      const audio = await decodeToMono16k(blob);
      if (!audio.length) { setState('idle'); return; }
      const text = await transcribeAudio(audio);
      if (text) insertText(text);
    } catch (e) {
      flashError('Transcription failed');
      console.warn('[stt] transcription failed:', (e && e.message) || e);
    } finally {
      setState('idle');
    }
  }

  // ============================================================
  // Insert transcript into the composer — at the caret if focused, else append.
  // Dispatches an 'input' event so conversations.js's autosize listener fires
  // (it does NOT observe the .value property, only the input event).
  // ============================================================
  function insertText(text) {
    const ta = document.getElementById('input');
    if (!ta) return;
    const t = String(text).trim();
    if (!t) return;
    const cur = ta.value;
    const focused = document.activeElement === ta && ta.selectionStart != null;
    if (focused) {
      const s = ta.selectionStart, e = ta.selectionEnd;
      const before = cur.slice(0, s), after = cur.slice(e);
      const lead  = before && !/\s$/.test(before) ? ' ' : '';
      const trail = after && !/^\s/.test(after) ? ' ' : '';
      ta.value = before + lead + t + trail + after;
      const pos = (before + lead + t).length;
      try { ta.setSelectionRange(pos, pos); } catch (_) {}
    } else {
      ta.value = cur + (cur && !/\s$/.test(cur) ? ' ' : '') + t;
    }
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    ta.focus();
  }

  // ============================================================
  // Composer mic button (self-injected, styled as an .attach-btn).
  // ============================================================
  let _btn = null, _state = 'idle', _flashTimer = null;

  function onMicClick() {
    if (_state === 'idle') startRecording();
    else if (_state === 'recording') stopRecording();
    // 'transcribing' → ignore (button is disabled anyway)
  }

  function setState(s) {
    _state = s;
    if (!_btn) return;
    clearTimeout(_flashTimer);
    _btn.classList.toggle('recording', s === 'recording');
    _btn.disabled = (s === 'transcribing');
    _btn.textContent = (s === 'recording') ? '⏹' : '🎤';
    _btn.title = s === 'recording' ? 'Stop & transcribe'
               : s === 'transcribing' ? 'Transcribing on-device…'
               : 'Speak (on-device)';
  }

  function flashError(msg) {
    if (!_btn) return;
    _btn.title = msg;
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(() => { if (_state === 'idle') _btn.title = 'Speak (on-device)'; }, 4000);
  }

  function injectButton() {
    if (document.getElementById('micBtn')) { _btn = document.getElementById('micBtn'); return true; }
    const bar = document.querySelector('.input-bar');
    if (!bar) return false;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'micBtn';
    btn.className = 'attach-btn mic-btn';
    btn.title = 'Speak (on-device)';
    btn.setAttribute('aria-label', 'Record speech');
    btn.textContent = '🎤';
    btn.addEventListener('click', onMicClick);
    const attach = document.getElementById('attachBtn');
    if (attach && attach.parentNode === bar) attach.insertAdjacentElement('afterend', btn);
    else bar.insertBefore(btn, bar.firstChild);
    _btn = btn;
    return true;
  }

  // ============================================================
  // Settings panel (gear modal via SandpieSettings; sidebar fallback).
  // ============================================================
  const PANEL_HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">
      Speak instead of typing. Transcription runs <strong>fully on-device</strong> with Whisper —
      your microphone audio never leaves this tab. The first use downloads the model (cached after).
    </p>
    <label style="display:block; font-size:0.72rem; color:var(--sp-text-dim); margin:0 0 0.2rem;">Model</label>
    <select id="sttModel" style="width:100%; padding:0.4rem; margin-bottom:0.6rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.82rem;"></select>
    <label style="display:block; font-size:0.72rem; color:var(--sp-text-dim); margin:0 0 0.2rem;">Spoken language</label>
    <select id="sttLang" style="width:100%; padding:0.4rem; margin-bottom:0.7rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.82rem;"></select>
    <button type="button" class="ghost" id="sttPreload">Download model now</button>
    <p id="sttStatus" style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.5rem 0 0;"></p>
  `;

  function renderPanel(panel) {
    panel.innerHTML = PANEL_HTML;
    const modelSel = panel.querySelector('#sttModel');
    const langSel  = panel.querySelector('#sttLang');
    const status   = panel.querySelector('#sttStatus');
    const preload  = panel.querySelector('#sttPreload');

    for (const m of MODELS) { const o = document.createElement('option'); o.value = m.id; o.textContent = m.label; modelSel.appendChild(o); }
    for (const [v, l] of LANGS) { const o = document.createElement('option'); o.value = v; o.textContent = l; langSel.appendChild(o); }
    modelSel.value = cfgModel();
    langSel.value  = cfgLang();

    modelSel.addEventListener('change', () => { setCfg({ model: modelSel.value }); status.textContent = ''; });
    langSel.addEventListener('change', () => setCfg({ lang: langSel.value }));

    if (!supported()) {
      preload.disabled = true;
      status.textContent = 'This browser lacks microphone/worker support, so on-device speech is unavailable.';
      return;
    }

    preload.addEventListener('click', () => {
      preload.disabled = true;
      status.textContent = 'Loading…';
      _progressCb = (d) => {
        if (d && d.ready) { status.textContent = 'Model ready.'; preload.disabled = false; _progressCb = null; return; }
        const pct = d && d.progress ? Math.round(d.progress * 100) : 0;
        status.textContent = 'Downloading model… ' + pct + '%';
      };
      try { getWorker().postMessage({ type: 'load', modelId: cfgModel() }); }
      catch (e) { status.textContent = 'Failed: ' + ((e && e.message) || e); preload.disabled = false; _progressCb = null; }
    });
  }

  // ============================================================
  // Init — idempotent + self-retrying (mirrors notifications.js). Hidden entirely
  // on unsupported browsers.
  // ============================================================
  let _btnDone = false, _panelDone = false;
  function init() {
    if (!supported()) return;   // no button, no panel — clean no-op
    if (!_btnDone) _btnDone = injectButton();
    if (!_panelDone && window.SandpieSettings) {
      _panelDone = true;
      SandpieSettings.register({ id: 'speech', title: 'Speech', order: 35, render: renderPanel });
    } else if (!_panelDone && typeof SandpieMenu !== 'undefined') {
      _panelDone = true;
      SandpieMenu.add('speechSection', { title: 'Speech', open: false, html: PANEL_HTML, onRender: renderPanel });
    }
    if (_btnDone && _panelDone) return;
    setTimeout(init, 500);   // composer or a host not ready yet — retry
  }

  return { init, insertText, startRecording, stopRecording, supported, _internals: { decodeToMono16k, transcribeAudio } };
})();

if (typeof window !== 'undefined') window.SandpieSpeech = SandpieSpeech;
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSpeech.init);
else SandpieSpeech.init();
