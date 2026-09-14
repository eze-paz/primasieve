// A stand-in for wali-worker.js that speaks the IDENTICAL wire protocol:
//   - the same control-block layout (ARGS 64 / RET 192, state word 0)
//   - the same struct stat layout as wali-worker.js putStat()  (x86-64, 144 bytes)
//   - the same linux_dirent64 records as its getdents64 case
//   - the same "negative return = -errno" convention
//
// It exists so the guest half (syscall-bridge.js + kernel-vfs.js + node's lib/fs.js)
// can be verified headlessly. It does NOT prove the real kernel behaves this way --
// the layouts were read out of wali-worker.js, but only a browser run proves the
// round trip end to end.
import { parentPort, workerData } from 'node:worker_threads';

const { ctl, mem, names, argv: argv0 = ['/bin/node'], stdin: STDIN = null, tty: TTY = false } = workerData;
// argv is mutable so one long-lived kernel can serve several `node ...` invocations
// against a SHARED filesystem -- which is what an install-then-require test needs.
// argv lives in SHARED MEMORY, not a postMessage: this kernel parks in Atomics.wait,
// so its event loop never runs and a message handler would never fire. The harness
// writes [i32 count][NUL-separated utf8] at ARGV_BASE before each run.
const ARGV_BASE = 8192;
let ARGV = argv0;
function readArgvFromMemory() {
  const d = dv();
  const n = d.getInt32(ARGV_BASE, true);
  if (n <= 0 || n > 64) return null;
  const m = u8();
  const out = [];
  let p = ARGV_BASE + 4;
  for (let i = 0; i < n; i++) {
    let e = p; while (m[e]) e++;
    out.push(td.decode(m.slice(p, e)));
    p = e + 1;
  }
  return out;
}
const i32 = new Int32Array(ctl);
const i64 = new BigInt64Array(ctl);
const ARGS = 64, RET = 192;
const ST_IDLE = 0, ST_REQ = 1, ST_REPLY = 2;

const u8 = () => new Uint8Array(mem);
const dv = () => new DataView(mem);
const td = new TextDecoder(), te = new TextEncoder();

const E = { EPERM: 1, ENOENT: 2, EBADF: 9, EEXIST: 17, ENOTDIR: 20, EISDIR: 21, EINVAL: 22, ENOTEMPTY: 39 };

// ---- a tiny filesystem, same shape as the kernel's VFS ----------------------
const files = new Map();                       // path -> {data, mode, mtimeMs}
const dirs = new Map([['/', new Set()]]);
const fds = new Map();
let nextFd = 3, inoSeq = 1000;
const inos = new Map();
const inoOf = (p) => { let n = inos.get(p); if (!n) inos.set(p, n = ++inoSeq); return n; };

function norm(p) {
  const out = [];
  for (const part of String(p).split('/')) { if (!part || part === '.') continue; if (part === '..') out.pop(); else out.push(part); }
  return '/' + out.join('/');
}
function mkdirp(p) {
  if (dirs.has(p)) return;
  const parent = p.slice(0, p.lastIndexOf('/')) || '/';
  if (p !== '/') mkdirp(parent);
  dirs.set(p, new Set());
  if (p !== '/') dirs.get(parent).add(p.slice(p.lastIndexOf('/') + 1));
}
function addFile(p, data, mode = 0o100644) {
  const parent = p.slice(0, p.lastIndexOf('/')) || '/';
  mkdirp(parent);
  dirs.get(parent).add(p.slice(p.lastIndexOf('/') + 1));
  files.set(p, { data, mode, mtimeMs: Date.now() });
}
// Seed the things a real walios boot seeds, so "reads a file the shell made" is real.
mkdirp('/tmp'); mkdirp('/root'); mkdirp('/etc');
addFile('/etc/gitconfig', te.encode('[user]\n\tname = walios\n'));
addFile('/etc/hosts', te.encode('127.0.0.1 localhost\n'));
addFile('/etc/passwd', te.encode('root:x:0:0:root:/root:/bin/sh\n'));

const cstr = (ptr) => { const m = u8(); let e = ptr; while (m[e]) e++; return td.decode(m.slice(ptr, e)); };

