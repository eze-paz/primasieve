'use strict';
// Stand-in for the walios kernel VFS. Deliberately the same SHAPE as the syscalls
// wali-worker.js already serves (open/read/write/close/stat over a path namespace),
// so swapping this for real hostCall() round trips is a mechanical change.
const E = { ENOENT: -2, EBADF: -9, EEXIST: -17, ENOTDIR: -20, EISDIR: -21, EINVAL: -22 };
class VfsError extends Error { constructor(code, sys, path) { super(code); this.errno = E[code]; this.code = code; this.syscall = sys; this.path = path; } }

class Vfs {
  constructor() {
    this.files = new Map();            // path -> { data: Uint8Array, mode, mtime }
    this.dirs  = new Set(['/', '/tmp']);
    this.fds   = new Map();            // fd -> { path, pos, flags }
    this.nextFd = 3;
    this.inoSeq = 1000;
    this.inos = new Map();
    this.calls = [];                   // trace, for the report
  }
  _ino(p) { let n = this.inos.get(p); if (!n) this.inos.set(p, n = ++this.inoSeq); return n; }
  _norm(p) {
    if (typeof p !== 'string') p = String(p);
    p = p.split(String.fromCharCode(92)).join('/');
    const out = [];
    for (const part of p.split('/')) { if (!part || part === '.') continue; if (part === '..') out.pop(); else out.push(part); }
    return '/' + out.join('/');
  }
  open(path, flags, mode) {
    const p = this._norm(path);
    const exists = this.files.has(p);
    const O_CREAT = 0o100, O_TRUNC = 0o1000, O_WRONLY = 1, O_RDWR = 2;
    const acc = flags & 3;
    if (!exists && !(flags & O_CREAT)) throw new VfsError('ENOENT', 'open', p);
    if (!exists) this.files.set(p, { data: new Uint8Array(0), mode: 0o100644, mtime: Date.now() });
    else if (flags & O_TRUNC && (acc === O_WRONLY || acc === O_RDWR)) this.files.get(p).data = new Uint8Array(0);
    const O_APPEND = 0o2000;
    const fd = this.nextFd++;
    this.fds.set(fd, { path: p, pos: (flags & O_APPEND) ? this.files.get(p).data.length : 0, flags });
    return fd;
  }
  close(fd) { if (!this.fds.delete(fd)) throw new VfsError('EBADF', 'close'); }
  _f(fd) { const h = this.fds.get(fd); if (!h) throw new VfsError('EBADF', 'read'); return h; }
  read(fd, buf, off, len, pos) {
    const h = this._f(fd); const f = this.files.get(h.path);
    const start = (pos === null || pos === undefined || pos < 0) ? h.pos : pos;
    const n = Math.max(0, Math.min(len, f.data.length - start));
    buf.set(f.data.subarray(start, start + n), off);
    if (pos === null || pos === undefined || pos < 0) h.pos = start + n;
    return n;
  }
  write(fd, bytes, pos) {
    const h = this._f(fd); const f = this.files.get(h.path);
    const start = (pos === null || pos === undefined || pos < 0) ? h.pos : pos;
    const end = start + bytes.length;
    if (end > f.data.length) { const nd = new Uint8Array(end); nd.set(f.data); f.data = nd; }
    f.data.set(bytes, start);
    f.mtime = Date.now();
    if (pos === null || pos === undefined || pos < 0) h.pos = end;
    return bytes.length;
  }
  statPath(path) { const p = this._norm(path);
    if (this.files.has(p)) return this._stat(p, this.files.get(p));
    if (this.dirs.has(p)) return this._statDir(p);
    throw new VfsError('ENOENT', 'stat', p); }
  statFd(fd) { const h = this._f(fd); return this._stat(h.path, this.files.get(h.path)); }
  _stat(p, f) { return { mode: f.mode, size: f.data.length, ino: this._ino(p), mtime: f.mtime, isDir: false }; }
  _statDir(p) { return { mode: 0o040755, size: 0, ino: this._ino(p), mtime: Date.now(), isDir: true }; }
  mkdir(path) { const p = this._norm(path); if (this.dirs.has(p) || this.files.has(p)) throw new VfsError('EEXIST', 'mkdir', p); this.dirs.add(p); }
  readdir(path) { const p = this._norm(path);
    if (!this.dirs.has(p)) throw new VfsError('ENOENT', 'scandir', p);
    const pre = p === '/' ? '/' : p + '/'; const out = new Set();
    for (const k of [...this.files.keys(), ...this.dirs]) {
      if (k === p || !k.startsWith(pre)) continue;
      out.add(k.slice(pre.length).split('/')[0]);
    }
    return [...out]; }
  unlink(path) { const p = this._norm(path); if (!this.files.delete(p)) throw new VfsError('ENOENT', 'unlink', p); }
  rename(from, to) { const a = this._norm(from), b = this._norm(to);
    const f = this.files.get(a); if (!f) throw new VfsError('ENOENT', 'rename', a);
    this.files.delete(a); this.files.set(b, f); }
  isatty() { return false; }
  readFd() { return new Uint8Array(0); }
  readAll() { return new Uint8Array(0); }
  exists(path) { const p = this._norm(path); return this.files.has(p) ? 1 : this.dirs.has(p) ? 0 : -1; }
}
module.exports = { Vfs, VfsError, E };
