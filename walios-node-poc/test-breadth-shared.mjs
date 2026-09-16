// How wide is the ecosystem, really?
//
// Installs a spread of genuinely popular packages, then REQUIRES each and calls
// something real. Installing proves the registry/tar/integrity path; requiring and
// calling is what proves the runtime. A package that unpacks but throws on require
// is a failure here, deliberately.
//
// NETWORK REQUIRED.  node walios-node-poc/test-breadth-shared.mjs
// Variant of test-breadth.mjs: ONE kernel, ONE /node_modules, everything
// installed before anything is required -- which is what a user does and what
// the per-package version never covered.
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

const names = importNames();
const sources = {};
(function walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.js')) sources[relative(LIB, p).split(/[\\/]/).join('/').replace(/\.js$/, '')] = readFileSync(p, 'utf8');
  }
})(LIB);

// name, version range, and an expression that must produce the expected string.
// Each `use` runs in its own script so one package cannot mask another.
const CASES = [
  ['lodash', '4.17.21', 'const _=R("lodash"); out(_.camelCase("hello world"))', 'helloWorld'],
  ['minimatch', '5.1.6', 'const m=R("minimatch"); const f=m.minimatch||m; out(f("a/b.js","a/*.js"))', 'true'],
  ['debug', '4.3.4', 'const d=R("debug"); out(typeof d("x"))', 'function'],
  ['ms', '2.1.3', 'out(R("ms")("1h"))', '3600000'],
  ['semver', '7.5.4', 'const s=R("semver"); out(s.satisfies("1.2.3","^1.0.0"))', 'true'],
  ['picomatch', '2.3.1', 'const p=R("picomatch"); out(p.isMatch("a/b.js","a/*.js"))', 'true'],
  ['chalk', '4.1.2', 'const c=R("chalk"); out(typeof c.red)', 'function'],
  ['commander', '9.5.0', 'const {Command}=R("commander"); out(typeof new Command().option)', 'function'],
  ['qs', '6.11.2', 'out(R("qs").stringify({a:1,b:"x"}))', 'a=1&b=x'],
  ['uuid', '8.3.2', 'const u=R("uuid"); out(u.v4().length)', '36'],
  ['js-yaml', '4.1.0', 'const y=R("js-yaml"); out(JSON.stringify(y.load("a: 1")))', '{"a":1}'],
  ['marked', '4.3.0', 'const m=R("marked"); const f=m.marked||m; out(/<h1/.test(f("# hi")))', 'true'],
  ['ejs', '3.1.9', 'const e=R("ejs"); out(e.render("<%= n %>",{n:"ok"}))', 'ok'],
  ['dayjs', '1.11.10', 'const d=R("dayjs"); out(d("2020-01-02").format("YYYY-MM"))', '2020-01'],
  ['moment', '2.29.4', 'const m=R("moment"); out(m("2020-01-02").format("YYYY-MM"))', '2020-01'],
  ['react', '18.2.0', 'const r=R("react"); out(typeof r.createElement)', 'function'],
  ['yargs-parser', '21.1.1', 'const y=R("yargs-parser"); out(y(["--a","1"]).a)', '1'],
  ['ajv', '8.12.0', 'const A=R("ajv"); const a=new A(); out(a.compile({type:"number"})(5))', 'true'],
  ['mkdirp', '1.0.4', 'out(typeof R("mkdirp"))', 'function'],
  ['balanced-match', '1.0.2', 'const b=R("balanced-match"); out(b("{","}","a{b}c").body)', 'b'],
  ['node-fetch', '2.7.0', 'out(typeof R("node-fetch"))', 'function'],
  ['axios', '1.6.2', 'const a=R("axios"); out(typeof a.get)', 'function'],
  ['express', '4.18.2', 'const e=R("express"); out(typeof e())', 'function'],
];

const ctl = new SharedArrayBuffer(256);
const memory = new WebAssembly.Memory({ initial: 512, maximum: 8192, shared: true });
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

fs.mkdirSync('/usr'); fs.mkdirSync('/usr/bin');
fs.writeFileSync('/usr/bin/npm-lite', readFileSync(join(here, 'npm-lite.js'), 'utf8'));

function setArgv(argv) {
  const ARGV_BASE = 8192;
  const mem = new Uint8Array(memory.buffer);
  new DataView(memory.buffer).setInt32(ARGV_BASE, argv.length, true);
  let p = ARGV_BASE + 4;
  for (const a of argv) { const b = new TextEncoder().encode(a); mem.set(b, p); p += b.length; mem[p++] = 0; }
}

async function run(argv) {
  out = ''; err = '';
  rt.process.exitCode = undefined;
  setArgv(argv);
  const Module = R('module');
  const M = Module.Module || Module;
  delete M._cache[argv[1]];
  if (M._pathCache) for (const k of Object.keys(M._pathCache)) delete M._pathCache[k];
  try { await main(rt, sys, arena); } catch (e) { err += String((e && e.message) || e); }
  const deadline = Date.now() + 120000;
  let last = '', stable = 0;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 80));
    const now = out + err;
    if (now === last && (!rt.pending || rt.pending.n === 0)) { stable += 80; if (stable >= 900 && now) break; }
    else { stable = 0; last = now; }
  }
  return { out: out.trim(), err: err.trim() };
}

const NL = String.fromCharCode(10);
const rows = [];
// PHASE 1: install everything into the one tree.
for (const [name, range] of CASES) {
  const inst = await run(['/bin/node', '/usr/bin/npm-lite', name + '@' + range]);
  const n = (inst.out.match(/installed (\d+) package/) || [])[1];
  console.log('  install ' + name.padEnd(16) + (n ? n + ' pkg' : 'FAILED: ' + (inst.err || inst.out).split(NL)[0].slice(0, 60)));
}
console.log('');
// PHASE 2: now require each, against the accumulated tree.
for (const [name, range, useSrc, expect] of CASES) {
  const t0 = Date.now();
  {
  const pkgs = 'shared';
  const script = '/use-' + name.replace(/[^a-z0-9]/gi, '_') + '.js';
  fs.writeFileSync(script,
    // Require by BARE NAME, the way a user would: a path require skips the
    // package's `exports` map, which is how axios resolved to its ESM index.js
    // instead of the CJS build node itself would pick.
    'const R = (m) => require(m);' + NL
    + 'const out = (v) => console.log("RESULT:" + v);' + NL
    + useSrc + NL);
  const used = await run(['/bin/node', script]);
  const got = (used.out.match(/RESULT:(.*)/) || [])[1];
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  if (got === undefined) rows.push([name, 'REQUIRE FAIL', (used.err || used.out).split(NL)[0].slice(0, 72), pkgs + ' pkg, ' + secs + 's']);
  else if (String(got) !== expect) rows.push([name, 'WRONG', 'got ' + got + ', want ' + expect, pkgs + ' pkg, ' + secs + 's']);
  else rows.push([name, 'OK', got, pkgs + ' pkg, ' + secs + 's']);
  }
}

const ok = rows.filter((r) => r[1] === 'OK');
console.log(NL + '=== package breadth: ' + ok.length + '/' + rows.length + ' work end to end ===' + NL);
for (const [name, status, detail, meta] of rows) {
  console.log('  ' + status.padEnd(13) + name.padEnd(16) + (meta || '').padEnd(16) + detail);
}
await kernel.terminate();
process.exit(0);
