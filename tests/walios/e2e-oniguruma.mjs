// End-to-end test: the OS ships a WORKING oniguruma for the WALI ABI.
//
// oniguruma cannot select its own integer types here. Both st.h and regint.h do:
//
//     #if   SIZEOF_VOIDP == SIZEOF_LONG
//     typedef unsigned long      st_data_t;    /* and hash_data_type, in regint.h */
//     #elif SIZEOF_VOIDP == SIZEOF_LONG_LONG
//     typedef unsigned long long st_data_t;
//     #endif                                   <- no #else, and no #error
//
// "the pointer-sized integer is long, or else long long". WALI is neither: 32-bit pointers
// with a 64-bit long (SIZEOF_VOIDP 4, SIZEOF_LONG 8, SIZEOF_LONG_LONG 8), because it mirrors
// the x86-64 Linux syscall ABI -- struct stat is 144 bytes here and time_t/off_t are 8. Only
// the exact triple wasm32-unknown-linux-muslwali does this; every other wasm32 triple gives
// long=4. So neither branch fires, nothing is declared, and -- because there is no #else --
// it fails far away, as a wall of "unknown type name 'st_data_t'" / "'hash_data_type'".
// jq's vendored copy died exactly there, which is what made jq look unbuildable in-browser.
//
// The OS now ships the library instead, the way it already ships openssl and curl:
// scripts/build-oniguruma-wali.sh cross-builds it and walios-backend.js mounts
// onig-wali.tar.gz at "/", giving /opt/wali/{lib/libonig.a,include/oniguruma.h}. `cc`
// already carries -I/opt/wali/include -L/opt/wali/lib, so `-lonig` needs no driver change.
// NO SOURCE PATCH: the type these headers want is uintptr_t, and since neither branch fires
// there is no typedef to collide with, so the recipe supplies it with
//     -include stdint.h -Dst_data_t=uintptr_t -Dhash_data_type=uintptr_t
//
// WHY THIS TEST RUNS THE CODE rather than just linking it: that -D changes the WIDTH of the
// hash-table key type (4 bytes here, 8 on a normal LP64 build). A library that merely links
// proves nothing about whether its hash tables actually work, and oniguruma keeps its name
// table -- which is what named captures use -- in exactly those tables. So the named-capture
// check below is the one that would catch a wrong-width st_data_t.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + llvm-resources.tar.gz +
// wali-sysroot.tar.gz + onig-wali.tar.gz (gitignored binaries), ../sandpie-server for
// wisp.js, playwright. Run: node tests/walios/e2e-oniguruma.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'bin/cc', 'clang.wasm', 'llvm-resources.tar.gz',
  'wali-sysroot.tar.gz', 'onig-wali.tar.gz'];
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

