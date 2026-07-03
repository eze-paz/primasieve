/* coi-serviceworker.js — make a page crossOriginIsolated WITHOUT server config.
 *
 * WHY: SharedArrayBuffer (→ wllama multi-threading) is only available when the
 * document is cross-origin isolated, which normally requires the server to send
 *   Cross-Origin-Opener-Policy: same-origin
 *   Cross-Origin-Embedder-Policy: require-corp | credentialless
 * sandpie's server does NOT send these (COI was removed). This service worker
 * re-adds them on the fly for its own scope, so a static host becomes isolated.
 *
 * We use COEP **credentialless** (not require-corp) so cross-origin loads that
 * lack a CORP header — the wllama wasm on jsDelivr, the GGUF on HuggingFace —
 * still succeed (they're fetched without credentials instead of being blocked).
 *
 * Scope = the directory this file is served from. Put it next to the page that
 * needs isolation. The page reloads itself ONCE after the worker takes control.
 */
if (typeof window === 'undefined') {
  // ---------- service-worker context ----------
  self.addEventListener('install', () => self.skipWaiting());
  self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

  self.addEventListener('fetch', (event) => {
    const req = event.request;
    // Don't touch range/cache-only cross-origin requests (would error on reconstruct).
    if (req.cache === 'only-if-cached' && req.mode !== 'same-origin') return;

    event.respondWith(
      fetch(req)
        .then((res) => {
          // Opaque (no-cors) responses can't be rewritten — pass through untouched.
          if (res.status === 0) return res;
          const headers = new Headers(res.headers);
          headers.set('Cross-Origin-Embedder-Policy', 'credentialless');
          headers.set('Cross-Origin-Opener-Policy', 'same-origin');
          return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
        })
        .catch((e) => { console.error('[coi-sw] fetch failed:', e); throw e; })
    );
  });
} else {
  // ---------- page context ----------
  (function () {
    // Already isolated (e.g. server started sending the headers) → clear guard, done.
    if (window.crossOriginIsolated) { try { sessionStorage.removeItem('coiReloaded'); } catch (_) {} return; }
    if (!window.isSecureContext || !('serviceWorker' in navigator)) return;   // SW needs https/localhost

    const reloadOnce = () => {
      let already = false;
      try { already = !!sessionStorage.getItem('coiReloaded'); } catch (_) {}
      if (already) return;                       // guard against reload loops if isolation can't be achieved
      try { sessionStorage.setItem('coiReloaded', '1'); } catch (_) {}
      window.location.reload();
    };

    const src = (document.currentScript && document.currentScript.src) || 'coi-serviceworker.js';
    navigator.serviceWorker.register(src).then((reg) => {
      // If a controller already exists, the headers are (or should be) applied — reload to pick them up.
      if (navigator.serviceWorker.controller) reloadOnce();
    }).catch((e) => console.error('[coi-sw] register failed:', e));

    // First-ever load: no controller yet. Reload as soon as the worker takes control.
    navigator.serviceWorker.addEventListener('controllerchange', reloadOnce);
  })();
}
