rm -f /tmp/nl.log
NPM_LITE_DEBUG=/tmp/nl.log npm-lite express@4.18.2 > /tmp/ex.log 2>&1; RC=$?
echo "=== RESULT ==="
echo "rc=$RC dirs=$(ls /node_modules | wc -l) traces=$(wc -l < /tmp/nl.log)"
tail -3 /tmp/nl.log
head -1 /tmp/nl.log
echo "EX3-DONE"
