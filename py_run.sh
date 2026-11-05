cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
for i in $(seq 1 90); do s=$(py -3.13 -m kaggle kernels status ezequieldepaz/primasieve-mt-pythia-states 2>&1 | tail -1); echo "$s" | grep -q "RUNNING\|QUEUED" || break; sleep 60; done
echo "kernel: $s"
mkdir -p mtest/kaggle_py/out && py -3.13 -m kaggle kernels output ezequieldepaz/primasieve-mt-pythia-states -p mtest/kaggle_py/out 2>&1 | tail -1
grep -o '"data":"[^"]*' mtest/kaggle_py/out/*.log | grep -v "window" | tail -12
echo "$s" | grep -q COMPLETE || exit 0
y() { timeout 295 py -3.12 -u -W ignore sieve_mtpy.py "$@" 2>&1 | grep -a "PY\|Error\|Trace\|line "; }
m() { timeout 295 py -3.12 -u -W ignore sieve_mtest.py "$@" 2>&1 | grep -a "MT\|Error\|Trace\|line "; }
for c in books wiki; do for e in all content; do MT_EVAL=$e y $c; MT_EVAL=$e m eval $c; done; done
