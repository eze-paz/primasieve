# SC1 searches: fit9 (both variants) first, then held-out and fresh books; each run < 5 min, resumable
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for job in "eval full" "fresh full"; do
  for i in $(seq 1 15); do
    r=$(SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_knn.py search $job 2>&1 | grep -a -E "SC1 search|Error|Trace")
    echo "$job run $i: $r"; echo "$r" | grep -qE " 0 of|Error|Trace" && break
  done
done
echo DONE
