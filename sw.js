self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/files/')) {
    e.respondWith(handleFiles(url.pathname));
  }
});

async function handleFiles(pathname) {
  const relPath = pathname.replace(/^\/files\//, '');
  const parts = relPath.split('/');
  const fileName = parts.pop();
  try {
    const root = await navigator.storage.getDirectory();
    let dir = root;
    for (const p of parts) {
      if (!p) continue;
      dir = await dir.getDirectoryHandle(p);
    }
    const fileHandle = await dir.getFileHandle(fileName);
    const blob = await fileHandle.getFile();
    const ct = contentType(fileName);
    return new Response(blob, { headers: { 'Content-Type': ct, 'Cross-Origin-Embedder-Policy': 'require-corp', 'X-Sandpie-SW': '1' } });
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
