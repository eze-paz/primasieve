'use strict';
// Boot Node's real lib/*.js against a synthetic internalBinding.
//
// This is the Phase-0 spike: NOTHING in lib/ is modified or reimplemented. We only
// supply the six wrapper parameters Node's own BuiltinLoader supplies
// (see lib/internal/bootstrap/realm.js:400):
//     fn(exports, require, module, process, internalBinding, primordials)
// If node's lib/ boots on top of that, the whole walios-node design is engineering.

// Host fs/path are used ONLY to read lib/*.js off disk when running under node.
// In a walios worker there is no host fs, so opts.sources (id -> source) is passed
// instead and these stay null. Guest code never sees either.
let hostFs = null, hostPath = null;
try { hostFs = require('fs'); hostPath = require('path'); } catch (_) { /* worker */ }
const { Vfs } = require('./vfs.js');
const { makeBindings } = require('./bindings.js');

function boot(libDir, opts = {}) {
  const trace = { bindings: new Set(), stubbed: new Set(), used: new Set(), missing: new Set(), loaded: [], stderr: [] };
  const vfs = opts.vfs || new Vfs();
  // Filled in below; the bindings close over it so user code sees OUR realm globals.
  const realm = {};
  const internalBinding = makeBindings(vfs, trace, realm);

  // ---- primordials: node's own file, run as node runs it --------------------
  const primSrc = opts.sources
    ? opts.sources['internal/per_context/primordials']
    : hostFs.readFileSync(hostPath.join(libDir, 'internal/per_context/primordials.js'), 'utf8');
  if (!primSrc) throw new Error('primordials source not available');
  const primordials = {};
  // eslint-disable-next-line no-new-func
  new Function('exports', 'primordials', primSrc)({}, primordials);

  // ---- a minimal process object (Phase 1 replaces this with the real bootstrap)
  const listeners = new Map();
  const tickQueue = [];
  const process = {
    platform: 'linux', arch: 'wasm32',
    version: 'v22.23.2',
    versions: { node: '22.23.2', v8: '12.4.0', walios: '0.0.1' },
    argv: ['/bin/node', '/eval'], argv0: 'node',
    execPath: '/bin/node',
    env: { NODE_ENV: '', PATH: '/bin:/usr/bin', HOME: '/root' },
    pid: 42, ppid: 1,
    cwd: () => '/',
    chdir: () => {},
    exitCode: undefined,
    exit(code) { this.exitCode = code; },
    nextTick(fn, ...a) { tickQueue.push([fn, a]); },
    emitWarning(w) { trace.stderr.push('Warning: ' + (w && w.message ? w.message : w)); },
    on(ev, fn) { (listeners.get(ev) || listeners.set(ev, []).get(ev)).push(fn); return this; },
    once(ev, fn) { return this.on(ev, fn); },
    off() { return this; }, removeListener() { return this; },
    emit(ev, ...a) { const l = listeners.get(ev); if (!l) return false; for (const f of l) f(...a); return true; },
    listenerCount(ev) { return (listeners.get(ev) || []).length; },
    hrtime: Object.assign(() => { const t = performance.now() * 1e6; return [Math.floor(t / 1e9), Math.trunc(t % 1e9)]; },
      { bigint: () => BigInt(Math.trunc(performance.now() * 1e6)) }),
    uptime: () => performance.now() / 1000,
    noDeprecation: false, throwDeprecation: false, traceDeprecation: false,
    features: { cached_builtins: false },
    release: { name: 'node' },
    _rawDebug: (s) => trace.stderr.push(String(s)),
    binding() { throw new Error('process.binding() is not available in walios-node'); },
    _drainTicks() { while (tickQueue.length) { const [fn, a] = tickQueue.shift(); fn(...a); } },
  };

  realm.process = process;
  realm.global = { process, console: { log: (...a) => trace.stderr.push(a.join(' ')) } };

  // ---- the builtin loader (mirrors BuiltinModule.compileForInternalLoader) ---
  const cache = new Map();
  const srcCache = new Map();

  // Either a preloaded {id: source} map (worker) or lib/ on disk (node).
  const sources = opts.sources || null;
  function readSource(id) {
    if (srcCache.has(id)) return srcCache.get(id);
    let out = null;
    if (sources) {
      out = sources[id] ?? sources[id + '/index'] ?? null;
    } else {
      for (const p of [hostPath.join(libDir, id + '.js'), hostPath.join(libDir, id, 'index.js')]) {
        try { if (hostFs.statSync(p).isFile()) { out = hostFs.readFileSync(p, 'utf8'); break; } } catch (_) { /* next */ }
      }
    }
    srcCache.set(id, out);
    return out;
  }

  // internal/bootstrap/realm IS this loader -- in real Node it is the bootstrap that
  // installs internalBinding, so it cannot be run through the wrapper that already
  // takes internalBinding as a parameter ("Identifier 'internalBinding' has already
  // been declared"). We serve its exports synthetically instead.
  // BuiltinModule.map.get(id).compileForPublicLoader() is how `require('fs')` from
  // USER code reaches a builtin (cjs/loader.js loadBuiltinModule). Entries are made
  // lazily -- there are 341 lib files and eager facades would defeat lazy loading.
  // A builtin id is a bare specifier that resolves inside lib/ and is not internal/.
  // Anything with a path separator or an extension is user code, never a builtin.
  const isBuiltinId = (raw) => {
    const id = String(raw).replace(/^node:/, '');
    if (id.startsWith('internal/') || id.startsWith('.') || id.startsWith('/') || id.includes('\\')) return false;
    if (/\.(js|cjs|mjs|json|node)$/.test(id)) return false;
    return readSource(id) !== null;
  };

  const facades = new Map();
  class BuiltinMap extends Map {
    get(id) {
      if (facades.has(id)) return facades.get(id);
      if (readSource(id) === null) return undefined;
      const facade = {
        id,
        canBeRequiredByUsers: !id.startsWith('internal/'),
        compileForPublicLoader: () => requireBuiltin(id),
        getESMFacade: () => undefined,
        syncExports: () => {},
        get exports() { return requireBuiltin(id); },
      };
      facades.set(id, facade);
      return facade;
    }
    has(id) { return readSource(id) !== null; }
  }

  const BuiltinModule = {
    map: new BuiltinMap(),
    exists: (id) => readSource(id) !== null,
    isBuiltin: (id) => readSource(String(id).replace(/^node:/, '')) !== null,
    // MUST be true only for real builtin ids. Returning true for any non-internal
    // string makes _load treat '/app/index.js' as a builtin and crash in
    // loadBuiltinModule (helpers.js:118) on an undefined map entry.
    canBeRequiredByUsers: (id) => isBuiltinId(id),
    canBeRequiredWithoutScheme: (id) => isBuiltinId(id),
    normalizeRequirableId: (id) => (isBuiltinId(id) ? String(id).replace(/^node:/, "") : undefined),
    getSchemeOnlyModuleNames: () => [],
    getCanBeRequiredByUsersWithoutSchemeList: () => [],
    allowRequireByUsers: () => {},
    setRealmAllowRequireByUsers: () => {},
    exposeInternals: () => {},
    prototype: {},
  };

  function requireBuiltin(id) {
    if (typeof id !== 'string') throw new TypeError('require() id must be a string, got ' + typeof id);
    if (id.startsWith('node:')) id = id.slice(5);
    if (id === 'internal/bootstrap/realm') return { BuiltinModule, require: requireBuiltin };
    if (cache.has(id)) return cache.get(id).exports;

    const src = readSource(id);
    if (src === null) {
      // deps/ bundles (acorn, undici, cjs-module-lexer...) live outside lib/ -- out of
      // scope for Phase 0; record and hand back an empty module rather than dying.
      trace.missing.add('require:' + id);
      const empty = { exports: {} };
      cache.set(id, empty);
      return empty.exports;
    }

    const mod = { exports: {}, id, loaded: false, loading: true };
    cache.set(id, mod);
    let fn;
    try {
      // eslint-disable-next-line no-new-func
      fn = new Function('exports', 'require', 'module', 'process', 'internalBinding', 'primordials', src);
    } catch (e) {
      throw new Error('compile failed for ' + id + ': ' + e.message);
    }
    try {
      fn(mod.exports, requireBuiltin, mod, process, internalBinding, primordials);
    } catch (e) {
      e.message = '[' + id + '] ' + e.message;
      throw e;
    }
    mod.loaded = true; mod.loading = false;
    trace.loaded.push(id);
    return mod.exports;
  }

  // ---- minimal bootstrap ----------------------------------------------------
  // Phase 1 replaces this with node's real internal/process/pre_execution.js. For now,
  // only the initialisers whose absence leaves a module half-built (debuglog leaves
  // testEnabled undefined, which crashes the first stream that logs).
  try {
    const dbg = requireBuiltin('internal/util/debuglog');
    if (typeof dbg.initializeDebugEnv === 'function') dbg.initializeDebugEnv(process.env.NODE_DEBUG || '');
  } catch (e) { trace.stderr.push('debuglog init: ' + e.message); }

  try { realm.Buffer = requireBuiltin('buffer').Buffer; realm.global.Buffer = realm.Buffer; } catch (_) {}

  return { require: requireBuiltin, process, primordials, internalBinding, vfs, trace, realm };
}

module.exports = { boot };
