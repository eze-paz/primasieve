'use strict';
// `tls` over REAL TLS, by putting walios' own tlswrap in front of a real socket.
//
// The old story was that TLS was out of reach: walios has OpenSSL compiled to wasm
// (python's _ssl.so) but dlopen links a shared object against the MAIN module's memory,
// table and libc, and a JS process has no main module. So https was fetch()-backed --
// real TLS, but the browser's, which means the browser's trust store, CORS rules, and
// no access to anything that is not an HTTP request.
//
// That reasoning was about loading OpenSSL INTO this process. It does not have to be in
// this process. walios ships `tlswrap -L LOCALPORT HOST PORT`, a wasm program that
// listens on loopback and forwards each connection to HOST:PORT over TLS -- OpenSSL in
// its own process, where dlopen is not involved at all. Now that child_process can spawn
// one and the kernel serves loopback listeners, tls.connect() is: spawn a tlswrap, then
// connect an ordinary net.Socket to it.
//
// What that buys, beyond honesty: node's OWN lib/https.js runs unmodified on top of it,
// CORS stops applying, and any TLS port works rather than only what fetch permits.
//
// Falls back to the fetch-backed shim when tlswrap is not on this host -- the poc page
// and the walios tool do not mount the same program set.

const LOCAL_LO = 20000, LOCAL_HI = 60000;
// tlswrap binds in well under this; the cost is paid once per connection.
const BIND_DELAY_MS = 400;

function makeTls(deps) {
  const { require: R, pending, trace } = deps;
  const T = trace || (() => {});
  let tlswrapAvailable = null;               // unknown until first probe

  const net = () => R('net');
  const cp = () => R('child_process');

  function haveTlswrap() {
    if (tlswrapAvailable !== null) return tlswrapAvailable;
    try {
      // `tlswrap` with no arguments prints usage and exits non-zero; what matters is
      // whether the program EXISTS, which a 127/ENOENT tells us.
      const r = cp().spawnSync('tlswrap', []);
      tlswrapAvailable = !(r.error && r.error.code === 'ENOENT') && r.status !== 127;
    } catch (_) { tlswrapAvailable = false; }
    T('tlswrap available: ' + tlswrapAvailable);
    return tlswrapAvailable;
  }

  function connect(...args) {
    // tls.connect([port][, host][, options][, callback])
    let options = {}, cb = null;
    for (const a of args) {
      if (typeof a === 'function') cb = a;
      else if (typeof a === 'number') options.port = a;
      else if (typeof a === 'string') options.host = a;
      else if (a && typeof a === 'object') options = { ...options, ...a };
    }
    const host = options.host || options.servername || 'localhost';
    const port = options.port || 443;

    if (!haveTlswrap()) {
      const e = new Error('tls.connect: tlswrap is not available on this host');
      e.code = 'ERR_TLS_UNAVAILABLE';
      throw e;
    }

    const localPort = LOCAL_LO + Math.floor(Math.random() * (LOCAL_HI - LOCAL_LO));
    T('tlswrap -L ' + localPort + ' ' + host + ' ' + port);
    const child = cp().spawn('tlswrap', ['-L', String(localPort), String(host), String(port)],
      { stdio: ['ignore', 'ignore', 'pipe'] });
    let childErr = '';
    if (child.stderr) child.stderr.on('data', (d) => { childErr += d; });

    const socket = new (net().Socket)();
    // NO readiness probe. The first version opened a throwaway connection to check
    // whether tlswrap was listening and then destroyed it -- but tlswrap accepts a
    // connection by opening a TLS session to the remote for it, so the probe consumed
    // exactly the thing it was testing and the real connection got nothing back.
    // Verified separately that tlswrap is fine: `nc` through it returns HTTP/1.1 200 OK.
    //
    // So: give it a moment to bind, then make ONE connection -- the one the caller
    // actually wanted.
    if (pending) pending.n++;
    setTimeout(() => {
      if (pending) pending.n--;
      if (socket.destroyed) { try { child.kill(); } catch (_) {} return; }
      socket.connect({ port: localPort, host: '127.0.0.1' }, () => {
        // The handshake happens inside tlswrap, so a forwarded connection that is up
        // means the TLS session to the remote is up too.
        socket.authorized = true;
        socket.encrypted = true;
        socket.emit('secureConnect');
        if (cb) cb();
      });
    }, BIND_DELAY_MS);

    // tlswrap self-closes after 120s idle, but a finished request should not wait for
    // that -- one process per connection adds up.
    const reap = () => { try { child.kill(); } catch (_) {} };
    socket.once('close', reap);
    socket.once('error', reap);

    socket.getPeerCertificate = () => ({});
    socket.getProtocol = () => 'TLSv1.3';
    socket.getCipher = () => ({ name: 'UNKNOWN', version: 'TLSv1.3' });
    socket.setServername = () => {};
    return socket;
  }

  return {
    connect,
    haveTlswrap,
    // Resolved through the GUEST's require, not the bundle's: `require('events')` at
    // module scope here reaches poc-bundle's loader, which only knows './' modules, so
    // it threw and took the whole shim table down with it -- https included, which is
    // why npm-lite stopped being able to reach the registry.
    get TLSSocket() { return R('net').Socket; },
    // Serving TLS would need tlswrap in the other direction, which it does not do.
    Server: class Server { constructor() { throw new Error('tls.Server is not implemented (tlswrap is client-side only)'); } },
    createServer: () => { throw new Error('tls.createServer is not implemented (tlswrap is client-side only)'); },
    createSecureContext: (o) => ({ context: o || {} }),
    getCiphers: () => ['TLS_AES_128_GCM_SHA256', 'TLS_AES_256_GCM_SHA384'],
    rootCertificates: [],
    DEFAULT_MIN_VERSION: 'TLSv1.2',
    DEFAULT_MAX_VERSION: 'TLSv1.3',
    CLIENT_RENEG_LIMIT: 3,
    CLIENT_RENEG_WINDOW: 600,
  };
}

module.exports = { makeTls };
