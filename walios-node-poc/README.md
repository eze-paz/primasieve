# walios-node

Running Node.js in the browser at native speed by **borrowing the page's own V8** and
running Node's real `lib/*.js` on a synthetic `internalBinding` wired to the walios
kernel. Two phases done so far.

| suite | what it proves | result |
|---|---|---|
| `run.js` | node's builtins boot on synthetic bindings | 28/28 |
| `run2.js` | encodings, stream data flow, CJS, perf | 22/22 |
| `run3.js` | a multi-file user app via node's real CJS loader | runs |
| `test-kernel-vfs.mjs` | node's fs over the walios syscall protocol | 20/20 |
| `test-node-cli.mjs` | `node -e`, `node script.js`, stdin, REPL | 36/36 |
| `test-browser.mjs` | **real Chromium, real kernel, real ash, real pty** | 17/17 |

## `walios:/root$ node`

The whole point, captured from an actual pty session in `test-browser.mjs`:

```
BusyBox v1.36.1 (2026-09-14) built-in shell (ash)

walios:/root$ node
Welcome to walios-node v22.23.2.
Type .exit to leave, .help for commands.
> 2+2
4
> const who = "walios-repl"
> who
'walios-repl'
> require("path").join("/a","b")
'/a/b'
> require("fs").readFileSync("/etc/hosts","utf8").trim()
'127.0.0.1 localhost'
> .exit
walios:/root$ echo BACK-IN-ASH
BACK-IN-ASH
```

Everything a shell command should do:

```
node -v                            node script.js one two
node -e '...'   node -p '...'      node < file
echo '...' | node                  node -e '...' | grep x
node -e '...' > out.txt            node build.js && echo ok   ($? propagates)
```

One filesystem with the rest of walios: node reads what ash wrote, ash reads what
node wrote, git and python see the same files.

### How the REPL works

Not node's `lib/repl.js`: that drives `vm.createScript`/`runInContext`, and a worker
has no way to make a real realm. `repl.js` here evaluates with `new Function` — the
same V8 either way; what it gives up is vm's isolation, not speed.

There is no readline and no raw mode, because there does not need to be: walios runs
the pty in **canonical mode**, so the kernel already does echo, backspace and line
assembly, and a read on fd 0 returns a finished line.

`isatty` is the real POSIX test — `ioctl(0, TCGETS)`, which walios answers only for a
pty. A tty gets the REPL; a pipe or redirect is read to EOF and run as a script,
exactly as node does.

Known limits: `var`/`let`/`const` at the top level are rewritten to properties of a
persistent scope object, so simple declarations survive across lines but destructuring
ones do not. No tab completion, no history.

---|---|---|
| `run.js` | node's builtins boot on synthetic bindings | 28/28 |
| `run2.js` | encodings, stream data flow, CJS, perf | 22/22 |
| `run3.js` | a multi-file user app via node's real CJS loader | runs |
| `test-kernel-vfs.mjs` | **node's fs over the walios syscall protocol** | 19/19 |
| `test-node-cli.mjs` | **`node -e` and `node script.js`, argv+stdio via syscalls** | 23/23 |
| `test-browser.mjs` | **the real thing: real Chromium, real kernel, real ash** | 9/9 |

---

# Phase 0 — does node's lib/ boot at all?

**Question:** can Node's own `lib/*.js` be booted, unmodified, on a synthetic
`internalBinding` backed by the walios kernel — instead of reimplementing Node's API
surface by hand?

**Answer: yes.** 50/50 assertions pass, including a multi-file user app run by Node's
real CJS loader out of a virtual filesystem.

Nothing in `lib/` is patched. The spike supplies only the six parameters Node's own
`BuiltinLoader` supplies (`lib/internal/bootstrap/realm.js:400`):

```js
fn(exports, require, module, process, internalBinding, primordials)
```

## Run it

```bash
curl -sL https://nodejs.org/dist/v22.23.2/node-v22.23.2.tar.gz | tar -xz --strip-components=1 node-v22.23.2/lib
node run.js ./lib     # 28 assertions: path, events, buffer, fs, util, assert, stream
node run2.js ./lib    # 22 assertions: encodings, stream data flow, CJS, perf
node run3.js ./lib    # a real multi-file app on the vfs
node surface.mjs fs path events   # static binding-surface measurement
```

## What actually runs

