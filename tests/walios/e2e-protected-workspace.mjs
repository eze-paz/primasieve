// End-to-end test: the app's own workspace (/root/sandpie) cannot be deleted from the
// guest -- on EITHER ABI.
//
// Why this exists
// ---------------
// Twice now a model asked to "clone the sandpie repo" ran, inside walios:
//     cd /root && rm -rf sandpie && git clone ...github.com/eze-paz/sandpie.git
// /root IS the OPFS root, so /root/sandpie is the app's own data -- conversations,
// memory, secrets, skills -- and the delete propagates to Dropbox and from there to
// every other device. (2026-09-08 admin transcript t946ympe; again 2026-09-15 22:10 UTC
// for mruiz, 8 times across 5 sessions, which cost that user ~100 conversations.)
//
// protectedDelete() gates unlink/rmdir/rename on the Linux syscall path. The WASI
// preview1 handlers -- path_unlink_file, path_remove_directory, path_rename -- went
// straight to rmEntry() with no check, so a wasm32-wasi guest walked around the gate.
// This test pins BOTH ABIs.
//
// The controls are the point. A gate that refuses everything would pass a
// "protected path is refused" check on its own, so every arm is paired with the same
// operation on an UNPROTECTED path that must still succeed, and with the documented
// escape hatch (/root/.allow-sandpie-delete) which must still work.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-protected-workspace.mjs
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

// ---- a minimal wasm32-wasi guest that calls path_unlink_file(3, <path>) and exits
//      with the returned errno. This is the ONLY way to reach the WASI handlers:
//      busybox is a WALI/Linux-ABI binary and never touches them.
//      preview1 errnos: 0 = success, 44 = ENOENT, 63 = EPERM.
function wasiUnlinkModule(targetPath) {
  const str = new TextEncoder().encode(targetPath);
  const OFF = 16;
  const sec = (id, body) => [id, body.length, ...body];
  const vec = (items) => [items.length, ...items.flat()];

  const types = vec([
    [0x60, 3, 0x7f, 0x7f, 0x7f, 1, 0x7f],   // (i32,i32,i32)->i32   path_unlink_file
    [0x60, 1, 0x7f, 0],                     // (i32)->()            proc_exit
    [0x60, 0, 0],                           // ()->()               _start
  ]);
  const mod = [...new TextEncoder().encode('wasi_snapshot_preview1')];
  const imp = (name, typeIdx) => {
    const n = [...new TextEncoder().encode(name)];
    return [mod.length, ...mod, n.length, ...n, 0x00, typeIdx];
  };
  const imports = vec([imp('path_unlink_file', 0), imp('proc_exit', 1)]);
  const funcs = vec([[2]]);                        // one function, type 2
  // SHARED memory (flags 0x03 = has-max + shared): the kernel maps the guest's
  // memory, and refuses a module whose memory is not shared.
  const mems = vec([[0x03, 1, 16]]);
  const expName = (s) => { const n = [...new TextEncoder().encode(s)]; return [n.length, ...n]; };
  const exports = vec([
    [...expName('memory'), 0x02, 0],
    [...expName('_start'), 0x00, 2],               // func 2 = first local func (0,1 imported)
  ]);
  const data = vec([[0x00, 0x41, OFF, 0x0b, str.length, ...str]]);   // (i32.const OFF)
  const body = [
    0,                                             // no locals
    0x41, 3,                                       // i32.const 3   (dirfd; path is absolute)
    0x41, OFF,                                     // i32.const OFF (path ptr)
    0x41, str.length,                              // i32.const len
    0x10, 0,                                       // call path_unlink_file
    0x10, 1,                                       // call proc_exit(result)
    0x0b,                                          // end
  ];
  const code = vec([[body.length, ...body]]);

  return Uint8Array.from([
    0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
    ...sec(1, types), ...sec(2, imports), ...sec(3, funcs), ...sec(5, mems),
    ...sec(7, exports), ...sec(10, code), ...sec(11, data),   // sections must ascend by id
  ]);
}
// Sanity-check the encoder here, not in the browser: a malformed module would make
// every WASI arm "fail" for the wrong reason.
const PROTECTED_FILE = '/root/sandpie/conversations/e2e-probe.json';
const SCRATCH_FILE = '/root/e2e-scratch/probe.json';
const modProtected = wasiUnlinkModule(PROTECTED_FILE);
const modScratch = wasiUnlinkModule(SCRATCH_FILE);
try { new WebAssembly.Module(modProtected); new WebAssembly.Module(modScratch); }
catch (e) { console.log('SKIP: hand-built wasi module is invalid - ' + e.message); process.exit(1); }
const b64 = (u8) => Buffer.from(u8).toString('base64');

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

