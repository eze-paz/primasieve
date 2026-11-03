# SA offers: head groups a, b, a again -- each repeated until it accepts nothing (every run < 5 min)
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for g in a b a; do
  for i in 1 2 3 4 5; do
    r=$(SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_attn.py offer sieve_sb_offer.json $g 2>&1 | grep -a -E "SA |\+ |Error|Trace")
    echo "$g run $i: $r"; echo "$r" | grep -q " 0 accepted" && break
  done
done
echo DONE
