'use strict';
// Real ESM, by handing modules to V8 rather than transforming them.
//
// Node's own ESM loader is built on internalBinding('module_wrap'), which wraps
// v8::Module -- an API a page has no access to. The usual fallback is to transform ESM
// source into CJS, which cannot give you live bindings and gets circular imports wrong.
//
// We do not need to: probe-esm.html measured that a CLASSIC worker (which is what node
// runs in here) can dynamic-import a blob URL, that a blob module can import another
// blob module, and that bindings across them stay LIVE. So each module is compiled to a
// blob URL with its specifiers rewritten to the blob URLs of its resolved dependencies,
// and V8 links and evaluates the graph itself. Live bindings, hoisting, TDZ and
// evaluation order are then V8's, not ours.
//
// The one thing this shape cannot do is a CYCLE: a blob URL's content is fixed when the
// URL is created, so compiling A needs B's URL and compiling B needs A's. That is
// detected and reported, not hung on.

// ---- specifier scanner -------------------------------------------------------
// Finds the string literals that are module specifiers. Written as a state walk rather
// than a regex because a regex over JS source hits every classic trap at once: a `from`
// inside a comment, an apostrophe in a line comment, a division sign that looks like the
// start of a regex literal.
function scanSpecifiers(src) {
  const out = [];                    // { start, end, value, dynamic }
  let i = 0;
  const n = src.length;
  // The last significant word we passed, to decide whether a string is a specifier.
  let lastWord = '';
  let prevSig = '';                  // last significant char, for regex detection

  const isIdChar = (c) => /[A-Za-z0-9_$]/.test(c);

  while (i < n) {
    const c = src[i];

    // comments
    if (c === '/' && src[i + 1] === '/') { while (i < n && src[i] !== '\n') i++; continue; }
    if (c === '/' && src[i + 1] === '*') { i += 2; while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i++; i += 2; continue; }

    // regex literal: only where a value cannot precede it
    if (c === '/' && !/[A-Za-z0-9_$)\]]/.test(prevSig)) {
      let j = i + 1, inClass = false;
      while (j < n) {
        const d = src[j];
        if (d === '\\') { j += 2; continue; }
        if (d === '[') inClass = true;
        else if (d === ']') inClass = false;
        else if (d === '/' && !inClass) break;
        else if (d === '\n') break;
        j++;
      }
      i = j + 1; prevSig = '/'; lastWord = '';
      continue;
    }

    // template literal: skip, honouring ${ } nesting
    if (c === '`') {
      let j = i + 1, depth = 0;
      while (j < n) {
        if (src[j] === '\\') { j += 2; continue; }
        if (src[j] === '$' && src[j + 1] === '{') { depth++; j += 2; continue; }
        if (src[j] === '}' && depth > 0) { depth--; j++; continue; }
        if (src[j] === '`' && depth === 0) break;
        j++;
      }
      i = j + 1; prevSig = '`'; lastWord = '';
      continue;
    }

    // string literal: the only thing that can BE a specifier
    if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < n) {
        if (src[j] === '\\') { j += 2; continue; }
        if (src[j] === c) break;
        j++;
      }
      const value = src.slice(i + 1, j);
      // A specifier is a string directly after `from`, after a bare `import`/`export`,
      // or inside import(...). Anything else is just data.
      let isSpec = false, dynamic = false;
      if (lastWord === 'from') isSpec = true;
      else if (lastWord === 'import' || lastWord === 'export') isSpec = true;
      else {
        // import( "x" ) -- walk back over whitespace and the paren
        let k = i - 1;
        while (k >= 0 && /\s/.test(src[k])) k--;
        if (src[k] === '(') {
          let m = k - 1;
          while (m >= 0 && /\s/.test(src[m])) m--;
          let w = '';
          while (m >= 0 && isIdChar(src[m])) { w = src[m] + w; m--; }
          if (w === 'import') { isSpec = true; dynamic = true; }
        }
      }
      if (isSpec) out.push({ start: i, end: j + 1, value, dynamic });
      i = j + 1; prevSig = '"'; lastWord = '';
      continue;
    }

    if (isIdChar(c)) {
      let j = i;
      let w = '';
      while (j < n && isIdChar(src[j])) { w += src[j]; j++; }
      lastWord = w;
      prevSig = src[j - 1];
      i = j;
      continue;
    }

    if (!/\s/.test(c)) { prevSig = c; if (c !== ')' && c !== ']') lastWord = ''; }
    i++;
  }
  return out;
}

