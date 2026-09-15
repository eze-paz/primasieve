O=/tmp/probe.out; : > $O
echo -n "which npm-lite: " >> $O; (command -v npm-lite || echo "ABSENT") >> $O 2>&1
echo -n "FOO seen by ash child: " >> $O; FOO=bar /bin/busybox env >> $O 2>&1 | true
echo "--- env as node sees it ---" >> $O
FOO=bar node -e 'console.log(Object.keys(process.env).sort().join(","))' >> $O 2>&1
echo "--- env via busybox (ground truth) ---" >> $O
FOO=bar /bin/busybox env | grep -c FOO >> $O 2>&1
cat $O
echo "PROBE-DONE"
