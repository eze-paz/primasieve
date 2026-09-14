'use strict';
// KernelVfs -- the same interface as vfs.js, but every operation is a REAL syscall
// into wali-worker.js over the SharedArrayBuffer control block.
//
// This is the whole point of Phase 1: node's lib/fs.js is unchanged, bindings.js is
// unchanged; only what sits under them changes from an in-memory Map to the walios
// kernel. If suite 1 passes against this, node is doing real I/O on the real VFS.
const { VfsError } = require('./vfs.js');

// errno -> name, for turning a negative syscall return into the error node expects.
const ERRNO = {
  1: 'EPERM', 2: 'ENOENT', 3: 'ESRCH', 4: 'EINTR', 5: 'EIO', 9: 'EBADF', 11: 'EAGAIN',
  12: 'ENOMEM', 13: 'EACCES', 16: 'EBUSY', 17: 'EEXIST', 18: 'EXDEV', 20: 'ENOTDIR',
  21: 'EISDIR', 22: 'EINVAL', 23: 'ENFILE', 24: 'EMFILE', 28: 'ENOSPC', 29: 'ESPIPE',
  30: 'EROFS', 31: 'EMLINK', 32: 'EPIPE', 36: 'ENAMETOOLONG', 38: 'ENOSYS', 39: 'ENOTEMPTY', 40: 'ELOOP',
};

// struct stat, x86-64 layout -- matches wali-worker.js putStat() exactly.
const ST = { DEV: 0, INO: 8, NLINK: 16, MODE: 24, UID: 28, GID: 32, RDEV: 40, SIZE: 48, BLKSIZE: 56, BLOCKS: 64, MTIME: 88, SIZEOF: 144 };

class KernelVfs {
  // `sys` is the syscall bag from node-proc-worker (sys.open, sys.read, ...).
  // `mem` is the marshalling arena inside the shared memory.
  constructor(sys, mem) {
    this.sys = sys;
    this.mem = mem;
    this.calls = 0;
    // Kept for interface parity with the in-memory Vfs (run3 prints them). The kernel
    // owns the real state; these are only ever a local mirror of what we created.
    this.files = new Map();
    this.dirs = new Set(['/']);
  }

  _check(r, syscall, path) {
    this.calls++;
    const n = Number(r);
    if (n < 0) throw new VfsError(ERRNO[-n] || ('ERRNO_' + -n), syscall, path);
    return n;
  }

  _norm(p) {
    if (typeof p !== 'string') p = String(p);
    p = p.split(String.fromCharCode(92)).join('/');
    const out = [];
    for (const part of p.split('/')) { if (!part || part === '.') continue; if (part === '..') out.pop(); else out.push(part); }
    return '/' + out.join('/');
  }

  open(path, flags, mode) {
    const p = this._norm(path);
    const ptr = this.mem.cstr(p);
    const fd = this._check(this.sys.open(ptr, flags | 0, mode === undefined ? 0o666 : mode), 'open', p);
    this.mem.reset();
    (this._opened || (this._opened = new Set())).add(fd);
    if (flags & 0o100) this.files.set(p, true);
    return fd;
  }

  close(fd) {
    // Closing fd 0/1/2 by accident detaches this process from the shell's pipeline:
    // writers drops to 0, the reader takes EOF and exits, and every later write to
    // fd 1 comes back EPIPE. Loud on purpose.
    // Closing an fd we never opened would drop a handle the shell still owns --
    // e.g. the pipe's write end -- making the reader take EOF and exit.
    if (!this._opened || !this._opened.has(fd)) {
      try {
        const b = new TextEncoder().encode('[vfs] CLOSE OF UNOWNED FD ' + fd + String.fromCharCode(10));
        const p = this.mem.bytes(b); this.sys.write(2, p, b.length); this.mem.reset();
      } catch (_) {}
    } else { this._opened.delete(fd); }
    this._check(this.sys.close(fd), 'close');
  }

  read(fd, buf, off, len, pos) {
    if (len <= 0) return 0;
    const scratch = this.mem.alloc(len);
    let n;
    if (pos === null || pos === undefined || pos < 0) {
      n = this._check(this.sys.read(fd, scratch, len), 'read');
    } else {
      // No pread in the stub import list; seek then read (single-threaded guest, safe).
      this._check(this.sys.lseek(fd, pos, 0), 'lseek');
      n = this._check(this.sys.read(fd, scratch, len), 'read');
    }
    if (n > 0) buf.set(this.mem.u8().subarray(scratch, scratch + n), off);
    this.mem.reset();
    return n;
  }

  write(fd, bytes, pos) {
    // Never issue a 0-length write. POSIX says it transfers nothing; walios used to
    // push an empty chunk into a pipe, which the reader took for EOF.
    if (!bytes || bytes.length === 0) return 0;
    if (pos !== null && pos !== undefined && pos >= 0) this._check(this.sys.lseek(fd, pos, 0), 'lseek');
    const ptr = this.mem.bytes(bytes);
    const n = this._check(this.sys.write(fd, ptr, bytes.length), 'write');
    this.mem.reset();
    return n;
  }

