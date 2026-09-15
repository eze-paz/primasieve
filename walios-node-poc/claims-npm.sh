O=/tmp/np.out; : > $O
echo -n "npm-lite on PATH: " >> $O; (command -v npm-lite || echo ABSENT) >> $O 2>&1
echo -n "install+require: " >> $O
(npm-lite left-pad@1.3.0 >/dev/null 2>&1 && node -e 'console.log(require("/node_modules/left-pad")("7",3,"0"))') >> $O 2>&1
echo "--- env/fork ---" >> $O
echo -n "keys plain: " >> $O; node -e 'console.log(Object.keys(process.env).sort().join(","))' >> $O 2>&1
echo -n "keys FOO=bar: " >> $O; FOO=bar node -e 'console.log(Object.keys(process.env).sort().join(","))' >> $O 2>&1
echo -n "fork child sees: " >> $O
cat > /tmp/k2.js <<'K'
process.send({ keys: Object.keys(process.env).sort().join(','), foo: process.env.FOO || 'none' });
process.exit(0);
K
FOO=bar node -e 'const k=require("child_process").fork("/tmp/k2.js");k.on("message",m=>console.log(m.keys+" | FOO="+m.foo))' >> $O 2>&1
cat $O
echo "NPM-DONE"
