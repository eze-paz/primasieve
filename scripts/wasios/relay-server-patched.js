#!/usr/bin/env node
// sandpie-local-ssh-relay  —  PATCHED with crash containment (2026-08-15)
// Fix: the original relay had NO crash containment: any aborted request body,
// client disconnect mid-response, or PTY error crashed the whole process
// silently (unhandled rejection / uncaught exception), which is why it kept
// "flapping" and needed manual restarts. This version logs and survives.
//
// Env: PORT (8765), HOST (127.0.0.1), SANDPIE_SSH_KEY (optional API key)

const http = require('http');
const url = require('url');
const WebSocket = require('ws');
const { sshHandler, sftpExec, acquire, release } = require('./ssh');
const { shellExecHandler, wsPtyHandler, fileReadHandler, fileWriteHandler, fileListHandler } = require('./shell');

// ── Crash containment: log and KEEP RUNNING. A single broken request must
//    never take down the relay (default Node behaviour for unhandled
//    rejections since v15 is to crash the process). ─────────────────────────
process.on('uncaughtException', (e) => {
  console.error('[guard] uncaughtException:', e && (e.stack || e.message) || e);
});
process.on('unhandledRejection', (e) => {
  console.error('[guard] unhandledRejection:', e && (e.stack || e.message) || e);
});

const PORT = Number(process.env.PORT) || 8765;
const HOST = process.env.HOST || '127.0.0.1';
const API_KEY = process.env.SANDPIE_SSH_KEY || '';

if (HOST === '0.0.0.0' && !API_KEY) {
  console.warn('');
  console.warn('  /!\\  WARNING: Binding to 0.0.0.0 without SANDPIE_SSH_KEY');
  console.warn('        Anyone on your network can run commands and open');
  console.warn('        shells on this machine. Set SANDPIE_SSH_KEY for');
  console.warn('        basic auth.');
  console.warn('');
}

function setCORS(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
}

// Swallow client-disconnect errors on the response: the browser aborting a
// fetch (tool timeout, page nav, reload) must NOT crash the relay via an
// unhandled 'error' event on the ServerResponse (EPIPE/ECONNRESET).
function safeRes(res) {
  res.on('error', () => {});
  return res;
}

