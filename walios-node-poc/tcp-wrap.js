'use strict';
// internalBinding('tcp_wrap') over REAL walios socket syscalls.
//
// This is the point of the whole exercise: node's own lib/net.js and lib/_http_*.js
// run unmodified on top of it, so `net` and `http` stop being modules we own and
// become modules walios serves -- the same socket/connect/send/recv the kernel
// already gives python, git and ssh.
//
// Reads are POLLED, not epolled: readStart() pumps a non-blocking recv on the event
// loop until EAGAIN, then reschedules. That costs a wakeup per tick and is the honest
// shortcut -- epoll integration would need the poll phase of a real libuv loop. It is
// correct, just not idle-efficient.
//
// TLS is NOT here. tls_wrap is OpenSSL, and while walios does have OpenSSL compiled to
// wasm (python's _ssl.so), dlopen links a side module against the MAIN module's memory,
// function table and libc -- and a JS process has no main module. So https stays on
// fetch(); see shim-https.js.

const AF_INET = 2, SOCK_STREAM = 1;
const FIONBIO = 0x5421;
const EAGAIN = 11, EINPROGRESS = 115, EINTR = 4;

// struct sockaddr_in { u16 family; u16 port_be; u32 addr_be; u8 zero[8] }
function writeSockaddrIn(mem, ptr, ip, port) {
  const u8 = mem.u8();
  const dv = mem.dv();
  u8.fill(0, ptr, ptr + 16);
  dv.setUint16(ptr, AF_INET, true);
  dv.setUint16(ptr + 2, port, false);            // network byte order
  const octets = ip.split('.').map((n) => parseInt(n, 10) & 0xff);
  u8.set(octets, ptr + 4);
  return 16;
}
function readSockaddrIn(mem, ptr) {
  const dv = mem.dv(), u8 = mem.u8();
  return {
    port: dv.getUint16(ptr + 2, false),
    address: [u8[ptr + 4], u8[ptr + 5], u8[ptr + 6], u8[ptr + 7]].join('.'),
    family: 'IPv4',
  };
}

