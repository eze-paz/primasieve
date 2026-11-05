cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
m() { timeout 295 py -3.12 -u -W ignore sieve_mstate.py "$@" 2>&1 | grep -a "MS\|Error\|Trace\|line "; }
c() { SZ_L2=1e-3 SZ_THREADS=12 timeout 295 py -3.12 -u -W ignore sieve_ctxw.py "$@" 2>&1 | grep -a "CW\|Error\|Trace\|line "; }
m probe 32; c content cca32
m states 32 1000; m states 32 1000; m mix 32 1000
m cca 8; m cca 128
