// End-to-end test: execvp() finds programs on $PATH, plus strip and pkg-config.
//
// THE EXEC BUG, which is the important one. walios' busybox fallback made EVERY exec
// succeed: any unresolved name ran busybox, which dispatches on argv[0]. So when a program
// did its own PATH walk -- which execvp() does -- the first candidate always "worked":
//
//     timeout 260 build-pkg tree   ->  "build-pkg: applet not found"
//
// because execvp tried /bin/build-pkg, the fallback ran busybox instead of returning
// ENOENT, busybox printed "applet not found" and exited, and the walk never reached
// /usr/bin/build-pkg where the program actually is. `timeout /usr/bin/build-pkg` worked
// fine, which is what made it look like a shebang problem rather than a lookup one.
//
// That silently broke `timeout CMD`, `env CMD`, `find -exec CMD` and anything spawning a
// helper by name. It was found by a batch of package builds that reported eight failures in
// 0 seconds each -- not one of them had started.
//
// The fix: an explicit path to a file that does not exist is ENOENT, so the caller's PATH
// walk continues. A BARE name still falls back to busybox, because "run the applet" is the
// intended meaning there and it is what the 17-byte /bin/sed applet stubs rely on -- those
// files EXIST, so they never reach the new branch.
//
// ALSO HERE, two smaller things fixed in the same pass:
//
//  - strip reported failure on work it had completed. LLVM ends a strip by setting
//    permissions on the output, WASI has no chmod, so llvm-strip printed
//    "error: 'out.o': Function not implemented" and exited 1 AFTER writing the file --
//    measured: output present at 377 bytes, and a stripped program still ran and returned
//    the right value. That exit 1 breaks `make install -s`. bin/strip now reports success
//    when THAT is the only error and the output exists, and still fails on anything else.
//
//  - pkg-config did not exist. A configure script asking for an optional library copes with
//    "not installed", but autoconf's PKG_CHECK_MODULES ABORTS when the pkg-config BINARY is
//    missing, before any fallback. The shim answers honestly from real .pc files and exits 1
//    for packages that are not there.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + the sysroot (for strip),
// ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-exec-path.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'bin/cc', 'bin/strip', 'bin/pkg-config',
  'clang.wasm', 'llvm-resources.tar.gz', 'wali-sysroot.tar.gz'];
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

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const PC = b64([
  'prefix=/opt/wali',
  'exec_prefix=${prefix}',
  'libdir=${exec_prefix}/lib',
  'includedir=${prefix}/include',
  'Name: demo',
  'Description: a test package',
  'Version: 1.2.3',
  'Cflags: -I${includedir}/demo -DDEMO=1',
  'Libs: -L${libdir} -ldemo',
  '',
].join('\n'));
const SRC = b64('int f(void){return 3;}\nint main(void){return f();}\n');

