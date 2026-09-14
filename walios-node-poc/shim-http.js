'use strict';
// `http` / `https` for walios-node, over the browser's own fetch().
//
// Node's https is tls -> _tls_wrap -> OpenSSL. walios has real TCP (wisp), but no
// TLS stack, and porting OpenSSL is not on the table. fetch() already does TLS
// natively, with the platform's trust store, so this replaces the module.
//
// Two real consequences, both worth knowing:
//   - requests are subject to CORS. registry.npmjs.org sends
//     `Access-Control-Allow-Origin: *` for metadata AND tarballs, which is why npm's
//     install path works; an arbitrary host may not.
//   - fetch cannot stream a request body or see response trailers, and it follows
//     redirects itself, so `res.statusCode` is the FINAL status.
//
// The surface is what an HTTP client library actually uses: request/get returning a
// ClientRequest, and an IncomingMessage that emits 'data'/'end'.

// EventEmitter is the guest's own, so it is a PARAMETER: declaring
// `class X extends EEs.EventEmitter` before injection made the superclass null.
function makeModule(defaultProtocol, EventEmitter, pending) {
  const EEs = { EventEmitter };

  class IncomingMessage extends EventEmitter {}

  function normalize(url, opts, cb) {
    if (typeof opts === 'function') { cb = opts; opts = {}; }
    if (typeof url === 'string' || url instanceof URL) {
      opts = Object.assign({}, opts);
      const u = new URL(String(url));
      opts.__url = u.href;
    } else {
      opts = Object.assign({}, url);
      const proto = opts.protocol || defaultProtocol;
      const host = opts.hostname || opts.host || 'localhost';
      const port = opts.port ? ':' + opts.port : '';
      opts.__url = proto + '//' + host + port + (opts.path || '/');
    }
    return { opts, cb };
  }

  function request(url, o, c) {
    const { opts, cb } = normalize(url, o, c);
    const req = new EEs.EventEmitter();
    const chunks = [];
    let ended = false;

    req.setHeader = (k, v) => { (opts.headers || (opts.headers = {}))[k] = v; return req; };
    req.getHeader = (k) => (opts.headers || {})[k];
    req.setTimeout = () => req;
    req.abort = req.destroy = () => { req.__aborted = true; return req; };
    req.write = (chunk) => {
      chunks.push(typeof chunk === 'string' ? new TextEncoder().encode(chunk) : new Uint8Array(chunk));
      return true;
    };
    req.end = (chunk) => {
      if (chunk) req.write(chunk);
      if (ended) return req;
      ended = true;
      go();
      return req;
    };
    if (cb) req.on('response', cb);

    async function go() {
      // Keeps the process alive across the request.
      if (pending) pending.n++;
      try {
        const method = (opts.method || 'GET').toUpperCase();
        const init = { method, headers: opts.headers || {} };
        if (chunks.length && method !== 'GET' && method !== 'HEAD') {
          let n = 0; for (const c2 of chunks) n += c2.length;
          const body = new Uint8Array(n);
          let off = 0; for (const c2 of chunks) { body.set(c2, off); off += c2.length; }
          init.body = body;
        }
        const r = await fetch(opts.__url, init);
        if (req.__aborted) return;
        const buf = new Uint8Array(await r.arrayBuffer());

        const res = new IncomingMessage();
        res.statusCode = r.status;
        res.statusMessage = r.statusText;
        res.url = opts.__url;
        res.httpVersion = '1.1';
        res.headers = {};
        r.headers.forEach((v, k) => { res.headers[k.toLowerCase()] = v; });
        res.rawHeaders = Object.entries(res.headers).flat();
        res.setEncoding = (e) => { res.__enc = e; return res; };
        res.resume = () => res;
        res.destroy = () => res;
        // Emitted on a later turn so a listener attached in the response callback
        // still sees the data, exactly as node behaves.
        res.on = function (ev, fn) {
          EEs.EventEmitter.prototype.on.call(this, ev, fn);
          if (ev === 'data' && !this.__flushed) {
            this.__flushed = true;
            queueMicrotask(() => {
              fn(this.__enc ? new TextDecoder().decode(buf) : buf);
              this.emit('end');
            });
          }
          return this;
        };
        res.body = buf;                       // convenience for our own code
        req.emit('response', res);
      } catch (e) {
        const err = new Error(String((e && e.message) || e));
        err.code = 'ECONNREFUSED';
        if (req.listenerCount('error')) req.emit('error', err);
        else throw err;
      } finally {
        if (pending) pending.n--;
      }
    }
    return req;
  }

  function get(url, o, c) { const r = request(url, o, c); r.end(); return r; }

  return { request, get, IncomingMessage, Agent: class {}, globalAgent: {}, STATUS_CODES: {}, __EEs: EEs };
}

// node's EventEmitter comes from the guest's own lib/, so it is injected rather than
// imported -- this file has no access to the builtin loader.
function install(EventEmitter, pending) {
  return { http: makeModule('http:', EventEmitter, pending), https: makeModule('https:', EventEmitter, pending) };
}

module.exports = { install };