Node's real `fs`, `path`, `events`, `buffer`, `util`, `assert`, `stream`,
`querystring`, `string_decoder`, and the real CJS loader. Concretely:

```
fs.writeFileSync            -> wrote 16 bytes to OUR vfs
fs.readFileSync utf8        -> hi from node lib
fs.readFileSync buffer      -> Buffer(16) = hi from node lib
fs.mkdirSync + readdirSync  -> ["a.txt","b.txt"]
ENOENT is a real fs error   -> ENOENT / stat / /missing/deep
util.inspect({a:[1,2]})     -> { a: [ 1, 2 ] }          (byte-identical to real node)
stream Readable -> data     -> chunks=["al","pha"] end=true
stream pipeline R->W        -> ["x","y","z"]
Buffer round-trip (7 encodings, incl. base64url/ucs2/hex)
CJS: multi-file app from vfs -> relative requires, builtins, __dirname, JSON round-trip
```

## The number that matters

Static analysis says `fs`+`path`+`events` reach **56** bindings. That number is
misleading — Node lazy-requires heavily. The measured **runtime** surface is:

| metric | value |
|---|---|
| lib modules loaded | 72 |
| bindings requested | **24** |
| bindings fully stubbed (never really called) | 4 — `async_context_frame` `icu` `mksnapshot` `permission` |
| binding **functions** actually implemented | **142** |
| binding functions missed (all optional paths) | 23 |

So the port surface for a genuinely useful Node is ~150 functions, not thousands —
and roughly 40 of those are `fs`, which maps directly onto syscalls `wali-worker.js`
already serves.

## Four findings worth keeping

1. **The constants table must be the target's, not the host's.** Generating it from a
   Windows Node gave `O_CREAT = 256` instead of Linux's `64`, so every
   `open(..., 'w')` silently failed to create. `constants.json` is now a hand-written
   Linux/x86-64 table — which is what WALI/musl needs anyway.

2. **User code must not reach the host realm.** Node relies on realm globals
   (`globalThis.process`), so under the harness user code read the *host's* process and
   reported `platform=win32`. Fixed by shadowing realm globals as parameters in
   `compileFunctionForCJSLoader`. In the real worker the realm is ours, so this is free
   there — but it proves the isolation seam is a thing you must deliberately close.

3. **`internal/bootstrap/realm` cannot go through the wrapper** — it *is* the loader,
   and declares `internalBinding` itself ("already been declared"). Served synthetically.

4. **`BuiltinModule.canBeRequiredWithoutScheme` must be exact.** Returning true for any
   non-`internal/` string makes `_load` treat `/app/index.js` as a builtin and crash.

## Where the real kernel plugs in

`vfs.js` is a deliberate stand-in with the same *shape* as the syscalls the kernel
already serves. Replacing it with `hostCall()` round trips over the existing
SharedArrayBuffer control block (`walios/wali-proc-worker.js`) is mechanical: same
open/read/write/close/stat, same path namespace.

`contextify.compileFunctionForCJSLoader` is the seam where user source becomes a
callable — `new Function` in the browser, i.e. the page's own V8 with full JIT. That is
why "native speed" is a property of the design, not an aspiration. Measured in-guest:
2e7 arithmetic ops in ~120ms, 20k `Buffer.from().toString('base64')` in ~41ms.

---

# Phase 1 — real syscalls

Phase 0's `vfs.js` was an in-memory stand-in. Phase 1 replaces it with `kernel-vfs.js`,
where every operation is a real syscall over the SharedArrayBuffer control block —
`store args / flip state word / Atomics.wait` — exactly as `wali-proc-worker.js` does.

```
node lib/fs.js   (unchanged)
  -> bindings.js         (unchanged)
    -> kernel-vfs.js     <- NEW: struct stat, linux_dirent64, -errno
      -> syscall-bridge.js  <- NEW: the SAB protocol, shared with the worker
        -> wali-worker.js
```

## How a JS process becomes a walios process

`node-proc-worker.js` is the JS analogue of `wali-proc-worker.js`: same `{t:'init'}`
message, same control block, same pid and fd table — it just boots node's `lib/`
instead of instantiating a wasm module.

The trick that keeps the kernel untouched is `node-stub.wasm` (603 bytes, built by
`mkstub.mjs`): a real WALI module declaring the syscall imports and a shared
`env.memory`. The kernel's `_workerPlan()` derives `names`, `sigs`, `handlers` and the
memory from it exactly as for any guest; the node worker never instantiates it. Total
kernel change: **three lines** — see `kernel-changes.md`.

