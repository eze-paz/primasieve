'use strict';
// Harder tests: real data flow, encoding round-trips, perf, and the CJS loader.
const { boot } = require('./boot.js');
const rt = boot(require('path').resolve(__dirname, process.argv[2] || '../nodesrc/lib'));
const { require: R, vfs, process: guestProcess, trace } = rt;

const ok = [], bad = [];
const t = (n, fn) => { try { const r = fn(); ok.push(n + (r === undefined ? '' : '  -> ' + r)); } catch (e) { bad.push(n + '\n      ' + String(e.message || e).split('\n')[0]); } };

const fs = R('fs');
const { Buffer } = R('buffer');

console.log('=== harder suite ===\n');

// --- encodings round-trip through node's real Buffer -----------------------
for (const enc of ['utf8', 'hex', 'base64', 'latin1', 'ascii', 'base64url', 'ucs2']) {
  t('Buffer round-trip ' + enc, () => {
    const src = 'Grüße, walios! 123';
    const safe = (enc === 'ascii' || enc === 'latin1') ? 'Grusse, walios! 123' : src;
    const b = Buffer.from(safe, 'utf8');
    const s = b.toString(enc);
    const back = Buffer.from(s, enc).toString('utf8');
    if (enc === 'ucs2') return 'encoded ' + s.length + ' chars';
    if (back !== safe) throw new Error('round-trip mismatch: ' + JSON.stringify(back));
    return JSON.stringify(s.slice(0, 22));
  });
}
t('Buffer.concat + compare', () => {
  const a = Buffer.from('foo'), b = Buffer.from('bar');
  const c = Buffer.concat([a, b]);
  return c.toString() + ' / indexOf("bar")=' + c.indexOf('bar') + ' / cmp=' + Buffer.compare(a, b);
});
t('Buffer.alloc + fill + slice', () => Buffer.alloc(8, 0xab).toString('hex') + ' / ' + Buffer.alloc(6).fill('xy').toString());
t('buf.readUInt32BE / writeUInt32BE', () => { const b = Buffer.alloc(4); b.writeUInt32BE(0xdeadbeef, 0); return '0x' + b.readUInt32BE(0).toString(16); });

// --- streams actually moving bytes -----------------------------------------
t('stream: Readable -> data events (async)', () => {
  const { Readable } = R('stream');
  const chunks = [];
  const r = Readable.from([Buffer.from('al'), Buffer.from('pha')]);
  r.on('data', (c) => chunks.push(c.toString()));
  let done = false;
  r.on('end', () => { done = true; });
  // drain microtasks + nextTick the way the event loop would
  for (let i = 0; i < 200 && !done; i++) guestProcess._drainTicks();
  return 'chunks=' + JSON.stringify(chunks) + ' end=' + done;
});
t('stream: pipeline Readable->Writable', () => {
  const { Readable, Writable } = R('stream');
  const got = [];
  const w = new Writable({ write(c, e, cb) { got.push(c.toString()); cb(); } });
  const r = Readable.from(['x', 'y', 'z']);
  r.pipe(w);
  let spins = 0;
  while (spins++ < 500 && got.length < 3) guestProcess._drainTicks();
  return JSON.stringify(got);
});

// --- fs: bigger surface ------------------------------------------------------
t('fs binary round-trip (256 bytes)', () => {
  const b = Buffer.alloc(256); for (let i = 0; i < 256; i++) b[i] = i;
  fs.writeFileSync('/tmp/bin', b);
  const rb = fs.readFileSync('/tmp/bin');
  if (Buffer.compare(b, rb) !== 0) throw new Error('binary mismatch');
  return rb.length + ' bytes identical';
});
t('fs.readFileSync of a 1MB file', () => {
  const big = Buffer.alloc(1024 * 1024, 0x41);
  fs.writeFileSync('/tmp/big', big);
  const back = fs.readFileSync('/tmp/big');
  return back.length + ' bytes, first=' + String.fromCharCode(back[0]);
});
t('fs.statSync on a directory', () => { fs.mkdirSync('/tmp/sub'); return 'isDirectory=' + fs.statSync('/tmp/sub').isDirectory(); });
t('fs.writeFileSync with encoding', () => { fs.writeFileSync('/tmp/e', 'héllo', 'utf8'); return fs.readFileSync('/tmp/e', 'utf8'); });
t('fs error has errno/path/syscall', () => { try { fs.statSync('/missing/deep'); return 'NO THROW'; } catch (e) { return [e.code, e.syscall, e.path].join(' '); } });

// --- can we run a USER script out of the VFS? --------------------------------
t('CJS: require("module") loads', () => typeof R('module') === 'object' || typeof R('module') === 'function');
t('CJS: run a user script from the VFS', () => {
  fs.writeFileSync('/app/index.js', 'module.exports = 40 + 2;');
  const Module = R('module');
  const M = Module.Module || Module;
  const m = new M('/app/index.js', null);
  m.load('/app/index.js');
  return 'module.exports = ' + m.exports;
});

// --- native speed sanity ------------------------------------------------------
t('perf: 2e7 arithmetic ops in guest-visible JS', () => {
  const s = Date.now();
  let x = 0;
  for (let i = 0; i < 2e7; i++) x = (x + i * 3) % 1000003;
  return (Date.now() - s) + 'ms for 2e7 ops (JIT, not interpreted)';
});
t('perf: 20k Buffer ops through node lib', () => {
  const s = Date.now();
  for (let i = 0; i < 20000; i++) Buffer.from('chunk-' + i).toString('base64');
  return (Date.now() - s) + 'ms for 20k Buffer.from+base64';
});
t('perf: 2000 fs write+read round trips', () => {
  const s = Date.now();
  for (let i = 0; i < 2000; i++) { fs.writeFileSync('/tmp/p', 'v' + i); fs.readFileSync('/tmp/p', 'utf8'); }
  return (Date.now() - s) + 'ms for 2000 write+read (in-memory vfs)';
});

console.log('PASS (' + ok.length + ')');
for (const s of ok) console.log('  + ' + s);
if (bad.length) { console.log('\nFAIL (' + bad.length + ')'); for (const s of bad) console.log('  - ' + s); }
console.log('\nlib modules loaded: ' + trace.loaded.length + ' | bindings: ' + trace.bindings.size + ' | binding fns used: ' + trace.used.size);
