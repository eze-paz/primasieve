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
  // node's resolver caches path lookups (_pathCache) and stat results across a
  // require tree. A file written AFTER a previous run had already looked for it is
  // remembered as missing -- which is why /app.js "could not be found" moments after
  // being written, while a file whose name had never been looked up resolved fine.
  delete M._cache[argv[1]];
  if (M._pathCache) for (const k of Object.keys(M._pathCache)) delete M._pathCache[k];
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

// pull one matching line out of output without embedding a newline in a regex
const firstLine = (s, needle) => (s.split(String.fromCharCode(10)).find((l) => l.includes(needle)) || '').trim();

const ok = [], bad = [];
const check = (name, cond, detail) => { (cond ? ok : bad).push(name + (detail ? '  -> ' + detail : '')); };

// ---- real packages, with real dependency trees -----------------------------
const r1 = await run(['/bin/node', '/usr/bin/npm-lite', 'debug@4.3.4'], 'install debug@4.3.4 (has deps)');
check('debug installed', /debug@4\.3\.4/.test(r1.out));
check('its dependency ms came too', /ms@/.test(r1.out), firstLine(r1.out, 'ms@'));

fs.writeFileSync('/use-debug.js',
  'const debug = require("/node_modules/debug");'
  + 'const log = debug("demo");'
  + 'console.log("debug loaded, enabled=" + (typeof log === "function"));');
console.log('  [probe] /app.js exists=' + fs.existsSync('/use-debug.js')
  + ' size=' + (fs.existsSync('/use-debug.js') ? fs.statSync('/use-debug.js').size : -1)
  + ' root=' + JSON.stringify(fs.readdirSync('/').sort().slice(0, 12)));
const r2 = await run(['/bin/node', '/use-debug.js'], 'require debug (resolves ms through the tree)');
check('debug requires and runs', /debug loaded, enabled=true/.test(r2.out), r2.out.trim());

// minimatch pulls brace-expansion -> balanced-match + concat-map: a 3-deep tree
const r3 = await run(['/bin/node', '/usr/bin/npm-lite', 'minimatch@5.1.6'], 'install minimatch@5.1.6 (deep tree)');
check('minimatch tree installed', /installed [2-9] package/.test(r3.out), firstLine(r3.out, 'installed'));

check('transitive dep came too', /balanced-match@|brace-expansion@/.test(r3.out));

fs.writeFileSync('/use-minimatch.js',
  'const mm = require("/node_modules/minimatch");'
  + 'const f = mm.minimatch || mm;'
  + 'console.log("minimatch: " + f("src/a.js", "src/*.js") + "," + f("src/a.js", "*.ts"));');
const r4 = await run(['/bin/node', '/use-minimatch.js'], 'require minimatch and actually glob');
check('minimatch runs its real logic', /minimatch: true,false/.test(r4.out), r4.out.trim());

// a big single package: ~1000 files, exercises the tar/write path at scale
const r5 = await run(['/bin/node', '/usr/bin/npm-lite', 'lodash@4.17.21'], 'install lodash (1000+ files)');
check('lodash installed', /lodash@4\.17\.21/.test(r5.out), firstLine(r5.out, 'installed'));

fs.writeFileSync('/use-lodash.js',
  'const _ = require("/node_modules/lodash");'
  + 'console.log("lodash: " + _.chunk([1,2,3,4],2).length + "," + _.camelCase("hello world"));');
const r6 = await run(['/bin/node', '/use-lodash.js'], 'require lodash and call it');
check('lodash runs', /lodash: 2,helloWorld/.test(r6.out), r6.out.trim());

const r7 = await run(['/bin/node', '/usr/bin/npm-lite', 'left-pad@0.0.0-nope'], 'a bad range fails cleanly');
check('unsatisfiable range is rejected', /no version of left-pad satisfies/.test(r7.err + r7.out));


console.log('\nPASS (' + ok.length + ')');
for (const s of ok) console.log('  + ' + s);
if (bad.length) { console.log('\nFAIL (' + bad.length + ')'); for (const s of bad) console.log('  - ' + s); }

await kernel.terminate();
process.exit(bad.length ? 1 : 0);
