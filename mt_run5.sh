cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
n() { timeout 295 py -3.12 -u -W ignore sieve_mtnn.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
m() { timeout 295 py -3.12 -u -W ignore sieve_mtest.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
p() { timeout 295 py -3.12 -u -W ignore sieve_mtph.py "$@" 2>&1 | grep -a "PH\|Error\|Trace\|line "; }
for c in books wiki; do for i in 1 2 3 4 5 6 7 8; do out=$(n $c); echo "$out"; echo "$out" | grep -q "done\|Error\|Trace" && break; done; done
p count books; p countb books; p count2 books; p countb wiki
for c in books wiki; do for e in content all; do MT_EVAL=$e p comp $c; MT_EVAL=$e m eval $c; done; done
