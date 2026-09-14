'use strict';
// internalBinding('buffer') -- pure JS. In real Node this is C++; nothing here needs to be.
// *Slice and base64/hex/ucs2 Write are installed as prototype methods (this = buffer);
// the *WriteStatic variants take the buffer explicitly. See lib/internal/buffer.js:1030.

const td = new TextDecoder('utf-8');
const te = new TextEncoder();
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function b64encode(u8) {
  let out = '';
  for (let i = 0; i < u8.length; i += 3) {
    const a = u8[i], b = u8[i + 1], c = u8[i + 2];
    out += B64[a >> 2];
    out += B64[((a & 3) << 4) | ((b || 0) >> 4)];
    out += i + 1 < u8.length ? B64[((b & 15) << 2) | ((c || 0) >> 6)] : '=';
    out += i + 2 < u8.length ? B64[c & 63] : '=';
  }
  return out;
}
function b64decode(str) {
  str = String(str).replace(/[^A-Za-z0-9+/_-]/g, '').replace(/-/g, '+').replace(/_/g, '/');
  const out = new Uint8Array((str.length * 3) >> 2);
  let n = 0, buf = 0, bits = 0;
  for (const ch of str) {
    const v = B64.indexOf(ch);
    if (v < 0) continue;
    buf = (buf << 6) | v; bits += 6;
    if (bits >= 8) { bits -= 8; out[n++] = (buf >> bits) & 0xff; }
  }
  return out.subarray(0, n);
}
const latin1 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]); return s; };
const ascii = (u8) => { let s = ''; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i] & 0x7f); return s; };
const hex = (u8) => { let s = ''; for (let i = 0; i < u8.length; i++) s += u8[i].toString(16).padStart(2, '0'); return s; };
const ucs2 = (u8) => { let s = ''; for (let i = 0; i + 1 < u8.length; i += 2) s += String.fromCharCode(u8[i] | (u8[i + 1] << 8)); return s; };

// range-clamped view of `this`
const view = (buf, start, end) => {
  const len = buf.length;
  let s = start === undefined ? 0 : start | 0, e = end === undefined ? len : end | 0;
  if (s < 0) s = 0; if (e > len) e = len; if (e < s) e = s;
  return buf.subarray(s, e);
};
const writeBytes = (buf, bytes, offset, length) => {
  const off = offset === undefined ? 0 : offset | 0;
  const max = Math.min(length === undefined ? buf.length - off : length | 0, buf.length - off);
  const n = Math.min(bytes.length, Math.max(0, max));
  buf.set(bytes.subarray(0, n), off);
  return n;
};