  _statAt(kind, arg, path) {
    const sbuf = this.mem.alloc(ST.SIZEOF);
    if (kind === 'fstat') this._check(this.sys.fstat(arg, sbuf), 'fstat');
    else {
      const ptr = this.mem.cstr(this._norm(arg));
      this._check(this.sys[kind](ptr, sbuf), kind, this._norm(arg));
    }
    const dv = this.mem.dv();
    const mode = dv.getUint32(sbuf + ST.MODE, true);
    const out = {
      mode,
      size: Number(dv.getBigUint64(sbuf + ST.SIZE, true)),
      ino: Number(dv.getBigUint64(sbuf + ST.INO, true)),
      mtime: Number(dv.getBigInt64(sbuf + ST.MTIME, true)) * 1000
             + Math.floor(Number(dv.getBigInt64(sbuf + ST.MTIME + 8, true)) / 1e6),
      isDir: (mode & 0o170000) === 0o040000,
    };
    this.mem.reset();
    return out;
  }

  statPath(path) { return this._statAt('stat', path); }
  statFd(fd) { return this._statAt('fstat', fd); }

  mkdir(path) {
    const p = this._norm(path);
    const ptr = this.mem.cstr(p);
    this._check(this.sys.mkdir(ptr, 0o755), 'mkdir', p);
    this.mem.reset();
    this.dirs.add(p);
  }

  unlink(path) {
    const p = this._norm(path);
    const ptr = this.mem.cstr(p);
    this._check(this.sys.unlink(ptr), 'unlink', p);
    this.mem.reset();
    this.files.delete(p);
  }

  rename(from, to) {
    const a = this._norm(from), b = this._norm(to);
    const pa = this.mem.cstr(a), pb = this.mem.cstr(b);
    this._check(this.sys.rename(pa, pb), 'rename', a);
    this.mem.reset();
    this.files.delete(a); this.files.set(b, true);
  }

  rmdir(path) {
    const p = this._norm(path);
    const ptr = this.mem.cstr(p);
    this._check(this.sys.rmdir(ptr), 'rmdir', p);
    this.mem.reset();
    this.dirs.delete(p);
  }

  // O_RDONLY | O_DIRECTORY, then getdents64 until it returns 0.
  readdir(path) {
    const p = this._norm(path);
    const ptr = this.mem.cstr(p);
    const fd = this._check(this.sys.open(ptr, 0o200000, 0), 'scandir', p);   // O_DIRECTORY
    this.mem.reset();
    (this._opened || (this._opened = new Set())).add(fd);
    const out = [];
    try {
      const BUF = 8192;
      for (;;) {
        const buf = this.mem.alloc(BUF);
        const n = this._check(this.sys.getdents64(fd, buf, BUF), 'scandir', p);
        if (n === 0) { this.mem.reset(); break; }
        const dv = this.mem.dv(), u8 = this.mem.u8();
        let off = 0;
        while (off < n) {
          const reclen = dv.getUint16(buf + off + 16, true);
          if (!reclen) break;
          let e = buf + off + 19;
          while (u8[e]) e++;
          const name = new TextDecoder().decode(u8.slice(buf + off + 19, e));
          if (name !== '.' && name !== '..') out.push(name);
          off += reclen;
        }
        this.mem.reset();
      }
    } finally { this.close(fd); }
    return out;
  }

  // POSIX isatty: TCGETS succeeds only on a terminal. walios serves 0x5401 for pty
  // fds and answers ENOTTY for anything else, so this is the real test -- not a
  // guess from st_mode, which reports a char device for plain std fds too.
  isatty(fd) {
    const buf = this.mem.alloc(64);
    let ok = false;
    try { ok = Number(this.sys.ioctl(fd, 0x5401, buf)) === 0; } catch (_) { ok = false; }
    this.mem.reset();
    return ok;
  }

  // Blocking read of up to `max` bytes. The kernel serves reads asynchronously, so
  // the guest simply parks in Atomics.wait -- no event loop needed.
  readFd(fd, max) {
    const scratch = this.mem.alloc(max);
    const n = this._check(this.sys.read(fd, scratch, max), 'read');
    const out = n > 0 ? this.mem.u8().slice(scratch, scratch + n) : new Uint8Array(0);
    this.mem.reset();
    return out;
  }

  // Everything until EOF -- what `node < file` and `echo x | node` need.
  readAll(fd) {
    const parts = [];
    let total = 0;
    for (;;) {
      const b = this.readFd(fd, 65536);
      if (!b.length) break;
      parts.push(b); total += b.length;
    }
    const out = new Uint8Array(total);
    let off = 0;
    for (const p of parts) { out.set(p, off); off += p.length; }
    return out;
  }

  // 1 = file, 0 = dir, -1 = missing. Matches vfs.js so bindings.js is unchanged.
  exists(path) {
    try { const st = this.statPath(path); return st.isDir ? 0 : 1; }
    catch (_) { this.mem.reset(); return -1; }
  }
}

module.exports = { KernelVfs, ERRNO, ST };