// struct stat -- mirrors wali-worker.js putStat() exactly
function putStat(p, o) {
  const d = dv();
  u8().fill(0, p, p + 144);
  d.setBigUint64(p, BigInt(o.dev || 1), true);
  d.setBigUint64(p + 8, BigInt(o.ino || 1), true);
  d.setBigUint64(p + 16, 1n, true);
  d.setUint32(p + 24, o.mode, true);
  d.setUint32(p + 28, 0, true);
  d.setUint32(p + 32, 0, true);
  d.setBigUint64(p + 40, 0n, true);
  d.setBigUint64(p + 48, BigInt(o.size), true);
  d.setBigUint64(p + 56, 4096n, true);
  d.setBigUint64(p + 64, BigInt(Math.ceil(o.size / 512)), true);
  const ms = o.mtimeMs || Date.now();
  for (const off of [72, 88, 104]) {
    d.setBigInt64(p + off, BigInt(Math.floor(ms / 1000)), true);
    d.setBigInt64(p + off + 8, BigInt(Math.floor((ms % 1000) * 1e6)), true);
  }
}
function statInto(path, sp) {
  const p = norm(path);
  if (dirs.has(p)) { putStat(sp, { size: 4096, mode: 0o040755, ino: inoOf(p) }); return 0n; }
  const f = files.get(p);
  if (!f) return BigInt(-E.ENOENT);
  putStat(sp, { size: f.data.length, mode: f.mode, mtimeMs: f.mtimeMs, ino: inoOf(p) });
  return 0n;
}

const dirState = new Map();
const stdinBytes = STDIN == null ? new Uint8Array(0) : te.encode(STDIN);
let stdinPos = 0;

function syscall(name, a) {
  switch (name) {
    case 'open': {
      const p = norm(cstr(a[0])), flags = a[1];
      const O_CREAT = 0o100, O_TRUNC = 0o1000, O_DIRECTORY = 0o200000, O_APPEND = 0o2000;
      if (flags & O_DIRECTORY) {
        if (!dirs.has(p)) return BigInt(-(files.has(p) ? E.ENOTDIR : E.ENOENT));
        const fd = nextFd++; fds.set(fd, { path: p, dir: true, pos: 0 }); return BigInt(fd);
      }
      if (dirs.has(p)) return BigInt(-E.EISDIR);
      if (!files.has(p)) { if (!(flags & O_CREAT)) return BigInt(-E.ENOENT); addFile(p, new Uint8Array(0)); }
      else if (flags & O_TRUNC) files.get(p).data = new Uint8Array(0);
      const fd = nextFd++;
      fds.set(fd, { path: p, pos: (flags & O_APPEND) ? files.get(p).data.length : 0 });
      return BigInt(fd);
    }
    case 'ioctl': {
      // TCGETS (0x5401) succeeds only on a terminal -- this IS isatty().
      if ((a[1] >>> 0) === 0x5401) return TTY && a[0] <= 2 ? 0n : BigInt(-25);   // ENOTTY
      return 0n;
    }
    case 'close': { if (!fds.delete(a[0])) return BigInt(-E.EBADF); dirState.delete(a[0]); return 0n; }
    case 'read': {
      if (a[0] === 0) {                                   // stdin
        if (stdinPos >= stdinBytes.length) return 0n;     // EOF
        const n = Math.min(a[2], stdinBytes.length - stdinPos);
        u8().set(stdinBytes.subarray(stdinPos, stdinPos + n), a[1]);
        stdinPos += n;
        return BigInt(n);
      }
      const h = fds.get(a[0]); if (!h || h.dir) return BigInt(-E.EBADF);
      const f = files.get(h.path);
      const n = Math.max(0, Math.min(a[2], f.data.length - h.pos));
      u8().set(f.data.subarray(h.pos, h.pos + n), a[1]);
      h.pos += n; return BigInt(n);
    }
    case 'write': {
      const h = fds.get(a[0]);
      if (a[0] === 1 || a[0] === 2) { parentPort.postMessage({ t: 'out', fd: a[0], s: td.decode(u8().slice(a[1], a[1] + a[2])) }); return BigInt(a[2]); }
      if (!h || h.dir) return BigInt(-E.EBADF);
      const f = files.get(h.path);
      const bytes = u8().slice(a[1], a[1] + a[2]);
      const end = h.pos + bytes.length;
      if (end > f.data.length) { const nd = new Uint8Array(end); nd.set(f.data); f.data = nd; }
      f.data.set(bytes, h.pos); h.pos = end; f.mtimeMs = Date.now();
      return BigInt(bytes.length);
    }
    case 'lseek': {
      const h = fds.get(a[0]); if (!h) return BigInt(-E.EBADF);
      const f = files.get(h.path);
      h.pos = a[2] === 0 ? a[1] : a[2] === 1 ? h.pos + a[1] : f.data.length + a[1];
      return BigInt(h.pos);
    }
    case 'fstat': {
      const h = fds.get(a[0]); if (!h) return BigInt(-E.EBADF);
      return statInto(h.path, a[1]);
    }
    case 'stat': case 'lstat': return statInto(cstr(a[0]), a[1]);
    case 'access': { const p = norm(cstr(a[0])); return (files.has(p) || dirs.has(p)) ? 0n : BigInt(-E.ENOENT); }
    case 'mkdir': { const p = norm(cstr(a[0])); if (dirs.has(p) || files.has(p)) return BigInt(-E.EEXIST); mkdirp(p); return 0n; }
    case 'rmdir': { const p = norm(cstr(a[0])); if (!dirs.has(p)) return BigInt(-E.ENOENT);
      if (dirs.get(p).size) return BigInt(-E.ENOTEMPTY);
      dirs.delete(p); const par = p.slice(0, p.lastIndexOf('/')) || '/';
      if (dirs.has(par)) dirs.get(par).delete(p.slice(p.lastIndexOf('/') + 1)); return 0n; }
    case 'unlink': { const p = norm(cstr(a[0])); if (!files.delete(p)) return BigInt(-E.ENOENT);
      const par = p.slice(0, p.lastIndexOf('/')) || '/';
      if (dirs.has(par)) dirs.get(par).delete(p.slice(p.lastIndexOf('/') + 1)); return 0n; }
    case 'rename': { const from = norm(cstr(a[0])), to = norm(cstr(a[1]));
      const f = files.get(from); if (!f) return BigInt(-E.ENOENT);
      files.delete(from); addFile(to, f.data, f.mode); return 0n; }
    case 'ftruncate': { const h = fds.get(a[0]); if (!h) return BigInt(-E.EBADF);
      const f = files.get(h.path); const nd = new Uint8Array(a[1]); nd.set(f.data.subarray(0, Math.min(a[1], f.data.length))); f.data = nd; return 0n; }
    case 'fsync': return 0n;
    case 'getdents64': {
      const h = fds.get(a[0]); if (!h || !h.dir) return BigInt(-E.EBADF);
      let st = dirState.get(a[0]);
      if (!st) { st = { names: ['.', '..', ...dirs.get(h.path)], pos: 0 }; dirState.set(a[0], st); }
      let off = 0;
      const m = u8(), d = dv();
      while (st.pos < st.names.length) {
        const nm = st.names[st.pos], nb = te.encode(nm);
        const reclen = (19 + nb.length + 1 + 7) & ~7;
        if (off + reclen > a[2]) break;
        const base = a[1] + off;
        m.fill(0, base, base + reclen);
        d.setBigUint64(base, BigInt(inoOf(norm(h.path + '/' + nm))), true);   // d_ino
        d.setBigUint64(base + 8, BigInt(st.pos + 1), true);                   // d_off
        d.setUint16(base + 16, reclen, true);                                 // d_reclen
        m[base + 18] = dirs.has(norm(h.path + '/' + nm)) ? 4 : 8;             // d_type
        m.set(nb, base + 19);
        off += reclen; st.pos++;
      }
      return BigInt(off);
    }
    case 'exit_group': return 0n;
    default: return BigInt(-E.EINVAL);
  }
}

