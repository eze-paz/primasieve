// The specifier scanner decides what gets rewritten, so a false positive corrupts a
// string literal in someone's source and a false negative leaves an unresolvable
// specifier. Both are silent, so it gets its own test.
//   node walios-node-poc/test-esm-scan.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { scanSpecifiers } = require('./esm.js');

let pass = 0, fail = 0;
const NL = String.fromCharCode(10);
function t(name, src, expected) {
  const got = scanSpecifiers(src).map((s) => s.value);
  const ok = JSON.stringify(got) === JSON.stringify(expected);
  if (ok) { pass++; console.log('  + ' + name); }
  else { fail++; console.log('  - ' + name + NL + '      got ' + JSON.stringify(got) + ' want ' + JSON.stringify(expected)); }
}

console.log(NL + '=== ESM specifier scanner ===' + NL);

t('default import', 'import a from "x";', ['x']);
t('named import', 'import { a, b } from "x";', ['x']);
t('namespace import', 'import * as ns from "x";', ['x']);
t('bare import', 'import "x";', ['x']);
t('export from', 'export { a } from "x";', ['x']);
t('export star', 'export * from "x";', ['x']);
t('export star as', 'export * as ns from "x";', ['x']);
t('dynamic import', 'const m = await import("x");', ['x']);
t('dynamic import with spaces', 'await import(  "x"  );', ['x']);
t('several', 'import a from "x";' + NL + 'import b from "y";', ['x', 'y']);
t('single quotes', "import a from 'x';", ['x']);

// The traps.
t('string containing the word from', 'const s = "copied from somewhere";', []);
t('line comment mentioning import', '// import x from "not-real"' + NL + 'const a = 1;', []);
t('block comment mentioning import', '/* import x from "not-real" */ const a = 1;', []);
t('apostrophe in a line comment', "// don't be fooled" + NL + 'import a from "x";', ['x']);
t('regex literal containing a quote', 'const r = /["]/g;' + NL + 'import a from "x";', ['x']);
t('regex that looks like division', 'const y = a / b; const z = c / d;', []);
t('template literal with a from', 'const s = `made from ${x}`;' + NL + 'import a from "x";', ['x']);
t('nested template', 'const s = `a${`b${c}d`}e`;' + NL + 'import a from "x";', ['x']);
t('escaped quote in string', 'const s = "she said \\"from\\" it";', []);
t('property named import', 'const o = { import: "nope" };', []);
t('importScripts is not import', 'importScripts("nope");', []);
t('a word ending in from', 'const cameFrom = "nope";', []);
t('import.meta.url', 'const u = import.meta.url;' + NL + 'import a from "x";', ['x']);

// Rewriting must land on the right bytes.
{
  const src = 'import a from "./dep.js";' + NL + 'const s = "./dep.js";';
  const specs = scanSpecifiers(src);
  const ok = specs.length === 1 && specs[0].value === './dep.js'
    && src.slice(specs[0].start, specs[0].end) === '"./dep.js"';
  if (ok) { pass++; console.log('  + offsets point at the specifier, not the lookalike string'); }
  else { fail++; console.log('  - offsets wrong: ' + JSON.stringify(specs)); }
}
{
  const src = 'const m = await import("x");';
  const s = scanSpecifiers(src)[0];
  if (s && s.dynamic) { pass++; console.log('  + dynamic import flagged as dynamic'); }
  else { fail++; console.log('  - dynamic flag missing'); }
}

console.log(NL + pass + ' passed, ' + fail + ' failed' + NL);
process.exit(fail ? 1 : 0);
