O=/tmp/dbg.out; : > $O; rm -f /tmp/.envdbg
echo -n "npm-lite: " >> $O; (command -v npm-lite || echo ABSENT) >> $O 2>&1
FOO=bar node -e 'console.log("keys=" + Object.keys(process.env).sort().join(","))' >> $O 2>&1
echo "--- envdbg ---" >> $O
cat /tmp/.envdbg >> $O 2>&1 || echo "(no envdbg)" >> $O
echo -n "wali env file exists: " >> $O
ls /.wali_env_* >> $O 2>&1 || echo "none" >> $O
cat $O
echo "DBG-DONE"
