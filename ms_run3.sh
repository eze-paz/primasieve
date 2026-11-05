cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
m() { timeout 295 py -3.12 -u -W ignore sieve_mstate.py "$@" 2>&1 | grep -a "MS\|Error\|Trace\|line "; }
for i in 1 2 3 4 5 6; do m assignall 32 1000 r; done
MS_ALL=1 m mix 32 1000 r; MS_ALL=1 MS_FORM=sw m mix 32 1000 r
m states 32 4000; m mix 32 4000
m states 8 1000; m states 8 1000; m mix 8 1000
m states 128 1000; m states 128 1000; m mix 128 1000
