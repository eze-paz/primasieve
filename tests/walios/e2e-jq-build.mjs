// End-to-end test: jq. The shipped binary works, and jq's OWN build still runs in-guest.
//
// WHY THIS TEST IS A SHRUNK ONE, AND WHAT THAT COSTS. A full in-browser jq build does not
// fit a test. Measured here, on jq-1.7.1, in the same harness:
//
//     fetch tarball            8s   (1,950,645 bytes)
//     extract                  2s
//     ./configure            >215s  -- 110 checks done, at "checking for strftime",
//                                      and NOT yet at the oniguruma probe
//
// so configure alone is ~2s per check and runs several times the length of the standing
// "no test over 5 minutes" rule; the whole build is ~15 minutes. Rather than raise the cap,
// this test bounds configure and asserts it got DEEP and CLEAN, and the full build stays
// out-of-band (scripts/build-jq-wali.sh in sandpie-server, which is also what produces the
// shipped pkgcache/jq.wasm).
//
// THAT SHRINK IS SOUND FOR THE BUGS THIS IS GUARDING, and it is worth being precise about
// why, because a bounded run is only evidence if the failures it must catch happen inside
// the bound. Every toolchain bug jq's build hit was an EARLY, LOUD abort:
//
//   - /etc/config.site returning non-zero -> "configure: error: failed to load site script"
//     before check 1. (The `&&`-list guard did exactly this once build_alias was set, which
//     build-pkg always sets.)
//   - no working nm -> libtool's symbol pipe comes out EMPTY -> eval of a pipeline with a
//     hole in it -> "syntax error near unexpected token |", and because eval is a special
//     builtin the shell EXITS.
//   - the executable bit missing on a linked program -> "C compiler cannot create
//     executables" at check ~2.
//   - cc absolutising -include -> no system header can be preincluded, which is how the
//     oniguruma recipe supplies uintptr_t.
//
// None of those can hide past check 40. A failure that only appears at check 200 WOULD
// escape this test -- that is the honest limit of the shrink, and the reason the assertion
// below is "no configure: error line AND got deep", not "configure exited 0".
//
// The shipped-binary half is not a shrink: it runs the real jq. The named-capture check is
// the load-bearing one there -- oniguruma's ABI fix (-Dst_data_t=uintptr_t) changes the WIDTH
// of its hash-table key type, and the name table that named captures use lives in exactly
// those tables, so a wrong-width build links and then gives wrong answers.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + llvm-resources.tar.gz +
// wali-sysroot.tar.gz + onig-wali.tar.gz + pkgcache/{index.json,jq.wasm,curl.wasm,openssl.wasm},
// ../sandpie-server for wisp.js, playwright, and NETWORK (it fetches jq's real tarball).
// Run: node tests/walios/e2e-jq-build.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'bin/cc', 'bin/wfetch', 'bin/wextract',
  'pkgcache/index.json', 'pkgcache/jq.wasm', 'pkgcache/curl.wasm', 'pkgcache/openssl.wasm',
  'clang.wasm', 'llvm-resources.tar.gz', 'wali-sysroot.tar.gz', 'onig-wali.tar.gz'];
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
// The relay's default allow-list is alpinelinux.org ONLY, and every other host is denied as
// a bare "Send failure: Broken pipe" -- which reads exactly like a broken curl. This is a
// loopback-only test relay; production keeps its own narrower list.
process.env.WISP_ALLOW_HOSTS = '*';
process.env.WISP_ALLOW_PORTS = '80,443';
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

const JQ_VER = '1.7.1';
const TARBALL = 'https://github.com/jqlang/jq/releases/download/jq-' + JQ_VER + '/jq-' + JQ_VER + '.tar.gz';
// 150s of configure is ~75 checks at the measured rate -- far past where any of the guarded
// failures live, and it keeps the whole run inside the 5-minute rule.
const CONF_BUDGET = 150;