function makeBufferBinding() {
  return {
    kMaxLength: 2 ** 32 - 1,
    kStringMaxLength: 2 ** 29 - 24,

    byteLengthUtf8: (s) => te.encode(s).length,

    // --- slices: called as prototype methods, `this` is the buffer -----------
    utf8Slice(start, end) { return td.decode(view(this, start, end)); },
    latin1Slice(start, end) { return latin1(view(this, start, end)); },
    asciiSlice(start, end) { return ascii(view(this, start, end)); },
    hexSlice(start, end) { return hex(view(this, start, end)); },
    base64Slice(start, end) { return b64encode(view(this, start, end)); },
    base64urlSlice(start, end) { return b64encode(view(this, start, end)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); },
    ucs2Slice(start, end) { return ucs2(view(this, start, end)); },

    // --- writes: prototype methods -------------------------------------------
    base64Write(string, offset, length) { return writeBytes(this, b64decode(string), offset, length); },
    base64urlWrite(string, offset, length) { return writeBytes(this, b64decode(string), offset, length); },
    hexWrite(string, offset, length) {
      const s = String(string); const n = s.length >> 1;
      const b = new Uint8Array(n);
      for (let i = 0; i < n; i++) { const v = parseInt(s.substr(i * 2, 2), 16); if (Number.isNaN(v)) { return writeBytes(this, b.subarray(0, i), offset, length); } b[i] = v; }
      return writeBytes(this, b, offset, length);
    },
    ucs2Write(string, offset, length) {
      const s = String(string); const b = new Uint8Array(s.length * 2);
      for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); b[i * 2] = c & 0xff; b[i * 2 + 1] = c >> 8; }
      return writeBytes(this, b, offset, length);
    },

    // --- writes: static form, buffer passed explicitly ------------------------
    utf8WriteStatic: (buf, string, offset, length) => writeBytes(buf, te.encode(String(string)), offset, length),
    latin1WriteStatic: (buf, string, offset, length) => {
      const s = String(string); const b = new Uint8Array(s.length);
      for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i) & 0xff;
      return writeBytes(buf, b, offset, length);
    },
    asciiWriteStatic: (buf, string, offset, length) => {
      const s = String(string); const b = new Uint8Array(s.length);
      for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i) & 0x7f;
      return writeBytes(buf, b, offset, length);
    },

    // --- bulk ops -------------------------------------------------------------
    copy: (src, tgt, tStart = 0, sStart = 0, sEnd = src.length) => {
      const chunk = src.subarray(sStart, sEnd);
      const n = Math.min(chunk.length, tgt.length - tStart);
      tgt.set(chunk.subarray(0, n), tStart);
      return n;
    },
    copyArrayBuffer: (dst, dstOff, src, srcOff, len) => {
      new Uint8Array(dst).set(new Uint8Array(src, srcOff, len), dstOff);
    },
    createUnsafeArrayBuffer: (size) => new ArrayBuffer(size),
    compare: (a, b) => {
      const n = Math.min(a.length, b.length);
      for (let i = 0; i < n; i++) { if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; }
      return a.length === b.length ? 0 : a.length < b.length ? -1 : 1;
    },
    compareOffset: (a, b, tStart = 0, sStart = 0, tEnd = b.length, sEnd = a.length) => {
      const x = a.subarray(sStart, sEnd), y = b.subarray(tStart, tEnd);
      const n = Math.min(x.length, y.length);
      for (let i = 0; i < n; i++) { if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1; }
      return x.length === y.length ? 0 : x.length < y.length ? -1 : 1;
    },
    fill: (buf, value, offset = 0, end = buf.length, encoding) => {
      let bytes;
      if (typeof value === 'number') { buf.fill(value & 0xff, offset, end); return buf; }
      if (typeof value === 'string') bytes = te.encode(value);
      else bytes = value;
      if (!bytes.length) { buf.fill(0, offset, end); return buf; }
      for (let i = offset; i < end; i++) buf[i] = bytes[(i - offset) % bytes.length];
      return buf;
    },
    indexOfNumber: (buf, val, byteOffset, dir) => {
      const v = val & 0xff;
      if (dir === false) { for (let i = Math.min(byteOffset, buf.length - 1); i >= 0; i--) if (buf[i] === v) return i; return -1; }
      for (let i = Math.max(0, byteOffset); i < buf.length; i++) if (buf[i] === v) return i;
      return -1;
    },
    indexOfBuffer: (buf, val, byteOffset, encodingVal, dir) => findBytes(buf, val, byteOffset, dir),
    indexOfString: (buf, val, byteOffset, encodingVal, dir) => findBytes(buf, te.encode(String(val)), byteOffset, dir),
    swap16: (buf) => { for (let i = 0; i < buf.length; i += 2) { const t = buf[i]; buf[i] = buf[i + 1]; buf[i + 1] = t; } return buf; },
    swap32: (buf) => { for (let i = 0; i < buf.length; i += 4) { buf.set([buf[i + 3], buf[i + 2], buf[i + 1], buf[i]], i); } return buf; },
    swap64: (buf) => { for (let i = 0; i < buf.length; i += 8) { const s = buf.subarray(i, i + 8).slice().reverse(); buf.set(s, i); } return buf; },
    isAscii: (buf) => { for (let i = 0; i < buf.length; i++) if (buf[i] > 0x7f) return false; return true; },
    isUtf8: (buf) => { try { new TextDecoder('utf-8', { fatal: true }).decode(buf); return true; } catch { return false; } },
    atob: (s) => latin1(b64decode(s)),
    btoa: (s) => { const b = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i) & 0xff; return b64encode(b); },
    // encodings map used by lib/buffer.js for indexOf dispatch
    encodings: ['ascii', 'utf8', 'base64', 'ucs2', 'binary', 'hex', 'utf16le', 'base64url'],
    constants: { MAX_LENGTH: 2 ** 32 - 1, MAX_STRING_LENGTH: 2 ** 29 - 24 },
    setBufferPrototype: () => {},
    zeroFill: new Uint32Array(1),
    detachArrayBuffer: () => {},
    getZeroFillToggle: () => new Uint32Array(1),
  };
}

function findBytes(buf, needle, byteOffset, dir) {
  if (!needle.length) return byteOffset <= buf.length ? byteOffset : buf.length;
  const last = buf.length - needle.length;
  if (dir === false) {
    for (let i = Math.min(byteOffset, last); i >= 0; i--) { let k = 0; while (k < needle.length && buf[i + k] === needle[k]) k++; if (k === needle.length) return i; }
    return -1;
  }
  for (let i = Math.max(0, byteOffset); i <= last; i++) { let k = 0; while (k < needle.length && buf[i + k] === needle[k]) k++; if (k === needle.length) return i; }
  return -1;
}

module.exports = { makeBufferBinding };
