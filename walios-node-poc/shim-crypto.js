'use strict';
// A `crypto` module for walios-node.
//
// Node's lib/crypto.js is an OpenSSL front-end: KeyObjects, ciphers, webcrypto, the
// lot. Porting OpenSSL is not on the table, and npm does not need it -- what npm
// needs is a hash, because it verifies a sha512 (or sha1) integrity digest on every
// tarball it downloads. So this replaces the module rather than the binding.
//
// SubtleCrypto is not usable here: createHash().digest() is synchronous and
// subtle.digest() is a promise. These are plain implementations of the FIPS 180-4
// algorithms instead.

// ---- sha256 -----------------------------------------------------------------
const K256 = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function sha256(bytes) {
  const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  const msg = pad(bytes, 64, 8, false);
  const w = new Uint32Array(64);
  const dv = new DataView(msg.buffer, msg.byteOffset, msg.byteLength);
  const rr = (x, n) => (x >>> n) | (x << (32 - n));
  for (let off = 0; off < msg.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
    for (let i = 16; i < 64; i++) {
      const s0 = rr(w[i - 15], 7) ^ rr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rr(w[i - 2], 17) ^ rr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const S1 = rr(e, 6) ^ rr(e, 11) ^ rr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K256[i] + w[i]) >>> 0;
      const S0 = rr(a, 2) ^ rr(a, 13) ^ rr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
  }
  const out = new Uint8Array(32);
  new DataView(out.buffer).setUint32(0, H[0]);
  for (let i = 0; i < 8; i++) new DataView(out.buffer).setUint32(i * 4, H[i]);
  return out;
}

// ---- sha512 -----------------------------------------------------------------
// BigInt rather than hi/lo pairs: npm hashes a few MB per install, so clarity beats
// the constant factor, and getting 64-bit rotations right in 32-bit halves is where
// hand-rolled sha512 usually goes wrong.
const K512 = [
  '428a2f98d728ae22', '7137449123ef65cd', 'b5c0fbcfec4d3b2f', 'e9b5dba58189dbbc', '3956c25bf348b538',
  '59f111f1b605d019', '923f82a4af194f9b', 'ab1c5ed5da6d8118', 'd807aa98a3030242', '12835b0145706fbe',
  '243185be4ee4b28c', '550c7dc3d5ffb4e2', '72be5d74f27b896f', '80deb1fe3b1696b1', '9bdc06a725c71235',
  'c19bf174cf692694', 'e49b69c19ef14ad2', 'efbe4786384f25e3', '0fc19dc68b8cd5b5', '240ca1cc77ac9c65',
  '2de92c6f592b0275', '4a7484aa6ea6e483', '5cb0a9dcbd41fbd4', '76f988da831153b5', '983e5152ee66dfab',
  'a831c66d2db43210', 'b00327c898fb213f', 'bf597fc7beef0ee4', 'c6e00bf33da88fc2', 'd5a79147930aa725',
  '06ca6351e003826f', '142929670a0e6e70', '27b70a8546d22ffc', '2e1b21385c26c926', '4d2c6dfc5ac42aed',
  '53380d139d95b3df', '650a73548baf63de', '766a0abb3c77b2a8', '81c2c92e47edaee6', '92722c851482353b',
  'a2bfe8a14cf10364', 'a81a664bbc423001', 'c24b8b70d0f89791', 'c76c51a30654be30', 'd192e819d6ef5218',
  'd69906245565a910', 'f40e35855771202a', '106aa07032bbd1b8', '19a4c116b8d2d0c8', '1e376c085141ab53',
  '2748774cdf8eeb99', '34b0bcb5e19b48a8', '391c0cb3c5c95a63', '4ed8aa4ae3418acb', '5b9cca4f7763e373',
  '682e6ff3d6b2b8a3', '748f82ee5defb2fc', '78a5636f43172f60', '84c87814a1f0ab72', '8cc702081a6439ec',
  '90befffa23631e28', 'a4506cebde82bde9', 'bef9a3f7b2c67915', 'c67178f2e372532b', 'ca273eceea26619c',
  'd186b8c721c0c207', 'eada7dd6cde0eb1e', 'f57d4f7fee6ed178', '06f067aa72176fba', '0a637dc5a2c898a6',
  '113f9804bef90dae', '1b710b35131c471b', '28db77f523047d84', '32caab7b40c72493', '3c9ebe0a15c9bebc',
  '431d67c49c100d4c', '4cc5d4becb3e42b6', '597f299cfc657e2a', '5fcb6fab3ad6faec', '6c44198c4a475817',
].map((h) => BigInt('0x' + h));

const M64 = (1n << 64n) - 1n;
const rotr = (x, n) => ((x >> n) | (x << (64n - n))) & M64;

