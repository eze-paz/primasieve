/**
 * Keep-alive: silent-audio trick so Android Chrome keeps the page's JS
 * running (timers + network) while a conversation generates and the user
 * locks the screen / switches apps. ANDROID ONLY — gated by UA and by a
 * user toggle in Settings → Notifications ("Keep generating when screen
 * is locked"). The audio is a looping WAV of pure digital silence played
 * through a real <audio> element, which is what earns the page the
 * media-session keep-alive. iOS/desktop: no-op.
 *
 * Usage: <script src="modules/keepalive.js?v=1"></script>
 * Hooks: SandpieKeepAlive.start() / .stop() from setStreamSending.
 */
const SandpieKeepAlive = (function () {
  'use strict';

  const PREF_KEY = 'keepalive'; // SandpieConfig namespace
  // 1 sample of digital silence, 8 kHz mono 8-bit WAV, looped. ~70 bytes.
  // 'data:audio/wav' base64 of: RIFF header + one zero sample.
  const SILENT_WAV =
    'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

  let audioEl = null;
  let wantOn = false;          // generation in progress
  let disabled = false;        // hard-failed this session — never retry-loop
  let clickRetryArmed = false;

  function isAndroid() {
    return /Android/i.test(navigator.userAgent || '');
  }

  function prefEnabled() {
    try {
      const c = window.SandpieConfig;
      if (c) {
        const k = c.get(PREF_KEY);
        if (k && typeof k.enabled === 'boolean') return k.enabled;
      }
    } catch (_) {}
    return localStorage.getItem('sandpie-keepalive') !== '0'; // default ON
  }

  function setPrefEnabled(on) {
    try {
      const c = window.SandpieConfig;
      if (c) c.set(PREF_KEY, Object.assign({}, c.get(PREF_KEY, {}) || {}, { enabled: !!on }));
    } catch (_) {}
    if (on) localStorage.removeItem('sandpie-keepalive');
    else localStorage.setItem('sandpie-keepalive', '0');
    // React immediately: turning it off mid-generation must stop the audio.
    if (!on) pauseAudio();
    else if (wantOn) playAudio();
  }

  function ensureEl() {
    if (audioEl) return audioEl;
    audioEl = new Audio(SILENT_WAV);
    audioEl.loop = true;
    audioEl.volume = 1; // samples are zero → inaudible; element must look "real"
    audioEl.addEventListener('error', () => {
      console.warn('[sandpie] keepalive: audio element error — disabled for session');
      disabled = true;
      pauseAudio();
    });
    return audioEl;
  }

  function playAudio() {
    if (disabled || !isAndroid() || !prefEnabled()) return;
    const a = ensureEl();
    if (!a.paused) return;
    const p = a.play();
    if (p && p.catch) {
      p.catch(() => {
        // Autoplay policy: needs a user gesture. Arm a one-shot retry on the
        // next interaction (worst case the keep-alive starts a moment late).
        if (clickRetryArmed) return;
        clickRetryArmed = true;
        document.addEventListener('click', function retry() {
          clickRetryArmed = false;
          if (wantOn) playAudio();
        }, { once: true, capture: true });
      });
    }
  }

  function pauseAudio() {
    try {
      if (audioEl && !audioEl.paused) { audioEl.pause(); audioEl.currentTime = 0; }
    } catch (_) {}
  }

  // Generation started (any conversation). Idempotent.
  function start() { wantOn = true; playAudio(); }

  // Generation ended (natural, Stop, or error). Idempotent.
  function stop() { wantOn = false; pauseAudio(); }

  return { start, stop, prefEnabled, setPrefEnabled, isAndroid };
})();
window.SandpieKeepAlive = SandpieKeepAlive;
