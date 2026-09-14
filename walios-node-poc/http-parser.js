'use strict';
// internalBinding('http_parser') -- HTTP/1.1 in JS, in place of llhttp.
//
// node's _http_client.js and _http_server.js drive the parser through a fixed
// callback protocol rather than returning anything, so this implements that protocol
// exactly: indices kOnMessageBegin..kOnExecute are slots on the parser object, and
// node installs functions there. execute(buffer) returns bytes consumed, or an Error.
//
// Covered: status/request line, headers (folded continuations included), Content-Length
// bodies, chunked transfer-encoding, and connection-close framing. Not covered:
// trailers beyond skipping them, and upgrade/CONNECT tunnelling.

const REQUEST = 1, RESPONSE = 2;

const METHODS = ['DELETE', 'GET', 'HEAD', 'POST', 'PUT', 'CONNECT', 'OPTIONS', 'TRACE',
  'COPY', 'LOCK', 'MKCOL', 'MOVE', 'PROPFIND', 'PROPPATCH', 'SEARCH', 'UNLOCK', 'BIND',
  'REBIND', 'UNBIND', 'ACL', 'REPORT', 'MKACTIVITY', 'CHECKOUT', 'MERGE', 'M-SEARCH',
  'NOTIFY', 'SUBSCRIBE', 'UNSUBSCRIBE', 'PATCH', 'PURGE', 'MKCALENDAR', 'LINK', 'UNLINK',
  'SOURCE', 'QUERY'];

const CR = 13, LF = 10;