function sha512(bytes) {
  let H = ['6a09e667f3bcc908', 'bb67ae8584caa73b', '3c6ef372fe94f82b', 'a54ff53a5f1d36f1',
    '510e527fade682d1', '9b05688c2b3e6c1f', '1f83d9abfb41bd6b', '5be0cd19137e2179'].map((h) => BigInt('0x' + h));
  const msg = pad(bytes, 128, 16, true);
  const dv = new DataView(msg.buffer, msg.byteOffset, msg.byteLength);
  const w = new Array(80);
  for (let off = 0; off < msg.length; off += 128) {
    for (let i = 0; i < 16; i++) w[i] = dv.getBigUint64(off + i * 8);
    for (let i = 16; i < 80; i++) {
      const s0 = rotr(w[i - 15], 1n) ^ rotr(w[i - 15], 8n) ^ (w[i - 15] >> 7n);
      const s1 = rotr(w[i - 2], 19n) ^ rotr(w[i - 2], 61n) ^ (w[i - 2] >> 6n);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & M64;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 80; i++) {
      const S1 = rotr(e, 14n) ^ rotr(e, 18n) ^ rotr(e, 41n);
      const ch = (e & f) ^ (~e & M64 & g);
      const t1 = (h + S1 + ch + K512[i] + w[i]) & M64;
      const S0 = rotr(a, 28n) ^ rotr(a, 34n) ^ rotr(a, 39n);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) & M64;
      h = g; g = f; f = e; e = (d + t1) & M64;
      d = c; c = b; b = a; a = (t1 + t2) & M64;
    }
    const add = [a, b, c, d, e, f, g, h];
    H = H.map((v, i) => (v + add[i]) & M64);
  }
  const out = new Uint8Array(64);
  const odv = new DataView(out.buffer);
  H.forEach((v, i) => odv.setBigUint64(i * 8, v));
  return out;
}

// ---- sha1 (npm's older integrity field) -------------------------------------
function sha1(bytes) {
  const H = new Uint32Array([0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0]);
  const msg = pad(bytes, 64, 8, false);
  const dv = new DataView(msg.buffer, msg.byteOffset, msg.byteLength);
  const rl = (x, n) => (x << n) | (x >>> (32 - n));
  const w = new Uint32Array(80);
  for (let off = 0; off < msg.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
    for (let i = 16; i < 80; i++) w[i] = rl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    let [a, b, c, d, e] = H;
    for (let i = 0; i < 80; i++) {
      let f, k;
      if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
      else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const t = (rl(a, 5) + f + e + k + w[i]) >>> 0;
      e = d; d = c; c = rl(b, 30) >>> 0; b = a; a = t;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0;
    H[3] = (H[3] + d) >>> 0; H[4] = (H[4] + e) >>> 0;
  }
  const out = new Uint8Array(20);
  const odv = new DataView(out.buffer);
  for (let i = 0; i < 5; i++) odv.setUint32(i * 4, H[i]);
  return out;
}

// Merkle-Damgard padding: 0x80, zeroes, then the bit length big-endian.
function pad(bytes, block, lenBytes, big) {
  const len = bytes.length;
  const total = Math.ceil((len + 1 + lenBytes) / block) * block;
  const out = new Uint8Array(total);
  out.set(bytes);
  out[len] = 0x80;
  const dv = new DataView(out.buffer);
  if (big) dv.setBigUint64(total - 8, BigInt(len) * 8n);
  else dv.setUint32(total - 4, (len * 8) >>> 0);
  if (!big && len * 8 > 0xffffffff) dv.setUint32(total - 8, Math.floor((len * 8) / 0x100000000));
  return out;
}

const ALGOS = { sha1, sha256, sha512, 'sha-1': sha1, 'sha-256': sha256, 'sha-512': sha512 };

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function toBase64(u8) {
  let out = '';
  for (let i = 0; i < u8.length; i += 3) {
    const a = u8[i], b = u8[i + 1], c = u8[i + 2];
    out += B64[a >> 2] + B64[((a & 3) << 4) | ((b || 0) >> 4)];
    out += i + 1 < u8.length ? B64[((b & 15) << 2) | ((c || 0) >> 6)] : '=';
    out += i + 2 < u8.length ? B64[c & 63] : '=';
  }
  return out;
}
const toHex = (u8) => { let s = ''; for (const b of u8) s += b.toString(16).padStart(2, '0'); return s; };

class Hash {
  constructor(algo) {
    const name = String(algo).toLowerCase();
    this._fn = ALGOS[name];
    if (!this._fn) { const e = new Error('Digest method not supported: ' + algo); e.code = 'ERR_CRYPTO_INVALID_DIGEST'; throw e; }
    this._parts = [];
    this._len = 0;
  }
  update(data, enc) {
    const b = typeof data === 'string'
      ? new TextEncoder().encode(enc === 'hex' ? data : data)
      : new Uint8Array(data.buffer || data, data.byteOffset || 0, data.byteLength !== undefined ? data.byteLength : data.length);
    this._parts.push(b); this._len += b.length;
    return this;
  }
  digest(enc) {
    const all = new Uint8Array(this._len);
    let off = 0;
    for (const p of this._parts) { all.set(p, off); off += p.length; }
    const d = this._fn(all);
    if (enc === 'hex') return toHex(d);
    if (enc === 'base64') return toBase64(d);
    return d;
  }
}

module.exports = {
  createHash: (algo) => new Hash(algo),
  getHashes: () => ['sha1', 'sha256', 'sha512'],
  randomBytes: (n, cb) => {
    const b = new Uint8Array(n);
    crypto.getRandomValues(b);
    if (cb) { cb(null, b); return undefined; }
    return b;
  },
  randomUUID: () => crypto.randomUUID(),
  timingSafeEqual: (a, b) => {
    if (a.length !== b.length) return false;
    let d = 0;
    for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
    return d === 0;
  },
  webcrypto: typeof crypto !== 'undefined' ? crypto : undefined,
  constants: {},
  // Deliberately absent: ciphers, KeyObjects, sign/verify, DH. Those are OpenSSL,
  // and nothing in the install path touches them.
};
