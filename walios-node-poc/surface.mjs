import fs from 'node:fs'; import path from 'node:path';
const LIB = 'lib';
const read = (id) => {
  for (const p of [path.join(LIB, id + '.js'), path.join(LIB, id, 'index.js')])
    if (fs.existsSync(p) && fs.statSync(p).isFile()) return fs.readFileSync(p, 'utf8');
  return null;
};
const seen = new Set(), bindings = new Map(), missing = new Set();
function walk(id) {
  if (seen.has(id)) return; seen.add(id);
  const src = read(id);
  if (src === null) { missing.add(id); return; }
  for (const m of src.matchAll(/internalBinding\(\s*'([^']+)'\s*\)/g))
    (bindings.get(m[1]) ?? bindings.set(m[1], new Set()).get(m[1])).add(id);
  for (const m of src.matchAll(/require\(\s*'([^']+)'\s*\)/g)) {
    const r = m[1];
    if (r.startsWith('node:')) walk(r.slice(5)); else walk(r);
  }
}
const roots = process.argv.slice(2);
for (const r of roots) walk(r);
console.log('roots        :', roots.join(' '));
console.log('lib modules  :', seen.size - missing.size);
console.log('bindings     :', bindings.size);
console.log([...bindings.keys()].sort().join(' '));
if (missing.size) console.log('\nunresolved   :', [...missing].sort().join(' '));
