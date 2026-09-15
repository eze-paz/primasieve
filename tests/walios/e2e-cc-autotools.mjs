// End-to-end test: the `cc` driver behaves the way autoconf requires.
//
// Three separate bugs stopped every autotools project dead at the very first check,
// "checking whether the C compiler works... no":
//
//  1. RELATIVE INPUT PATHS. clang.wasm is a WASI binary and this wasi-libc has no cwd of
//     its own, so it resolved every relative path against "/" -- `cc conftest.c` looked
//     for /conftest.c. The kernel cannot fix it (wasi-libc strips the matching preopen
//     prefix, so an absolute /tmp/x.c arrives as "tmp/x.c" and a relative x.c as "x.c" --
//     indistinguishable), and this clang has no PWD/chdir support, so `cc` absolutises.
//
//  2. RELATIVE DEFAULT OUTPUTS. With no -o, clang defaults to `a.out` when linking and
//     `conftest.o` for -c, both relative, both landing in / instead of the cwd. autoconf's
//     ac_compile is literally `$CC -c conftest.c` with no -o at all.
//
// Both are a REGRESSION from 57f712c, which moved clang from a page-side bridge (that
// resolved paths for it) to an ordinary guest process.
//
// CORRECTION: this file previously claimed a third bug -- that cc always exited 0 because
// its step loop ran in a pipeline subshell. That was WRONG. A pipeline's exit status is its
// last element's, and the while loop is that element, so `exit $?` propagates. The original
// driver was verified to return 1 on a failing compile step. The evidence I mistook for it
// was `$? = 0` in config.log, which was really the env-newline bug making ac_link_default
// EMPTY -- and `eval ""` succeeds. The exit-status checks below are kept as a genuine guard.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + llvm-resources.tar.gz +
// wali-sysroot.tar.gz (~84MB, gitignored), ../sandpie-server for wisp.js, playwright.
// Skips (exit 0) with a clear message when anything is missing.
//
// Run: node tests/walios/e2e-cc-autotools.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'bin/cc', 'clang.wasm', 'llvm-resources.tar.gz',
  'wali-sysroot.tar.gz'];
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

