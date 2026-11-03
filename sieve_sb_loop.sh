# SB training: L then U, resumable runs of < 5 min each, until one pass over the 6M-position sample
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for v in L U; do
  for i in $(seq 1 10); do
    r=$(SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_bilin.py train $v 2>&1 | grep -E "SB train|Error|Trace")
    echo "$v run $i: $r"; echo "$r" | grep -qE "done|Error|Trace" && break
  done
done
echo DONE
