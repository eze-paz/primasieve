// End-to-end test: `wget https://...` inside walios, in a REAL browser.
//
// This is the test that would have caught the bug it was written for. busybox was built
// without CONFIG_FEATURE_WGET_OPENSSL, so its wget did not know the https scheme and died
// in parse_url ("not an http or ftp url") before opening a socket. build-pkg's wfetch was
// that wget, so EVERY APKBUILD fetch failed instantly and was misreported as "no APKBUILD
// for <pkg>" -- `build-pkg jq` looked like a missing package for as long as that stood.
//
// Nothing is mocked: the real page, the real modules/sandpie-worker.js walios host, the
// real kernel workers, the real busybox.wasm, and the real WISP relay (sandpie-server's
// wisp.js) terminating TLS. Static files and the relay are served from ONE origin because
// sandpie-worker.js points the bridge at ws://<location.host>/wisp.
//
// REQUIREMENTS: walios runtime assets in walios/ at the repo root (gitignored, ~22MB):
//   scp sandpie:/opt/sandpie-server/walios/{wali-worker.js,wali-proc-worker.js,\
//   opfs-worker.js,wisp-worker.js,busybox.wasm,rootfs.tar.gz,aports-catalog.json} walios/
//   scp sandpie:/opt/sandpie-server/walios/pkgcache/{index.json,openssl.wasm,curl.wasm,\
//   tlswrap.wasm} walios/pkgcache/
//   scp sandpie:/opt/sandpie-server/walios/bin/{cc,wfetch,wextract,build-pkg} walios/bin/
// ...plus ../sandpie-server checked out next to this repo (for wisp.js), and playwright.
// Skips (exit 0) with a clear message when anything is missing.
//
// Run: node tests/walios/e2e-wget-https.mjs [--headed]
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');
// Port 0: let the OS pick. Fixed ports collide with Windows/Hyper-V reserved
// ranges (netsh excludedportrange), which fails as a bare EADDRINUSE.
const HEADED = process.argv.includes('--headed');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'pkgcache/index.json', 'pkgcache/openssl.wasm',
  'pkgcache/curl.wasm', 'bin/wfetch'];
const missing = ASSETS.filter(a => !fs.existsSync(path.join(repoRoot, 'walios', a)));
if (missing.length) { console.log('SKIP: walios assets missing - ' + missing.join(', ')); process.exit(0); }
if (!fs.existsSync(path.join(serverRepo, 'wisp.js'))) { console.log('SKIP: ../sandpie-server/wisp.js not found (needed for the relay)'); process.exit(0); }

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch (_) { console.log('SKIP: playwright not installed (npm i -g playwright && npx playwright install chromium)'); process.exit(0); }

let attachWisp;
try { ({ attachWisp } = require(path.join(serverRepo, 'wisp.js'))); }
catch (e) { console.log('SKIP: could not load wisp.js - ' + e.message); process.exit(0); }

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n        ' + String(detail).replace(/\n/g, '\n        ') : '')); }
};

// -- one origin: COOP/COEP static files + the real relay at /wisp ------------
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.wasm': 'application/wasm', '.gz': 'application/gzip', '.pem': 'text/plain' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'sandpie.html';
  const file = path.join(repoRoot, rel);
  if (!file.startsWith(repoRoot) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); res.end('not found'); return;
  }
  res.writeHead(200, {
    'content-type': MIME[path.extname(file)] || 'application/octet-stream',
    // walios needs SharedArrayBuffer -> cross-origin isolation.
    'cross-origin-opener-policy': 'same-origin',
    'cross-origin-embedder-policy': 'require-corp',
    'cross-origin-resource-policy': 'cross-origin',
    'cache-control': 'no-store',
  });
  fs.createReadStream(file).pipe(res);
});
process.env.WISP_ENABLED = '1';                       // the relay is off unless asked for
// The relay's default allow-list is 'alpinelinux.org' only -- every other host is
// denied and the guest sees a bare "Send failure: Broken pipe". This is a local,
// loopback-only test relay, so open it up; production keeps its own narrower list.
process.env.WISP_ALLOW_HOSTS = '*';
process.env.WISP_ALLOW_PORTS = '80,443';                       // the relay is off unless asked for
attachWisp(server, { log: () => {}, warn: (...a) => console.log('  [wisp]', ...a), error: (...a) => console.log('  [wisp]', ...a) });

const GUEST_C = [
  '#include <openssl/ssl.h>',
  '#include <stdio.h>',
  'int main(void){ SSL_CTX *c = SSL_CTX_new(TLS_client_method());',
  '  printf("ctx=%s\\n", c ? "ok" : "null"); return c ? 0 : 1; }',
].join('\n');

