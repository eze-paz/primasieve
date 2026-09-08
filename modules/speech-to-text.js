// sandpie/modules/speech-to-text.js — SandpieSpeech: voice input UI (rebuild).
//
// UI layer only for now: injects a mic button into the composer's .input-bar
// (right of the model picker) and a "Speech" panel in the gear settings. The
// button toggles idle -> recording -> idle; the transcription engine (on-device
// Whisper + sentence VAD, audio never leaves the tab) plugs into
// window.SandpieSpeechEngine and lands in a later commit — until then the
// button works as a visible state machine and the engine calls are no-ops.
//
// Self-wiring like every sandpie module: injects its own button, registers its
// own settings panel, degrades to a clean no-op on unsupported browsers.
//
// CLASSIC script (global window.SandpieSpeech). Load after settings.js.

const SandpieSpeech = (function () {
  'use strict';

  const NS = 'speech';
  const LS_KEY = 'sandpie-speech';
  const DEFAULTS = { model: 'onnx-community/whisper-base', lang: 'auto' };

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

  // ── Engine hooks — filled by the logic commit. UI must NOT throw when the
  // engine is absent, so this build is safe to ship before the engine lands. ──
  function engineStart() {
    if (window.SandpieSpeechEngine && window.SandpieSpeechEngine.start) return window.SandpieSpeechEngine.start();
    console.warn('[stt] engine not wired yet — UI only');
    flashTitle('Engine pending — logic commit next');
    setState('idle');
  }
  function engineStop() {
    if (window.SandpieSpeechEngine && window.SandpieSpeechEngine.stop) return window.SandpieSpeechEngine.stop();
    setState('idle');
  }

  function onMicClick() {
    if (_state === 'idle') {
      setState('recording');
      engineStart();
    } else if (_state === 'recording') {
      setState('busy');
      engineStop();
      // The engine calls SandpieSpeech.engineDone() when it finishes; with no
      // engine wired, return to idle right away.
      if (!window.SandpieSpeechEngine) setState('idle');
    } else {
      setState('idle');   // busy state clicked: user bailed out
    }
  }

  // Public hook for the engine: call when a stop/finish transition completes.
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
      status.textContent = 'Engine not wired yet — model download arrives with the logic commit.';
      setTimeout(() => { preload.disabled = false; }, 2500);
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
    _internals: { setState, cfgModel, cfgLang },
  };
})();

if (typeof window !== 'undefined') window.SandpieSpeech = SandpieSpeech;
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSpeech.init);
else SandpieSpeech.init();
