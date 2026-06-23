// sandpie.js — Minimal service worker: only /opfs/ file serving.
// All Pyodide, tools, and the agent loop have moved to sandpie-worker.js (Web Worker).
const SW_VERSION = '2.0.0-minimal';
console.log('[sandpie-sw] boot — version=' + SW_VERSION);

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

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

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.includes('/opfs/')) return event.respondWith(handleOpfs(url.pathname));
  // All other requests fall through to the network.
});

// ---- OPFS helpers ----
function splitPath(p) {
  const parts = String(p).split('/').filter(Boolean);
  const name = parts.pop();
  return { parts, name };
}
async function opfsResolveDir(parts) {
  let dir = await navigator.storage.getDirectory();
  for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: false });
  return dir;
}
async function opfsReadBytes(path) {
  const { parts, name } = splitPath(path);
  const dir = await opfsResolveDir(parts);
  const handle = await dir.getFileHandle(name);
  return new Uint8Array(await (await handle.getFile()).arrayBuffer());
}

async function handleOpfs(path) {
  const [pathOnly, query] = path.split('?');
  const opfsPath = decodeURIComponent(pathOnly.slice(pathOnly.indexOf('/opfs/') + '/opfs/'.length));
  const forceDownload = query && new URLSearchParams(query).get('download') === '1';
  const isolation = {
    'Cross-Origin-Embedder-Policy': 'credentialless',
    'Cross-Origin-Resource-Policy': 'same-origin',
  };
  try {
    const bytes = await opfsReadBytes(opfsPath);
    const ext = (opfsPath.split('.').pop() || '').toLowerCase();
    const types = { html:'text/html', htm:'text/html', svg:'image/svg+xml',
                    png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg',
                    gif:'image/gif', webp:'image/webp', csv:'text/csv',
                    json:'application/json', txt:'text/plain' };
    const ct = types[ext] || 'application/octet-stream';
    if (ext === 'html' || ext === 'htm') {
      let text = new TextDecoder().decode(bytes);
      const script = `<script>(function(){` +
        `function report(){var h=Math.max(document.body?document.body.scrollHeight:0,` +
        `document.documentElement?document.documentElement.scrollHeight:0,100);` +
        `parent.postMessage({type:'sandpie-artifact-resize',h:h},'*');}` +
        `var ro=new ResizeObserver(function(){requestAnimationFrame(report);});` +
        `if(document.body)ro.observe(document.body);` +
        `if(document.documentElement)ro.observe(document.documentElement);` +
        `window.addEventListener('load',report);` +
        `setTimeout(report,50);setTimeout(report,300);` +
        `})();<\/script>`;
      if (/<\/body>/i.test(text)) text = text.replace(/<\/body>/i, script + '</body>');
      else text += script;
      return new Response(text, { headers: { 'Content-Type': 'text/html', 'Cache-Control': 'no-store', ...isolation } });
    }
    const headers = { 'Content-Type': ct, 'Cache-Control': 'no-store', ...isolation };
    if (forceDownload) headers['Content-Disposition'] = 'attachment';
    return new Response(bytes, { headers });
  } catch (e) {
    return new Response('Not found: ' + opfsPath, { status: 404, headers: { 'Content-Type': 'text/plain' } });
  }
}
