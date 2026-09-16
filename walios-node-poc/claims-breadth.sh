# The 23-package breadth result was measured on the POC PAGE with a poc-seeded
# npm-lite. npm-lite now ships as a walios bin, so re-measure it where users are.
# Prints one line per package and a total; the terminal's visible buffer is short, so
# only the summary is echoed at the end.
O=/tmp/br.out; : > $O
run() {
  name="$1"; ver="$2"; expr="$3"; want="$4"
  if ! npm-lite "$name@$ver" >/dev/null 2>&1; then echo "FAIL-INSTALL $name" >> $O; return; fi
  echo "$expr" > /tmp/use.js
  got=$(node /tmp/use.js 2>&1 | tail -1)
  if [ "$got" = "$want" ]; then echo "OK $name" >> $O; else echo "FAIL-RUN $name ($got)" >> $O; fi
}

run lodash 4.17.21 'console.log(require("lodash").camelCase("hello world"))' helloWorld
run ms 2.1.3 'console.log(String(require("ms")("1h")))' 3600000
run semver 7.5.4 'console.log(String(require("semver").satisfies("1.2.3","^1.0.0")))' true
run chalk 4.1.2 'console.log(typeof require("chalk").red)' function
run commander 9.5.0 'const {Command}=require("commander");console.log(typeof new Command().option)' function
run qs 6.11.2 'console.log(require("qs").stringify({a:1,b:"x"}))' a=1&b=x
run uuid 8.3.2 'console.log(String(require("uuid").v4().length))' 36
run js-yaml 4.1.0 'console.log(JSON.stringify(require("js-yaml").load("a: 1")))' '{"a":1}'
run marked 4.3.0 'const m=require("marked");const f=m.marked||m;console.log(String(/<h1/.test(f("# hi"))))' true
run ejs 3.1.9 'console.log(require("ejs").render("<%= n %>",{n:"ok"}))' ok
run dayjs 1.11.10 'console.log(require("dayjs")("2020-01-02").format("YYYY-MM"))' 2020-01
run react 18.2.0 'console.log(typeof require("react").createElement)' function
run ajv 8.12.0 'const A=require("ajv");console.log(String(new A().compile({type:"number"})(5)))' true
run axios 1.6.2 'console.log(typeof require("axios").get)' function
run express 4.18.2 'console.log(typeof require("express")())' function

echo '=== RESULT ==='
echo "ok=$(grep -c '^OK ' $O) fail=$(grep -c '^FAIL' $O)"
grep '^FAIL' $O | head -5
echo "BREADTH-DONE"
