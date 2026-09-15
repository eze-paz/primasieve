'use strict';
// internalBinding('contextify'): enough of it for lib/vm.js to work.
//
// Real node contextifies an object into a fresh v8::Context, which a page cannot do --
// there is no API to make a new global. What we CAN do honestly:
//
//   runInThisContext  -- exact. It is `new Function`, the same seam the CJS loader uses,
//                        so the code really does run in this realm with our globals.
//   runInContext      -- APPROXIMATE, via `with (sandbox)`. Property lookup goes to the
//                        sandbox first and assignments land on it, which covers what vm
//                        is normally reached for (templating, config evaluation, small
//                        sandboxed expressions). It is NOT isolation: code in the
//                        sandbox can still reach our globals for anything the sandbox
//                        does not define, and `this` is the sandbox rather than a fresh
//                        global. Anyone using vm as a SECURITY boundary must not use
//                        this -- and node's own docs say vm is not a security boundary
//                        either, so the gap is narrower than it sounds.
//
// Saying that plainly beats a stub that throws, and beats one that pretends to isolate.

// Our own marker, used to find the sandbox again in runInContext.
const kSandbox = Symbol.for('walios.vm.sandbox');

function makeContextify(realm, privateSymbols) {
  // The realm globals a script should see, shadowed by name the way the CJS wrapper
  // does it -- otherwise `console` inside vm code binds to the HOST's console and the
  // output leaves the guest entirely.
  const GLOBALS = ['process', 'Buffer', 'console', 'setTimeout', 'setInterval', 'setImmediate',
                   'clearTimeout', 'clearInterval', 'globalThis', 'global'];
  const valueOf = (n) => (n === 'globalThis' || n === 'global' ? realm.global : realm[n]);

  // Compile with the realm globals shadowed, dropping any name the code declares itself
  // (a top-level `const process` is legal source, not a redeclaration).
  function compile(body, filename, extraNames, extraVals) {
    let names = GLOBALS.slice();
    const extras = extraNames || [];
    for (;;) {
      try {
        // eslint-disable-next-line no-new-func
        const fn = new Function(...names, ...extras,
          body + String.fromCharCode(10) + '//# sourceURL=' + (filename || 'evalmachine.<anonymous>'));
        return { fn, names };
      } catch (e) {
        const m = (e instanceof SyntaxError)
          ? /Identifier '([^']+)' has already been declared/.exec(e.message || '') : null;
        const i = m ? names.indexOf(m[1]) : -1;
        if (i < 0) throw e;
        names.splice(i, 1);
      }
    }
  }

  class ContextifyScript {
    constructor(code, filename, lineOffset, columnOffset, cachedData, produceCachedData, parsingContext) {
      this.code = String(code);
      this.filename = filename || 'evalmachine.<anonymous>';
      this.cachedDataRejected = cachedData !== undefined;
      this.cachedData = undefined;
      // Validate NOW, so bad syntax throws from `new vm.Script(...)` as node does,
      // rather than from the first run.
      compile(this.code, this.filename);
      // Run through a DIRECT eval. A function body loses the completion value --
      // `new vm.Script('1+1').runInThisContext()` must be 2, and a wrapper returns
      // undefined -- while eval yields it, and a direct eval still sees the realm
      // globals we shadowed as parameters.
      const r = compile('return eval(__code__);', this.filename, ['__code__']);
      this._run = r.fn;
      this._names = r.names;
    }

    runInThisContext() {
      return this._run(...this._names.map(valueOf), this.code);
    }

    runInContext(sandbox) {
      const box = (sandbox && sandbox[kSandbox]) || sandbox || {};
      // `with` is the only construct that redirects free identifiers at runtime. It is
      // why this is an approximation and not a context: a lookup the sandbox cannot
      // answer falls through to the enclosing scope instead of being a ReferenceError.
      const { fn, names } = compile(
        'with (__sandbox__) { return eval(__code__); }',
        this.filename, ['__sandbox__', '__code__']);
      return fn(...names.map(valueOf), box, this.code);
    }
  }

  return {
    ContextifyScript,
    // makeContext marks an object as a context. We keep the object itself as the
    // sandbox -- there is nothing to contextify it INTO.
    makeContext: (contextObject) => {
      // isContext() is NOT this binding's -- it lives in lib/internal/vm.js and reads
      // object[contextify_context_private_symbol], one of internalBinding('util')'s
      // privateSymbols. Stamping our own marker alone left vm.createContext() returning
      // an object that vm.runInContext() then rejected as "not a vm.Context", with the
      // marker plainly visible on it. Stamp BOTH: theirs is what node checks, ours is
      // how runInContext finds the sandbox again.
      const priv = privateSymbols && privateSymbols.contextify_context_private_symbol;
      for (const sym of [kSandbox, priv]) {
        if (!sym) continue;
        try { Object.defineProperty(contextObject, sym, { value: contextObject, enumerable: false, configurable: true }); }
        catch (_) { /* frozen: runInContext still treats it as the sandbox */ }
      }
      return contextObject;
    },
    isContext: (o) => !!(o && (o[kSandbox] !== undefined
      || (privateSymbols && o[privateSymbols.contextify_context_private_symbol] !== undefined))),
    compileFunction: undefined,          // filled in by bindings.js, which owns the CJS seam
    constants: { measureMemory: { mode: {}, execution: {} } },
    measureMemory: () => Promise.resolve({ total: { jsMemoryEstimate: 0, jsMemoryRange: [0, 0] } }),
    startSigintWatchdog: () => {},
    stopSigintWatchdog: () => {},
    watchdogHasPendingSigint: () => false,
  };
}

module.exports = { makeContextify };
