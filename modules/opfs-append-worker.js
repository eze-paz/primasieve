// sandpie OPFS append worker — true O(1) in-place appends.
//
// The main-thread opfs.append uses createWritable({keepExistingData:true}). That is
// O(new bytes) at the API level, but several Chromium versions implement the writable
// stream as a swap file that is COPIED over the original on close() — so appending one
// message to a long conversation can cost O(whole file) on disk. FileSystemSyncAccessHandle
// writes in place with no swap file (true O(1) append), but is only available inside a
// Worker. This worker owns those handles: the main thread posts {seq, path, data} and we
// write `data` (UTF-8) at the current end-of-file, then reply {seq, ok} / {seq, error}.
//
// A SyncAccessHandle takes an EXCLUSIVE lock on its file, so two concurrent handles on the
// same path throw. Appends to a given path are therefore serialized through a per-path
// promise chain; different paths still run without contention.

const encoder = new TextEncoder();

// path -> promise tail, so appends to the same file never hold two handles at once.
const chains = new Map();

async function resolveDir(parts) {
  let dir = await navigator.storage.getDirectory();
  for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: true });
  return dir;
}

async function appendOnce(path, data) {
  const parts = String(path).split('/').filter(Boolean);
  const name = parts.pop();
  const dir = await resolveDir(parts);
  const handle = await dir.getFileHandle(name, { create: true });
  const access = await handle.createSyncAccessHandle();
  try {
    const bytes = encoder.encode(data);
    const at = access.getSize();
    // write() may accept fewer bytes than offered; loop until the buffer is drained.
    let written = 0;
    while (written < bytes.length) {
      const n = access.write(bytes.subarray(written), { at: at + written });
      if (!n) throw new Error('SyncAccessHandle.write wrote 0 bytes');
      written += n;
    }
    access.flush();
  } finally {
    access.close();
  }
}

// Serialize per path: chain each append after the previous one for the same file.
function enqueue(path, data) {
  const prev = chains.get(path) || Promise.resolve();
  const next = prev.catch(() => {}).then(() => appendOnce(path, data));
  // Clear the chain slot once this is the tail and it has settled, so the Map does not
  // grow unbounded across the session.
  const cleanup = next.catch(() => {}).finally(() => { if (chains.get(path) === cleanup) chains.delete(path); });
  chains.set(path, cleanup);
  return next;
}

self.onmessage = async (e) => {
  const { seq, path, data } = e.data || {};
  try {
    await enqueue(path, data);
    self.postMessage({ seq, ok: true });
  } catch (err) {
    self.postMessage({ seq, ok: false, error: (err && err.message) || String(err) });
  }
};
