cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
m() { timeout 295 py -3.12 -u -W ignore sieve_mstate.py "$@" 2>&1 | grep -a "MS\|Error\|Trace\|line "; }
m states 32 1000; m mix 32 1000; MS_FORM=w m mix 32 1000; MS_FORM=sw m mix 32 1000
m refine 32 1000; m mix 32 1000 r; MS_FORM=sw m mix 32 1000 r
