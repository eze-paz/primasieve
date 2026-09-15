'use strict';
// internalBinding('pipe_wrap'): a stream handle over an ordinary fd.
//
// Same shape as tcp-wrap's TCP -- node's stream_base_commons drives both through
// readStart/readStop/writeBuffer and the shared STREAM_BASE_STATE -- but over read(2)
// and write(2) instead of the socket calls, because a pipe from posix_spawn is a plain
// fd. Reads are POLLED for the same reason they are there: the kernel serves blocking
// reads, and blocking here would stop the whole JS process, which IS the event loop.

const EAGAIN = 11, EINTR = 4;
const F_GETFL = 3, F_SETFL = 4, O_NONBLOCK = 0o4000;
const BUF = 64 * 1024;

function makePipeWrap(sys, mem, deps) {
  const { streamBaseState, kReadBytesOrError, kArrayBufferOffset, kBytesWritten,
    kLastWriteWasAsync, pending, uvErrno } = deps;
  // Buffer comes from the guest's own lib/, which is not loaded when this is built.
  const Buffer = new Proxy({}, { get: (_t, k) => deps.getBuffer()[k] });
  const T = deps.trace || (() => {});

  const call = (n, ...a) => {
    try { return Number(sys[n](...a)); }
    catch (e) { T('sys.' + n + ' THREW ' + ((e && e.message) || e)); return -EAGAIN; }
  };
  // A pump must keep the process ALIVE: the worker's raw setTimeout does not register
  // with `pending`, so the process would exit the moment main() returned.
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

  class Pipe {
    constructor(type) {
      this.type = type;
      this.fd = -1;
      this.reading = false;
      this._pumping = false;
      this._closed = false;
      this._pump = null;
      this.onread = null;
    }

    open(fd) {
      this.fd = fd;
      this._setNonBlock(true);
      return 0;
    }

    _setNonBlock(on) {
      const fl = call('fcntl', this.fd, F_GETFL, 0);
      if (fl < 0) return;
      call('fcntl', this.fd, F_SETFL, on ? (fl | O_NONBLOCK) : (fl & ~O_NONBLOCK));
    }

    // ---- write ---------------------------------------------------------------
    _write(req, bytes) {
      let sent = 0;
      while (sent < bytes.length) {
        const chunk = bytes.subarray(sent);
        const p = mem.bytes(chunk);
        const n = call('write', this.fd, p, chunk.length);
        mem.reset();
        if (n < 0) {
          if (-n === EAGAIN || -n === EINTR) continue;   // the kernel serves the block
          return n;
        }
        if (n === 0) break;
        sent += n;
      }
      streamBaseState[kBytesWritten] = sent;
      // 0 means the write finished synchronously and node completes the request itself.
      // Calling req.oncomplete as well is a SECOND callback -- ERR_MULTIPLE_CALLBACK.
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

    // ---- read ----------------------------------------------------------------
    readStart() {
      // `reading` is NODE's flag and is already true by the time this is called, so
      // guarding on it would mean the pump never starts (see tcp-wrap).
      if (this._pumping || this._closed || this.fd < 0) return 0;
      this._pumping = true;
      this._setNonBlock(true);
      const tick = () => {
        if (!this._pumping || this._closed) return;
        for (;;) {
          const p = mem.alloc(BUF);
          const n = call('read', this.fd, p, BUF);
          if (n > 0) {
            const bytes = mem.u8().slice(p, p + n);
            mem.reset();
            streamBaseState[kReadBytesOrError] = n;
            streamBaseState[kArrayBufferOffset] = 0;
            if (this.onread) this.onread(Buffer.from(bytes));
            continue;                                   // drain what is queued
          }
          mem.reset();
          if (n === 0) {                                // EOF: the child closed its end
            streamBaseState[kReadBytesOrError] = uvErrno.UV_EOF;
            this._pumping = false;
            if (this.onread) this.onread(Buffer.alloc(0));
            return;
          }
          if (-n === EAGAIN || -n === EINTR) break;      // nothing right now
          streamBaseState[kReadBytesOrError] = n;
          this._pumping = false;
          if (this.onread) this.onread(Buffer.alloc(0));
          return;
        }
        this._pump = later(tick, 1);
      };
      this._pump = later(tick, 0);
      return 0;
    }
    readStop() {
      this._pumping = false;
      cancel(this._pump); this._pump = null;
      return 0;
    }

    // A pipe has no half-close: shutting down the writable side IS closing the fd,
    // and it must actually happen or the child's read end never sees EOF -- which is
    // exactly what `child.stdin.end()` is asking for.
    shutdown(req) {
      this.readStop();
      if (this.fd >= 0) { call('close', this.fd); this.fd = -1; }
      this._closed = true;
      if (req) {
        if (pending) pending.n++;
        queueMicrotask(() => {
          if (pending) pending.n--;
          if (req.oncomplete) req.oncomplete(0, this, req);
        });
      }
      return 0;
    }

    close(cb) {
      if (this._closed) { if (cb) queueMicrotask(cb); return; }
      this._closed = true;
      this.readStop();
      if (this.fd >= 0) { call('close', this.fd); this.fd = -1; }
      if (cb) {
        if (pending) pending.n++;
        queueMicrotask(() => { if (pending) pending.n--; cb(); });
      }
    }

    // Surface node asks for but that means nothing for a pipe we already own.
    bind() { return 0; }
    listen() { return 0; }
    connect() { return 0; }
    ref() {}
    unref() {}
    setBlocking() { return 0; }
    fchmod() { return 0; }
    getsockname() { return 0; }
    getpeername() { return 0; }
    hasRef() { return this._pumping; }
  }

  return {
    Pipe,
    // libuv's uv_pipe_type values, which child_process passes back to us verbatim.
    constants: { SOCKET: 0, SERVER: 1, IPC: 2, UV_READABLE: 1, UV_WRITABLE: 2 },
  };
}

module.exports = { makePipeWrap };