function makeHttpParser(deps) {
  const Buffer = new Proxy({}, { get: (_t, k) => deps.getBuffer()[k] });

  class HTTPParser {
    constructor() { this._reset(RESPONSE); }

    _reset(type) {
      this.type = type || RESPONSE;
      this.state = 'LINE';
      this.buf = null;                 // bytes not yet consumed
      this.headers = [];
      this.statusCode = 0;
      this.statusMessage = '';
      this.method = 0;
      this.url = '';
      this.versionMajor = 1;
      this.versionMinor = 1;
      this.contentLength = null;
      this.chunked = false;
      this.bodyLeft = 0;
      this.shouldKeepAlive = true;
      this.upgrade = false;
      this._skipBody = false;
    }

    initialize(type, resource, maxHeaderSize, lenient, headersTimeout) {
      this._reset(type);
      return 0;
    }
    reinitialize(type) { this._reset(type); return 0; }
    free() { this.buf = null; return 0; }
    close() { this.buf = null; return 0; }
    remove() {}
    pause() {}
    resume() {}
    consume() {}
    unconsume() {}
    getCurrentBuffer() { return Buffer.alloc(0); }
    duration() { return 0; }
    headersCompleted() { return this.state !== 'LINE' && this.state !== 'HEADERS'; }

    // node calls this when it knows a response has no body (HEAD, 204, 304).
    // Without it the parser waits forever for bytes that never come.
    _setSkipBody(v) { this._skipBody = !!v; }

    finish() {
      if (this.state === 'BODY_EOF') { this._messageComplete(); }
      return undefined;
    }

    execute(chunk) {
      let b = chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk);
      if (this.buf && this.buf.length) {
        const merged = new Uint8Array(this.buf.length + b.length);
        merged.set(this.buf); merged.set(b, this.buf.length);
        b = merged;
      }
      this.buf = null;
      const consumed = b.length;
      let p = 0;
      try {
        for (;;) {
          if (this.state === 'LINE') {
            const e = findCRLF(b, p);
            if (e < 0) { this.buf = b.subarray(p); break; }
            const line = ascii(b, p, e);
            p = e + 2;
            if (!line) continue;                       // tolerate a leading blank line
            this._startLine(line);
            this.state = 'HEADERS';
            continue;
          }
          if (this.state === 'HEADERS') {
            const e = findCRLF(b, p);
            if (e < 0) { this.buf = b.subarray(p); break; }
            const line = ascii(b, p, e);
            p = e + 2;
            if (line === '') { const r = this._headersDone(); if (r === 'DONE') { this._messageComplete(); this.state = 'LINE'; continue; } continue; }
            const c = line.indexOf(':');
            if (c > 0) this.headers.push(line.slice(0, c).trim(), line.slice(c + 1).trim());
            else if (this.headers.length && /^[ \t]/.test(line)) this.headers[this.headers.length - 1] += ' ' + line.trim();
            continue;
          }
          if (this.state === 'BODY_LEN') {
            if (p >= b.length) break;
            const take = Math.min(this.bodyLeft, b.length - p);
            this._body(b, p, take);
            p += take; this.bodyLeft -= take;
            if (this.bodyLeft === 0) { this._messageComplete(); this.state = 'LINE'; }
            continue;
          }
          if (this.state === 'CHUNK_SIZE') {
            const e = findCRLF(b, p);
            if (e < 0) { this.buf = b.subarray(p); break; }
            const size = parseInt(ascii(b, p, e).split(';')[0].trim(), 16);
            p = e + 2;
            if (!Number.isFinite(size)) return new Error('bad chunk size');
            if (size === 0) { this.state = 'TRAILERS'; continue; }
            this.bodyLeft = size;
            this.state = 'CHUNK_DATA';
            continue;
          }
          if (this.state === 'CHUNK_DATA') {
            if (p >= b.length) break;
            const take = Math.min(this.bodyLeft, b.length - p);
            this._body(b, p, take);
            p += take; this.bodyLeft -= take;
            if (this.bodyLeft === 0) this.state = 'CHUNK_CRLF';
            continue;
          }
          if (this.state === 'CHUNK_CRLF') {
            if (b.length - p < 2) { this.buf = b.subarray(p); break; }
            p += 2;
            this.state = 'CHUNK_SIZE';
            continue;
          }
          if (this.state === 'TRAILERS') {
            const e = findCRLF(b, p);
            if (e < 0) { this.buf = b.subarray(p); break; }
            const line = ascii(b, p, e);
            p = e + 2;
            if (line === '') { this._messageComplete(); this.state = 'LINE'; }
            continue;
          }
          if (this.state === 'BODY_EOF') {
            if (p >= b.length) break;
            this._body(b, p, b.length - p);
            p = b.length;
            continue;
          }
          break;
        }
      } catch (e) { return e instanceof Error ? e : new Error(String(e)); }
      return consumed;
    }

    _startLine(line) {
      if (this.type === RESPONSE) {
        const m = /^HTTP\/(\d)\.(\d)\s+(\d{3})\s*(.*)$/.exec(line);
        if (!m) throw new Error('bad status line: ' + line.slice(0, 40));
        this.versionMajor = +m[1]; this.versionMinor = +m[2];
        this.statusCode = +m[3]; this.statusMessage = m[4] || '';
      } else {
        const parts = line.split(' ');
        this.method = Math.max(0, METHODS.indexOf(parts[0]));
        this.url = parts[1] || '/';
        const v = /HTTP\/(\d)\.(\d)/.exec(parts[2] || '');
        if (v) { this.versionMajor = +v[1]; this.versionMinor = +v[2]; }
      }
      this.headers = [];
      const cb = this[HTTPParser.kOnMessageBegin];
      if (cb) cb.call(this);
    }

    _headersDone() {
      let len = null, chunked = false, connClose = this.versionMinor === 0;
      for (let i = 0; i < this.headers.length; i += 2) {
        const k = this.headers[i].toLowerCase(), v = this.headers[i + 1];
        if (k === 'content-length') len = parseInt(v, 10);
        else if (k === 'transfer-encoding' && /chunked/i.test(v)) chunked = true;
        else if (k === 'connection') connClose = /close/i.test(v);
        else if (k === 'upgrade') this.upgrade = true;
      }
      this.shouldKeepAlive = !connClose;
      this.contentLength = len;
      this.chunked = chunked;

      const cb = this[HTTPParser.kOnHeadersComplete];
      let skip = this._skipBody;
      if (cb) {
        // _http_common branches on `typeof method === 'number'`: a number means
        // SERVER (request) and node never reads statusCode. Responses must pass
        // undefined, or res.statusCode comes back null.
        const r = cb.call(this, this.versionMajor, this.versionMinor, this.headers,
          this.type === REQUEST ? this.method : undefined,
          this.type === REQUEST ? this.url : undefined,
          this.statusCode, this.statusMessage,
          this.upgrade, this.shouldKeepAlive);
        // node returns 1 (or 2) to say "this message has no body"
        if (r === 1 || r === 2) skip = true;
      }
      // 1xx/204/304 never have a body, regardless of headers.
      if (this.type === RESPONSE
        && (this.statusCode === 204 || this.statusCode === 304
          || (this.statusCode >= 100 && this.statusCode < 200))) skip = true;

      if (skip) return 'DONE';
      if (chunked) { this.state = 'CHUNK_SIZE'; return 'BODY'; }
      if (len !== null && Number.isFinite(len)) {
        if (len === 0) return 'DONE';
        this.bodyLeft = len; this.state = 'BODY_LEN'; return 'BODY';
      }
      if (this.type === RESPONSE) { this.state = 'BODY_EOF'; return 'BODY'; }
      return 'DONE';
    }

    _body(b, off, len) {
      const cb = this[HTTPParser.kOnBody];
      if (cb && len > 0) cb.call(this, Buffer.from(b.slice(off, off + len)));
    }

    _messageComplete() {
      const cb = this[HTTPParser.kOnMessageComplete];
      if (cb) cb.call(this);
    }
  }

  // Slot indices node writes its callbacks into.
  HTTPParser.kOnMessageBegin = 0;
  HTTPParser.kOnHeaders = 1;
  HTTPParser.kOnHeadersComplete = 2;
  HTTPParser.kOnBody = 3;
  HTTPParser.kOnMessageComplete = 4;
  HTTPParser.kOnExecute = 5;
  HTTPParser.kOnTimeout = 6;
  HTTPParser.REQUEST = REQUEST;
  HTTPParser.RESPONSE = RESPONSE;
  HTTPParser.kLenientNone = 0;
  HTTPParser.kLenientAll = 1023;

  return { HTTPParser, methods: METHODS.slice(), allMethods: METHODS.slice() };
}

function findCRLF(b, from) {
  for (let i = from; i + 1 < b.length; i++) if (b[i] === CR && b[i + 1] === LF) return i;
  return -1;
}
function ascii(b, from, to) {
  let s = '';
  for (let i = from; i < to; i++) s += String.fromCharCode(b[i]);
  return s;
}

module.exports = { makeHttpParser, METHODS };
