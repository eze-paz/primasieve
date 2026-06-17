// sandpie/modules/speech-to-text.js — SandpieSpeech: on-device voice input.
//
// Adds a mic button to the composer. Click → start listening; the captured audio
// is transcribed locally with Whisper and STREAMED into the chat input as you
// speak (the text updates every ~tick, not just on stop). Click again → stop and
// commit. It never auto-sends — the user reviews then sends. Transcription runs
// in a dedicated Web Worker (modules/stt-worker.js) via Transformers.js, so the
// audio NEVER leaves the tab — true to sandpie's "nothing escapes the tab"
// promise. The only network traffic is the one-time model download (cached after).
//
// Whisper isn't stream-native, so "streaming" here = continuously capturing PCM
// and re-transcribing the live window every tick, replacing the dictated region
// in the box. For long dictation the window is periodically committed and slid so
// per-tick cost stays bounded.
//
// Optional + self-wiring, like every sandpie module: this script injects its own
// button and registers its own settings panel, so removing the <script> tag
// removes the feature cleanly. It needs only the static .input-bar and degrades
// to no-op on browsers without getUserMedia / AudioContext / Workers.
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
    ['auto', 'Auto-detect'], ['en', 'English'], ['es', 'Spanish'], ['ca', 'Catalan'], ['fr', 'French'],
    ['de', 'German'], ['it', 'Italian'], ['pt', 'Portuguese'], ['nl', 'Dutch'],
    ['ru', 'Russian'], ['zh', 'Chinese'], ['ja', 'Japanese'], ['ko', 'Korean'],
    ['ar', 'Arabic'], ['hi', 'Hindi'],
  ];
  const NS = 'speech';
  const LS_KEY = 'sandpie-speech';
  const DEFAULTS = { model: 'onnx-community/whisper-base', lang: 'auto' };

  const TARGET_SR  = 16000;   // Whisper expects 16 kHz mono
  const TICK_MS    = 700;     // re-transcribe cadence (+ the transcribe time itself)
  const MIN_SEC    = 0.4;     // don't transcribe less than this (avoids silence hallucination)
  const COMMIT_SEC = 24;      // commit + slide the window before whisper's 30s receptive field

  // ── Professional mic glyph (inline SVG, inherits the button's currentColor).
  // Outline mic for idle, filled square for the stop/recording state. ──
  const MIC_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="8" y1="22" x2="16" y2="22"/></svg>';
  const STOP_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="3"/></svg>';

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
  // only hard requirements are mic capture, audio context, and Workers. ──
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
  const WORKER_URL = 'modules/stt-worker.js?v=3';
  let _worker = null, _seq = 0, _progressCb = null;
  function getWorker() {
    if (!_worker) {
      _worker = new Worker(WORKER_URL, { type: 'module' });
      _worker.addEventListener('error', (ev) => console.warn('[stt] worker error:', (ev && ev.message) || ev));
    }
    return _worker;
  }

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
      // Transfer the audio buffer (no copy). Callers pass a disposable snapshot.
      try { worker.postMessage({ type: 'transcribe', id, modelId: cfgModel(), lang: cfgLang(), audio }, [audio.buffer]); }
      catch (e) { cleanup(); reject(e); }
    });
  }

  // Preload / switch the model. Attaches its OWN listener (a plain 'load' posted
  // without this would have nothing routing the worker's reply back), and the
  // worker replies 'ready' to every load — even when the model is already cached
  // — so the settings panel gets a definite finish instead of hanging on "Loading…".
  function loadModel(modelId, onProgress) {
    const worker = getWorker();
    return new Promise((resolve, reject) => {
      function cleanup() { worker.removeEventListener('message', onMsg); }
      const onMsg = (e) => {
        const m = e.data || {};
        if (m.type === 'progress') { try { onProgress && onProgress(m.data); } catch (_) {} return; }
        if (m.type === 'ready') { cleanup(); resolve(); return; }
        if (m.type === 'error') { cleanup(); reject(new Error(m.message || 'stt worker error')); return; }
      };
      worker.addEventListener('message', onMsg);
      try { worker.postMessage({ type: 'load', modelId }); }
      catch (e) { cleanup(); reject(e); }
    });
  }

  // ============================================================
  // Live audio capture (Web Audio → raw PCM) + the streaming transcription loop.
  // ============================================================
  let _ctx = null, _stream = null, _src = null, _node = null, _sink = null;
  let _srcRate = TARGET_SR;
  let _chunks = [];          // Float32Array chunks captured since the last commit
  let _windowLen = 0;        // samples in _chunks (at _srcRate)
  let _committedText = '';   // dictation committed before the current window
  let _windowText = '';      // latest transcript of the current window
  let _prefix = '', _suffix = '';   // the composer text around the dictated region
  // Cooperative sleep so stop() can wake the loop immediately to finalize.
  let _loopTimer = null, _wake = null;
  function sleep(ms) { return new Promise((r) => { _wake = r; _loopTimer = setTimeout(() => { _wake = null; r(); }, ms); }); }
  function wake() { if (_wake) { clearTimeout(_loopTimer); const r = _wake; _wake = null; r(); } }

  function resampleLinear(data, from, to) {
    if (from === to || !data.length) return data;
    const ratio = from / to, n = Math.max(1, Math.floor(data.length / ratio)), out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const idx = i * ratio, i0 = Math.floor(idx), i1 = Math.min(i0 + 1, data.length - 1), f = idx - i0;
      out[i] = data[i0] * (1 - f) + data[i1] * f;
    }
    return out;
  }
  // A fresh 16 kHz mono copy of the live window (safe to transfer to the worker).
  function snapshotWindow() {
    const out = new Float32Array(_windowLen);
    let o = 0; for (const c of _chunks) { out.set(c, o); o += c.length; }
    return _srcRate === TARGET_SR ? out : resampleLinear(out, _srcRate, TARGET_SR);
  }
  // Cheap energy gate — skip transcribing near-silence (whisper hallucinates text
  // like "Thank you." on silence). Only gates BEFORE any speech is detected, so
  // trailing pauses never blank already-dictated text.
  function hasSpeech(a) { let peak = 0; for (let i = 0; i < a.length; i += 64) { const v = Math.abs(a[i]); if (v > peak) peak = v; } return peak > 0.01; }

  function joinText(a, b) { a = (a || '').trim(); b = (b || '').trim(); if (!a) return b; if (!b) return a; return a + ' ' + b; }

  // Replace the dictated region in the composer with the latest transcript and
  // fire 'input' so conversations.js autosize runs. Does NOT steal focus mid-stream.
  function renderLive() {
    const ta = document.getElementById('input');
    if (!ta) return;
    const dict = joinText(_committedText, _windowText);
    ta.value = _prefix + dict + _suffix;
    const pos = (_prefix + dict).length;
    try { ta.setSelectionRange(pos, pos); } catch (_) {}
    if (_btn && _state === 'recording' && dict) _btn.title = 'Stop & insert';
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  }

  async function doTranscribeTick(final) {
    const audio = snapshotWindow();
    const secs = audio.length / TARGET_SR;
    if (!final && secs < MIN_SEC) return;
    if (final && secs < 0.15 && !_windowText) return;
    const gate = (!_committedText && !_windowText);
    if (gate && !hasSpeech(audio)) return;
    let txt;
    try { txt = await transcribeAudio(audio); }
    catch (e) { if (final) flashError('Transcription failed'); console.warn('[stt] transcribe failed:', (e && e.message) || e); return; }
    _windowText = txt;
    renderLive();
    // Commit + slide so the next tick re-transcribes only the trailing window.
    if (!final && secs >= COMMIT_SEC && _windowText) {
      _committedText = joinText(_committedText, _windowText);
      _chunks = []; _windowLen = 0; _windowText = '';
    }
  }

  // The ONLY thing that transcribes during a session — one pass at a time (awaited),
  // so there's no overlap. Exits when state leaves 'recording', does a final pass.
  async function captureLoop() {
    try {
      while (_state === 'recording') {
        await sleep(TICK_MS);
        if (_state !== 'recording') break;
        await doTranscribeTick(false);
      }
      await doTranscribeTick(true);   // finalize the remaining window
    } catch (e) {
      console.warn('[stt] capture loop error:', (e && e.message) || e);
    } finally {
      resetSession();
      setState('idle');
      try { document.getElementById('input')?.focus(); } catch (_) {}
    }
  }

  function teardownCapture() {
    try { if (_node) { _node.onaudioprocess = null; _node.disconnect(); } } catch (_) {}
    try { _sink && _sink.disconnect(); } catch (_) {}
    try { _src && _src.disconnect(); } catch (_) {}
    try { if (_stream) _stream.getTracks().forEach(t => t.stop()); } catch (_) {}   // clears the recording indicator
    try { if (_ctx && _ctx.state !== 'closed') _ctx.close(); } catch (_) {}
    _node = _sink = _src = _stream = _ctx = null;
  }
  function resetSession() {
    teardownCapture();
    _chunks = []; _windowLen = 0; _committedText = ''; _windowText = '';
    _prefix = ''; _suffix = ''; _progressCb = null;
  }

  async function startRecording() {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } }); }
    catch (e) { flashError(e && e.name === 'NotAllowedError' ? 'Microphone permission denied' : 'No microphone available'); return; }
    _stream = stream;

    const AC = window.AudioContext || window.webkitAudioContext;
    try { _ctx = new AC({ sampleRate: TARGET_SR }); }
    catch (_) { try { _ctx = new AC(); } catch (e2) { flashError('Audio not supported'); teardownCapture(); return; } }
    _srcRate = _ctx.sampleRate;   // browser may ignore the requested rate; we resample if so

    try {
      _src = _ctx.createMediaStreamSource(stream);
      _node = _ctx.createScriptProcessor(4096, 1, 1);
      _node.onaudioprocess = (e) => {
        const ch = e.inputBuffer.getChannelData(0);
        _chunks.push(new Float32Array(ch));   // copy — the source buffer is reused
        _windowLen += ch.length;
      };
      // Route through a muted gain so the mic isn't played back; ScriptProcessor
      // still needs a path to the destination to fire on some browsers.
      _sink = _ctx.createGain(); _sink.gain.value = 0;
      _src.connect(_node); _node.connect(_sink); _sink.connect(_ctx.destination);
    } catch (e) { flashError('Could not start capture'); teardownCapture(); return; }

    // Anchor the dictation region to the current caret (or the end), normalising
    // spacing so the inserted text doesn't run into existing words.
    const ta = document.getElementById('input');
    const at = (ta && document.activeElement === ta && ta.selectionStart != null) ? ta.selectionStart : (ta ? ta.value.length : 0);
    _prefix = ta ? ta.value.slice(0, at) : '';
    _suffix = ta ? ta.value.slice(at) : '';
    if (_prefix && !/\s$/.test(_prefix)) _prefix += ' ';
    if (_suffix && !/^\s/.test(_suffix)) _suffix = ' ' + _suffix;
    _chunks = []; _windowLen = 0; _committedText = ''; _windowText = '';

    // Surface model-download progress on first use via the button tooltip.
    _progressCb = (d) => {
      if (!_btn || _state === 'idle') return;
      if (d && d.ready) { _btn.title = 'Listening…'; return; }
      const p = d && d.progress ? Math.round(d.progress * 100) : 0;
      _btn.title = 'Loading model… ' + p + '%';
    };

    setState('recording');
    captureLoop();
  }

  function stopRecording() {
    if (_state !== 'recording') return;
    setState('finalizing');
    teardownCapture();   // stop capturing now; the loop does one last transcribe of what we have
    wake();              // don't wait out the current tick delay
  }

  // ============================================================
  // Composer mic button (self-injected, styled as an .attach-btn).
  // ============================================================
  let _btn = null, _state = 'idle', _flashTimer = null;

  function onMicClick() {
    if (_state === 'idle') startRecording();
    else if (_state === 'recording') stopRecording();
    // 'finalizing' → ignore (button is disabled)
  }

  function setState(s) {
    _state = s;
    if (!_btn) return;
    clearTimeout(_flashTimer);
    _btn.classList.toggle('recording', s === 'recording');
    _btn.disabled = (s === 'finalizing');
    _btn.innerHTML = (s === 'idle') ? MIC_SVG : STOP_SVG;
    _btn.title = s === 'recording' ? 'Listening… (click to stop)'
               : s === 'finalizing' ? 'Finishing…'
               : 'Speak (on-device)';
  }

  function flashError(msg) {
    if (!_btn) return;
    _btn.title = msg;
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(() => { if (_state === 'idle') _btn.title = 'Speak (on-device)'; }, 4000);
    console.warn('[stt]', msg);
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
    btn.setAttribute('aria-label', 'Dictate by voice');
    btn.innerHTML = MIC_SVG;
    btn.addEventListener('click', onMicClick);
    // Place it to the RIGHT of the model picker (send stays far right via margin).
    const picker = document.getElementById('modelPicker');
    const attach = document.getElementById('attachBtn');
    if (picker && picker.parentNode === bar) picker.insertAdjacentElement('afterend', btn);
    else if (attach && attach.parentNode === bar) attach.insertAdjacentElement('afterend', btn);
    else bar.insertBefore(btn, bar.firstChild);
    _btn = btn;
    return true;
  }

  // ============================================================
  // Settings panel (gear modal via SandpieSettings; sidebar fallback).
  // ============================================================
  const PANEL_HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">
      Speak instead of typing — the text streams into the box as you talk. Transcription runs
      <strong>fully on-device</strong> with Whisper, so your microphone audio never leaves this tab.
      The first use downloads the model (cached after).
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

    preload.addEventListener('click', async () => {
      preload.disabled = true;
      status.textContent = 'Loading…';
      try {
        await loadModel(cfgModel(), (d) => {
          const pct = d && d.progress ? Math.round(d.progress * 100) : 0;
          status.textContent = pct ? ('Downloading model… ' + pct + '%') : 'Loading…';
        });
        status.textContent = 'Model ready.';
      } catch (e) {
        status.textContent = 'Failed: ' + ((e && e.message) || e);
      } finally {
        preload.disabled = false;
      }
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

  return { init, supported, startRecording, stopRecording, _internals: { resampleLinear, transcribeAudio } };
})();

if (typeof window !== 'undefined') window.SandpieSpeech = SandpieSpeech;
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSpeech.init);
else SandpieSpeech.init();