// Heredoc'd C, so the harness never has to escape a C string literal -- doing that through
// JSON and a shell is how an earlier probe silently injected quote characters into its input.
const SCRIPT = [
  'mkdir -p /tmp/og && cd /tmp/og && rm -f /tmp/og/*',
  '',
  '# The bundle mounts LAZILY on first clang use, so touch cc before looking for it.',
  'printf "int main(void){return 0;}\\n" > /tmp/og/m.c && cc -c /tmp/og/m.c -o /tmp/og/m.o 2>/dev/null',
  'echo "lib=$([ -f /opt/wali/lib/libonig.a ] && echo yes || echo no) hdr=$([ -f /opt/wali/include/oniguruma.h ] && echo yes || echo no)"',
  '',
  'cat > /tmp/og/t.c <<\'CEOF\'',
  '#include <stdio.h>',
  '#include <stdint.h>',
  '#include <oniguruma.h>',
  '/* The ABI premise the build recipe relies on: uintptr_t IS pointer-sized. If this ever',
  '   stops holding, -Dst_data_t=uintptr_t is silently wrong and the hash tables rot. */',
  'int abi_ok[(sizeof(uintptr_t) == sizeof(void *)) ? 1 : -1];',
  'static void run(const char *pat, const char *str){',
  '  regex_t *reg; OnigErrorInfo einfo; OnigRegion *reg_out; int r;',
  '  int plen = 0, slen = 0;',
  '  while (pat[plen]) plen++;',
  '  while (str[slen]) slen++;',
  '  r = onig_new(&reg,(UChar*)pat,(UChar*)pat+plen,ONIG_OPTION_DEFAULT,',
  '               ONIG_ENCODING_UTF8,ONIG_SYNTAX_DEFAULT,&einfo);',
  '  if (r != ONIG_NORMAL) { printf("R %s :: COMPILE_FAILED\\n", pat); return; }',
  '  reg_out = onig_region_new();',
  '  r = onig_search(reg,(UChar*)str,(UChar*)str+slen,(UChar*)str,(UChar*)str+slen,reg_out,ONIG_OPTION_NONE);',
  '  printf("R %s :: at=%d", pat, r);',
  '  if (r >= 0 && reg_out->num_regs > 1) printf(" g1=%d,%d", reg_out->beg[1], reg_out->end[1]);',
  '  printf("\\n");',
  '  onig_region_free(reg_out,1); onig_free(reg);',
  '}',
  '/* Named captures live in oniguruma\'s name table, which is an st_data_t hash table --',
  '   the exact structure the -D flag retypes. This is the discriminating check. */',
  'static void named(void){',
  '  regex_t *reg; OnigErrorInfo einfo; OnigRegion *reg_out; int r;',
  '  const char *pat = "(?<year>[0-9]{4})-(?<mon>[0-9]{2})";',
  '  const char *str = "on 2026-09-15 ok";',
  '  const char *nm  = "year";',
  '  int plen = 0, slen = 0;',
  '  while (pat[plen]) plen++;',
  '  while (str[slen]) slen++;',
  '  r = onig_new(&reg,(UChar*)pat,(UChar*)pat+plen,ONIG_OPTION_DEFAULT,',
  '               ONIG_ENCODING_UTF8,ONIG_SYNTAX_DEFAULT,&einfo);',
  '  if (r != ONIG_NORMAL) { printf("NAMED compile_failed\\n"); return; }',
  '  printf("NAMED count=%d", onig_number_of_names(reg));',
  '  reg_out = onig_region_new();',
  '  r = onig_search(reg,(UChar*)str,(UChar*)str+slen,(UChar*)str,(UChar*)str+slen,reg_out,ONIG_OPTION_NONE);',
  '  if (r >= 0) {',
  '    int gnum = onig_name_to_backref_number(reg,(UChar*)nm,(UChar*)nm+4,reg_out);',
  '    printf(" year_group=%d text=%.*s", gnum, reg_out->end[gnum]-reg_out->beg[gnum], str+reg_out->beg[gnum]);',
  '  }',
  '  printf("\\n");',
  '  onig_region_free(reg_out,1); onig_free(reg);',
  '}',
  'int main(void){',
  '  onig_init();',
  '  printf("VERSION %s\\n", onig_version());',
  '  run("a(.*)c","xxabbbcyy");',
  '  run("^[0-9]+$","12345");',
  '  run("(foo|bar)+","zzbarfoo");',
  '  run("no_match_here","abc");',   // CONTROL: must report -1
  '  run("\\\\p{Hiragana}+","abc\\u3072\\u3089\\u304c\\u306axyz");',
  '  named();',
  '  onig_end();',
  '  printf("DONE\\n");',
  '  return 0;',
  '}',
  'CEOF',
  '',
  '# -lonig only, with no -I/-L of our own: the OS must have put them on cc\'s default path.',
  'cd /tmp/og && cc t.c -lonig -o t 2>/tmp/og/cc.err; echo "link_rc=$?"',
  'head -3 /tmp/og/cc.err',
  '/tmp/og/t; echo "run_rc=$?"',
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

  check('the OS mounts libonig.a and oniguruma.h', /lib=yes hdr=yes/.test(out), out);
  // The array-size assertion in the source fails the COMPILE if uintptr_t stops being
  // pointer-sized, so a clean link is itself the ABI check.
  check('-lonig links with no extra -I/-L (cc default path) and the ABI premise holds',
    /link_rc=0/.test(out), out);
  check('the linked program RUNS', /run_rc=0/.test(out) && /DONE/.test(out), out);
  check('onig_version reports a version', /VERSION 6\.\d+\.\d+/.test(out), out);
  check('a capturing group matches with correct offsets', /R a\(\.\*\)c :: at=2 g1=3,6/.test(out), out);
  check('an anchored pattern matches', /R \^\[0-9\]\+\$ :: at=0/.test(out), out);
  check('alternation + repetition captures the last repetition', /R \(foo\|bar\)\+ :: at=2 g1=5,8/.test(out), out);
  // CONTROL: without this, an engine that "matched" everything would pass the checks above.
  check('CONTROL: a non-matching pattern reports -1', /R no_match_here :: at=-1/.test(out), out);
  check('a UTF-8 unicode property class matches multibyte text', /R \\p\{Hiragana\}\+ :: at=3/.test(out), out);
  // The real target: the name table is an st_data_t hash, which the -D flag retypes.
  check('NAMED CAPTURES work (the st_data_t hash table is sound)',
    /NAMED count=2 year_group=1 text=2026/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
