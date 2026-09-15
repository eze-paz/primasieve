// End-to-end test: mkdir works in the OPFS-backed workspace (/root).
//
// It did not, and the failure was a liar. `mkdir /root/x` reported
//     mkdir: can't create directory '/root/x': Operation not permitted
// while ACTUALLY CREATING THE DIRECTORY -- it was there immediately afterwards, which is
// what made it so confusing to chase.
//
// Cause: opfsLoaded is a Map (path -> when we last listed it), but the mkdir handler
// called opfsLoaded.add(p). That threw TypeError AFTER the OPFS mkdir had already
// succeeded, and the syscall dispatcher turns ANY handler exception into -1 -- which the
// guest reads as EPERM. One wrong method name, reported as a permission error.
//
// What it broke: `tar x` into the workspace, `mkdir -p`, `git clone` into a new directory,
// and `mkdir ~/.ssh` (that last one showed up in a real session, where it looked like
// walios deliberately locking down /root). It also made multi-call builds impossible: a
// source tree could not be unpacked anywhere that survives between run_walios calls, since
// /tmp is a fresh VFS every call and only /root is OPFS-backed.
//
// The persistence check at the end is the point of the fix, not a bonus: a build too long
// for one 300s call can only work if the tree is still there on the next one.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-workspace-mkdir.mjs
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

// Two scripts, run as two SEPARATE tool calls against the same page. /tmp is a fresh VFS
// each call; only /root survives, so this is what proves cross-call persistence.
const CALL1 = [
  'rm -rf /root/mkt 2>/dev/null',
  'mkdir /root/mkt; echo "mkdir_rc=$?"',
  'mkdir -p /root/mkt/a/b/c; echo "mkdirp_rc=$?"',
  'echo hello > /root/mkt/a/b/c/f.txt; echo "write_rc=$?"',
  'echo "read_back=$(cat /root/mkt/a/b/c/f.txt)"',
  // the errno must be right too: a SECOND mkdir of the same path is EEXIST, not EPERM
  'mkdir /root/mkt 2>/tmp/e; echo "again_rc=$? again_err=$(cat /tmp/e)"',
  // and a real tar into the workspace, which is what this blocked
  'mkdir -p /root/mkt/tt && cd /root/mkt/tt && mkdir -p src/sub && echo x > src/sub/y.txt',
  'tar czf /root/mkt/t.tgz -C /root/mkt/tt src && rm -rf /root/mkt/tt/src',
  'tar xzf /root/mkt/t.tgz -C /root/mkt/tt; echo "untar_rc=$? untar_body=$(cat /root/mkt/tt/src/sub/y.txt 2>/dev/null)"',
].join('\n');
const CALL2 = [
  'echo "persist_dir=$([ -d /root/mkt/a/b/c ] && echo yes || echo no)"',
  'echo "persist_file=$(cat /root/mkt/a/b/c/f.txt 2>/dev/null)"',
  'rm -rf /root/mkt',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const run = (script) => page.evaluate(async (script) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), 200000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 190, script } });
    });
  }, script);

  const a = await run(CALL1);
  console.log('    ' + String(a).replace(/\n/g, '\n    '));
  check('mkdir in the workspace succeeds', /mkdir_rc=0/.test(a), a);
  check('mkdir -p creates a nested tree', /mkdirp_rc=0/.test(a), a);
  check('a file written in that tree reads back', /write_rc=0/.test(a) && /read_back=hello/.test(a), a);
  // Without this the first check could pass on a build that made mkdir unconditionally
  // succeed: re-creating an existing directory must still FAIL, and as EEXIST.
  check('CONTROL: mkdir of an existing dir still fails, and says File exists', /again_rc=[1-9]/.test(a) && /File exists/i.test(a), a);
  check('tar extracts into the workspace', /untar_rc=0/.test(a) && /untar_body=x/.test(a), a);

  const b = await run(CALL2);
  console.log('    ' + String(b).replace(/\n/g, '\n    '));
  check('the tree survives into a SEPARATE tool call (multi-call builds)', /persist_dir=yes/.test(b) && /persist_file=hello/.test(b), b);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
