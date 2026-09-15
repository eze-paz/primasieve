'use strict';
// The `node` entry point: argv from the kernel, real stdio, real console, then
// -e / -p / script.js. Shared by the browser worker and the headless test so both
// exercise the same code.
//
// Rung one of "make `node` work at the walios shell". NOT the REPL.

const REPL = require('./repl.js');

const USAGE = [
  'Usage: node [options] [script.js] [arguments]',
  '',
  '  -e, --eval <code>     evaluate code',
  '  -p, --print <code>    evaluate and print the result',
  '  -c, --check           check the script for syntax errors, do not run it',
  '  -v, --version         print the version',
  '  -h, --help            print this',
  '',
  'walios-node: no interactive REPL yet (needs vm/contextify).',
].join('\n');

// ---- argv, straight out of the kernel ---------------------------------------
// WALI hands argv over three imports rather than a pointer array:
//   __cl_get_argc()            -> count
//   __cl_get_argv_len(i)       -> byte length of argv[i]
//   __cl_copy_argv(buf, i)     -> writes argv[i] into buf
function readArgv(sys, arena) {
  if (!sys.argc) return ['/bin/node'];
  const n = sys.argc();
  const out = [];
  for (let i = 0; i < n; i++) {
    const len = sys.argvLen(i);
    const p = arena.alloc(len + 1);
    sys.copyArgv(p, i);
    const u8 = arena.u8();
    let e = p; const end = p + len;
    while (e < end && u8[e]) e++;
    out.push(new TextDecoder().decode(u8.slice(p, e)));
    arena.reset();
  }
  return out.length ? out : ['/bin/node'];
}

// ---- stdio ------------------------------------------------------------------
// Node builds these itself (internal/bootstrap/switches/is_main_thread.js):
// guessHandleType(fd) === 'FILE' selects internal/fs/sync_write_stream, which
// writes through fs.writeSync -> our fs binding -> SYS_write. So this is node's
// own stream code on top of our syscalls, not a hand-rolled substitute.
function makeStdio(R, process) {
  const SyncWriteStream = R('internal/fs/sync_write_stream');
  const mk = (fd) => {
    const s = new SyncWriteStream(fd, { autoClose: false });
    s.fd = fd;
    s._type = 'fs';
    s.isTTY = false;
    s._destroy = (err, cb) => { if (cb) cb(err); };       // never close fd 1/2
    s.destroySoon = s.destroy;
    return s;
  };
  const stdout = mk(1), stderr = mk(2);
  Object.defineProperty(process, 'stdout', { get: () => stdout, configurable: true });
  Object.defineProperty(process, 'stderr', { get: () => stderr, configurable: true });
  return { stdout, stderr };
}

function makeConsole(R, stdout, stderr) {
  // node's real Console -- format(), inspect(), %s/%d, console.table, the lot.
  const mod = R('internal/console/constructor');
  const Console = mod.Console || mod;
  return new Console({ stdout, stderr, colorMode: false });
}

// ---- the entry point --------------------------------------------------------
// rt   : the object boot() returned
// sys  : syscall bag (needs argc/argvLen/copyArgv wired)
// arena: marshalling arena
// Built once per RUNTIME, and only if something actually imports: constructing it
// pulls in the resolver and touches package.json, which a plain CJS run need not pay.
//
// Cached on `rt`, NOT in a module-level variable. In the worker each process gets a
// fresh realm so either would do, but the headless harness runs many runtimes in ONE
// process: a module-level cache handed the second script run a host still bound to the
// FIRST run's rt, whose kernel worker had already been terminated -- so its next
// syscall parked in Atomics.wait and never came back. That deadlock reads as "the
// suite got slow", which is exactly how I first mis-diagnosed it.
function makeEsmHostOnce(rt, trace) {
  if (rt.__esmHost !== undefined) return rt.__esmHost;
  try {
    const { makeEsmHost } = require('./esm-host.js');
    rt.__esmHost = makeEsmHost(rt, { trace: (m) => trace && trace('[esm] ' + m) });
  } catch (e) {
    trace && trace('[esm] host unavailable: ' + ((e && e.message) || e));
    rt.__esmHost = false;
  }
  return rt.__esmHost;
}

