// Reapply the walios-node kernel change to walios/wali-worker.js.
//
// /walios/ is in .git/info/exclude, so this change cannot be committed and is lost
// whenever the file is regenerated or overwritten by another session -- which has
// already happened once. Idempotent: safe to run any time.
//
//   node walios-node-poc/apply-kernel-patch.mjs          apply
//   node walios-node-poc/apply-kernel-patch.mjs --check   report only
//   node walios-node-poc/apply-kernel-patch.mjs --revert  remove
//   node walios-node-poc/apply-kernel-patch.mjs <path>    patch that file instead
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

// A path argument lets this run against a COPY of a deployed kernel, so the
// server's own file can be patched in place rather than overwritten with a
// local one that may be missing another session's changes.
const pathArg = process.argv.slice(2).find((a) => !a.startsWith('--'));
const KERNEL = pathArg || join(dirname(fileURLToPath(new URL('.', import.meta.url))), 'walios', 'wali-worker.js');
const mode = process.argv.includes('--check') ? 'check' : process.argv.includes('--revert') ? 'revert' : 'apply';

const CONSTS_ANCHOR = 'const modSigs = new Map();';
const CONSTS = `// walios-node: a process whose USERSPACE is JavaScript on the page's own V8 rather
// than a wasm guest. Everything else is identical -- same control block, same
// syscalls, same pid, same fd table -- so only the worker script differs.
// node-stub.wasm is a real WALI module declaring the syscall imports and a shared
// env.memory, purely so _workerPlan() can derive names/sigs/memory the way it does
// for any guest; the node worker never instantiates it. See walios-node-poc/.
const NODE_STUB_RE = /node-stub\\.wasm/;
const NODE_WORKER_URL = '/walios-node-poc/node-proc-worker.js';
`;

const SPAWN_FROM = "    const w = new Worker('wali-proc-worker.js');\n    this.procWorker = w;";
const SPAWN_TO = "    const w = new Worker(NODE_STUB_RE.test(this.modKey) ? NODE_WORKER_URL : 'wali-proc-worker.js');\n    this.procWorker = w;";

// A real walios bug, not a walios-node one. POSIX says write(fd, buf, 0) on a pipe
// transfers nothing, but the kernel pushed an EMPTY chunk and woke the reader; the
// reader then read 0 bytes and took it for EOF. Any guest that probed a pipe with a
// zero-length write silently killed its own pipeline.
const NL = String.fromCharCode(10);
const PIPE_FROM = "          h.fifo.chunks.push(S.u8.slice(a[1], a[1] + a[2])); wakePipe(h.fifo); return BigInt(a[2]); }";
const PIPE_TO = [
  "          // POSIX: a 0-length write to a pipe transfers nothing and has no effect.",
  "          // Pushing an empty chunk woke the reader, which read 0 bytes and took it",
  "          // for EOF -- a writer that probed with write(fd, p, 0) silently killed its",
  "          // own pipeline.",
  "          if (a[2] === 0) return 0n;",
  PIPE_FROM,
].join(NL);
const SPAIR_FROM = "          h.spair.wr.chunks.push(S.u8.slice(a[1], a[1] + a[2])); wakePipe(h.spair.wr); return BigInt(a[2]); }";
const SPAIR_TO = [
  "          if (a[2] === 0) return 0n;                                   // same rule as the pipe above",
  SPAIR_FROM,
].join(NL);

let src = readFileSync(KERNEL, 'utf8');
const hasConsts = src.includes('const NODE_STUB_RE');
const hasSpawn = src.includes('NODE_STUB_RE.test(this.modKey)');
const hasPipe = src.includes('a 0-length write to a pipe transfers nothing');

if (mode === 'check') {
  console.log('constants     :', hasConsts ? 'present' : 'MISSING');
  console.log('spawn hook    :', hasSpawn ? 'present' : 'MISSING');
  console.log('0-len pipe fix:', hasPipe ? 'present' : 'MISSING');
  process.exit(hasConsts && hasSpawn && hasPipe ? 0 : 1);
}

if (mode === 'revert') {
  if (hasConsts) src = src.replace(CONSTS, '');
  if (hasSpawn) src = src.replace(SPAWN_TO, SPAWN_FROM);
  if (hasPipe) { src = src.replace(PIPE_TO, PIPE_FROM).replace(SPAIR_TO, SPAIR_FROM); }
  writeFileSync(KERNEL, src);
  // Report what actually came out, not what we attempted: an anchor that has drifted
  // leaves a hunk in place, and silently claiming success would hide that.
  const after = readFileSync(KERNEL, 'utf8');
  const left = [
    after.includes('const NODE_STUB_RE') && 'constants',
    after.includes('NODE_STUB_RE.test(this.modKey)') && 'spawn hook',
    after.includes('a 0-length write to a pipe transfers nothing') && '0-len pipe fix',
  ].filter(Boolean);
  console.log(left.length ? 'reverted, but still present: ' + left.join(', ') : 'reverted');
  process.exit(left.length ? 1 : 0);
}

let changed = 0;
if (!hasConsts) {
  if (!src.includes(CONSTS_ANCHOR)) { console.error('FAILED: anchor not found: ' + CONSTS_ANCHOR); process.exit(2); }
  src = src.replace(CONSTS_ANCHOR, CONSTS + CONSTS_ANCHOR);
  changed++;
}
if (!hasSpawn) {
  // The threadSpawn path has an identical line; only the FIRST (runInWorker) is patched.
  if (!src.includes(SPAWN_FROM)) { console.error('FAILED: spawn anchor not found'); process.exit(2); }
  src = src.replace(SPAWN_FROM, SPAWN_TO);
  changed++;
}

if (!hasPipe) {
  if (!src.includes(PIPE_FROM)) { console.error('FAILED: pipe anchor not found'); process.exit(2); }
  src = src.replace(PIPE_FROM, PIPE_TO);
  if (src.includes(SPAIR_FROM)) src = src.replace(SPAIR_FROM, SPAIR_TO);
  changed++;
}

if (!changed) { console.log('already applied; nothing to do'); process.exit(0); }

// Never write a kernel that does not parse.
try { new Function(src); }
catch (e) { console.error('FAILED: patched kernel does not parse: ' + e.message); process.exit(2); }

writeFileSync(KERNEL, src);
console.log('applied (' + changed + ' hunk' + (changed === 1 ? '' : 's') + ') to ' + KERNEL);
