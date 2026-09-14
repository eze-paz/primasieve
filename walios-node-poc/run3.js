'use strict';
// The end-to-end test: a multi-file user app, in the VFS, run by node's real CJS loader,
// requiring node builtins, doing real fs I/O. This is "node app/index.js".
const { boot } = require('./boot.js');
const rt = boot(require('path').resolve(__dirname, process.argv[2] || '../nodesrc/lib'));
const { require: R, vfs } = rt;
const fs = R('fs');

// --- lay down a little app in the guest filesystem --------------------------
fs.mkdirSync('/app');
fs.mkdirSync('/app/lib');

fs.writeFileSync('/app/lib/greet.js', `
'use strict';
const path = require('path');
module.exports = function greet(who, file) {
  return 'hello ' + who + ' from ' + path.basename(file);
};
`);

fs.writeFileSync('/app/lib/store.js', `
'use strict';
const fs = require('fs');
exports.save = (p, obj) => fs.writeFileSync(p, JSON.stringify(obj));
exports.load = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
`);

fs.writeFileSync('/app/index.js', `
'use strict';
const os = require('os');
const greet = require('./lib/greet.js');
const store = require('./lib/store.js');
const { EventEmitter } = require('events');

const bus = new EventEmitter();
const log = [];
bus.on('step', (s) => log.push(s));

bus.emit('step', greet('walios', __filename));
bus.emit('step', 'hostname=' + os.hostname());
bus.emit('step', 'platform=' + process.platform);

store.save('/app/state.json', { runs: 1, log });
const back = store.load('/app/state.json');

module.exports = { log: back.log, runs: back.runs, dirname: __dirname };
`);

// --- run it exactly as \`node /app/index.js\` would ---------------------------
const Module = R('module');
const M = Module.Module || Module;

console.log('=== running /app/index.js via node\'s real CJS loader ===\n');
let result;
try {
  result = M._load('/app/index.js', null, true);
} catch (e) {
  console.log('FAILED: ' + e.message);
  console.log(e.stack.split('\n').slice(0, 6).join('\n'));
  process.exitCode = 1;
}

if (result) {
  console.log('exports.runs     :', result.runs);
  console.log('exports.dirname  :', result.dirname);
  console.log('exports.log      :');
  for (const l of result.log) console.log('   - ' + l);
  console.log('\nstate.json on the vfs:', new TextDecoder().decode(vfs.files.get('/app/state.json').data));
  console.log('\nfiles in vfs:', [...vfs.files.keys()].sort().join('  '));
  console.log('\nlib modules loaded:', rt.trace.loaded.length, '| bindings:', rt.trace.bindings.size, '| binding fns used:', rt.trace.used.size);
}
