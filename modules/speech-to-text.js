// sandpie/modules/speech-to-text.js — SandpieSpeech: on-device voice input.
//
// Mic button in the composer. Click → start listening; speech is segmented by
// an energy VAD into sentence-ish chunks, each chunk is transcribed ON-DEVICE
// with Whisper (modules/stt-worker.js, Transformers.js: WebGPU first, WASM
// fallback) and the text is APPENDED into the prompt box as segments complete.
// Cost per transcription is constant (one segment, not the whole window) — no
// drag as the dictation gets long. Click again → stop; the trailing buffer is
// flushed as a final segment. It never auto-sends: the user reviews then sends.
//
// FULLY ON-DEVICE: the microphone audio NEVER leaves the tab. The only network
// traffic is the one-time model download from the HF CDN (cached after).
//
// Self-wiring like every sandpie module: injects its own button, registers its
// own settings panel, degrades to a clean no-op on unsupported browsers.
//
// CLASSIC script (global window.SandpieSpeech). Load after settings.js.

const SandpieSpeech = (function () {
  'use strict';

  const NS = 'speech';
  const LS_KEY = 'sandpie-speech';
  const DEFAULTS = { model: 'onnx-community/whisper-base', lang: 'auto', engine: 'webspeech' };

  const MODELS = [
    { id: 'onnx-community/whisper-tiny',  label: 'Whisper Tiny — fastest (~80 MB)' },
    { id: 'onnx-community/whisper-base',  label: 'Whisper Base — balanced (~150 MB)' },
    { id: 'onnx-community/whisper-small', label: 'Whisper Small — most accurate (~480 MB)' },
  ];
  const LANGS = [
    ['auto', 'Auto-detect'], ['es', 'Spanish'], ['en', 'English'], ['fr', 'French'],
    ['de', 'German'], ['it', 'Italian'], ['pt', 'Portuguese'], ['ru', 'Russian'],
    ['zh', 'Chinese'], ['ja', 'Japanese'], ['ar', 'Arabic'],
  ];

  // Inline SVG glyphs, inherit currentColor.
  const MIC_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="8" y1="22" x2="16" y2="22"/></svg>';
  const STOP_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="3"/></svg>';

  // ── VAD / capture tuning ──
  const TARGET_SR   = 16000;  // Whisper expects 16 kHz mono
  const RMS_THRESH  = 0.012;  // speech vs silence energy gate
  const MIN_SEG_SEC = 0.5;    // shorter than this after silence → discard (hallucination guard)
  const SILENCE_MS  = 400;    // silence that closes a segment (lower = text appears sooner)
  const MAX_SEG_SEC = 28;     // force-close before Whisper's 30 s receptive field

  // ── Prefs (SandpieConfig namespace, localStorage fallback — no secrets) ──
  function cfgAll() {
    try {
      const c = window.SandpieConfig && window.SandpieConfig.get(NS);
      if (c && typeof c === 'object') return Object.assign({}, DEFAULTS, c);
    } catch (_) {}
    try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(LS_KEY) || '{}')); }
    catch (_) { return Object.assign({}, DEFAULTS); }
  }
  function setCfg(patch) {
    const next = Object.assign(cfgAll(), patch);
    try {
      if (window.SandpieConfig && window.SandpieConfig.set) window.SandpieConfig.set(NS, next);
      else localStorage.setItem(LS_KEY, JSON.stringify(next));
    } catch (_) { try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch (_) {} }
  }
  const cfgModel = () => cfgAll().model;
  const cfgLang  = () => cfgAll().lang;
  // 'moonshine' was removed — migrate any saved pref to whisper
  const cfgEngine = () => { const e = cfgAll().engine; return e === 'moonshine' ? 'whisper' : e; };

  // ── State machine: idle | recording | busy ──
  let _state = 'idle';
  let _btn = null;

  function supported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia
      && (window.AudioContext || window.webkitAudioContext)
      && typeof Worker !== 'undefined');
  }

  function setState(next) {
    _state = next;
    if (!_btn) return;
    _btn.classList.toggle('recording', next === 'recording');
    _btn.classList.toggle('busy', next === 'busy');
    _btn.innerHTML = next === 'recording' ? STOP_SVG : MIC_SVG;
    _btn.title = next === 'recording' ? 'Stop dictation'
      : next === 'busy' ? 'Transcribing…'
      : 'Dictate by voice (on-device)';
  }

  function flashTitle(msg) {
    if (!_btn) return;
    _btn.title = msg;
    setTimeout(() => { if (_btn && _state === 'idle') _btn.title = 'Dictate by voice (on-device)'; }, 4000);
  }

  // ── Worker plumbing ──
  let _worker = null, _workerReady = false, _reqId = 0, _progressCb = null;
  function getWorker() {
    if (_worker) return _worker;
    _worker = new Worker('modules/stt-worker.js', { type: 'module' });
    _worker.onmessage = (e) => {
      const d = e.data || {};
      if (d.type === 'progress') { if (_progressCb) _progressCb(d.data); return; }
      if (d.type === 'ready') { _workerReady = true; if (_progressCb) { _progressCb({ ready: true }); } return; }
      if (d.type === 'result') { const r = _pending.get(d.id); _pending.delete(d.id); if (r) r.resolve(d.text); return; }
      if (d.type === 'error') {
        const r = _pending.get(d.id);
        if (r) { _pending.delete(d.id); r.reject(new Error(d.message)); }
        else console.warn('[stt] worker error:', d.message);
        return;
      }
    };
    _worker.onerror = (e) => {
      console.warn('[stt] worker error:', e.message || e);
      flashTitle('STT engine error: ' + (e.message || 'worker failed'));
      window.SandpieSpeech.engineDone(false, (e && e.message) || 'worker failed');
    };
    return _worker;
  }
  const _pending = new Map();
  function transcribeSegment(f32) {
    const id = ++_reqId;
    return new Promise((resolve, reject) => {
      _pending.set(id, { resolve, reject });
      getWorker().postMessage({ type: 'transcribe', id, modelId: activeModelId(), lang: cfgLang(), audio: f32 }, [f32.buffer]);
    });
  }

  // ── Composer insertion: append text to the main prompt box ──
  function appendToComposer(text) {
    if (!text) return;
    const ta = document.getElementById('input') || document.querySelector('textarea');
    if (!ta) return;
    const cur = ta.value;
    const needsSpace = cur && !/\s$/.test(cur);
    ta.value = cur + (needsSpace ? ' ' : '') + text + ' ';
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    ta.focus();
    // keep caret at end
    try { ta.setSelectionRange(ta.value.length, ta.value.length); } catch (_) {}
  }

  // ── Interim tail: live Web Speech interim text rendered INTO the prompt box ──
  // The unconfirmed interim text is appended to the composer and REPLACED in
  // place as recognition refines it; on a final result the tail is removed and
  // the confirmed transcript appended in its place. On stop, any surviving tail
  // is promoted to committed text so no dictated words are lost.
  let _interimTail = '';
  function _composerEl() {
    return document.getElementById('input') || document.querySelector('textarea');
  }
  function setInterimText(text) {
    const ta = _composerEl(); if (!ta) return;
    let cur = ta.value;
    if (_interimTail && cur.endsWith(_interimTail)) {
      cur = cur.slice(0, cur.length - _interimTail.length);
    }
    _interimTail = text || '';
    if (_interimTail) {
      const needsSpace = cur && !/\s$/.test(cur);
      cur = cur + (needsSpace ? ' ' : '') + _interimTail;
    }
    ta.value = cur;
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    try { ta.setSelectionRange(ta.value.length, ta.value.length); } catch (_) {}
  }
  function commitInterim(finalText) {
    setInterimText('');          // drop the unconfirmed tail
    appendToComposer(finalText); // append the confirmed transcript
  }

  // ── Engine: Web Speech API (default) — native recognizer, live text ──
  // Chrome/Edge: excellent quality + instant live results. Desktop Chrome routes
  // audio through Google's recognizer service (not fully on-device); Android is
  // on-device. Unavailable on Firefox/Safari -> falls back to Whisper on-device.
  let _recog = null, _recogActive = false;
  function webspeechSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }
  function wsStart() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return false;
    const r = new SR();
    r.continuous = true;
    r.interimResults = true;
    const lang = cfgLang();
    r.lang = lang === 'auto' ? (navigator.language || 'es-ES') : lang;
    r.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) {
          commitInterim(res[0].transcript);
        } else interim += res[0].transcript;
      }
      if (interim) setInterimText(interim);
      setState('recording');
      if (interim) _btn.title = interim.slice(-60);
    };
    r.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;   // benign
      console.warn('[stt] webspeech error:', e.error);
      flashTitle('Voice input error: ' + e.error);
    };
    r.onend = () => {
      // Chrome auto-stops after silence; restart while the user is still recording.
      if (_recogActive && !_stopping) { try { r.start(); return; } catch (_) {} }
      if (!_recogActive) window.SandpieSpeech.engineDone(true);
    };
    _recog = r;
    _recogActive = true;
    try { r.start(); } catch (e) { _recogActive = false; return false; }
    return true;
  }
  function wsStop() {
    if (_interimTail) commitInterim(_interimTail);   // promote unconfirmed tail
    _recogActive = false;
    try { _recog && _recog.stop(); } catch (_) {}
    // onend fires engineDone; settle shortly after in case it never fires.
    setTimeout(() => { if (_state === 'busy') window.SandpieSpeech.engineDone(true); }, 800);
  }

  // ── Capture + VAD loop (Whisper on-device engine) ──
  let _stream = null, _ctx = null, _node = null, _src = null;
  let _buf = [];            // Float32 chunks at 16 kHz (current segment)
  let _bufSec = 0;
  let _silenceMs = 0;
  let _speechSeen = false;
  let _queue = Promise.resolve();   // serialized transcription queue
  let _stopping = false;

  function resampleTo16k(input, inputRate) {
    if (inputRate === TARGET_SR) return input;
    const ratio = inputRate / TARGET_SR;
    const outLen = Math.floor(input.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const j = Math.floor(i * ratio);
      out[i] = input[j] || 0;
    }
    return out;
  }

  function rms(buf) {
    let s = 0;
    for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
    return Math.sqrt(s / buf.length);
  }

  function enqueueSegment(f32, final) {
    if (f32.length / TARGET_SR < MIN_SEG_SEC && !final) return;
    _queue = _queue.then(async () => {
      try {
        const txt = await transcribeSegment(f32);
        console.info('[stt] segment ->', JSON.stringify(txt));
        if (txt) appendToComposer(txt);
      } catch (e) {
        console.warn('[stt] segment failed:', e && e.message);
        if (final) flashTitle('Dictation failed: ' + (e && e.message || e));
      }
      if (final) window.SandpieSpeech.engineDone(true);
    });
  }

  let _dbgT = 0;
  function onAudioChunk(chunk, rate) {
    const f32 = resampleTo16k(chunk, rate);
    const level = rms(f32);
    const now = Date.now();
    if (now - _dbgT > 2000) { _dbgT = now; console.info('[stt] mic level rms=' + level.toFixed(4) + ' (thresh ' + RMS_THRESH + ')'); }
    const loud = level > RMS_THRESH;
    if (loud) {
      _speechSeen = true;
      _silenceMs = 0;
      _buf.push(f32);
      _bufSec += f32.length / TARGET_SR;
      if (_bufSec >= MAX_SEG_SEC) flushSegment(false);   // force-close long segment
    } else if (_speechSeen) {
      _silenceMs += (f32.length / TARGET_SR) * 1000;
      _buf.push(f32);   // keep trailing silence inside the segment (natural tail)
      _bufSec += f32.length / TARGET_SR;
      if (_silenceMs >= SILENCE_MS) flushSegment(false);
    }
    // pure silence before any speech: drop (keeps ticks cheap)
  }

  function flushSegment(final) {
    if (!_buf.length) { if (final) window.SandpieSpeech.engineDone(true); return; }
    let n = 0;
    for (const c of _buf) n += c.length;
    const total = new Float32Array(n);
    let off = 0;
    for (const c of _buf) { total.set(c, off); off += c.length; }
    _buf = []; _bufSec = 0; _silenceMs = 0; _speechSeen = false;
    enqueueSegment(total, final);
  }

  function activeModelId() {
    return cfgModel();
  }
  async function engineStart() {
    if (cfgEngine() === 'webspeech' && webspeechSupported()) {
      if (wsStart()) return;   // native engine took over
      flashTitle('Web Speech unavailable — using on-device Whisper');
    }
    try {
      _stopping = false;
      _stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      _ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (_ctx.state === 'suspended') await _ctx.resume();
      _src = _ctx.createMediaStreamSource(_stream);
      _node = _ctx.createScriptProcessor(4096, 1, 1);   // deprecated but universal; capture-only
      _node.onaudioprocess = (e) => { if (_state === 'recording') onAudioChunk(e.inputBuffer.getChannelData(0), _ctx.sampleRate); };
      _src.connect(_node);
      const sink = _ctx.createGain(); sink.gain.value = 0;   // ScriptProcessor needs a destination; keep it silent
      _node.connect(sink); sink.connect(_ctx.destination);
      // Preload the model in the background so the first segment isn't slow.
      try { getWorker().postMessage({ type: 'load', modelId: activeModelId() }); } catch (_) {}
    } catch (e) {
      console.warn('[stt] mic denied/failed:', e && e.message);
      flashTitle('Microphone unavailable: ' + (e && e.message || e));
      teardownCapture();
      window.SandpieSpeech.engineDone(false, (e && e.message) || 'mic failed');
    }
  }

  function teardownCapture() {
    try { if (_node) _node.disconnect(); } catch (_) {}
    try { if (_src) _src.disconnect(); } catch (_) {}
    try { if (_ctx) _ctx.close(); } catch (_) {}
    try { if (_stream) _stream.getTracks().forEach((t) => t.stop()); } catch (_) {}
    _node = _src = _ctx = _stream = null;
  }

  function engineStop() {
    if (_recogActive) { wsStop(); return; }
    _stopping = true;
    teardownCapture();
    flushSegment(true);   // trailing buffer → final segment; engineDone fires on drain
    // If nothing was pending, engineDone already fired inside flushSegment.
  }

  function onMicClick() {
    if (_state === 'idle') {
      setState('recording');
      // Preload the model immediately so the first segment isn't slow
      // (runs in parallel with the getUserMedia permission prompt).
      try { getWorker().postMessage({ type: 'load', modelId: activeModelId() }); } catch (_) {}
      engineStart();
    } else if (_state === 'recording') {
      setState('busy');
      engineStop();
    } else {
      setState('idle');   // busy state clicked: user bailed out
    }
  }

  // Public hook: called when the final segment drains (or on failure).
  function engineDone(ok, err) {
    if (err) { console.warn('[stt]', err); flashTitle('Dictation failed: ' + err); }
    setState('idle');
  }

  // ── Button injection ──
  function injectButton() {
    if (document.getElementById('micBtn')) { _btn = document.getElementById('micBtn'); return true; }
    const bar = document.querySelector('.input-bar');
    if (!bar) return false;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'micBtn';
    btn.className = 'attach-btn mic-btn';
    btn.title = 'Dictate by voice (on-device)';
    btn.setAttribute('aria-label', 'Dictate by voice');
    btn.innerHTML = MIC_SVG;
    btn.addEventListener('click', onMicClick);
    const picker = document.getElementById('modelPicker');
    const attach = document.getElementById('attachBtn');
    if (picker && picker.parentNode === bar) picker.insertAdjacentElement('afterend', btn);
    else if (attach && attach.parentNode === bar) attach.insertAdjacentElement('afterend', btn);
    else bar.insertBefore(btn, bar.firstChild);
    _btn = btn;
    return true;
  }

  // ── Settings panel (gear modal via SandpieSettings) ──
  const PANEL_HTML = `
    <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.6rem;">
      Speak instead of typing — the dictated text streams into the prompt box as you talk.
      Transcription runs <strong>fully on-device</strong> with Whisper: your microphone audio
      never leaves this tab. The first use downloads the model (cached after).
    </p>
    <label style="display:block; font-size:0.72rem; color:var(--sp-text-dim); margin:0 0 0.2rem;">Engine</label>
    <select id="sttEngine" style="width:100%; padding:0.4rem; margin-bottom:0.6rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font-size:0.82rem;">
      <option value="webspeech">Browser native (Web Speech) — fast, live text</option>
      <option value="whisper">Whisper on-device — private, audio never leaves the tab</option>
      </select>
    <p id="sttEngineNote" style="font-size:0.68rem; color:var(--sp-text-dim); margin:0 0 0.6rem;"></p>
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
    for (const pair of LANGS) { const o = document.createElement('option'); o.value = pair[0]; o.textContent = pair[1]; langSel.appendChild(o); }
    const engineSel = panel.querySelector('#sttEngine');
    const engineNote = panel.querySelector('#sttEngineNote');
    engineSel.value = cfgEngine();
    modelSel.value = cfgModel();
    langSel.value  = cfgLang();
    function noteFor() {
      if (cfgEngine() === 'webspeech') {
        return webspeechSupported()
          ? "Desktop Chrome/Edge route the audio through the browser's speech service; Android runs it on-device."
          : 'This browser has no Web Speech API — Whisper on-device will be used instead.';
      }
      return 'Whisper runs fully in this tab; the first use downloads the model.';
    }
    engineNote.textContent = noteFor();

    engineSel.addEventListener('change', () => { setCfg({ engine: engineSel.value }); engineNote.textContent = noteFor(); });

    modelSel.addEventListener('change', () => { setCfg({ model: modelSel.value }); _workerReady = false; status.textContent = ''; });
    langSel.addEventListener('change', () => setCfg({ lang: langSel.value }));

    if (!supported()) {
      preload.disabled = true;
      status.textContent = 'This browser lacks microphone/worker support, so on-device speech is unavailable.';
      return;
    }

    preload.addEventListener('click', () => {
      preload.disabled = true;
      status.textContent = 'Downloading model… 0%';
      _progressCb = (d) => {
        if (d && d.ready) { status.textContent = 'Model ready.'; preload.disabled = false; _progressCb = null; return; }
        const pct = d && d.progress ? Math.round(d.progress * 100) : 0;
        status.textContent = 'Downloading model… ' + pct + '%';
      };
      try { getWorker().postMessage({ type: 'load', modelId: activeModelId() }); }
      catch (e) { status.textContent = 'Failed: ' + ((e && e.message) || e); preload.disabled = false; _progressCb = null; }
    });
  }

  // ── Init — idempotent + self-retrying (mirrors notifications.js) ──
  let _btnDone = false, _panelDone = false;
  function init() {
    if (!supported()) return;   // no button, no panel — clean no-op
    if (!_btnDone) _btnDone = injectButton();
    if (!_panelDone && window.SandpieSettings) {
      _panelDone = true;
      window.SandpieSettings.register({ id: 'speech', title: 'Speech', order: 35, render: renderPanel });
    }
    if (_btnDone && _panelDone) return;
    setTimeout(init, 500);
  }

  return {
    init, supported, engineDone,
    startRecording: () => { if (_state === 'idle') onMicClick(); },
    stopRecording:  () => { if (_state !== 'idle') onMicClick(); },
    _internals: { setState, cfgModel, cfgLang, resampleTo16k, rms, onAudioChunk, flushSegment },
  };
})();

if (typeof window !== 'undefined') window.SandpieSpeech = SandpieSpeech;
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSpeech.init);
else SandpieSpeech.init();
