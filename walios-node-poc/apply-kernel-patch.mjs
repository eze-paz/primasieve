// Reapply the walios-node kernel change to walios/wali-worker.js.
//
// /walios/ is in .git/info/exclude, so this change cannot be committed and is lost
// whenever the file is regenerated or overwritten by another session -- which has
// already happened once. Idempotent: safe to run any time.
//
//   node walios-node-poc/apply-kernel-patch.mjs          apply
//   node walios-node-poc/apply-kernel-patch.mjs --check   report only
//   node walios-node-poc/apply-kernel-patch.mjs --revert  remove
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

const KERNEL = join(dirname(fileURLToPath(new URL('.', import.meta.url))), 'walios', 'wali-worker.js');
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

let src = readFileSync(KERNEL, 'utf8');
const hasConsts = src.includes('const NODE_STUB_RE');
const hasSpawn = src.includes('NODE_STUB_RE.test(this.modKey)');

if (mode === 'check') {
  console.log('constants  :', hasConsts ? 'present' : 'MISSING');
  console.log('spawn hook :', hasSpawn ? 'present' : 'MISSING');
  process.exit(hasConsts && hasSpawn ? 0 : 1);
}

if (mode === 'revert') {
  if (hasConsts) src = src.replace(CONSTS, '');
  if (hasSpawn) src = src.replace(SPAWN_TO, SPAWN_FROM);
  writeFileSync(KERNEL, src);
  console.log('reverted');
  process.exit(0);
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

if (!changed) { console.log('already applied; nothing to do'); process.exit(0); }

// Never write a kernel that does not parse.
try { new Function(src); }
catch (e) { console.error('FAILED: patched kernel does not parse: ' + e.message); process.exit(2); }

writeFileSync(KERNEL, src);
console.log('applied (' + changed + ' hunk' + (changed === 1 ? '' : 's') + ') to ' + KERNEL);
