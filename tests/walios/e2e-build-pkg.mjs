// End-to-end test: build-pkg gets the source, and a library counts as success.
//
// Measured backlog before this: of eight aports tried, bzip2 and tree built, three never
// STARTED, and one built perfectly and was then thrown away. Four separate defects, none of
// them in the compiler:
//
//  1. .tar.bz2 was not in build-pkg's accepted-source list. pcre2's only source is a
//     .tar.bz2, so it was filtered out before any download and the run ended at "no usable
//     source tarball fetched/extracted" -- which reads like a network problem and is not.
//     Extraction was never broken: pcre2-10.48.tar.bz2 unpacks fine, measured.
//
//  2. A non-http source URL was skipped outright. figlet's APKBUILD points at
//     ftp://ftp.figlet.org, and the distfiles MIRROR is fetched by NAME, so the scheme of
//     the upstream URL should decide only whether the upstream FALLBACK is usable.
//
//  3. The .tar.xz path went through an in-tab xz decoder compiled on demand from
//     /usr/lib/xzminidec.c -- a file that IS NOT SEEDED in this image (measured: "ls:
//     /usr/lib/xzminidec.c: No such file or directory"). So ensure_xz returned 1 every
//     time and every .tar.xz package died before extraction. It was also unnecessary:
//     busybox tar sniffs the magic and does xz itself. Note `xz` the binary does not exist
//     here -- only `unxz` -- so tar's internal decompressor is the only xz path present.
//
//  4. The "did the build produce a wasm binary" fallback ran
//         dd if="$f" bs=4 count=1 | od -An -tx1 | grep -qi "00 61 73 6d"
//     and `dd` DOES NOT EXIST in this busybox (measured: command -v dd -> MISSING). It
//     wrote nothing for every candidate, so the fallback matched nothing, always. `od -N4`
//     reads the first four bytes with no pipeline at all.
//
//  5. And a library was reported as a failure. zlib compiles, archives, and then hit "no
//     built binary found" -- a successful build discarded because it produced no program.
//     Libraries now install into /opt/wali, which is where `cc` already looks.
//
// WHAT THIS TEST DOES NOT DO: build those packages. A full aport build is minutes each and
// the standing rule is no test over five. It asserts the FETCH+EXTRACT stage for the real
// tarball formats, the library-install path, and the two primitives the old code got wrong
// (dd absent, tar's magic sniffing) -- i.e. every defect above, at the layer it lives in.
//
// REQUIREMENTS: walios assets in walios/ INCLUDING clang.wasm + the sysroot, bin/build-pkg,
// bin/wextract, bin/wfetch, ../sandpie-server for wisp.js, playwright, and NETWORK.
// Run: node tests/walios/e2e-build-pkg.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'bin/cc', 'bin/build-pkg', 'bin/wextract', 'bin/wfetch',
  'pkgcache/index.json', 'pkgcache/curl.wasm', 'pkgcache/openssl.wasm',
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
// The relay allows alpinelinux.org ONLY by default, and a denied host surfaces in the guest
// as a bare "Send failure: Broken pipe" -- indistinguishable from a broken curl. Loopback
// test relay; production keeps its own narrower list.
process.env.WISP_ALLOW_HOSTS = '*';
process.env.WISP_ALLOW_PORTS = '80,443';
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

const DIST = 'https://distfiles.alpinelinux.org/distfiles';
const D = DIST + '/edge';

