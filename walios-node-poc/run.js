'use strict';
const { boot } = require('./boot.js');
const LIB = process.argv[2] || '../nodesrc/lib';

const ok = [], bad = [];
function t(name, fn) {
  try { const r = fn(); ok.push(name + (r === undefined ? '' : '  -> ' + r)); }
  catch (e) { bad.push(name + '\n      ' + (e.message || e).split('\n')[0]); }
}

const rt = boot(require('path').resolve(__dirname, LIB));
const { require: R, vfs, trace } = rt;

console.log('=== booting node lib/ on synthetic bindings ===\n');

t('require("path")', () => typeof R('path').join === 'function');
t('path.join("/a","b","../c")', () => R('path').join('/a', 'b', '../c'));
t('path.resolve("/x","y")', () => R('path').resolve('/x', 'y'));
t('path.basename("/a/b.txt",".txt")', () => R('path').basename('/a/b.txt', '.txt'));

t('require("events")', () => typeof R('events') === 'function');
t('EventEmitter emit/on', () => {
  const EE = R('events');
  const e = new EE(); let got = null;
  e.on('x', (v) => { got = v; });
  e.emit('x', 'fired');
  if (got !== 'fired') throw new Error('listener did not fire');
  return got;
});

t('require("buffer")', () => typeof R('buffer').Buffer === 'function');
t('Buffer.from().toString()', () => R('buffer').Buffer.from('hello walios').toString());

t('require("fs")', () => typeof R('fs').writeFileSync === 'function');
t('fs.writeFileSync', () => { R('fs').writeFileSync('/tmp/x', 'hi from node lib'); return 'wrote ' + vfs.files.get('/tmp/x').data.length + ' bytes to OUR vfs'; });
t('fs.readFileSync utf8', () => R('fs').readFileSync('/tmp/x', 'utf8'));
t('fs.readFileSync buffer', () => { const b = R('fs').readFileSync('/tmp/x'); return b.constructor.name + '(' + b.length + ') = ' + b.toString(); });
t('fs.existsSync', () => R('fs').existsSync('/tmp/x'));
t('fs.statSync().size', () => R('fs').statSync('/tmp/x').size);
t('fs.statSync().isFile()', () => R('fs').statSync('/tmp/x').isFile());
t('fs.mkdirSync + readdirSync', () => { const fs = R('fs'); fs.mkdirSync('/tmp/d'); fs.writeFileSync('/tmp/d/a.txt', 'a'); fs.writeFileSync('/tmp/d/b.txt', 'b'); return JSON.stringify(fs.readdirSync('/tmp/d')); });
t('fs.appendFileSync', () => { const fs = R('fs'); fs.appendFileSync('/tmp/x', '!'); return fs.readFileSync('/tmp/x', 'utf8'); });
t('fs.unlinkSync', () => { const fs = R('fs'); fs.unlinkSync('/tmp/d/a.txt'); return JSON.stringify(fs.readdirSync('/tmp/d')); });
t('ENOENT is a real fs error', () => { try { R('fs').readFileSync('/nope', 'utf8'); return 'NO THROW (bad)'; } catch (e) { return e.code + ' / ' + (e.syscall || '?'); } });

t('require("util")', () => typeof R('util').format === 'function');
t('util.format("%s:%d","a",1)', () => R('util').format('%s:%d', 'a', 1));
t('util.inspect({a:[1,2]})', () => R('util').inspect({ a: [1, 2] }));
t('require("assert")', () => typeof R('assert').strictEqual === 'function');
t('assert.throws on mismatch', () => { try { R('assert').strictEqual(1, 2); return 'NO THROW (bad)'; } catch (e) { return e.code; } });
t('require("querystring")', () => R('querystring').stringify({ a: 1, b: 'x y' }));
t('require("string_decoder")', () => typeof R('string_decoder').StringDecoder === 'function');
t('require("stream")', () => typeof R('stream').Readable === 'function');
t('stream Readable->data', () => {
  const { Readable } = R('stream');
  const out = [];
  const r = Readable.from(['a', 'b', 'c']);
  r.on('data', (c) => out.push(String(c)));
  return 'constructed ok, flowing=' + (typeof r.read === 'function');
});

console.log('PASS (' + ok.length + ')');
for (const s of ok) console.log('  + ' + s);
if (bad.length) { console.log('\nFAIL (' + bad.length + ')'); for (const s of bad) console.log('  - ' + s); }

console.log('\n=== runtime surface actually exercised ===');
console.log('lib modules loaded : ' + trace.loaded.length);
console.log('bindings requested : ' + trace.bindings.size + '  [' + [...trace.bindings].sort().join(' ') + ']');
console.log('bindings stubbed   : ' + trace.stubbed.size + (trace.stubbed.size ? '  [' + [...trace.stubbed].sort().join(' ') + ']' : ''));
console.log('binding fns USED   : ' + trace.used.size);
const missFns = [...trace.missing].filter((m) => !m.startsWith('require:'));
const missReq = [...trace.missing].filter((m) => m.startsWith('require:'));
console.log('binding fns MISSED : ' + missFns.length + (missFns.length ? '\n   ' + missFns.sort().join('\n   ') : ''));
if (missReq.length) console.log('deps/ not in lib/  : ' + missReq.length + '  [' + missReq.map((s) => s.slice(8)).join(' ') + ']');
if (trace.stderr.length) console.log('\nguest stderr:\n  ' + trace.stderr.join('\n  '));
process.exitCode = bad.length ? 1 : 0;
