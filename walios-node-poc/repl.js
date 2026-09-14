'use strict';
// A REPL for walios-node.
//
// Deliberately NOT node's lib/repl.js: that drives vm.createScript/runInContext, and
// a worker has no way to make a real realm. This evaluates with `new Function`, which
// is the same V8 either way -- what it gives up is vm's isolation, not speed.
//
// Line editing is the PTY's job. walios runs the terminal in canonical mode, so the
// kernel already handles echo, backspace and line assembly; a read on fd 0 returns a
// finished line. That is why there is no readline and no raw mode here.

const NL = String.fromCharCode(10);

// `var x = 1` inside new Function would land in that call's scope and vanish on the
// next line. Rewriting a top-level declaration to a property of the persistent scope
// object is what makes `> const x = 1` then `> x` work. Only top-level, only simple
// names -- destructuring declarations still evaporate, which is the honest limit.
const DECL = /^\s*(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=/;
function hoist(src) {
  const m = DECL.exec(src);
  if (!m) return src;
  return src.replace(DECL, '__scope.' + m[1] + ' =');
}

function isRecoverable(err) {
  // A line that is merely incomplete ("function f() {") should continue, not error.
  const msg = String((err && err.message) || '');
  return /Unexpected end of input|Unterminated (string|template|comment)/.test(msg);
}

function start(rt, vfs, io) {
  const R = rt.require;
  const util = R('util');
  const { out, err, readLine } = io;

  const scope = Object.create(null);
  const params = {
    __scope: scope,
    require: R,
    console: rt.realm.console,
    process: rt.process,
    Buffer: R('buffer').Buffer,
    global: rt.realm.global,
    globalThis: rt.realm.global,
  };
  const names = Object.keys(params);
  const args = names.map((k) => params[k]);

  const evaluate = (src) => {
    // Try as an expression first so `2+2` prints 4 rather than undefined; fall back
    // to statement form for `if (...) {}`, `const x = 1`, etc.
    let fn;
    try {
      fn = new Function(...names, 'with (__scope) { return (' + src + NL + '); }');
    } catch (_) {
      fn = new Function(...names, 'with (__scope) {' + NL + hoist(src) + NL + '}');
    }
    return fn(...args);
  };

  out('Welcome to walios-node ' + rt.process.version + '.' + NL);
  out('Type .exit to leave, .help for commands.' + NL);

  let buffer = '';
  for (;;) {
    out(buffer ? '... ' : '> ');
    const line = readLine();
    if (line === null) { out(NL); return 0; }            // EOF (Ctrl-D)

    const src = buffer + line;
    const trimmed = src.trim();
    if (!trimmed) { buffer = ''; continue; }

    if (!buffer) {
      if (trimmed === '.exit') return 0;
      if (trimmed === '.help') {
        out('.exit    leave the REPL' + NL);
        out('.help    this message' + NL);
        out('.clear   forget everything defined so far' + NL);
        continue;
      }
      if (trimmed === '.clear') {
        for (const k of Object.keys(scope)) delete scope[k];
        out('(scope cleared)' + NL);
        continue;
      }
    }

    try {
      const value = evaluate(src);
      buffer = '';
      if (value !== undefined) out(util.inspect(value, { colors: false, depth: 2 }) + NL);
    } catch (e) {
      if (isRecoverable(e)) { buffer = src + NL; continue; }
      buffer = '';
      err((e && e.stack ? String(e.stack).split(NL).slice(0, 4).join(NL) : String(e)) + NL);
    }
  }
}

module.exports = { start, hoist, isRecoverable };
