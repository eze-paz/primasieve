// End-to-end test: walios can spawn thousands of processes in one run.
//
// It could not. A long process-heavy run -- which is what ./configure IS -- died at around
// 380 pipelines with
//     RangeError: WebAssembly.instantiate(): Out of memory: Cannot allocate Wasm memory
// and never recovered for the life of that kernel worker. Every subsequent command in the
// run failed, which is why autotools looked like it had a broken compiler near the end.
//
// ROOT CAUSE, isolated in a 2x2 outside walios entirely:
//
//     posts memory across threads | grows | result
//     no                          | no    | survived 250
//     no                          | YES   | survived 250
//     YES                         | no    | FAILED at 124
//     YES                         | YES   | FAILED at 123
//
// Posting a SHARED wasm memory across a thread boundary is the whole cause, and growth is
// irrelevant. The direction is what matters: if the agent that CREATED the memory is then
// terminated, its backing store is never reclaimed -- terminate() runs no finalisation, and
// the surviving peer's reference pins it with nobody left to free it. The reverse (creator
// survives, receiver terminated) is fine: 400 iterations clean.
//
// walios did exactly the bad shape: every proc-worker instantiated a module that DEFINED
// its own memory, handed that memory to the kernel, and was then terminated. So each
// process leaked one memory permanently.
//
// THE FIX IS ONE LINKER FLAG: busybox is built -Wl,--import-memory, so the KERNEL creates
// the memory (getSharedMemory()) and passes it in. The creator now outlives the process.
// No kernel change was needed -- makeImports() already supplies env.memory to any module
// that imports it, for wasi-threads.
//
// This is why none of the obvious levers moved the ceiling: it is one leaked object per
// process, not bytes. --max-memory 2GB->64MB, stack 8MB->1MB and a yield after terminate
// all left it at ~380.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-process-ceiling.mjs
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

// 1500 pipelines is ~3000 forks -- comfortably past the old ~380 cliff, and it stays
// inside the 5-minute ceiling this project holds itself to.
const N = 1500;
const SCRIPT = [
  'k=0; f=0; first=-1',
  'while [ $k -lt ' + N + ' ]; do',
  '  y=$(echo hi | sed "s/h/H/")',
  '  if [ "$y" != "Hi" ]; then f=$((f+1)); [ $first -lt 0 ] && first=$k; fi',
  '  k=$((k+1))',
  'done',
  'echo "RESULT total=' + N + ' fails=$f first_fail=$first"',
  // A process must still work AFTER the churn: exhaustion used to be permanent for the
  // life of the kernel worker, so a post-churn command is the part that really regressed.
  'echo "AFTER=$(echo done | sed "s/done/still-alive/")"',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const oom = [];
  page.on('console', m => { const t = m.text(); if (t.includes('Out of memory')) oom.push(t.slice(0, 120)); });
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const out = await page.evaluate(async (script) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), 290000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 280, script } });
    });
  }, SCRIPT);
  console.log('    ' + String(out).replace(/\n/g, '\n    '));

  check(N + ' pipelines all succeed', new RegExp('RESULT total=' + N + ' fails=0 first_fail=-1').test(out), out);
  check('the guest is still usable after the churn', /AFTER=still-alive/.test(out), out);
  check('the kernel reported no wasm OOM', oom.length === 0, oom.join('\n'));

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
