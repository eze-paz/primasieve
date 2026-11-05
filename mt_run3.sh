cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve

m() { timeout 295 py -3.12 -u -W ignore sieve_mtest.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
n() { timeout 295 py -3.12 -u -W ignore sieve_mtnn.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
for c in books wiki; do
  for i in $(seq 1 40); do out=$(n $c); echo "$out"; echo "$out" | grep -q "done\|Error\|Trace" && break; done
  m eval $c
done
for s in 3000000 9000000; do for c in books wiki; do MT_SIZE=$s m count $c; MT_SIZE=$s m eval $c; done; done
