// End-to-end test: busybox tar accepts the archive formats real tar accepts.
//
// Written for this bug: busybox was built without FEATURE_TAR_OLDGNU_COMPATIBILITY, so it
// rejected any archive whose header magic is five NULs -- the v7 / pre-POSIX format. That
// is exactly what jq-1.8.2.tar.gz is, so `build-pkg jq` died with "invalid tar magic" on
// the FIRST header while the download and gunzip were both perfect (8755200 bytes, byte 0
// = 'jq-1.8.2/'). GNU tar reads it without complaint. get_header_tar.c says it plainly:
// `"ustar" is for the proper tar, five NULs are for the old tar format` -- gated on a
// config that is `default y` upstream and was lost because this .config started minimal.
//
// The formats are BUILT LOCALLY by GNU tar (--format=v7/oldgnu/ustar/gnu/posix) so the
// test does not depend on a third party continuing to publish an archive in an old
// format. jq's real tarball is fetched too, as the original case.
//
// Fixtures reach the guest through OPFS, not the network: /root IS the OPFS root, and the
// WISP relay quite correctly refuses to connect to 127.0.0.1 (netguard blocks loopback),
// so a guest-side fetch of a local fixture server can never work.
//
// REQUIREMENTS: same as e2e-wget-https.mjs (walios assets in walios/, ../sandpie-server
// for wisp.js, playwright), plus GNU tar on PATH to generate the fixtures.
// Skips (exit 0) with a clear message when anything is missing.
//
// Run: node tests/walios/e2e-tar-formats.mjs
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
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

// -- fixtures: one tree, packed in every format GNU tar can emit ------------
const FORMATS = ['v7', 'oldgnu', 'ustar', 'gnu', 'posix'];
const fixDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tarfmt-'));
fs.mkdirSync(path.join(fixDir, 'payload', 'sub'), { recursive: true });
fs.writeFileSync(path.join(fixDir, 'payload', 'sub', 'a.txt'), 'hello from a\n');
fs.writeFileSync(path.join(fixDir, 'payload', 'top.txt'), 'hello from top\n');
let tarBin = null;
for (const cand of ['tar', 'bsdtar']) {
  try { execFileSync(cand, ['--version'], { stdio: 'ignore' }); tarBin = cand; break; } catch (_) {}
}
if (!tarBin) { console.log('SKIP: no tar on PATH to build the fixtures'); process.exit(0); }
const built = [];
for (const fmt of FORMATS) {
  // Relative paths + cwd: GNU tar on Windows reads an absolute "C:\..." argument as a
  // REMOTE host:path and dies with "Cannot connect to C:".
  try {
    execFileSync(tarBin, ['--format=' + fmt, '-czf', fmt + '.tar.gz', 'payload'], { stdio: 'pipe', cwd: fixDir });
    built.push(fmt);
  } catch (_) { /* this tar cannot emit that format; skip it rather than fail the run */ }
}
if (!built.includes('v7')) { console.log('SKIP: the local tar cannot emit --format=v7 (the format under test)'); process.exit(0); }
console.log('  fixtures built with ' + tarBin + ': ' + built.join(', '));

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n        ' + String(detail).replace(/\n/g, '\n        ') : '')); }
};

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.wasm': 'application/wasm', '.gz': 'application/gzip', '.pem': 'text/plain' };
const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  const file = url.startsWith('/fixtures/')
    ? path.join(fixDir, url.slice('/fixtures/'.length))
    : path.join(repoRoot, url.replace(/^\/+/, '') || 'sandpie.html');
  if (!(file.startsWith(repoRoot) || file.startsWith(fixDir)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); res.end('nf'); return;
  }
  res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream',
    'cross-origin-opener-policy': 'same-origin', 'cross-origin-embedder-policy': 'require-corp',
    'cross-origin-resource-policy': 'cross-origin', 'cache-control': 'no-store' });
  fs.createReadStream(file).pipe(res);
});
process.env.WISP_ENABLED = '1';
process.env.WISP_ALLOW_HOSTS = '*';
process.env.WISP_ALLOW_PORTS = '80,443';
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: (...a) => console.log('  [wisp]', ...a), error: (...a) => console.log('  [wisp]', ...a) });

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const PORT = server.address().port;
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
  await page.goto('http://127.0.0.1:' + PORT + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  // Seed the fixtures into OPFS: /root in the guest IS the OPFS root.
  const seeded = await page.evaluate(async (names) => {
    const root = await navigator.storage.getDirectory();
    const out = [];
    for (const n of names) {
      const buf = await (await fetch('/fixtures/' + n + '.tar.gz')).arrayBuffer();
      const fh = await root.getFileHandle('fx-' + n + '.tar.gz', { create: true });
      const w = await fh.createWritable(); await w.write(buf); await w.close();
      out.push(n + ':' + buf.byteLength);
    }
    return out;
  }, built);
  console.log('  seeded into OPFS: ' + seeded.join(' '));

  const runTool = (script, timeoutMs) => page.evaluate(async ([script, timeoutMs]) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), timeoutMs);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 280, script } });
    });
  }, [script, timeoutMs]);

  // -- 1. every GNU-tar format extracts, with the right contents ------------
  console.log('\n1. busybox tar vs every format GNU tar emits');
  const lines = ['cd /tmp && rm -rf tf && mkdir tf'];
  for (const fmt of built) {
    lines.push(
      'mkdir -p /tmp/tf/' + fmt + ' && cd /tmp/tf/' + fmt,
      // rc must come straight off tar -- a pipeline would report sed's status instead.
      'tar xzf /root/fx-' + fmt + '.tar.gz 2>/tmp/tf/' + fmt + '.err; echo "' + fmt + '_rc=$? body=[$(cat payload/sub/a.txt 2>/dev/null)]"',
      'sed "s/^/  ' + fmt + '-err: /" /tmp/tf/' + fmt + '.err');
  }
  const out = await runTool(lines.join('\n'), 200000);
  console.log('    ' + String(out).replace(/\n/g, '\n    '));
  for (const fmt of built) {
    check('tar extracts --format=' + fmt, new RegExp(fmt + '_rc=0 body=\\[hello from a\\]').test(out), out);
  }
  check('no "invalid tar magic" for any format', !/invalid tar magic/.test(out), out);

  // -- 2. the original case: jq's real tarball ------------------------------
  console.log('\n2. the original case: jq-1.8.2.tar.gz (v7 format, from Alpine distfiles)');
  const jq = await runTool([
    'cd /tmp && rm -rf jqt && mkdir jqt && cd jqt',
    'wfetch https://distfiles.alpinelinux.org/distfiles/edge/jq-1.8.2.tar.gz -O jq.tgz; echo "fetch_rc=$?"',
    'echo "size=$(wc -c < jq.tgz)"',
    'tar tzf jq.tgz 2>/tmp/jq.err | head -3',
    'tar tzf jq.tgz 2>/dev/null | wc -l | sed "s/^/entries=/"',
    'cat /tmp/jq.err',
  ].join('\n'), 200000);
  console.log('    ' + String(jq).replace(/\n/g, '\n    '));
  check('jq tarball downloads (the TLS fix still holds)', /fetch_rc=0/.test(jq) && /size=\s*19\d{5}/.test(jq), jq);
  check('jq tarball no longer hits "invalid tar magic"', !/invalid tar magic/.test(jq), jq);
  check('jq tarball lists a real number of entries', /entries=\s*[1-9]\d{1,}/.test(jq), jq);

} finally {
  if (browser) await browser.close();
  server.close();
  try { fs.rmSync(fixDir, { recursive: true, force: true }); } catch (_) {}
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