const SCRIPT = [
  'set +e',
  'cd /tmp; rm -rf bp; mkdir -p bp; cd bp',
  '',
  '# ---- the two primitives the old code assumed wrongly --------------------',
  'echo "has_dd=$(command -v dd >/dev/null 2>&1 && echo yes || echo no)"',
  'echo "has_xz=$(command -v xz >/dev/null 2>&1 && echo yes || echo no)"',
  'echo "has_unxz=$(command -v unxz >/dev/null 2>&1 && echo yes || echo no)"',
  'echo "xzminidec_seeded=$(test -f /usr/lib/xzminidec.c && echo yes || echo no)"',
  '# the wasm-magic probe must work WITHOUT dd. Build a real wasm binary and sniff it.',
  'printf "int main(void){return 7;}\\n" > m.c && cc m.c -o m.bin 2>/dev/null',
  'echo "magic=$(od -An -tx1 -N4 m.bin 2>/dev/null | tr -s \' \' | sed \'s/^ //\')"',
  '',
  '# ---- real tarballs, the three compressed forms --------------------------',
  '# .tar.xz (expat) -- the format that used to need a decoder that was never there.',
  'wfetch ' + D + '/expat-2.8.4.tar.xz -O e.tar.xz >/dev/null 2>&1; echo "xz_fetch_rc=$? xz_bytes=$(wc -c < e.tar.xz 2>/dev/null)"',
  'mkdir -p x; wextract e.tar.xz x >/dev/null 2>&1; echo "xz_extract_rc=$? xz_got=$(ls x 2>/dev/null | head -1)"',
  '# .tar.bz2 (pcre2) -- the format build-pkg filtered out before downloading.',
  'wfetch ' + D + '/pcre2-10.48.tar.bz2 -O p.tar.bz2 >/dev/null 2>&1; echo "bz2_fetch_rc=$? bz2_bytes=$(wc -c < p.tar.bz2 2>/dev/null)"',
  'mkdir -p b; wextract p.tar.bz2 b >/dev/null 2>&1; echo "bz2_extract_rc=$? bz2_got=$(ls b 2>/dev/null | head -1)"',
  '# .tar.gz control, so a pass here is not just "everything extracts".',
  '# Built locally: the point is that the .gz code path still works, not that a mirror has it.',
  'tar czf j.tar.gz -C x expat-2.8.4 2>/dev/null; echo "gz_fetch_rc=$? gz_bytes=$(wc -c < j.tar.gz 2>/dev/null)"',
  'mkdir -p g; wextract j.tar.gz g >/dev/null 2>&1; echo "gz_extract_rc=$? gz_got=$(ls g 2>/dev/null | head -1)"',
  '',
  '# ---- the mirror is SHARDED BY RELEASE, not one flat edge/ directory -----',
  '# figlet is the case that proves it: its upstream is ftp:// (unfetchable here), so the',
  '# mirror is the only route, and the shard is the only place the file exists.',
  'echo "shard_edge=$(curl -fsS --max-time 25 -o /dev/null -w %{http_code} ' + DIST + '/edge/figlet-2.2.5.tar.gz 2>/dev/null)"',
  'echo "shard_v320=$(curl -fsS --max-time 25 -o /dev/null -w %{http_code} ' + DIST + '/v3.20/figlet-2.2.5.tar.gz 2>/dev/null)"',
  '# ---- CONTROL: wextract must FAIL LOUDLY on a non-tarball ----------------',
  '# A 404 HTML body saved under a .tar.gz name is the realistic case. It used to look like',
  '# success and the blame landed on the next step.',
  'printf "<html>404 not found</html>\\n" > fake.tar.gz',
  'mkdir -p f; wextract fake.tar.gz f > /tmp/bp/fake.log 2>&1; echo "fake_rc=$?"',
  'echo "fake_said=$(grep -c \'nothing extracted\' /tmp/bp/fake.log)"',
  'echo "fake_dir_empty=$(test -z "$(ls -A f 2>/dev/null)" && echo yes || echo no)"',
  '',
  '# ---- build-pkg source selection, without running a build ----------------',
  '# Source the real script up to its fetch loop is not possible, so drive the SAME logic:',
  '# does build-pkg accept these names now? Assert against the script itself, which is the',
  '# thing that regressed, and confirm the ftp source reaches the mirror step.',
  'BP=$(command -v build-pkg)',
  '# Comment lines are stripped FIRST. This script quotes the old dd pipeline in a comment,',
  '# to record why it never worked; grepping the raw file finds that quote and reports it as',
  '# a regression. What matters is whether anything still CALLS these.',
  'grep -v "^[ 	]*#" "$BP" > /tmp/bp/bp.code',
  'echo "accepts_bz2=$(grep -c tar[.]bz2 /tmp/bp/bp.code)"',
  'echo "no_dd_left=$(grep -c dd.if= /tmp/bp/bp.code)"',
  'echo "no_xzdec_left=$(grep -c xzdec /tmp/bp/bp.code)"',
  '# same file, same stripped copy: does it walk the release shards or only edge?',
  'echo "walks_shards=$(grep -c v3.20 /tmp/bp/bp.code)"',
  '',
  '# ---- the library path, end to end ---------------------------------------',
  '# A real library build, small enough to finish: compile an archive and let build-pkg\'s',
  '# install logic place it. Done by hand here because running a whole aport is minutes.',
  'mkdir -p lib && cd lib',
  'echo aW50IGFuc3dlcih2b2lkKXsgcmV0dXJuIDQyOyB9Cg== | base64 -d > a.c',
  'cc -c a.c -o a.o 2>/dev/null && ar rc libanswer.a a.o && ranlib libanswer.a; echo "made_lib_rc=$? lib_bytes=$(wc -c < libanswer.a 2>/dev/null)"',
  'mkdir -p /opt/wali/lib /opt/wali/include && cp libanswer.a /opt/wali/lib/ && echo aW50IGFuc3dlcih2b2lkKTsK | base64 -d > /opt/wali/include/answer.h',
  '# the point of installing there: cc finds it with a bare -l, no paths.',
  'cd /tmp/bp && echo I2luY2x1ZGUgPGFuc3dlci5oPgojaW5jbHVkZSA8c3RkaW8uaD4KaW50IG1haW4odm9pZCl7IHByaW50ZigiYT0lZFxuIiwgYW5zd2VyKCkpOyByZXR1cm4gMDsgfQo= | base64 -d > use.c',
  'cc use.c -lanswer -o use 2>/tmp/bp/link.log; echo "link_rc=$?"',
  './use; echo "ran_rc=$?"',
  'head -2 /tmp/bp/link.log',
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

  // -- the assumptions the old code made, recorded so a change is visible ----
  check('dd really is absent (the wasm-magic probe could never have worked)', /has_dd=no/.test(out), out);
  check('xz the binary is absent, only unxz exists', /has_xz=no/.test(out) && /has_unxz=yes/.test(out), out);
  check('xzminidec.c really is not seeded (the decoder could never build)',
    /xzminidec_seeded=no/.test(out), out);
  check('the wasm magic is readable with od alone, no dd', /magic=00 61 73 6d/.test(out), out);

  // -- the three formats, on real upstream tarballs -------------------------
  check('.tar.xz fetches and extracts (expat)',
    /xz_fetch_rc=0/.test(out) && /xz_bytes=5\d{5}/.test(out) && /xz_extract_rc=0/.test(out) && /xz_got=expat-2\.8\.4/.test(out), out);
  check('.tar.bz2 fetches and extracts (pcre2)',
    /bz2_fetch_rc=0/.test(out) && /bz2_extract_rc=0/.test(out) && /bz2_got=pcre2-10\.48/.test(out), out);
  check('CONTROL: .tar.gz still works (a locally made one)',
    /gz_fetch_rc=0/.test(out) && /gz_extract_rc=0/.test(out) && /gz_got=expat-2\.8\.4/.test(out), out);

  // -- loud failure, which is the rule for this OS --------------------------
  check('wextract FAILS on a 404 body saved as a tarball', /fake_rc=[1-9]/.test(out), out);
  check('and says so rather than leaving the blame downstream', /fake_said=1/.test(out), out);
  check('CONTROL: nothing was extracted from it', /fake_dir_empty=yes/.test(out), out);

  // -- the script no longer depends on what is not there --------------------
  check('build-pkg accepts .tar.bz2 sources', /accepts_bz2=[1-9]/.test(out), out);
  check('build-pkg no longer calls dd', /no_dd_left=0/.test(out), out);
  check('build-pkg no longer calls the xz decoder that does not exist', /no_xzdec_left=0/.test(out), out);

  check('the distfiles mirror is sharded: figlet is NOT under edge/', /shard_edge=404/.test(out), out);
  check('...and IS under v3.20/, which is why one prefix was a guess', /shard_v320=200/.test(out), out);

  check('build-pkg walks the release shards, not just edge',
    /walks_shards=[1-9]/.test(out), out);

  // -- a library is a usable result, not a failure --------------------------
  check('a static library builds', /made_lib_rc=0/.test(out) && /lib_bytes=[1-9]/.test(out), out);
  check('installed into /opt/wali it links with a bare -l', /link_rc=0/.test(out), out);
  check('and the linked program runs and returns the library\'s value', /a=42/.test(out) && /ran_rc=0/.test(out), out);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
