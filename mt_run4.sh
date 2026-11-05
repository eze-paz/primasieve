cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
n() { timeout 295 py -3.12 -u -W ignore sieve_mtnn.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
m() { timeout 295 py -3.12 -u -W ignore sieve_mtest.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
n books; n wiki
bash ph_run.sh
for s in 3000000 9000000; do for c in books wiki; do MT_SIZE=$s m count $c; MT_SIZE=$s m eval $c; done; done
