// End-to-end test: `tlswrap -L LOCALPORT HOST 443` actually proxies, same call and later.
//
// This is the workflow the run_walios description tells the model to use -- "for TLS on a
// raw socket run `tlswrap -L LOCALPORT HOST 443` and talk to 127.0.0.1:LOCALPORT" -- and it
// could not work, in two separate ways.
//
//  1. Nothing could bind. listen() handed the port to the WISP relay, but WISP is an
//     OUTBOUND transport, so the relay refused and the guest saw "Address in use" on every
//     port. Fixed by serving loopback listeners inside the kernel (see e2e-loopback.mjs).
//
//  2. The SHIPPED tlswrap.wasm then bound and printed its banner, and hung on every
//     proxied request. It had no source in any repo or on the build box -- only a 93KB
//     .wasm -- so there was nothing to debug. A proxy of the identical shape written in
//     python and run in the same guest worked first time (accept -> TLS connect -> select
//     pump -> 828 bytes of "HTTP/1.1 200 OK" back to nc), which placed the fault inside
//     that binary rather than in the kernel. It was replaced by
//     sandpie-server walios/src/tlswrap.c, built by scripts/build-tlswrap-wali.sh.
//
// The replacement does not implement TLS: it marks the outbound socket with the private
// setsockopt level the kernel reads before connect, and the relay terminates TLS. Same
// mechanism openssl-shim.c uses. The relay therefore sees plaintext, which is the
// documented walios model -- clients wanting end-to-end TLS link libssl themselves.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING pkgcache/tlswrap.wasm, ../sandpie-server
// for wisp.js, playwright, and OUTBOUND network (the relay must reach example.com:443).
// Run: node tests/walios/e2e-tlswrap.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'pkgcache/tlswrap.wasm'];
const missing = ASSETS.filter(a => !fs.existsSync(path.join(repoRoot, 'walios', a)));
if (missing.length) { console.log('SKIP: walios assets missing - ' + missing.join(', ')); process.exit(0); }
if (!fs.existsSync(path.join(serverRepo, 'wisp.js'))) { console.log('SKIP: ../sandpie-server/wisp.js not found'); process.exit(0); }

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch (_) { console.log('SKIP: playwright not installed'); process.exit(0); }

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n        ' + String(detail).replace(/\n/g, '\n        ') : '')); }
};

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.wasm': 'application/wasm', '.gz': 'application/gzip', '.pem': 'text/plain' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'sandpie.html';
  const file = path.join(repoRoot, rel);
  if (!file.startsWith(repoRoot) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end('nf'); return; }
  res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream',
    'cross-origin-opener-policy': 'same-origin', 'cross-origin-embedder-policy': 'require-corp',
    'cross-origin-resource-policy': 'cross-origin', 'cache-control': 'no-store' });
  fs.createReadStream(file).pipe(res);
});
process.env.WISP_ENABLED = '1';
process.env.WISP_ALLOW_HOSTS = '*';
process.env.WISP_ALLOW_PORTS = '80,443';
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

// base64 rather than printf/heredocs: an HTTP request is nothing but CRLF escapes and
// quotes, and pushing those through JSON, a shell and printf is how earlier versions of
// this test silently sent a malformed request instead of failing.
const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const REQ = b64('GET / HTTP/1.0\r\nHost: example.com\r\n\r\n');

const START = [
  'rm -f /tmp/tw.log /tmp/tw1',
  'echo ' + REQ + ' | base64 -d > /tmp/req.txt',
  'tlswrap -L 9443 example.com 443 > /tmp/tw.log 2>&1 &',
  'sleep 3',
  'echo "banner=$(head -1 /tmp/tw.log)"',
  'timeout 30 nc 127.0.0.1 9443 < /tmp/req.txt > /tmp/tw1 2>&1',
  'echo "same_call=$(head -1 /tmp/tw1) bytes=$(wc -c < /tmp/tw1)"',
].join('\n');

// The daemon half: the tunnel must still be serving in a LATER call. That is the use the
// tool documents, and the reason a backgrounded process is allowed to outlive its call.
const REUSE = [
  'rm -f /tmp/tw2',
  'timeout 30 nc 127.0.0.1 9443 < /tmp/req.txt > /tmp/tw2 2>&1',
  'echo "next_call=$(head -1 /tmp/tw2) bytes=$(wc -c < /tmp/tw2)"',
].join('\n');

// CONTROLS. Without these, "it returned something" would pass on a tlswrap that answered
// every port and never reported a failure -- which is close to what the old one did.
const CONTROLS = [
  'echo "=== bad usage must be LOUD, not a hang:"',
  'tlswrap > /tmp/u.log 2>&1; echo "usage_rc=$?"',
  'echo "usage_said=$(grep -c usage /tmp/u.log)"',
  'echo "=== an unresolvable upstream must be reported, not silently empty:"',
  'rm -f /tmp/bad.log',
  'tlswrap -L 9444 no-such-host-xyz.invalid 443 > /tmp/bad.log 2>&1 &',
  'sleep 2',
  'timeout 20 nc 127.0.0.1 9444 < /tmp/req.txt > /dev/null 2>&1',
  'sleep 1',
  'echo "bad_reported=$(grep -c "upstream closed without a single byte" /tmp/bad.log)"',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const call = (args) => page.evaluate(async (args) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), 200000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args });
    });
  }, args);

  const a = await call({ timeout: 120, script: START });
  console.log('    ' + String(a).replace(/\n/g, '\n    '));
  check('tlswrap binds and announces the tunnel', /banner=tlswrap: 127\.0\.0\.1:9443 -> TLS example\.com:443/.test(a), a);
  check('a request through the tunnel returns a real HTTP response', /same_call=HTTP\/1\.[01] 200/.test(a), a);
  check('and a non-trivial body came back', /bytes=[1-9]\d{2,}/.test(a), a);

  const b = await call({ timeout: 120, script: REUSE });
  console.log('    ' + String(b).replace(/\n/g, '\n    '));
  check('the SAME tunnel still serves from a LATER call', /next_call=HTTP\/1\.[01] 200/.test(b), b);

  const c = await call({ timeout: 120, script: CONTROLS });
  console.log('    ' + String(c).replace(/\n/g, '\n    '));
  check('CONTROL: bad usage prints usage and exits non-zero', /usage_rc=[1-9]/.test(c) && /usage_said=[1-9]/.test(c), c);
  check('CONTROL: an unreachable upstream is REPORTED, not silently empty', /bad_reported=[1-9]/.test(c), c);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
