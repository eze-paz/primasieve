#!/usr/bin/env node
// Node.js drop-in replacement for serve.py. The python version used
// http.server.HTTPServer, which is single-threaded: every request blocks
// the next one. SSE proxies hold their TCP connection open for the entire
// LLM completion, so two parallel browser streams ended up serializing
// (one waiting in accept() while the other streams). Node's HTTP stack
// is non-blocking by design — concurrent connections share the event
// loop, and `req.pipe(upstreamReq)` / `upstreamRes.pipe(res)` handle
// backpressure natively, so N parallel SSE streams interleave naturally.
//
// Feature parity with serve.py:
//   - GET/POST /proxy/<host>/<rest>     → forwards to https://<host>/<rest>
//   - POST /shell                       → spawn shell command (ssh-key-gated)
//   - POST /shell/challenge             → issue nonce for shell auth
//   - OPTIONS                           → CORS preflight (204)
//   - static file serving fallback      → serves /opt/sandpie/\*.html etc.
//   - bootstrap fetch of sandpie.html   → for local-dev mode
//   - env vars: SANDPIE_NO_SHELL, SANDPIE_RESTRICT_PROXY, SANDPIE_BOOTSTRAP,
//               SANDPIE_URL
//   - same proxy.log format
//
// Drop-in for systemd: change ExecStart to `/usr/bin/node /opt/sandpie/serve.js`.

 

const http   = require('http');
const https  = require('https');
const fs     = require('fs');
const path   = require('path');
const url    = require('url');
const crypto = require('crypto');
const os     = require('os');
const { spawn } = require('child_process');

 

const PORT = 8080;
const HOST = '127.0.0.1';
const SHELL_CWD = __dirname;
const SHELL_TIMEOUT_MAX = 120;
const ALLOWED_ORIGINS = new Set([
  'http://localhost:8080',
  'http://127.0.0.1:8080',
  'https://gasn2cloud.com',
]);
const SHELL_ENABLED  = process.env.SANDPIE_NO_SHELL       !== '1';
const RESTRICT_PROXY = process.env.SANDPIE_RESTRICT_PROXY === '1';
const SANDPIE_URL    = process.env.SANDPIE_URL || 'https://gasn2cloud.com/sdk/sandpie.html';

 

// Hop-by-hop + routing headers stripped on forward. accept-encoding is
// included so upstream returns identity-encoded bodies (we don't forward
// Content-Encoding back, so otherwise the browser would see gzipped bytes
// tagged as plain JSON and fail to parse).
const SKIP = new Set([
  'host', 'content-length', 'connection', 'keep-alive',
  'proxy-authenticate', 'proxy-authorization', 'te', 'trailers',
  'transfer-encoding', 'upgrade', 'cookie', 'accept-encoding',
]);

 

const LOG_PATH = path.join(__dirname, 'proxy.log');
function logLine(s) {
  try { fs.appendFileSync(LOG_PATH, s + '\n', 'utf8'); } catch {}
}

 

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': '*',
};

 

