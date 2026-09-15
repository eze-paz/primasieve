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
let libSources = null, libPromise = null;

class ProcExit { constructor(code) { this.code = code; } }

// Diagnostic that cannot fail: postMessage reaches the kernel, which prints it as
// "[host] <msg>". Independent of syscalls, the arena, and node's streams.
function trace(msg) { if (!self.WALIOS_NODE_DEBUG) return; try { self.postMessage({ t: 'warn', s: 'node-dbg: ' + msg }); } catch (_) {} }

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

// node's lib/ assumes a current V8. Chromium in CI can be a few versions behind, and
// lib/http.js calls methods.toSorted() at module scope -- so `require("http")` threw
// "methods.toSorted is not a function" and took the whole module with it. Polyfill the
// small, well-defined change-array-by-copy methods rather than pin a browser.
for (const [name, impl] of [
  ['toSorted', function (cmp) { return Array.prototype.slice.call(this).sort(cmp); }],
  ['toReversed', function () { return Array.prototype.slice.call(this).reverse(); }],
  ['toSpliced', function (...a) { const c = Array.prototype.slice.call(this); c.splice(...a); return c; }],
  ['with', function (i, v) { const c = Array.prototype.slice.call(this); c[i < 0 ? c.length + i : i] = v; return c; }],
]) {
  if (typeof Array.prototype[name] !== 'function') {
    Object.defineProperty(Array.prototype, name, { value: impl, writable: true, configurable: true });
  }
}

self.onmessage = async (ev) => {
  const m = ev.data;

  if (m.t === 'init') {
    trace('init received; names=' + (m.names ? m.names.length : 'none') + ' memory=' + (m.memory ? 'yes' : 'NO'));
    ctl = m.ctl; names = m.names; sigv = m.sigs;
    i32 = new Int32Array(ctl);
    i64 = new BigInt64Array(ctl);
    memory = m.memory;
    if (!memory || !(memory.buffer instanceof SharedArrayBuffer)) {
      self.postMessage({ t: 'ready', ok: false, error: 'node-proc-worker needs an imported shared memory (node-stub.wasm must import env.memory)' });
      return;
    }
    // Post ready IMMEDIATELY, then fetch node's lib/ in the background.
    //
    // Fetching before ready left a long async window in which this process was not
    // yet registered with the kernel. In a pipeline that is fatal: the reader (cat)
    // saw no writers, took EOF and exited, readers dropped to 0, and node's first
    // write to fd 1 came back EPIPE + SIGPIPE (exit 141). A wasm guest instantiates
    // synchronously and never opens that window.
    libPromise = (async () => {
      // The gzipped bundle is what ships (883KB vs 3967KB). DecompressionStream is
      // already a dependency, so inflating it costs nothing we were not paying.
      const gz = await fetch(new URL('./node-lib.json.gz', self.location.href));
      if (gz.ok) {
        const stream = gz.body.pipeThrough(new DecompressionStream('gzip'));
        return JSON.parse(await new Response(stream).text());
      }
      const r = await fetch(new URL('./node-lib.json', self.location.href));
      if (!r.ok) throw new Error('node-lib.json ' + r.status + ' (and .gz ' + gz.status + ')');
      return r.json();
    })();
    self.postMessage({ t: 'ready', ok: true, memory });
    return;
  }

  if (m.t === 'run') {
    trace('run received');
    let code = 0;
    if (!libSources) {
      try { libSources = await libPromise; }
      catch (e) {
        self.postMessage({ t: 'trap', error: 'lib fetch failed: ' + e.message });
        Atomics.store(i32, 3, 70); Atomics.store(i32, 0, ST_DONE); Atomics.notify(i32, 0);
        self.postMessage({ t: 'exit', code: 70 });
        return;
      }
    }
    try { code = await runNode(); }
    catch (e) {
      if (e instanceof ProcExit) code = e.code;
      else { trace('RUN THREW: ' + String((e && e.stack) || e).slice(0, 500)); code = 139; self.postMessage({ t: 'trap', error: String((e && e.stack) || e).slice(0, 800) }); }
    }
    // Drain the event loop before exiting, the way node does. Bounded so a runaway
    // interval cannot wedge the process forever.
    const pending = runNode.pending;
    if (pending) {
      // Exit when the loop has been QUIET for a while, not the instant the counter
      // touches zero. The count legitimately dips between async boundaries -- a pump
      // re-schedules itself, node emits 'close' on a later tick, a handler starts the
      // next child -- and sampling exactly in one of those gaps retired the process
      // with work still to come. That is what made async child_process and ESM output
      // appear in some runs and not others, and why adding a console.log "fixed" it.
      // Requiring sustained quiet turns a knife-edge race into a stable condition.
      const QUIET_MS = 120;
      const deadline = Date.now() + 10000;
      let quietSince = null;
      for (;;) {
        if (pending.n > 0) quietSince = null;
        else if (quietSince === null) quietSince = Date.now();
        else if (Date.now() - quietSince >= QUIET_MS) break;
        if (Date.now() >= deadline) break;
        await new Promise((r) => setTimeout(r, 1));
      }
      const rt = runNode.rt;
      if (rt && typeof rt.process.exitCode === 'number') code = rt.process.exitCode;
    }
    Atomics.store(i32, 3, code | 0);
    Atomics.store(i32, 0, ST_DONE);
    Atomics.notify(i32, 0);
    self.postMessage({ t: 'exit', code });
    return;
  }
};

async function runNode() {
  const { makeArena, makeSyscalls } = require('./syscall-bridge.js');
  const { KernelVfs } = require('./kernel-vfs.js');
  const { boot } = require('./boot.js');
  const { shimFactories } = require('./shims.js');
  const { main } = require('./node-main.js');

  const sys = makeSyscalls(names, hostCall);
  const arena = makeArena(memory, 1 << 16);

  // Unbuffered diagnostic straight to fd 2 -- no node streams, no buffering, no
  // event loop. If node's own stdout is broken this still gets through.
  const DEBUG = (typeof self !== 'undefined' && self.WALIOS_NODE_DEBUG) || false;
  const raw = (s2) => {
    if (!DEBUG) return;
    trace(s2);
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

    rt = boot(null, { sources: libSources, vfs, shimFactories, sys, mem: arena, trace });
    raw('boot ok; lib modules=' + rt.trace.loaded.length);
  } catch (e) {
    raw('BOOT FAILED: ' + ((e && e.stack) || e));
    return 70;
  }

  let code;
  try {
    code = await main(rt, sys, arena, trace);
    raw('main returned ' + code + '; syscalls=' + vfs.calls);
  } catch (e) {
    raw('MAIN THREW: ' + String((e && e.stack) || e).slice(0, 600));
    return 70;
  }
  // Node exits when the loop is empty, not when the main script ends. Hand the
  // pending count back so the caller can drain before retiring the process --
  // without this, a setTimeout or an unresolved promise is simply dropped.
  runNode.pending = rt.pending;
  runNode.rt = rt;

  self.postMessage({ t: 'result', code, calls: vfs.calls,
                     loaded: rt.trace.loaded.length, bindings: rt.trace.bindings.size });
  return code;
}
