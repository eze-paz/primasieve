'use strict';
// child_process over the kernel's posix_spawn.
//
// Node builds child_process on fork()+exec. That is not available to us: this kernel's
// fork()/vfork() snapshot a WASM IMAGE -- asyncify stack plus linear memory -- and a JS
// process has neither, which is why the kernel answers execve-outside-a-fork-window with
// ENOSYS. So the kernel grew posix_spawn (apply-kernel-patch.mjs hunk 4): make a new pid
// directly, with an explicit fd redirection list instead of the child running code
// between fork and exec. Everything after that -- wait4, SIGCHLD, pipes -- is the
// machinery ash and git already use, unchanged.
//
// Serves internalBinding('spawn_sync'). The async process_wrap path is not here yet.

// uv-style negative errnos. node hands result.error to ErrnoException, which calls
// getSystemErrorName() and throws on anything that is not a number.
const UV_ENOENT = -2, UV_EINVAL = -22, UV_ECHILD = -10;
const O_CLOEXEC = 0o2000000;
const POLLIN = 0x001, POLLERR = 0x008, POLLHUP = 0x010;
const SCRATCH_BYTES = 1 << 20;
const CHUNK = 65536;

function makeChildProcess(sys, mem, opts) {
  const getBuffer = opts.getBuffer;

  // A scratch region of our own: a spawn holds pointers across many syscalls, and an
  // arena.reset() somewhere else would pull them out from under us mid-call.
  const SCRATCH = mem.alloc(SCRATCH_BYTES);
  let top = 0;
  const reset = () => { top = 0; };
  const alloc = (n) => { const p = SCRATCH + top; top = (top + n + 7) & ~7; return p; };
  const u8 = () => mem.u8();
  const dv = () => mem.dv();

  const cstr = (s) => {
    const b = new TextEncoder().encode(String(s));
    const p = alloc(b.length + 1);
    u8().set(b, p);
    u8()[p + b.length] = 0;
    return p;
  };
  // NULL-terminated array of pointers, the shape execve takes.
  const ptrArray = (list) => {
    const ptrs = list.map(cstr);
    const p = alloc((ptrs.length + 1) * 4);
    const d = dv();
    for (let i = 0; i < ptrs.length; i++) d.setInt32(p + i * 4, ptrs[i], true);
    d.setInt32(p + ptrs.length * 4, 0, true);
    return p;
  };

  const pipe2 = (flags) => {
    const p = alloc(8);
    const r = Number(sys.pipe2(p, flags));
    if (r < 0) throw Object.assign(new Error('pipe2'), { errno: -r });
    const d = dv();
    return [d.getInt32(p, true), d.getInt32(p + 4, true)];
  };
  const close = (fd) => { if (fd >= 0) { try { sys.close(fd); } catch (_) {} } };

  // Read from every pipe until all have hit EOF. Draining stdout fully and stderr
  // afterwards deadlocks as soon as a child fills the stderr pipe while we block on
  // stdout -- which is why node polls, and so do we.
  function drain(readers, maxBuffer) {
    for (const r of readers) { r.chunks = []; r.total = 0; }
    const buf = alloc(CHUNK);
    const pfds = alloc(Math.max(1, readers.length) * 8);
    let open = readers.filter((r) => r.fd >= 0);
    while (open.length) {
      const d = dv();
      for (let i = 0; i < open.length; i++) {
        d.setInt32(pfds + i * 8, open[i].fd, true);
        d.setInt16(pfds + i * 8 + 4, POLLIN, true);
        d.setInt16(pfds + i * 8 + 6, 0, true);
      }
      if (Number(sys.poll(pfds, open.length, -1)) < 0) break;
      const still = [];
      for (let i = 0; i < open.length; i++) {
        const r = open[i];
        const rev = dv().getInt16(pfds + i * 8 + 6, true);
        if (!(rev & (POLLIN | POLLHUP | POLLERR))) { still.push(r); continue; }
        const got = Number(sys.read(r.fd, buf, CHUNK));
        if (got > 0) {
          if (r.total + got <= maxBuffer) r.chunks.push(u8().slice(buf, buf + got));
          r.total += got;
          still.push(r);
        }
        // 0 is EOF and a negative is an error we cannot act on here. Either way this fd
        // leaves the set -- keep it and poll spins forever on a dead pipe.
      }
      open = still;
    }
    for (const r of readers) {
      let size = 0;
      for (const c of r.chunks) size += c.length;
      const out = new Uint8Array(size);
      let o = 0;
      for (const c of r.chunks) { out.set(c, o); o += c.length; }
      r.buf = out;
    }
  }

  function waitFor(pid) {
    const st = alloc(8);
    dv().setInt32(st, 0, true);
    const r = Number(sys.wait4(pid, st, 0, 0));
    const wRaw = dv().getInt32(st, true);
    if (opts.trace) opts.trace('wait4(' + pid + ') -> r=' + r + ' status=0x' + (wRaw >>> 0).toString(16));
    if (r < 0) return { status: null, signal: null, errno: -r };
    const w = wRaw;
    // POSIX wait status: the low 7 bits are the terminating signal, byte 1 the exit code.
    const termSig = w & 0x7f;
    if (termSig) return { status: null, signal: termSig, errno: 0 };
    return { status: (w >> 8) & 0xff, signal: null, errno: 0 };
  }

  return {
    spawn(options) {
      reset();
      const Buffer = getBuffer();
      const file = options.file;
      const args = options.args || [file];
      const envPairs = options.envPairs || null;
      const stdio = options.stdio || [];
      const maxBuffer = options.maxBuffer === undefined ? Infinity : options.maxBuffer;

      const fdmap = [];          // [childFd, parentFd] pairs handed to posix_spawn
      const ours = [];           // the child's ends, which WE must drop after the spawn
      const readers = [];
      let stdinWrite = -1, stdinInput = null;

      try {
        for (let i = 0; i < stdio.length; i++) {
          const s = stdio[i] || { type: 'ignore' };
          if (s.type === 'pipe') {
            // O_CLOEXEC so the child inherits neither end by accident: it gets exactly
            // the one named in fdmap, and an explicit mapping clears cloexec the way
            // dup2 does.
            const [rd, wr] = pipe2(O_CLOEXEC);
            if (i === 0) {
              fdmap.push([0, rd]); ours.push(rd);
              stdinWrite = wr; stdinInput = s.input || null;
            } else {
              fdmap.push([i, wr]); ours.push(wr);
              readers.push({ fd: rd, slot: i });
            }
          } else if (s.type === 'fd' && typeof s.fd === 'number') {
            fdmap.push([i, s.fd]);
          } else {
            fdmap.push([i, -1]);                    // 'ignore': the child gets nothing
          }
        }

        const fdmapPtr = alloc(Math.max(1, fdmap.length) * 8);
        const d = dv();
        for (let i = 0; i < fdmap.length; i++) {
          d.setInt32(fdmapPtr + i * 8, fdmap[i][0], true);
          d.setInt32(fdmapPtr + i * 8 + 4, fdmap[i][1], true);
        }

        const pid = Number(sys.posix_spawn(
          cstr(file), ptrArray(args), envPairs ? ptrArray(envPairs) : 0,
          fdmapPtr, fdmap.length));

        if (opts.trace) opts.trace('posix_spawn(' + file + ') -> ' + pid + ' fdmap=' + JSON.stringify(fdmap));
        // Drop our copies of the child's ends NOW. While we hold a write end open the
        // reader never sees EOF and drain() blocks forever on a pipe nobody will close.
        for (const fd of ours) close(fd);

        if (pid < 0) {
          for (const r of readers) close(r.fd);
          close(stdinWrite);
          return { pid: -1, output: null, status: null, signal: null,
                   error: pid === -2 ? UV_ENOENT : UV_EINVAL };
        }

        if (stdinWrite >= 0) {
          if (stdinInput && stdinInput.length) {
            const b = new Uint8Array(stdinInput.buffer || stdinInput,
                                     stdinInput.byteOffset || 0, stdinInput.length);
            let off = 0;
            while (off < b.length) {
              const n = Math.min(CHUNK, b.length - off);
              const p = alloc(n);
              u8().set(b.subarray(off, off + n), p);
              const wrote = Number(sys.write(stdinWrite, p, n));
              if (wrote <= 0) break;                // the child closed stdin; not fatal
              off += wrote;
            }
          }
          close(stdinWrite);
        }

        drain(readers, maxBuffer);
        for (const r of readers) close(r.fd);
        const w = waitFor(pid);

        const output = [null, null, null];
        for (const r of readers) output[r.slot] = Buffer.from(r.buf);
        return { pid, output, status: w.status, signal: w.signal,
                 error: w.errno ? UV_ECHILD : undefined };
      } catch (e) {
        if (opts.trace) opts.trace('spawn_sync threw: ' + ((e && e.stack) || e));
        for (const fd of ours) close(fd);
        for (const r of readers) close(r.fd);
        close(stdinWrite);
        return { pid: -1, output: null, status: null, signal: null, error: UV_EINVAL };
      } finally {
        reset();
      }
    },
  };
}

module.exports = { makeChildProcess };