function jsonReply(res, status, obj) {
  setCORS(res);
  safeRes(res).writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function textReply(res, status, text) {
  setCORS(res);
  safeRes(res).writeHead(status, { 'Content-Type': 'text/plain' });
  res.end(text);
}

function checkAuth(req) {
  if (!API_KEY) return true;
  const key = req.headers['x-sandpie-api-key'] || '';
  return key === API_KEY;
}

// Minimal JSON body parser — stream errors (client abort) become a normal
// thrown Error that the caller catches, NOT an unhandled rejection.
async function readBody(req, maxBytes = 2 * 1024 * 1024) {
  const chunks = [];
  let len = 0;
  try {
    for await (const chunk of req) {
      len += chunk.length;
      if (len > maxBytes) throw new Error('body too large');
      chunks.push(chunk);
    }
  } catch (e) {
    if (e && e.message === 'body too large') throw e;
    throw new Error('readBody stream error: ' + (e && e.message || e));
  }
  const buf = Buffer.concat(chunks);
  if (!buf.length) return {};
  try { return JSON.parse(buf.toString('utf8')); } catch (_) { return {}; }
}

// Read the body with the failure contained: an aborted body returns an error
// response instead of killing the process.
async function readBodySafe(req, res, maxBytes) {
  try {
    return await readBody(req, maxBytes);
  } catch (e) {
    jsonReply(res, 400, { error: 'bad request body: ' + e.message });
    return null;
  }
}

const server = http.createServer(async (req, res) => {
  setCORS(res);
  safeRes(res);

  // Preflight for CORS
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const pathname = url.parse(req.url).pathname;

  // Healthcheck
  if (req.method === 'GET' && pathname === '/health') {
    return textReply(res, 200, 'ok');
  }

  // SSH exec
  if (req.method === 'POST' && pathname === '/ssh/exec') {
    if (!checkAuth(req)) {
      return jsonReply(res, 403, { error: 'invalid or missing X-Sandpie-Api-Key' });
    }
    const body = await readBodySafe(req, res, 512 * 1024);
    if (body === null) return;
    const fauxReq = { body, headers: req.headers };
    const fauxRes = {
      statusCode: 200,
      status(n) { this.statusCode = n; return this; },
      json(obj) { jsonReply(res, this.statusCode, obj); },
      end(s) { textReply(res, this.statusCode, s || ''); },
    };
    try {
      await sshHandler(fauxReq, fauxRes);
    } catch (e) {
      console.error('[server] sshHandler threw:', e.message);
      jsonReply(res, 500, { error: 'relay internal error: ' + e.message });
    }
    return;
  }

  // Local shell exec (one-shot, spawns PTY directly — no SSH key involved)
  if (req.method === 'POST' && pathname === '/shell/exec') {
    if (!checkAuth(req)) {
      return jsonReply(res, 403, { error: 'invalid or missing X-Sandpie-Api-Key' });
    }
    const body = await readBodySafe(req, res, 2 * 1024 * 1024);
    if (body === null) return;
    const fauxReq = { body, headers: req.headers };
    const fauxRes = {
      statusCode: 200,
      status(n) { this.statusCode = n; return this; },
      json(obj) { jsonReply(res, this.statusCode, obj); },
      end(s) { textReply(res, this.statusCode, s || ''); },
    };
    try {
      await shellExecHandler(fauxReq, fauxRes);
    } catch (e) {
      console.error('[server] shellExecHandler threw:', e.message);
      jsonReply(res, 500, { error: 'shell exec error: ' + e.message });
    }
    return;
  }

  // SFTP operations (get/put/ls/rm/mkdir via ssh2 SFTP channel)
  if (req.method === 'POST' && pathname === '/ssh/sftp') {
    if (!checkAuth(req)) {
      return jsonReply(res, 403, { error: 'invalid or missing X-Sandpie-Api-Key' });
    }
    const body = await readBodySafe(req, res, 100 * 1024 * 1024);
    if (body === null) return;
    const { host, username, action, remote, data, privateKey, passphrase, password, port } = body;
    if (!host || !username || !action || !remote) {
      return jsonReply(res, 400, { error: 'host, username, action, remote are required' });
    }
    if (!privateKey && !password) {
      return jsonReply(res, 400, { error: 'privateKey or password required' });
    }
    if (!acquire()) {
      return jsonReply(res, 429, { error: `too many concurrent ssh connections (max 8)` });
    }
    const t0 = Date.now();
    try {
      const r = await sftpExec({ host, port, username, action, remote,
                                  data: data ? Buffer.from(data, 'base64') : undefined,
                                  privateKey, passphrase, password });
      console.log(`[sftp] ${action} ${remote} on ${host} ms=${Date.now() - t0}`);
      if (action === 'get') {
        res.writeHead(200, {
          'Content-Type': 'application/octet-stream',
          'Content-Length': r.size,
          'X-Sandpie-Fingerprint': r.fingerprint || '',
        });
        res.end(r.buffer);
      } else {
        jsonReply(res, 200, { ...r, fingerprint: r.fingerprint });
      }
    } catch (e) {
      console.log(`[sftp] ERROR ${action} ${remote}: ${e.message}`);
      jsonReply(res, 502, { error: e.message });
    } finally {
      release();
    }
    return;
  }

  // Local file operations (direct fs — no SSH, no shell spawning)
  if (req.method === 'POST' && pathname.startsWith('/shell/file/')) {
    if (!checkAuth(req)) {
      return jsonReply(res, 403, { error: 'invalid or missing X-Sandpie-Api-Key' });
    }
    const body = await readBodySafe(req, res, 100 * 1024 * 1024);
    if (body === null) return;
    const fauxReq = { body, headers: req.headers };
    try {
      if (pathname === '/shell/file/read') await fileReadHandler(fauxReq, res);
      else if (pathname === '/shell/file/write') await fileWriteHandler(fauxReq, res);
      else if (pathname === '/shell/file/ls') await fileListHandler(fauxReq, res);
      else jsonReply(res, 404, { error: 'unknown file action' });
    } catch (e) {
      console.error('[server] fileHandler threw:', e.message);
      jsonReply(res, 500, { error: 'file handler error: ' + e.message });
    }
    return;
  }

  textReply(res, 404, 'not found');
});

// ── WebSocket PTY ────────────────────────────────────────────────────────────
const wss = new WebSocket.Server({ noServer: true, path: '/shell/pty' });

wss.on('connection', (ws, req) => {
  console.log('[ws] PTY client connected');
  try {
    wsPtyHandler(ws, req);
  } catch (e) {
    console.error('[ws] pty handler threw:', e && (e.stack || e.message) || e);
    try { ws.close(); } catch (_) {}
  }
});

server.on('upgrade', (request, socket, head) => {
  const pathname = url.parse(request.url).pathname;
  if (pathname === '/shell/pty') {
    const origin = request.headers.origin || '';
    const allowed = [
      /^http:\/\/localhost(:\d+)?$/,
      /^https:\/\/sandpie\.app/,
      /^https:\/\/.*\.gasn2\.com/,
    ];
    const ok = !origin || allowed.some(r => r.test(origin));
    if (!ok) {
      console.warn('[ws] Rejected connection from origin:', origin);
      socket.write('HTTP/1.1 403 Forbidden\r\n\r\n');
      socket.destroy();
      return;
    }
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, request);
    });
  } else {
    socket.destroy();
  }
});

server.listen(PORT, HOST, () => {
  console.log(`[*] sandpie-local-ssh-relay (patched, crash-contained) listening on http://${HOST}:${PORT}`);
  console.log(`    SSH relay   → http://${HOST}:${PORT}/ssh/exec   (remote machines)`);
  console.log(`    Shell exec  → http://${HOST}:${PORT}/shell/exec  (local machine)`);
  console.log(`    File read   → http://${HOST}:${PORT}/shell/file/read  (local fs)`);
  console.log(`    File write  → http://${HOST}:${PORT}/shell/file/write (local fs)`);
  console.log(`    File list   → http://${HOST}:${PORT}/shell/file/ls   (local fs)`);
  console.log(`    PTY socket  → ws://${HOST}:${PORT}/shell/pty     (interactive terminal)`);
  if (API_KEY) console.log('    API key is required (SANDPIE_SSH_KEY set)');
});
