'use strict';
// The guest half of the walios syscall protocol, factored out of node-proc-worker.js
// so the exact same code can be exercised headlessly against a mock kernel
// (test-kernel-vfs.mjs). Wire format mirrors wali-proc-worker.js.

const ARGS = 64, RET = 192, MAXARGS = 16;
const ST_IDLE = 0, ST_REQ = 1, ST_REPLY = 2, ST_DONE = 3, ST_DIE = 4;

class ProcExit { constructor(code) { this.code = code; } }

// store args -> flip state -> Atomics.wait for the kernel's reply.
function makeHostCall(ctl) {
  const i32 = new Int32Array(ctl);
  const i64 = new BigInt64Array(ctl);
  return function hostCall(idx, args) {
    const n = Math.min(args.length, MAXARGS);
    for (let k = 0; k < n; k++) {
      const a = args[k];
      i64[(ARGS >> 3) + k] = (typeof a === 'bigint') ? a : BigInt(Math.trunc(a));
    }
    Atomics.store(i32, 2, n);
    Atomics.store(i32, 1, idx);
    Atomics.store(i32, 0, ST_REQ);
    Atomics.notify(i32, 0);
    for (;;) {
      const st = Atomics.load(i32, 0);
      if (st === ST_REPLY) break;
      if (st === ST_DIE) throw new ProcExit(Atomics.load(i32, 3) & 0xff);
      Atomics.wait(i32, 0, st);
    }
    const ret = i64[RET >> 3];
    Atomics.store(i32, 0, ST_IDLE);
    return ret;
  };
}

// Bump allocator inside the shared memory. The kernel reads guest pointers straight
// out of memory.buffer, so anything passed by pointer must live there.
function makeArena(mem, base) {
  let top = base;
  const api = {
    u8: () => new Uint8Array(mem.buffer),
    dv: () => new DataView(mem.buffer),
    reset: () => { top = base; },
    alloc(n) { const p = top; top = (top + n + 7) & ~7; return p; },
    bytes(b) { const p = api.alloc(b.length); new Uint8Array(mem.buffer).set(b, p); return p; },
    cstr(s) {
      const b = new TextEncoder().encode(s);
      const p = api.alloc(b.length + 1);
      const u8 = new Uint8Array(mem.buffer);
      u8.set(b, p); u8[p + b.length] = 0;
      return p;
    },
  };
  return api;
}

const SYSCALL_NAMES = [
  'open', 'close', 'read', 'write', 'lseek', 'fstat', 'stat', 'lstat',
  'mkdir', 'rmdir', 'unlink', 'getdents64', 'access', 'rename',
  'ftruncate', 'fsync', 'chdir', 'getcwd', 'exit_group',
];

// names[] is the kernel-supplied import list; syscalls are addressed by index into it.
function makeSyscalls(names, hostCall) {
  const idx = {};
  for (let i = 0; i < names.length; i++) idx[names[i]] = i;
  const sys = {};
  for (const n of SYSCALL_NAMES) {
    const i = idx['wali.SYS_' + n];
    sys[n] = (i === undefined)
      ? () => { throw new Error('syscall not in stub imports: ' + n); }
      : (...a) => hostCall(i, a);
  }
  sys._idx = idx;
  return sys;
}

module.exports = { makeHostCall, makeArena, makeSyscalls, ProcExit, SYSCALL_NAMES, ARGS, RET, ST_IDLE, ST_REQ, ST_REPLY, ST_DONE, ST_DIE };