// ---- arm 1: the Linux ABI (busybox rm), which is what the real incidents used -------
const CALL_LINUX = [
  'rm -f /root/.allow-sandpie-delete 2>/dev/null',
  'mkdir -p /root/sandpie/conversations /root/e2e-scratch',
  'echo protected > /root/sandpie/conversations/e2e-probe.json',
  'echo scratch  > /root/e2e-scratch/probe.json',
  // the exact shape of both incidents
  'rm -rf /root/sandpie 2>/tmp/e1; echo "rmtree_rc=$?"',
  'echo "survived_tree=$([ -f /root/sandpie/conversations/e2e-probe.json ] && echo yes || echo no)"',
  'rm -f /root/sandpie/conversations/e2e-probe.json 2>/tmp/e2; echo "rmfile_rc=$?"',
  'echo "survived_file=$([ -f /root/sandpie/conversations/e2e-probe.json ] && echo yes || echo no)"',
  // CONTROL: the identical operation outside the workspace must still work
  'rm -rf /root/e2e-scratch; echo "control_rc=$?"',
  'echo "control_gone=$([ -e /root/e2e-scratch ] && echo no || echo yes)"',
  // CONTROL: a rename INSIDE the workspace is an edit, not a deletion -- still allowed
  'mv /root/sandpie/conversations/e2e-probe.json /root/sandpie/conversations/e2e-probe2.json 2>/dev/null; echo "inner_mv_rc=$?"',
  'mv /root/sandpie/conversations/e2e-probe2.json /root/sandpie/conversations/e2e-probe.json 2>/dev/null',
  // ...but moving it OUT is a deletion by another name
  'mv /root/sandpie/conversations/e2e-probe.json /root/escaped.json 2>/dev/null; echo "escape_mv_rc=$?"',
  'echo "survived_escape=$([ -f /root/sandpie/conversations/e2e-probe.json ] && echo yes || echo no)"',
].join('\n');

// ---- arm 2: the WASI ABI, the hole this test was written for ------------------------
const CALL_WASI = [
  'mkdir -p /root/sandpie/conversations /root/e2e-scratch',
  'echo protected > /root/sandpie/conversations/e2e-probe.json',
  'echo scratch  > /root/e2e-scratch/probe.json',
  'echo "' + b64(modProtected) + '" | base64 -d > /root/wasi-prot.wasm && chmod +x /root/wasi-prot.wasm',
  'echo "' + b64(modScratch) + '" | base64 -d > /root/wasi-scratch.wasm && chmod +x /root/wasi-scratch.wasm',
  // CONTROL FIRST: if the unprotected unlink does not return 0 the guest never reached
  // the handler, and the protected result below would prove nothing.
  '/root/wasi-scratch.wasm; echo "wasi_control_errno=$?"',
  'echo "wasi_control_gone=$([ -e /root/e2e-scratch/probe.json ] && echo no || echo yes)"',
  '/root/wasi-prot.wasm; echo "wasi_protected_errno=$?"',
  'echo "wasi_survived=$([ -f /root/sandpie/conversations/e2e-probe.json ] && echo yes || echo no)"',
].join('\n');

// ---- arm 3: the documented escape hatch must still let a deliberate wipe through ----
const CALL_SENTINEL = [
  'touch /root/.allow-sandpie-delete',
  'rm -rf /root/sandpie/conversations; echo "override_rc=$?"',
  'echo "override_gone=$([ -e /root/sandpie/conversations ] && echo no || echo yes)"',
  'rm -f /root/.allow-sandpie-delete /root/wasi-prot.wasm /root/wasi-scratch.wasm /root/escaped.json',
  'rm -rf /root/e2e-scratch',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const run = (script) => page.evaluate(async (script) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('TIMED OUT'), 200000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args: { timeout: 190, script } });
    });
  }, script);

  console.log('\n-- Linux ABI (busybox rm) --');
  const a = String(await run(CALL_LINUX));
  console.log('    ' + a.replace(/\n/g, '\n    '));
  check('CONTROL: rm -rf outside the workspace still works',
    /control_rc=0/.test(a) && /control_gone=yes/.test(a), a);
  check('CONTROL: a rename INSIDE the workspace is still allowed', /inner_mv_rc=0/.test(a), a);
  check('rm -rf /root/sandpie does not take the workspace', /survived_tree=yes/.test(a), a);
  check('rm of a single conversation file is refused', /rmfile_rc=[1-9]/.test(a) && /survived_file=yes/.test(a), a);
  check('moving a protected path OUT is refused', /survived_escape=yes/.test(a), a);

  console.log('\n-- WASI ABI (path_unlink_file) --');
  const b = String(await run(CALL_WASI));
  console.log('    ' + b.replace(/\n/g, '\n    '));
  check('CONTROL: the wasi guest really reaches path_unlink_file (errno 0 off-workspace)',
    /wasi_control_errno=0/.test(b) && /wasi_control_gone=yes/.test(b), b);
  check('path_unlink_file on the workspace returns EPERM (63), not success',
    /wasi_protected_errno=63/.test(b), b);
  check('the protected file survives the wasi unlink', /wasi_survived=yes/.test(b), b);

  console.log('\n-- escape hatch --');
  const c = String(await run(CALL_SENTINEL));
  console.log('    ' + c.replace(/\n/g, '\n    '));
  check('.allow-sandpie-delete still permits a deliberate wipe',
    /override_rc=0/.test(c) && /override_gone=yes/.test(c), c);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