function handleProxy(req, res) {
  if (RESTRICT_PROXY) {
    const origin = req.headers.origin;
    // Allow when Origin is absent (non-browser clients). Reject only when
    // present and not in our allowlist.
    if (origin && !ALLOWED_ORIGINS.has(origin)) {
      res.writeHead(403, { 'Content-Type': 'text/plain', 'Access-Control-Allow-Origin': '*' });
      return res.end(`Origin not allowed: ${origin}`);
    }
  }
  // /proxy/<host>[/<rest>]?<query>  →  https://<host>/<rest>?<query>
  const rest   = req.url.slice('/proxy/'.length);
  const target = url.parse('https://' + rest);
  const targetPath = (target.path || '/');

 

  // Forward headers preserving case (Node lowercases on req.headers, but
  // most upstreams are case-insensitive so this is fine in practice).
  const fwdHeaders = {};
  for (const k of Object.keys(req.headers)) {
    if (!SKIP.has(k.toLowerCase())) fwdHeaders[k] = req.headers[k];
  }
  fwdHeaders['host'] = target.host;

 

  let entry = `[proxy] ${req.method} ${target.host}${targetPath}\n`;
  for (const [k, v] of Object.entries(fwdHeaders)) {
    const s = (typeof v === 'string' && v.length >= 80) ? v.slice(0, 77) + '...' : v;
    entry += `        ${k}: ${s}\n`;
  }
  logLine(entry.trimEnd());

 

  const upstream = https.request({
    hostname: target.hostname,
    port: target.port || 443,
    path: targetPath,
    method: req.method,
    headers: fwdHeaders,
    timeout: 120000,
  }, upstreamRes => {
    // Mirror serve.py: only forward status + Content-Type, add permissive
    // CORS. We deliberately drop Content-Length (upstream may chunk), and
    // Content-Encoding (we asked for identity by stripping accept-encoding).
    res.writeHead(upstreamRes.statusCode, {
      'Access-Control-Allow-Origin': '*',
      'Content-Type': upstreamRes.headers['content-type'] || 'application/octet-stream',
    });
    upstreamRes.pipe(res);
  });
  upstream.on('error', err => {
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'text/plain', 'Access-Control-Allow-Origin': '*' });
    }
    res.end('upstream error: ' + err.message);
  });
  upstream.on('timeout', () => upstream.destroy(new Error('upstream timeout')));
  // Pipe request body (POST) without buffering — supports large uploads
  // and matches the original semantics for chunked request bodies.
  req.pipe(upstream);
}

 

function jsonReply(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
    'Access-Control-Allow-Origin': '*',
  });
  res.end(body);
}

 

// ---------------------------------------------------------------------------
// SSH key challenge-response auth for /shell
//
// Flow:
//   1. POST /shell/challenge  → server returns { nonce, ts }
//   2. client signs "nonce:ts:cmd" with SSH private key
//   3. POST /shell { cmd, nonce, ts, pubkey, sig }
//      server checks: pubkey in authorized_keys, sig valid, nonce unused & fresh
//
// Only ssh-ed25519 keys are supported (covers the vast majority of modern
// OpenSSH deployments; RSA can be added later if needed).
// ---------------------------------------------------------------------------

 

const _nonces = new Map();  // nonce -> expiry (unix seconds)
const NONCE_TTL = 60;       // nonce valid for 60 s
const TS_WINDOW = 30;       // clock skew tolerance

 

function _cleanNonces() {
  const now = Math.floor(Date.now() / 1000);
  for (const [n, exp] of _nonces) if (exp < now) _nonces.delete(n);
}

 

// Parse an authorized_keys line (ssh-ed25519 <b64> [comment]) into a
// Node CryptoKey by building the SubjectPublicKeyInfo DER by hand.
// Wire format: [4 len][11 "ssh-ed25519"][4 len][32 key bytes]
// SPKI DER:    30 2a 30 05 06 03 2b 65 70 03 21 00 <32 bytes>
function _parseEd25519Line(line) {
  const parts = line.trim().split(/\s+/);
  if (parts.length < 2 || parts[0] !== 'ssh-ed25519') return null;
  let raw;
  try { raw = Buffer.from(parts[1], 'base64'); } catch { return null; }

 

  let off = 0;
  const nameLen = raw.readUInt32BE(off); off += 4;
  if (raw.slice(off, off + nameLen).toString() !== 'ssh-ed25519') return null;
  off += nameLen;
  const keyLen = raw.readUInt32BE(off); off += 4;
  const keyBytes = raw.slice(off, off + keyLen);
  if (keyBytes.length !== 32) return null;

 

  // 30 2a = SEQUENCE(42), 30 05 06 03 2b 65 70 = AlgorithmIdentifier(Ed25519),
  // 03 21 00 = BIT STRING(33 bytes, 0 padding bits)
  const spki = Buffer.concat([
    Buffer.from('302a300506032b6570032100', 'hex'),
    keyBytes,
  ]);
  try {
    return crypto.createPublicKey({ key: spki, format: 'der', type: 'spki' });
  } catch { return null; }
}

 

