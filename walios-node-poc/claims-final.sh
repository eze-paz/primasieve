O=/tmp/f.out; : > $O
echo -n "npm-lite: " >> $O; (command -v npm-lite || echo ABSENT) >> $O 2>&1
echo -n "install+run: " >> $O
(npm-lite left-pad@1.3.0 >/dev/null 2>&1 && node -e 'console.log(require("/node_modules/left-pad")("7",3,"0"))') >> $O 2>&1
echo -n "env via -e: " >> $O; FOO=bar node -e 'console.log(process.env.FOO||"MISSING")' >> $O 2>&1
echo -n "env via script: " >> $O; echo 'console.log(process.env.FOO||"MISSING")' > /tmp/e2.js; FOO=bar node /tmp/e2.js >> $O 2>&1
echo -n "fork ipc: " >> $O
cat > /tmp/k3.js <<'K'
process.on('message', (m) => { process.send({ r: m.n * 2 }); process.exit(0); });
process.send({ ready: 1 });
K
node -e 'const k=require("child_process").fork("/tmp/k3.js");k.on("message",m=>{if(m.ready)return k.send({n:21});console.log(m.r===42?"OK":"FAIL")})' >> $O 2>&1
cat $O
echo "FINAL-DONE"