const SCRIPT = [
  'cd /tmp && rm -rf cclab && mkdir cclab && cd /tmp/cclab',
  'printf "int main(void){return 0;}\\n" > /tmp/cclab/conftest.c',
  'mkdir -p /tmp/cclab/inc && printf "#define OK 1\\n" > /tmp/cclab/inc/hdr.h',
  'printf "#include <hdr.h>\\nint main(void){return OK-1;}\\n" > /tmp/cclab/uses.c',
  'printf "int main(void){ this is not c }\\n" > /tmp/cclab/bad.c',
  '',
  '# 1. ac_link shape: relative source, relative -o',
  'cc conftest.c -o conftest 2>/dev/null; echo "link_rc=$? link_out=$([ -f conftest ] && echo yes || echo no)"',
  './conftest; echo "link_run=$?"',
  '',
  '# 2. ac_compile shape: -c with NO -o at all',
  'rm -f conftest.o; cc -c conftest.c 2>/dev/null; echo "cshape_rc=$? cshape_out=$([ -f conftest.o ] && echo yes || echo no)"',
  '',
  '# 3. default a.out',
  'rm -f a.out; cc conftest.c 2>/dev/null; echo "aout_rc=$? aout_out=$([ -f a.out ] && echo yes || echo no)"',
  '',
  '# 4. relative -I',
  'cc -Iinc uses.c -o uses 2>/dev/null; echo "inc_rc=$?"; ./uses; echo "inc_run=$?"',
  '',
  '# 5. absolute paths must be unaffected',
  'cc /tmp/cclab/conftest.c -o /tmp/cclab/absout 2>/dev/null; echo "abs_rc=$? abs_out=$([ -f /tmp/cclab/absout ] && echo yes || echo no)"',
  '',
  '# 6. nothing may land at / ',
  'echo "leaked=$(ls /a.out /conftest /conftest.o /uses 2>/dev/null | wc -l)"',
  '',
  '# 7. -print-prog-name must answer with an ABSOLUTE path (libtool AC_PROG_LD takes an',
  '#    absolute answer as final; a bare name sends it hunting $PATH and then judging the',
  '#    result against with_gnu_ld, which our LLD is not -- "no acceptable ld found").',
  'echo "ppn_ld=$(cc -print-prog-name=ld)"',
  'echo "ppn_ar=$(cc -print-prog-name=ar)"',
  'echo "ppn_unknown=$(cc -print-prog-name=nosuchtool)"',
  '',
  '# 8. A LINK OUTPUT MUST BE EXECUTABLE. autoconf ends every link test with',
  '#    test -x conftest$ac_exeext -- so a 0644 output makes AC_CHECK_LIB report "no"',
  '#    on a link that SUCCEEDED. jq answered no to all 47 of its libm probes.',
  'rm -f xo; cc conftest.c -o xo 2>/dev/null; echo "linkx=$([ -x xo ] && echo yes || echo no)"',
  'rm -f a.out; cc conftest.c 2>/dev/null; echo "aoutx=$([ -x a.out ] && echo yes || echo no)"',
  '# CONTROL: an OBJECT is not a program and must NOT be marked executable.',
  'rm -f xo.o; cc -c conftest.c -o xo.o 2>/dev/null; echo "objx=$([ -x xo.o ] && echo yes || echo no)"',
  '',
  '# 8. FAILURE must be non-zero. A compile error and a link error, both.',
  'cc bad.c -o bad 2>/dev/null; echo "badc_rc=$?"',
  'printf "extern void nosuchsym(void);\\nint main(void){nosuchsym();return 0;}\\n" > /tmp/cclab/ln.c',
  'cc ln.c -o ln 2>/dev/null; echo "badlink_rc=$?"',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const PORT = server.address().port;
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
  await page.goto('http://127.0.0.1:' + PORT + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const out = await page.evaluate(async (script) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), 280000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 280, script } });
    });
  }, SCRIPT);
  console.log('    ' + String(out).replace(/\n/g, '\n    '));

  check('relative source + relative -o compiles and runs', /link_rc=0 link_out=yes/.test(out) && /link_run=0/.test(out), out);
  check('-c with no -o writes the .o in the cwd (autoconf ac_compile)', /cshape_rc=0 cshape_out=yes/.test(out), out);
  check('no -o at all produces a.out in the cwd', /aout_rc=0 aout_out=yes/.test(out), out);
  check('relative -I is honoured', /inc_rc=0/.test(out) && /inc_run=0/.test(out), out);
  check('absolute paths still work (no regression)', /abs_rc=0 abs_out=yes/.test(out), out);
  check('nothing was written to /', /leaked=\s*0/.test(out), out);
  // The control for 7 is test 1 above: a GOOD compile returns 0. Without it, "failure is
  // non-zero" would also pass on a cc that failed at everything.
  check('a compile ERROR is reported as non-zero', /badc_rc=[1-9]/.test(out), out);
  check('a link ERROR is reported as non-zero', /badlink_rc=[1-9]/.test(out), out);
  check('a linked program is executable (autoconf test -x)', /linkx=yes/.test(out), out);
  check('the default a.out is executable too', /aoutx=yes/.test(out), out);
  check('CONTROL: a -c object is NOT marked executable', /objx=no/.test(out), out);
  check('-print-prog-name=ld gives an absolute path libtool accepts', /ppn_ld=\/usr\/bin\/ld/.test(out), out);
  check('-print-prog-name=ar gives an absolute path', /ppn_ar=\/usr\/bin\/ar/.test(out), out);
  // CONTROL: a tool we do NOT ship must still echo the bare name back, or the check above
  // would pass on a wrapper that blindly prefixes /usr/bin/ onto anything.
  check('CONTROL: an unknown tool is echoed back unchanged', /ppn_unknown=nosuchtool$/m.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
