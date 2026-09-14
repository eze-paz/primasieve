'use strict';
// `zlib` for walios-node, over the platform's DecompressionStream.
//
// npm's install path needs exactly one thing from zlib: ungzip a .tgz. Both the
// worker and node have DecompressionStream, which is a real, fast, correct inflate --
// far better than a hand-rolled one, and the whole reason not to write 200 lines of
// Huffman decoding that would be wrong in some edge case.
//
// The catch is that it is ASYNC. gunzipSync therefore cannot be implemented on it and
// throws a directive rather than a wrong answer; everything in the install path uses
// the callback or promise form anyway.

let PENDING = null;

async function decompress(bytes, format) {
  if (PENDING) PENDING.n++;
  try { return await doDecompress(bytes, format); }
  finally { if (PENDING) PENDING.n--; }
}

async function doDecompress(bytes, format) {
  const src = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const ds = new DecompressionStream(format);
  const stream = new Blob([src]).stream().pipeThrough(ds);
  const out = new Uint8Array(await new Response(stream).arrayBuffer());
  return out;
}

const mk = (format) => {
  const asyncFn = (buf, opts, cb) => {
    if (typeof opts === 'function') { cb = opts; opts = {}; }
    const p = decompress(buf, format);
    if (!cb) return p;
    p.then((r) => cb(null, r), (e) => cb(e));
    return undefined;
  };
  return asyncFn;
};

const notSync = (name, alt) => () => {
  const e = new Error(
    name + ' is not available in walios-node: it is built on DecompressionStream, '
    + 'which is asynchronous. Use ' + alt + ' instead.');
  e.code = 'ERR_METHOD_NOT_IMPLEMENTED';
  throw e;
};

const api = {
  gunzip: mk('gzip'),
  inflate: mk('deflate'),
  inflateRaw: mk('deflate-raw'),
  brotliDecompress: (buf, o, cb) => mk('deflate')(buf, o, cb),   // best effort

  // Promise forms, which is what our own code uses.
  promises: {
    gunzip: (b) => decompress(b, 'gzip'),
    inflate: (b) => decompress(b, 'deflate'),
    inflateRaw: (b) => decompress(b, 'deflate-raw'),
  },

  gunzipSync: notSync('zlib.gunzipSync', 'zlib.promises.gunzip or the callback form'),
  inflateSync: notSync('zlib.inflateSync', 'zlib.promises.inflate'),
  gzipSync: notSync('zlib.gzipSync', 'CompressionStream directly'),
  deflateSync: notSync('zlib.deflateSync', 'CompressionStream directly'),

  constants: { Z_OK: 0, Z_STREAM_END: 1, Z_NO_FLUSH: 0, Z_FINISH: 4 },
};

// install(pending) so decompression keeps the process alive, like a request does.
api.install = (pending) => { PENDING = pending; return api; };

module.exports = api;