// Return a Node CryptoKey if clientKeyLine exactly matches a line in
// ~/.ssh/authorized_keys, null otherwise.
function _findAuthorizedKey(clientKeyLine) {
  const cp = clientKeyLine.trim().split(/\s+/);
  if (cp.length < 2) return null;
  let content;
  try {
    content = fs.readFileSync(
      path.join(os.homedir(), '.ssh', 'authorized_keys'), 'utf8');
  } catch { return null; }

 

  for (const line of content.split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const ap = t.split(/\s+/);
    // Match on key type + base64 blob only (ignore comment field).
    if (ap.length >= 2 && ap[0] === cp[0] && ap[1] === cp[1])
      return _parseEd25519Line(t);
  }
  return null;
}

 

function handleChallenge(req, res) {
  _cleanNonces();
  const nonce = crypto.randomBytes(16).toString('hex');
  const ts    = Math.floor(Date.now() / 1000);
  _nonces.set(nonce, ts + NONCE_TTL);
  logLine(`[shell/challenge] nonce issued`);
  jsonReply(res, 200, { nonce, ts });
}

 

function handleShell(req, res) {
  _cleanNonces();
  let buf = '';
  req.setEncoding('utf8');
  req.on('data', c => { buf += c; });
  req.on('end', () => {
    let parsed;
    try { parsed = JSON.parse(buf || '{}'); }
    catch (e) { return jsonReply(res, 400, { error: 'bad json: ' + e.message }); }

 

    // --- auth ---
    const { cmd, nonce, ts, pubkey, sig } = parsed;
    if (!nonce || ts == null || !pubkey || !sig)
      return jsonReply(res, 401, { error: 'missing auth fields: nonce, ts, pubkey, sig' });

 

    const now = Math.floor(Date.now() / 1000);
    if (Math.abs(now - ts) > TS_WINDOW)
      return jsonReply(res, 401, { error: 'timestamp out of window' });

 

    if (!_nonces.has(nonce))
      return jsonReply(res, 401, { error: 'unknown or expired nonce' });
    _nonces.delete(nonce);  // single-use: consume immediately

 

    const pubKey = _findAuthorizedKey(pubkey);
    if (!pubKey)
      return jsonReply(res, 403, { error: 'public key not in authorized_keys' });

 

    let sigBuf;
    try { sigBuf = Buffer.from(sig, 'base64'); }
    catch { return jsonReply(res, 400, { error: 'bad sig encoding' }); }

 

    // Message binds nonce + ts + cmd so a MITM cannot swap the command after signing.
    const message = Buffer.from(`${nonce}:${ts}:${(cmd || '').trim()}`);
    let ok;
    try { ok = crypto.verify(null, message, pubKey, sigBuf); }
    catch (e) { return jsonReply(res, 400, { error: 'verify error: ' + e.message }); }
    if (!ok) return jsonReply(res, 403, { error: 'invalid signature' });

 

    // --- exec ---
    const safeCmd = (cmd || '').trim();
    if (!safeCmd) return jsonReply(res, 400, { error: 'missing cmd' });
    const cwd = parsed.cwd || SHELL_CWD;
    const timeoutSec = Math.min(parseInt(parsed.timeout, 10) || 30, SHELL_TIMEOUT_MAX);
    logLine(`[shell] ${JSON.stringify(safeCmd)} (cwd=${cwd}, timeout=${timeoutSec})`);

 

    let stdout = '', stderr = '';
    let timedOut = false;
    const proc = spawn(safeCmd, { shell: true, cwd });
    const timer = setTimeout(() => { timedOut = true; proc.kill('SIGKILL'); }, timeoutSec * 1000);
    proc.stdout.on('data', d => { stdout += d.toString('utf8'); });
    proc.stderr.on('data', d => { stderr += d.toString('utf8'); });
    proc.on('error', e => {
      clearTimeout(timer);
      jsonReply(res, 500, { error: String(e && e.message || e) });
    });
    proc.on('close', code => {
      clearTimeout(timer);
      if (timedOut) {
        jsonReply(res, 200, { stdout: '', stderr: `(timeout after ${timeoutSec}s)`, code: -1, cwd });
      } else {
        jsonReply(res, 200, { stdout, stderr, code, cwd });
      }
    });
  });
}

 

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.txt':  'text/plain; charset=utf-8',
  '.wasm': 'application/wasm',
};

 

