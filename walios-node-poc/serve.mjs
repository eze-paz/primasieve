// Static server for the sandpie repo root with cross-origin isolation.
// SharedArrayBuffer -- and therefore the whole walios kernel -- requires COOP/COEP.
//   node walios-node-poc/serve.mjs   ->  http://localhost:8788/walios-node-poc/
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, extname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const PORT = Number(process.env.PORT || 8788);

const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.json': 'application/json', '.wasm': 'application/wasm', '.css': 'text/css',
  '.tar': 'application/x-tar', '.gz': 'application/gzip', '.py': 'text/plain',
  '.map': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
};

createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  let p = join(ROOT, normalize(url).replace(/^(\.\.[\\/])+/, ''));
  try {
    const s = await stat(p).catch(() => null);
    if (s && s.isDirectory()) p = join(p, 'index.html');
    const body = await readFile(p);
    res.writeHead(200, {
      'Content-Type': TYPES[extname(p)] || 'application/octet-stream',
      // the two headers the whole thing depends on
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'Cross-Origin-Resource-Policy': 'same-origin',
      // node-lib.json is ~4MB and every `node` invocation is a fresh worker that
      // fetches it. Under no-store an 8-command demo refetches 32MB.
      'Cache-Control': /node-lib\.json$/.test(p) ? 'public, max-age=300' : 'no-store',
    });
    res.end(body);
  } catch (e) {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('404 ' + url + '\n');
  }
}).listen(PORT, () => {
  console.log('serving ' + ROOT);
  console.log('  http://localhost:' + PORT + '/walios-node-poc/');
});
