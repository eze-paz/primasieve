// sandpie.js — Minimal service worker: notifications only.
// File serving has moved to blob URLs (opfs.toUrl in opfs.js).
// All compute (Pyodide, tools, agent loop) runs in sandpie-worker.js.
const SW_VERSION = '3.0.0-notifications-only';
console.log('[sandpie-sw] boot — version=' + SW_VERSION);

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// Focus an existing sandpie window when the user taps a completion notification.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of wins) {
      if (c.url.includes('sandpie') && 'focus' in c) return c.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow('./sandpie.html');
  })());
});