let browser;
try {
  await new Promise((r, j) => { server.listen(0, '127.0.0.1', r); server.once('error', j); });
  const PORT = server.address().port;
  console.log('  (test origin: http://127.0.0.1:' + PORT + ')');
  browser = await chromium.launch({ headless: !HEADED });
  const page = await browser.newPage();
  page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
  await page.goto('http://127.0.0.1:' + PORT + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });
  check('page is cross-origin isolated', await page.evaluate(() => crossOriginIsolated));

  const runTool = (name, args, timeoutMs) => page.evaluate(async ([name, args, timeoutMs]) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => { window._sandpieWorker.removeEventListener('message', h); resolve('TIMED OUT (no tool_result)'); }, timeoutMs);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name, args });
    });
  }, [name, args, timeoutMs]);

  // -- 1. the binary actually knows the scheme (the regression that bit us) --
  console.log('\n1. busybox wget: does it know https at all?');
  const scheme = await runTool('walios', { timeout: 100, script: [
    'wget -q https://example.com -O /tmp/ex.html 2>/tmp/err; echo "rc=$?"',
    'echo "err=$(cat /tmp/err 2>/dev/null)"',
  ].join('\n') }, 120000);
  console.log('    ' + String(scheme).replace(/\n/g, '\n    '));
  check('wget does NOT reject the https scheme', !/not an http or ftp url/.test(scheme), scheme);
  check('wget https exits 0', /rc=0/.test(scheme), scheme);

  // -- 2. it fetched the real bytes, not an empty file ----------------------
  console.log('\n2. did it actually transfer the document?');
  const body = await runTool('walios', { timeout: 100, script: [
    'wget -q https://example.com -O /tmp/ex.html; echo "rc=$?"',
    'echo "bytes=$(wc -c < /tmp/ex.html)"',
    'grep -qi "example domain" /tmp/ex.html && echo "content=OK" || echo "content=MISSING"',
  ].join('\n') }, 120000);
  console.log('    ' + String(body).replace(/\n/g, '\n    '));
  check('wget https transferred a non-trivial body', /bytes=\s*[1-9]\d{2,}/.test(body), body);
  check('wget https body is the real page', /content=OK/.test(body), body);

  // -- 3. TLS is really TLS: a bad cert must FAIL, not silently pass --------
  console.log('\n3. is the certificate actually validated?');
  // The CONTROL comes first and is not optional: when TLS is broken outright, every
  // fetch fails and "bad cert rejected" passes for the wrong reason. A VALID cert on
  // the same domain must SUCCEED, or the two rejections below prove nothing.
  const badcert = await runTool('walios', { timeout: 120, script: [
    'wget -q https://sha256.badssl.com -O /tmp/good.html 2>/dev/null; echo "valid_rc=$? valid_bytes=$(wc -c < /tmp/good.html 2>/dev/null)"',
    'wget -q https://expired.badssl.com -O /tmp/bad.html 2>/dev/null; echo "expired_rc=$?"',
    'wget -q https://self-signed.badssl.com -O /tmp/ss.html 2>/dev/null; echo "selfsigned_rc=$?"',
  ].join('\n') }, 140000);
  console.log('    ' + String(badcert).replace(/\n/g, '\n    '));
  const discriminates = /valid_rc=0/.test(badcert) && /valid_bytes=\s*[1-9]/.test(badcert);
  check('CONTROL: a valid cert on badssl.com SUCCEEDS (so the rejections below mean something)', discriminates, badcert);
  check('expired certificate is REJECTED', discriminates && /expired_rc=[1-9]/.test(badcert), badcert);
  check('self-signed certificate is REJECTED', discriminates && /selfsigned_rc=[1-9]/.test(badcert), badcert);

  // -- 4. the original victim: build-pkg can fetch an APKBUILD --------------
  console.log('\n4. build-pkg wfetch (the thing that was actually broken)');
  const wf = await runTool('walios', { timeout: 120, script: [
    'wfetch https://raw.githubusercontent.com/alpinelinux/aports/master/main/jq/APKBUILD -O /tmp/APKBUILD; echo "rc=$?"',
    'grep -c "^pkgname=" /tmp/APKBUILD 2>/dev/null | sed "s/^/pkgname_lines=/"',
  ].join('\n') }, 140000);
  console.log('    ' + String(wf).replace(/\n/g, '\n    '));
  check('wfetch retrieves a real APKBUILD over https', /pkgname_lines=1/.test(wf), wf);

  // -- 5. tier 2: anything compiled in-tab can LINK TLS ---------------------
  //   Needs clang.wasm + the sysroot staged (75MB+); the same link is proven on the
  //   build host, so this is the in-guest confirmation, not the only evidence.
  if (fs.existsSync(path.join(repoRoot, 'walios', 'clang.wasm'))) {
    console.log('\n5. cc: can a guest-compiled program link -lssl?');
    const link = await runTool('walios', { timeout: 280, script: [
      "cat > /tmp/t.c <<'CEOF'", GUEST_C, 'CEOF',
      'cc /tmp/t.c -lssl -lcrypto -o /tmp/t 2>&1 | tail -5; echo "cc_rc=$?"',
      '/tmp/t; echo "run_rc=$?"',
    ].join('\n') }, 290000);
    console.log('    ' + String(link).replace(/\n/g, '\n    '));
    check('cc links -lssl -lcrypto', /cc_rc=0/.test(link), link);
    check('the linked program creates a TLS context', /ctx=ok/.test(link), link);
  } else {
    console.log('\n5. cc -lssl link: SKIPPED (walios/clang.wasm not staged - proven on the build host)');
  }

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
