# What of the last day's node work is actually live in the REAL walios (terminal/tool),
# not just on the poc page. Run: wget it and sh it inside walios.
O=/tmp/nodefeat.out; : > $O
t() { printf '%s' "$1: " >> $O; shift; "$@" >> $O 2>&1 || echo "(nonzero)" >> $O; }

echo -n "node-present: " >> $O; (command -v node >/dev/null && node -v) >> $O 2>&1

echo -n "check-good: " >> $O
echo 'const x=1' > /tmp/g.js
if node --check /tmp/g.js >/dev/null 2>&1; then echo "OK" >> $O; else echo "FAIL" >> $O; fi
echo -n "check-bad: " >> $O
printf 'function ( {\n' > /tmp/b.js
if node --check /tmp/b.js >/dev/null 2>&1; then echo "FAIL(accepted)" >> $O; else echo "OK" >> $O; fi

echo -n "spawnSync: " >> $O
node -e 'const r=require("child_process").spawnSync("/bin/busybox",["echo","x"]);console.log(r.status===0&&String(r.stdout).trim()==="x"?"OK":"FAIL")' >> $O 2>&1

echo -n "spawn-async: " >> $O
node -e 'const c=require("child_process").spawn("/bin/busybox",["echo","y"]);let o="";c.stdout.on("data",d=>o+=d);c.on("close",()=>console.log(o.trim()==="y"?"OK":"FAIL"))' >> $O 2>&1

echo -n "fork-ipc: " >> $O
cat > /tmp/k.js <<'K'
process.on('message', (m) => { process.send({ r: m.n * 2 }); process.exit(0); });
process.send({ ready: 1 });
K
node -e 'const k=require("child_process").fork("/tmp/k.js");k.on("message",m=>{if(m.ready)return k.send({n:21});console.log(m.r===42?"OK":"FAIL")})' >> $O 2>&1

echo -n "esm: " >> $O
mkdir -p /tmp/e
echo 'export const v = "esm-ok";' > /tmp/e/d.mjs
echo 'import { v } from "./d.mjs"; console.log(v === "esm-ok" ? "OK" : "FAIL");' > /tmp/e/m.mjs
node /tmp/e/m.mjs >> $O 2>&1

echo -n "vm: " >> $O
node -e 'const vm=require("vm");const b=vm.createContext({x:2,o:null});vm.runInContext("o=x*21",b);console.log(vm.runInThisContext("1+1")===2&&b.o===42?"OK":"FAIL")' >> $O 2>&1

echo -n "worker_threads-loads: " >> $O
node -e 'const w=require("worker_threads");console.log(w.isMainThread===true&&w.threadId===0?"OK":"FAIL")' >> $O 2>&1

echo -n "process.exit: " >> $O
node -e 'process.exit(3)' >/dev/null 2>&1; echo $? >> $O

echo -n "env-passthrough: " >> $O
FOO=bar node -e 'console.log(process.env.FOO==="bar"?"OK":"FAIL:"+process.env.FOO)' >> $O 2>&1

echo -n "npm-lite: " >> $O
(npm-lite left-pad@1.3.0 >/dev/null 2>&1 && node -e 'console.log(require("left-pad")("7",3,"0")==="007"?"OK":"FAIL")') >> $O 2>&1

echo -n "tls-module: " >> $O
node -e 'const t=require("tls");console.log(typeof t.connect==="function"?"OK":"FAIL")' >> $O 2>&1

cat $O
echo "NODEFEAT-DONE"
