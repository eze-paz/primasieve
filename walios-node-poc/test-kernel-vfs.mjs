// Headless verification of the Phase-1 guest half.
//
// Main thread = the GUEST (node's lib/fs.js -> bindings.js -> kernel-vfs.js ->
// syscall-bridge.js), parking in Atomics.wait exactly as node-proc-worker.js does.
// Worker thread = a mock kernel speaking wali-worker.js's wire format.
//
// This exercises the REAL bridge/vfs code -- the same files the browser worker loads.
import { Worker } from 'node:worker_threads';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const require = createRequire(import.meta.url);
const here = new URL('.', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const LIB = process.argv[2] || join(here, 'lib');

const { makeHostCall, makeArena, makeSyscalls, importNames } = require('./syscall-bridge.js');
const { KernelVfs } = require('./kernel-vfs.js');
const { boot } = require('./boot.js');
const { shimFactories } = require('./shims.js');

// The import list the kernel would build from node-stub.wasm, in the same order.
// names come from syscall-bridge's canonical list; see mkstub.mjs for the guard.
const names = importNames();

const ctl = new SharedArrayBuffer(256);
const memory = new WebAssembly.Memory({ initial: 256, maximum: 4096, shared: true });

const kernel = new Worker(new URL('./mock-kernel.mjs', import.meta.url), {
  workerData: { ctl, mem: memory.buffer, names },
});
let kernelErrors = [];
kernel.on('message', (m) => {
  if (m.t === 'out') process.stdout.write(m.s);
  else if (m.t === 'kernel-error') kernelErrors.push(m.s);
});

await new Promise((res) => kernel.once('message', res));   // kernel-ready

// ---- load node's lib/ -------------------------------------------------------
const sources = {};
(function walk(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.js')) sources[relative(LIB, p).split(/[\\/]/).join('/').replace(/\.js$/, '')] = readFileSync(p, 'utf8');
  }
})(LIB);

// ---- the guest --------------------------------------------------------------
const hostCall = makeHostCall(ctl);
const sys = makeSyscalls(names, hostCall);
const arena = makeArena(memory, 1 << 16);
const vfs = new KernelVfs(sys, arena);
const rt = boot(null, { sources, vfs, shimFactories, sys, mem: arena });
const R = rt.require;

const ok = [], bad = [];
const t = (n, fn) => { try { const r = fn(); ok.push(n + (r === undefined ? '' : '  -> ' + r)); } catch (e) { bad.push(n + '\n      ' + String((e && e.message) || e).split('\n')[0]); } };

console.log('=== node lib/fs.js over the walios syscall protocol (mock kernel) ===\n');

const fs = R('fs');
const Buffer = R('buffer').Buffer;

t('fs.mkdirSync            [SYS_mkdir]', () => { fs.mkdirSync('/tmp/np'); return 'ok'; });
t('fs.writeFileSync        [SYS_open+write]', () => { fs.writeFileSync('/tmp/np/x', 'hi from node lib'); return 'wrote through syscalls'; });
t('fs.readFileSync utf8    [SYS_open+read]', () => fs.readFileSync('/tmp/np/x', 'utf8'));
t('fs.readFileSync buffer', () => { const b = fs.readFileSync('/tmp/np/x'); return b.constructor.name + '(' + b.length + ') = ' + b.toString(); });
t('fs.existsSync           [SYS_stat]', () => fs.existsSync('/tmp/np/x'));
t('fs.statSync().size', () => fs.statSync('/tmp/np/x').size);
t('fs.statSync().isFile()', () => fs.statSync('/tmp/np/x').isFile());
t('fs.statSync("/").isDirectory()', () => fs.statSync('/').isDirectory());
t('fs.statSync().mtime is a Date', () => fs.statSync('/tmp/np/x').mtime instanceof Date);
t('fs.readdirSync          [SYS_getdents64]', () => {
  fs.writeFileSync('/tmp/np/a.txt', 'a'); fs.writeFileSync('/tmp/np/b.txt', 'b');
  return JSON.stringify(fs.readdirSync('/tmp/np').sort());
});
t('fs.appendFileSync', () => { fs.appendFileSync('/tmp/np/x', '!'); return fs.readFileSync('/tmp/np/x', 'utf8'); });
t('fs.unlinkSync           [SYS_unlink]', () => { fs.unlinkSync('/tmp/np/a.txt'); return JSON.stringify(fs.readdirSync('/tmp/np').sort()); });
t('fs.renameSync           [SYS_rename]', () => { fs.renameSync('/tmp/np/b.txt', '/tmp/np/c.txt'); return JSON.stringify(fs.readdirSync('/tmp/np').sort()); });
t('binary round-trip 256B', () => {
  const b = Buffer.alloc(256); for (let i = 0; i < 256; i++) b[i] = i;
  fs.writeFileSync('/tmp/np/bin', b);
  const rb = fs.readFileSync('/tmp/np/bin');
  if (Buffer.compare(b, rb) !== 0) throw new Error('binary mismatch');
  return rb.length + ' bytes identical across the SAB';
});
t('64KB file (multi-read path)', () => {
  const big = Buffer.alloc(65536, 0x5a);
  fs.writeFileSync('/tmp/np/big', big);
  const back = fs.readFileSync('/tmp/np/big');
  if (Buffer.compare(big, back) !== 0) throw new Error('mismatch at ' + back.length);
  return back.length + ' bytes';
});
t('ENOENT is a real fs error', () => { try { fs.readFileSync('/nope/missing', 'utf8'); return 'NO THROW (bad)'; } catch (e) { return e.code + ' / ' + (e.syscall || '?'); } });
t('EEXIST on mkdir of existing', () => { try { fs.mkdirSync('/tmp/np'); return 'NO THROW (bad)'; } catch (e) { return e.code; } });
t('reads files the "shell" seeded', () => {
  const etc = fs.readdirSync('/etc').sort();
  return '/etc = ' + JSON.stringify(etc) + ' gitconfig=' + JSON.stringify(fs.readFileSync('/etc/gitconfig', 'utf8').slice(0, 12));
});
t('0-length write issues NO syscall  [pipe EOF regression]', () => {
  const before = vfs.calls;
  const n = vfs.write(1, new Uint8Array(0), null);
  if (n !== 0) throw new Error('expected 0, got ' + n);
  if (vfs.calls !== before) throw new Error('a syscall was issued for a 0-length write');
  return 'returned 0, no syscall';
});
t('fs.readFileSync on a dir throws EISDIR', () => { try { fs.readFileSync('/etc'); return 'NO THROW (bad)'; } catch (e) { return e.code; } });

console.log('PASS (' + ok.length + ')');
for (const s of ok) console.log('  + ' + s);
if (bad.length) { console.log('\nFAIL (' + bad.length + ')'); for (const s of bad) console.log('  - ' + s); }
if (kernelErrors.length) { console.log('\nkernel errors:'); for (const s of kernelErrors) console.log('  ! ' + s); }

console.log('\nsyscalls issued    : ' + vfs.calls);
console.log('lib modules loaded : ' + rt.trace.loaded.length);
console.log('bindings requested : ' + rt.trace.bindings.size);
console.log('binding fns used   : ' + rt.trace.used.size);

await kernel.terminate();
process.exit(bad.length ? 1 : 0);
