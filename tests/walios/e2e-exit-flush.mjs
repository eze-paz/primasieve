// End-to-end test: returning from main runs the C exit sequence (atexit + stdio flush).
//
// It did not, and it lost data SILENTLY. wali-musl's crt/crt1-command.c ended:
//
//     r = __main_void();
//     if (r) goto exit_label;
//     int s = __wali_cleanup();
//     ...
//   exit_label:
//     __wali_proc_exit(r);      <-- never calls exit()
//
// so returning from main left the process without running atexit handlers or musl's
// __stdio_exit. Any buffered stdout not already written was simply gone. Measured
// in-browser with stdout redirected to a file:
//
//     printf("BUFFERED-PAYLOAD"); atexit(bye); return 0;   -> 0 bytes, bye() never ran
//     printf("BUFFERED-PAYLOAD"); atexit(bye); exit(0);    -> 16 bytes, "ATEXIT-RAN"
//     printf("x"); return 42;                              -> rc 42 correct, 0 bytes out
//
// The exit CODE was always propagated correctly, which is most of why this hid for so long.
// The rest of why: it only bites output that does NOT end in a newline. walios answers
// TIOCGWINSZ on a non-tty fd, so musl leaves stdout line-buffered and a trailing newline
// has already flushed it. That is exactly the shape of the bug as first reported --
// `curl -w "%{http_code}\n"` worked while `curl -w "%{http_code}"` wrote nothing at all,
// with an empty stderr and rc 0.
//
// The fix is one call in the crt: exit(r) instead of __wali_proc_exit(r). exit() runs the
// atexit handlers and __stdio_exit and then ends at _Exit -> __wali_proc_exit, so the
// process still leaves by the same door. Safe because __wali_cleanup/__wali_deinit is a
// host import walios implements as a no-op, so the flush is not writing through a
// torn-down syscall layer. Recipe: sandpie-server scripts/build-wali-crt-exitfix.sh.
//
// SCOPE, stated because the test cannot: this fixes binaries compiled from now on. An
// ALREADY-LINKED binary keeps the old crt, so pkgcache/curl.wasm is still affected and
// `curl -w` with no trailing newline still writes nothing. Relinking curl is the only fix
// for that one, and it has not been done.
//
// The C sources are base64'd rather than written with printf/heredocs: they contain nested
// quotes and backslash escapes, and passing those through JSON, a shell and printf is how
// several earlier attempts at this test silently produced a truncated program instead.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + llvm-resources.tar.gz +
// wali-sysroot.tar.gz (gitignored), ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-exit-flush.mjs
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
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');

// The payload deliberately has NO trailing newline: with one, line buffering would already
// have written it and the test would pass on the broken crt too.
const SRC_RETURN = `#include <stdio.h>
#include <stdlib.h>
static void bye(void){ fprintf(stderr, "ATEXIT-RAN\\n"); }
int main(void){ atexit(bye); printf("NO-TRAILING-NEWLINE"); return 0; }
`;
// CONTROL: the exit CODE must survive. A crt change is precisely where that would break.
const SRC_CODE = `#include <stdio.h>
int main(void){ printf("CODE-PAYLOAD"); return 42; }
`;
// CONTROL: the explicit exit() path worked even before the fix and must keep working.
const SRC_EXIT = `#include <stdio.h>
#include <stdlib.h>
int main(void){ printf("EXIT-PAYLOAD"); exit(7); }
`;

const SCRIPT = [
  'mkdir -p /tmp/xf && cd /tmp/xf && rm -f /tmp/xf/*',
  'echo ' + b64(SRC_RETURN) + ' | base64 -d > /tmp/xf/ret.c',
  'echo ' + b64(SRC_CODE) + ' | base64 -d > /tmp/xf/code.c',
  'echo ' + b64(SRC_EXIT) + ' | base64 -d > /tmp/xf/ex.c',
  'echo "sources=$(ls /tmp/xf/*.c | wc -l)"',
  '',
  '# 1. THE BUG: return from main, buffered output with no trailing newline, stdout to a FILE.',
  'cc /tmp/xf/ret.c -o /tmp/xf/ret 2>/dev/null; echo "ret_cc=$?"',
  '/tmp/xf/ret > /tmp/xf/ret.out 2>/tmp/xf/ret.err',
  'echo "ret_bytes=$(wc -c < /tmp/xf/ret.out) ret_atexit=$(grep -c ATEXIT-RAN /tmp/xf/ret.err)"',
  '',
  '# 2. the same program with stdout on a PIPE rather than a file',
  '/tmp/xf/ret 2>/dev/null | cat > /tmp/xf/pipe.out',
  'echo "pipe_bytes=$(wc -c < /tmp/xf/pipe.out)"',
  '',
  '# 3. CONTROL: the exit code still propagates, and its output still lands',
  'cc /tmp/xf/code.c -o /tmp/xf/code 2>/dev/null',
  '/tmp/xf/code > /tmp/xf/code.out 2>&1; echo "code_rc=$? code_bytes=$(wc -c < /tmp/xf/code.out)"',
  '',
  '# 4. CONTROL: the explicit exit() path is unchanged',
  'cc /tmp/xf/ex.c -o /tmp/xf/ex 2>/dev/null',
  '/tmp/xf/ex > /tmp/xf/ex.out 2>&1; echo "ex_rc=$? ex_bytes=$(wc -c < /tmp/xf/ex.out)"',
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

  check('the three test programs were written and compiled', /sources=3/.test(out) && /ret_cc=0/.test(out), out);
  check('returning from main FLUSHES buffered stdout (19 bytes)', /ret_bytes=19/.test(out), out);
  check('returning from main runs atexit handlers', /ret_atexit=1/.test(out), out);
  check('the same holds when stdout is a pipe', /pipe_bytes=19/.test(out), out);
  check('CONTROL: the exit code still propagates', /code_rc=42/.test(out), out);
  check('CONTROL: and that program output lands too', /code_bytes=12/.test(out), out);
  check('CONTROL: the explicit exit() path is unchanged', /ex_rc=7/.test(out) && /ex_bytes=12/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