## Verified (19/19, `node test-kernel-vfs.mjs ./lib`)

Main thread = the guest (node's fs, parking in `Atomics.wait`); worker thread = a mock
kernel speaking wali-worker.js's wire format. It exercises the **real** bridge and vfs
code — the same files the browser worker loads.

```
fs.mkdirSync         [SYS_mkdir]        -> ok
fs.writeFileSync     [SYS_open+write]   -> wrote through syscalls
fs.readFileSync utf8 [SYS_open+read]    -> hi from node lib
fs.readdirSync       [SYS_getdents64]   -> ["a.txt","b.txt","x"]
fs.renameSync        [SYS_rename]       -> ["b.txt","c.txt","x"]
fs.appendFileSync                       -> hi from node lib!
binary round-trip 256B                  -> 256 bytes identical across the SAB
64KB file (multi-read path)             -> 65536 bytes
ENOENT / EEXIST / EISDIR                -> correct errno mapping
reads files the "shell" seeded          -> /etc = ["gitconfig","hosts","passwd"]
72 syscalls issued
```

That last one matters: the node process reads files another walios process wrote. One
filesystem, not a private heap.

## A real bug this caught

`fs.appendFileSync('/x','!')` returned `!` instead of `<old>!`. `writeFileUtf8` was
force-ORing `O_TRUNC`, truncating on every append — `stringToFlags()` already sets the
right flags per mode. Present in Phase 0 too; only surfaced once real open flags were
involved. Fixed in `bindings.js`.

## VERIFIED in a real browser

`test-browser.mjs` starts the COOP/COEP server, drives headless Chromium via
Playwright, and asserts on what ash prints. No human in the loop:

```bash
node walios-node-poc/apply-kernel-patch.mjs   # /walios/ is gitignored; see below
node walios-node-poc/mkstub.mjs
node walios-node-poc/build.mjs ./walios-node-poc/lib
node walios-node-poc/test-browser.mjs         # --headed to watch
```

busybox ash execs `node`, which runs as an ordinary walios process:

```
--- node -v ---                        v22.23.2
--- node -e ---                        hello from node v22.23.2 on walios
--- node writes, busybox reads ---     written by node
--- node reads what the shell made --- hello-from-ash
--- node script.js with args ---       script says: one,two
--- redirect to a file ---             redir-456
--- exit codes ---                     ok / && worked / exit code was 3
```

One filesystem: node reads files ash created and ash reads files node wrote.

### The in-app browser cannot run walios at all

Nested workers created from a URL-based worker fail there -- including the kernel's
own `wali-proc-worker.js` and a one-line trivial worker. Blob-to-blob nesting works.
Real Chromium is fine. That is why `test-browser.mjs` exists.

## The pipe bug: a zero-length write meant EOF

`node -e '...' | grep x` produced nothing. Fixed, and the root cause was not in node.

A **zero-length** write to a pipe pushed an *empty chunk* into the fifo and woke the
reader. The reader read 0 bytes and took that for EOF, exited, `readers` went to 0,
and the writer's next real write came back EPIPE + SIGPIPE (exit 141). POSIX is
explicit that `write(fd, buf, 0)` on a pipe transfers nothing and has no effect.

The kernel log that showed it:

```
[FIFO] blockread pipe#1 pid=103 chunks=0 w=1      grep waits, one writer alive
[FIFO] blockread EXIT  pipe#1 pid=103 chunks=1 w=1  woken: a chunk arrived
[FIFO] read      pipe#1 pid=103 got=0 w=1 r=1     the chunk is EMPTY -> EOF -> grep exits
[FIFO] EPIPE     pipe#1 pid=101 w=1 r=0           node's next write, no readers left
```

Fixed in two places:

- **the kernel** (`wali-worker.js`, both the pipe and socketpair write paths): a
  0-length write returns 0 without pushing a chunk or waking the reader. This is a
  latent walios bug that any guest could hit, not a walios-node one.
- **`kernel-vfs.js`**: never issue a 0-length write at all. Regression-tested in
  `test-kernel-vfs.mjs`.

The zero-length writes were my own diagnostic probes, which is a lesson worth
recording: **the probe caused the failure it was measuring.** It looked like a race
for a long time because the early probe succeeded and killed the reader, so the next
write failed -- consistent with "the pipe dies after ~200ms" and entirely misleading.

What finally separated it was a control matrix: a builtin writer (`echo`) worked, a
fast exec'd writer (`cat`) worked, a *slow* exec'd writer (`sh -c 'sleep 1; echo'`)
also worked -- which ruled out latency and the exec path, leaving only something our
process did. Kernel-side refcount logging then named it in one run.

## Previously NOT verified: the browser

**The browser run did not happen.** The kernel boots, resolves `node`, and starts pid
100 with the node worker — then the worker fails to load. Diagnosed: *nested workers
created from a URL-based worker fail in this environment*, including the kernel's own
`wali-proc-worker.js` and a one-line trivial worker. Blob→blob nesting works. So walios
cannot run here at all; it is an environment limitation, not a code failure — but it
means **the real kernel round trip is still unproven**.

To finish it, on a normal Chrome:

```bash
node walios-node-poc/mkstub.mjs
node walios-node-poc/build.mjs ./walios-node-poc/lib
node walios-node-poc/serve.mjs          # COOP/COEP, port 8788
# open http://localhost:8788/walios-node-poc/
```

The mock kernel's layouts were read out of `wali-worker.js` (`putStat`, the
`getdents64` case, the control block), so the wire format should match — but "should"
is exactly what the browser run is for.

