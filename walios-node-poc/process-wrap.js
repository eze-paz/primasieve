'use strict';
// internalBinding('process_wrap'): async child_process.spawn() over posix_spawn.
//
// The sync half (child-process.js) can block in wait4 because nobody else is running.
// Here we must NOT: this JS process IS the event loop, so blocking in wait4 would stop
// the child's own pipes being drained and deadlock the moment it filled one. So the
// exit is POLLED with WNOHANG on the same `pending`-registered timer the stream pumps
// use, exactly as tcp-wrap polls reads.

const O_CLOEXEC = 0o2000000;
const WNOHANG = 1;
const UV_EINVAL = -22;
const SCRATCH_BYTES = 64 * 1024;

function makeProcessWrap(sys, mem, deps) {
  const { pending, Pipe } = deps;
  const T = deps.trace || (() => {});

  const call = (n, ...a) => {
    try { return Number(sys[n](...a)); }
    catch (e) { T('sys.' + n + ' THREW ' + ((e && e.message) || e)); return UV_EINVAL; }
  };
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

  // A scratch region of our own: spawn holds pointers across several syscalls and an
  // arena.reset() elsewhere would pull them out from under us.
  const SCRATCH = mem.alloc(SCRATCH_BYTES);
  let top = 0;
  const reset = () => { top = 0; };
  const alloc = (n) => { const p = SCRATCH + top; top = (top + n + 7) & ~7; return p; };
  const cstr = (s) => {
    const b = new TextEncoder().encode(String(s));
    const p = alloc(b.length + 1);
    mem.u8().set(b, p);
    mem.u8()[p + b.length] = 0;
    return p;
  };
  const ptrArray = (list) => {
    const ptrs = list.map(cstr);
    const p = alloc((ptrs.length + 1) * 4);
    const d = mem.dv();
    for (let i = 0; i < ptrs.length; i++) d.setInt32(p + i * 4, ptrs[i], true);
    d.setInt32(p + ptrs.length * 4, 0, true);
    return p;
  };
  const pipe2 = (flags) => {
    const p = alloc(8);
    if (call('pipe2', p, flags) < 0) return null;
    const d = mem.dv();
    return [d.getInt32(p, true), d.getInt32(p + 4, true)];
  };

  class Process {
    constructor() {
      this.pid = -1;
      this.onexit = null;
      this._closed = false;
      this._poll = null;
      this._exited = false;
    }

    spawn(options) {
      reset();
      const file = options.file;
      const args = options.args || [file];
      const envPairs = options.envPairs || null;
      const stdio = options.stdio || [];

      const fdmap = [];
      const ours = [];          // the child's ends, which we drop once it is running
      const attach = [];        // [handle, parentFd] to hand to the caller's Pipes

      for (let i = 0; i < stdio.length; i++) {
        const s = stdio[i] || { type: 'ignore' };
        if (s.type === 'pipe' && s.handle) {
          // O_CLOEXEC so the child inherits neither end by accident; it gets exactly
          // the one named in fdmap, and an explicit mapping clears cloexec like dup2.
          const p = pipe2(O_CLOEXEC);
          if (!p) return UV_EINVAL;
          const [rd, wr] = p;
          // readable/writable describe the CHILD's end: stdin is readable (the child
          // reads it), stdout and stderr are writable.
          if (s.readable) { fdmap.push([i, rd]); ours.push(rd); attach.push([s.handle, wr]); }
          else { fdmap.push([i, wr]); ours.push(wr); attach.push([s.handle, rd]); }
        } else if (s.type === 'fd' && typeof s.fd === 'number') {
          fdmap.push([i, s.fd]);
        } else {
          fdmap.push([i, -1]);
        }
      }

      const fdmapPtr = alloc(Math.max(1, fdmap.length) * 8);
      const d = mem.dv();
      for (let i = 0; i < fdmap.length; i++) {
        d.setInt32(fdmapPtr + i * 8, fdmap[i][0], true);
        d.setInt32(fdmapPtr + i * 8 + 4, fdmap[i][1], true);
      }

      const pid = call('posix_spawn',
        cstr(file), ptrArray(args), envPairs ? ptrArray(envPairs) : 0,
        fdmapPtr, fdmap.length);
      T('spawn ' + file + ' -> ' + pid);

      // Drop our copies of the child's ends NOW: while we hold a write end open the
      // reader never sees EOF and the stream never ends.
      for (const fd of ours) call('close', fd);
      reset();

      if (pid < 0) {
        for (const [, parentFd] of attach) call('close', parentFd);
        return pid;
      }

      this.pid = pid;
      // Hold the process open for the CHILD'S WHOLE LIFETIME, not just while a poll
      // timer happens to be scheduled. node emits 'exit'/'close' asynchronously, so a
      // handler that starts more work (the common `spawn another one when this closes`
      // shape) runs after the last timer has already dropped its count -- and the
      // worker's drain loop exits the moment the count reaches zero.
      if (pending) { pending.n++; this._alive = true; }
      for (const [handle, parentFd] of attach) handle.open(parentFd);
      this._watch();
      return 0;
    }

    // Poll wait4(WNOHANG) rather than blocking in it: blocking would stop this process
    // servicing the child's pipes, and a child that fills one would then never exit.
    _watch() {
      const st = alloc(8);
      const tick = () => {
        if (this._exited) return;
        mem.dv().setInt32(st, 0, true);
        const r = call('wait4', this.pid, st, WNOHANG, 0);
        if (r === this.pid) {
          const w = mem.dv().getInt32(st, true);
          const termSig = w & 0x7f;
          this._exited = true;
          const code = termSig ? 0 : ((w >> 8) & 0xff);
          T('exit pid=' + this.pid + ' code=' + code + ' sig=' + termSig);
          if (this.onexit) this.onexit(code, termSig || 0);
          this._release();
          return;
        }
        if (r < 0) {                       // ECHILD: already reaped, or never ours
          this._exited = true;
          if (this.onexit) this.onexit(0, 0);
          this._release();
          return;
        }
        this._poll = later(tick, 4);
      };
      this._poll = later(tick, 1);
    }

    // Released a MACROTASK after onexit, so anything the 'exit'/'close' handlers queue
    // on nextTick or as a microtask has registered its own work before we let go.
    _release() {
      if (!this._alive) return;
      setTimeout(() => {
        if (!this._alive) return;
        this._alive = false;
        if (pending && pending.n > 0) pending.n--;
      }, 0);
    }

    kill(signal) {
      if (this.pid < 0 || this._exited) return UV_EINVAL;
      return call('kill', this.pid, signal || 15);
    }

    close(cb) {
      if (this._closed) { if (cb) queueMicrotask(cb); return; }
      this._closed = true;
      cancel(this._poll); this._poll = null;
      this._release();
      if (cb) {
        if (pending) pending.n++;
        queueMicrotask(() => { if (pending) pending.n--; cb(); });
      }
    }

    ref() {}
    unref() {}
    hasRef() { return !this._exited; }
  }

  return { Process };
}

module.exports = { makeProcessWrap };
