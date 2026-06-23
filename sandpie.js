// sandpie.js — self-destructing SW.
// Replaces any previously cached heavy SW (which had a fetch handler that would
// intercept sandpie-worker.js fetches), then unregisters itself.
// All functionality has moved to sandpie-worker.js (Web Worker, page lifetime).
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil(
    self.clients.claim()
      .then(() => self.registration.unregister())
      .catch(() => {})
  );
});