const SCRIPT = [
  'rm -rf /tmp/xp; mkdir -p /tmp/xp; cd /tmp/xp',
  '',
  '# 1. EXECVP FINDS A PROGRAM ON $PATH. build-pkg lives in /usr/bin, and /bin comes first,',
  '#    so this only works if the /bin miss returns ENOENT and the walk continues.',
  'echo "where=$(command -v build-pkg)"',
  'timeout 10 build-pkg > /tmp/xp/bp.out 2>&1; echo "bare_rc=$?"',
  'echo "bare_said=$(head -1 /tmp/xp/bp.out)"',
  'echo "env_said=$(env build-pkg 2>&1 | head -1)"',
  '# a wasm binary by bare name too, not just a script',
  'echo "cc_said=$(timeout 20 cc --version 2>&1 | head -1 | cut -c1-20)"',
  '',
  '# CONTROL: an explicit path to a file that does not exist must be ENOENT, NOT busybox.',
  '#   Before the fix this said "applet not found", which is what hid the whole bug.',
  'timeout 10 /bin/build-pkg > /tmp/xp/abs.out 2>&1; echo "badpath_rc=$?"',
  'echo "badpath_said=$(head -1 /tmp/xp/abs.out)"',
  '',
  '# CONTROL: a BARE name that is a busybox applet must still reach busybox.',
  '# functional, not a version string: busybox sed prints "This is not GNU sed...", which',
  '# is easy to assert wrongly. Whether it TRANSFORMS is the thing that matters.',
  'echo "applet=$(echo abc | timeout 10 sed s/b/B/)"',
  '',
  '# 2. strip must report success for work it completed.',
  'echo ' + SRC + ' | base64 -d > /tmp/xp/s.c',
  'cc -c /tmp/xp/s.c -o /tmp/xp/s.o 2>/dev/null',
  'cd /tmp/xp && strip s.o -o s2.o 2>/tmp/xp/se1; echo "strip_rc=$? strip_bytes=$(wc -c < /tmp/xp/s2.o 2>/dev/null)"',
  'cc /tmp/xp/s.c -o /tmp/xp/prog 2>/dev/null && strip /tmp/xp/prog 2>/dev/null; echo "strip_prog_rc=$?"',
  '/tmp/xp/prog; echo "stripped_prog_runs=$?"',
  '# CONTROL: a REAL strip failure must still fail.',
  'strip /tmp/xp/nope.o 2>/tmp/xp/se2; echo "strip_missing_rc=$?"',
  '',
  '# 3. pkg-config.',
  'echo "pc_version=$(pkg-config --version)"',
  'pkg-config --exists not-installed-anywhere; echo "pc_absent_rc=$?"',
  'mkdir -p /opt/wali/lib/pkgconfig',
  'echo ' + PC + ' | base64 -d > /opt/wali/lib/pkgconfig/demo.pc',
  'echo "pc_modversion=$(pkg-config --modversion demo)"',
  'echo "pc_cflags=$(pkg-config --cflags demo)"',
  'echo "pc_libs=$(pkg-config --libs demo)"',
  'echo "pc_var=$(pkg-config --variable=libdir demo)"',
  'pkg-config --atleast-version=1.0 demo; echo "pc_atleast_ok_rc=$?"',
  'pkg-config --atleast-version=9.9 demo; echo "pc_atleast_no_rc=$?"',
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
      const t = setTimeout(() => resolve('TIMED OUT'), 280000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 270, script } });
    });
  }, SCRIPT);
  console.log('    ' + String(out).replace(/\n/g, '\n    '));

  check('the program under test really is in /usr/bin, not /bin', /where=\/usr\/bin\/build-pkg/.test(out), out);
  check('execvp finds a SCRIPT by bare name along $PATH', /bare_said=usage: build-pkg/.test(out), out);
  check('env does too', /env_said=usage: build-pkg/.test(out), out);
  check('and a wasm binary by bare name', /cc_said=clang version/.test(out), out);
  // The two that keep the fix honest at both edges.
  check('CONTROL: an explicit path to a missing file is ENOENT, not busybox',
    /badpath_rc=[1-9]/.test(out) && /No such file or directory/.test(out) && !/applet not found/.test(String(out).split('badpath_said=')[1] || ''), out);
  check('CONTROL: a bare busybox applet still reaches busybox and works', /applet=aBc/.test(out), out);

  check('strip succeeds and writes its output', /strip_rc=0/.test(out) && /strip_bytes=[1-9]/.test(out), out);
  check('a stripped program still runs and returns the right value',
    /strip_prog_rc=0/.test(out) && /stripped_prog_runs=3/.test(out), out);
  check('CONTROL: a real strip failure still fails', /strip_missing_rc=[1-9]/.test(out), out);

  check('pkg-config exists and reports a version', /pc_version=0\.29/.test(out), out);
  // The point of shipping it: "not installed" must be an exit code, not a missing binary.
  check('pkg-config exits 1 for a package that is not installed', /pc_absent_rc=1/.test(out), out);
  check('pkg-config reads a real .pc file', /pc_modversion=1\.2\.3/.test(out), out);
  check('pkg-config expands ${} variables in Cflags/Libs',
    /pc_cflags=.*-I\/opt\/wali\/include\/demo/.test(out) && /pc_libs=.*-L\/opt\/wali\/lib -ldemo/.test(out), out);
  check('pkg-config --variable works', /pc_var=\/opt\/wali\/lib/.test(out), out);
  check('pkg-config --atleast-version answers both ways',
    /pc_atleast_ok_rc=0/.test(out) && /pc_atleast_no_rc=1/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
