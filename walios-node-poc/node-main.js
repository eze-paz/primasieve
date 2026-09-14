'use strict';
// The `node` entry point: argv from the kernel, real stdio, real console, then
// -e / -p / script.js. Shared by the browser worker and the headless test so both
// exercise the same code.
//
// Rung one of "make `node` work at the walios shell". NOT the REPL.

const USAGE = [
  'Usage: node [options] [script.js] [arguments]',
  '',
  '  -e, --eval <code>     evaluate code',
  '  -p, --print <code>    evaluate and print the result',
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
function main(rt, sys, arena) {
  const R = rt.require;
  const process = rt.process;

  const argv = readArgv(sys, arena);
  process.argv = argv;
  process.argv0 = 'node';
  process.execPath = argv[0] || '/bin/node';

  const { stdout, stderr } = makeStdio(R, process);
  const console = makeConsole(R, stdout, stderr);

  // The realm user code sees. In the worker this IS the global scope; here we
  // hand it to compileFunctionForCJSLoader as shadowed parameters.
  rt.realm.console = console;
  if (rt.realm.global) {
    rt.realm.global.console = console;
    rt.realm.global.process = process;
  }

  const out = (s) => { try { stdout.write(s); } catch (_) { /* fd gone */ } };
  const errOut = (s) => { try { stderr.write(s); } catch (_) {} };

  // argv[0] is the interpreter; walios passes the program name there.
  const args = argv.slice(1);
  let evalCode = null, printResult = false, script = null;
  const scriptArgs = [];

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (script !== null) { scriptArgs.push(a); continue; }
    if (a === '-e' || a === '--eval') { evalCode = args[++i]; continue; }
    if (a === '-p' || a === '--print') { evalCode = args[++i]; printResult = true; continue; }
    if (a === '-v' || a === '--version') { out(process.version + '\n'); return 0; }
    if (a === '-h' || a === '--help') { out(USAGE + '\n'); return 0; }
    if (a === '--') { continue; }
    if (a.startsWith('-')) { errOut('node: bad option: ' + a + '\n'); return 9; }
    script = a;
  }

  // ---- node -e / -p ---------------------------------------------------------
  if (evalCode !== null) {
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

  // ---- node script.js -------------------------------------------------------
  if (script !== null) {
    process.argv = [process.execPath, absolute(script, process), ...scriptArgs];
    try {
      const Module = R('module');
      const M = Module.Module || Module;
      M._load(absolute(script, process), null, true);
      return typeof process.exitCode === 'number' ? process.exitCode : 0;
    } catch (e) {
      if (e && e.code === 'MODULE_NOT_FOUND') {
        errOut('node: cannot find module ' + JSON.stringify(script) + '\n');
        return 1;
      }
      errOut(formatErr(e) + '\n');
      return 1;
    }
  }

  // ---- bare `node` ----------------------------------------------------------
  errOut('walios-node ' + process.version + ': no interactive REPL yet.\n');
  errOut('Try:  node -e "console.log(2+2)"   or   node script.js\n');
  return 1;
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

module.exports = { main, readArgv, makeStdio, makeConsole, USAGE };
