// Emits node-stub.wasm -- a minimal WALI module whose ONLY job is to declare the
// syscall imports and a shared memory import.
//
// Why a stub at all: the kernel derives names/sigs/handlers/memory from a real wasm
// module (wali-worker.js _workerPlan -> WebAssembly.Module.imports + parseImportSigs).
// Handing it this module means ZERO changes to that machinery, the control block, or
// the signature plumbing. node-proc-worker.js never instantiates it -- it only reads
// the `names` array the kernel builds from it and calls hostCall() by index.
import { writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const { SYSCALL_NAMES } = createRequire(import.meta.url)('./syscall-bridge.js');

// WALI: pointers/fds/flags are i32, syscalls return i64.
const I32 = 0x7f, I64 = 0x7e;
const SYSCALLS = [
  ['open', 3], ['openat', 4], ['close', 1], ['read', 3], ['write', 3],
  ['lseek', 3], ['fstat', 2], ['stat', 2], ['lstat', 2], ['newfstatat', 4],
  ['mkdir', 2], ['rmdir', 1], ['unlink', 1], ['getdents64', 3], ['access', 2],
  ['ioctl', 3], ['dup', 1], ['fcntl', 3],
  // sockets: net/http go through these, exactly as python and git do
  ['socket', 3], ['connect', 3], ['bind', 3], ['listen', 2], ['accept4', 4],
  ['sendto', 6], ['recvfrom', 6], ['setsockopt', 5], ['getsockopt', 5], ['shutdown', 2],
  ['getrandom', 3],
  ['rename', 2], ['ftruncate', 2], ['fsync', 1], ['readlink', 3], ['chdir', 1],
  ['getcwd', 2], ['exit_group', 1], ['exit', 1],
  // processes. posix_spawn(path, argv, envp, fdmap, fdmapLen) is this kernel's own:
  // see syscall-bridge.js for why fork+exec cannot serve a JS process.
  ['posix_spawn', 5], ['wait4', 4], ['pipe2', 2], ['dup2', 2], ['dup3', 3],
  ['poll', 3], ['kill', 2], ['socketpair', 4],
];
// (name, params, result) for the non-SYS wali imports
const WALI_MISC = [
  ['__cl_get_argc', [], I32],
  ['__cl_get_argv_len', [I32], I32],
  ['__cl_copy_argv', [I32, I32], I32],
  ['__proc_exit', [I32], null],
  ['__get_init_envfile', [I32, I32], I32],
];

const uleb = (n) => { const out = []; do { let b = n & 0x7f; n >>>= 7; if (n) b |= 0x80; out.push(b); } while (n); return out; };
const sleb = (n) => uleb(n < 0 ? n >>> 0 : n);
const str = (s) => { const b = [...new TextEncoder().encode(s)]; return [...uleb(b.length), ...b]; };
const section = (id, body) => [id, ...uleb(body.length), ...body];
const vec = (items) => [...uleb(items.length), ...items.flat()];

// --- type section: one functype per distinct (params, result) ----------------
const types = [];
const typeIdx = new Map();
const typeOf = (params, result) => {
  const key = params.join(',') + '->' + (result ?? 'v');
  if (typeIdx.has(key)) return typeIdx.get(key);
  const idx = types.length;
  types.push([0x60, ...uleb(params.length), ...params, ...(result === null ? [0] : [1, result])]);
  typeIdx.set(key, idx);
  return idx;
};

// --- imports -----------------------------------------------------------------
const imports = [];
for (const [name, argc] of SYSCALLS) {
  imports.push([...str('wali'), ...str('SYS_' + name), 0x00, ...uleb(typeOf(Array(argc).fill(I32), I64))]);
}
for (const [name, params, result] of WALI_MISC) {
  imports.push([...str('wali'), ...str(name), 0x00, ...uleb(typeOf(params, result))]);
}
// Shared memory, imported: this is what makes the kernel create it and makes
// memory.buffer a SharedArrayBuffer the kernel can read guest pointers out of.
// limits flag 0x03 = has-max | shared.
const PAGES_INIT = 256;      // 16 MB scratch is plenty for syscall argument marshalling
const PAGES_MAX = 4096;      // 256 MB
imports.push([...str('env'), ...str('memory'), 0x02, 0x03, ...uleb(PAGES_INIT), ...uleb(PAGES_MAX)]);

// --- a trivial _start so the module is well-formed ---------------------------
const startType = typeOf([], null);
const funcs = [...uleb(1), ...uleb(startType)];
const exports_ = vec([[...str('_start'), 0x00, ...uleb(SYSCALLS.length + WALI_MISC.length)]]);
const body = [...uleb(0), 0x0b];                         // no locals, end
const code = vec([[...uleb(body.length), ...body]]);

// Guard: the stub must declare exactly the canonical list, or a harness will build a
// `names` array that does not match the stub's imports and syscalls silently vanish.
{
  const declared = SYSCALLS.map(([n]) => n).sort().join(',');
  const canonical = [...SYSCALL_NAMES].sort().join(',');
  if (declared !== canonical) {
    console.error('MISMATCH with syscall-bridge.js SYSCALL_NAMES');
    console.error('  only in stub  :', SYSCALLS.map(([n]) => n).filter((n) => !SYSCALL_NAMES.includes(n)).join(' ') || '(none)');
    console.error('  only in bridge:', SYSCALL_NAMES.filter((n) => !SYSCALLS.some(([m]) => m === n)).join(' ') || '(none)');
    process.exit(1);
  }
}

const wasm = Uint8Array.from([
  0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,        // magic + version
  ...section(1, vec(types)),
  ...section(2, vec(imports)),
  ...section(3, funcs),
  ...section(7, exports_),
  ...section(10, code),
]);

// validate before writing -- a malformed stub would fail deep inside the kernel
const mod = new WebAssembly.Module(wasm);
const imps = WebAssembly.Module.imports(mod);
writeFileSync(new URL('./node-stub.wasm', import.meta.url), wasm);
console.log('node-stub.wasm:', wasm.length, 'bytes,', imps.length, 'imports');
console.log('  syscalls:', SYSCALLS.map(([n]) => n).join(' '));
console.log('  memory  :', imps.find((i) => i.kind === 'memory') ? 'imported shared' : 'MISSING');
