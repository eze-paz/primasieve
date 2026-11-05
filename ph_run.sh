cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
p() { timeout 295 py -3.12 -u -W ignore sieve_mtph.py "$@" 2>&1 | grep -a "PH\|Error\|Trace\|line \|Memory"; }
m() { timeout 295 py -3.12 -u -W ignore sieve_mtest.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
for c in books wiki; do p count $c; p count2 $c; for e in content all; do MT_EVAL=$e p comp $c; MT_EVAL=$e m eval $c; done; done
