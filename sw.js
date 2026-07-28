self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/files/')) {
    e.respondWith(handleFiles(url.pathname, e.request));
  }
});

// Files under a dehydrated (on-demand) workspace exist in Dropbox but not in OPFS,
// so reading straight from OPFS 404s — which breaks any artifact that fetches its
// own sibling assets. The SW has no Dropbox credentials and shouldn't; instead it
// asks a page client to fetch the file and then retries the read once.
async function askClientToHydrate(rel) {
  let clients = [];
  try { clients = await self.clients.matchAll({ includeUncontrolled: true, type: 'window' }); } catch (_) {}
  if (!clients.length) return false;
  return await new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    const timer = setTimeout(() => finish(false), 20000);   // never hang a fetch on an unresponsive page
    try {
      const ch = new MessageChannel();
      ch.port1.onmessage = (ev) => { clearTimeout(timer); finish(!!(ev.data && ev.data.ok)); };
      clients[0].postMessage({ type: 'sw-hydrate', rel }, [ch.port2]);
    } catch (_) { clearTimeout(timer); finish(false); }
  });
}

async function handleFiles(pathname, request) {
  const relPath = pathname.replace(/^\/files\//, '');
  const parts = relPath.split('/').map(s => {
    try { return decodeURIComponent(s); } catch (_) { return s; }
  });
  const fileName = parts.pop();
  const decodedRel = parts.concat([fileName]).filter(Boolean).join('/');

  // Walk + read as one unit. When a whole folder is dehydrated the DIRECTORY is
  // missing too, not just the file, so retrying only the file handle would never
  // recover — the retry has to redo the walk.
  const readLocal = async () => {
    const root = await navigator.storage.getDirectory();
    let dir = root;
    for (const p of parts) { if (!p) continue; dir = await dir.getDirectoryHandle(p); }
    return await (await dir.getFileHandle(fileName)).getFile();
  };

  try {
    if (request.method === 'PUT') {
      const root = await navigator.storage.getDirectory();
      let dir = root;
      for (const p of parts) { if (!p) continue; dir = await dir.getDirectoryHandle(p, { create: true }); }
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
    let blob;
    try { blob = await readLocal(); }
    catch (_) {
      // Not local — it may simply be dehydrated. hydrateRel() consults the cloud
      // index first, so a file that genuinely doesn't exist costs no network.
      if (!(await askClientToHydrate(decodedRel))) throw new Error('not found');
      blob = await readLocal();
    }
    return new Response(blob, {
      headers: {
        'Content-Type': contentType(fileName),
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
