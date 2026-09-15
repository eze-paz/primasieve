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

echo "--- done ---"
