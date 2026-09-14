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
node /usr/bin/npm-lite left-pad@1.3.0

echo "--- require the installed package ---"
echo 'console.log("[" + require("/node_modules/left-pad")("42", 8, "0") + "]")' > /tmp/use.js
node /tmp/use.js

echo "--- done ---"
