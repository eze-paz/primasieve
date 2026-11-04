# TX3: held-out and fresh searches for the composed retrieval, then offer on the TX program and score (each run < 5 min)
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for cx in eval fresh; do
  for i in $(seq 1 20); do
    r=$(SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_knn.py search $cx comp 2>&1 | grep -a -E "SC1 search|Error|Trace"); echo "$cx run $i: $r"
    echo "$r" | grep -qE " 0 of|Error|Trace" && break
  done
done
SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_tx3.py offer 2>&1 | grep -a -E "TX3|\+ |Error|Trace"
SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_tx3.py eval 2>&1 | grep -a -E "TX3|Error|Trace"
SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_paq.py sieve_tx3_offer.json > sieve_paq_run_sieve_tx3_offer.txt 2>&1; grep -a -E "^SP scored|Error|Trace" sieve_paq_run_sieve_tx3_offer.txt
SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_diag.py sieve_tx3_offer.json paq 2>&1 | grep -a -E "diag|Error|Trace"
SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_fresh.py build sieve_tx3_offer.json 2>&1 | grep -a -E "SF1|Error|Trace"
SZ_EXACT=1 timeout 295 py -3.12 -W ignore sieve_fresh.py eval sieve_tx3_offer.json 2>&1 | grep -a -E "SF1|Error|Trace"
echo CHAIN DONE
