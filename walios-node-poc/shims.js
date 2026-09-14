'use strict';
// The three modules walios-node replaces instead of running node's own source.
// Wired in boot() via opts.shimFactories; see boot.js for why each one exists.
const cryptoShim = require('./shim-crypto.js');
const zlibShim = require('./shim-zlib.js');
const httpShim = require('./shim-http.js');

// `pending` is the runtime's outstanding-async-work counter. fetch and
// DecompressionStream must register there or the process exits mid-request: the
// counter only knew about timers and nextTick, so an install was killed in flight.
function shimFactories(EventEmitter, requireBuiltin, pending) {
  const { http, https } = httpShim.install(EventEmitter, pending);
  return { crypto: cryptoShim, zlib: zlibShim.install(pending), http, https };
}

module.exports = { shimFactories };
