#!/bin/node
'use strict';
// npm-lite -- install a package from the real npm registry, inside walios.
//
// Not npm. npm itself is 1338 files of pure JS and would run here in principle, but
// it wants concurrency and a lot more of the fs/promises surface. This is the install
// path reduced to its essentials, which is what proves the pieces work:
//
//   registry metadata  -> https over fetch      (shim-http.js)
//   integrity check    -> sha512 of the tarball (shim-crypto.js)
//   decompress         -> DecompressionStream   (shim-zlib.js)
//   unpack             -> tar reader below
//   write              -> real SYS_open/write into the walios filesystem
//
// Usage:  node /usr/bin/npm-lite <pkg>[@version] [--prefix DIR]

const fs = require('fs');
const path = require('path');
const https = require('https');
const zlib = require('zlib');
const crypto = require('crypto');

const REGISTRY = 'https://registry.npmjs.org';

function getJSON(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      if (res.statusCode !== 200) return reject(new Error(url + ' -> HTTP ' + res.statusCode));
      try { resolve(JSON.parse(new TextDecoder().decode(res.body))); }
      catch (e) { reject(e); }
    }).on('error', reject);
  });
}

function getBytes(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      if (res.statusCode !== 200) return reject(new Error(url + ' -> HTTP ' + res.statusCode));
      resolve(res.body);
    }).on('error', reject);
  });
}

// ---- tar --------------------------------------------------------------------
// Only what an npm tarball contains: regular files, directories, and the long-name
// extensions ('L' and the PAX 'x' record) that real packages do hit.
function untar(buf) {
  const td = new TextDecoder();
  const out = [];
  let off = 0;
  let longName = null;
  const str = (o, n) => td.decode(buf.subarray(o, o + n)).replace(/\0.*$/, '').trim();
  while (off + 512 <= buf.length) {
    const hdr = buf.subarray(off, off + 512);
    if (hdr.every((b) => b === 0)) break;
    let name = str(off, 100);
    const prefix = str(off + 345, 155);
    if (prefix) name = prefix + '/' + name;
    const size = parseInt(str(off + 124, 12), 8) || 0;
    const type = String.fromCharCode(hdr[156] || 48);
    off += 512;
    const data = buf.subarray(off, off + size);
    off += Math.ceil(size / 512) * 512;

    if (type === 'L') { longName = td.decode(data).replace(/\0.*$/, ''); continue; }
    if (type === 'x' || type === 'g') {
      const rec = td.decode(data);
      const m = /\d+ path=([^\n]+)\n/.exec(rec);
      if (m) longName = m[1];
      continue;
    }
    if (longName) { name = longName; longName = null; }
    if (type === '0' || type === '\0') out.push({ name, data: data.slice() });
    else if (type === '5') out.push({ name, dir: true });
  }
  return out;
}

function mkdirp(p) {
  const parts = p.split('/').filter(Boolean);
  let cur = '';
  for (const part of parts) {
    cur += '/' + part;
    try { fs.mkdirSync(cur); } catch (e) { if (e.code !== 'EEXIST') throw e; }
  }
}

// npm's integrity is "<algo>-<base64 digest>"
function verify(bytes, integrity) {
  if (!integrity) return 'no integrity field in the registry metadata';
  const [algo, expected] = String(integrity).split('-', 2);
  const got = crypto.createHash(algo).update(bytes).digest('base64');
  if (got !== expected) throw new Error('integrity mismatch: ' + algo + ' expected ' + expected.slice(0, 24) + '..., got ' + got.slice(0, 24) + '...');
  return algo + ' ok';
}

async function install(spec, prefix) {
  const at = spec.lastIndexOf('@');
  const name = at > 0 ? spec.slice(0, at) : spec;
  const wanted = at > 0 ? spec.slice(at + 1) : null;

  const meta = await getJSON(REGISTRY + '/' + name);
  const version = wanted || (meta['dist-tags'] && meta['dist-tags'].latest);
  const v = meta.versions && meta.versions[version];
  if (!v) throw new Error('no such version: ' + name + '@' + version);

  const tgz = await getBytes(v.dist.tarball);
  const integrity = verify(tgz, v.dist.integrity || (v.dist.shasum && 'sha1-' + Buffer.from(v.dist.shasum, 'hex').toString('base64')));
  const tar = await zlib.promises.gunzip(tgz);
  const entries = untar(tar);

  const dest = path.join(prefix, name);
  let written = 0, bytes = 0;
  for (const e of entries) {
    // npm tarballs are rooted at "package/"
    const rel = e.name.replace(/^[^/]+\//, '');
    if (!rel) continue;
    const full = path.join(dest, rel);
    if (e.dir) { mkdirp(full); continue; }
    mkdirp(path.dirname(full));
    fs.writeFileSync(full, e.data);
    written++; bytes += e.data.length;
  }
  return { name, version, dest, written, bytes, tgz: tgz.length, integrity };
}

async function main() {
  const args = process.argv.slice(2);
  let prefix = '/node_modules';
  const specs = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--prefix') { prefix = args[++i]; continue; }
    specs.push(args[i]);
  }
  if (!specs.length) {
    console.error('usage: npm-lite <pkg>[@version] [--prefix DIR]');
    process.exitCode = 1;
    return;
  }
  for (const spec of specs) {
    const r = await install(spec, prefix);
    console.log('installed ' + r.name + '@' + r.version
      + '  (' + r.written + ' files, ' + r.bytes + ' bytes, tarball ' + r.tgz + ', integrity ' + r.integrity + ')');
    console.log('  -> ' + r.dest);
  }
}

main().catch((e) => { console.error('npm-lite: ' + (e && e.message || e)); process.exitCode = 1; });