---

# Rung one — `node` as a shell command

Turning `ash: node: not found` into a working command. `node-main.js` is the entry
point, shared by the browser worker and `test-node-cli.mjs`.

**argv** comes from the kernel over WALI's three imports (`__cl_get_argc`,
`__cl_get_argv_len`, `__cl_copy_argv`) — not a pointer array.

**stdout/stderr are node's own streams.** `guessHandleType(fd)` returns `'FILE'`, so
node builds `internal/fs/sync_write_stream`, which writes through `fs.writeSync` -> our
fs binding -> `SYS_write`. And `console` is node's real `Console`, so `%s/%d`,
`util.inspect` formatting and `console.table` all come for free.

## Works (23/23, `node test-node-cli.mjs ./lib`)

```
node -e "console.log(2+2)"            -> 4
node -e 'console.log("%s:%d","x",7)'  -> x:7
node -e "console.log({a:[1,2]})"      -> { a: [ 1, 2 ] }
node -p "1+1"                         -> 2
node -v                               -> v22.23.2
node -e "console.error('boom')"       -> boom  (on fd 2, not fd 1)
node -e "throw new Error('nope')"     -> stack on stderr, exit 1
node script.js one two                -> process.argv.slice(2) == ["one","two"]
node /app/main.js                     -> require("./dep.js") resolves
node -e fs.writeFileSync/readFileSync -> real SYS_open/write/read
node missing.js                       -> "cannot find module", exit 1
node --bogus                          -> exit 9
```

Exit codes propagate, so `node build.js && echo ok` and `$?` work.

## Not done

`node` with no args prints a message and exits 1. The REPL needs `vm`/contextify, and
there are no real realms in a worker. stdin is not wired, so `echo x | node` and
`node < file` do not work yet.

## Another realm leak, same shape as before

Every `console.log` test passed *and* printed nothing — the output was going to the
**host** terminal. `compileFunctionForCJSLoader` shadows realm globals by name, and
`console` was not in the list, so user code resolved the host's. Exactly the bug that
made `process.platform` report `win32` in Phase 0.

Worth stating as a rule: **a missing realm global does not fail, it silently binds to
the host's.** In the real worker the realm is ours so this is free, but every global
has to be enumerated deliberately.

## Known gaps (Phase 2+)

- **The real bootstrap.** `boot.js` hand-rolls `process` and calls one initialiser
  (`debuglog.initializeDebugEnv`). Node's `internal/process/pre_execution.js` should run
  instead — the hand-rolled process is the shakiest part of this spike.
- **Async fs.** `FSReqCallback` is a shape, not a completion. Needs the kernel's async path.
- **No net/http/child_process.** Needs `tcp_wrap`/`pipe_wrap`/`process_wrap` over wisp
  and the walios process model.
- **ESM.** Untested here. `module_wrap` remains the biggest fidelity risk in the design.
- **`vm`/`contextify`** is a stub — no real realms in a worker.