function main(rt, sys, arena, trace) {
  trace = trace || (() => {});
  const vfs = rt.vfs;
  const R = rt.require;
  const process = rt.process;

  const argv = readArgv(sys, arena);
  process.argv = argv;
  process.argv0 = 'node';
  process.execPath = argv[0] || '/bin/node';

  trace('argv=' + JSON.stringify(argv));
  const { stdout, stderr } = makeStdio(R, process);
  // SyncWriteStream._write swallows a failing writeSync into cb(err) -> an 'error'
  // event. With no listener that goes through process.nextTick, which we never drain,
  // so a broken stdout is completely silent. Listen, and probe writeSync directly.
  // Is _write even reached?
  for (const [nm, st] of [['stdout', stdout], ['stderr', stderr]]) {
    const orig = st._write;
    st._write = function (chunk, enc, cb) {
      // Call writeSync ourselves so a throw is visible SYNCHRONOUSLY. SyncWriteStream
      // routes it to cb(err) -> 'error' -> process.nextTick, which never drains here.
      try {
        R('fs').writeSync(this.fd, chunk, 0, chunk.length);
        cb();
      } catch (e) {
        // A failing stdout must never be silent. SyncWriteStream routes this to
        // cb(err) -> 'error' -> process.nextTick, which never drains here, so the
        // failure would vanish entirely. Report it on fd 2 by the rawest means.
        trace(nm + '._write fd=' + this.fd + ' THREW ' + (e && e.code) + ' ' + (e && e.message));
        try {
          const msg = 'node: write to fd ' + this.fd + ' failed: ' + ((e && e.code) || '') + ' ' + ((e && e.message) || e) + String.fromCharCode(10);
          const bb = new TextEncoder().encode(msg);
          const pp = arena.bytes(bb);
          sys.write(2, pp, bb.length);
          arena.reset();
        } catch (_) { /* nothing left */ }
        cb(e);
      }
    };
  }
  stdout.on('error', (e) => trace('STDOUT STREAM ERROR: ' + (e && e.code) + ' ' + (e && e.message)));
  stderr.on('error', (e) => trace('STDERR STREAM ERROR: ' + (e && e.code) + ' ' + (e && e.message)));
  trace('stdio built; stdout.fd=' + stdout.fd + ' writable=' + stdout.writable + ' constructed=' + (stdout._writableState && stdout._writableState.constructed));
  const console = makeConsole(R, stdout, stderr);
  trace('console built');

  // The realm user code sees. In the worker this IS the global scope; here we
  // hand it to compileFunctionForCJSLoader as shadowed parameters.
  rt.realm.console = console;
  if (rt.realm.global) {
    rt.realm.global.console = console;
    rt.realm.global.process = process;
  }
  // An ESM module is handed to V8 as a blob and evaluates in the WORKER's global
  // scope, not in our realm -- so `console.log` inside it binds to the WORKER's
  // console and the output goes to devtools instead of fd 1. It looked like ESM
  // worked; the writes were just landing somewhere nobody was reading.
  //
  // Installing the realm's globals ON the worker global is what node itself does
  // (they ARE globals there), and it keeps legal shadowing working: a module with its
  // own `const process` shadows it at module scope rather than colliding.
  //
  // Worker-only: in the headless harness globalThis is the TEST RUNNER's global, and
  // overwriting its console would silence the suite reporting on us.
  if (typeof importScripts === 'function' && typeof self !== 'undefined') {
    self.console = console;
    self.process = process;
    if (rt.realm.Buffer) self.Buffer = rt.realm.Buffer;
  }

  // Do NOT swallow write failures. Swallowing them is why a broken stdout showed up
  // as a blank screen and exit 0 instead of an error: `node -v` "succeeded" silently.
  // If stdout is unusable, say so on fd 2 by the rawest means available.
  const rawFd = (fd, s) => {
    try {
      const b = new TextEncoder().encode(s);
      const p = arena.bytes(b);
      sys.write(fd, p, b.length);
      arena.reset();
    } catch (_) { /* truly nothing left */ }
  };
  const NL = String.fromCharCode(10);
  const out = (s) => {
    try {
      const r = stdout.write(s);
      if (r !== true) trace('stdout.write backpressured');
    } catch (e) { trace('stdout.write THREW ' + (e && e.message)); rawFd(2, 'node: stdout write failed: ' + (e && e.message) + NL); }
  };
  const errOut = (s) => { try { stderr.write(s); } catch (e) { rawFd(2, s); } };

  // ---- stdin ---------------------------------------------------------------
  // Reads park in Atomics.wait and the kernel serves them asynchronously, so
  // blocking here costs nothing and needs no event loop.
  let stdinBuf = '';
  let stdinEof = false;
  const readLine = () => {
    for (;;) {
      const nl = stdinBuf.indexOf(NL);
      if (nl >= 0) { const line = stdinBuf.slice(0, nl); stdinBuf = stdinBuf.slice(nl + 1); return line; }
      if (stdinEof) { if (!stdinBuf) return null; const rest = stdinBuf; stdinBuf = ''; return rest; }
      let chunk;
      try { chunk = vfs.readFd(0, 4096); } catch (_) { stdinEof = true; continue; }
      if (!chunk.length) { stdinEof = true; continue; }
      stdinBuf += new TextDecoder().decode(chunk);
    }
  };
  const readAllStdin = () => {
    let rest = '';
    try { rest = new TextDecoder().decode(vfs.readAll(0)); } catch (_) {}
    const all = stdinBuf + rest;
    stdinBuf = ''; stdinEof = true;
    return all;
  };
  const stdinIsTty = (() => { try { return vfs.isatty(0); } catch (_) { return false; } })();

  // Minimal process.stdin. Node's real one is a stream over libuv; this covers the
  // synchronous shapes scripts actually reach for here.
  Object.defineProperty(process, 'stdin', {
    configurable: true,
    get() {
      const EE = R('events');
      const s2 = new EE();
      s2.fd = 0;
      s2.isTTY = stdinIsTty;
      s2.setEncoding = () => s2;
      s2.read = () => { const l = readLine(); return l === null ? null : l + NL; };
      s2.resume = () => { const all = readAllStdin(); if (all) s2.emit('data', all); s2.emit('end'); return s2; };
      const on = s2.on.bind(s2);
      s2.on = function (ev, fn) {
        on(ev, fn);
        if (ev === 'data') { const all = readAllStdin(); if (all) fn(all); s2.emit('end'); }
        return s2;
      };
      return s2;
    },
  });

  // argv[0] is the interpreter; walios passes the program name there.
  const args = argv.slice(1);
  let evalCode = null, printResult = false, script = null, checkOnly = false;
  const scriptArgs = [];

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (script !== null) { scriptArgs.push(a); continue; }
    if (a === '-e' || a === '--eval') { evalCode = args[++i]; continue; }
    if (a === '-p' || a === '--print') { evalCode = args[++i]; printResult = true; continue; }
    if (a === '-c' || a === '--check') { checkOnly = true; continue; }
    if (a === '-v' || a === '--version') { out(process.version + '\n'); return 0; }
    if (a === '-h' || a === '--help') { out(USAGE + '\n'); return 0; }
    if (a === '--') { continue; }
    if (a.startsWith('-')) { errOut('node: bad option: ' + a + '\n'); return 9; }
    script = a;
  }

  // NB these two run BEFORE any branch. They used to sit after the -e/-p branch,
  // which returns -- so `FOO=bar node -e ...` never read its environment while
  // `node script.js` did. That asymmetry is exactly why fork() worked (its child runs
  // a SCRIPT and so got NODE_CHANNEL_FD) while plain env passthrough did not, which
  // looked like a contradiction until the ordering explained both.
  // ---- environment ----------------------------------------------------------
  // The kernel hands a process its env as a FILE whose path __get_init_envfile writes
  // into a buffer (newline-separated K=V). Reading it is what makes `FOO=1 node x.js`,
  // an env: option to spawn, and fork()'s own NODE_CHANNEL_FD actually reach the child.
  try {
    if (sys.envFile) {
      const p = arena.alloc(1024);
      if (sys.envFile(p, 1024) === 1) {
        const u8 = arena.u8();
        let end = p; while (u8[end] !== 0 && end < p + 1024) end++;
        const path = new TextDecoder().decode(u8.slice(p, end));
        arena.reset();
        const text = R('fs').readFileSync(path, 'utf8');
        for (const line of text.split(NL)) {
          if (!line) continue;
          const eq = line.indexOf('=');
          if (eq > 0) process.env[line.slice(0, eq)] = line.slice(eq + 1);
        }
        try { R('fs').unlinkSync(path); } catch (_) {}
        trace('env: ' + Object.keys(process.env).length + ' variables');
      } else { arena.reset(); }
    }
  } catch (e) { trace('env read failed: ' + ((e && e.message) || e)); }

  // ---- fork()'s child half --------------------------------------------------
  // node does this in internal/process/pre_execution.js, which we do not run: if the
  // parent set NODE_CHANNEL_FD, open that fd as the IPC channel so process.send() and
  // the 'message' event exist. Without it a forked child is just a spawned one and
  // process.send is undefined.
  if (process.env && process.env.NODE_CHANNEL_FD) {
    const fd = parseInt(process.env.NODE_CHANNEL_FD, 10);
    const mode = process.env.NODE_CHANNEL_SERIALIZATION_MODE || 'json';
    delete process.env.NODE_CHANNEL_FD;
    delete process.env.NODE_CHANNEL_SERIALIZATION_MODE;
    try {
      R('child_process')._forkChild(fd, mode);
      trace('ipc channel opened on fd ' + fd);
    } catch (e) { trace('ipc channel failed: ' + ((e && e.message) || e)); }
  }

  // ---- node -e / -p ---------------------------------------------------------
  if (evalCode !== null) { trace('branch: -e/-p code=' + JSON.stringify(String(evalCode).slice(0, 40)));
    if (evalCode === undefined) { errOut('node: -e requires an argument\n'); return 9; }
    try {
      const Module = R('module');
      const M = Module.Module || Module;
      const m = new M('[eval]', null);
      m.filename = '/[eval]';
      m.paths = [];
      const binding = rt.internalBinding('contextify');
      const compiled = binding.compileFunctionForCJSLoader(
        printResult ? 'module.exports = (' + evalCode + '\n);' : evalCode,
        '[eval]',
      );
      const result = compiled.function.call(m.exports, m.exports, m.require.bind(m), m, '/[eval]', '/');
      if (printResult) {
        const v = m.exports === undefined ? result : m.exports;
        out(typeof v === 'string' ? v + '\n' : R('util').inspect(v) + '\n');
      }
      // `node -e 'process.exitCode = 3'` must exit 3, like real node.
      return typeof process.exitCode === 'number' ? process.exitCode : 0;
    } catch (e) {
      errOut(formatErr(e) + '\n');
      return 1;
    }
  }

  // ---- node --check script.js ----------------------------------------------
  // Parse and do not run. Deliberately compiled WITHOUT the realm globals as
  // shadowed parameters: a module-level `const process` is legal source, and
  // reporting it as a redeclaration is exactly the bug that broke commander.
  if (checkOnly) {
    if (script === null) { errOut('node: --check requires a script' + NL); return 9; }
    const path = absolute(script, process);
    let src;
    try { src = R('fs').readFileSync(path, 'utf8'); }
    catch (e) { errOut('node: cannot open ' + path + ': ' + ((e && e.code) || (e && e.message)) + NL); return 1; }
    if (src.charCodeAt(0) === 35 && src.charCodeAt(1) === 33) {          // shebang
      const nl = src.indexOf(NL);
      src = nl < 0 ? '' : src.slice(nl);
    }
    try {
      // eslint-disable-next-line no-new-func
      new Function('exports', 'require', 'module', '__filename', '__dirname', src);
    } catch (e) {
      errOut(path + NL + ((e && e.message) ? 'SyntaxError: ' + e.message : String(e)) + NL);
      return 1;
    }
    return 0;                                     // node prints nothing on success
  }

  // ---- node script.js -------------------------------------------------------
  if (script !== null) {
    trace('branch: script ' + script);
    process.argv = [process.execPath, absolute(script, process), ...scriptArgs];
    try {
      const Module = R('module');
      const M = Module.Module || Module;
      const abs = absolute(script, process);
      // An ESM entry cannot go through M._load: it is handed to V8 as a module, not
      // wrapped as CJS. The import is async, so it is registered with `pending` --
      // without that the process exits before the graph has evaluated.
      const esmHost = makeEsmHostOnce(rt, trace);
      if (esmHost && esmHost.isEsmPath(abs)) {
        trace('branch: ESM entry ' + abs);
        // RETURN THE PROMISE. The first version started the import and returned the
        // exit code immediately, leaning on the `pending` counter to keep the process
        // alive -- and that raced: the module's output landed after the process had
        // been retired in roughly half of runs, so ESM looked intermittently broken
        // when it was only intermittently WAITED for. main() may now return a promise
        // of the exit code, and every caller awaits it (awaiting a plain number is
        // free, so the CJS paths are unchanged).
        return esmHost.importModule(abs).then(
          () => (typeof process.exitCode === 'number' ? process.exitCode : 0),
          (e) => { errOut(formatErr(e) + NL); return 1; });
      }
      M._load(abs, null, true);
      return typeof process.exitCode === 'number' ? process.exitCode : 0;
    } catch (e) {
      if (e && e.code === 'MODULE_NOT_FOUND') {
        // Report the error's OWN message. Blaming `script` hid the real cause: the
        // miss was usually an inner require (a dependency), not the entry file.
        errOut('node: ' + e.message.split(NL)[0] + NL);
        if (e.requireStack && e.requireStack.length) {
          errOut('  required from: ' + e.requireStack.join(' <- ') + NL);
        }
        return 1;
      }
      errOut(formatErr(e) + '\n');
      return 1;
    }
  }

  // ---- bare `node` ----------------------------------------------------------
  // A terminal gets the REPL; anything else (a pipe, a redirected file) is read to
  // EOF and run as a script -- what real node does.
  if (stdinIsTty) {
    trace('branch: REPL');
    return REPL.start(rt, vfs, { out, err: errOut, readLine });
  }

  trace('branch: script from stdin');
  const src = readAllStdin();
  if (!src.trim()) {
    errOut('walios-node ' + process.version + ': nothing on stdin and no script given.' + NL);
    errOut('Try:  node -e "..."   |   node script.js   |   echo "..." | node' + NL);
    return 1;
  }
  try {
    const Module = R('module');
    const M = Module.Module || Module;
    const m = new M('[stdin]', null);
    m.filename = '/[stdin]';
    m.paths = [];
    const compiled = rt.internalBinding('contextify').compileFunctionForCJSLoader(src, '[stdin]');
    compiled.function.call(m.exports, m.exports, m.require.bind(m), m, '/[stdin]', '/');
    return typeof process.exitCode === 'number' ? process.exitCode : 0;
  } catch (e) {
    errOut(formatErr(e) + NL);
    return 1;
  }
}

function absolute(p, process) {
  if (p.startsWith('/')) return p;
  const cwd = typeof process.cwd === 'function' ? process.cwd() : '/';
  return (cwd === '/' ? '' : cwd) + '/' + p.replace(/^\.\//, '');
}

function formatErr(e) {
  if (!e) return 'Unknown error';
  if (e.stack) return String(e.stack).split('\n').slice(0, 12).join('\n');
  return (e.name || 'Error') + ': ' + (e.message || String(e));
}

module.exports = { main, readArgv, makeStdio, makeConsole, makeEsmHostOnce, USAGE };
