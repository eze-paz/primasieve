// opfs-io-worker.js — sync-over-async OPFS byte reads for pyodide-worker's lazy
// /files mount. The Pyodide worker cannot await inside Emscripten's synchronous
// FS.lookupNode fault-in, and OPFS handle acquisition is async even in workers,
// so it blocks on Atomics.wait while THIS worker does the async read and feeds
// the bytes back through a SharedArrayBuffer (chunked for files larger than the
// data buffer).
//
// IMPORTANT: while the requester is blocked in Atomics.wait, its event loop is
// frozen — and a nested worker's postMessage/startup can be starved by a frozen
// parent. So after the one-time init handshake ('io-ready', which the parent
// AWAITS before Python ever runs), the entire request/response protocol lives
// in the SABs: requests are signaled with Atomics.notify and observed here via
// Atomics.waitAsync — no per-read postMessage at all.
//
// ctrl (Int32Array, 16 slots):
//   [0] response state: 0 consumer owns, 1 chunk ready, 2 FINAL chunk ready, -1 error
//   [1] byte length of the chunk currently in data
//   [2] total file size (set on every chunk; lets the consumer preallocate)
//   [3] request signal: 0 idle, 1 request pending (path bytes are in data)
//   [4] request path byte length
// One request in flight at a time by construction: the requester is
// single-threaded and blocked for the whole exchange.

let ctrl = null;   // Int32Array over the control SAB
let data = null;   // Uint8Array over the data SAB

function iolog(text) { try { self.postMessage({ type: 'io-log', text }); } catch (_) {} }

async function readBytes(rel) {
  let dir = await navigator.storage.getDirectory();
  const parts = String(rel).split('/').filter(Boolean);
  const name = parts.pop();
  for (const p of parts) dir = await dir.getDirectoryHandle(p);
  const file = await (await dir.getFileHandle(name)).getFile();
  return new Uint8Array(await file.arrayBuffer());
}

function feed(bytes) {
  // The consumer set ctrl[0]=0 before signaling the request; after each
  // non-final chunk it copies the bytes, resets ctrl[0]=0 and notifies.
  // Sync Atomics.wait between chunks is fine here — this is a dedicated worker
  // and the whole file is already in memory.
  let off = 0;
  do {
    const len = Math.min(bytes.length - off, data.length);
    data.set(bytes.subarray(off, off + len));
    off += len;
    Atomics.store(ctrl, 1, len);
    Atomics.store(ctrl, 2, bytes.length);
    const final = off >= bytes.length;
    Atomics.store(ctrl, 0, final ? 2 : 1);
    Atomics.notify(ctrl, 0);
    if (final) break;
    Atomics.wait(ctrl, 0, 1, 30000);          // until the consumer resets to 0
  } while (Atomics.load(ctrl, 0) === 0);
}

async function serveLoop() {
  for (;;) {
    if (Atomics.load(ctrl, 3) !== 1) {
      const w = Atomics.waitAsync(ctrl, 3, 0);
      if (w.async) await w.value;
      continue;                                // re-check the signal on every wake
    }
    Atomics.store(ctrl, 3, 0);
    let rel = '';
    try { rel = new TextDecoder().decode(data.slice(0, Atomics.load(ctrl, 4))); } catch (_) {}
    try {
      feed(await readBytes(rel));
    } catch (e) {
      iolog('read failed: ' + rel + ' — ' + (e && e.message || e));
      Atomics.store(ctrl, 0, -1);
      Atomics.notify(ctrl, 0);
    }
  }
}

self.addEventListener('message', (event) => {
  const msg = event.data;
  if (!msg) return;
  if (msg.type === 'init') {
    ctrl = new Int32Array(msg.ctrl);
    data = new Uint8Array(msg.data);
    serveLoop();
    self.postMessage({ type: 'io-ready' });
    return;
  }
});
