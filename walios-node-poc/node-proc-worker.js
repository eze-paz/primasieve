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

// ---- marshalling arena inside the shared memory -----------------------------
// The kernel reads guest pointers straight out of memory.buffer, so anything we pass
// by pointer has to live there. A bump allocator over a fixed region is enough: every
// syscall wrapper resets it as soon as the call returns.
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

// ---- syscall bag ------------------------------------------------------------
function makeSyscalls() {
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

// ---- stdout straight to the kernel ------------------------------------------
function makeOut(sys, arena) {
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
  const sys = makeSyscalls();
  // Arena starts well above 0 so a stray null-pointer write is not silently legal.
  const arena = makeArena(memory, 1 << 16);
  const out = makeOut(sys, arena);

  const { KernelVfs } = require('./kernel-vfs.js');
  const { boot } = require('./boot.js');

  const vfs = new KernelVfs(sys, arena);
  const rt = boot(null, { sources: libSources, vfs });
  const R = rt.require;

  // ---- suite 1, verbatim in intent: node's real lib/ over real syscalls -----
  const ok = [], bad = [];
  const t = (name, fn) => {
    try { const r = fn(); ok.push(name + (r === undefined ? '' : '  -> ' + r)); }
    catch (e) { bad.push(name + '\n      ' + String((e && e.message) || e).split('\n')[0]); }
  };

  out('=== node lib/ on the REAL walios kernel (pid via syscalls) ===\n\n');

  t('require("path")', () => typeof R('path').join === 'function');
  t('path.join("/a","b","../c")', () => R('path').join('/a', 'b', '../c'));
  t('require("events") + emit', () => {
    const EE = R('events'); const e = new EE(); let got = null;
    e.on('x', (v) => { got = v; }); e.emit('x', 'fired');
    if (got !== 'fired') throw new Error('listener did not fire');
    return got;
  });
  t('require("buffer")', () => R('buffer').Buffer.from('hello walios').toString());
  t('require("fs")', () => typeof R('fs').writeFileSync === 'function');

  const fs = R('fs');
  const Buffer = R('buffer').Buffer;

  t('fs.mkdirSync /tmp/nodepoc  [SYS_mkdir]', () => { try { fs.mkdirSync('/tmp/nodepoc'); } catch (e) { if (e.code !== 'EEXIST') throw e; } return 'ok'; });
  t('fs.writeFileSync           [SYS_open+write]', () => { fs.writeFileSync('/tmp/nodepoc/x', 'hi from node lib'); return 'wrote via syscalls'; });
  t('fs.readFileSync utf8       [SYS_open+read]', () => fs.readFileSync('/tmp/nodepoc/x', 'utf8'));
  t('fs.readFileSync buffer', () => { const b = fs.readFileSync('/tmp/nodepoc/x'); return b.constructor.name + '(' + b.length + ') = ' + b.toString(); });
  t('fs.existsSync              [SYS_stat]', () => fs.existsSync('/tmp/nodepoc/x'));
  t('fs.statSync().size', () => fs.statSync('/tmp/nodepoc/x').size);
  t('fs.statSync().isFile()', () => fs.statSync('/tmp/nodepoc/x').isFile());
  t('fs.statSync("/").isDirectory()', () => fs.statSync('/').isDirectory());
  t('fs.readdirSync             [SYS_getdents64]', () => {
    fs.writeFileSync('/tmp/nodepoc/a.txt', 'a');
    fs.writeFileSync('/tmp/nodepoc/b.txt', 'b');
    return JSON.stringify(fs.readdirSync('/tmp/nodepoc').sort());
  });
  t('fs.appendFileSync', () => { fs.appendFileSync('/tmp/nodepoc/x', '!'); return fs.readFileSync('/tmp/nodepoc/x', 'utf8'); });
  t('fs.unlinkSync              [SYS_unlink]', () => { fs.unlinkSync('/tmp/nodepoc/a.txt'); return JSON.stringify(fs.readdirSync('/tmp/nodepoc').sort()); });
  t('binary round-trip 256B', () => {
    const b = Buffer.alloc(256); for (let i = 0; i < 256; i++) b[i] = i;
    fs.writeFileSync('/tmp/nodepoc/bin', b);
    const rb = fs.readFileSync('/tmp/nodepoc/bin');
    if (Buffer.compare(b, rb) !== 0) throw new Error('binary mismatch');
    return rb.length + ' bytes identical through the kernel';
  });
  t('ENOENT is a real fs error', () => { try { fs.readFileSync('/definitely/missing', 'utf8'); return 'NO THROW (bad)'; } catch (e) { return e.code + ' / ' + (e.syscall || '?'); } });
  t('reads a file the SHELL made', () => {
    // /etc/gitconfig is seeded by walios-backend runMessage() -- proof we are on the
    // same filesystem as busybox/python, not a private heap.
    const names2 = fs.readdirSync('/etc');
    return '/etc has ' + names2.length + ' entries incl. ' + names2.slice(0, 4).join(',');
  });
  t('require("util") + inspect', () => R('util').inspect({ a: [1, 2] }));
  t('require("assert")', () => { try { R('assert').strictEqual(1, 2); return 'NO THROW'; } catch (e) { return e.code; } });
  t('require("stream")', () => typeof R('stream').Readable === 'function');

  out('PASS (' + ok.length + ')\n');
  for (const s of ok) out('  + ' + s + '\n');
  if (bad.length) { out('\nFAIL (' + bad.length + ')\n'); for (const s of bad) out('  - ' + s + '\n'); }

  out('\n=== kernel interaction ===\n');
  out('syscalls issued    : ' + vfs.calls + '\n');
  out('lib modules loaded : ' + rt.trace.loaded.length + '\n');
  out('bindings requested : ' + rt.trace.bindings.size + '\n');
  out('binding fns used   : ' + rt.trace.used.size + '\n');

  self.postMessage({ t: 'result', pass: ok.length, fail: bad.length, calls: vfs.calls,
                     loaded: rt.trace.loaded.length, bindings: rt.trace.bindings.size });
  return bad.length ? 1 : 0;
}
