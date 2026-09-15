'use strict';
// Wires esm.js to the guest: resolution, the CJS/ESM decision, and the two globals a
// generated module reaches back through.
//
// A blob module evaluates in the WORKER's global scope, not in node's realm -- so the
// bridges it calls (__waliosRequireBuiltin / __waliosRequireCjs) have to be installed on
// globalThis, not on the realm. Putting them on the realm is the version of this that
// looks right and silently resolves to nothing.

const { makeEsm } = require('./esm.js');

// Node decides ESM-vs-CJS by extension first, then by the nearest package.json "type".
function isEsmPath(path, readFileMaybe, nearestType) {
  if (path.endsWith('.mjs')) return true;
  if (path.endsWith('.cjs')) return false;
  if (!path.endsWith('.js')) return false;
  return nearestType(path) === 'module';
}

function makeEsmHost(rt, opts) {
  const R = rt.require;
  const fs = R('fs');
  const path = R('path');
  const Module = R('module');
  const M = Module.Module || Module;
  const trace = opts && opts.trace;

  const readFile = (p) => fs.readFileSync(p, 'utf8');

  // Walk up for the nearest package.json, as the resolver does, and read its "type".
  const typeCache = new Map();
  function nearestType(from) {
    let dir = path.dirname(from);
    for (;;) {
      if (typeCache.has(dir)) return typeCache.get(dir);
      const pj = path.join(dir, 'package.json');
      let type = null;
      try { type = JSON.parse(fs.readFileSync(pj, 'utf8')).type || 'commonjs'; } catch (_) { type = null; }
      if (type) { typeCache.set(dir, type); return type; }
      const up = path.dirname(dir);
      if (up === dir) { typeCache.set(dir, 'commonjs'); return 'commonjs'; }
      dir = up;
    }
  }

  const builtinIds = new Set(['fs', 'path', 'os', 'util', 'events', 'stream', 'buffer', 'url',
    'crypto', 'zlib', 'http', 'https', 'net', 'dns', 'assert', 'querystring', 'string_decoder',
    'timers', 'tty', 'child_process', 'module', 'process', 'punycode', 'readline', 'v8', 'vm',
    'worker_threads', 'perf_hooks', 'async_hooks', 'constants']);

  function resolve(spec, parent) {
    let id = spec;
    if (id.startsWith('node:')) id = id.slice(5);
    if (builtinIds.has(id)) return { builtin: true, id };

    // Reuse the CJS resolver: it already knows node_modules, "exports", "main" and
    // extension probing, and an ESM package is found the same way.
    let resolved;
    try {
      resolved = M._resolveFilename(spec, { id: parent, filename: parent, paths: M._nodeModulePaths(path.dirname(parent)) }, false);
    } catch (e) {
      const err = new Error("Cannot find module '" + spec + "' imported from " + parent);
      err.code = 'ERR_MODULE_NOT_FOUND';
      throw err;
    }
    if (builtinIds.has(resolved)) return { builtin: true, id: resolved };
    return isEsmPath(resolved, readFile, nearestType)
      ? { path: resolved }
      : { cjs: true, path: resolved };
  }

  const esm = makeEsm({
    readFile,
    resolve,
    requireBuiltin: (id) => R(id),
    requireCjs: (p) => M._load(p, null, false),
    trace,
  });

  // The bridges a generated module calls. globalThis here is the worker's.
  const g = (typeof globalThis !== 'undefined') ? globalThis : {};
  g.__waliosRequireBuiltin = (id) => R(id);
  g.__waliosRequireCjs = (p) => M._load(p, null, false);

  return {
    isEsmPath: (p) => isEsmPath(p, readFile, nearestType),
    importModule: (p) => esm.importModule(p),
    // `import()` written inside CJS source. The CJS wrapper is a `new Function`, whose
    // dynamic import would resolve against the WORKER's URL rather than the guest file,
    // so bindings.js rewrites those calls to this and we resolve them properly.
    dynamicImport: async (spec, parent) => {
      const r = resolve(spec, parent || '/');
      if (r.builtin) return esm.importModule.__builtin ? null : importBuiltinNamespace(r.id);
      if (r.cjs) {
        const m = M._load(r.path, null, false);
        return namespaceFromCjs(m);
      }
      return esm.importModule(r.path);
    },
  };

  function importBuiltinNamespace(id) {
    return namespaceFromCjs(R(id));
  }
  // `await import('fs')` yields a namespace: module.exports as default plus its keys.
  function namespaceFromCjs(m) {
    const ns = { __proto__: null, default: m };
    if (m && (typeof m === 'object' || typeof m === 'function')) {
      for (const k of Object.keys(m)) if (k !== 'default') ns[k] = m[k];
    }
    return ns;
  }
}

module.exports = { makeEsmHost, isEsmPath };
