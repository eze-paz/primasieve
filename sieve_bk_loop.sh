# SK builds: each context's Votes in resumable runs of < 5 min, until none are left
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for cx in fit9K evalK0 evalK1 evalK2 evalK3 evalK4 freshK0 freshK1 freshK2; do
  for i in $(seq 1 12); do
    r=$(SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_bigk.py build $cx 2>&1 | grep -E "SK build|candidate list|Error|Trace|MemoryError")
    echo "$cx run $i: $r"; echo "$r" | grep -q " 0 of" && break; echo "$r" | grep -qE "Error|Trace" && break
  done
done
echo DONE
