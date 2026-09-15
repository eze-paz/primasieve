// End-to-end test: nm/strip/objdump accept RELATIVE paths, so libtool can link.
//
// They did not. walios-backend.js mapped `nm`, `strip` and `objdump` straight onto
// clang.wasm by argv[0]. But clang.wasm is a WASI binary whose wasi-libc has no cwd of its
// own and resolves every relative path against "/", so from /tmp/x:
//     nm /tmp/x/foo.o  ->  prints the symbol table
//     nm foo.o         ->  nm: error: foo.o: No such file or directory
// `ar`, `ranlib` and `ld` already had absolutising wrappers for exactly this. nm/strip/
// objdump were missed because nothing we had built ever invoked them.
//
// WHAT IT BROKE -- and why it looked like someone else's bug. libtool's configure builds
// lt_cv_sys_global_symbol_pipe by probing a RELATIVE conftest.o. The probe failed, so on a
// pre-fix tree the generated libtool read:
//     global_symbol_pipe=""            <- empty
//     global_symbol_to_cdecl=""        <- empty
//     NM="/bin/nm -B"
// and libtool then eval'd a pipeline with a hole in it. eval EXPANDS FIRST and parses the
// RESULT, so an empty stage is a parse error, not a no-op:
//     ./libtool: eval: line 1719: syntax error: unexpected "|"
// Every libtool link died there. jq compiled all 43 of its objects and then could not link
// libjq.la -- which reads like a jq problem and was entirely ours. With the wrappers in
// place jq 1.7.1 configures, builds and runs: `.a|map(.*2)` -> [2,4,6].
//
// NOTE the shell subtlety, because it is easy to "disprove" this bug with the wrong test:
//     sh -c 'E=""; echo x | $E | cat'        -> fine (parsed BEFORE expansion)
//     sh -c 'E=""; eval "echo x | $E | cat"' -> syntax error near unexpected token `|'
// Only the eval form reproduces it. The last check below is the eval form.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + llvm-resources.tar.gz +
// wali-sysroot.tar.gz (~84MB, gitignored), ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-binutils-relpaths.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'bin/cc', 'bin/nm', 'bin/strip', 'bin/objdump',
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

const SCRIPT = [
  'mkdir -p /tmp/bu && cd /tmp/bu && rm -f /tmp/bu/*',
  'printf "int shared_symbol_abc = 7;\\nint main(void){return 0;}\\n" > /tmp/bu/o.c',
  'cc -c /tmp/bu/o.c -o /tmp/bu/o.o; echo "compile_rc=$?"',
  '',
  '# The tools must come from the wrappers in /usr/bin, NOT a manifest-dispatched /bin/nm.',
  'echo "which_nm=$(command -v nm) which_strip=$(command -v strip) which_objdump=$(command -v objdump)"',
  '',
  '# 1. RELATIVE paths -- the whole bug. cd into the dir and use a bare filename.',
  'cd /tmp/bu && nm o.o > /tmp/bu/nm.out 2>&1; echo "nm_rel_rc=$?"',
  'echo "nm_rel_found=$(grep -c shared_symbol_abc /tmp/bu/nm.out)"',
  'cd /tmp/bu && objdump -h o.o > /tmp/bu/od.out 2>&1; echo "od_rel_rc=$?"',
  'echo "od_rel_fmt=$(grep -c "file format" /tmp/bu/od.out)"',
  '',
  '# 2. CONTROL: absolute paths must still work (a wrapper that broke them would be worse).',
  'cd / && nm /tmp/bu/o.o > /tmp/bu/nm2.out 2>&1; echo "nm_abs_rc=$?"',
  'echo "nm_abs_found=$(grep -c shared_symbol_abc /tmp/bu/nm2.out)"',
  '',
  '# 3. strip WRITES: -o must be absolutised or the output lands at / (the trap cc hit,',
  '#    where make install quietly wrote binaries into the root).',
  'cd /tmp/bu && cp o.o s.o && strip s.o -o stripped.o > /tmp/bu/st.out 2>&1',
  'echo "strip_out_in_cwd=$([ -f /tmp/bu/stripped.o ] && echo yes || echo no)"',
  '',
  '# 4. Nothing may be created at /.',
  'echo "leaked=$(ls /o.o /s.o /stripped.o /conftest.o 2>/dev/null | wc -l)"',
  '',
  '# 5. THE REGRESSION THAT MATTERS: the libtool shape. libtool evals a pipeline built from',
  '#    the nm probe; when the probe failed the pipe was EMPTY and eval hit a parse error.',
  '#    Note this only reproduces via eval -- a plain pipeline parses before expanding.',
  'cd /tmp/bu',
  'PIPE="sed -n \'s/^.* [BDT] \\(.*\\)$/\\1/p\'"',
  'eval "nm o.o | $PIPE" > /tmp/bu/pipe.out 2>/tmp/bu/pipe.err; echo "pipe_rc=$?"',
  'echo "pipe_syntaxerr=$(grep -c "syntax error" /tmp/bu/pipe.err)"',
  'echo "pipe_found=$(grep -c shared_symbol_abc /tmp/bu/pipe.out)"',
  '',
  '# 6. CONTROL for 5: an EMPTY stage really is a parse error, so check 5 is discriminating.',
  '#    Without this, pipe_syntaxerr=0 would also pass on a shell that tolerates the hole.',
  '#    It must run in a CHILD shell: eval is a special builtin, so a syntax error inside it',
  '#    exits a non-interactive shell outright -- which is precisely why libtool did not',
  '#    merely warn, it died and make reported Error 2.',
  'sh -c \'E=""; eval "nm /tmp/bu/o.o | $E | cat"\' > /dev/null 2>/tmp/bu/empty.err; echo "empty_rc=$?"',
  'echo "empty_syntaxerr=$(grep -c "syntax error" /tmp/bu/empty.err)"',
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

  check('the test object compiled', /compile_rc=0/.test(out), out);
  check('nm/strip/objdump resolve to the /usr/bin wrappers', /which_nm=\/usr\/bin\/nm/.test(out)
    && /which_strip=\/usr\/bin\/strip/.test(out) && /which_objdump=\/usr\/bin\/objdump/.test(out), out);
  check('nm reads a RELATIVE object path', /nm_rel_rc=0/.test(out) && /nm_rel_found=[1-9]/.test(out), out);
  check('objdump reads a RELATIVE object path', /od_rel_rc=0/.test(out) && /od_rel_fmt=[1-9]/.test(out), out);
  check('CONTROL: absolute paths still work', /nm_abs_rc=0/.test(out) && /nm_abs_found=[1-9]/.test(out), out);
  check('strip -o writes into the cwd, not /', /strip_out_in_cwd=yes/.test(out), out);
  check('nothing was created at /', /leaked=\s*0/.test(out), out);
  check('the libtool symbol-pipe shape evals cleanly and finds the symbol',
    /pipe_syntaxerr=0/.test(out) && /pipe_found=[1-9]/.test(out), out);
  // Proves check 8 can actually fail: with an empty stage, eval DOES report a syntax error.
  check('CONTROL: an empty pipeline stage under eval IS a syntax error (and is fatal)',
    /empty_syntaxerr=[1-9]/.test(out) && /empty_rc=[1-9]/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
