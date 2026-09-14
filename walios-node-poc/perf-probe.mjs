import { Worker } from 'node:worker_threads';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { makeHostCall, makeArena, makeSyscalls } = require('./syscall-bridge.js');
const { KernelVfs } = require('./kernel-vfs.js');
const SYSCALLS = ['open','openat','close','read','write','lseek','fstat','stat','lstat','newfstatat','mkdir','rmdir','unlink','getdents64','access','rename','ftruncate','fsync','readlink','chdir','getcwd','exit_group','exit'];
const names = [...SYSCALLS.map(n=>'wali.SYS_'+n),'wali.__cl_get_argc','wali.__cl_get_argv_len','wali.__cl_copy_argv','wali.__proc_exit'];
const ctl = new SharedArrayBuffer(256);
const memory = new WebAssembly.Memory({ initial: 256, maximum: 4096, shared: true });
const k = new Worker(new URL('./mock-kernel.mjs', import.meta.url), { workerData:{ctl, mem:memory.buffer, names} });
await new Promise(r=>k.once('message',r));
const sys = makeSyscalls(names, makeHostCall(ctl));
const vfs = new KernelVfs(sys, makeArena(memory, 1<<16));
// raw round trips
const N = 200000;
let t0 = Date.now();
for (let i=0;i<N;i++) sys.stat(vfs.mem.cstr('/etc/hosts'), vfs.mem.alloc(144)), vfs.mem.reset();
const raw = Date.now()-t0;
console.log('raw syscall round trip : ' + (raw*1e6/N).toFixed(0) + ' ns  (' + N.toLocaleString() + ' in ' + raw + 'ms)');
console.log('  => ' + Math.round(N/(raw/1000)).toLocaleString() + ' syscalls/sec');
// a realistic "write one package file" op (open+write+close = 3 syscalls)
t0 = Date.now();
const M = 20000;
for (let i=0;i<M;i++){ const fd = vfs.open('/tmp/f'+(i%500), 0o1101, 0o644); vfs.write(fd, new Uint8Array(512), null); vfs.close(fd); }
const w = Date.now()-t0;
console.log('write a 512B file      : ' + (w*1000/M).toFixed(0) + ' us  (' + M.toLocaleString() + ' files in ' + w + 'ms)');
console.log('  => extrapolated 40,000-file install: ' + (w/M*40000/1000).toFixed(1) + 's of pure fs syscalls');
await k.terminate();
