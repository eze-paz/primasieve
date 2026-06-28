const http = require('http');
const fs = require('fs');
const path = require('path');
const PORT = process.env.PORT || 8765;
const ROOT = path.resolve(__dirname, '..');
const MIME = {
  '.html':  'text/html',
  '.js':    'application/javascript',
  '.mjs':   'application/javascript',
  '.css':   'text/css',
  '.json':  'application/json',
  '.svg':   'image/svg+xml',
  '.png':   'image/png',
  '.ico':   'image/x-icon',
};

const API_STUBS = {
  '/auth/me':           {},
  '/auth/token':        {},
  '/config':            {},
  '/config/public':     {},
  '/sync/state':        {},
};

const server = http.createServer((req, res) => {
  let rel = decodeURIComponent(req.url.split('?')[0]);

  if (API_STUBS[rel]) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify(API_STUBS[rel]));
  }

  if (rel === '/') rel = '/sandpie.html';

  const file = path.join(ROOT, rel);
  if (!file.startsWith(ROOT)) { res.writeHead(403); return res.end('Forbidden'); }
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end('Not found'); }

  const ext = path.extname(file);
  res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});

server.listen(PORT, () => console.log('[server] http://localhost:' + PORT));