const SCRIPT = [
  'set +e',
  '',
  '# ---- 1. the SHIPPED jq ------------------------------------------------',
  'echo "version=$(jq --version 2>&1)"',
  'echo "map=$(echo \'[1,2,3]\' | jq -c \'map(.*2)\' 2>&1)"',
  'echo "select=$(echo \'[{"a":1},{"a":9}]\' | jq -c \'[.[]|select(.a>5)]\' 2>&1)"',
  '# regex builtins: these are the ones that need oniguruma linked in at all.',
  'echo "test=$(echo \'"foobar"\' | jq -c \'test("^foo")\' 2>&1)"',
  'echo "gsub=$(echo \'"foobar"\' | jq -c \'gsub("o";"0")\' 2>&1)"',
  '# NAMED CAPTURES: the canary for a wrong-width st_data_t. A library built with the wrong',
  '# key width still links and still matches -- it loses the NAME TABLE, which is this.',
  'echo "named=$(echo \'"2026-09-16"\' | jq -c \'capture("(?<y>[0-9]{4})-(?<m>[0-9]{2})")\' 2>&1)"',
  '# CONTROL: a jq error must be a nonzero exit, not a silent empty answer.',
  'echo \'{}\' | jq -e \'.missing\' >/dev/null 2>&1; echo "absent_rc=$?"',
  '',
  '# ---- 2. jq\'s OWN build, bounded ---------------------------------------',
  'cd /tmp; rm -rf jqb; mkdir -p jqb; cd jqb',
  'T=$(date +%s)',
  'wfetch ' + TARBALL + ' -O jq.tar.gz >/dev/null 2>&1; echo "fetch_rc=$? fetch_s=$(( $(date +%s) - T ))"',
  'echo "tarball_bytes=$(wc -c < jq.tar.gz 2>/dev/null)"',
  'wextract jq.tar.gz . >/dev/null 2>&1; echo "extract_rc=$?"',
  'cd jq-' + JQ_VER + ' 2>/dev/null || { echo "NO_SRC_DIR"; exit 1; }',
  'echo "csrc=$(ls src/*.c 2>/dev/null | wc -l)"',
  '',
  'T=$(date +%s)',
  'timeout ' + CONF_BUDGET + ' ./configure > /tmp/jqb/conf.log 2>&1',
  'echo "conf_rc=$? conf_s=$(( $(date +%s) - T ))"',
  '# "still going when we stopped it" is the PASS shape here; an exit 0 inside the budget',
  '# would be a nice surprise and is accepted too. What must never appear is an error line.',
  'echo "checks_done=$(grep -c \'^checking\' /tmp/jqb/conf.log)"',
  'echo "cc_works=$(grep -c \'whether the C compiler works\\.\\.\\. yes\' /tmp/jqb/conf.log)"',
  'echo "cross=$(grep -m1 \'whether we are cross compiling\' /tmp/jqb/conf.log)"',
  'echo "conf_errors=$(grep -c \'^configure: error\' /tmp/jqb/conf.log)"',
  'echo "site_error=$(grep -c \'failed to load site script\' /tmp/jqb/conf.log)"',
  'echo "libtool_synerr=$(grep -ci \'syntax error near unexpected token\' /tmp/jqb/conf.log)"',
  'echo "last_check=$(grep \'^checking\' /tmp/jqb/conf.log | tail -1)"',
  '',
  '# ---- 3. CONTROL: the site script itself, both ways --------------------',
  '# This is the one that regressed. It must load cleanly whether or not build_alias is set.',
  '( unset build_alias; . /etc/config.site >/dev/null 2>&1; echo "site_unset_rc=$?" )',
  '( build_alias=wasm32-unknown-linux-musl; . /etc/config.site >/dev/null 2>&1; echo "site_set_rc=$?" )',
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

  // -- the shipped binary ---------------------------------------------------
  check('jq is present and reports its version', /version=jq-1\.7\.1/.test(out), out);
  check('jq evaluates a filter', /map=\[2,4,6\]/.test(out), out);
  check('jq handles select over an array', /select=\[\{"a":9\}\]/.test(out), out);
  check('the regex builtins work at all (oniguruma is linked)', /test=true/.test(out), out);
  check('gsub rewrites', /gsub="f00bar"/.test(out), out);
  // The one that catches a wrong-width st_data_t: matching still works, the name table dies.
  check('NAMED CAPTURES resolve (the st_data_t width canary)',
    /named=\{"y":"2026","m":"09"\}/.test(out), out);
  check('CONTROL: jq -e on an absent key exits nonzero', /absent_rc=[1-9]/.test(out), out);

  // -- jq's own build, as far as the budget allows --------------------------
  check('jq\'s real tarball fetches over https', /fetch_rc=0/.test(out) && /tarball_bytes=19\d{5}/.test(out), out);
  check('and extracts into a source tree', /extract_rc=0/.test(out) && /csrc=(1[0-9]|[2-9][0-9])/.test(out), out);
  check('configure runs the compiler and it works', /cc_works=1/.test(out), out);
  check('configure sees a NATIVE build, not a cross one (config.site set the triple)',
    /cross=.*cross compiling\.\.\. no/.test(out), out);
  // The three shapes of early death this exists to catch.
  check('configure emitted NO error line', /conf_errors=0/.test(out), out);
  check('specifically: no "failed to load site script"', /site_error=0/.test(out), out);
  check('specifically: no libtool empty-symbol-pipe syntax error', /libtool_synerr=0/.test(out), out);
  // Depth is the evidence that the bounded run went past where those failures live.
  const depth = Number((String(out).match(/checks_done=(\d+)/) || [])[1] || 0);
  check('configure got deep before the budget stopped it (>=40 checks, got ' + depth + ')',
    depth >= 40, out);

  // -- the site script directly --------------------------------------------
  check('/etc/config.site loads with build_alias unset', /site_unset_rc=0/.test(out), out);
  check('/etc/config.site loads with build_alias SET (what build-pkg does)',
    /site_set_rc=0/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
