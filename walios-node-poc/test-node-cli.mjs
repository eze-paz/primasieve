// Rung one, headless: `node -e ...` and `node script.js` driven through the walios
// syscall protocol. argv comes from the kernel, stdout is node's own SyncWriteStream
// over SYS_write, console is node's real Console.
//
// Each case spawns a fresh mock kernel with its own argv, exactly as the kernel would
// hand a new process its argv.
import { Worker } from 'node:worker_threads';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';

const require = createRequire(import.meta.url);
const here = new URL('.', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const LIB = process.argv[2] || join(here, 'lib');

const { makeHostCall, makeArena, makeSyscalls } = require('./syscall-bridge.js');
const { KernelVfs } = require('./kernel-vfs.js');
const { boot } = require('./boot.js');
const { main } = require('./node-main.js');

const SYSCALLS = ['open', 'openat', 'close', 'read', 'write', 'lseek', 'fstat', 'stat',
  'lstat', 'newfstatat', 'mkdir', 'rmdir', 'unlink', 'getdents64', 'access',
  'ioctl', 'dup', 'fcntl', 'rename',
  'ftruncate', 'fsync', 'readlink', 'chdir', 'getcwd', 'exit_group', 'exit'];
const names = [...SYSCALLS.map((n) => 'wali.SYS_' + n),
  'wali.__cl_get_argc', 'wali.__cl_get_argv_len', 'wali.__cl_copy_argv', 'wali.__proc_exit'];

// node's lib/, loaded once
const sources = {};
(function walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.js')) sources[relative(LIB, p).split(/[\\/]/).join('/').replace(/\.js$/, '')] = readFileSync(p, 'utf8');
  }
})(LIB);

// Run one `node ...` invocation against a fresh kernel. `seed` writes files first.
async function runNode(argv, seed, opts) {
  opts = opts || {};
  const ctl = new SharedArrayBuffer(256);
  const memory = new WebAssembly.Memory({ initial: 256, maximum: 4096, shared: true });
  const kernel = new Worker(new URL('./mock-kernel.mjs', import.meta.url), {
    workerData: { ctl, mem: memory.buffer, names, argv, stdin: opts.stdin || null, tty: !!opts.tty },
  });
  let out = '', err = '';
  kernel.on('message', (m) => { if (m.t === 'out') { if (m.fd === 2) err += m.s; else out += m.s; } });
  await new Promise((res) => kernel.once('message', res));

  const sys = makeSyscalls(names, makeHostCall(ctl));
  const arena = makeArena(memory, 1 << 16);
  const vfs = new KernelVfs(sys, arena);
  const rt = boot(null, { sources, vfs });
  if (seed) seed(rt.require('fs'));

  let code, thrown = null;
  try { code = main(rt, sys, arena); }
  catch (e) { thrown = e; code = 139; }
  // Same exit rule as the worker: wait for outstanding async work.
  const deadline = Date.now() + 5000;
  while (rt.pending && rt.pending.n > 0 && Date.now() < deadline) await new Promise((r) => setTimeout(r, 1));
  if (typeof rt.process.exitCode === 'number') code = rt.process.exitCode;
  await new Promise((r) => setTimeout(r, 30));      // let stdout flush
  await kernel.terminate();
  return { out, err, code, thrown, calls: vfs.calls };
}

const ok = [], bad = [];
async function t(name, argv, expect, seed, opts) {
  try {
    const r = await runNode(argv, seed, opts);
    if (r.thrown) throw r.thrown;
    const got = (r.out + (r.err ? '[stderr] ' + r.err : '')).trim();
    const pass = typeof expect === 'function' ? expect(r) : got === expect;
    if (!pass) throw new Error('got ' + JSON.stringify(got) + ' exit=' + r.code);
    ok.push(name + '  -> ' + JSON.stringify(got.slice(0, 68)) + ' (exit ' + r.code + ')');
  } catch (e) { bad.push(name + '\n      ' + String((e && e.message) || e).split('\n')[0]); }
}

console.log('=== `node` at the walios shell (headless, real syscalls) ===\n');