function makeTcpWrap(sys, mem, deps) {
  const { streamBaseState, kReadBytesOrError, kArrayBufferOffset, kBytesWritten,
    kLastWriteWasAsync, pending, uvErrno } = deps;
  // Buffer comes from the guest's own lib/, which is not loaded yet when this is
  // constructed -- so it is resolved on first use, not captured.
  const Buffer = new Proxy({}, { get: (_t, k) => deps.getBuffer()[k] });

  const T = deps.trace || (() => {});
  const call = (n, ...a) => {
    try { const r = Number(sys[n](...a)); if (r < 0 && -r !== EAGAIN) T('sys.' + n + ' -> ' + r); return r; }
    catch (e) { T('sys.' + n + ' THREW ' + ((e && e.message) || e)); return -EAGAIN; }
  };

  // The read/accept pumps must keep the process ALIVE. The worker's raw setTimeout
  // does not register with `pending`, so the process exited the moment main() returned
  // and every response arrived after nobody was listening.
  // The decrement must happen AFTER fn(), not before. A pump re-schedules itself from
  // inside fn(), so dropping the count first leaves a window where pending.n is 0 while
  // work is still outstanding -- and the worker's drain loop, which exits the process
  // the moment the count reaches zero, could sample exactly there. That is why async
  // child_process output vanished in some runs and came back when two console.log calls
  // shifted the timing: the process was being retired mid-pump.
  const later = (fn, ms) => {
    if (pending) pending.n++;
    return setTimeout(() => {
      try { fn(); } finally { if (pending) pending.n--; }
    }, ms);
  };
  const cancel = (t) => { if (t) { clearTimeout(t); if (pending && pending.n > 0) pending.n--; } };

  class TCP {
    constructor() {
      this.fd = -1;
      this.reading = false;
      this._pumping = false;
      this.onread = null;
      this.onconnection = null;
      this._closed = false;
      this._pump = null;
    }

    _ensure() {
      if (this.fd < 0) {
        const fd = call('socket', AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return fd;
        this.fd = fd;
      }
      return 0;
    }

    _setNonBlock(on) {
      const p = mem.alloc(4);
      mem.dv().setInt32(p, on ? 1 : 0, true);
      call('ioctl', this.fd, FIONBIO, p);
      mem.reset();
    }

    // ---- connect ------------------------------------------------------------
    // Blocking on purpose: the guest parks in Atomics.wait and the kernel serves it
    // asynchronously, so nothing else is held up, and node's async contract is kept
    // by delivering oncomplete on a later turn.
    connect(req, ip, port) {
      const e = this._ensure();
      if (e < 0) return -e;
      const sa = mem.alloc(16);
      writeSockaddrIn(mem, sa, ip, port);
      const r = call('connect', this.fd, sa, 16);
      T('connect ' + ip + ':' + port + ' fd=' + this.fd + ' -> ' + r);
      mem.reset();
      if (r < 0 && -r !== EINPROGRESS) return r;
      this._setNonBlock(true);
      if (pending) pending.n++;
      queueMicrotask(() => {
        if (pending) pending.n--;
        if (req.oncomplete) req.oncomplete(0, this, req, true, true);
      });
      return 0;
    }

    // ---- write --------------------------------------------------------------
    _write(req, bytes) {
      let sent = 0;
      while (sent < bytes.length) {
        const chunk = bytes.subarray(sent);
        const p = mem.bytes(chunk);
        const n = call('sendto', this.fd, p, chunk.length, 0, 0, 0);
        T('send fd=' + this.fd + ' len=' + chunk.length + ' -> ' + n);
        mem.reset();
        if (n < 0) {
          if (-n === EAGAIN || -n === EINTR) continue;     // kernel serves blocking sends
          return n;
        }
        if (n === 0) break;
        sent += n;
      }
      streamBaseState[kBytesWritten] = sent;
      // 0 = the write finished synchronously. node then completes the request ITSELF,
      // inline, so calling req.oncomplete here as well is a second callback --
      // "ERR_MULTIPLE_CALLBACK: Callback called multiple times".
      streamBaseState[kLastWriteWasAsync] = 0;
      if (req) req.bytes = sent;
      return 0;
    }
    writeBuffer(req, buf) { return this._write(req, buf); }
    writeLatin1String(req, s) { return this._write(req, Buffer.from(String(s), 'latin1')); }
    writeUtf8String(req, s) { return this._write(req, Buffer.from(String(s), 'utf8')); }
    writeAsciiString(req, s) { return this._write(req, Buffer.from(String(s), 'ascii')); }
    writeUcs2String(req, s) { return this._write(req, Buffer.from(String(s), 'ucs2')); }
    writev(req, chunks) {
      // chunks is [data, encoding, data, encoding, ...]
      const parts = [];
      for (let i = 0; i < chunks.length; i += 2) {
        const d = chunks[i];
        parts.push(typeof d === 'string' ? Buffer.from(d, chunks[i + 1] || 'utf8') : d);
      }
      let total = 0; for (const p of parts) total += p.length;
      const all = Buffer.alloc(total);
      let off = 0; for (const p of parts) { all.set(p, off); off += p.length; }
      return this._write(req, all);
    }

    // ---- read ---------------------------------------------------------------
    readStart() {
      // `reading` is NODE's flag: internal/stream_base_commons sets handle.reading =
      // true BEFORE calling readStart, so guarding on it meant the pump never started.
      if (this._pumping || this._closed) return 0;
      this._pumping = true;
      this._setNonBlock(true);
      const BUF = 64 * 1024;
      let ticks = 0;
      const tick = () => {
        if (++ticks <= 3 || ticks % 50 === 0) T('tick ' + ticks + ' fd=' + this.fd);
        if (!this._pumping || this._closed) return;
        for (;;) {
          const p = mem.alloc(BUF);
          const n = call('recvfrom', this.fd, p, BUF, 0, 0, 0);
          if (n !== -EAGAIN) T('recv fd=' + this.fd + ' -> ' + n);
          if (n > 0) {
            const bytes = mem.u8().slice(p, p + n);
            mem.reset();
            const ab = Buffer.from(bytes);
            streamBaseState[kReadBytesOrError] = n;
            streamBaseState[kArrayBufferOffset] = 0;
            if (this.onread) this.onread(ab);
            continue;                                   // drain what is queued
          }
          mem.reset();
          if (n === 0) {                                // orderly EOF
            streamBaseState[kReadBytesOrError] = uvErrno.UV_EOF;
            this._pumping = false;
            if (this.onread) this.onread(Buffer.alloc(0));
            return;
          }
          if (-n === EAGAIN || -n === EINTR) break;      // nothing right now
          streamBaseState[kReadBytesOrError] = n;        // real error
          this._pumping = false;
          if (this.onread) this.onread(Buffer.alloc(0));
          return;
        }
        this._pump = later(tick, 1);                    // poll; see header
      };
      this._pump = later(tick, 0);
      return 0;
    }
    readStop() {
      this._pumping = false;
      if (this._pump) { cancel(this._pump); this._pump = null; }
      return 0;
    }

    // ---- server side --------------------------------------------------------
    bind(ip, port) {
      const e = this._ensure();
      if (e < 0) return e;
      const sa = mem.alloc(16);
      writeSockaddrIn(mem, sa, ip || '0.0.0.0', port);
      const r = call('bind', this.fd, sa, 16);
      mem.reset();
      return r < 0 ? r : 0;
    }
    bind6(ip, port) { return this.bind('0.0.0.0', port); }
    listen(backlog) {
      const r = call('listen', this.fd, backlog | 0 || 511);
      if (r < 0) return r;
      this._setNonBlock(true);
      const tick = () => {
        if (this._closed) return;
        const cfd = call('accept4', this.fd, 0, 0, 0);
        if (cfd >= 0) {
          const client = new TCP();
          client.fd = cfd;
          client._setNonBlock(true);
          if (this.onconnection) this.onconnection(0, client);
        }
        this._pump = later(tick, 5);
      };
      this._pump = later(tick, 0);
      return 0;
    }

    // ---- names --------------------------------------------------------------
    getsockname(out) { Object.assign(out, { address: '0.0.0.0', port: 0, family: 'IPv4' }); return 0; }
    getpeername(out) { Object.assign(out, this._peer || { address: '0.0.0.0', port: 0, family: 'IPv4' }); return 0; }

    // ---- lifecycle ----------------------------------------------------------
    shutdown(req) {
      call('shutdown', this.fd, 1);
      if (req) queueMicrotask(() => { if (req.oncomplete) req.oncomplete(0, this, req); });
      return 0;
    }
    close(cb) {
      if (!this._closed) {
        this._closed = true;
        this.readStop();
        if (this.fd >= 0) call('close', this.fd);
        this.fd = -1;
      }
      if (cb) queueMicrotask(cb);
      return 0;
    }
    setNoDelay() { return 0; }
    setKeepAlive() { return 0; }
    setBlocking() { return 0; }
    ref() {} unref() {}
    getAsyncId() { return 0; }
    hasRef() { return true; }
    open(fd) { this.fd = fd; return 0; }
    fchmod() { return 0; }
    reset(req) { return this.close(req && req.oncomplete); }
  }

  function TCPConnectWrap() {}
  function ShutdownWrap() {}
  function WriteWrap() {}

  return {
    TCP,
    TCPConnectWrap,
    ShutdownWrap,
    WriteWrap,
    constants: { SOCKET: 0, SERVER: 1, IPV6ONLY: 2, UV_TCP_IPV6ONLY: 2 },
  };
}

module.exports = { makeTcpWrap, writeSockaddrIn, readSockaddrIn };
