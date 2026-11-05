cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
r() { SZ_L2=1e-3 SZ_THREADS=12 timeout 295 py -3.12 -u -W ignore sieve_ctxw.py "$@" 2>&1 | grep -a "CW\|counts\|features\|Error\|Trace\|File"; }
r content c32 w32; r content 32; r content c32; r content w32; r content 32
