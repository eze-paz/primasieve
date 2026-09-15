// Re-check of the "missing tools" inventory an LLM produced during a walios systems
// check on 2026-09-14 (transcript session ne58n349). Each entry is probed FUNCTIONALLY --
// a tool that prints a version but cannot do its job is not present -- and the result is
// printed as `name :: rc=N :: first lines`, so a regression reads like an inventory diff.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// The `apk add` group needs walios/pkgs/*.wasm, which is a server-side artifact, not in git:
//   scp sandpie:/opt/sandpie-server/walios/pkgs/{bc,patch,cpio,m4,which}.wasm walios/pkgs/
// Without them the local static server 404s and the guest reports a truncated wasm module.
// Run: node tests/walios/e2e-missing-tools.mjs
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

// Each probe runs the real JOB, not `--version`: a tool that prints a version but cannot
// do its work is not present. Results print as `name :: rc=N :: output`, so a regression
// reads like an inventory diff.
//
// QUOTING: probe arguments are SINGLE-quoted. Double quotes would let the OUTER shell
// expand `$?` / `$(...)` before the probe ran -- which silently reported every compiled
// program's exit status as 0 while this test was being written.
const sq = (c) => "'" + c.split("'").join("'\\''") + "'";

// Group 1: on PATH at boot.
const BOOT = [
  ['node',     `node -e 'console.log(2+40)'`],
  ['jq',       `echo '{"a":[1,2,3]}' | jq -c '.a[1]'`],
  ['gcc',      `printf 'int main(){return 7;}\\n' > /tmp/mt/a.c; gcc /tmp/mt/a.c -o /tmp/mt/ac && /tmp/mt/ac; echo rc=$?`],
  ['cc',       `cc /tmp/mt/a.c -o /tmp/mt/ac2 && /tmp/mt/ac2; echo rc=$?`],
  ['openssl',  `openssl s_client -help 2>&1 | head -1`],
  ['vi',       `command -v vi`],
  ['ssh',      `command -v ssh`],
  ['python3',  `python3 -c "import sqlite3;print(sqlite3.connect(':memory:').execute('select 40+2').fetchone()[0])"`],
  ['unzip',    `command -v unzip; command -v unxz`],
  ['grep_AB',  `printf '1\\n2\\n3\\n' | grep -A1 2 | tr '\\n' ','`],
  ['devnull',  `echo x > /dev/null; echo ok`],
  ['root_ssh', `mkdir -p /root/.ssh && echo k > /root/.ssh/probe && cat /root/.ssh/probe`],
];
// Group 2: one `apk add` away (catalog tier 'wasm' -> walios/pkgs/NAME.wasm).
const ADDABLE = [
  ['bc',       `echo '6*7' | bc`],
  ['patch',    `cd /tmp/mt && printf 'a\\nb\\n' > p1 && printf 'a\\nB\\n' > p2 && diff -u p1 p2 > p.diff; patch p1 < p.diff > /dev/null && tr '\\n' ',' < p1`],
  ['cpio',     `cd /tmp/mt && echo p1 | cpio -o > c.cpio && wc -c < c.cpio`],
  ['m4',       `printf 'define(x,42)x\\n' | m4 | tail -1`],
  ['which',    `which cc`],
];
// Group 3: still absent. Neither on PATH nor in the catalog as wasm, so `build-pkg NAME`
// (in-tab clang, minutes, best effort) is the only route. These are the real gaps.
const ABSENT = [
  ['npm',      `command -v npm || echo NOTFOUND`],
  ['scp',      `command -v scp || echo NOTFOUND`],
  ['rsync',    `command -v rsync || echo NOTFOUND`],
  ['zip',      `command -v zip || echo NOTFOUND`],
  ['xz',       `command -v xz || echo NOTFOUND`],
  ['sqlite3',  `command -v sqlite3 || echo NOTFOUND`],
  ['file',     `command -v file || echo NOTFOUND`],
  ['strace',   `command -v strace || echo NOTFOUND`],
  ['lsof',     `command -v lsof || echo NOTFOUND`],
  ['netstat',  `command -v netstat || echo NOTFOUND`],
  ['perl',     `command -v perl || echo NOTFOUND`],
  ['ruby',     `command -v ruby || echo NOTFOUND`],
  ['go',       `command -v go || echo NOTFOUND`],
  ['java',     `command -v java || echo NOTFOUND`],
  ['php',      `command -v php || echo NOTFOUND`],
  ['cmake',    `command -v cmake || echo NOTFOUND`],
  ['cxx',      `command -v g++ || command -v c++ || command -v clang++ || echo NOTFOUND`],
  ['nano',     `command -v nano || echo NOTFOUND`],
];