// ---- loader ------------------------------------------------------------------
function makeEsm(deps) {
  const { readFile, resolve, requireBuiltin, isBuiltin, trace } = deps;
  const T = trace || (() => {});

  const byPath = new Map();          // resolved path -> blob URL
  const inFlight = new Set();        // cycle detection
  const urls = [];                   // kept alive; revoking early breaks later imports

  // A builtin reached by `import fs from "node:fs"` has to become a real module. Its
  // named exports are enumerated at generation time off the CJS object, which is what
  // node's own cjs-module-lexer does for the same purpose.
  function builtinModule(id) {
    const key = 'builtin:' + id;
    if (byPath.has(key)) return byPath.get(key);
    const m = requireBuiltin(id);
    const names = [];
    if (m && (typeof m === 'object' || typeof m === 'function')) {
      for (const k of Object.keys(m)) if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(k) && k !== 'default') names.push(k);
    }
    const src = 'const m = globalThis.__waliosRequireBuiltin(' + JSON.stringify(id) + ');\n'
      + 'export default m;\n'
      + names.map((k) => 'export const ' + k + ' = m[' + JSON.stringify(k) + '];').join('\n') + '\n';
    const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
    urls.push(url);
    byPath.set(key, url);
    return url;
  }

  // A CJS dependency imported from ESM: node gives you module.exports as `default`
  // plus its enumerable keys as named exports.
  function cjsModule(path) {
    const key = 'cjs:' + path;
    if (byPath.has(key)) return byPath.get(key);
    const m = deps.requireCjs(path);
    const names = [];
    if (m && (typeof m === 'object' || typeof m === 'function')) {
      for (const k of Object.keys(m)) if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(k) && k !== 'default') names.push(k);
    }
    const src = 'const m = globalThis.__waliosRequireCjs(' + JSON.stringify(path) + ');\n'
      + 'export default m;\n'
      + names.map((k) => 'export const ' + k + ' = m[' + JSON.stringify(k) + '];').join('\n') + '\n';
    const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
    urls.push(url);
    byPath.set(key, url);
    return url;
  }

  // Compile one module and everything it imports, depth first, and return its blob URL.
  async function compile(path) {
    if (byPath.has(path)) return byPath.get(path);
    if (inFlight.has(path)) {
      // See the header: a blob URL's content is fixed at creation, so a cycle cannot be
      // linked this way. Say so instead of hanging or half-loading.
      const e = new Error('Cannot load ' + path + ': circular ESM imports are not supported here '
        + '(a module URL is created with its content, so two modules cannot each name the other)');
      e.code = 'ERR_ESM_CIRCULAR';
      throw e;
    }
    inFlight.add(path);
    try {
      const src = readFile(path);
      const specs = scanSpecifiers(src);
      let out = '';
      let last = 0;
      for (const s of specs) {
        out += src.slice(last, s.start);
        let url;
        const r = resolve(s.value, path);
        if (r.builtin) url = builtinModule(r.id);
        else if (r.cjs) url = cjsModule(r.path);
        else url = await compile(r.path);
        out += JSON.stringify(url);
        last = s.end;
      }
      out += src.slice(last);
      // Keep the original path discoverable for stack traces.
      out += '\n//# sourceURL=' + path + '\n';
      const url = URL.createObjectURL(new Blob([out], { type: 'text/javascript' }));
      urls.push(url);
      byPath.set(path, url);
      T('compiled ' + path + ' (' + specs.length + ' imports)');
      return url;
    } finally {
      inFlight.delete(path);
    }
  }

  return {
    scanSpecifiers,
    // The whole public surface: give it a resolved path, get the namespace.
    async importModule(path) {
      const url = await compile(path);
      return import(url);
    },
  };
}

module.exports = { makeEsm, scanSpecifiers };
