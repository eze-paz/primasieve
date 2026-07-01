// sandpie.js — SERVICE WORKER KILL SWITCH (tombstone).
//
// This is NOT the old service worker. All compute (Pyodide, tools, agent loop)
// moved to sandpie-worker.js (a dedicated Web Worker, page lifetime). File
// serving moved to blob URLs (opfs.toUrl). Notifications moved page-side.
//
// This file exists ONLY to evict the previously-registered heavy SW from
// browsers that already cached it. You can't unregister a SW by deleting its
// file: the browser's update check 404s and KEEPS the old worker running. The
// only way to remove it is to serve a new script at the same URL that calls
// registration.unregister() on itself. That is all this does.
//
// It has NO fetch handler, so even during its brief life it never intercepts
// the sandpie-worker.js request. On the next load there is no registration
// left, nothing re-registers it, and no SW ever runs again.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try { await self.clients.claim(); } catch (_) {}
    try { await self.registration.unregister(); } catch (_) {}
    // Force every controlled tab to reload into a SW-free (uncontrolled) state,
    // so the pending sandpie-worker.js fetch is reissued straight to the network.
    try {
      const clients = await self.clients.matchAll({ type: 'window' });
      for (const c of clients) { try { c.navigate(c.url); } catch (_) {} }
    } catch (_) {}
  })());
});