const SCRIPT = [
  'rm -rf /tmp/mt; mkdir -p /tmp/mt; cd /tmp/mt',
  `probe() { eval "$2" > /tmp/mt/out 2>&1; r=$?; echo "$1 :: rc=$r :: $(head -3 /tmp/mt/out | tr '\\n' ' ' | cut -c1-140)"; }`,
  ...BOOT.map(([n, c]) => `probe ${n} ${sq(c)}`),
  'apk add bc patch cpio m4 which > /dev/null 2>&1',
  ...ADDABLE.map(([n, c]) => `probe ${n} ${sq(c)}`),
  ...ABSENT.map(([n, c]) => `probe ${n} ${sq(c)}`),
].join('\n');

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n        ' + String(detail).replace(/\n/g, '\n        ') : '')); }
};
const line = (out, name) => (String(out).split('\n').find((l) => l.startsWith(name + ' ::')) || '');

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
      const t = setTimeout(() => resolve('TIMED OUT'), 280000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 270, script } });
    });
  }, SCRIPT);
  console.log('    ' + String(out).replace(/\n/g, '\n    '));

  check('node runs JS', /node :: rc=0 :: 42/.test(out), line(out, 'node'));
  check('jq parses JSON', /jq :: rc=0 :: 2/.test(out), line(out, 'jq'));
  // The 2026-09-14 inventory called gcc "a broken stub (applet not found)". It is real
  // clang now, so it must COMPILE and the program's exit status must come back.
  check('gcc compiles and the exit status propagates', /gcc :: rc=0 :: rc=7/.test(out), line(out, 'gcc'));
  check('cc does too', /cc :: rc=0 :: rc=7/.test(out), line(out, 'cc'));
  check('openssl is the s_client-only shim, and says so', /openssl :: rc=0 :: openssl: s_client needs/.test(out), line(out, 'openssl'));
  check('vi is an editor on PATH', /vi :: rc=0 :: (\/bin\/)?vi/.test(out), line(out, 'vi'));
  check('python3 has sqlite3 built in (no sqlite3 CLI needed)', /python3 :: rc=0 :: 42/.test(out), line(out, 'python3'));
  check('grep -A works (the busybox flag gap is gone)', /grep_AB :: rc=0 :: 2,3,/.test(out), line(out, 'grep_AB'));
  check('/dev/null takes a write without an "Invalid seek"', /devnull :: rc=0 :: ok/.test(out), line(out, 'devnull'));
  check('/root/.ssh is writable', /root_ssh :: rc=0 :: k/.test(out), line(out, 'root_ssh'));

  // Installable on demand: `apk add` must FETCH AND RUN, not just print "added".
  check('apk add bc gives a working bc', /bc :: rc=0 :: 42/.test(out), line(out, 'bc'));
  check('apk add patch applies a diff', /patch :: rc=0 :: a,B,/.test(out), line(out, 'patch'));
  check('apk add cpio writes an archive', /cpio :: rc=0 :: .*512/.test(out), line(out, 'cpio'));
  check('apk add m4 expands a macro', /m4 :: rc=0 :: 42/.test(out), line(out, 'm4'));
  check('apk add which resolves a program', /which :: rc=0 :: \/usr\/bin\/cc/.test(out), line(out, 'which'));

  // The remaining gaps, asserted ABSENT so this speaks up when one of them lands.
  for (const [n] of ABSENT) check('still absent: ' + n, new RegExp(n + ' :: rc=[01] :: NOTFOUND').test(out), line(out, n));
} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
