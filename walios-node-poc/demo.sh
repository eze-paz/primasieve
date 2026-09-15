#!/bin/sh
# Driven by index.html: seeded into the guest at /demo.sh and run by busybox ash.
# A real file on purpose -- embedding it meant escaping through JS and then ash.

echo "--- node -v ---"
node -v

echo "--- node -e ---"
node -e 'console.log("hello from node " + process.version + " on " + require("os").hostname())'

echo "--- node writes, busybox reads ---"
node -e 'require("fs").writeFileSync("/tmp/from-node", "written by node")'
cat /tmp/from-node
echo ""

echo "--- node reads what the shell made ---"
echo hello-from-ash > /tmp/from-ash
node -e 'console.log(require("fs").readFileSync("/tmp/from-ash","utf8").trim())'

echo "--- node script.js with args ---"
echo 'console.log("script says: " + process.argv.slice(2).join(","))' > /tmp/s.js
node /tmp/s.js one two

echo "--- redirect to a file ---"
node -e 'console.log("redir-456")' > /tmp/r.txt
cat /tmp/r.txt

echo "--- control: busybox-only pipe ---"
echo pipe-from-echo | grep pipe

echo "--- pipe node into grep ---"
node -e 'console.log("findme-123"); console.log("ignore-me")' | grep findme

echo "--- echo | node  (script from stdin) ---"
echo 'console.log("from-stdin-777")' | node

echo "--- node < file ---"
echo 'console.log("from-redirect-888")' > /tmp/in.js
node < /tmp/in.js

echo "--- exit codes ---"
node -e 'console.log("ok")' && echo "&& worked"
node -e 'process.exitCode = 3'
echo "exit code was $?"

echo "--- npm-lite: install left-pad from the real registry ---"
node /usr/bin/npm-lite minimatch@5.1.6 left-pad@1.3.0

echo "--- require the installed package ---"
echo 'const mm=require("/node_modules/minimatch");const f=mm.minimatch||mm;console.log("[" + require("/node_modules/left-pad")("42", 8, "0") + "] glob=" + f("a/b.js","a/*.js"))' > /tmp/use.js
node /tmp/use.js

echo "--- node http over REAL walios sockets (no fetch) ---"
cat > /tmp/http.js <<'HTTPEOF'
// node's OWN lib/_http_client.js, on our http_parser and tcp_wrap. No fetch.
const http = require('http');
http.get({ hostname: 'example.com', port: 80, path: '/' }, (res) => {
  let n = 0;
  res.on('data', (c) => { n += c.length; });
  res.on('end', () => console.log('HTTP-OVER-SYSCALLS status=' + res.statusCode + ' bytes=' + n));
}).on('error', (e) => console.log('http failed: ' + e.message));
HTTPEOF
node /tmp/http.js

echo "--- net.connect over REAL walios sockets ---"
cat > /tmp/net.js <<'NETEOF'
// node's own lib/net.js on walios socket syscalls -- no fetch, no shim.
const net = require('net');
const CRLF = String.fromCharCode(13, 10);
const s = net.connect(80, 'example.com', () => {
  s.write('HEAD / HTTP/1.0' + CRLF + 'Host: example.com' + CRLF + CRLF);
});
let got = '';
s.setEncoding('utf8');
s.on('data', (d) => { got += d; });
s.on('end', () => console.log('NET-CONNECT-OK ' + got.split(CRLF)[0]));
s.on('error', (e) => console.log('net failed: ' + e.message));
NETEOF
node /tmp/net.js

echo "--- node --check: parse without running ---"
echo 'const x = 1; console.log("SHOULD NOT RUN")' > /tmp/ok.js
node --check /tmp/ok.js && echo "CHECK-OK-SILENT"
echo 'function ( {' > /tmp/bad.js
node --check /tmp/bad.js || echo "CHECK-REJECTED-BAD-SOURCE"

