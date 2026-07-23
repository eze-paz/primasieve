self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/files/')) {
    e.respondWith(handleFiles(url.pathname, e.request));
  }
});

async function handleFiles(pathname, request) {
  const relPath = pathname.replace(/^\/files\//, '');
  const parts = relPath.split('/').map(s => {
    try { return decodeURIComponent(s); } catch (_) { return s; }
  });
  const fileName = parts.pop();
  try {
    const root = await navigator.storage.getDirectory();
    let dir = root;
    const createDirs = request.method === 'PUT';
    for (const p of parts) {
      if (!p) continue;
      dir = await dir.getDirectoryHandle(p, { create: createDirs });
    }

    if (request.method === 'PUT') {
      const body = await request.text();
      const fh = await dir.getFileHandle(fileName, { create: true });
      const w = await fh.createWritable();
      await w.write(body);
      await w.close();
      // Notify all page clients so they can mark the file dirty for Dropbox sync
      const clients = await self.clients.matchAll();
      for (const client of clients) {
        client.postMessage({ type: 'sw-opfs-changed', paths: [relPath] });
      }
      return new Response('OK', { status: 200, headers: { 'Content-Type': 'text/plain' } });
    }

    // GET
    const fh = await dir.getFileHandle(fileName);
    const blob = await fh.getFile();
    const ct = contentType(fileName);
    return new Response(blob, {
      headers: {
        'Content-Type': ct,
        'Cross-Origin-Embedder-Policy': 'credentialless',
        'X-Sandpie-SW': '1',
      },
    });
  } catch (e) {
    return new Response('Not found: ' + relPath, { status: 404 });
  }
}

function contentType(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = {
    html: 'text/html; charset=utf-8', htm: 'text/html; charset=utf-8',
    css: 'text/css; charset=utf-8',
    js: 'application/javascript; charset=utf-8',
    json: 'application/json; charset=utf-8',
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
    gif: 'image/gif', svg: 'image/svg+xml',
    ico: 'image/x-icon', webp: 'image/webp',
    pdf: 'application/pdf',
    txt: 'text/plain; charset=utf-8',
    ionapi: 'application/json; charset=utf-8',
    ttf: 'font/ttf', otf: 'font/otf',
    wasm: 'application/wasm',
  };
  return map[ext] || 'application/octet-stream';
}