await t('node -e "console.log(2+2)"', ['/bin/node', '-e', 'console.log(2+2)'], '4');
await t('node -e with string', ['/bin/node', '-e', 'console.log("hello walios")'], 'hello walios');
await t('node -e console.log %s/%d', ['/bin/node', '-e', 'console.log("%s:%d","x",7)'], 'x:7');
await t('node -e object inspect', ['/bin/node', '-e', 'console.log({a:[1,2]})'], '{ a: [ 1, 2 ] }');
await t('node -p "1+1"', ['/bin/node', '-p', '1+1'], '2');
await t('node -p object', ['/bin/node', '-p', '({x:1})'], '{ x: 1 }');
await t('node -v', ['/bin/node', '-v'], (r) => /^v\d+\./.test(r.out.trim()) && r.code === 0);
await t('node -h', ['/bin/node', '-h'], (r) => r.out.includes('Usage: node') && r.code === 0);
await t('node --eval process.argv0', ['/bin/node', '--eval', 'console.log(process.argv0)'], 'node');
await t('node -e process.platform', ['/bin/node', '-e', 'console.log(process.platform)'], 'linux');
await t('node -e require("path")', ['/bin/node', '-e', 'console.log(require("path").join("/a","b/../c"))'], '/a/c');
await t('node -e console.error -> stderr', ['/bin/node', '-e', 'console.error("boom")'],
  (r) => r.err.trim() === 'boom' && r.out === '');
await t('node -e throws -> exit 1', ['/bin/node', '-e', 'throw new Error("nope")'],
  (r) => r.code === 1 && /nope/.test(r.err));
await t('node -e process.exitCode', ['/bin/node', '-e', 'console.log("bye")'], 'bye');
await t('node -e fs write+read (real syscalls)',
  ['/bin/node', '-e', 'const fs=require("fs");fs.writeFileSync("/tmp/cli","via node -e");console.log(fs.readFileSync("/tmp/cli","utf8"))'],
  'via node -e');
await t('node -e reads a shell-seeded file',
  ['/bin/node', '-e', 'console.log(require("fs").readFileSync("/etc/hosts","utf8").trim())'],
  '127.0.0.1 localhost');
await t('node script.js', ['/bin/node', '/app/hello.js'], 'hello from a script',
  (fs) => { fs.mkdirSync('/app'); fs.writeFileSync('/app/hello.js', 'console.log("hello from a script")'); });
await t('node script.js with args', ['/bin/node', '/app/args.js', 'one', 'two'], 'one,two',
  (fs) => { fs.mkdirSync('/app'); fs.writeFileSync('/app/args.js', 'console.log(process.argv.slice(2).join(","))'); });
await t('node script.js requires a sibling', ['/bin/node', '/app/main.js'], 'lib says 42',
  (fs) => {
    fs.mkdirSync('/app');
    fs.writeFileSync('/app/dep.js', 'module.exports = 42;');
    fs.writeFileSync('/app/main.js', 'console.log("lib says " + require("./dep.js"))');
  });
await t('node script.js does fs work', ['/bin/node', '/app/w.js'], 'wrote 11',
  (fs) => {
    fs.mkdirSync('/app');
    fs.writeFileSync('/app/w.js', 'const fs=require("fs");fs.writeFileSync("/tmp/o","hello world");console.log("wrote "+fs.statSync("/tmp/o").size)');
  });
await t('node missing.js -> exit 1', ['/bin/node', '/app/nope.js'], (r) => r.code === 1 && /cannot find module/i.test(r.err));

await t('node --bogus -> exit 9', ['/bin/node', '--bogus'], (r) => r.code === 9 && /bad option/.test(r.err));

// ---- stdin + REPL ----------------------------------------------------------
// N avoids backslash escapes entirely: this file has been mangled twice by them.
const N = String.fromCharCode(10);
await t('echo "..." | node  (script from stdin)', ['/bin/node'], 'from stdin', null,
  { stdin: 'console.log("from stdin")' + N });
await t('node < file  (multi-line stdin script)', ['/bin/node'], 'a' + N + 'b', null,
  { stdin: 'console.log("a");' + N + 'console.log("b");' + N });
await t('stdin script can require()', ['/bin/node'], '/x/y', null,
  { stdin: 'console.log(require("path").join("/x","y"))' + N });
await t('stdin script sees process.argv0', ['/bin/node'], 'node', null,
  { stdin: 'console.log(process.argv0)' + N });
await t('bare node, no stdin -> usage, exit 1', ['/bin/node'],
  (r) => r.code === 1 && /nothing on stdin/.test(r.err));
await t('REPL: 2+2', ['/bin/node'], (r) => /(^|\s)4(\s|$)/m.test(r.out) && r.code === 0,
  null, { tty: true, stdin: '2+2' + N + '.exit' + N });
await t('REPL: const persists across lines', ['/bin/node'],
  (r) => /walios-repl/.test(r.out) && r.code === 0,
  null, { tty: true, stdin: 'const who = "walios-repl"' + N + 'who' + N + '.exit' + N });