echo "--- child_process over posix_spawn ---"
cat > /tmp/cp.js <<'CPEOF'
const cp = require('child_process');
const r = cp.spawnSync('/bin/busybox', ['echo', 'from-child']);
console.log('CP-STATUS:' + r.status + ' OUT:' + String(r.stdout).trim());
const s2 = cp.spawnSync('/bin/busybox', ['sh', '-c', 'echo O; echo E 1>&2']);
console.log('CP-SPLIT:' + String(s2.stdout).trim() + '/' + String(s2.stderr).trim());
const s3 = cp.spawnSync('/bin/busybox', ['sh', '-c', 'exit 7']);
console.log('CP-EXIT:' + s3.status);
const s4 = cp.spawnSync('/bin/busybox', ['cat'], { input: 'piped-in' });
console.log('CP-STDIN:' + String(s4.stdout).trim());
console.log('CP-EXECSYNC:' + cp.execSync('echo alpha').toString().trim());
// walios resolves ANY unresolvable path to a busybox applet by basename, so a
// missing program is never ENOENT here the way it is on Linux -- it starts
// busybox, which exits 127 with "applet not found". Asserting ENOENT would be
// asserting Linux, not this platform.
const s5 = cp.spawnSync('/tmp/definitely-not-here', []);
console.log('CP-MISSING:' + s5.status + ':' + (/applet not found/.test(String(s5.stderr)) ? 'applet-not-found' : 'other'));
const s6 = cp.spawnSync('/bin/nope-xyz', []);
console.log('CP-BIN-APPLET:' + s6.status);   // busybox: applet not found
CPEOF
node /tmp/cp.js

echo "--- async child_process.spawn ---"
cat > /tmp/cpa.js <<'CPAEOF'
const cp = require('child_process');
const c = cp.spawn('/bin/busybox', ['sh', '-c', 'echo async-out; echo async-err 1>&2; exit 3']);
let out = '', err = '';
c.stdout.on('data', (d) => { out += d; });
c.stderr.on('data', (d) => { err += d; });
c.on('close', (code) => {
  console.log('SPAWN-CLOSE:' + code + ' OUT:' + out.trim() + ' ERR:' + err.trim());
  // stdin, then a second child, to prove the handle wiring both ways
  const c2 = cp.spawn('/bin/busybox', ['cat']);
  let got = '';
  c2.stdout.on('data', (d) => { got += d; });
  c2.on('close', () => console.log('SPAWN-STDIN:' + got.trim()));
  c2.stdin.write('async-piped');
  c2.stdin.end();
});
CPAEOF
node /tmp/cpa.js

echo "--- ESM ---"
mkdir -p /tmp/esm
cat > /tmp/esm/dep.mjs <<'D1'
export const greet = (n) => 'hello ' + n;
export let counter = 0;
export function bump() { counter++; }
D1
cat > /tmp/esm/lib.cjs <<'D2'
module.exports = { fromCjs: 'cjs-value' };
D2
cat > /tmp/esm/main.mjs <<'D3'
import { greet, counter, bump } from './dep.mjs';
import * as fsns from 'node:fs';
import cjs from './lib.cjs';
bump(); bump();
console.log('ESM-BASIC:' + greet('esm'));
console.log('ESM-LIVE:' + counter);
console.log('ESM-BUILTIN:' + (typeof fsns.readFileSync));
console.log('ESM-CJS:' + cjs.fromCjs);
const dyn = await import('./dep.mjs');
console.log('ESM-DYNAMIC:' + dyn.greet('dyn'));
D3
node /tmp/esm/main.mjs

echo "--- a REAL ESM-only package from the registry ---"
npm-lite nanoid@5.0.4 >/dev/null 2>&1
cat > /tmp/esm/pkg.mjs <<'D4'
import { nanoid, customAlphabet } from 'nanoid';
const id = nanoid();
console.log('ESM-PKG:' + id.length + ':' + (typeof customAlphabet));
D4
node /tmp/esm/pkg.mjs

echo "--- done ---"
