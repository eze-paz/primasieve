# Kernel changes (NOT in git)

`/walios/` is excluded in `.git/info/exclude`, so the changes below live only in the
working tree. They are recorded here so they can be reapplied or reverted.

Total: **three lines**, all additive. Nothing in the process model, control block,
signature plumbing or memory handling was touched.

## 1. Two constants, next to `const modSigs = new Map();` (~line 364)

```js
const NODE_STUB_RE = /node-stub\.wasm/;   // walios-node spike; see runInWorker
const NODE_WORKER_URL = '/walios-node-poc/node-proc-worker.js';
```

## 2. Worker choice in `runInWorker()` (~line 2489)

```js
// was:
const w = new Worker('wali-proc-worker.js');

// now:
const w = new Worker(NODE_STUB_RE.test(this.modKey) ? NODE_WORKER_URL : 'wali-proc-worker.js');
```

A comment above it explains why a stub module exists at all.

## 3. Better worker-load diagnostics (~line 2501, optional)

`w.onerror` now appends `@${ev.filename}:${ev.lineno}`. Independently useful — a worker
that fails to *load* reports a bare `[object Event]`, which is what made the failure in
this spike hard to read.

## To revert

Delete the two constants and restore `new Worker('wali-proc-worker.js')`.

## Why this is the whole integration

`_workerPlan()` derives `names`, `sigs`, `handlers` and the shared `memory` from a real
wasm module via `WebAssembly.Module.imports()` + `parseImportSigs()`. `node-stub.wasm`
is a real WALI module that declares exactly those syscall imports plus a shared
`env.memory`, so all of that machinery works untouched. The node worker never
instantiates it — it only reads the `names` array the kernel builds from it and calls
`hostCall()` by index.

Verified against the kernel's own parsers:

```
parseImportSigs      -> 27 entries
  wali.SYS_open      = {"params":[127,127,127],"results":[126],"retI64":true}
  wali.__cl_get_argc = {"params":[],"results":[127],"retI64":false}
parseSharedMemImport -> {"initial":256,"maximum":4096}
```