await t('REPL: require works', ['/bin/node'], (r) => /\/a\/b/.test(r.out),
  null, { tty: true, stdin: 'require("path").join("/a","b")' + N + '.exit' + N });
await t('REPL: multi-line continuation', ['/bin/node'], (r) => /(^|\s)3(\s|$)/m.test(r.out),
  null, { tty: true, stdin: 'function f() {' + N + 'return 3' + N + '}' + N + 'f()' + N + '.exit' + N });
await t('REPL: an error does not kill the session', ['/bin/node'],
  (r) => /ReferenceError/.test(r.err) && /(^|\s)7(\s|$)/m.test(r.out) && r.code === 0,
  null, { tty: true, stdin: 'nope_not_defined' + N + '7' + N + '.exit' + N });
await t('REPL: Ctrl-D (EOF) exits 0', ['/bin/node'], (r) => r.code === 0,
  null, { tty: true, stdin: '1+1' + N });
await t('REPL: .clear forgets the scope', ['/bin/node'],
  (r) => /scope cleared/.test(r.out) && /ReferenceError/.test(r.err),
  null, { tty: true, stdin: 'const z = 1' + N + '.clear' + N + 'z' + N + '.exit' + N });
await t('REPL: console.log inside the REPL', ['/bin/node'], (r) => /repl-log/.test(r.out),
  null, { tty: true, stdin: 'console.log("repl-log")' + N + '.exit' + N });
await t('REPL: fs works (real syscalls)', ['/bin/node'], (r) => /etc-ok/.test(r.out),
  null, { tty: true, stdin: 'require("fs").readFileSync("/etc/hosts","utf8") ? "etc-ok" : "no"' + N + '.exit' + N });


// ---- async: timers, promises, nextTick, fs.promises -------------------------
await t('setTimeout fires before exit', ['/bin/node', '-e', 'setTimeout(()=>console.log("TIMER"),5)'], 'TIMER');
await t('setImmediate fires', ['/bin/node', '-e', 'setImmediate(()=>console.log("IMM"))'], 'IMM');
await t('process.nextTick fires', ['/bin/node', '-e', 'process.nextTick(()=>console.log("TICK"))'], 'TICK');
await t('nextTick runs after main body', ['/bin/node', '-e', 'process.nextTick(()=>console.log("B"));console.log("A")'], 'A' + N + 'B');
await t('promise .then', ['/bin/node', '-e', 'Promise.resolve("P").then(v=>console.log(v))'], 'P');
await t('async/await', ['/bin/node', '-e', '(async()=>{console.log(await Promise.resolve("AW"))})()'], 'AW');
await t('await fs.promises.readFile', ['/bin/node', '-e',
  '(async()=>{const s=await require("fs").promises.readFile("/etc/hosts","utf8");console.log(s.trim())})()'],
  '127.0.0.1 localhost');
await t('await fs.promises write+read round trip', ['/bin/node', '-e',
  '(async()=>{const fsp=require("fs").promises;await fsp.writeFile("/tmp/p.txt","promised");console.log(await fsp.readFile("/tmp/p.txt","utf8"))})()'],
  'promised');
await t('await fs.promises.readdir', ['/bin/node', '-e',
  '(async()=>{const d=await require("fs").promises.readdir("/etc");console.log(d.sort().join(","))})()'],
  'gitconfig,hosts,passwd');
await t('await fs.promises.stat', ['/bin/node', '-e',
  '(async()=>{const st=await require("fs").promises.stat("/etc/hosts");console.log("size="+(st.size>0))})()'],
  'size=true');
await t('fs.promises.mkdir + rm round trip', ['/bin/node', '-e',
  '(async()=>{const fsp=require("fs").promises;await fsp.mkdir("/tmp/pd");await fsp.writeFile("/tmp/pd/f","x");console.log((await fsp.readdir("/tmp/pd")).join(","))})()'],
  'f');
await t('async exitCode is honoured', ['/bin/node', '-e', 'setTimeout(()=>{process.exitCode=4},2)'],
  (r) => r.code === 4);
await t('rejected promise surfaces', ['/bin/node', '-e',
  '(async()=>{try{await require("fs").promises.readFile("/nope/x")}catch(e){console.log("caught "+e.code)}})()'],
  'caught ENOENT');

console.log('PASS (' + ok.length + ')');
for (const s of ok) console.log('  + ' + s);
if (bad.length) { console.log('\nFAIL (' + bad.length + ')'); for (const s of bad) console.log('  - ' + s); }
process.exit(bad.length ? 1 : 0);
