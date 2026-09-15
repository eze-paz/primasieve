// End-to-end test: the /dev nodes shell and build glue actually use.
//
// walios had /dev/null, /dev/random, /dev/urandom, /dev/tty, /dev/ptmx and /dev/hostcall.
// It did NOT have /dev/stdin, /dev/stdout, /dev/stderr, /dev/zero or /dev/full -- every one
// of those was a plain ENOENT, and `test -e` said no, which is how configure scripts ask.
//
// The stdio three matter most. `cmd > /dev/stdout`, `... < /dev/stdin` and the
// "write to stdout by name" idiom are everywhere in Makefiles, configure scripts and shell
// glue, and on Linux they are symlinks into /proc/self/fd -- so opening one hands you a DUP
// of that fd. That is what this implements, sharing the open-file description rather than
// making a fresh handle, the same rule fork/dup2 follow.
//
// /dev/zero reads endless NULs and swallows writes. /dev/full does the same on read but
// fails every write with ENOSPC, which is the entire reason it exists: test suites use it
// to exercise an out-of-space path. (E.NOSPC had to be added to the errno table for that;
// without it the write would have returned -undefined.)
//
// NOTE dd is NOT a busybox applet in this build, so `dd if=/dev/zero` is "dd: not found"
// and says nothing about the device. An earlier version of this test used dd and was
// measuring the missing applet. head -c is used instead.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-dev-nodes.mjs
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

const SCRIPT = [
  'rm -rf /tmp/dv; mkdir -p /tmp/dv',
  'echo "=== existence, which is how configure asks:"',
  'for d in null zero full random urandom tty stdin stdout stderr; do',
  '  printf "have_%s=%s " "$d" "$([ -e /dev/$d ] && echo 1 || echo 0)"',
  'done; echo',
  '',
  '# /dev/zero: endless NULs on read, writes swallowed.',
  'head -c 256 /dev/zero > /tmp/dv/z 2>/dev/null',
  'echo "zero_bytes=$(wc -c < /tmp/dv/z) zero_nonnul=$(tr -d "\\0" < /tmp/dv/z | wc -c)"',
  'echo discard > /dev/zero; echo "zero_write_rc=$?"',
  '',
  '# /dev/full: reads like zero, every write is ENOSPC. This is the discriminating one --',
  '# a naive "make /dev/full an alias of /dev/zero" would pass every other check here.',
  'echo discard > /dev/full 2>/tmp/dv/full.err; echo "full_write_rc=$?"',
  'echo "full_msg=$(head -1 /tmp/dv/full.err)"',
  '',
  '# the stdio three, by name',
  'echo STDOUT-BY-NAME > /dev/stdout > /tmp/dv/so 2>&1; echo "stdout_file=[$(cat /tmp/dv/so)]"',
  'printf "%s\\n" PIPED-IN | { read -r L < /dev/stdin; echo "stdin_read=[$L]"; }',
  'echo STDERR-BY-NAME 2>/tmp/dv/se > /dev/stderr 2>/tmp/dv/se; echo "stderr_rc=$?"',
  '',
  '# CONTROL: a device that does NOT exist must still be ENOENT. Without this, a change',
  '# that made every /dev/* path succeed would pass everything above.',
  'echo "bogus_exists=$([ -e /dev/nosuchdevice ] && echo 1 || echo 0)"',
  'cat /dev/nosuchdevice > /dev/null 2>/tmp/dv/bogus.err; echo "bogus_rc=$?"',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const out = await page.evaluate(async (script) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), 200000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 120, script } });
    });
  }, SCRIPT);
  console.log('    ' + String(out).replace(/\n/g, '\n    '));

  for (const d of ['zero', 'full', 'stdin', 'stdout', 'stderr'])
    check('/dev/' + d + ' exists (test -e)', new RegExp('have_' + d + '=1').test(out), out);
  check('the devices that already worked still do', /have_null=1/.test(out) && /have_tty=1/.test(out) && /have_urandom=1/.test(out), out);

  check('/dev/zero reads 256 bytes and they are ALL NUL', /zero_bytes=256/.test(out) && /zero_nonnul=0/.test(out), out);
  check('/dev/zero swallows writes', /zero_write_rc=0/.test(out), out);
  check('/dev/full fails a write with ENOSPC', /full_write_rc=[1-9]/.test(out) && /No space left on device/.test(out), out);

  check('/dev/stdout writes to wherever stdout points', /stdout_file=\[STDOUT-BY-NAME\]/.test(out), out);
  check('/dev/stdin reads the process stdin', /stdin_read=\[PIPED-IN\]/.test(out), out);
  check('/dev/stderr is writable', /stderr_rc=0/.test(out), out);

  // Without this, "every /dev path succeeds" would look identical to a correct fix.
  check('CONTROL: an unknown /dev path is still ENOENT', /bogus_exists=0/.test(out) && /bogus_rc=[1-9]/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
