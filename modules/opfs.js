// sandpie OPFS core — filesystem primitives and path utilities
function splitPath(path) {
  const parts = String(path).split('/').filter(Boolean);
  const name = parts.pop();
  return { parts, name };
}
const opfs = {
  async root() { return await navigator.storage.getDirectory(); },

  async resolveDir(parts, { create = false } = {}) {
    let dir = await this.root();
    for (const p of parts) dir = await dir.getDirectoryHandle(p, { create });
    return dir;
  },
  async read(path) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts);
    const handle = await dir.getFileHandle(name);
    return await (await handle.getFile()).text();
  },

  async readBytes(path) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts);
    const handle = await dir.getFileHandle(name);
    const file = await handle.getFile();
    return new Uint8Array(await file.arrayBuffer());
  },
  async write(path, content) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts, { create: true });
    const handle = await dir.getFileHandle(name, { create: true });
    const w = await handle.createWritable();
    await w.write(content);
    await w.close();
  },
  async remove(path) {
    const { parts, name } = splitPath(path);
    const dir = await this.resolveDir(parts);
    await dir.removeEntry(name, { recursive: true });

    try {
      const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (sw) sw.postMessage({ type: 'opfs-removed', paths: [path] });
    } catch (_) {}
  },

  async exists(path) {
    try {
      const { parts, name } = splitPath(path);
      const dir = await this.resolveDir(parts);
      await dir.getFileHandle(name);
      return true;
    } catch { return false; }
  },
  async mkdir(path) {
    const parts = String(path).split('/').filter(Boolean);
    await this.resolveDir(parts, { create: true });
  },

  async listDir(path = '') {
    const parts = String(path).split('/').filter(Boolean);
    const dir = await this.resolveDir(parts);
    const out = [];
    for await (const [n, h] of dir.entries()) out.push({ name: n, kind: h.kind });
    return out.sort((a, b) => a.kind !== b.kind ? (a.kind === 'directory' ? -1 : 1) : a.name.localeCompare(b.name));
  },

  async list(prefix = '') {
    const out = [];
    const walk = async (dir, p) => {
      for await (const [n, h] of dir.entries()) {
        const full = p ? `${p}/${n}` : n;
        if (h.kind === 'file') out.push(full);
        else await walk(h, full);
      }
    };
    const startParts = String(prefix).split('/').filter(Boolean);
    const start = await this.resolveDir(startParts);
    await walk(start, prefix.replace(/^\/+|\/+$/g, ''));
    return out.sort();
  },

  async listAll(prefix = '') {
    const out = [];
    const walk = async (dir, p) => {
      for await (const [n, h] of dir.entries()) {
        const full = p ? `${p}/${n}` : n;
        out.push({ path: full, kind: h.kind });
        if (h.kind === 'directory') await walk(h, full);
      }
    };
    const startParts = String(prefix).split('/').filter(Boolean);
    const start = await this.resolveDir(startParts);
    await walk(start, prefix.replace(/^\/+|\/+$/g, ''));
    return out;
  },
};
function joinPath(folder, name) {
  if (folder === '/' || folder === '') return '/' + name;
  return folder.replace(/\/$/, '') + '/' + name;
}

window.opfs = opfs;
window.splitPath = splitPath;
window.joinPath = joinPath;
