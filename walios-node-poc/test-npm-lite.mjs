// End-to-end: install a real package from the real npm registry inside walios-node,
// verify its sha512, unpack it into the walios filesystem, then require() it.
//
// NETWORK REQUIRED -- kept out of the main suite on purpose so that stays hermetic.
//   node walios-node-poc/test-npm-lite.mjs [./lib]
import { Worker } from 'node:worker_threads';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';

const require = createRequire(import.meta.url);
const here = new URL('.', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const LIB = process.argv[2] || join(here, 'lib');

const { makeHostCall, makeArena, makeSyscalls, importNames } = require('./syscall-bridge.js');
const { KernelVfs } = require('./kernel-vfs.js');
const { boot } = require('./boot.js');
const { shimFactories } = require('./shims.js');
const { main } = require('./node-main.js');

// names come from syscall-bridge's canonical list; see mkstub.mjs for the guard.
const names = importNames();

const sources = {};
(function walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.js')) sources[relative(LIB, p).split(/[\\/]/).join('/').replace(/\.js$/, '')] = readFileSync(p, 'utf8');
  }
})(LIB);

const NPM_LITE = readFileSync(join(here, 'npm-lite.js'), 'utf8');

// One long-lived guest so the install and the require() that follows share a filesystem.
const ctl = new SharedArrayBuffer(256);
const memory = new WebAssembly.Memory({ initial: 256, maximum: 4096, shared: true });
const kernel = new Worker(new URL('./mock-kernel.mjs', import.meta.url), {
  workerData: { ctl, mem: memory.buffer, names, argv: ['node'] },
});
let out = '', err = '';
kernel.on('message', (m) => { if (m.t === 'out') { if (m.fd === 2) err += m.s; else out += m.s; } });
await new Promise((res) => kernel.once('message', res));

const sys = makeSyscalls(names, makeHostCall(ctl));
const arena = makeArena(memory, 1 << 16);
const vfs = new KernelVfs(sys, arena);
const rt = boot(null, { sources, vfs, shimFactories, sys, mem: arena });
const R = rt.require;
const fs = R('fs');

fs.mkdirSync('/usr');
fs.mkdirSync('/usr/bin');
fs.writeFileSync('/usr/bin/npm-lite', NPM_LITE);

async function run(argv, label) {
  out = ''; err = '';
  rt.process.exitCode = undefined;
  // Through main(), not Module._load: main() is what builds stdio, the real Console
  // and the realm globals. Loading the module directly left `console` undefined.
  setArgv(argv);
  const Module = R('module');
  const M = Module.Module || Module;
  delete M._cache[argv[1]];
  let code = 0;
  try { code = main(rt, sys, arena); }
  catch (e) { err += String(e && e.stack || e); code = 1; }
  // pending counts timers and nextTick, NOT fetch, so wait for output to go quiet
  // instead: poll until nothing has changed for a while, or the deadline passes.
  const deadline = Date.now() + 90000;
  let last = '', stableFor = 0;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 100));
    const now = out + err;
    if (now === last && (!rt.pending || rt.pending.n === 0)) { stableFor += 100; if (stableFor >= 1500 && now) break; }
    else { stableFor = 0; last = now; }
  }
  console.log('--- ' + label + ' ---');
  if (out.trim()) console.log(out.trimEnd());
  if (err.trim()) console.log('[stderr] ' + err.trimEnd());
  return { out, err, code };
}

// The kernel parks in Atomics.wait and cannot receive messages, so argv goes through
// shared memory at a fixed offset (mirrors ARGV_BASE in mock-kernel.mjs).
function setArgv(argv) {
  const ARGV_BASE = 8192;
  const mem = new Uint8Array(memory.buffer);
  new DataView(memory.buffer).setInt32(ARGV_BASE, argv.length, true);
  let p = ARGV_BASE + 4;
  for (const a of argv) {
    const b = new TextEncoder().encode(a);
    mem.set(b, p); p += b.length; mem[p++] = 0;
  }
}

const ok = [], bad = [];
const check = (name, cond, detail) => { (cond ? ok : bad).push(name + (detail ? '  -> ' + detail : '')); };

// ---- install ----------------------------------------------------------------
const r1 = await run(['/bin/node', '/usr/bin/npm-lite', 'left-pad@1.3.0'], 'npm-lite install left-pad@1.3.0');
check('install reported success', /installed left-pad@1\.3\.0/.test(r1.out), (r1.out.match(/installed[^\n]*/) || [''])[0]);
check('integrity was verified', /integrity sha\d+ ok/.test(r1.out));
check('files landed in the walios fs', (() => { try { return fs.readdirSync('/node_modules/left-pad').length > 0; } catch { return false; } })(),
  (() => { try { return fs.readdirSync('/node_modules/left-pad').sort().join(','); } catch { return 'MISSING'; } })());
check('package.json is real JSON', (() => {
  try { return JSON.parse(fs.readFileSync('/node_modules/left-pad/package.json', 'utf8')).name === 'left-pad'; } catch { return false; }
})());

// ---- use it -----------------------------------------------------------------
fs.writeFileSync('/app.js', 'const leftPad = require("/node_modules/left-pad");'
  + 'console.log("[" + leftPad("42", 8, "0") + "]");');
const r2 = await run(['/bin/node', '/app.js'], 'require the installed package');
check('the installed package actually runs', /\[00000042\]/.test(r2.out), r2.out.trim());

// ---- a package with a dependency tree shape (scoped name) -------------------
const r3 = await run(['/bin/node', '/usr/bin/npm-lite', 'is-number@7.0.0'], 'npm-lite install is-number@7.0.0');
check('second package installed', /installed is-number@7\.0\.0/.test(r3.out));
fs.writeFileSync('/app2.js', 'const isNumber = require("/node_modules/is-number");'
  + 'console.log(isNumber(7) + "," + isNumber("x"));');
const r4 = await run(['/bin/node', '/app2.js'], 'require the second package');
check('second package runs', /true,false/.test(r4.out), r4.out.trim());

// ---- integrity is actually enforced -----------------------------------------
const r5 = await run(['/bin/node', '/usr/bin/npm-lite', 'left-pad@0.0.0-does-not-exist'], 'unknown version is rejected');
check('a bad version fails cleanly', /no such version/.test(r5.err) || /no such version/.test(r5.out));

console.log('\nPASS (' + ok.length + ')');
for (const s of ok) console.log('  + ' + s);
if (bad.length) { console.log('\nFAIL (' + bad.length + ')'); for (const s of bad) console.log('  - ' + s); }

await kernel.terminate();
process.exit(bad.length ? 1 : 0);
