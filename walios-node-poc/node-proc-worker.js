'use strict';
// ONE walios process whose userspace is JavaScript on the page's own V8.
//
// Same contract as wali-proc-worker.js: the kernel (wali-worker.js) sends {t:'init'}
// with the control-block SAB, the import `names` array and a shared memory; every
// syscall is store-args / flip-state / Atomics.wait. The ONLY difference is that this
// worker never instantiates a wasm module -- it boots node's lib/*.js instead and
// calls the same syscalls from JS.
//
// node-stub.wasm exists purely so the kernel's _workerPlan() can derive names, sigs
// and the shared memory the way it does for any guest. We ignore m.mod entirely.

importScripts('poc-bundle.js');          // vfs / bindings / boot / kernel-vfs
const require = self.__pocRequire;

// ---- control block, mirrored from wali-proc-worker.js -----------------------
const ARGS = 64, RET = 192, MAXARGS = 16;
const ST_IDLE = 0, ST_REQ = 1, ST_REPLY = 2, ST_DONE = 3, ST_DIE = 4;

let ctl = null, i32 = null, i64 = null, names = null, sigv = null, memory = null;
let libSources = null;

class ProcExit { constructor(code) { this.code = code; } }

function hostCall(idx, args) {
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
}

// (makeArena / makeSyscalls now live in syscall-bridge.js, shared with the
// headless tests so both exercise the same code.)
function __unused_makeArena(mem, base) {
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

function __unused_makeSyscalls() {
  const idx = {};
  for (let i = 0; i < names.length; i++) idx[names[i]] = i;
  const call = (name) => {
    const i = idx['wali.SYS_' + name];
    if (i === undefined) return () => { throw new Error('syscall not in stub imports: ' + name); };
    return (...a) => hostCall(i, a);
  };
  return {
    open: call('open'), close: call('close'), read: call('read'), write: call('write'),
    lseek: call('lseek'), fstat: call('fstat'), stat: call('stat'), lstat: call('lstat'),
    mkdir: call('mkdir'), rmdir: call('rmdir'), unlink: call('unlink'),
    getdents64: call('getdents64'), access: call('access'), rename: call('rename'),
    ftruncate: call('ftruncate'), fsync: call('fsync'), chdir: call('chdir'),
    getcwd: call('getcwd'), exit_group: call('exit_group'),
    _argc: () => Number(hostCall(idx['wali.__cl_get_argc'], [])),
    _argvIdx: idx['wali.__cl_copy_argv'],
  };
}

function __unused_makeOut(sys, arena) {
  const enc = new TextEncoder();
  return (s, fd = 1) => {
    const b = enc.encode(s);
    const p = arena.bytes(b);
    sys.write(fd, p, b.length);
    arena.reset();
  };
}

self.onmessage = async (ev) => {
  const m = ev.data;

  if (m.t === 'init') {
    ctl = m.ctl; names = m.names; sigv = m.sigs;
    i32 = new Int32Array(ctl);
    i64 = new BigInt64Array(ctl);
    memory = m.memory;
    if (!memory || !(memory.buffer instanceof SharedArrayBuffer)) {
      self.postMessage({ t: 'ready', ok: false, error: 'node-proc-worker needs an imported shared memory (node-stub.wasm must import env.memory)' });
      return;
    }
    // node's lib/ -- fetched once, cached across processes by the HTTP cache.
    try {
      if (!libSources) {
        const r = await fetch(new URL('./node-lib.json', self.location.href));
        if (!r.ok) throw new Error('node-lib.json ' + r.status);
        libSources = await r.json();
      }
    } catch (e) {
      self.postMessage({ t: 'ready', ok: false, error: 'lib fetch failed: ' + e.message });
      return;
    }
    self.postMessage({ t: 'ready', ok: true, memory });
    return;
  }

  if (m.t === 'run') {
    let code = 0;
    try { code = runNode(); }
    catch (e) {
      if (e instanceof ProcExit) code = e.code;
      else { code = 139; self.postMessage({ t: 'trap', error: String((e && e.stack) || e).slice(0, 800) }); }
    }
    Atomics.store(i32, 3, code | 0);
    Atomics.store(i32, 0, ST_DONE);
    Atomics.notify(i32, 0);
    self.postMessage({ t: 'exit', code });
    return;
  }
};

function runNode() {
  const { makeArena, makeSyscalls } = require('./syscall-bridge.js');
  const { KernelVfs } = require('./kernel-vfs.js');
  const { boot } = require('./boot.js');
  const { main } = require('./node-main.js');

  const sys = makeSyscalls(names, hostCall);
  const arena = makeArena(memory, 1 << 16);

  // Unbuffered diagnostic straight to fd 2 -- no node streams, no buffering, no
  // event loop. If node's own stdout is broken this still gets through.
  const DEBUG = true;
  const raw = (s2) => {
    if (!DEBUG) return;
    try {
      const b = new TextEncoder().encode('[node-dbg] ' + s2 + String.fromCharCode(10));
      const p2 = arena.bytes(b);
      sys.write(2, p2, b.length);
      arena.reset();
    } catch (_) { /* nothing we can do */ }
  };

  raw('runNode entered; names=' + names.length + ' libSources=' + (libSources ? Object.keys(libSources).length : 'NULL'));

  let vfs, rt;
  try {
    vfs = new KernelVfs(sys, arena);
    raw('vfs built; probing SYS_write on fd 1');
    // Does a bare write to stdout work at all, before node is involved?
    const probe = new TextEncoder().encode('');
    const pp = arena.bytes(probe);
    const wrote = Number(sys.write(1, pp, 0));
    arena.reset();
    raw('bare SYS_write(1, "", 0) returned ' + wrote);

    rt = boot(null, { sources: libSources, vfs });
    raw('boot ok; lib modules=' + rt.trace.loaded.length);
  } catch (e) {
    raw('BOOT FAILED: ' + ((e && e.stack) || e));
    return 70;
  }

  let code;
  try {
    code = main(rt, sys, arena);
    raw('main returned ' + code + '; syscalls=' + vfs.calls);
  } catch (e) {
    raw('MAIN THREW: ' + String((e && e.stack) || e).slice(0, 600));
    return 70;
  }

  self.postMessage({ t: 'result', code, calls: vfs.calls,
                     loaded: rt.trace.loaded.length, bindings: rt.trace.bindings.size });
  return code;
}
