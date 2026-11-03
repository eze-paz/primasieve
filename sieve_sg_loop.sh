# SG offers by hypothesis group, each repeated until it accepts nothing (every run < 5 min)
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for g in h1 h23 h4; do
  for i in 1 2 3 4; do
    r=$(SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_sg.py offer sieve_l5_offer.json $g 2>&1 | grep -E "SG |\+ |Error|Trace")
    echo "$g run $i: $r"; echo "$r" | grep -q "0 accepted" && break
  done
done
echo DONE