// ---- the serve loop ---------------------------------------------------------
parentPort.postMessage({ t: 'kernel-ready' });
for (;;) {
  const st = Atomics.load(i32, 0);
  if (st !== ST_REQ) { Atomics.wait(i32, 0, st); continue; }
  const idx = Atomics.load(i32, 1), argc = Atomics.load(i32, 2);
  const full = names[idx] || '';
  const a = [];
  for (let k = 0; k < argc; k++) a.push(Number(i64[(ARGS >> 3) + k]));
  let ret = 0n;
  try {
    if (full.startsWith('wali.SYS_')) ret = syscall(full.slice(9), a);
    else if (full === 'wali.__cl_get_argc') { const a2 = readArgvFromMemory(); if (a2) ARGV = a2; ret = BigInt(ARGV.length); }
    else if (full === 'wali.__cl_get_argv_len') ret = BigInt(te.encode(ARGV[a[0]] || '').length);
    else if (full === 'wali.__cl_copy_argv') {
      const b = te.encode(ARGV[a[1]] || '');
      u8().set(b, a[0]); u8()[a[0] + b.length] = 0;
      ret = BigInt(b.length);
    }
    else ret = 0n;
  } catch (e) {
    parentPort.postMessage({ t: 'kernel-error', s: full + ': ' + (e.message || e) });
    ret = BigInt(-E.EINVAL);
  }
  i64[RET >> 3] = ret;
  Atomics.store(i32, 0, ST_REPLY);
  Atomics.notify(i32, 0);
}
