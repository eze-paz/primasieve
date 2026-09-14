'use strict';
// internalBinding('cares_wrap') -- name resolution over REAL walios UDP sockets.
//
// The kernel's sockaddr carries only an address, and connect() hands "<ip>|<port>" to
// wisp, so a guest must resolve names itself. walios serves UDP (wisp OP.UDP/SENDTO/
// RECVFROM), so this speaks actual DNS over the wire rather than reaching for fetch --
// same path python and git take, and it keeps resolution a syscall concern.
//
// A records only, plus /etc/hosts first. CNAMEs are followed within the same answer
// section. No AAAA: the kernel's connect writes an IPv4 sockaddr.

const AF_INET = 2, SOCK_DGRAM = 2;
const EAGAIN = 11;

function encodeQuery(id, name) {
  const labels = name.split('.').filter(Boolean);
  let len = 12 + 1 + 4;
  for (const l of labels) len += 1 + l.length;
  const b = new Uint8Array(len);
  const dv = new DataView(b.buffer);
  dv.setUint16(0, id);
  dv.setUint16(2, 0x0100);          // standard query, recursion desired
  dv.setUint16(4, 1);               // one question
  let p = 12;
  for (const l of labels) {
    b[p++] = l.length;
    for (let i = 0; i < l.length; i++) b[p++] = l.charCodeAt(i) & 0x7f;
  }
  b[p++] = 0;
  dv.setUint16(p, 1); p += 2;       // QTYPE A
  dv.setUint16(p, 1);               // QCLASS IN
  return b;
}

// Names are compressed with 0xC0 pointers, so skipping a name means following them.
function skipName(b, p) {
  for (;;) {
    const len = b[p];
    if (len === 0) return p + 1;
    if ((len & 0xc0) === 0xc0) return p + 2;      // pointer: always the last thing
    p += 1 + len;
  }
}

function parseAnswers(b) {
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const rcode = dv.getUint16(2) & 0x0f;
  if (rcode !== 0) return { rcode, addrs: [] };
  const qd = dv.getUint16(4), an = dv.getUint16(6);
  let p = 12;
  for (let i = 0; i < qd; i++) { p = skipName(b, p); p += 4; }
  const addrs = [];
  for (let i = 0; i < an && p < b.length; i++) {
    p = skipName(b, p);
    const type = dv.getUint16(p); p += 2;
    p += 2;                                        // class
    p += 4;                                        // ttl
    const rdlen = dv.getUint16(p); p += 2;
    if (type === 1 && rdlen === 4) addrs.push(b[p] + '.' + b[p + 1] + '.' + b[p + 2] + '.' + b[p + 3]);
    p += rdlen;
  }
  return { rcode, addrs };
}

function makeDnsWrap(sys, mem, deps) {
  const { readFileSync, pending, servers } = deps;
  const cache = new Map();

  const call = (n, ...a) => { try { return Number(sys[n](...a)); } catch (_) { return -EAGAIN; } };

  // /etc/hosts wins, like every resolver. walios seeds it at boot.
  function fromHosts(name) {
    let txt = '';
    try { txt = readFileSync('/etc/hosts', 'utf8'); } catch (_) { return null; }
    for (const line of txt.split('\n')) {
      const s = line.replace(/#.*$/, '').trim();
      if (!s) continue;
      const parts = s.split(/\s+/);
      if (parts.length >= 2 && parts.slice(1).includes(name)) return parts[0];
    }
    return null;
  }

  function queryOnce(name, server) {
    const fd = call('socket', AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return null;
    try {
      const id = (Math.random() * 65535) | 0;
      const q = encodeQuery(id, name);
      // sockaddr_in for the resolver
      const sa = mem.alloc(16);
      const u8 = mem.u8(), dv = mem.dv();
      u8.fill(0, sa, sa + 16);
      dv.setUint16(sa, AF_INET, true);
      dv.setUint16(sa + 2, 53, false);
      u8.set(server.split('.').map(Number), sa + 4);
      const qp = mem.bytes(q);
      const sent = call('sendto', fd, qp, q.length, 0, sa, 16);
      mem.reset();
      if (sent < 0) return null;

      // wisp answers asynchronously; poll briefly rather than block forever.
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
        const bp = mem.alloc(1500);
        const n = call('recvfrom', fd, bp, 1500, 0, 0, 0);
        if (n > 0) {
          const resp = mem.u8().slice(bp, bp + n);
          mem.reset();
          const { addrs } = parseAnswers(resp);
          return addrs.length ? addrs : null;
        }
        mem.reset();
        if (n !== -EAGAIN && n < 0) return null;
        // Spin: there is no poll phase to park in, and a DNS reply is milliseconds away.
      }
      return null;
    } finally { call('close', fd); }
  }

  function resolve(name) {
    if (/^\d+\.\d+\.\d+\.\d+$/.test(name)) return name;
    if (cache.has(name)) return cache.get(name);
    const h = fromHosts(name);
    if (h) { cache.set(name, h); return h; }
    for (const s of servers) {
      const addrs = queryOnce(name, s);
      if (addrs && addrs.length) { cache.set(name, addrs[0]); return addrs[0]; }
    }
    return null;
  }

  // node calls getaddrinfo(req, hostname, family, hints, verbatim) and expects the
  // result on req.oncomplete(err, addresses).
  function getaddrinfo(req, hostname, family) {
    if (pending) pending.n++;
    queueMicrotask(() => {
      if (pending) pending.n--;
      let ip = null;
      try { ip = resolve(hostname); } catch (_) { ip = null; }
      if (req && req.oncomplete) {
        if (ip) req.oncomplete(0, [ip]);
        else req.oncomplete(-3008, undefined);          // UV_EAI_NONAME
      }
    });
    return 0;
  }

  class ChannelWrap {
    constructor() {}
    setServers() { return 0; }
    getServers() { return servers.map((s) => [s, 53]); }
    setLocalAddress() { return 0; }
    cancel() {}
    strerror(code) { return 'dns error ' + code; }
    queryA(req, name) { return getaddrinfo(req, name, 4); }
  }

  return {
    ChannelWrap,
    GetAddrInfoReqWrap: function GetAddrInfoReqWrap() {},
    GetNameInfoReqWrap: function GetNameInfoReqWrap() {},
    QueryReqWrap: function QueryReqWrap() {},
    getaddrinfo,
    getnameinfo: (req) => { queueMicrotask(() => req && req.oncomplete && req.oncomplete(0, '', '')); return 0; },
    isIP: (s) => (/^\d+\.\d+\.\d+\.\d+$/.test(s) ? 4 : (String(s).includes(':') ? 6 : 0)),
    isIPv4: (s) => /^\d+\.\d+\.\d+\.\d+$/.test(s),
    isIPv6: (s) => String(s).includes(':'),
    canonicalizeIP: (s) => s,
    strerror: (c) => 'dns error ' + c,
    AI_ADDRCONFIG: 1024, AI_ALL: 16, AI_V4MAPPED: 8,
    // resolve() is exported for tcp_wrap's own use and for tests.
    __resolve: resolve,
  };
}

module.exports = { makeDnsWrap, encodeQuery, parseAnswers, skipName };
