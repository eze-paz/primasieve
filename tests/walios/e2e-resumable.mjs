// End-to-end test: a walios() call that hits its deadline keeps the session.
//
// It used to destroy it. The deadline called kill() -> _waliosDrop(), which terminated the
// whole kernel worker, so /tmp and every compiled module went with it:
//     "walios run exceeded 250s and was terminated (worker killed; the next call starts a fresh one)"
// A long ./configure therefore threw away everything it had just done, every attempt --
// which is exactly the trap that made jq's build look impossible. The FS was never the
// problem: calls already share one per-conversation kernel, so /tmp survives a normal
// return. Only the timeout path was throwing it away.
//
// Now the deadline posts {t:'killall'} to the kernel, which groupExit()s every process and
// KEEPS the kernel, the VFS, the compiled modules and the OPFS bridge. The next call
// carries on from there.
//
// The second assertion is the one that must never regress: the stopped work is really
// STOPPED. Keeping the session is only safe if a runaway loop does not keep burning CPU
// after the call returns -- otherwise "resumable" quietly means "leaks a process per
// timeout". A test that only checked /tmp survived would pass on exactly that bug.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-resumable.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz'];
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
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

// Work, then hang. The hang must be killed; the work must survive.
const HANG = [
  'echo IMPORTANT-WORK > /tmp/keep.txt',
  'mkdir -p /tmp/built && echo obj > /tmp/built/a.o',
  'rm -f /tmp/tick',
  'echo started',
  'while true; do echo x >> /tmp/tick; sleep 1; done',
].join('\n');
const CHECK = [
  'echo "kept=[$(cat /tmp/keep.txt 2>/dev/null)]"',
  'echo "objs=[$(ls /tmp/built 2>/dev/null)]"',
  'a=$(wc -c < /tmp/tick 2>/dev/null)',
  'sleep 4',
  'b=$(wc -c < /tmp/tick 2>/dev/null)',
  'echo "tick_before=$a tick_after=$b"',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const run = (script, secs) => page.evaluate(async ([script, secs]) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('HARNESS TIMEOUT'), secs * 1000 + 60000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: secs, script } });
    });
  }, [script, secs]);

  const a = await run(HANG, 8);
  console.log('    ' + String(a).replace(/\n/g, '\n    '));
  check('the deadline reports a stop, not a destroyed worker', /exceeded 8s and was stopped/.test(a), a);
  check('partial output from before the deadline comes back', /started/.test(a), a);
  check('the reply says the session survived', /session is intact/i.test(a), a);

  const b = await run(CHECK, 40);
  console.log('    ' + String(b).replace(/\n/g, '\n    '));
  check('work done before the deadline is still there', /kept=\[IMPORTANT-WORK\]/.test(b), b);
  check('files built before the deadline are still there', /objs=\[a\.o\]/.test(b), b);
  // The safety property. Without it, keeping the session would just mean leaking a
  // runaway process on every timeout, and the checks above would still pass.
  const m = /tick_before=(\d*) tick_after=(\d*)/.exec(String(b));
  check('CONTROL: the stopped loop is really dead (tick count frozen)', !!m && m[1] === m[2] && m[1] !== '', m ? m[0] : b);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
