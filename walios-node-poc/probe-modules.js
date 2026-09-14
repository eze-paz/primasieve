// Which of node's public modules actually load in walios-node, and what breaks first.
// Run inside the guest:  node /probe-modules.js
'use strict';

const MODULES = ['assert', 'async_hooks', 'buffer', 'child_process', 'cluster', 'console',
  'constants', 'crypto', 'dgram', 'diagnostics_channel', 'dns', 'domain', 'events', 'fs',
  'http', 'http2', 'https', 'module', 'net', 'os', 'path', 'perf_hooks', 'process',
  'punycode', 'querystring', 'readline', 'repl', 'stream', 'string_decoder', 'timers',
  'tls', 'tty', 'url', 'util', 'v8', 'vm', 'worker_threads', 'zlib'];

const load = [];
for (const m of MODULES) {
  try { require(m); load.push('LOAD  OK   ' + m); }
  catch (e) { load.push('LOAD  FAIL ' + m + ' :: ' + String(e && e.message).slice(0, 62).replace(/\s+/g, ' ')); }
}

// Loading is cheap; USING is the real test. node lazy-requires, so a module can
// import fine and still explode on its first real call.
const uses = [
  ['fs.readFileSync', () => require('fs').readFileSync('/etc/hosts', 'utf8').length > 0],
  ['fs.promises', () => typeof require('fs').promises.readFile === 'function'],
  ['stream pipe', () => { const { PassThrough } = require('stream'); const p = new PassThrough(); p.end('x'); return true; }],
  ['crypto hash', () => require('crypto').createHash('sha256').update('a').digest('hex').length === 64],
  ['zlib gunzip (async)', () => typeof require('zlib').promises.gunzip === 'function'],
  ['https.get', () => typeof require('https').get === 'function'],
  ['url.URL', () => new (require('url').URL)('https://x/y').pathname === '/y'],
  ['querystring', () => require('querystring').stringify({ a: 1 }) === 'a=1'],
  ['os.cpus', () => Array.isArray(require('os').cpus())],
  ['util.promisify', () => typeof require('util').promisify(function (cb) { cb(null, 1); }) === 'function'],
  ['readline.createInterface', () => typeof require('readline').createInterface === 'function'],
  ['child_process.spawn', () => { require('child_process').spawn('echo', ['hi']); return true; }],
  ['net.connect', () => { require('net').connect(80, 'example.com'); return true; }],
  ['net.createServer', () => { require('net').createServer(); return true; }],
  ['http.createServer', () => { require('http').createServer(); return true; }],
  ['tls.connect', () => { require('tls').connect(443, 'example.com'); return true; }],
  ['dns.lookup', () => { require('dns').lookup('example.com', () => {}); return true; }],
  ['vm.runInNewContext', () => require('vm').runInNewContext('1+1') === 2],
  ['worker_threads.Worker', () => { new (require('worker_threads').Worker)('/x.js'); return true; }],
  ['crypto.createCipheriv', () => { require('crypto').createCipheriv('aes-256-cbc', Buffer.alloc(32), Buffer.alloc(16)); return true; }],
  ['crypto.randomUUID', () => typeof require('crypto').randomUUID() === 'string'],
  ['perf_hooks.performance', () => typeof require('perf_hooks').performance.now() === 'number'],
  ['process.hrtime.bigint', () => typeof process.hrtime.bigint() === 'bigint'],
  ['Buffer.alloc', () => Buffer.alloc(4).length === 4],
  ['dynamic import()', () => { import('/etc/hosts'); return true; }],
];

const use = [];
for (const [name, fn] of uses) {
  try { use.push((fn() ? 'USE   OK   ' : 'USE   BAD  ') + name); }
  catch (e) { use.push('USE   FAIL ' + name + ' :: ' + String(e && e.message).slice(0, 62).replace(/\s+/g, ' ')); }
}

console.log(load.join('\n'));
console.log(use.join('\n'));
