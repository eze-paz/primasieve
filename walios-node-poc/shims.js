'use strict';
// The modules walios-node still REPLACES instead of running node's own source.
//
// `http` and `net` used to be here. They are not any more: tcp_wrap talks to walios's
// real socket syscalls, so node's own lib/net.js and lib/_http_*.js run unmodified --
// which is the point. What is left are the two things the platform does natively and
// a JS process cannot:
//
//   crypto : OpenSSL. Hashing is pure computation, so it is implemented directly and
//            checked against NIST vectors; randomBytes goes through getrandom(2).
//   https  : TLS. walios DOES have OpenSSL compiled to wasm (python's _ssl.so), but
//            dlopen links a side module against the MAIN module's memory, function
//            table and libc -- and a JS process has no main module. So https is
//            fetch()-backed, which brings TLS with the platform trust store and CORS
//            as the price.
//   zlib   : a native inflate. DecompressionStream is real and correct, but async.
const cryptoShim = require('./shim-crypto.js');
const zlibShim = require('./shim-zlib.js');
const httpsShim = require('./shim-http.js');

function shimFactories(deps) {
  const { EventEmitter, pending, sys, mem } = deps;

  // randomBytes via the getrandom(2) syscall -- the same entropy every other walios
  // guest gets, rather than the JS engine's own CSPRNG.
  if (sys && mem && sys.getrandom) {
    cryptoShim.useSyscalls((out) => {
      const p = mem.alloc(out.length);
      const n = Number(sys.getrandom(p, out.length, 0));
      if (n === out.length) out.set(mem.u8().subarray(p, p + n));
      else crypto.getRandomValues(out);           // short read: do not hand back zeros
      mem.reset();
    });
  }

  const { https } = httpsShim.install(EventEmitter, pending);
  return { crypto: cryptoShim, zlib: zlibShim.install(pending), https };
}

module.exports = { shimFactories };