function serveStatic(req, res) {
  // Strip query and decode percent-encoding before path-traversal check.
  const reqPath = decodeURIComponent(req.url.split('?')[0]);
  const safe = path.normalize(reqPath).replace(/^[\\/]+/, '');
  let filePath = path.join(__dirname, safe || '.');
  if (!filePath.startsWith(__dirname)) {
    res.writeHead(403); return res.end('forbidden');
  }
  fs.stat(filePath, (err, stat) => {
    if (err) { res.writeHead(404); return res.end('not found'); }
    if (stat.isDirectory()) filePath = path.join(filePath, 'index.html');
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    fs.createReadStream(filePath)
      .on('error', () => { try { res.end(); } catch {} })
      .pipe(res);
  });
}

 

const server = http.createServer((req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS_HEADERS);
    return res.end();
  }
  if (req.url.startsWith('/proxy/')) {
    return handleProxy(req, res);
  }
  if (req.method === 'POST' && req.url === '/shell/challenge') {
    if (!SHELL_ENABLED) { res.writeHead(404); return res.end(); }
    return handleChallenge(req, res);
  }
  if (req.method === 'POST' && req.url === '/shell') {
    if (!SHELL_ENABLED) { res.writeHead(404); return res.end(); }
    return handleShell(req, res);
  }
  if (req.method === 'GET') {
    return serveStatic(req, res);
  }
  res.writeHead(404); res.end();
});

 

// Keep idle connections open long enough that SSE clients reconnecting on
// brief network blips don't pay a full TLS handshake every time.
server.keepAliveTimeout = 60000;
server.headersTimeout   = 65000;

 

// Bootstrap: if sandpie.html isn't alongside us and the user hasn't opted
// out, fetch it from the public deployment so this script works standalone
// in local-dev mode. Cloud setups set SANDPIE_BOOTSTRAP=0 because Apache
// serves the page from htdocs directly. Strictly best-effort: failure
// here doesn't block the server.
function bootstrap(then) {
  if (process.env.SANDPIE_BOOTSTRAP === '0') return then();
  const localPath = path.join(__dirname, 'sandpie.html');
  fs.access(localPath, fs.constants.F_OK, err => {
    if (!err) return then();
    console.log(`Bootstrap: fetching ${SANDPIE_URL}`);
    https.get(SANDPIE_URL, r => {
      if (r.statusCode !== 200) {
        console.log(`  bootstrap failed: HTTP ${r.statusCode}`);
        r.resume();
        return then();
      }
      const out = fs.createWriteStream(localPath);
      r.pipe(out);
      out.on('finish', () => { console.log('  → saved sandpie.html'); then(); });
      out.on('error', e => { console.log('  bootstrap save failed:', e.message); then(); });
    }).on('error', e => { console.log('  bootstrap failed:', e.message); then(); });
  });
}

 

bootstrap(() => {
  server.listen(PORT, HOST, () => {
    console.log(`Serving at http://localhost:${PORT}  (shell cwd: ${SHELL_CWD}, shell=${SHELL_ENABLED ? 'on' : 'off'}, restrictProxy=${RESTRICT_PROXY ? 'on' : 'off'})`);
  });
});
